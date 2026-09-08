"""El objetivo de la dieta y lo que hay de verdad en el plato.

Son dos cosas distintas y se estaban mezclando por los dos lados.

Al MIRAR: la lista enseñaba la meta escrita. Una dieta con 1164 kcal de
objetivo y 1572 montadas salía como 1164, y el coach leía esa fila como lo que
su cliente iba a comer. Ahora las cuatro cifras salen de los alimentos, y la
meta se ve donde toca —el editor pinta "1572 /1164 · 408 kcal de más"—.

Al EDITAR: `/edit` devuelve las cifras rellenas para poder mirarlas, y esa
misma respuesta carga el formulario. El editor no podía distinguir «el coach
escribió 1164» de «los alimentos suman 1164», así que metía la suma en la
casilla del objetivo y al guardar la almacenaba como si alguien la hubiera
tecleado. Desde ahí la cifra quedaba congelada.

Lo que hay que dejar sujeto:

  · Que la respuesta diga por separado lo escrito (`objetivo`) y lo calculado.
  · Que las cifras que se enseñan salgan de los alimentos, no de la meta.
  · Que abrir una dieta y guardarla SIN TOCAR NADA no le invente un objetivo.
  · Y que la meta escrita no se pierda: el editor la necesita entera.
"""
import uuid

from tests.test_macros_porcion import _alimento, _monta


def _crea(client, h, titulo, foods, **objetivo):
    r = client.post("/api/diets", headers=h, json={"title": titulo, "foods": foods, **objetivo})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _edit(client, h, did):
    r = client.get(f"/api/diets/{did}/edit", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _en_lista(client, h, did):
    dietas = client.get("/api/diets/findAll", headers=h).json()["data"]
    fila = [d for d in dietas if d["id"] == did]
    assert fila, "la dieta no sale en la lista"
    return fila[0]


def _comida(aliment_id, cantidad, nombre="Media mañana"):
    return {"name": nombre, "time": "11:00",
            "detail": [{"aliment_id": aliment_id, "quantity_calc": cantidad, "order": 0}]}


# ── La respuesta separa las dos cosas ──────────────────────────────────────

def test_LO_ESCRITO_Y_LO_CALCULADO_VIENEN_POR_SEPARADO(client, seed, admin_headers):
    """Sin esto el formulario no puede saber qué escribió el coach."""
    suf = uuid.uuid4().hex[:8]
    h, _det, _hc = _monta(client, admin_headers, suf)
    pollo = _alimento(f"Pollo {suf}", 165.0, 100.0, "g")   # 10P 1C 5G por 100 g
    did = _crea(client, h, f"Sin objetivo {suf}", [_comida(pollo, 200)])

    d = _edit(client, h, did)
    # Para mirar: las cifras rellenas con lo que suman los alimentos.
    assert d["calories"] == 330, d
    assert d["detail"]["proteins"] == 20, d
    # Para editar: lo que el coach escribió, que es nada.
    assert d["goal_mode"] == "libre", d
    assert d["objetivo"] == {"calories": None, "proteins": None, "carbs": None,
                             "fats": None, "fiber": None}, d["objetivo"]


def test_y_cuando_si_escribio_algo_sale_lo_suyo(client, seed, admin_headers):
    suf = uuid.uuid4().hex[:8]
    h, _det, _hc = _monta(client, admin_headers, suf)
    pollo = _alimento(f"Pollo {suf}", 165.0, 100.0, "g")
    did = _crea(client, h, f"Con objetivo {suf}", [_comida(pollo, 200)],
                calories=1800, proteins=120)

    d = _edit(client, h, did)
    assert d["goal_mode"] == "macros", d
    assert d["objetivo"]["calories"] == 1800
    assert d["objetivo"]["proteins"] == 120
    # Lo que no escribió sigue vacío en el objetivo, aunque la lista lo rellene.
    assert d["objetivo"]["carbs"] is None and d["objetivo"]["fats"] is None, d["objetivo"]
    assert d["detail"]["carbs"] == 2, "la lista sí lo rellena"


# ── El caso reportado ──────────────────────────────────────────────────────

def _como_lo_manda_el_navegador(d, titulo=None):
    """El formulario reenvía LO QUE EL COACH ESCRIBIÓ, no lo calculado."""
    obj = d["objetivo"]
    libre = d["goal_mode"] == "libre"
    return {
        "title": titulo or d["title"],
        "calories": None if libre else obj["calories"],
        "proteins": None if libre else obj["proteins"],
        "carbs": None if libre else obj["carbs"],
        "fats": None if libre else obj["fats"],
        "foods": [
            {"name": f["name"], "time": f.get("time"), "subtitle": f.get("subtitle"),
             "detail": [{"aliment_id": a["aliment_id"], "quantity_calc": a.get("quantity"),
                         "order": a.get("order") or 0} for a in f.get("detail") or []]}
            for f in d.get("foods") or []
        ],
    }


def test_DUPLICAR_Y_ANADIR_UN_ALIMENTO_MUEVE_LAS_CIFRAS(client, seed, admin_headers):
    """El caso de la captura: la copia lleva un alimento más y la lista seguía
    diciendo las mismas kcal que la original."""
    suf = uuid.uuid4().hex[:8]
    h, _det, _hc = _monta(client, admin_headers, suf)
    aceite = _alimento(f"Aceite {suf}", 899.0, 100.0, "g")
    acedera = _alimento(f"Acedera {suf}", 33.0, 100.0, "g")
    original = _crea(client, h, f"dia martes {suf}", [_comida(aceite, 100)])
    assert _en_lista(client, h, original)["calories"] == 899

    # Se duplica: el editor reenvía el formulario con un alimento más.
    cuerpo = _como_lo_manda_el_navegador(_edit(client, h, original), f"dia martes {suf} (Copia)")
    cuerpo["foods"][0]["detail"].append(
        {"aliment_id": acedera, "quantity_calc": 100, "order": 1})
    copia = client.post("/api/diets", headers=h, json=cuerpo).json()["data"]["id"]

    assert _en_lista(client, h, copia)["calories"] == 932, \
        "la copia sigue diciendo las kcal de la original"
    assert _en_lista(client, h, original)["calories"] == 899, "y la original no se ha movido"


def test_ABRIR_Y_GUARDAR_SIN_TOCAR_NADA_NO_INVENTA_UN_OBJETIVO(client, seed, admin_headers):
    """Es lo que congelaba la cifra: la suma entraba en la casilla del objetivo
    y se guardaba como si alguien la hubiera tecleado."""
    suf = uuid.uuid4().hex[:8]
    h, _det, _hc = _monta(client, admin_headers, suf)
    aceite = _alimento(f"Aceite {suf}", 899.0, 100.0, "g")
    acedera = _alimento(f"Acedera {suf}", 33.0, 100.0, "g")
    did = _crea(client, h, f"dia martes {suf}", [_comida(aceite, 100)])

    d = _edit(client, h, did)
    cuerpo = _como_lo_manda_el_navegador(d)
    cuerpo["id"] = did
    assert client.put(f"/api/diets/{did}/update", headers=h, json=cuerpo).status_code == 200

    # Sigue sin objetivo escrito, así que sus cifras siguen saliendo de la comida.
    assert _edit(client, h, did)["goal_mode"] == "libre", "le ha inventado un objetivo"

    # Y por eso añadir un alimento ahora sí se nota.
    cuerpo = _como_lo_manda_el_navegador(_edit(client, h, did))
    cuerpo["id"] = did
    cuerpo["foods"][0]["detail"].append(
        {"aliment_id": acedera, "quantity_calc": 100, "order": 1})
    client.put(f"/api/diets/{did}/update", headers=h, json=cuerpo)
    assert _en_lista(client, h, did)["calories"] == 932


def test_EL_OBJETIVO_SE_CONSERVA_AUNQUE_LA_LISTA_ENSENE_LO_QUE_HAY(client, seed, admin_headers):
    """Una plantilla de 1800 kcal con 899 en el plato: la lista dice 899 —es lo
    que el cliente se va a comer— y la meta sigue guardada para el editor, que
    la pinta al lado ("899 /1800"). Guardar desde el formulario no la pierde."""
    suf = uuid.uuid4().hex[:8]
    h, _det, _hc = _monta(client, admin_headers, suf)
    aceite = _alimento(f"Aceite {suf}", 899.0, 100.0, "g")
    did = _crea(client, h, f"Plantilla {suf}", [_comida(aceite, 100)], calories=1800)

    cuerpo = _como_lo_manda_el_navegador(_edit(client, h, did))
    cuerpo["id"] = did
    client.put(f"/api/diets/{did}/update", headers=h, json=cuerpo)

    assert _en_lista(client, h, did)["calories"] == 899, "la lista tiene que decir lo que hay"
    assert _edit(client, h, did)["objetivo"]["calories"] == 1800, "y la meta no se pierde"
    assert _edit(client, h, did)["goal_mode"] == "kcal"


def test_EL_CASO_DE_LA_CAPTURA(client, seed, admin_headers):
    """«dia martes»: meta de 1164 kcal y 1572 en el plato —899 de aceite y 673
    de tocino—. La fila decía 1164, que es lo que el coach había puesto de
    meta, y se leía como lo que su cliente iba a comer."""
    suf = uuid.uuid4().hex[:8]
    h, _det, _hc = _monta(client, admin_headers, suf)
    aceite = _alimento(f"Aceite de cacahuete {suf}", 899.0, 100.0, "g")
    tocino = _alimento(f"Tocino {suf}", 673.0, 100.0, "g")
    did = _crea(client, h, f"dia martes {suf}", calories=1164, foods=[
        {"name": "Media mañana", "time": "11:00", "detail": [
            {"aliment_id": aceite, "quantity_calc": 100, "order": 0},
            {"aliment_id": tocino, "quantity_calc": 100, "order": 1}]}])

    assert _en_lista(client, h, did)["calories"] == 1572, "la fila sigue diciendo la meta"
    # Y la meta sigue ahí: el editor la pinta al lado, con lo que se pasa.
    assert _edit(client, h, did)["objetivo"]["calories"] == 1164
