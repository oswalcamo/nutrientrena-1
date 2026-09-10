"""Un grupo se ve desde dentro, lo haya montado quien lo haya montado.

Lo que se probaba hasta ahora era que el grupo QUEDA BIEN MONTADO, y siempre
mirándolo desde la lista de quien lo creó. Lo que faltaba —y es lo que se
notó usando la aplicación— es lo de después: que a quien está dentro le
aparezca. Dos cosas distintas fallaban por el mismo sitio:

  1. Un grupo por REGLA ("mis clientes") solo se recalculaba cuando lo abría
     quien lo creó. El cliente dado de alta más tarde no entraba en él hasta
     que su coach volviera a mirar su propia lista de chats: mientras tanto el
     grupo existía, los demás hablaban dentro y a él no le salía.
  2. La pantalla del cliente pedía una sola conversación —la de su coach— y
     pintaba esa. Eso se arregla en `client-chat.html`, y se comprueba en
     `tests/frontend/chat_cliente_grupos.test.js`.

Aquí va lo primero: que la lista del servidor diga la verdad para cualquiera
que esté dentro, no solo para el que lo creó.
"""
import uuid

from app.database import SessionLocal
from app.models.organization import OrganizationMember

from tests.test_chat_grupos import _cliente_de, _crear_grupo, _monta_centro
from tests.test_org_scope import _crear_coach


def _mis_conversaciones(client, headers):
    r = client.get("/api/chat/conversations", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _nombres(convs):
    return [c.get("name") for c in convs]


# ── Grupos por regla ───────────────────────────────────────────────────────

def test_el_cliente_ve_el_grupo_de_avisos_de_su_coach(client, seed, admin_headers):
    suf = uuid.uuid4().hex[:8]
    _org, _det, h_coach, h_c1, _h2 = _monta_centro(client, admin_headers, suf)
    _crear_grupo(client, h_coach, audience="mis_clientes", name="Avisos")

    assert "Avisos" in _nombres(_mis_conversaciones(client, h_c1))


def test_un_cliente_nuevo_lo_ve_sin_que_su_coach_toque_nada(client, seed, admin_headers):
    """El fallo de verdad: el grupo por regla se ponía al día SOLO cuando lo
    abría quien lo creó. El cliente que entra después se quedaba fuera hasta
    que su coach volviera a mirar su lista, que puede ser nunca."""
    suf = uuid.uuid4().hex[:8]
    _org, det_coach, h_coach, _h1, _h2 = _monta_centro(client, admin_headers, suf)
    _crear_grupo(client, h_coach, audience="mis_clientes", name="Avisos")

    # Cliente de alta DESPUÉS de montar el grupo. El coach no vuelve a entrar.
    _d3, h_c3 = _cliente_de(client, admin_headers, det_coach,
                            f"cli.tarde.{suf}@nutrientrena-qa.com")

    assert "Avisos" in _nombres(_mis_conversaciones(client, h_c3))


def test_recalcular_desde_el_cliente_no_le_mete_en_grupos_ajenos(client, seed, admin_headers):
    """Poner al día los grupos desde este lado no puede convertirse en una
    puerta para ver los de otra cuenta."""
    suf = uuid.uuid4().hex[:8]
    _orgA, _detA, h_coachA, _a1, _a2 = _monta_centro(client, admin_headers, suf + "a")
    _orgB, _detB, h_coachB, h_b1, _b2 = _monta_centro(client, admin_headers, suf + "b")

    _crear_grupo(client, h_coachA, audience="mis_clientes", name=f"Solo A {suf}")

    assert f"Solo A {suf}" not in _nombres(_mis_conversaciones(client, h_b1))


def test_el_grupo_del_coach_no_se_le_cuela_a_otro_coach(client, seed, admin_headers):
    """"mis clientes" es de clientes. Un compañero de equipo no entra en él por
    el hecho de que ahora la lista se recalcule desde más sitios."""
    suf = uuid.uuid4().hex[:8]
    org_id, _det, h_coach, _h1, _h2 = _monta_centro(client, admin_headers, suf)
    _uid2, det2, h_coach2 = _crear_coach(
        client, admin_headers, f"coach2.ve.{suf}@nutrientrena-qa.com")
    db = SessionLocal()
    try:
        db.add(OrganizationMember(organization_id=org_id, user_detail_id=det2, permissions={}))
        db.commit()
    finally:
        db.close()

    _crear_grupo(client, h_coach, audience="mis_clientes", name=f"Clientes {suf}")

    assert f"Clientes {suf}" not in _nombres(_mis_conversaciones(client, h_coach2))


# ── Grupos a mano ──────────────────────────────────────────────────────────

def test_el_cliente_ve_el_grupo_a_mano_en_el_que_le_metieron(client, seed, admin_headers):
    suf = uuid.uuid4().hex[:8]
    _org, _det, h_coach, h_c1, _h2 = _monta_centro(client, admin_headers, suf)
    contactos = client.get("/api/chat/contactos", headers=h_coach).json()["data"]
    clientes = [c["user_id"] for c in contactos if c["rol"] == "cliente"]
    assert clientes, contactos

    r = _crear_grupo(client, h_coach, participant_user_ids=clientes,
                     name="Reto de verano", tipo="comunidad")
    assert r.status_code == 200, r.text

    assert "Reto de verano" in _nombres(_mis_conversaciones(client, h_c1))


def test_y_puede_escribir_en_el(client, seed, admin_headers):
    """Un grupo que se ve pero en el que no se puede hablar no sirve de nada."""
    suf = uuid.uuid4().hex[:8]
    _org, _det, h_coach, h_c1, _h2 = _monta_centro(client, admin_headers, suf)
    contactos = client.get("/api/chat/contactos", headers=h_coach).json()["data"]
    clientes = [c["user_id"] for c in contactos if c["rol"] == "cliente"]
    grupo = _crear_grupo(client, h_coach, participant_user_ids=clientes,
                         name="Reto", tipo="comunidad").json()["data"]

    conv = next(c for c in _mis_conversaciones(client, h_c1) if c["id"] == grupo["id"])
    assert conv["puedo_escribir"] is True, conv

    r = client.post(f"/api/chat/conversations/{grupo['id']}/messages",
                    headers=h_c1, json={"content": "voy por el día 12"})
    assert r.status_code == 200, r.text


def test_en_el_de_avisos_se_ve_pero_no_se_escribe(client, seed, admin_headers):
    """Y la lista lo dice, para que la pantalla pueda enseñar el motivo en vez
    de un cuadro de escribir que devuelve un error al pulsar Enviar."""
    suf = uuid.uuid4().hex[:8]
    _org, _det, h_coach, h_c1, _h2 = _monta_centro(client, admin_headers, suf)
    grupo = _crear_grupo(client, h_coach, audience="mis_clientes",
                         name="Avisos").json()["data"]

    conv = next(c for c in _mis_conversaciones(client, h_c1) if c["id"] == grupo["id"])
    assert conv["broadcast"] is True and conv["puedo_escribir"] is False, conv


def test_los_mensajes_del_grupo_se_leen_desde_el_rol_cliente(client, seed, admin_headers):
    """Estar en la lista y poder abrirlo son dos permisos distintos."""
    suf = uuid.uuid4().hex[:8]
    _org, _det, h_coach, h_c1, _h2 = _monta_centro(client, admin_headers, suf)
    grupo = _crear_grupo(client, h_coach, audience="mis_clientes",
                         name="Avisos").json()["data"]
    client.post(f"/api/chat/conversations/{grupo['id']}/messages",
                headers=h_coach, json={"content": "cerramos el 15"})

    r = client.get(f"/api/chat/conversations/{grupo['id']}/messages", headers=h_c1)
    assert r.status_code == 200, r.text
    textos = [m["content"] for m in r.json()["data"]["messages"]]
    assert "cerramos el 15" in textos, textos


def test_los_no_leidos_del_grupo_van_con_su_conversacion(client, seed, admin_headers):
    """La pantalla del cliente pinta el globito por conversación: si el desglose
    no trajera el grupo, el número del menú no cuadraría con ninguna fila."""
    suf = uuid.uuid4().hex[:8]
    _org, _det, h_coach, h_c1, _h2 = _monta_centro(client, admin_headers, suf)
    grupo = _crear_grupo(client, h_coach, audience="mis_clientes",
                         name="Avisos").json()["data"]
    client.post(f"/api/chat/conversations/{grupo['id']}/messages",
                headers=h_coach, json={"content": "cerramos el 15"})

    d = client.get("/api/chat/unread-count", headers=h_c1).json()["data"]
    ids = [x["conversation_id"] for x in d["conversations"]]
    assert grupo["id"] in ids, d
