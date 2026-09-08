"""Lo que el coach ESCRIBIÓ como objetivo, y lo que suman los alimentos.

La lista de dietas rellena las cifras que el coach no escribió con lo que suman
los alimentos: una dieta sin objetivo no sale con cuatro guiones al lado de sus
comidas. Eso está bien para MIRAR.

El problema es que `/edit` —la misma respuesta— es lo que carga el FORMULARIO.
El editor no podía distinguir «el coach escribió 1164» de «los alimentos suman
1164», así que metía la suma en la casilla del objetivo y al guardar la
almacenaba como si alguien la hubiera tecleado. Desde ese momento la cifra
quedaba congelada: se duplicaba la dieta, se le añadía un alimento y la lista
seguía diciendo lo mismo que la original.

Lo que hay que dejar sujeto:

  · Que la respuesta diga por separado lo escrito y lo calculado.
  · Que abrir una dieta y guardarla SIN TOCAR NADA no le invente un objetivo.
  · Y que entonces sí: añadir un alimento mueve las cifras de la lista.
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


def test_y_el_objetivo_que_SI_se_escribio_no_se_pisa(client, seed, admin_headers):
    """Lo de siempre: una plantilla de 1800 kcal sigue siendo de 1800 aunque la
    comida de hoy sume 900."""
    suf = uuid.uuid4().hex[:8]
    h, _det, _hc = _monta(client, admin_headers, suf)
    aceite = _alimento(f"Aceite {suf}", 899.0, 100.0, "g")
    did = _crea(client, h, f"Plantilla {suf}", [_comida(aceite, 100)], calories=1800)

    cuerpo = _como_lo_manda_el_navegador(_edit(client, h, did))
    cuerpo["id"] = did
    client.put(f"/api/diets/{did}/update", headers=h, json=cuerpo)
    assert _en_lista(client, h, did)["calories"] == 1800
    assert _edit(client, h, did)["objetivo"]["calories"] == 1800
