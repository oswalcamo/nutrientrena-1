"""Lo que el cliente ve al terminar un entreno.

Antes, al darle a «Terminar», salía una ventanita con cinco caras. Ahora se le
enseña el resumen de lo que acaba de hacer —duración, series, volumen y
récords— y se le preguntan dos cosas en una escala de 1 a 10: con qué energía
llegó y cuánto se esforzó.

Las cuentas se hacen en el servidor a propósito. Series y volumen podría
sacarlos el navegador, pero entonces habría DOS fórmulas para el mismo número:
la del móvil al terminar y la del historial que ve el coach. El día que
divergen —un "8-10" contado por el mayor en un sitio y por el primero en
otro— el cliente ve un volumen y su coach otro, y nadie sabe cuál es.

Lo que hay que dejar sujeto:

  · Que series y volumen cuenten SOLO lo marcado, como el tonelaje del coach.
  · Que un récord se mida por 1RM estimado y no por el peso a secas.
  · Que la primera vez que se hace un ejercicio cuente como récord, y que
    empatar no cuente.
  · Y que las dos respuestas se guarden: la energía tenía que perderse porque
    no había dónde ponerla.
"""
import uuid

from app.core.entrenos import mejor_marca, records_de
from app.database import SessionLocal
from app.models.session_log import WorkoutSession

from tests.test_macros_porcion import _monta


class _Serie:
    def __init__(self, reps, weight, done=True):
        self.reps, self.weight, self.done = reps, weight, done


class _Ej:
    def __init__(self, name, sets):
        self.name, self.sets = name, sets


# ── La cuenta, sin base de datos ───────────────────────────────────────────

def test_LA_MARCA_ES_EL_1RM_NO_EL_PESO():
    """80 kg × 8 es más que 100 kg × 1. Comparar por el peso a secas le diría
    al cliente que ha bajado el día que ha subido."""
    ocho = mejor_marca([_Serie("8", 80)])       # 80 × (1 + 8/30) = 101.3
    uno = mejor_marca([_Serie("1", 100)])       # 100 × (1 + 1/30) = 103.3
    assert ocho == 101.3 and uno == 103.3
    assert mejor_marca([_Serie("10", 80)]) > ocho


def test_una_serie_sin_marcar_no_es_una_marca():
    """Lo que dejó a medias no lo levantó."""
    assert mejor_marca([_Serie("8", 100, done=False)]) is None
    assert mejor_marca([_Serie("8", 100, done=False), _Serie("5", 60)]) == 70.0


def test_una_plancha_no_tiene_record():
    """Una serie por tiempo no tiene 1RM: no se le puede batir nada."""
    assert mejor_marca([_Serie("40s", 20)]) is None
    assert mejor_marca([_Serie("1 min", None)]) is None


def test_LA_PRIMERA_VEZ_CUENTA_COMO_RECORD():
    """Es la primera marca del ejercicio, y es lo que espera quien lo acaba de
    levantar."""
    rs = records_de([_Ej("Press banca", [_Serie("8", 80)])], {})
    assert len(rs) == 1 and rs[0]["previo"] is None


def test_EMPATAR_NO_ES_SUPERAR():
    """Repetir la misma marca no es un récord: si lo fuera, la pantalla diría
    récord cada semana y la palabra dejaría de significar nada."""
    ejercicios = [_Ej("Press banca", [_Serie("8", 80)])]
    assert records_de(ejercicios, {"press banca": 101.3}) == []
    assert len(records_de(ejercicios, {"press banca": 101.2})) == 1


def test_el_nombre_se_normaliza_para_encontrar_su_historia():
    """El cliente escribe «Press banca» y la semana que viene «press  Banca».
    Sin normalizar, la segunda no encuentra su historia y sale récord siempre."""
    assert records_de([_Ej("  press   BANCA ", [_Serie("8", 80)])],
                      {"press banca": 200}) == []


# ── Y de punta a punta ─────────────────────────────────────────────────────

def _cliente(client, admin_headers, suf):
    _h_coach, _det, h_cli = _monta(client, admin_headers, suf)
    return h_cli


def _sesion(reps, kg, done=True, nombre="Press banca"):
    return {"name": nombre, "sets": [{"reps": reps, "weight": kg, "done": done}]}


def test_SERIES_Y_VOLUMEN_SOLO_CUENTAN_LO_MARCADO(client, seed, admin_headers):
    """Sumar lo que dejó a medias sería contarle kilos que no levantó, y justo
    en las sesiones parciales —donde más importa— sería lo más falso."""
    h = _cliente(client, admin_headers, uuid.uuid4().hex[:8])
    r = client.post("/api/client/workout-summary", headers=h, json={"exercises": [
        {"name": "Press banca", "sets": [
            {"reps": "10", "weight": 60, "done": True},
            {"reps": "10", "weight": 60, "done": True},
            {"reps": "10", "weight": 60, "done": False},   # no la hizo
        ]},
    ]})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["sets"] == 2, d
    assert d["volume"] == 1200.0, d


def test_de_un_rango_se_cuenta_la_primera_cifra(client, seed, admin_headers):
    """Igual que el tonelaje del historial. Quedarse con la mayor infla el
    volumen y descuadra las dos pantallas."""
    h = _cliente(client, admin_headers, uuid.uuid4().hex[:8])
    d = client.post("/api/client/workout-summary", headers=h, json={
        "exercises": [_sesion("8-10", 50)]}).json()["data"]
    assert d["volume"] == 400.0, d


def test_UN_RECORD_SE_CUENTA_CONTRA_LO_QUE_YA_HABIA(client, seed, admin_headers):
    """El caso de verdad: se guarda una sesión y la siguiente se compara."""
    suf = uuid.uuid4().hex[:8]
    h = _cliente(client, admin_headers, suf)

    # La primera vez, récord.
    d = client.post("/api/client/workout-summary", headers=h, json={
        "exercises": [_sesion("8", 80)]}).json()["data"]
    assert d["records"] == 1, d

    guardar = client.post("/api/client/workout-session", headers=h, json={
        "duration_min": 45, "exercises": [_sesion("8", 80)]})
    assert guardar.status_code == 200, guardar.text

    # Lo mismo otra vez ya no lo es.
    d = client.post("/api/client/workout-summary", headers=h, json={
        "exercises": [_sesion("8", 80)]}).json()["data"]
    assert d["records"] == 0, d

    # Un kilo más, sí.
    d = client.post("/api/client/workout-summary", headers=h, json={
        "exercises": [_sesion("8", 81)]}).json()["data"]
    assert d["records"] == 1, d
    assert d["record_exercises"][0]["previo"] == 101.3, d


def test_LAS_DOS_RESPUESTAS_SE_GUARDAN(client, seed, admin_headers):
    """La energía no tenía columna: la respuesta se perdía al guardar."""
    suf = uuid.uuid4().hex[:8]
    h = _cliente(client, admin_headers, suf)
    r = client.post("/api/client/workout-session", headers=h, json={
        "duration_min": 50, "energy": 7, "rpe": 8, "mood": 4,
        "exercises": [_sesion("8", 80)]})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        s = db.query(WorkoutSession).filter(
            WorkoutSession.id == r.json()["data"]["id"]).first()
        assert s.energy == 7, "la energía con la que llegó no se ha guardado"
        assert s.rpe == 8, "el esfuerzo no se ha guardado"
        assert s.mood == 4, "el ánimo no se ha guardado"
    finally:
        db.close()


def test_EL_COACH_VE_LA_ENERGIA_DE_SU_CLIENTE(client, seed, admin_headers):
    """Un dato que el cliente contesta y nadie puede leer no sirve de nada:
    tiene que llegar a la ficha, al lado del esfuerzo."""
    suf = uuid.uuid4().hex[:8]
    h_coach, det_cli, h_cli = _monta(client, admin_headers, suf)
    client.post("/api/client/workout-session", headers=h_cli, json={
        "duration_min": 55, "energy": 3, "rpe": 9, "exercises": [_sesion("8", 80)]})

    r = client.get(f"/api/session-logs/client/{det_cli}/historial", headers=h_coach)
    assert r.status_code == 200, r.text
    filas = [f for f in r.json()["data"]["sesiones"] if f["registrada"]]
    assert filas, r.text
    assert filas[0]["energy"] == 3, filas[0]
    assert filas[0]["rpe"] == 9, filas[0]


def test_no_contestar_no_inventa_un_valor(client, seed, admin_headers):
    """Vacío es vacío. Un 5 por defecto sería un dato que el cliente no dio, y
    el coach lo leería como si lo hubiera dado."""
    h = _cliente(client, admin_headers, uuid.uuid4().hex[:8])
    r = client.post("/api/client/workout-session", headers=h, json={
        "duration_min": 30, "exercises": [_sesion("8", 80)]})
    db = SessionLocal()
    try:
        s = db.query(WorkoutSession).filter(
            WorkoutSession.id == r.json()["data"]["id"]).first()
        assert s.energy is None and s.rpe is None and s.mood is None
    finally:
        db.close()


def test_fuera_de_la_escala_no_entra(client, seed, admin_headers):
    """1 a 10. Un 11 guardado sin más rompería cualquier media que se haga."""
    h = _cliente(client, admin_headers, uuid.uuid4().hex[:8])
    for energia in (0, 11):
        r = client.post("/api/client/workout-session", headers=h, json={
            "duration_min": 30, "energy": energia, "exercises": []})
        assert r.status_code == 422, (energia, r.text)
