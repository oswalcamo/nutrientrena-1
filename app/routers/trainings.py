from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.core.dependencies import (
    require_role_ids, get_org_context, OrgContext, _user_role_ids,
    SUPERADMIN, ADMIN, SETTER, CLOSER, COACH, EDITOR_CONTENIDO_GLOBAL,
)
from app.core.responses import send_response, send_error
from app.models.training import Training, TrainingClient
from app.schemas.training import TrainingCreate, TrainingUpdate, TrainingAssignRequest, TrainingOut

router = APIRouter(prefix="/trainings", tags=["Trainings"])


def _get_or_404(db: Session, training_id: int):
    return db.query(Training).filter(Training.id == training_id).first()


def _autores_de(items, db: Session) -> dict:
    """{user_id: nombre} de quienes crearon estos ejercicios, en una consulta.

    Hace falta para poder decir en la pantalla de dónde salió cada uno: subir
    un ejercicio a la plataforma le cambia el ámbito, no quién lo hizo, y sin
    esto esa información se perdía de vista.
    """
    from app.models.user import User, UserDetail

    ids = {t.created_user_id for t in items if t.created_user_id}
    if not ids:
        return {}
    nombres = {}
    for d in db.query(UserDetail).filter(UserDetail.user_id.in_(ids)).all():
        nombres[d.user_id] = f"{d.name} {d.last_name or ''}".strip()
    # Quien no tenga ficha todavía: al menos su nombre de usuario.
    faltan = ids - set(nombres)
    if faltan:
        for u in db.query(User).filter(User.id.in_(faltan)).all():
            nombres[u.id] = u.name
    return nombres


def _visible_para(obj: Training, org: OrgContext) -> bool:
    """Un ejercicio se ve si es del catálogo maestro o de tu organización."""
    if obj.organization_id is None:
        return True  # catálogo maestro: compartido por toda la plataforma
    if org.solo_plataforma:
        return False  # se está mirando el catálogo común, no las cuentas
    if org.org_id is None and org.is_owner:
        return True  # superadmin, o admin sin organización propia
    return obj.organization_id == org.org_id


def _bloqueado_para_editar(obj: Training, org: OrgContext, current_user, db: Session):
    """Motivo por el que no puede editar/borrar este ejercicio, o None.

    Mismo orden de reglas que en rutinas y dietas:

    1. Quien lo creó siempre puede tocar lo suyo. Va primero porque un coach
       sin organización crea con organization_id NULL, y sin esta regla la
       de abajo ("lo NULL es de plataforma") le bloquearía su propio
       ejercicio.
    2. Contenido del catálogo maestro (NULL): solo superadmin, admin sin
       organización, o el editor de contenido global — para el que esto es
       justamente su único trabajo.
    3. Si es de una organización, tiene que ser la tuya.
    """
    # Quien lo creó puede tocar lo suyo — pero solo mientras SIGA siendo suyo.
    # Subirlo al catálogo común cambia de quién es: pasa a ser material del que
    # dependen otras cuentas, y un clic del autor se lo llevaría por delante.
    # Antes esta regla iba primero y sin condición, así que el coach conservaba
    # la llave sobre algo que ya había entregado.
    #
    # La excepción de abajo es el caso para el que se escribió la regla: un
    # coach SIN organización crea con organization_id NULL, y sin ella "lo NULL
    # es de la plataforma" le bloquearía su propio contenido. Solo se le aplica
    # a él, no a un coach con centro, para el que NULL sí significa plataforma.
    if obj.created_user_id is not None and obj.created_user_id == current_user.id:
        if obj.organization_id is not None or org.org_id is None:
            return None

    if org.solo_plataforma and obj.organization_id is not None:
        return "No tienes acceso a este ejercicio"   # actuando solo como plataforma

    if org.org_id is None and org.is_owner:
        return None  # bypass total

    if obj.organization_id is None:
        roles = _user_role_ids(current_user.id, db)
        if EDITOR_CONTENIDO_GLOBAL in roles:
            return None
        return "No puedes editar ejercicios del catálogo de la plataforma"

    if obj.organization_id != org.org_id:
        return "No tienes acceso a este ejercicio"
    return None


@router.get("/findAll", summary="Listar ejercicios", description="Retorna todos los ejercicios activos del catálogo.")
def find_all(
    db: Session = Depends(get_db),
    _=Depends(require_role_ids(SUPERADMIN, ADMIN, SETTER, CLOSER, COACH, EDITOR_CONTENIDO_GLOBAL)),
    org: OrgContext = Depends(get_org_context),
):
    q = db.query(Training).filter(Training.state == 1)
    if org.solo_plataforma:
        q = q.filter(Training.organization_id.is_(None))
    elif org.org_id:
        q = q.filter(or_(Training.organization_id.is_(None), Training.organization_id == org.org_id))
    items = q.all()
    autores = _autores_de(items, db)
    return send_response([TrainingOut.from_orm_training(i, autores).model_dump() for i in items], "OK")


@router.get("/search", summary="Buscar ejercicios", description="Búsqueda paginada de ejercicios con filtro por nombre o grupo muscular.")
def search(
    search: Optional[str] = Query(None),
    muscle_group_id: Optional[int] = Query(None),
    difficulty: Optional[int] = Query(None),
    material: Optional[str] = Query(None),
    state: Optional[int] = Query(None),
    page: int = Query(1),
    per_page: int = Query(15),
    db: Session = Depends(get_db),
    _=Depends(require_role_ids(SUPERADMIN, ADMIN, SETTER, CLOSER, COACH, EDITOR_CONTENIDO_GLOBAL)),
    org: OrgContext = Depends(get_org_context),
):
    q = db.query(Training)
    if org.solo_plataforma:
        q = q.filter(Training.organization_id.is_(None))
    elif org.org_id:
        q = q.filter(or_(Training.organization_id.is_(None), Training.organization_id == org.org_id))
    if search:
        # También por los otros nombres, que es para lo único que existen: un
        # sinónimo que no se busca no le sirve a nadie.
        q = q.filter(or_(
            Training.name.ilike(f"%{search}%"),
            Training.aliases.ilike(f"%{search}%"),
        ))
    if muscle_group_id:
        q = q.filter(Training.muscle_group_id == muscle_group_id)
    if difficulty:
        # El ejercicio puede tener varios niveles; basta con que incluya el buscado.
        q = q.filter(
            or_(
                Training.difficulty == difficulty,
                Training.difficulty_levels == str(difficulty),
                Training.difficulty_levels.like(f"{difficulty},%"),
                Training.difficulty_levels.like(f"%,{difficulty},%"),
                Training.difficulty_levels.like(f"%,{difficulty}"),
            )
        )
    if material:
        q = q.filter(Training.material.ilike(f"%{material}%"))
    if state is not None:
        q = q.filter(Training.state == state)
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return send_response(
        {
            "data": [TrainingOut.from_orm_training(i, _autores_de(items, db)).model_dump() for i in items],
            "total": total,
            "page": page,
            "per_page": per_page,
            "last_page": (total + per_page - 1) // per_page,
        },
        "OK",
    )


@router.post("/assign", summary="Asignar ejercicios a usuario", description="Asigna múltiples ejercicios a un usuario específico.")
def assigned(
    data: TrainingAssignRequest,
    db: Session = Depends(get_db),
    _=Depends(require_role_ids(SUPERADMIN, ADMIN, SETTER, CLOSER, COACH)),
    org: OrgContext = Depends(get_org_context),
):
    # Solo se puede asignar lo que se puede ver: sin esto, un coach podía
    # colar en la rutina de su cliente el ejercicio privado de otra
    # organización con solo saber el id.
    for training_id in data.training_ids:
        obj = _get_or_404(db, training_id)
        if not obj:
            return send_error(f"Ejercicio {training_id} no encontrado")
        if not _visible_para(obj, org):
            return send_error("No tienes acceso a alguno de los ejercicios", code=403)

    for training_id in data.training_ids:
        exists = db.query(TrainingClient).filter_by(training_id=training_id, user_id=data.user_id).first()
        if not exists:
            db.add(TrainingClient(training_id=training_id, user_id=data.user_id))
    db.commit()
    return send_response(None, "Ejercicios asignados")


@router.get("/{id}/edit", summary="Ver ejercicio", description="Retorna el detalle de un ejercicio por su ID.")
def edit(
    id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role_ids(SUPERADMIN, ADMIN, SETTER, CLOSER, COACH, EDITOR_CONTENIDO_GLOBAL)),
    org: OrgContext = Depends(get_org_context),
):
    obj = _get_or_404(db, id)
    if not obj:
        return send_error("Ejercicio no encontrado")
    if not _visible_para(obj, org):
        return send_error("No tienes acceso a este ejercicio", code=403)
    return send_response(TrainingOut.from_orm_training(obj, _autores_de([obj], db)).model_dump(), "OK")


def _apply_secondary_ids(payload: dict):
    """Normalize secondary_muscle_group_ids (list) into the CSV column + single id."""
    if "secondary_muscle_group_ids" in payload:
        ids = payload.pop("secondary_muscle_group_ids") or []
        payload["secondary_muscle_group_ids"] = ",".join(str(i) for i in ids) if ids else None
        payload["secondary_muscle_group_id"] = ids[0] if ids else None
    # Un ejercicio puede valer para varios niveles: se guardan en CSV y se deja
    # el más bajo en `difficulty` para no romper filtros/lecturas antiguas.
    if "difficulty_levels" in payload:
        levels = sorted({int(x) for x in (payload.pop("difficulty_levels") or [])})
        if levels:
            payload["difficulty_levels"] = ",".join(str(i) for i in levels)
            payload["difficulty"] = levels[0]
        else:
            # Sin lista: se respeta el `difficulty` suelto que llegue (clientes antiguos).
            payload["difficulty_levels"] = str(payload["difficulty"]) if payload.get("difficulty") else None
    return payload


@router.post("", summary="Crear ejercicio", description="Agrega un nuevo ejercicio al catálogo.")
def create(
    data: TrainingCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, SETTER, CLOSER, COACH, EDITOR_CONTENIDO_GLOBAL)),
    org: OrgContext = Depends(get_org_context),
):
    obj = Training(
        **_apply_secondary_ids(data.model_dump()),
        organization_id=org.org_id,
        created_user_id=current_user.id,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return send_response(TrainingOut.from_orm_training(obj).model_dump(), "Ejercicio creado")


@router.put("/{id}/update", summary="Actualizar ejercicio", description="Modifica los datos de un ejercicio existente.")
def updated(
    id: int,
    data: TrainingUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, SETTER, CLOSER, COACH, EDITOR_CONTENIDO_GLOBAL)),
    org: OrgContext = Depends(get_org_context),
):
    obj = _get_or_404(db, id)
    if not obj:
        return send_error("Ejercicio no encontrado")
    motivo = _bloqueado_para_editar(obj, org, current_user, db)
    if motivo:
        return send_error(motivo, code=403)
    for f, v in _apply_secondary_ids(data.model_dump(exclude_unset=True)).items():
        setattr(obj, f, v)
    db.commit()
    db.refresh(obj)
    return send_response(TrainingOut.from_orm_training(obj).model_dump(), "Actualizado")


@router.delete("/{id}", summary="Eliminar ejercicio", description="Elimina un ejercicio del catálogo.")
def delete(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, SETTER, CLOSER, COACH, EDITOR_CONTENIDO_GLOBAL)),
    org: OrgContext = Depends(get_org_context),
):
    obj = _get_or_404(db, id)
    if not obj:
        return send_error("Ejercicio no encontrado")
    # Borrar desengancha el ejercicio de las rutinas que lo usan, así que aquí
    # el control de organización importa aún más que al editar.
    motivo = _bloqueado_para_editar(obj, org, current_user, db)
    if motivo:
        return send_error(motivo, code=403)
    # Hay TRES tablas que apuntan a `trainings.id` y hay que soltarlas todas
    # antes de borrar. Faltaba la tercera —el historial de lo que la gente ha
    # entrenado— y la clave foránea bloqueaba el DELETE: el ejercicio que nadie
    # había hecho nunca se borraba bien y el que sí, no, que es justo al revés
    # de lo que uno esperaría. El coach solo veía «Error al eliminar».
    #
    # Se sueltan, no se borran: `workout_session_exercises` guarda el nombre y
    # el grupo muscular como copia precisamente para esto. Lo que una persona
    # hizo un martes sigue siendo verdad aunque su coach retire el ejercicio
    # del catálogo, y no se recupera de ningún sitio.
    from app.models.routine import RoutineDayDetail
    from app.models.session_log import WorkoutSessionExercise
    db.query(RoutineDayDetail).filter(RoutineDayDetail.training_id == id).update({"training_id": None})
    db.query(WorkoutSessionExercise).filter(
        WorkoutSessionExercise.training_id == id).update({"training_id": None})
    db.query(TrainingClient).filter(TrainingClient.training_id == id).delete()
    db.delete(obj)
    db.commit()
    return send_response(None, "Ejercicio eliminado")
