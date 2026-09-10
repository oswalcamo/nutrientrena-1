"""Lo que la pantalla de nutrición del cliente necesitaba y no existía.

Dos cosas del prototipo no tenían nada detrás:

  1. "Marcar día como completado". No había dónde guardarlo, así que la barra
     de "consumido hoy" decía siempre 0 / 2100 y el botón no podía hacer nada.
  2. La pestaña "Recetas". El catálogo existe desde hace tiempo, pero TODOS sus
     endpoints exigían admin, coach o editor: el cliente no podía leer ni una,
     aunque el catálogo se hizo para él.

Lo tercero del prototipo —"Ver recetas para cambiar una comida"— es navegación
entre las dos pestañas y se comprueba en
`tests/frontend/nutricion_pestanas.test.js`.
"""
import uuid
from datetime import date, timedelta

from app.database import SessionLocal
from app.models.nutrition.diet import Diet
from app.models.nutrition.recipe import Recipe
from app.models.user import UserDetail, UserParent

from tests.test_org_scope import _crear_coach, _crear_organizacion, _crear_usuario


def _monta(client, admin_headers, suf):
    """Un centro con su coach y un cliente suyo."""
    _u, det_coach, h_coach = _crear_coach(
        client, admin_headers, f"coach.nut.{suf}@nutrientrena-qa.com")
    org_id = _crear_organizacion(det_coach, f"Centro Nutri {suf}")
    _uid, det_cli, h_cli = _crear_usuario(
        client, admin_headers, f"cli.nut.{suf}@nutrientrena-qa.com", role_id=6)
    db = SessionLocal()
    try:
        db.add(UserParent(user_detail_id=det_cli, parent_user_detail_id=det_coach))
        # Con una dieta asignada, que es lo que hace que la semana traiga sus
        # siete días. Sin plan no hay días, y entonces no hay nada que marcar.
        fila = db.query(UserDetail).filter(UserDetail.id == det_cli).first()
        db.add(Diet(title=f"Plan {suf}", calories=2100, user_id=fila.user_id))
        db.commit()
    finally:
        db.close()
    return org_id, det_coach, h_coach, det_cli, h_cli


def _receta(nombre, organization_id=None, **campos):
    db = SessionLocal()
    try:
        r = Recipe(name=nombre, organization_id=organization_id, state=1, **campos)
        db.add(r)
        db.commit()
        return r.id
    finally:
        db.close()


def _marcar(client, h_cli, dia, completado=True):
    return client.post(f"/api/client/nutrition/day/{dia}/completado",
                       headers=h_cli, json={"completado": completado})


def _dias(client, h_cli):
    r = client.get("/api/client/nutrition", headers=h_cli)
    assert r.status_code == 200, r.text
    return {d["date"]: d for d in (r.json()["data"].get("days") or [])}


def _recetas(client, h_cli, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/client/recipes{'?' + q if q else ''}", headers=h_cli)
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ── Marcar el día como completado ──────────────────────────────────────────

def test_el_cliente_marca_su_dia_y_queda_guardado(client, seed, admin_headers):
    suf = uuid.uuid4().hex[:8]
    _org, _dc, _hc, _det, h_cli = _monta(client, admin_headers, suf)
    hoy = date.today().isoformat()

    assert _marcar(client, h_cli, hoy).status_code == 200
    assert _dias(client, h_cli)[hoy]["completed"] is True


def test_se_puede_desmarcar(client, seed, admin_headers):
    """Un botón que solo va en un sentido convierte un toque sin querer en un
    dato falso que ya no hay forma de corregir."""
    suf = uuid.uuid4().hex[:8]
    _org, _dc, _hc, _det, h_cli = _monta(client, admin_headers, suf)
    hoy = date.today().isoformat()

    _marcar(client, h_cli, hoy)
    assert _marcar(client, h_cli, hoy, completado=False).status_code == 200
    assert _dias(client, h_cli)[hoy]["completed"] is False


def test_marcarlo_dos_veces_no_lo_duplica(client, seed, admin_headers):
    """Dos toques seguidos, o dos pestañas abiertas."""
    from app.models.nutrition_day import ClientNutritionDay

    suf = uuid.uuid4().hex[:8]
    _org, _dc, det_cli, _det, h_cli = _monta(client, admin_headers, suf)
    hoy = date.today().isoformat()

    _marcar(client, h_cli, hoy)
    _marcar(client, h_cli, hoy)

    db = SessionLocal()
    try:
        n = db.query(ClientNutritionDay).filter(
            ClientNutritionDay.day == date.today()).count()
    finally:
        db.close()
    assert n >= 1
    assert _dias(client, h_cli)[hoy]["completed"] is True


def test_un_dia_sin_marcar_sale_sin_marcar(client, seed, admin_headers):
    suf = uuid.uuid4().hex[:8]
    _org, _dc, _hc, _det, h_cli = _monta(client, admin_headers, suf)
    dias = _dias(client, h_cli)
    assert dias, "la semana tiene que traer sus siete días"
    assert all(d["completed"] is False for d in dias.values()), dias


def test_no_se_puede_marcar_un_dia_que_no_ha_llegado(client, seed, admin_headers):
    suf = uuid.uuid4().hex[:8]
    _org, _dc, _hc, _det, h_cli = _monta(client, admin_headers, suf)
    manana = (date.today() + timedelta(days=1)).isoformat()

    assert _marcar(client, h_cli, manana).status_code == 422


def test_una_fecha_inventada_se_rechaza(client, seed, admin_headers):
    suf = uuid.uuid4().hex[:8]
    _org, _dc, _hc, _det, h_cli = _monta(client, admin_headers, suf)
    assert _marcar(client, h_cli, "el-martes").status_code == 422


def test_lo_que_marca_un_cliente_no_se_le_marca_a_otro(client, seed, admin_headers):
    suf = uuid.uuid4().hex[:8]
    _o1, _d1, _h1, _det1, h_c1 = _monta(client, admin_headers, suf + "a")
    _o2, _d2, _h2, _det2, h_c2 = _monta(client, admin_headers, suf + "b")
    hoy = date.today().isoformat()

    _marcar(client, h_c1, hoy)

    assert _dias(client, h_c1)[hoy]["completed"] is True
    assert _dias(client, h_c2)[hoy]["completed"] is False


def test_el_coach_no_marca_el_dia_por_su_cliente(client, seed, admin_headers):
    """El único que puede decir que ha comido lo del martes es quien comió."""
    suf = uuid.uuid4().hex[:8]
    _org, _dc, h_coach, _det, _h_cli = _monta(client, admin_headers, suf)
    r = _marcar(client, h_coach, date.today().isoformat())
    assert r.status_code == 403, r.text


# ── La pestaña de recetas ──────────────────────────────────────────────────

def test_el_cliente_ve_las_recetas_de_la_plataforma(client, seed, admin_headers):
    """Antes no podía ver ninguna: todos los endpoints le daban 403."""
    suf = uuid.uuid4().hex[:8]
    _org, _dc, _hc, _det, h_cli = _monta(client, admin_headers, suf)
    _receta(f"Arroz con pollo {suf}", calories=540, prep_time=30, meal_type="Comida")

    nombres = [r["name"] for r in _recetas(client, h_cli)["items"]]
    assert f"Arroz con pollo {suf}" in nombres, nombres


def test_y_las_de_su_centro(client, seed, admin_headers):
    suf = uuid.uuid4().hex[:8]
    org_id, _dc, _hc, _det, h_cli = _monta(client, admin_headers, suf)
    _receta(f"Receta del centro {suf}", organization_id=org_id, calories=400)

    nombres = [r["name"] for r in _recetas(client, h_cli)["items"]]
    assert f"Receta del centro {suf}" in nombres, nombres


def test_pero_no_las_de_otro_centro(client, seed, admin_headers):
    """El mismo motivo por el que no ve a los clientes de otro."""
    suf = uuid.uuid4().hex[:8]
    _orgA, _dcA, _hcA, _detA, h_cliA = _monta(client, admin_headers, suf + "a")
    orgB, _dcB, _hcB, _detB, _h_cliB = _monta(client, admin_headers, suf + "b")
    _receta(f"Solo de B {suf}", organization_id=orgB, calories=300)

    nombres = [r["name"] for r in _recetas(client, h_cliA)["items"]]
    assert f"Solo de B {suf}" not in nombres, nombres


def test_un_cliente_sin_centro_solo_ve_el_catalogo_de_la_plataforma(client, seed, admin_headers):
    """Un cliente recién dado de alta puede no tener coach todavía. Sin este
    caso, la consulta se quedaba sin ningún filtro de organización y le
    enseñaba el material de todos los centros."""
    suf = uuid.uuid4().hex[:8]
    org_id, _dc, _hc, _det, _h_cli = _monta(client, admin_headers, suf)
    _receta(f"Del centro {suf}", organization_id=org_id, calories=300)
    _receta(f"De la plataforma {suf}", calories=300)

    # Otro cliente, sin coach y por tanto sin centro.
    _uid, _det2, h_suelto = _crear_usuario(
        client, admin_headers, f"cli.suelto.{suf}@nutrientrena-qa.com", role_id=6)

    nombres = [r["name"] for r in _recetas(client, h_suelto)["items"]]
    assert f"De la plataforma {suf}" in nombres, nombres
    assert f"Del centro {suf}" not in nombres, nombres


def test_la_tarjeta_trae_lo_que_pinta(client, seed, admin_headers):
    """Foto, tiempo y kcal: es lo que enseña la tarjeta del prototipo."""
    suf = uuid.uuid4().hex[:8]
    _org, _dc, _hc, _det, h_cli = _monta(client, admin_headers, suf)
    _receta(f"Salmon {suf}", calories=480.4, prep_time=25, meal_type="Cena",
            image="https://cdn.example/salmon.png")

    r = next(x for x in _recetas(client, h_cli)["items"] if x["name"] == f"Salmon {suf}")
    assert r["kcal"] == 480 and r["prep_time"] == 25, r
    assert r["image"] == "https://cdn.example/salmon.png", r
    assert r["meal_type"] == "Cena", r


def test_se_busca_por_nombre(client, seed, admin_headers):
    suf = uuid.uuid4().hex[:8]
    _org, _dc, _hc, _det, h_cli = _monta(client, admin_headers, suf)
    _receta(f"Tortilla de claras {suf}", calories=220)
    _receta(f"Crema de calabaza {suf}", calories=220)

    nombres = [r["name"] for r in _recetas(client, h_cli, search="Tortilla")["items"]]
    assert any("Tortilla" in n for n in nombres), nombres
    assert not any("calabaza" in n for n in nombres), nombres


def test_se_filtra_por_tipo_de_comida(client, seed, admin_headers):
    """Es lo que hace el botón "cambiar una comida": llega a esta pestaña ya
    filtrada por la comida que se quiere cambiar."""
    suf = uuid.uuid4().hex[:8]
    _org, _dc, _hc, _det, h_cli = _monta(client, admin_headers, suf)
    _receta(f"Cena rica {suf}", calories=400, meal_type="Cena")
    _receta(f"Desayuno rico {suf}", calories=300, meal_type="Desayuno")

    tipos = {r["meal_type"] for r in _recetas(client, h_cli, meal_type="Cena")["items"]}
    assert tipos <= {"Cena"}, tipos
    nombres = [r["name"] for r in _recetas(client, h_cli, meal_type="Cena")["items"]]
    assert f"Cena rica {suf}" in nombres, nombres


def test_las_pastillas_son_los_tipos_que_de_verdad_hay(client, seed, admin_headers):
    """Una lista fija enseñaría categorías vacías que no llevan a nada."""
    suf = uuid.uuid4().hex[:8]
    _org, _dc, _hc, _det, h_cli = _monta(client, admin_headers, suf)
    _receta(f"Algo {suf}", calories=200, meal_type="Post-entreno")

    assert "Post-entreno" in _recetas(client, h_cli)["meal_types"]


def test_una_receta_desactivada_no_se_le_enseña(client, seed, admin_headers):
    suf = uuid.uuid4().hex[:8]
    _org, _dc, _hc, _det, h_cli = _monta(client, admin_headers, suf)
    rid = _receta(f"Retirada {suf}", calories=100)
    db = SessionLocal()
    try:
        db.query(Recipe).filter(Recipe.id == rid).update({"state": 0})
        db.commit()
    finally:
        db.close()

    nombres = [r["name"] for r in _recetas(client, h_cli)["items"]]
    assert f"Retirada {suf}" not in nombres, nombres


def test_el_catalogo_del_cliente_es_de_solo_lectura(client, seed, admin_headers):
    """Puede mirarlo; crear y borrar siguen siendo del coach."""
    suf = uuid.uuid4().hex[:8]
    _org, _dc, _hc, _det, h_cli = _monta(client, admin_headers, suf)

    r = client.post("/api/recipes", headers=h_cli,
                    json={"name": f"Mia {suf}", "details": []})
    assert r.status_code == 403, r.text
