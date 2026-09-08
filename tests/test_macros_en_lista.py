"""Kcal / Prot / Carb / Grasa en la lista de dietas: lo que hay en el plato.

Empezó siendo otra cosa. Una dieta en modo "kcal" —el coach escribe las kcal
objetivo y no toca los macros— salía con 1439 kcal y tres guiones al lado, con
las comidas enteras debajo; se arregló rellenando cada cifra por su cuenta,
pero dejando mandar a lo escrito sobre lo sumado.

Con eso, una plantilla con 1164 kcal de meta y 1572 en el plato salía en la
lista como 1164, y el coach leía esa fila como lo que su cliente iba a comer.
El objetivo es una META, no un dato de la dieta: la lista enseña AHORA lo que
suman los alimentos, y el objetivo se ve donde toca —el editor pinta
"1572 /1164 · 408 kcal de más"— y viaja aparte en `objetivo`.

Lo que hay que dejar sujeto:

  · Que las cuatro cifras salgan de los alimentos que hay montados.
  · Que el objetivo escrito NO las pise, ni siquiera cuando existe.
  · Que sin nada montado se enseñe lo escrito, que es lo único que hay.
  · Y que la suma respete la porción del alimento, como en todas partes.
"""
import uuid

from tests.test_macros_porcion import _alimento, _monta


def _crear(client, h_coach, suf, foods, **objetivo):
    r = client.post("/api/diets", headers=h_coach, json={
        "title": f"Low Carb {suf}", "foods": foods, **objetivo})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _en_lista(client, h_coach, did):
    dietas = client.get("/api/diets/findAll", headers=h_coach).json()["data"]
    mias = [d for d in dietas if d["id"] == did]
    assert mias, "la dieta no sale en la lista"
    return mias[0]


# El pollo de pruebas lleva 10 g de proteína, 1 de carbo y 5 de grasa por
# porción de 100 g. 150 g -> 15 / 1.5 / 7.5.
def _pollo(suf):
    return _alimento(f"Pollo {suf}", 165.0, 100.0, "g")


def test_LAS_CUATRO_CIFRAS_SALEN_DE_LOS_ALIMENTOS(client, seed, admin_headers):
    """150 g de un pollo de 165 kcal/100 g: 248 kcal, no las 1500 de la meta."""
    suf = uuid.uuid4().hex[:8]
    h_coach, _det, _hc = _monta(client, admin_headers, suf)
    did = _crear(client, h_coach, suf, calories=1500, foods=[
        {"name": "Comida", "time": "14:00", "detail": [
            {"aliment_id": _pollo(suf), "quantity_calc": 150, "order": 0}]}])

    d = _en_lista(client, h_coach, did)
    assert d["calories"] == 248, "sigue enseñando la meta en vez de lo que hay"
    det = d["detail"] or {}
    assert det.get("proteins") == 15, det
    assert det.get("carbs") == 1.5, det
    assert det.get("fats") == 7.5, det


def test_EL_OBJETIVO_ESCRITO_NO_PISA_LO_QUE_HAY_EN_EL_PLATO(client, seed, admin_headers):
    """El caso reportado: meta de 120 g de proteína y 15 montados. La fila dice
    15, que es lo que el cliente se va a comer. La meta se ve en el editor."""
    suf = uuid.uuid4().hex[:8]
    h_coach, _det, _hc = _monta(client, admin_headers, suf)
    did = _crear(client, h_coach, suf, calories=1500, proteins=120, carbs=100, fats=50,
                 foods=[{"name": "Comida", "time": "14:00", "detail": [
                     {"aliment_id": _pollo(suf), "quantity_calc": 150, "order": 0}]}])

    d = _en_lista(client, h_coach, did)
    assert d["calories"] == 248, d
    det = d["detail"]
    assert (det["proteins"], det["carbs"], det["fats"]) == (15, 1.5, 7.5), det


def test_pero_el_objetivo_sigue_guardado_y_se_puede_leer(client, seed, admin_headers):
    """Enseñar lo real no es perder la meta: el editor la necesita entera."""
    suf = uuid.uuid4().hex[:8]
    h_coach, _det, _hc = _monta(client, admin_headers, suf)
    did = _crear(client, h_coach, suf, calories=1500, proteins=120,
                 foods=[{"name": "Comida", "time": "14:00", "detail": [
                     {"aliment_id": _pollo(suf), "quantity_calc": 150, "order": 0}]}])

    d = client.get(f"/api/diets/{did}/edit", headers=h_coach).json()["data"]
    assert d["objetivo"]["calories"] == 1500
    assert d["objetivo"]["proteins"] == 120
    assert d["goal_mode"] == "macros"


def test_el_detalle_de_la_dieta_dice_lo_mismo_que_la_lista(client, seed, admin_headers):
    """La lista y el previo leen el mismo dato; si divergieran, el coach
    vería una cifra en la fila y otra al abrirla."""
    suf = uuid.uuid4().hex[:8]
    h_coach, _det, _hc = _monta(client, admin_headers, suf)
    did = _crear(client, h_coach, suf, calories=1500, foods=[
        {"name": "Comida", "time": "14:00", "detail": [
            {"aliment_id": _pollo(suf), "quantity_calc": 150, "order": 0}]}])

    lista = _en_lista(client, h_coach, did)["detail"]
    previo = client.get(f"/api/diets/{did}/edit", headers=h_coach).json()["data"]["detail"]
    assert (previo["proteins"], previo["carbs"], previo["fats"]) == \
        (lista["proteins"], lista["carbs"], lista["fats"])


def test_la_suma_respeta_la_porcion_del_alimento(client, seed, admin_headers):
    """Dos huevos por unidad: 20 g de proteína, no 0,2."""
    suf = uuid.uuid4().hex[:8]
    h_coach, _det, _hc = _monta(client, admin_headers, suf)
    huevo = _alimento(f"Huevo {suf}", 74.0, 1.0, "ud")
    did = _crear(client, h_coach, suf, calories=1500, foods=[
        {"name": "Desayuno", "time": "08:00", "detail": [
            {"aliment_id": huevo, "quantity_calc": 2, "order": 0}]}])

    det = _en_lista(client, h_coach, did)["detail"]
    assert det["proteins"] == 20, det
    assert det["fats"] == 10, det


def test_sin_alimentos_se_enseña_lo_escrito(client, seed, admin_headers):
    """Una plantilla recién creada con su meta y sin comidas todavía: no hay
    nada que sumar, así que se enseña la meta. Un 0 diría que el cliente no
    come nada, y los macros que nadie escribió siguen vacíos: eso es la
    verdad, no un cero que parezca un dato."""
    suf = uuid.uuid4().hex[:8]
    h_coach, _det, _hc = _monta(client, admin_headers, suf)
    did = _crear(client, h_coach, suf, calories=1500, foods=[])

    d = _en_lista(client, h_coach, did)
    assert d["calories"] == 1500
    det = d.get("detail") or {}
    assert not det.get("proteins") and not det.get("carbs") and not det.get("fats"), det
