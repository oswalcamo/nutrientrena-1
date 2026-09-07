"""Duplicar una dieta.

El botón «Duplicar» de la biblioteca no copia nada en el servidor: abre el
editor con la dieta cargada, le quita el identificador y deja que el coach
guarde. Lo que se manda, entonces, es el formulario TAL COMO ESTÁ — y el
formulario arrastra los identificadores de las comidas y de las filas de la
dieta ORIGINAL, que es de donde se cargó.

Al crear, el servidor buscaba cada comida por `(id, diet_id)`. En una dieta
recién creada ninguno de esos identificadores existe, así que no encontraba
ninguna y las saltaba todas, una por una, sin decir nada: la copia se creaba
con su título y sus objetivos, y VACÍA. El coach veía «Dieta creada».

Y un nivel más abajo la búsqueda de las filas ni siquiera miraba de qué dieta
eran: un identificador de otra dieta encontraba su fila y se la reescribía.
Eso no es que se pierda una copia, es que se estropea el original.

Lo que hay que dejar sujeto:

  · Que la copia salga con sus comidas y sus alimentos.
  · Que el original no se entere de que lo han copiado.
  · Que una fila de otra dieta no se pueda tocar desde ésta.
"""
import uuid

from app.database import SessionLocal
from app.models.nutrition.diet import DietFoodAliment

from tests.test_macros_porcion import _alimento, _monta


def _crea_dieta(client, h, suf):
    """La dieta de partida: dos comidas, tres alimentos."""
    pollo = _alimento(f"Pollo {suf}", 165.0, 100.0, "g")
    arroz = _alimento(f"Arroz {suf}", 130.0, 100.0, "g")
    huevo = _alimento(f"Huevo {suf}", 74.0, 1.0, "ud")
    r = client.post("/api/diets", headers=h, json={
        "title": f"Volumen {suf}", "calories": 2200, "notes": "sin lactosa",
        "foods": [
            {"name": "Desayuno", "time": "08:00", "subtitle": "Huevos revueltos",
             "detail": [{"aliment_id": huevo, "quantity_calc": 3, "order": 0}]},
            {"name": "Comida", "time": "14:00", "detail": [
                {"aliment_id": pollo, "quantity_calc": 150, "order": 0},
                {"aliment_id": arroz, "quantity_calc": 80, "order": 1}]},
        ]})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _editor(client, h, did):
    """Lo que el editor recibe al abrir la dieta: es lo que luego reenvía."""
    r = client.get(f"/api/diets/{did}/edit", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _como_lo_manda_el_navegador(d, titulo):
    """El payload de «Duplicar»: el formulario entero, con los identificadores
    de la dieta de la que se cargó."""
    return {
        "title": titulo,
        "calories": d.get("calories"),
        "notes": d.get("notes"),
        "foods": [
            {"id": f["id"], "name": f["name"], "subtitle": f.get("subtitle"),
             "time": f.get("time"),
             "detail": [{"id": a["id"], "aliment_id": a["aliment_id"],
                         "quantity_calc": a.get("quantity"), "order": a.get("order") or 0}
                        for a in f.get("detail") or []]}
            for f in d.get("foods") or []
        ],
    }


def _resumen(d):
    """Lo que hay dentro, sin identificadores: para comparar copia y original."""
    return [(f["name"], f.get("time"), f.get("subtitle"),
             sorted(((a.get("aliment") or {}).get("name"), a.get("quantity"))
                    for a in f.get("detail") or []))
            for f in d.get("foods") or []]


# ── El caso reportado ───────────────────────────────────────────────────────

def test_LA_COPIA_NO_SALE_VACIA(client, seed, admin_headers):
    """El fallo tal cual: «Dieta creada», y dentro no había nada."""
    suf = uuid.uuid4().hex[:8]
    h, _det, _hc = _monta(client, admin_headers, suf)
    did = _crea_dieta(client, h, suf)

    cuerpo = _como_lo_manda_el_navegador(_editor(client, h, did), f"Volumen {suf} (Copia)")
    r = client.post("/api/diets", headers=h, json=cuerpo)
    assert r.status_code == 200, r.text
    copia = _editor(client, h, r.json()["data"]["id"])

    assert len(copia["foods"]) == 2, f"la copia se creó vacía: {copia['foods']}"
    assert _resumen(copia) == _resumen(_editor(client, h, did))


def test_la_copia_tiene_sus_propias_filas(client, seed, admin_headers):
    """Copiar no es compartir: si las filas fueran las mismas, tocar la copia
    le cambiaría la dieta al cliente que tiene el original asignado."""
    suf = uuid.uuid4().hex[:8]
    h, _det, _hc = _monta(client, admin_headers, suf)
    did = _crea_dieta(client, h, suf)
    original = _editor(client, h, did)

    r = client.post("/api/diets", headers=h,
                    json=_como_lo_manda_el_navegador(original, f"Volumen {suf} (Copia)"))
    copia = _editor(client, h, r.json()["data"]["id"])

    ids = lambda d: {a["id"] for f in d["foods"] for a in f.get("detail") or []}
    assert ids(copia) and not (ids(copia) & ids(original)), "las filas son las mismas"
    comidas = lambda d: {f["id"] for f in d["foods"]}
    assert not (comidas(copia) & comidas(original)), "las comidas son las mismas"


def test_EL_ORIGINAL_NO_SE_ENTERA(client, seed, admin_headers):
    """Duplicar y luego cambiar la copia no puede mover el original."""
    suf = uuid.uuid4().hex[:8]
    h, _det, _hc = _monta(client, admin_headers, suf)
    did = _crea_dieta(client, h, suf)
    antes = _resumen(_editor(client, h, did))

    cuerpo = _como_lo_manda_el_navegador(_editor(client, h, did), f"Volumen {suf} (Copia)")
    # El coach le sube el arroz a la copia antes de guardarla.
    for f in cuerpo["foods"]:
        for a in f["detail"]:
            a["quantity_calc"] = 999
    r = client.post("/api/diets", headers=h, json=cuerpo)
    assert r.status_code == 200, r.text

    assert _resumen(_editor(client, h, did)) == antes, "le ha movido las cantidades al original"


# ── Y la puerta de atrás que lo permitía ────────────────────────────────────

def test_UNA_FILA_DE_OTRA_DIETA_NO_SE_TOCA(client, seed, admin_headers):
    """Guardar la dieta B mandando el identificador de una fila de A: la fila
    de A no es suya y no se toca. La búsqueda no filtraba por dieta."""
    suf = uuid.uuid4().hex[:8]
    h, _det, _hc = _monta(client, admin_headers, suf)
    a_id = _crea_dieta(client, h, suf)
    b_id = _crea_dieta(client, h, suf + "b")
    a = _editor(client, h, a_id)
    fila_de_a = a["foods"][0]["detail"][0]

    b = _editor(client, h, b_id)
    cuerpo = {"id": b_id, "title": b["title"], "foods": [
        {"id": b["foods"][0]["id"], "name": b["foods"][0]["name"], "detail": [
            {"id": fila_de_a["id"], "aliment_id": fila_de_a["aliment_id"],
             "quantity_calc": 777, "order": 0}]}]}
    r = client.put(f"/api/diets/{b_id}/update", headers=h, json=cuerpo)
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        sigue = db.query(DietFoodAliment).filter(
            DietFoodAliment.id == fila_de_a["id"]).first()
        assert sigue is not None, "le ha borrado la fila a la otra dieta"
        assert float(sigue.quantity) == float(fila_de_a["quantity"]), \
            "le ha cambiado la cantidad a la otra dieta"
        assert str(sigue.diet_id) == str(a_id), "se ha llevado la fila a otra dieta"
    finally:
        db.close()
