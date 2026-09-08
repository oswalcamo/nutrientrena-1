"""Lo que ve el cliente de su dieta: kcal del día y macros.

El plan del cliente sacaba los macros SOLO de lo que el coach hubiera escrito
como objetivo al crear la dieta. Con un plan montado en modo "kcal" —el más
habitual: se escriben las kcal y no los macros— el cliente abría su nutrición
y veía un guion en proteínas, carbohidratos y grasas, con las comidas enteras
listadas debajo.

Es el mismo fallo que tenía la lista de dietas del coach, en el otro lado de
la aplicación. Ahora la cuenta es UNA: `app/core/macros.totales_de_dieta`.

Lo que hay que dejar sujeto:

  · Que el cliente vea los macros de su día aunque nadie los escribiera.
  · Que respeten la porción de cada alimento, como en todas partes.
  · Que se le enseñe LO QUE HAY EN EL PLATO y no la meta del coach: la cifra
    que tiene delante mientras come es la de lo que se está comiendo.
  · Y que el coach y el cliente digan lo mismo de la misma dieta.
"""
import uuid

from tests.test_macros_porcion import _alimento, _monta


def _dieta_asignada(client, h_coach, det_cli, suf, detalles, **objetivo):
    """Una dieta montada y asignada al cliente, como la haría el coach."""
    r = client.post("/api/diets", headers=h_coach, json={
        "title": f"Plan {suf}",
        "foods": [{"name": "Desayuno", "time": "08:00", "detail": detalles}],
        **objetivo})
    assert r.status_code == 200, r.text
    did = r.json()["data"]["id"]
    r = client.post(f"/api/diets/{did}/assign", headers=h_coach, json={"client_id": det_cli})
    assert r.status_code == 200, r.text
    return did


def _dia_de_hoy(client, h_cli):
    r = client.get("/api/client/nutrition", headers=h_cli)
    assert r.status_code == 200, r.text
    dias = r.json()["data"]["days"]
    assert dias, r.json()["data"]
    return [d for d in dias if d["is_today"]][0]


# El pollo de pruebas trae 10 g de proteína, 1 de carbo y 5 de grasa por 100 g.
def test_EL_CLIENTE_VE_SUS_MACROS_AUNQUE_NADIE_LOS_ESCRIBIERA(client, seed, admin_headers):
    """El caso reportado: tres guiones donde tenían que ir los macros."""
    suf = uuid.uuid4().hex[:8]
    h_coach, det_cli, h_cli = _monta(client, admin_headers, suf)
    pollo = _alimento(f"Pollo {suf}", 165.0, 100.0, "g")
    # Modo "kcal": el coach escribe el objetivo en calorías y ningún macro.
    _dieta_asignada(client, h_coach, det_cli, suf,
                    [{"aliment_id": pollo, "quantity_calc": 200, "order": 0}],
                    calories=1500)

    dia = _dia_de_hoy(client, h_cli)
    assert dia["protein"] == 20, dia      # 10 g / 100 g × 200
    assert dia["carbs"] == 2, dia
    assert dia["fats"] == 10, dia


def test_y_las_kcal_del_dia(client, seed, admin_headers):
    """Sin kcal escritas, el día salía sin ninguna cifra al lado del nombre."""
    suf = uuid.uuid4().hex[:8]
    h_coach, det_cli, h_cli = _monta(client, admin_headers, suf)
    pollo = _alimento(f"Pollo {suf}", 165.0, 100.0, "g")
    _dieta_asignada(client, h_coach, det_cli, suf,
                    [{"aliment_id": pollo, "quantity_calc": 200, "order": 0}])

    assert _dia_de_hoy(client, h_cli)["kcal"] == 330


def test_RESPETA_LA_PORCION_DEL_ALIMENTO(client, seed, admin_headers):
    """Dos huevos son dos huevos, no la centésima parte de uno."""
    suf = uuid.uuid4().hex[:8]
    h_coach, det_cli, h_cli = _monta(client, admin_headers, suf)
    huevo = _alimento(f"Huevo {suf}", 74.0, 1.0, "ud")
    _dieta_asignada(client, h_coach, det_cli, suf,
                    [{"aliment_id": huevo, "quantity_calc": 2, "order": 0}])

    dia = _dia_de_hoy(client, h_cli)
    assert dia["kcal"] == 148, dia
    assert dia["protein"] == 20, dia      # 10 g por unidad × 2


def test_AL_CLIENTE_SE_LE_ENSEÑA_LO_QUE_HAY_EN_EL_PLATO(client, seed, admin_headers):
    """Aunque el coach haya puesto una meta de 1500 kcal, el día tiene 330.

    Con la meta mandando, el cliente abría su nutrición, leía 1500 y debajo
    tenía la comida de 330. La cifra que tiene delante mientras come tiene que
    ser la de lo que se está comiendo; la meta es cosa del coach y se ve en su
    editor."""
    suf = uuid.uuid4().hex[:8]
    h_coach, det_cli, h_cli = _monta(client, admin_headers, suf)
    pollo = _alimento(f"Pollo {suf}", 165.0, 100.0, "g")
    _dieta_asignada(client, h_coach, det_cli, suf,
                    [{"aliment_id": pollo, "quantity_calc": 200, "order": 0}],
                    calories=1500, proteins=120, carbs=100, fats=50)

    dia = _dia_de_hoy(client, h_cli)
    assert (dia["kcal"], dia["protein"], dia["carbs"], dia["fats"]) == (330, 20, 2, 10), dia


def test_EL_COACH_Y_EL_CLIENTE_DICEN_LO_MISMO(client, seed, admin_headers):
    """Es el motivo de que la cuenta viva en un solo sitio: dos cuentas
    parecidas acaban dando dos números para la misma dieta."""
    suf = uuid.uuid4().hex[:8]
    h_coach, det_cli, h_cli = _monta(client, admin_headers, suf)
    pollo = _alimento(f"Pollo {suf}", 165.0, 100.0, "g")
    did = _dieta_asignada(client, h_coach, det_cli, suf,
                          [{"aliment_id": pollo, "quantity_calc": 150, "order": 0}],
                          calories=1500)

    del_coach = client.get(f"/api/diets/{did}/edit", headers=h_coach).json()["data"]
    dia = _dia_de_hoy(client, h_cli)
    assert dia["protein"] == del_coach["detail"]["proteins"], (dia, del_coach["detail"])
    assert dia["carbs"] == del_coach["detail"]["carbs"]
    assert dia["fats"] == del_coach["detail"]["fats"]


def test_una_dieta_sin_alimentos_no_inventa_macros(client, seed, admin_headers):
    """Un cero se leería como "hoy no comes proteína"; lo que pasa es que la
    dieta está vacía."""
    suf = uuid.uuid4().hex[:8]
    h_coach, det_cli, h_cli = _monta(client, admin_headers, suf)
    _dieta_asignada(client, h_coach, det_cli, suf, [], calories=1500)

    dia = _dia_de_hoy(client, h_cli)
    assert dia["protein"] is None and dia["carbs"] is None and dia["fats"] is None, dia
    assert dia["kcal"] == 1500, dia


def test_las_comidas_siguen_llegando_con_sus_alimentos(client, seed, admin_headers):
    """Lo que ya funcionaba no se toca: el cliente ve qué come y cuánto."""
    suf = uuid.uuid4().hex[:8]
    h_coach, det_cli, h_cli = _monta(client, admin_headers, suf)
    huevo = _alimento(f"Huevo {suf}", 74.0, 1.0, "ud")
    _dieta_asignada(client, h_coach, det_cli, suf,
                    [{"aliment_id": huevo, "quantity_calc": 2, "order": 0}])

    comida = _dia_de_hoy(client, h_cli)["meals"][0]
    assert comida["kcal"] == 148, comida
    assert comida["foods"][0]["name"] == f"Huevo {suf}", comida["foods"]
    assert comida["foods"][0]["quantity"] == 2
    assert comida["foods"][0]["unit"] == "ud", comida["foods"][0]
