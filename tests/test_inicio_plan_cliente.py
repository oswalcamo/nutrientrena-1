"""El plan de entrenamiento en la pantalla de Inicio del cliente.

La pantalla decía qué toca HOY y nada más. En un día de descanso eso la deja
sin ninguna referencia a lo que el cliente está siguiendo: ve "Día de
descanso" y se acabó, como si no tuviera plan. El prototipo pone ahí una
tarjeta con el plan entero —a qué apunta y cuántos días tiene—, y ese dato ya
estaba en la rutina; solo que no salía por la API.
"""
import uuid

from app.database import SessionLocal
from app.models.routine import Routine
from app.models.user import UserDetail, UserParent

from tests.test_org_scope import _crear_coach, _crear_usuario


def _monta(client, admin_headers, suf):
    _u, det_coach, _h_coach = _crear_coach(
        client, admin_headers, f"coach.plan.{suf}@nutrientrena-qa.com")
    _uid, det_cli, h_cli = _crear_usuario(
        client, admin_headers, f"cli.plan.{suf}@nutrientrena-qa.com", role_id=6)
    db = SessionLocal()
    try:
        db.add(UserParent(user_detail_id=det_cli, parent_user_detail_id=det_coach))
        db.commit()
        fila = db.query(UserDetail).filter(UserDetail.id == det_cli).first()
        user_id = fila.user_id
    finally:
        db.close()
    return det_cli, h_cli, user_id


def _rutina(user_id, **campos):
    db = SessionLocal()
    try:
        r = Routine(user_id=user_id, **campos)
        db.add(r)
        db.commit()
        return r.id
    finally:
        db.close()


def _inicio(client, h_cli):
    r = client.get("/api/client/home", headers=h_cli)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_el_plan_sale_con_su_objetivo_y_sus_dias(client, seed, admin_headers):
    suf = uuid.uuid4().hex[:8]
    _det, h_cli, user_id = _monta(client, admin_headers, suf)
    _rutina(user_id, name=f"Full body {suf}", objective="Fuerza", days=3)

    plan = _inicio(client, h_cli)["plan"]
    assert plan is not None, "sin plan no hay tarjeta que pintar"
    assert plan["objective"] == "Fuerza", plan
    assert plan["days_per_week"] == 3, plan
    assert plan["name"] == f"Full body {suf}", plan


def test_sin_rutina_asignada_no_se_inventa_un_plan(client, seed, admin_headers):
    """Una tarjeta que dice "tu plan" cuando no hay ninguno es peor que no
    enseñar nada: manda al cliente a una pantalla vacía."""
    suf = uuid.uuid4().hex[:8]
    _det, h_cli, _uid = _monta(client, admin_headers, suf)

    assert _inicio(client, h_cli)["plan"] is None


def test_si_el_coach_no_escribio_los_dias_se_cuentan_los_que_hay(client, seed, admin_headers):
    """`days` lo rellena el coach a mano y se queda vacío a menudo. Antes que
    enseñar el plan sin ese dato, se cuentan los días que de verdad tiene
    montados, que es el mismo número visto desde el otro lado."""
    from app.models.routine import RoutineDay

    suf = uuid.uuid4().hex[:8]
    _det, h_cli, user_id = _monta(client, admin_headers, suf)
    rid = _rutina(user_id, name=f"Torso pierna {suf}", objective="Hipertrofia", days=None)

    db = SessionLocal()
    try:
        for i in range(4):
            db.add(RoutineDay(routine_id=rid, day_name=f"Día {i + 1}"))
        db.commit()
    finally:
        db.close()

    plan = _inicio(client, h_cli)["plan"]
    assert plan["days_per_week"] == 4, plan


def test_el_objetivo_cae_al_tipo_de_entrenamiento_si_no_hay(client, seed, admin_headers):
    """Sin objetivo la tarjeta se quedaba con el subtítulo a medias."""
    suf = uuid.uuid4().hex[:8]
    _det, h_cli, user_id = _monta(client, admin_headers, suf)
    _rutina(user_id, name=f"Plan {suf}", objective=None, training="Calistenia", days=2)

    plan = _inicio(client, h_cli)["plan"]
    assert plan["objective"] == "Calistenia", plan


def test_el_plan_es_el_del_cliente_y_no_el_de_otro(client, seed, admin_headers):
    """La rutina se busca por user_id: si eso se rompiera, un cliente vería en
    su Inicio el plan de otra persona."""
    suf = uuid.uuid4().hex[:8]
    _d1, h_c1, uid1 = _monta(client, admin_headers, suf + "a")
    _d2, h_c2, uid2 = _monta(client, admin_headers, suf + "b")
    _rutina(uid1, name=f"Solo de A {suf}", objective="Fuerza", days=3)
    _rutina(uid2, name=f"Solo de B {suf}", objective="Resistencia", days=5)

    assert _inicio(client, h_c1)["plan"]["name"] == f"Solo de A {suf}"
    assert _inicio(client, h_c2)["plan"]["name"] == f"Solo de B {suf}"
