"""La ficha del ejercicio, mientras el cliente entrena.

Al tocar la foto de un ejercicio a mitad de la serie solo se abría el vídeo.
Todo lo demás que el coach había escrito —cómo se hace, qué músculos trabaja,
con qué material, qué patrón de movimiento— estaba guardado y el cliente no
podía verlo en ninguna parte.

El catálogo de ejercicios NO es suyo: hay ejercicios privados de otras
organizaciones. Solo puede pedir los que están en alguna de sus rutinas.

Lo que hay que dejar sujeto:

  · Que la ficha traiga lo que el coach escribió del ejercicio.
  · Que los códigos salgan en palabras: "compound" y un 2 no le dicen nada a
    quien está entrenando con el móvil en la mano.
  · Y que NO pueda pedir un ejercicio que no tiene asignado.
"""
import uuid

from app.database import SessionLocal
from app.models.muscle_group import MuscleGroup
from app.models.routine import Routine, RoutineDay, RoutineDayDetail
from app.models.training import Training

from tests.test_org_scope import _crear_coach, _crear_usuario


def _musculo(nombre):
    db = SessionLocal()
    try:
        g = MuscleGroup(name=nombre)
        db.add(g); db.commit()
        return g.id
    finally:
        db.close()


def _ejercicio(nombre, **campos):
    db = SessionLocal()
    try:
        t = Training(name=nombre, **campos)
        db.add(t); db.commit()
        return t.id
    finally:
        db.close()


def _rutina_con(user_id, training_id):
    """Una rutina asignada a ese usuario con ese ejercicio dentro."""
    db = SessionLocal()
    try:
        r = Routine(name="Fuerza", user_id=user_id)
        db.add(r); db.flush()
        d = RoutineDay(routine_id=r.id, day_name="Día 1")
        db.add(d); db.flush()
        db.add(RoutineDayDetail(routine_id=r.id, routine_day_id=d.id,
                                training_id=training_id, series="4", repetitions="8"))
        db.commit()
        return r.id
    finally:
        db.close()


def _monta(client, admin_headers):
    suf = uuid.uuid4().hex[:8]
    _crear_coach(client, admin_headers, f"coach.fe.{suf}@nutrientrena-qa.com")
    uid, _det, h = _crear_usuario(client, admin_headers,
                                  f"cli.fe.{suf}@nutrientrena-qa.com", role_id=6)
    return uid, h, suf


def test_LA_FICHA_TRAE_LO_QUE_EL_COACH_ESCRIBIO(client, seed, admin_headers):
    uid, h, suf = _monta(client, admin_headers)
    pecho = _musculo(f"Pecho {suf}")
    triceps = _musculo(f"Tríceps {suf}")
    hombro = _musculo(f"Hombro {suf}")
    tid = _ejercicio(f"Press banca {suf}",
                     description="Tumbado en el banco, baja la barra al pecho.",
                     muscle_group_id=pecho,
                     secondary_muscle_group_ids=f"{triceps},{hombro}",
                     image="/img/press.jpg", video_url="https://youtu.be/abc",
                     material="Barra", movement_pattern="Empuje horizontal",
                     rec_series="3-4", rec_reps="8-12", rec_rest="90s")
    _rutina_con(uid, tid)

    r = client.get(f"/api/client/exercise/{tid}", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["description"].startswith("Tumbado"), d
    assert d["muscle_group_name"] == f"Pecho {suf}", d
    assert d["secondary_muscle_names"] == [f"Tríceps {suf}", f"Hombro {suf}"], d
    assert d["material"] == "Barra" and d["movement_pattern"] == "Empuje horizontal", d
    assert (d["rec_series"], d["rec_reps"], d["rec_rest"]) == ("3-4", "8-12", "90s"), d
    assert d["video_url"] == "https://youtu.be/abc", d


def test_LOS_CODIGOS_SALEN_EN_PALABRAS(client, seed, admin_headers):
    """«compound», «gym» y un 2 no le dicen nada a quien está entrenando."""
    uid, h, suf = _monta(client, admin_headers)
    tid = _ejercicio(f"Sentadilla {suf}", exercise_type="compound", location="gym",
                     difficulty_levels="2,3")
    _rutina_con(uid, tid)

    d = client.get(f"/api/client/exercise/{tid}", headers=h).json()["data"]
    assert d["exercise_type"] == "Compuesto", d
    assert d["location"] == "Gimnasio", d
    assert d["difficulty_names"] == ["Intermedio", "Avanzado"], d


def test_un_ejercicio_a_medio_rellenar_no_revienta_la_ficha(client, seed, admin_headers):
    """La mayoría del catálogo no tiene todos los campos. Lo que falta va
    vacío, y la pantalla decide qué enseñar."""
    uid, h, suf = _monta(client, admin_headers)
    tid = _ejercicio(f"Plancha {suf}")
    _rutina_con(uid, tid)

    d = client.get(f"/api/client/exercise/{tid}", headers=h).json()["data"]
    assert d["name"] == f"Plancha {suf}"
    assert d["description"] is None and d["material"] is None
    assert d["secondary_muscle_names"] == [] and d["difficulty_names"] == []


def test_NO_PUEDE_PEDIR_UN_EJERCICIO_QUE_NO_TIENE(client, seed, admin_headers):
    """El catálogo entero no es suyo: hay ejercicios privados de otras
    organizaciones y bastaría con acertar un número."""
    _uid, h, suf = _monta(client, admin_headers)
    ajeno = _ejercicio(f"Ejercicio de otra cuenta {suf}", description="secreto")

    r = client.get(f"/api/client/exercise/{ajeno}", headers=h)
    assert r.status_code == 404, r.text
    assert "secreto" not in r.text


def test_y_uno_que_no_existe_tampoco(client, seed, admin_headers):
    _uid, h, _suf = _monta(client, admin_headers)
    assert client.get("/api/client/exercise/99999999", headers=h).status_code == 404
