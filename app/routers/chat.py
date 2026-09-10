import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import (
    ADMIN,
    CLIENT,
    COACH,
    SUPERADMIN,
    _coach_client_ids,
    _get_coach_detail,
    _user_role_ids,
    get_current_user,
    get_db,
)
from app.core.responses import send_error, send_response
from app.core.security import decode_token
from app.core.ws_manager import manager
from app.database import SessionLocal
from app.models.chat import ChatConversation, ChatMessage, ChatParticipant
from app.models.user import RoleUser, User, UserDetail

router = APIRouter(prefix="/chat", tags=["Chat"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    type: str  # 'individual' | 'group'
    participant_user_ids: Optional[list[int]] = None
    name: Optional[str] = None
    # Grupo por REGLA: 'mis_clientes' | 'mis_coaches'. Sin esto, la lista de
    # participantes es la que se manda y no cambia sola.
    audience: Optional[str] = None
    # Difusión: solo escribe quien lo crea. Por defecto lo son los grupos por
    # regla, porque "un mensaje a todos mis clientes" no es una tertulia.
    broadcast: Optional[bool] = None
    # Nombre viejo de `audience`, de cuando solo lo usaba el admin. Se sigue
    # aceptando para no romper a quien lo mandara.
    target: Optional[str] = None
    # Qué clase de grupo es: 'equipo' | 'comunidad' | 'seguimiento'. Determina
    # quién puede estar dentro. Ver TIPOS_GRUPO.
    tipo: Optional[str] = None


class MessageCreate(BaseModel):
    # Un mensaje puede ser solo un archivo, así que el texto no es obligatorio.
    content: Optional[str] = None
    attachment_url: Optional[str] = None
    attachment_name: Optional[str] = None
    attachment_type: Optional[str] = None
    attachment_size: Optional[int] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _user_detail(db: Session, user_id: int) -> Optional[UserDetail]:
    return db.query(UserDetail).filter(UserDetail.user_id == user_id).first()


def _chat_apagado(db: Session, user_id: int) -> bool:
    """Si a este CLIENTE su coach le ha desactivado el chat.

    El interruptor existía en la ficha del cliente pero no lo miraba nadie: el
    coach lo apagaba, veía "Chat desactivado" y su cliente seguía pudiendo
    escribirle. Un interruptor que no hace nada es peor que no tenerlo.

    Solo afecta a quien ESCRIBE siendo cliente. El coach sigue pudiendo
    mandarle cosas: apagarlo es dejar de recibir mensajes suyos, no dejar de
    poder darle su plan.
    """
    es_cliente = db.query(RoleUser).filter(
        RoleUser.user_id == user_id, RoleUser.role_id == CLIENT).first() is not None
    if not es_cliente:
        return False
    detail = _user_detail(db, user_id)
    return bool(detail) and detail.chat_enabled is False


TIPOS_GRUPO = ("equipo", "comunidad", "seguimiento")


def _validar_tipo_grupo(tipo: str, tipo_conv: str, ids: list, yo: int, db: Session) -> Optional[str]:
    """Comprueba que la gente elegida encaja con la clase de grupo.

    Tres clases, y no son intercambiables:

      · `equipo`      — solo el equipo. Meter a un cliente en el grupo interno
                        le deja leer cómo se habla de los clientes.
      · `comunidad`   — el coach con sus clientes: un reto, un grupo de ánimo.
                        OJO: aquí los clientes SÍ se ven entre ellos, al revés
                        que en el aviso a todos, que va uno a uno. Es lo que se
                        pidió para los retos, pero conviene tenerlo escrito.
      · `seguimiento` — el caso de un cliente con quien lo lleva: hace falta al
                        menos un cliente y al menos alguien del equipo, o no es
                        un seguimiento, es otra cosa.
    """
    if tipo not in TIPOS_GRUPO:
        return f"Tipo de grupo no válido. Admitidos: {', '.join(TIPOS_GRUPO)}"
    if tipo_conv != "group":
        return "Solo un grupo puede tener tipo"

    otros = [uid for uid in ids if uid != yo]
    if not otros:
        return "Elige a quién va el grupo"

    clientes, equipo = [], []
    for uid in otros:
        (clientes if CLIENT in _user_role_ids(uid, db) else equipo).append(uid)

    if tipo == "equipo" and clientes:
        return "Un grupo de equipo no puede llevar clientes dentro"
    if tipo == "comunidad" and not clientes:
        return "Una comunidad de clientes necesita al menos un cliente"
    if tipo == "seguimiento":
        if not clientes:
            return "Un seguimiento necesita el cliente al que se hace seguimiento"
        if not equipo:
            return "Un seguimiento necesita a alguien del equipo además del cliente"
    return None


def _etiqueta_equipo(db: Session, detalle) -> Optional[str]:
    """El oficio de un miembro del equipo: "Entrenador", "Nutricionista"…"""
    if not detalle:
        return None
    from app.models.team_member import TeamMember
    tm = (
        db.query(TeamMember)
        .filter(TeamMember.user_detail_id == detalle.id)
        .order_by(TeamMember.id.desc())
        .first()
    )
    return (tm.role_label or None) if tm else None


def _serialize_message(msg: ChatMessage, db: Session) -> dict:
    sender_detail = _user_detail(db, msg.sender_user_id)
    sender_name = ""
    sender_photo = None
    if sender_detail:
        sender_name = f"{sender_detail.name} {sender_detail.last_name or ''}".strip()
        sender_photo = sender_detail.photo
    elif msg.sender:
        sender_name = msg.sender.name
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "content": msg.content,
        "sender_user_id": msg.sender_user_id,
        "sender_name": sender_name,
        "sender_photo": sender_photo,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "attachment_url": msg.attachment_url,
        "attachment_name": msg.attachment_name,
        "attachment_type": msg.attachment_type,
        "attachment_size": msg.attachment_size,
    }


def _serialize_conversation(conv: ChatConversation, current_user_id: int, db: Session) -> dict:
    participant_user_ids = [p.user_id for p in conv.participants]

    # En un grupo de difusión, quien recibe no ve a los demás: son clientes que
    # no se conocen entre sí y que no eligieron estar juntos. Solo se le enseña
    # quién le escribe (y él mismo).
    es_creador = conv.created_by_user_id == current_user_id
    if conv.broadcast and not es_creador:
        participant_user_ids = [uid for uid in participant_user_ids
                                if uid in (conv.created_by_user_id, current_user_id)]

    participants_info = []
    for uid in participant_user_ids:
        detail = _user_detail(db, uid)
        if detail:
            participants_info.append({
                "user_id": uid,
                "name": f"{detail.name} {detail.last_name or ''}".strip(),
                "photo": detail.photo,
                # Para que el chat pueda decir si está activo y llevar a la
                # ficha sin tener que pedir el cliente aparte.
                "user_detail_id": detail.id,
                "chat_enabled": detail.chat_enabled,
                # Para poder agrupar a la gente del grupo por lo que es y
                # enseñar su oficio, igual que al montarlo.
                "rol": "cliente" if CLIENT in _user_role_ids(uid, db) else "coach",
                "etiqueta": _etiqueta_equipo(db, detail),
            })
        else:
            u = db.query(User).filter(User.id == uid).first()
            if u:
                participants_info.append({"user_id": uid, "name": u.name, "photo": None,
                                          "user_detail_id": None, "chat_enabled": None,
                                          "rol": "coach", "etiqueta": None})

    last_msg = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conv.id)
        .order_by(ChatMessage.created_at.desc())
        .first()
    )
    last_message = _serialize_message(last_msg, db) if last_msg else None

    return {
        "id": conv.id,
        "type": conv.type,
        "name": conv.name,
        "created_by_user_id": conv.created_by_user_id,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        "participants": participants_info,
        # Cuánta gente hay de verdad. En difusión solo lo sabe quien lo creó:
        # a quien recibe no le dice nada útil y sí cuenta de más sobre otros.
        "participantes_total": len(conv.participants) if (es_creador or not conv.broadcast) else None,
        "audience": conv.audience,
        "broadcast": bool(conv.broadcast),
        # Lo que la pantalla necesita para decidir si enseña el cuadro de
        # escribir o el botón de "responder en privado".
        "puedo_escribir": (not conv.broadcast) or es_creador,
        "last_message": last_message,
    }


def _get_client_user_ids_for_coach(coach_user_id: int, db: Session) -> list[int]:
    coach_detail = _get_coach_detail(coach_user_id, db)
    if not coach_detail:
        return []
    client_detail_ids = _coach_client_ids(coach_detail.id, db)
    result = []
    for detail_id in client_detail_ids:
        detail = db.query(UserDetail).filter(UserDetail.id == detail_id).first()
        if detail:
            result.append(detail.user_id)
    return result


def _get_all_coach_user_ids(db: Session) -> list[int]:
    """TODOS los coaches de la plataforma. Solo vale para el super-admin.

    Estaba usándose para el grupo "todos los coaches" de cualquier ADMIN, que
    es de una organización concreta: metía en el mismo grupo a gente de cuentas
    distintas, y en un grupo todos se leen entre sí.
    """
    rows = db.query(RoleUser).filter(RoleUser.role_id == COACH).all()
    return [r.user_id for r in rows]


def _get_all_client_user_ids(db: Session) -> list[int]:
    """TODOS los clientes de la plataforma. Ver la nota de arriba."""
    rows = db.query(RoleUser).filter(RoleUser.role_id == CLIENT).all()
    return [r.user_id for r in rows]


# ── A quién alcanza cada uno ─────────────────────────────────────────────────
# El chat cruza la frontera entre cuentas si se le deja: un grupo mete a varias
# personas a leerse entre sí. Todo lo de aquí abajo responde a la misma
# pregunta —¿con quién puede hablar este usuario?— y la responde una vez.

def _mi_organizacion(user_id: int, db: Session):
    """La organización de la que este usuario es dueño o miembro, o None."""
    from app.models.organization import Organization, OrganizationMember
    from app.models.team_member import TeamMember

    detail = _user_detail(db, user_id)
    if not detail:
        return None
    org = db.query(Organization).filter(Organization.owner_id == detail.id).first()
    if org:
        return org
    fila = db.query(TeamMember).filter(
        TeamMember.user_detail_id == detail.id,
        TeamMember.organization_id.isnot(None),
    ).first()
    if fila:
        return db.query(Organization).filter(Organization.id == fila.organization_id).first()
    miembro = db.query(OrganizationMember).filter(
        OrganizationMember.user_detail_id == detail.id
    ).first()
    if miembro:
        return db.query(Organization).filter(Organization.id == miembro.organization_id).first()
    return None


def _user_ids_de_detalles(detail_ids, db: Session) -> list[int]:
    if not detail_ids:
        return []
    filas = db.query(UserDetail).filter(UserDetail.id.in_(list(detail_ids))).all()
    return [d.user_id for d in filas if d.user_id]


def _coaches_de_la_organizacion(org, db: Session) -> list[int]:
    """El dueño y su equipo. Sin organización, nadie."""
    from app.models.organization import OrganizationMember
    from app.models.team_member import TeamMember

    if not org:
        return []
    detail_ids = {org.owner_id}
    detail_ids.update(
        m.user_detail_id for m in
        db.query(OrganizationMember).filter(OrganizationMember.organization_id == org.id).all()
    )
    detail_ids.update(
        t.user_detail_id for t in
        db.query(TeamMember).filter(TeamMember.organization_id == org.id).all()
        if t.user_detail_id
    )
    return _user_ids_de_detalles(detail_ids, db)


def _clientes_de_la_organizacion(org, db: Session) -> list[int]:
    """Los clientes de todos los coaches de esa organización."""
    if not org:
        return []
    ids: set[int] = set()
    for coach_user_id in _coaches_de_la_organizacion(org, db):
        ids.update(_get_client_user_ids_for_coach(coach_user_id, db))
    return list(ids)


def _resolver_audiencia(audiencia: str, user_id: int, db: Session) -> list[int]:
    """Quién está HOY en un grupo definido por una regla.

    Se resuelve cada vez, no al crearlo: es lo que hace que un cliente nuevo
    entre solo en "mis clientes" y que quien se va deje de recibir.
    """
    roles = _user_role_ids(user_id, db)
    org = _mi_organizacion(user_id, db)

    if audiencia == "mis_coaches":
        # El super-admin sin organización propia ES la plataforma: sus coaches
        # son todos. Con organización, la suya, como cualquier otro.
        if SUPERADMIN in roles and not org:
            return [uid for uid in _get_all_coach_user_ids(db) if uid != user_id]
        return [uid for uid in _coaches_de_la_organizacion(org, db) if uid != user_id]

    if audiencia == "mis_clientes":
        if COACH in roles and ADMIN not in roles and SUPERADMIN not in roles:
            # Un coach a secas: los suyos, no los de sus compañeros.
            return _get_client_user_ids_for_coach(user_id, db)
        if SUPERADMIN in roles and not org:
            return _get_all_client_user_ids(db)
        return _clientes_de_la_organizacion(org, db)

    return []


AUDIENCIAS = ("mis_clientes", "mis_coaches")

# Los nombres que mandaba la pantalla antes. "all_coaches" no lo entendía el
# backend y caía en el `else`, que eran CLIENTES: pulsar "todos los coaches"
# creaba un grupo con todos los clientes.
AUDIENCIA_VIEJA = {
    "clients": "mis_clientes",
    "my_clients": "mis_clientes",
    "all_clients": "mis_clientes",
    "coaches": "mis_coaches",
    "all_coaches": "mis_coaches",
}


def _coaches_de_un_cliente(user_id: int, db: Session) -> list[int]:
    """Los coaches a los que está asignado este cliente."""
    from app.models.user import UserParent

    detalle = _user_detail(db, user_id)
    if not detalle:
        return []
    padres = db.query(UserParent).filter(UserParent.user_detail_id == detalle.id).all()
    return _user_ids_de_detalles([p.parent_user_detail_id for p in padres], db)


def _alcance(user_id: int, db: Session) -> set[int]:
    """Con quién puede abrir conversación este usuario.

    Sin esto, `participant_user_ids` aceptaba cualquier id: se podía montar un
    grupo con el cliente de otra cuenta metiendo su número a mano.
    """
    roles = _user_role_ids(user_id, db)
    org = _mi_organizacion(user_id, db)
    if SUPERADMIN in roles and not org:
        return set()   # la plataforma habla con quien haga falta; se comprueba aparte

    # Un cliente habla con SU coach y con nadie más. Es quien menos alcance
    # tiene y el que primero se rompe si esto se olvida: sin él, responder al
    # mensaje de su coach le respondía que no puede.
    if CLIENT in roles and COACH not in roles and ADMIN not in roles:
        return set(_coaches_de_un_cliente(user_id, db))

    alcance: set[int] = set()
    alcance.update(_coaches_de_la_organizacion(org, db))
    if COACH in roles and ADMIN not in roles and SUPERADMIN not in roles:
        alcance.update(_get_client_user_ids_for_coach(user_id, db))
    else:
        alcance.update(_clientes_de_la_organizacion(org, db))
    alcance.discard(user_id)
    return alcance


def _sincronizar_audiencia(conv: ChatConversation, db: Session) -> None:
    """Pone al día los participantes de un grupo definido por una regla.

    Se guardan filas de participantes igual que en los grupos hechos a mano
    —así el resto del chat (no leídos, listados, avisos) sigue funcionando sin
    saber que este grupo es especial— pero se recalculan al abrirlo.
    """
    if not conv.audience:
        return
    deberian = set(_resolver_audiencia(conv.audience, conv.created_by_user_id, db))
    deberian.add(conv.created_by_user_id)

    actuales = {p.user_id: p for p in conv.participants}
    ahora = datetime.utcnow()

    for uid in deberian - set(actuales):
        db.add(ChatParticipant(conversation_id=conv.id, user_id=uid, joined_at=ahora))
    for uid in set(actuales) - deberian:
        db.delete(actuales[uid])
    if deberian != set(actuales):
        db.commit()


def _grupos_por_regla_que_me_tocan(user_id: int, db: Session) -> list:
    """Grupos por regla creados por gente de mi cuenta.

    Un grupo por regla solo se recalculaba cuando lo abría QUIEN LO CREÓ. Un
    cliente dado de alta después de montar "mis clientes" no entraba en él
    hasta que su coach volviera a mirar su lista de chats: mientras tanto el
    grupo existía, los demás hablaban dentro y a él no le aparecía por ningún
    lado. Se recalcula también desde este lado, que es el que se queda fuera.
    """
    relacionados = set(_alcance(user_id, db))
    relacionados.update(_coaches_de_un_cliente(user_id, db))
    relacionados.discard(user_id)
    if not relacionados:
        return []
    return (
        db.query(ChatConversation)
        .filter(
            ChatConversation.audience.isnot(None),
            ChatConversation.created_by_user_id.in_(relacionados),
        )
        .all()
    )


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.get("/contactos", summary="Con quién puedo hablar",
            description="Las personas de tu cuenta con las que puedes abrir un chat o "
                        "montar un grupo: tu equipo y tus clientes.")
def listar_contactos(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """La lista para armar un grupo a mano.

    Es la misma que valida el servidor al crear la conversación: si aquí sale
    alguien, se puede; si no sale, tampoco se cuela mandando su id a mano.
    """
    roles = _user_role_ids(current_user.id, db)
    ids = _alcance(current_user.id, db)

    # El super-admin sin organización propia es la plataforma: su lista es todo
    # el equipo y todos los clientes.
    if SUPERADMIN in roles and not ids:
        ids = set(_get_all_coach_user_ids(db)) | set(_get_all_client_user_ids(db))
        ids.discard(current_user.id)

    fuera = []
    for uid in ids:
        detalle = _user_detail(db, uid)
        usuario = db.query(User).filter(User.id == uid).first()
        if not usuario:
            continue
        sus_roles = _user_role_ids(uid, db)
        fuera.append({
            "user_id": uid,
            "name": (f"{detalle.name} {detalle.last_name or ''}".strip()
                     if detalle else usuario.name),
            "email": usuario.email,
            "photo": detalle.photo if detalle else None,
            # Para que la pantalla pueda agrupar por rol al elegir.
            "rol": "cliente" if CLIENT in sus_roles else "coach",
            # Lo que hace cada uno en el equipo ("Entrenador", "Nutricionista"…).
            # Al montar un grupo de seguimiento se elige por el oficio, no por
            # el nombre: sin esto hay que acordarse de quién es quién.
            "etiqueta": _etiqueta_equipo(db, detalle),
        })
    fuera.sort(key=lambda c: (c["rol"], (c["name"] or "").lower()))
    return send_response(fuera, "OK")


@router.get("/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Antes de mirar en cuáles estoy, se ponen al día los grupos por regla de
    # mi cuenta: si no, quien entra después de crearlos no los ve nunca.
    for grupo in _grupos_por_regla_que_me_tocan(current_user.id, db):
        _sincronizar_audiencia(grupo, db)

    participations = (
        db.query(ChatParticipant)
        .filter(ChatParticipant.user_id == current_user.id)
        .all()
    )
    conv_ids = [p.conversation_id for p in participations]
    convs = (
        db.query(ChatConversation)
        .filter(ChatConversation.id.in_(conv_ids))
        .order_by(ChatConversation.updated_at.desc())
        .all()
    )
    # Los grupos por regla se recalculan al abrir la lista: es lo que hace que
    # un cliente nuevo aparezca en "mis clientes" sin que nadie lo añada.
    for c in convs:
        if c.audience and c.created_by_user_id == current_user.id:
            _sincronizar_audiencia(c, db)
    data = [_serialize_conversation(c, current_user.id, db) for c in convs]
    return send_response(data, "Conversaciones obtenidas")


@router.post("/conversations")
def create_conversation(
    body: ConversationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user_roles = _user_role_ids(current_user.id, db)

    if body.type not in ("individual", "group"):
        return send_error("Tipo debe ser 'individual' o 'group'", code=400)

    if body.type == "group" and CLIENT in user_roles and COACH not in user_roles and ADMIN not in user_roles and SUPERADMIN not in user_roles:
        return send_error("Los clientes no pueden crear grupos", code=403)

    participant_ids: list[int] = list(body.participant_user_ids or [])

    # ¿Grupo por regla o lista a mano? El nombre viejo (`target`) se traduce.
    audiencia = body.audience or AUDIENCIA_VIEJA.get(body.target or "")
    if audiencia and audiencia not in AUDIENCIAS:
        return send_error(f"Audiencia no válida. Admitidas: {', '.join(AUDIENCIAS)}", code=400)
    if audiencia and body.type != "group":
        return send_error("Solo un grupo puede tener audiencia", code=400)

    if audiencia:
        participant_ids = _resolver_audiencia(audiencia, current_user.id, db)
        if not participant_ids:
            return send_error(
                "Todavía no hay nadie en ese grupo: "
                + ("no tienes clientes asignados." if audiencia == "mis_clientes"
                   else "no tienes coaches en tu equipo."), code=400)
    elif body.type == "group" and not participant_ids:
        return send_error("Elige a quién va el grupo", code=400)

    # Una conversación individual es con OTRA persona. Sin esto se podía crear
    # una consigo mismo —una fila en la lista que no lleva a nadie— pasando la
    # lista vacía o el propio id.
    if body.type == "individual" and not [
            uid for uid in participant_ids if uid != current_user.id]:
        return send_error("Elige con quién quieres hablar", code=400)

    # Nadie puede montar un grupo con gente que no es suya. Antes se aceptaba
    # cualquier id: bastaba con escribir el número del cliente de otra cuenta.
    if not audiencia:
        permitidos = _alcance(current_user.id, db)
        es_plataforma = SUPERADMIN in user_roles and not permitidos
        fuera = [] if es_plataforma else [
            uid for uid in participant_ids if uid != current_user.id and uid not in permitidos]
        if fuera:
            return send_error("Hay personas en la lista que no son de tu cuenta", code=403)

    # Cada clase de grupo admite a unos y no a otros, y conviene comprobarlo
    # aquí y no solo en la pantalla: quien manda la petición a mano se saltaría
    # el filtro y metería a un cliente en el grupo interno del equipo.
    if body.tipo:
        error = _validar_tipo_grupo(body.tipo, body.type, participant_ids, current_user.id, db)
        if error:
            return send_error(error, code=422)

    if current_user.id not in participant_ids:
        participant_ids.append(current_user.id)

    # Un grupo por regla nace de difusión: "un mensaje a todos mis clientes" no
    # es una tertulia entre clientes que no se conocen. Uno hecho a mano, no.
    difusion = body.broadcast if body.broadcast is not None else bool(audiencia)

    now = datetime.utcnow()
    conv = ChatConversation(
        id=str(uuid.uuid4()),
        type=body.type,
        name=body.name,
        audience=audiencia,
        broadcast=bool(difusion) and body.type == "group",
        created_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(conv)
    db.flush()

    for uid in set(participant_ids):
        db.add(ChatParticipant(
            conversation_id=conv.id,
            user_id=uid,
            joined_at=now,
        ))

    db.commit()
    db.refresh(conv)
    return send_response(_serialize_conversation(conv, current_user.id, db), "Conversación creada")


@router.get("/con/{user_id}", summary="La conversación con esa persona",
            description="Devuelve la conversación individual con ese usuario, creándola si todavía no existe.")
def conversacion_con(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Abrir el chat con alguien sin tener que buscarlo en la lista.

    Hacía falta para poder chatear desde la ficha del cliente, pero arregla
    algo más: hasta ahora cada pantalla se buscaba la conversación entre las
    que tuviera cargadas y, si no la encontraba, creaba otra. Con la lista
    paginada eso significa que basta con no haber cargado la página donde
    estaba para acabar con dos conversaciones con la misma persona — y los
    mensajes repartidos entre las dos, cada uno creyendo que el otro no
    contesta.

    Aquí la busca la base, que las tiene todas.
    """
    if user_id == current_user.id:
        return send_error("Elige con quién quieres hablar", code=400)

    otro = db.query(User).filter(User.id == user_id).first()
    if not otro:
        return send_error("Usuario no encontrado", code=404)

    # De quién es: sin esto bastaba con cambiar el número de la URL para
    # abrirle un chat al cliente de otra cuenta.
    roles = _user_role_ids(current_user.id, db)
    permitidos = _alcance(current_user.id, db)
    if not (SUPERADMIN in roles and not permitidos) and user_id not in permitidos:
        return send_error("Esa persona no es de tu cuenta", code=403)

    mias = {p.conversation_id for p in db.query(ChatParticipant).filter(
        ChatParticipant.user_id == current_user.id).all()}
    conv = None
    if mias:
        for c in db.query(ChatConversation).filter(
                ChatConversation.id.in_(mias),
                ChatConversation.type == "individual").all():
            if user_id in {p.user_id for p in c.participants}:
                conv = c
                break

    creada = False
    if conv is None:
        now = datetime.utcnow()
        conv = ChatConversation(
            id=str(uuid.uuid4()), type="individual", name=None,
            created_by_user_id=current_user.id, created_at=now, updated_at=now)
        db.add(conv)
        db.flush()
        db.add(ChatParticipant(conversation_id=conv.id, user_id=current_user.id, joined_at=now))
        db.add(ChatParticipant(conversation_id=conv.id, user_id=user_id, joined_at=now))
        db.commit()
        db.refresh(conv)
        creada = True

    datos = _serialize_conversation(conv, current_user.id, db)
    datos["creada"] = creada
    return send_response(datos, "OK")


@router.get("/conversations/{conv_id}/messages")
def list_messages(
    conv_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    part = (
        db.query(ChatParticipant)
        .filter(
            ChatParticipant.conversation_id == conv_id,
            ChatParticipant.user_id == current_user.id,
        )
        .first()
    )
    if not part:
        return send_error("Conversación no encontrada", code=404)

    total = db.query(ChatMessage).filter(ChatMessage.conversation_id == conv_id).count()
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.created_at.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    data = [_serialize_message(m, db) for m in messages]
    return send_response({"messages": data, "total": total, "page": page, "per_page": per_page}, "Mensajes obtenidos")


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Total de mensajes no leídos del usuario y desglose por conversación.

    'No leído' = mensaje de otra persona con created_at posterior a la
    última vez que el usuario abrió esa conversación (last_read_at); si
    nunca la abrió, se usa joined_at como referencia.
    """
    parts = (
        db.query(ChatParticipant)
        .filter(ChatParticipant.user_id == current_user.id)
        .all()
    )
    total = 0
    per_conversation = []
    for part in parts:
        threshold = part.last_read_at or part.joined_at
        q = db.query(ChatMessage).filter(
            ChatMessage.conversation_id == part.conversation_id,
            ChatMessage.sender_user_id != current_user.id,
        )
        if threshold is not None:
            q = q.filter(ChatMessage.created_at > threshold)
        n = q.count()
        if n:
            total += n
            per_conversation.append({"conversation_id": part.conversation_id, "count": n})
    return send_response({"total": total, "conversations": per_conversation}, "OK")


@router.post("/conversations/{conv_id}/read")
def mark_conversation_read(
    conv_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Marca la conversación como leída para el usuario (limpia su badge)."""
    part = (
        db.query(ChatParticipant)
        .filter(
            ChatParticipant.conversation_id == conv_id,
            ChatParticipant.user_id == current_user.id,
        )
        .first()
    )
    if not part:
        return send_error("Conversación no encontrada", code=404)
    part.last_read_at = datetime.utcnow()
    db.commit()
    return send_response(None, "Conversación marcada como leída")


@router.post("/conversations/{conv_id}/messages")
async def send_message_rest(
    conv_id: str,
    body: MessageCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    part = (
        db.query(ChatParticipant)
        .filter(
            ChatParticipant.conversation_id == conv_id,
            ChatParticipant.user_id == current_user.id,
        )
        .first()
    )
    if not part:
        return send_error("Conversación no encontrada", code=404)

    conv_previa = db.query(ChatConversation).filter(ChatConversation.id == conv_id).first()
    if conv_previa and conv_previa.broadcast and conv_previa.created_by_user_id != current_user.id:
        return send_error(
            "En este grupo solo escribe quien lo creó. Respóndele por privado.", code=403)

    if _chat_apagado(db, current_user.id):
        return send_error("Tu coach ha desactivado el chat.", code=403)

    texto = (body.content or "").strip()
    # Un mensaje vacío del todo no es un mensaje: sin esto, darle a Enviar sin
    # escribir nada dejaba una burbuja en blanco en la conversación de los dos.
    if not texto and not body.attachment_url:
        return send_error("El mensaje está vacío", code=422)

    now = datetime.utcnow()
    msg = ChatMessage(
        id=str(uuid.uuid4()),
        conversation_id=conv_id,
        sender_user_id=current_user.id,
        content=texto or None,
        created_at=now,
        attachment_url=body.attachment_url,
        attachment_name=body.attachment_name,
        attachment_type=body.attachment_type,
        attachment_size=body.attachment_size,
    )
    db.add(msg)

    conv = db.query(ChatConversation).filter(ChatConversation.id == conv_id).first()
    if conv:
        conv.updated_at = now

    db.commit()
    db.refresh(msg)

    data = _serialize_message(msg, db)

    # Notificar en tiempo real a los demás participantes (p. ej. el coach)
    # por WebSocket, igual que el endpoint WS. Sin esto, quien envía por
    # REST (la zona del cliente) no notificaba al destinatario conectado.
    recipient_ids = [
        p.user_id for p in
        db.query(ChatParticipant).filter(ChatParticipant.conversation_id == conv_id).all()
    ]
    await manager.broadcast_to_users(
        recipient_ids,
        {"type": "message", "conversation_id": conv_id, "message": data},
    )

    return send_response(data, "Mensaje enviado")


ADJ_TIPOS = {
    "image/jpeg", "image/png", "image/webp", "image/gif", "image/heic",
    "application/pdf",
}
ADJ_MAX_MB = 10


@router.post("/conversations/{conv_id}/attachment",
             summary="Subir un archivo para mandarlo por el chat")
async def subir_adjunto(
    conv_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Sube el archivo y devuelve con qué mandarlo; NO crea el mensaje.

    Va aquí y no en `/files/upload` a propósito: el permiso que hace falta es
    "estar en esta conversación y poder escribir en ella". Con el subidor
    general, cualquiera con cuenta podría dejar archivos en el almacén sin que
    nadie compruebe con quién habla.
    """
    import boto3
    from app.config import settings

    part = (
        db.query(ChatParticipant)
        .filter(ChatParticipant.conversation_id == conv_id,
                ChatParticipant.user_id == current_user.id)
        .first()
    )
    if not part:
        return send_error("Conversación no encontrada", code=404)

    conv = db.query(ChatConversation).filter(ChatConversation.id == conv_id).first()
    # Quien no puede escribir tampoco puede adjuntar: si no, en un grupo de
    # difusión los clientes podrían soltar archivos a todos los demás.
    if conv and conv.broadcast and conv.created_by_user_id != current_user.id:
        return send_error("En este grupo solo escribe quien lo creó.", code=403)
    if _chat_apagado(db, current_user.id):
        return send_error("Tu coach ha desactivado el chat.", code=403)

    if not settings.AWS_BUCKET:
        return send_error("Almacenamiento no configurado", code=500)
    if file.content_type not in ADJ_TIPOS:
        return send_error("Solo se pueden mandar imágenes (JPG, PNG, WEBP, GIF) o PDF",
                          code=400)

    contenido = await file.read()
    if len(contenido) > ADJ_MAX_MB * 1024 * 1024:
        return send_error(f"El archivo supera los {ADJ_MAX_MB} MB", code=400)

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
    key = f"chat/{conv_id}/{uuid.uuid4()}.{ext}"
    try:
        r2 = boto3.client(
            "s3",
            endpoint_url="https://77925e3b1a6f6513bce155f71f6aa790.r2.cloudflarestorage.com",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name="auto",
        )
        r2.put_object(Bucket=settings.AWS_BUCKET, Key=key, Body=contenido,
                      ContentType=file.content_type,
                      CacheControl="public, max-age=31536000")
    except Exception as e:
        return send_error(f"Error al subir el archivo: {e}", code=500)

    base = (settings.R2_PUBLIC_URL or "").rstrip("/")
    return send_response({
        "attachment_url": f"{base}/{key}",
        # El nombre original, porque "a3f9…-2b1c.pdf" no le dice nada a nadie.
        "attachment_name": (file.filename or "archivo")[:255],
        "attachment_type": file.content_type,
        "attachment_size": len(contenido),
    }, "Archivo subido")


class ParticipantesAdd(BaseModel):
    user_ids: list[int]


def _grupo_editable(conv_id: str, current_user, db: Session):
    """El grupo, si quien llama puede cambiar quién está dentro.

    Devuelve (conv, error). Dos reglas:

      · Solo los grupos hechos a MANO. Uno por regla ("mis clientes") lo define
        la regla: añadir a alguien a mano ahí duraría hasta la próxima vez que
        se resuelve, así que se dice en vez de dejar hacer algo que se deshace
        solo.
      · Solo quien lo creó. Es quien reunió a esa gente.
    """
    conv = db.query(ChatConversation).filter(ChatConversation.id == conv_id).first()
    if not conv:
        return None, send_error("Conversación no encontrada", code=404)
    if conv.type != "group":
        return None, send_error("Esto no es un grupo", code=400)
    if conv.audience:
        return None, send_error(
            "Este grupo se arma solo con la gente que cumple la regla "
            "(«mis clientes», «mis coaches»). Para elegir a mano, crea un grupo a medida.",
            code=400)
    if conv.created_by_user_id != current_user.id:
        return None, send_error("Solo quien creó el grupo puede cambiar quién está dentro", code=403)
    return conv, None


class GrupoRenombrar(BaseModel):
    name: str


@router.patch("/conversations/{conv_id}", summary="Cambiar el nombre del grupo")
def renombrar_grupo(
    conv_id: str,
    body: GrupoRenombrar,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """El nombre del grupo, que hasta ahora solo se ponía al crearlo.

    Un grupo que nació "Reto enero" y sigue en marcha en marzo se queda con un
    nombre que ya no es verdad, y no había forma de cambiarlo sin rehacerlo y
    perder la conversación entera.
    """
    conv, error = _grupo_editable(conv_id, current_user, db)
    if error:
        return error
    nombre = (body.name or "").strip()
    # Un grupo sin nombre sale como "Grupo" en la lista, y con tres grupos
    # todos se llaman igual.
    if not nombre:
        return send_error("El grupo necesita un nombre", code=422)
    conv.name = nombre[:255]
    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(conv)
    return send_response(_serialize_conversation(conv, current_user.id, db), "Nombre cambiado")


@router.post("/conversations/{conv_id}/participants", summary="Añadir gente al grupo")
async def anadir_participantes(
    conv_id: str,
    body: ParticipantesAdd,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    conv, error = _grupo_editable(conv_id, current_user, db)
    if error:
        return error

    # La misma comprobación que al crearlo: solo gente de tu cuenta. Si no,
    # bastaría con crear un grupo limpio y luego colar a quien no toca.
    roles = _user_role_ids(current_user.id, db)
    permitidos = _alcance(current_user.id, db)
    es_plataforma = SUPERADMIN in roles and not permitidos
    fuera = [] if es_plataforma else [uid for uid in body.user_ids if uid not in permitidos]
    if fuera:
        return send_error("Hay personas en la lista que no son de tu cuenta", code=403)

    ya = {p.user_id for p in conv.participants}
    nuevos = [uid for uid in dict.fromkeys(body.user_ids) if uid not in ya]
    if not nuevos:
        return send_error("Esas personas ya están en el grupo", code=400)

    ahora = datetime.utcnow()
    for uid in nuevos:
        db.add(ChatParticipant(conversation_id=conv_id, user_id=uid, joined_at=ahora))
    db.commit()
    db.refresh(conv)

    # A quien entra se le avisa para que le aparezca el grupo sin recargar.
    await manager.broadcast_to_users(
        [p.user_id for p in conv.participants],
        {"type": "participants", "conversation_id": conv_id},
    )
    return send_response(_serialize_conversation(conv, current_user.id, db), "Añadidos al grupo")


@router.delete("/conversations/{conv_id}/participants/{user_id}", summary="Sacar a alguien del grupo")
async def quitar_participante(
    conv_id: str,
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Sacar a alguien, o salirse uno mismo.

    Salir del grupo lo puede hacer cualquiera: estar dentro no es una condena.
    Sacar a otro, solo quien lo creó.
    """
    conv = db.query(ChatConversation).filter(ChatConversation.id == conv_id).first()
    if not conv:
        return send_error("Conversación no encontrada", code=404)

    soy_yo = user_id == current_user.id
    if not soy_yo:
        conv, error = _grupo_editable(conv_id, current_user, db)
        if error:
            return error
    elif conv.audience:
        return send_error(
            "De este grupo no se sale: está armado con la gente que cumple la regla. "
            "Habla con quien te lo envía.", code=400)

    # Quien creó el grupo no puede salirse y dejarlo sin dueño: lo que quiere
    # hacer es borrarlo, y para eso está el botón de borrar.
    if soy_yo and conv.created_by_user_id == current_user.id:
        return send_error("Creaste tú el grupo: bórralo en vez de salirte", code=400)

    parte = db.query(ChatParticipant).filter(
        ChatParticipant.conversation_id == conv_id,
        ChatParticipant.user_id == user_id,
    ).first()
    if not parte:
        return send_error("Esa persona no está en el grupo", code=404)

    quedan = [p.user_id for p in conv.participants if p.user_id != user_id]
    db.delete(parte)
    db.commit()

    await manager.broadcast_to_users(
        quedan + [user_id],
        {"type": "participants", "conversation_id": conv_id},
    )
    return send_response(None, "Ha salido del grupo" if soy_yo else "Sacado del grupo")


@router.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    conv = db.query(ChatConversation).filter(ChatConversation.id == conv_id).first()
    if not conv:
        return send_error("Conversación no encontrada", code=404)

    user_roles = _user_role_ids(current_user.id, db)
    is_admin = ADMIN in user_roles or SUPERADMIN in user_roles
    if conv.created_by_user_id != current_user.id and not is_admin:
        return send_error("No tienes permisos para eliminar esta conversación", code=403)

    db.delete(conv)
    db.commit()
    return send_response(None, "Conversación eliminada")


# ── WebSocket endpoint ────────────────────────────────────────────────────────

router_ws = APIRouter(tags=["Chat"])


@router_ws.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, token: str = Query(...)):
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        await websocket.close(code=4001)
        return

    user_id_raw = payload.get("sub")
    if user_id_raw is None:
        await websocket.close(code=4001)
        return

    user_id = int(user_id_raw)

    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")

            if msg_type == "typing":
                conv_id = data.get("conversation_id")
                if not conv_id:
                    continue
                db = SessionLocal()
                try:
                    participants = db.query(ChatParticipant).filter(
                        ChatParticipant.conversation_id == conv_id
                    ).all()
                    recipient_ids = [p.user_id for p in participants if p.user_id != user_id]
                finally:
                    db.close()
                await manager.broadcast_to_users(
                    recipient_ids,
                    {"type": "typing", "conversation_id": conv_id, "user_id": user_id},
                )
                continue

            conv_id = data.get("conversation_id")
            content = data.get("content", "").strip()
            if not conv_id or not content:
                continue

            db = SessionLocal()
            try:
                part = db.query(ChatParticipant).filter(
                    ChatParticipant.conversation_id == conv_id,
                    ChatParticipant.user_id == user_id,
                ).first()
                if not part:
                    continue

                # La misma regla que por REST: en un grupo de difusión solo
                # escribe quien lo creó. Cerrar una puerta y dejar la otra
                # abierta es no cerrar ninguna.
                conv_previa = db.query(ChatConversation).filter(
                    ChatConversation.id == conv_id).first()
                if conv_previa and conv_previa.broadcast and \
                        conv_previa.created_by_user_id != user_id:
                    await websocket.send_json({
                        "type": "error", "conversation_id": conv_id,
                        "message": "En este grupo solo escribe quien lo creó. "
                                   "Respóndele por privado.",
                    })
                    continue

                # La otra puerta de entrada. Comprobarlo solo en REST dejaría
                # el interruptor abierto por aquí, que es por donde escribe el
                # panel del coach.
                if _chat_apagado(db, user_id):
                    await websocket.send_json({
                        "type": "error", "conversation_id": conv_id,
                        "message": "Tu coach ha desactivado el chat.",
                    })
                    continue

                now = datetime.utcnow()
                msg = ChatMessage(
                    id=str(uuid.uuid4()),
                    conversation_id=conv_id,
                    sender_user_id=user_id,
                    content=content,
                    created_at=now,
                )
                db.add(msg)

                conv = db.query(ChatConversation).filter(ChatConversation.id == conv_id).first()
                if conv:
                    conv.updated_at = now

                db.commit()
                db.refresh(msg)

                msg_data = {
                    "id": msg.id,
                    "conversation_id": msg.conversation_id,
                    "content": msg.content,
                    "sender_user_id": msg.sender_user_id,
                    "sender_name": "",
                    "sender_photo": None,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                sender_detail = _user_detail(db, user_id)
                if sender_detail:
                    msg_data["sender_name"] = f"{sender_detail.name} {sender_detail.last_name or ''}".strip()
                    msg_data["sender_photo"] = sender_detail.photo

                participants = db.query(ChatParticipant).filter(
                    ChatParticipant.conversation_id == conv_id
                ).all()
                recipient_ids = [p.user_id for p in participants]
            finally:
                db.close()

            broadcast_payload = {
                "type": "message",
                "conversation_id": conv_id,
                "message": msg_data,
            }
            await manager.broadcast_to_users(recipient_ids, broadcast_payload)

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception:
        manager.disconnect(websocket, user_id)
