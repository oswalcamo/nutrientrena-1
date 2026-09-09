"""Borrar un ejercicio del catálogo cuando alguien ya lo ha usado.

Hay TRES tablas que apuntan a `trainings.id` y el borrado solo soltaba dos: las
rutinas donde estaba puesto y los clientes que lo tenían asignado. La tercera
—`workout_session_exercises`, el historial de lo que la gente ha entrenado— se
quedaba enganchada, la clave foránea bloqueaba el DELETE y el coach veía «Error
al eliminar» sin más pista.

El ejercicio que nadie ha hecho nunca se borraba bien. El que sí, no. Y es
justo al revés de lo que uno esperaría: cuanto más usado, menos se puede
limpiar.

El historial NO se borra. `workout_session_exercises` guarda el nombre y el
grupo muscular como copia precisamente para esto: lo que una persona hizo un
martes sigue siendo verdad aunque su coach retire el ejercicio del catálogo, y
no se recupera de ningún sitio.

OJO CON LO QUE ESTAS PRUEBAS PUEDEN VER: corren sobre SQLite, que por defecto
NO comprueba las claves foráneas. En producción es MySQL/InnoDB y sí las
comprueba, y por eso este fallo llegó hasta allí sin que ninguna de las
novecientas pruebas se enterara. Lo que aquí se sujeta es que el enlace se
SUELTE —que es lo que evita el error— y no el error en sí. Reproducirlo hay
que hacerlo contra MySQL a mano:

    DATABASE_URL="mysql+pymysql://ne:ne@127.0.0.1/nutri_e2e" ...
    → sin soltar el enlace: (1451, 'Cannot delete or update a parent row')

Lo que hay que dejar sujeto:

  · Que se pueda borrar un ejercicio que ya se ha entrenado.
  · Que el historial siga ahí, con su nombre, y solo pierda el enlace.
  · Y que lo que ya funcionaba —rutinas y asignaciones— siga funcionando.
"""
import uuid

from app.database import SessionLocal
from app.models.muscle_group import MuscleGroup
from app.models.routine import Routine, RoutineDay, RoutineDayDetail
from app.models.session_log import WorkoutSession, WorkoutSessionExercise
from app.models.training import Training, TrainingClient

from tests.test_org_scope import _crear_coach, _crear_usuario


def _ejercicio(nombre, **campos):
    db = SessionLocal()
    try:
        t = Training(name=nombre, **campos)
        db.add(t); db.commit()
        return t.id
    finally:
        db.close()


def _monta(client, admin_headers):
    suf = uuid.uuid4().hex[:8]
    coach_uid, _det_coach, h_coach = _crear_coach(
        client, admin_headers, f"coach.del.{suf}@nutrientrena-qa.com")
    uid, det_cli, h_cli = _crear_usuario(
        client, admin_headers, f"cli.del.{suf}@nutrientrena-qa.com", role_id=6)
    return h_coach, coach_uid, uid, det_cli, suf


def _historial_con(det_cli, training_id, nombre):
    """Una sesión ya entrenada que usó ese ejercicio."""
    from datetime import date
    db = SessionLocal()
    try:
        s = WorkoutSession(client_user_detail_id=det_cli, session_date=date.today(),
                           duration_min=45)
        db.add(s); db.flush()
        ex = WorkoutSessionExercise(session_id=s.id, training_id=training_id,
                                    name=nombre, muscle_group_name="Pecho",
                                    order_index=0)
        db.add(ex); db.commit()
        return ex.id
    finally:
        db.close()


def test_SE_PUEDE_BORRAR_UN_EJERCICIO_QUE_YA_SE_HA_ENTRENADO(client, seed, admin_headers):
    """El caso reportado: «Error al eliminar» porque estaba asignado a un
    cliente que ya lo había hecho."""
    h_coach, coach_uid, _uid, det_cli, suf = _monta(client, admin_headers)
    nombre = f"Press banca {suf}"
    tid = _ejercicio(nombre, created_user_id=coach_uid)
    _historial_con(det_cli, tid, nombre)

    r = client.delete(f"/api/trainings/{tid}", headers=h_coach)
    assert r.status_code == 200, r.text
    assert "eliminad" in r.json().get("message", "").lower(), r.text

    db = SessionLocal()
    try:
        assert db.query(Training).filter(Training.id == tid).first() is None
    finally:
        db.close()


def test_EL_HISTORIAL_DEL_CLIENTE_NO_SE_BORRA(client, seed, admin_headers):
    """Lo que una persona hizo un martes sigue siendo verdad aunque su coach
    retire el ejercicio del catálogo. Y no se recupera de ningún sitio."""
    h_coach, coach_uid, _uid, det_cli, suf = _monta(client, admin_headers)
    nombre = f"Sentadilla {suf}"
    tid = _ejercicio(nombre, created_user_id=coach_uid)
    ex_id = _historial_con(det_cli, tid, nombre)

    assert client.delete(f"/api/trainings/{tid}", headers=h_coach).status_code == 200

    db = SessionLocal()
    try:
        ex = db.query(WorkoutSessionExercise).filter(
            WorkoutSessionExercise.id == ex_id).first()
        assert ex is not None, "se ha llevado por delante el historial del cliente"
        assert ex.name == nombre, "y sin el nombre el historial no dice nada"
        assert ex.muscle_group_name == "Pecho"
        assert ex.training_id is None, "solo tenía que perder el enlace"
    finally:
        db.close()


def test_y_lo_que_ya_funcionaba_sigue_funcionando(client, seed, admin_headers):
    """Las rutinas donde estaba puesto y los clientes que lo tenían asignado:
    eso ya se soltaba, y tiene que seguir soltándose."""
    h_coach, coach_uid, uid, _det_cli, suf = _monta(client, admin_headers)
    tid = _ejercicio(f"Remo {suf}", created_user_id=coach_uid)

    db = SessionLocal()
    try:
        r = Routine(name=f"Fuerza {suf}", user_id=uid)
        db.add(r); db.flush()
        d = RoutineDay(routine_id=r.id, day_name="Día 1")
        db.add(d); db.flush()
        det = RoutineDayDetail(routine_id=r.id, routine_day_id=d.id,
                               training_id=tid, series="4", repetitions="8")
        db.add(det)
        db.add(TrainingClient(training_id=tid, user_id=uid))
        db.commit()
        det_id = det.id
    finally:
        db.close()

    assert client.delete(f"/api/trainings/{tid}", headers=h_coach).status_code == 200

    db = SessionLocal()
    try:
        fila = db.query(RoutineDayDetail).filter(RoutineDayDetail.id == det_id).first()
        assert fila is not None, "la rutina se ha quedado sin su fila"
        assert fila.training_id is None, "la fila sigue apuntando al ejercicio borrado"
        assert db.query(TrainingClient).filter(
            TrainingClient.training_id == tid).count() == 0
    finally:
        db.close()


def test_uno_que_nadie_ha_usado_se_borra_igual(client, seed, admin_headers):
    """El caso que sí funcionaba: que no se rompa por el camino."""
    h_coach, coach_uid, _uid, _det, suf = _monta(client, admin_headers)
    tid = _ejercicio(f"Sin usar {suf}", created_user_id=coach_uid)
    assert client.delete(f"/api/trainings/{tid}", headers=h_coach).status_code == 200
    db = SessionLocal()
    try:
        assert db.query(Training).filter(Training.id == tid).first() is None
    finally:
        db.close()
