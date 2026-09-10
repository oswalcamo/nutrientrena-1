"""Lo que el cliente ve de un ejercicio: resumen, historial e indicaciones.

Al tocar la foto de un ejercicio en medio de la sesión se abría una ficha con
la descripción y poco más. El diseño pide tres pestañas, y dos de ellas
necesitan datos que el endpoint no daba:

  · Resumen: sus RÉCORDS —mayor peso, mejor 1RM, mejor volumen— y cómo ha ido
    subiendo la carga sesión a sesión.
  · Historial: las sesiones anteriores con sus series, peso y RPE.
  · Indicaciones: eso ya lo había.

La cuenta NO es nueva: es la que la pantalla de Fuerza del coach hacía dentro
de su propio bucle. Se ha sacado a `core/entrenos` y ahora la usan los dos,
porque dos pantallas calculando el mismo levantamiento por su cuenta acaban
diciendo cifras distintas — y aquí la que se equivoque le está mintiendo a
quien está levantando el peso.

Lo que hay que dejar sujeto:

  · Que los récords sean el máximo histórico de verdad.
  · Que la evolución vaya de la sesión más vieja a la más nueva, y el
    historial al revés: lo último es lo que se quiere ver.
  · Que el 1RM sea el del peso top, no el de la serie más larga.
  · Que un ejercicio por tiempo no invente kilos.
  · Que el cliente solo vea SU historial.
  · Y que el coach y el cliente digan lo mismo del mismo levantamiento.
"""
import uuid
from datetime import date, timedelta

from app.database import SessionLocal
from app.models.routine import Routine, RoutineDay, RoutineDayDetail
from app.models.session_log import (WorkoutSession, WorkoutSessionExercise,
                                    WorkoutSessionSet)
from app.models.training import Training

from tests.test_org_scope import _crear_coach, _crear_usuario


def _monta(client, admin_headers):
    suf = uuid.uuid4().hex[:8]
    _cu, det_coach, h_coach = _crear_coach(
        client, admin_headers, f"coach.pest.{suf}@nutrientrena-qa.com")
    uid, det_cli, h_cli = _crear_usuario(
        client, admin_headers, f"cli.pest.{suf}@nutrientrena-qa.com", role_id=6)
    return h_coach, det_coach, uid, det_cli, h_cli, suf


def _ejercicio_en_rutina(uid, nombre, **campos):
    """Un ejercicio del catálogo puesto en una rutina de ese cliente: si no
    está en ninguna, la ficha no se la deja ver, y con razón."""
    db = SessionLocal()
    try:
        t = Training(name=nombre, **campos)
        db.add(t); db.flush()
        r = Routine(name=f"Fuerza {nombre}", user_id=uid)
        db.add(r); db.flush()
        d = RoutineDay(routine_id=r.id, day_name="Día 1")
        db.add(d); db.flush()
        db.add(RoutineDayDetail(routine_id=r.id, routine_day_id=d.id,
                                training_id=t.id, series="4", repetitions="8",
                                break_time=90))
        db.commit()
        return t.id
    finally:
        db.close()


def _sesion(det_cli, training_id, nombre, dias_atras, series, dia="Empuje A"):
    """`series` son tuplas (peso, reps, rpe). Peso None = por tiempo."""
    db = SessionLocal()
    try:
        s = WorkoutSession(client_user_detail_id=det_cli, day_name=dia,
                           session_date=date.today() - timedelta(days=dias_atras),
                           duration_min=45)
        db.add(s); db.flush()
        ex = WorkoutSessionExercise(session_id=s.id, training_id=training_id,
                                    name=nombre, muscle_group_name="Pecho",
                                    order_index=0)
        db.add(ex); db.flush()
        for n, (peso, reps, rpe) in enumerate(series, start=1):
            db.add(WorkoutSessionSet(session_exercise_id=ex.id, set_number=n,
                                     reps=reps, weight=peso, rpe=rpe, done=True))
        db.commit()
    finally:
        db.close()


def _ficha(client, h_cli, tid):
    r = client.get(f"/api/client/exercise/{tid}", headers=h_cli)
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ── Resumen ────────────────────────────────────────────────────────────────

def test_LOS_RECORDS_SON_EL_MAXIMO_HISTORICO(client, seed, admin_headers):
    _hc, _dc, uid, det_cli, h_cli, suf = _monta(client, admin_headers)
    nombre = f"Press de banca {suf}"
    tid = _ejercicio_en_rutina(uid, nombre)
    # La sesión vieja mueve menos que la nueva: el récord es de la nueva.
    _sesion(det_cli, tid, nombre, 30, [(55, "10", 8), (60, "10", 8.5), (65, "8", 9)])
    _sesion(det_cli, tid, nombre, 3, [(60, "10", 8), (65, "8", None), (70, "6", 9)])

    rec = _ficha(client, h_cli, tid)["records"]
    assert rec["mayor_peso"] == 70, rec
    # 70 kg × 6 → 70 × (1 + 6/30) = 84
    assert rec["mejor_rm1"] == 84.0, rec
    # Nueva: 60×10 + 65×8 + 70×6 = 1540. Vieja: 550+600+520 = 1670… no: 1670.
    assert rec["mejor_volumen"] == max(1540.0, 1670.0), rec


def test_EL_1RM_ES_EL_DEL_PESO_TOP_no_el_de_la_serie_mas_larga(client, seed, admin_headers):
    """15 repeticiones con 40 kg dan un 1RM más alto que 6 con 70 si se coge la
    serie más larga. El récord es del levantamiento más pesado."""
    _hc, _dc, uid, det_cli, h_cli, suf = _monta(client, admin_headers)
    nombre = f"Sentadilla {suf}"
    tid = _ejercicio_en_rutina(uid, nombre)
    _sesion(det_cli, tid, nombre, 5, [(40, "15", None), (70, "6", None)])

    d = _ficha(client, h_cli, tid)
    assert d["records"]["mayor_peso"] == 70
    assert d["records"]["mejor_rm1"] == 84.0, d["records"]
    assert d["historial"][0]["reps_top"] == 6, d["historial"][0]


def test_LA_EVOLUCION_VA_DE_LA_MAS_VIEJA_A_LA_MAS_NUEVA(client, seed, admin_headers):
    """Es una línea de progreso: al revés bajaría."""
    _hc, _dc, uid, det_cli, h_cli, suf = _monta(client, admin_headers)
    nombre = f"Peso muerto {suf}"
    tid = _ejercicio_en_rutina(uid, nombre)
    for dias, peso in ((40, 80), (20, 90), (2, 100)):
        _sesion(det_cli, tid, nombre, dias, [(peso, "5", None)])

    ev = _ficha(client, h_cli, tid)["evolucion"]
    assert [p["peso"] for p in ev] == [80, 90, 100], ev
    assert ev[0]["fecha"] < ev[-1]["fecha"]


def test_y_el_historial_al_reves_lo_ultimo_primero(client, seed, admin_headers):
    _hc, _dc, uid, det_cli, h_cli, suf = _monta(client, admin_headers)
    nombre = f"Remo {suf}"
    tid = _ejercicio_en_rutina(uid, nombre)
    _sesion(det_cli, tid, nombre, 40, [(50, "10", None)], dia="Tirón A")
    _sesion(det_cli, tid, nombre, 2, [(60, "10", None)], dia="Tirón B")

    h = _ficha(client, h_cli, tid)["historial"]
    assert [s["sesion"] for s in h] == ["Tirón B", "Tirón A"], h
    assert h[0]["fecha"] > h[1]["fecha"]


# ── Historial: las series, como se leen ────────────────────────────────────

def test_CADA_SESION_TRAE_SUS_SERIES_CON_PESO_REPS_Y_RPE(client, seed, admin_headers):
    """Es lo que la pestaña pinta: «60 kg × 10 @ 8 rpe»."""
    _hc, _dc, uid, det_cli, h_cli, suf = _monta(client, admin_headers)
    nombre = f"Press militar {suf}"
    tid = _ejercicio_en_rutina(uid, nombre)
    _sesion(det_cli, tid, nombre, 1, [(60, "10", 8), (65, "8", None), (70, "6", 9)])

    s = _ficha(client, h_cli, tid)["historial"][0]
    assert s["series"] == 3, s
    assert [(x["serie"], x["peso"], x["reps"], x["rpe"]) for x in s["detalle"]] == [
        (1, 60.0, "10", 8.0), (2, 65.0, "8", None), (3, 70.0, "6", 9.0)], s["detalle"]
    assert s["sesion"] == "Empuje A"
    assert s["descanso_s"] == 90, "el descanso que su coach puso en la rutina"


def test_una_serie_sin_marcar_no_entra_en_el_historial(client, seed, admin_headers):
    """Lo que dejó a medias no lo levantó."""
    _hc, _dc, uid, det_cli, h_cli, suf = _monta(client, admin_headers)
    nombre = f"Curl {suf}"
    tid = _ejercicio_en_rutina(uid, nombre)
    db = SessionLocal()
    try:
        s = WorkoutSession(client_user_detail_id=det_cli, day_name="Brazo",
                           session_date=date.today())
        db.add(s); db.flush()
        ex = WorkoutSessionExercise(session_id=s.id, training_id=tid, name=nombre,
                                    order_index=0)
        db.add(ex); db.flush()
        db.add(WorkoutSessionSet(session_exercise_id=ex.id, set_number=1,
                                 reps="10", weight=20, rpe=None, done=True))
        db.add(WorkoutSessionSet(session_exercise_id=ex.id, set_number=2,
                                 reps="10", weight=99, rpe=None, done=False))
        db.commit()
    finally:
        db.close()

    d = _ficha(client, h_cli, tid)
    assert d["records"]["mayor_peso"] == 20, "ha contado la serie que no hizo"
    assert d["historial"][0]["series"] == 1


def test_UN_EJERCICIO_POR_TIEMPO_NO_INVENTA_KILOS(client, seed, admin_headers):
    """Una plancha no tiene peso top ni 1RM. Un 0 diría que no levantó nada,
    cuando lo que pasa es que ahí no se levanta."""
    _hc, _dc, uid, det_cli, h_cli, suf = _monta(client, admin_headers)
    nombre = f"Plancha {suf}"
    tid = _ejercicio_en_rutina(uid, nombre)
    _sesion(det_cli, tid, nombre, 1, [(None, "40s", None), (None, "45s", None)])

    d = _ficha(client, h_cli, tid)
    assert d["records"]["mayor_peso"] is None, d["records"]
    assert d["records"]["mejor_rm1"] is None, d["records"]
    assert d["records"]["mejor_tiempo_s"] == 45, d["records"]
    assert d["evolucion"] == [], "no hay kilos que pintar en la línea"
    assert d["historial"][0]["tiempo"] == "0:45", d["historial"][0]


# ── De quién es el historial ───────────────────────────────────────────────

def test_UN_CLIENTE_NO_VE_EL_HISTORIAL_DE_OTRO(client, seed, admin_headers):
    _hc, _dc, uid, det_cli, h_cli, suf = _monta(client, admin_headers)
    nombre = f"Dominadas {suf}"
    tid = _ejercicio_en_rutina(uid, nombre)
    _sesion(det_cli, tid, nombre, 1, [(80, "8", None)])

    # Otro cliente, con el mismo ejercicio en su rutina.
    otro_uid, otro_det, h_otro = _crear_usuario(
        client, admin_headers, f"otro.pest.{suf}@nutrientrena-qa.com", role_id=6)
    db = SessionLocal()
    try:
        r = Routine(name="Suya", user_id=otro_uid); db.add(r); db.flush()
        d = RoutineDay(routine_id=r.id, day_name="D1"); db.add(d); db.flush()
        db.add(RoutineDayDetail(routine_id=r.id, routine_day_id=d.id, training_id=tid))
        db.commit()
    finally:
        db.close()

    mio = _ficha(client, h_cli, tid)
    suyo = _ficha(client, h_otro, tid)
    assert mio["records"]["mayor_peso"] == 80
    assert suyo["records"]["mayor_peso"] is None, "le está enseñando el peso de otro"
    assert suyo["historial"] == []


def test_sin_haberlo_entrenado_nunca_las_pestanas_salen_vacias(client, seed, admin_headers):
    """No es un error: es un ejercicio que todavía no ha hecho. Vacío es vacío
    y la pantalla decide qué decir."""
    _hc, _dc, uid, _det, h_cli, suf = _monta(client, admin_headers)
    tid = _ejercicio_en_rutina(uid, f"Nuevo {suf}",
                               description="1. Colócate.\n2. Empuja.")
    d = _ficha(client, h_cli, tid)
    assert d["historial"] == [] and d["evolucion"] == []
    assert all(v is None for v in d["records"].values()), d["records"]
    assert d["description"].startswith("1."), "las indicaciones sí están"


# ── Y que las dos pantallas digan lo mismo ─────────────────────────────────

def test_EL_COACH_Y_EL_CLIENTE_DICEN_LO_MISMO(client, seed, admin_headers):
    """Es el motivo de que el cálculo viva en un solo sitio."""
    h_coach, _dc, uid, det_cli, h_cli, suf = _monta(client, admin_headers)
    nombre = f"Hip thrust {suf}"
    tid = _ejercicio_en_rutina(uid, nombre)
    _sesion(det_cli, tid, nombre, 6, [(100, "10", 8), (120, "8", 9)])

    mio = _ficha(client, h_cli, tid)["historial"][0]
    r = client.get(f"/api/session-logs/client/{det_cli}/fuerza", headers=h_coach)
    assert r.status_code == 200, r.text
    delcoach = [e for e in r.json()["data"]["ejercicios"]
                if e["nombre"] == nombre][0]["sesiones"][-1]

    for campo in ("peso_top", "reps_top", "rm1", "volumen", "series", "rir"):
        assert mio[campo] == delcoach[campo], (campo, mio[campo], delcoach[campo])
