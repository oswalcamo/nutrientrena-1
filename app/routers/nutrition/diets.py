from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from sqlalchemy import or_
from app.core.dependencies import (
    EDITOR_CONTENIDO_GLOBAL,
    require_role_ids, get_org_context, OrgContext,
    verify_client_access, SUPERADMIN, ADMIN, COACH, CLIENT,
    bloqueado_para_ver,
)
from app.core.responses import send_response, send_error
from app.core.macros import escalar, totales_de_dieta
from app.models.nutrition.diet import Diet, DietDetail, DietFood, DietFoodAliment, Pathology, diet_pathologies_table
from app.models.nutrition.aliment import Aliment, AlimentDescription
from app.schemas.nutrition.diet import DietCreate, DietUpdate, DietOut, DietFoodCreate, DietFoodAlimentCreate
from app.pdf.diet_pdf import generate_diet_pdf

router = APIRouter(prefix="/diets", tags=["Nutrition - Diets"])


def _get_or_404(db: Session, diet_id: str):
    return db.query(Diet).filter(Diet.id == diet_id).first()


def _visible_to(obj, org: OrgContext) -> bool:
    """Si quien llama puede ver esta dieta: es de plataforma (organization_id
    NULL), es de su propia organización, o quien llama es superadmin/admin sin
    organización (bypass total, igual que en aliments.py)."""
    if obj.organization_id is None:
        return True
    if org.solo_plataforma:
        return False        # se está mirando el catálogo común, no las cuentas
    if org.org_id is None and org.is_owner:
        return True
    return obj.organization_id == org.org_id


def _bloqueado_para_editar(obj, org: OrgContext, current_user, db: Session) -> Optional[str]:
    """Si hay que impedir ver/editar/eliminar esta dieta, el motivo; si no, None.

    Antes esto no comprobaba nada: cualquier coach podía tocar cualquier dieta
    por id, de cualquier organización. Tres reglas, en este orden:

    1. Quien la creó siempre puede tocar la suya. Esto es lo que evita romper
       el caso más común: un coach sin organización (organization_id queda
       NULL al crearla) editando su propia dieta — sin esta regla primero,
       "solo el dueño de la organización edita lo NULL" le habría bloqueado
       su propio contenido.
    2. Si ya está asignada a un cliente concreto (su `user_id` es hoy una
       cuenta con rol CLIENT), el acceso es por relación coach-cliente, NO
       por organización — cada coach gestiona solo sus propios clientes,
       aunque compartan organización con otros coaches.
    3. Si no, es contenido de biblioteca de OTRO coach: solo puede tocarlo
       alguien de su misma organización, o superadmin/admin.
    """
    # Solo mientras siga siendo suya: subirla al catálogo común cambia de
    # quién es, y un clic del autor se la llevaría por delante a cuentas que
    # ya dependen de ella. La excepción es el coach SIN organización, que
    # crea con organization_id NULL y sin ella se quedaría bloqueado con lo
    # suyo propio.
    if obj.user_id == current_user.id:
        if obj.organization_id is not None or org.org_id is None:
            return None

    if obj.user_id is not None:
        from app.models.user import RoleUser, UserDetail

        es_cliente = db.query(RoleUser).filter(
            RoleUser.user_id == obj.user_id, RoleUser.role_id == CLIENT
        ).first() is not None
        if es_cliente:
            client_detail = db.query(UserDetail).filter(UserDetail.user_id == obj.user_id).first()
            if not client_detail:
                return "No tienes acceso a esta dieta"
            verify_client_access(client_detail.id, current_user, db)  # lanza 403 si no toca
            return None

    if org.solo_plataforma and obj.organization_id is not None:
        return "No tienes acceso a esta dieta"    # actuando solo como plataforma
    if org.org_id is None and org.is_owner:
        return None  # superadmin/admin: bypass total
    if obj.organization_id is not None and obj.organization_id == org.org_id:
        return None  # de tu misma organización
    return "No tienes acceso a esta dieta"


def _get_or_404_with_pathologies(db: Session, diet_id: str):
    return (
        db.query(Diet)
        .options(selectinload(Diet.pathologies))
        .filter(Diet.id == diet_id)
        .first()
    )


def _diet_food_totals(diet: Diet):
    """Suma kcal y macros reales a partir de los alimentos de la dieta.

    La cuenta vive en `app/core/macros.py`: la misma que usa el plan del
    cliente, para que las dos pantallas no digan cosas distintas."""
    return totales_de_dieta(diet)


def _serialize(diet: Diet) -> dict:
    data = DietOut.model_validate(diet).model_dump()
    # Objetivo nutricional de la plantilla, leído ANTES del relleno de abajo:
    # una dieta "libre" acaba con kcal/macros calculados y ya no se distinguiría.
    det0 = diet.detail
    if det0 and (det0.proteins or det0.carbs or det0.fats):
        data["goal_mode"] = "macros"
    elif diet.calories:
        data["goal_mode"] = "kcal"
    else:
        data["goal_mode"] = "libre"
    # Lo que el coach ESCRIBIÓ, tal cual y sin rellenar. El relleno de abajo
    # sirve para mirar la dieta; esto es lo que carga el formulario, y sin
    # separarlo el editor no podía distinguir «el coach escribió 1164» de «los
    # alimentos suman 1164». Metía la suma en la casilla del objetivo y al
    # guardar la almacenaba como si alguien la hubiera tecleado: desde ahí la
    # cifra quedaba congelada y añadir un alimento ya no la movía.
    data["objetivo"] = {
        "calories": diet.calories,
        "proteins": det0.proteins if det0 else None,
        "carbs": det0.carbs if det0 else None,
        "fats": det0.fats if det0 else None,
        "fiber": det0.fiber if det0 else None,
    }
    # Lo que el coach escribió como objetivo manda; lo que no escribió se
    # rellena con lo que suman los alimentos de verdad. Cada cifra por su
    # cuenta: en modo "kcal" hay kcal escritas pero ningún macro, y antes
    # bastaba con tener kcal para que Prot/Carb/Grasa salieran vacíos en la
    # lista, con la dieta entera montada debajo.
    k, p, c, f = _diet_food_totals(diet)
    if k > 0:
        if not data.get("calories"):
            data["calories"] = round(k)
        det = data.get("detail")
        if not isinstance(det, dict):
            det = {}
        if not det.get("proteins"):
            det["proteins"] = round(p, 1)
        if not det.get("carbs"):
            det["carbs"] = round(c, 1)
        if not det.get("fats"):
            det["fats"] = round(f, 1)
        data["detail"] = det
    return data


def _clone_aliment(db: Session, source: Aliment) -> Aliment:
    clone = Aliment(
        group_food_id=source.group_food_id,
        brand=source.brand,
        name=source.name,
        quantity=source.quantity,
        quantity_unit=source.quantity_unit,
        quantity_type_id=source.quantity_type_id,
        proteins=source.proteins,
        carbohydrates=source.carbohydrates,
        fats=source.fats,
        calories=source.calories,
        comments=source.comments,
        parent_id=source.id,
        created_user_id=source.created_user_id,
    )
    # La ficha de micronutrientes (fibra, sodio, vitaminas…) va aparte. Sin
    # copiarla, cada alimento metido en una dieta salía con 0 g de fibra
    # aunque el del catálogo la tuviera.
    if source.description:
        clone.description = AlimentDescription(**_micros_de(source.description))
    db.add(clone)
    db.flush()
    return clone


def _micros_de(desc: AlimentDescription) -> dict:
    """Los valores de una ficha de micros, sin su id ni a quién pertenece."""
    return {c.name: getattr(desc, c.name)
            for c in AlimentDescription.__table__.columns
            if c.name not in ("id", "aliment_id")}


def _limpiar_clones(db: Session, aliment_ids) -> int:
    """Borra los clones de alimento que ya no usa nadie.

    Meter un alimento en una dieta no apunta al del catálogo: hace una COPIA
    suya (con `parent_id` al original) y la dieta apunta a la copia. Eso está
    bien —editar la dieta de un cliente no puede cambiarle las kcal a la
    biblioteca ni a los demás—. Lo que faltaba era recoger: cuando la copia
    dejaba de usarse se quedaba en la tabla para siempre. No sale en la
    biblioteca, no se puede usar, y ahí estaba contando. En la base del cliente
    había miles.

    Solo se borra lo que cumple TODO:

      · es una copia (tiene `parent_id`) — un alimento del catálogo no se toca
        jamás por aquí, aunque nadie lo esté usando;
      · no lo usa ninguna dieta, ninguna receta, y no es padre de otra copia.

    Hay que llamarlo DESPUÉS de que los borrados estén en la sesión: si no, las
    consultas de abajo siguen viendo las filas que se acaban de quitar y no se
    limpia nada.
    """
    from app.models.nutrition.recipe import RecipeDetail
    from app.models.nutrition.aliment import AlimentDescription

    ids = {i for i in (aliment_ids or []) if i}
    if not ids:
        return 0
    db.flush()

    borrados = 0
    for aid in ids:
        al = db.query(Aliment).filter(Aliment.id == aid).first()
        if not al or al.parent_id is None:
            continue
        en_uso = (
            db.query(DietFoodAliment).filter(DietFoodAliment.aliment_id == aid).first()
            or db.query(RecipeDetail).filter(RecipeDetail.aliment_id == aid).first()
            or db.query(Aliment).filter(Aliment.parent_id == aid).first()
        )
        if en_uso:
            continue
        db.query(AlimentDescription).filter(
            AlimentDescription.aliment_id == aid).delete(synchronize_session=False)
        db.delete(al)
        borrados += 1
    if borrados:
        db.flush()
    return borrados


def _clones_de_dieta(db: Session, diet_id: str) -> list:
    """Los alimentos a los que apunta una dieta, para poder recogerlos luego."""
    return [r[0] for r in db.query(DietFoodAliment.aliment_id).filter(
        DietFoodAliment.diet_id == diet_id).all()]


def _clones_de_comida(db: Session, food_id: int) -> list:
    return [r[0] for r in db.query(DietFoodAliment.aliment_id).filter(
        DietFoodAliment.diet_food_id == food_id).all()]


def _save_pathologies(db: Session, diet_id: str, pathology_ids: list):
    db.execute(
        diet_pathologies_table.delete().where(diet_pathologies_table.c.diet_id == diet_id)
    )
    for pid in (pathology_ids or []):
        db.execute(diet_pathologies_table.insert().values(diet_id=diet_id, pathology_id=pid))


def _fila_de(db: Session, dfa_id, diet_id: str):
    """La fila de alimento `dfa_id`, SI es de esta dieta.

    Antes se buscaba solo por identificador, sin mirar de quién era. Guardar
    una dieta con el identificador de una fila ajena —lo que manda «Duplicar»,
    que reenvía el formulario de la dieta de la que se cargó— encontraba la
    fila de la OTRA dieta y le reescribía la cantidad, o la borraba. No es que
    se perdiera la copia: es que se estropeaba el original.
    """
    return db.query(DietFoodAliment).filter(
        DietFoodAliment.id == dfa_id, DietFoodAliment.diet_id == diet_id
    ).first()


def _save_foods(db: Session, diet_id: str, foods_data: Optional[list], current_user_id: int):
    """Guarda las comidas de una dieta.

    El editor borra por omisión: cuando se quita un alimento o una comida,
    simplemente deja de enviarse. Así que lo que no llega se poda, a los dos
    niveles (alimentos dentro de cada comida, y comidas dentro de la dieta).

    `foods_data is None` significa "no toques las comidas" — una edición
    parcial, por ejemplo cambiar solo el título. Sin esa distinción, cualquier
    petición que no mandara `foods` vaciaría la dieta entera.
    """
    if foods_data is None:
        return

    kept_food_ids = set()
    # Los alimentos que van quedando sueltos por el camino. Se recogen al final,
    # cuando ya no queda ninguna referencia en la sesión.
    posibles_huerfanos = []

    for food_data in foods_data:
        if food_data.delete and food_data.id:
            food = db.query(DietFood).filter(
                DietFood.id == food_data.id, DietFood.diet_id == diet_id
            ).first()
            if food:
                posibles_huerfanos += _clones_de_comida(db, food.id)
                db.delete(food)
            continue

        food = None
        if food_data.id:
            food = db.query(DietFood).filter(
                DietFood.id == food_data.id, DietFood.diet_id == diet_id
            ).first()

        # Un identificador que no es de esta dieta describe una comida NUEVA, no
        # una que no exista. Es lo que manda «Duplicar»: el editor abre la dieta
        # original, le quita el identificador a la dieta y guarda, pero las
        # comidas y las filas siguen llevando el de aquélla. Saltárselas creaba
        # la copia vacía —con su título y sus objetivos— diciendo «Dieta creada».
        if food:
            food.name = food_data.name
            # `None` = "no lo toques"; vacío = "bórralo". Sin distinguirlo, una
            # edición parcial que no mandara el subtítulo lo borraría sin que
            # nadie lo hubiera pedido.
            if food_data.subtitle is not None:
                food.subtitle = food_data.subtitle.strip()[:255] or None
            if food_data.time is not None:
                food.time = food_data.time or None
        else:
            food = DietFood(diet_id=diet_id, name=food_data.name,
                            subtitle=(food_data.subtitle or "").strip()[:255] or None,
                            time=food_data.time)
            db.add(food)
            db.flush()

        kept_ids = set()

        for aliment_data in (food_data.detail or []):
            if aliment_data.delete and aliment_data.id:
                dfa = _fila_de(db, aliment_data.id, diet_id)
                if dfa:
                    db.delete(dfa)
                continue

            source_aliment = db.query(Aliment).filter(
                Aliment.id == aliment_data.aliment_id
            ).first()
            if not source_aliment:
                # Puede ser un alimento personal (client_aliments): clonarlo a
                # aliments para que la dieta lo referencie como cualquier otro.
                from app.models.nutrition.client_aliment import ClientAliment
                ca = db.query(ClientAliment).filter(
                    ClientAliment.id == aliment_data.aliment_id
                ).first()
                if not ca:
                    continue
                source_aliment = Aliment(
                    group_food_id=ca.group_food_id,
                    brand=ca.brand,
                    name=ca.name,
                    quantity=ca.quantity,
                    quantity_unit=ca.quantity_unit,
                    proteins=ca.proteins,
                    carbohydrates=ca.carbohydrates,
                    fats=ca.fats,
                    calories=ca.calories,
                    comments=ca.comments,
                    created_user_id=current_user_id,
                )
                db.add(source_aliment)
                db.flush()

            if aliment_data.id:
                dfa = _fila_de(db, aliment_data.id, diet_id)
                if dfa:
                    # If the chosen aliment changed, re-clone the new source and repoint.
                    # dfa.aliment_id points to a clone; its parent_id is the source aliment.
                    current_source = dfa.aliment.parent_id if dfa.aliment else None
                    unchanged = (
                        str(dfa.aliment_id) == str(aliment_data.aliment_id)
                        or str(current_source) == str(aliment_data.aliment_id)
                    )
                    if not unchanged:
                        # La copia anterior se queda sin quien la use.
                        posibles_huerfanos.append(dfa.aliment_id)
                        cloned = _clone_aliment(db, source_aliment)
                        cloned.created_user_id = current_user_id
                        dfa.aliment_id = cloned.id
                    dfa.quantity = aliment_data.quantity_calc
                    dfa.order = aliment_data.order or 0
                    kept_ids.add(dfa.id)
                    continue

            cloned = _clone_aliment(db, source_aliment)
            cloned.created_user_id = current_user_id

            dfa = DietFoodAliment(
                diet_id=diet_id,
                diet_food_id=food.id,
                aliment_id=cloned.id,
                quantity=aliment_data.quantity_calc,
                order=aliment_data.order or 0,
            )
            db.add(dfa)
            db.flush()
            kept_ids.add(dfa.id)

        # Remove aliments deleted in the editor (existing rows no longer sent)
        for orphan in db.query(DietFoodAliment).filter(
            DietFoodAliment.diet_food_id == food.id
        ).all():
            if orphan.id not in kept_ids:
                posibles_huerfanos.append(orphan.aliment_id)
                db.delete(orphan)

        kept_food_ids.add(food.id)

    # Y lo mismo un nivel más arriba: las comidas que ya no llegan.
    # Antes esta poda no existía y la de arriba vive DENTRO del bucle, así que
    # una comida que dejaba de enviarse no se visitaba nunca y sobrevivía con
    # todos sus alimentos. Es justo lo que pasaba al borrar el último alimento
    # de una comida: diets.html descarta del payload las comidas que se quedan
    # sin alimentos, así que el borrado no se guardaba.
    for orphan_food in db.query(DietFood).filter(DietFood.diet_id == diet_id).all():
        if orphan_food.id not in kept_food_ids:
            posibles_huerfanos += _clones_de_comida(db, orphan_food.id)
            db.delete(orphan_food)  # cascade borra sus DietFoodAliment

    # Y se recoge. Va al final a propósito: un alimento puede haberse quitado de
    # una comida y puesto en otra dentro de la misma edición, y borrarlo sobre
    # la marcha se lo llevaría de donde sí se está usando.
    _limpiar_clones(db, posibles_huerfanos)


@router.get("/findAll", summary="Listar dietas", description="Retorna la biblioteca de dietas: las de la organización del coach y las plantillas de plataforma.")
def find_all(
    db: Session = Depends(get_db),
    current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH, EDITOR_CONTENIDO_GLOBAL)),
    org: OrgContext = Depends(get_org_context),
):
    from app.models.user import RoleUser

    # Antes filtraba solo por Diet.user_id == current_user.id: aunque el
    # organization_id ya se guardaba bien al crear, este filtro obligatorio lo
    # dejaba sin efecto, así que ni Oswal (SUPERADMIN) veía sus propias dietas
    # reflejadas a los coaches, ni Sergio y Andrés compartían nada entre sí.
    #
    # Una dieta asignada a un cliente reutiliza esta misma tabla con
    # Diet.user_id apuntando al cliente, no al coach: se excluye comprobando
    # el rol ACTUAL del dueño de la fila, no una convención de datos.
    # selectinload: Diet.pathologies es lazy="noload" y sin esto llegaría vacío.
    client_ids = db.query(RoleUser.user_id).filter(RoleUser.role_id == CLIENT).scalar_subquery()
    q = (
        db.query(Diet)
        .options(selectinload(Diet.pathologies))
        .filter(or_(Diet.user_id.is_(None), ~Diet.user_id.in_(client_ids)))
    )

    if org.solo_plataforma:
        q = q.filter(Diet.organization_id.is_(None))
    elif org.org_id:
        q = q.filter(or_(Diet.organization_id.is_(None), Diet.organization_id == org.org_id))
    elif not org.is_owner:
        q = q.filter(Diet.user_id == current_user.id)
    # org.is_owner sin org_id (superadmin/admin) -> ve la biblioteca entera.

    return send_response([_serialize(i) for i in q.all()], "OK")


@router.get("/client/{client_id}", summary="Dietas del cliente", description="Retorna las dietas de un cliente agrupadas por tipo de alimentación.")
def client_diets(client_id: str, db: Session = Depends(get_db), current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH))):
    verify_client_access(client_id, current_user, db)
    from app.models.user import UserDetail
    from app.models.nutrition.type_food import TypeFood

    client_detail = db.query(UserDetail).filter(UserDetail.id == client_id).first()
    if not client_detail:
        return send_error("Cliente no encontrado")

    diets = db.query(Diet).filter(Diet.user_id == client_detail.user_id).all()

    type_foods = db.query(TypeFood).all()
    grouped = []
    for tf in type_foods:
        matching = [_serialize(d) for d in diets if d.type_id == tf.id]
        if matching:
            grouped.append({"type": {"id": tf.id, "name": tf.name}, "diets": matching})

    untyped = [_serialize(d) for d in diets if d.type_id is None]
    if untyped:
        grouped.append({"type": None, "diets": untyped})

    return send_response(grouped, "OK")


# ── Generación con IA ─────────────────────────────────────────────────────────
class _AIGenerateBody(BaseModel):
    client_id: Optional[str] = None       # UserDetail UUID; opcional
    kcal: float
    proteins: Optional[float] = None
    carbs: Optional[float] = None
    fats: Optional[float] = None
    fiber: Optional[float] = None
    meal_count: int = 4
    notes: Optional[str] = None           # indicaciones libres del coach
    seed: Optional[int] = None            # otra variante: cambia el subconjunto del catálogo
    max_aliments: int = 220


def _client_context(db: Session, client_id: str) -> dict:
    """Lo que necesita saber el modelo para proponer un plan, y nada más.

    Va sin nombre, sin correo y sin identificadores: quien lo recibe no puede
    saber de quién es la ficha. Tampoco viajan los diagnósticos — de una
    patología solo sale la restricción que implica ("evitar gluten"), que es lo
    único que cambia la dieta. El aviso clínico para el coach se calcula aparte,
    aquí en el servidor, y no se le pide a la IA.
    """
    from app.core.diet_builder import exclusions_for
    from app.models.user import UserDetail

    detail = db.query(UserDetail).filter(UserDetail.id == client_id).first()
    if not detail:
        return {}

    patologias = [p.name for p in (detail.pathologies or [])]
    evitar = sorted(exclusions_for(patologias))

    ctx = {
        "Edad": detail.age,
        "Sexo": detail.gender.description if detail.gender else None,
        "Peso (kg)": detail.weight,
        "Altura (cm)": detail.height,
        "Objetivo": detail.objective.description if detail.objective else None,
        "Nivel de actividad": detail.activity.description if detail.activity else None,
        "Alergias": detail.allergies,
        "Intolerancias": detail.intolerances,
        "No le gusta": detail.dislikes,
        "Preferencias alimentarias": detail.food_preferences,
    }
    if evitar:
        ctx["Alimentos a evitar"] = ", ".join(evitar)
    return ctx


def _stable_seed(*partes) -> int:
    """Semilla estable entre reinicios.

    `hash()` de Python lleva sal por proceso, así que con él la misma dieta
    dejaría de ser reproducible en cuanto se reiniciara el servidor.
    """
    import zlib

    return zlib.crc32("|".join(str(p) for p in partes).encode()) & 0x7FFFFFFF


def _catalogo_generador(db: Session, org):
    """Alimentos con los que se construye una dieta.

    Se usa el catálogo marcado como utilizable, no la tabla entera: los 7.348
    del USDA son referencia nutricional con nombres de laboratorio ("Abadejo de
    Alaska, crudo") y no valen para un plan que lee una persona. Si no hay
    ninguno marcado se cae a todo el catálogo, para que una instalación sin el
    catálogo base siga generando dietas.
    """
    base = db.query(Aliment).filter(Aliment.calories.isnot(None))
    if org.solo_plataforma:
        base = base.filter(Aliment.organization_id.is_(None))
    elif org.org_id:
        base = base.filter(or_(Aliment.organization_id.is_(None),
                               Aliment.organization_id == org.org_id))

    marcados = base.filter(Aliment.use_in_generator.is_(True))
    if marcados.limit(1).first() is not None:
        return marcados
    return base


def _pick_catalog(aliments: list, limit: int, seed: Optional[int] = None) -> list:
    """Recorta el catálogo a un subconjunto que siga siendo utilizable.

    Mandar los primeros N alimentos podía dejar al modelo sin proteínas o sin
    nada de desayuno, según cómo estuviera ordenada la tabla. Se reparte el
    cupo entre los cuatro roles (proteína, carbohidrato, grasa, verdura) y,
    dentro de cada uno, entre los momentos del día, cogiendo por turnos hasta
    llenar. Así el recorte no deja fuera una categoría entera.

    Dentro de cada cajón se baraja con la semilla: sin esto salían siempre los
    mismos alimentos por muy grande que fuera el catálogo, que es justo lo que
    hace que todas las dietas se parezcan.
    """
    import random

    from app.core.diet_builder import MOMENTS, classify, moments_for

    if len(aliments) <= limit:
        return aliments

    rnd = random.Random(seed or 0)

    # (rol, momento) -> alimentos
    cajones: dict = {}
    for a in aliments:
        rol = classify(a)
        if not rol:
            continue
        for momento in moments_for(a):
            cajones.setdefault((rol, momento), []).append(a)

    for grupo in cajones.values():
        rnd.shuffle(grupo)

    claves = [(r, m) for r in ("protein", "carb", "fat", "veg") for m in MOMENTS]
    elegidos, vistos = [], set()
    # Ronda a ronda: uno de cada cajón, hasta llenar el cupo.
    for vuelta in range(limit):
        if len(elegidos) >= limit:
            break
        for clave in claves:
            grupo = cajones.get(clave) or []
            if vuelta >= len(grupo):
                continue
            a = grupo[vuelta]
            if a.id in vistos:
                continue
            vistos.add(a.id)
            elegidos.append(a)
            if len(elegidos) >= limit:
                break
    # Si algo quedó suelto (sin rol reconocible), se completa con el resto.
    if len(elegidos) < limit:
        for a in aliments:
            if a.id not in vistos:
                elegidos.append(a)
                vistos.add(a.id)
                if len(elegidos) >= limit:
                    break
    return elegidos


def _macros_for(aliment, grams: float) -> tuple:
    f = (grams or 0) / 100.0
    return (
        (aliment.calories or 0) * f,
        (aliment.proteins or 0) * f,
        (aliment.carbohydrates or 0) * f,
        (aliment.fats or 0) * f,
    )


class _AutoGenerateBody(BaseModel):
    client_id: Optional[str] = None
    kcal: float
    proteins: float = 0
    carbs: float = 0
    fats: float = 0
    meal_count: int = 4
    seed: Optional[int] = None            # cambia la variante sin cambiar los datos
    # Directrices del coach: hacia dónde cargar las calorías y qué evitar.
    distribution: Optional[str] = None    # balanced | big_breakfast | big_lunch | light_dinner
    avoid: Optional[str] = None           # términos libres separados por coma


@router.post("/auto-generate", summary="Generar una dieta automáticamente", description="Construye un plan diario con los alimentos del catálogo ajustado a los objetivos de Nutrición. Sin IA ni servicios externos.")
def auto_generate(
    data: _AutoGenerateBody,
    db: Session = Depends(get_db),
    current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH)),
    org: OrgContext = Depends(get_org_context),
):
    from app.core import diet_builder

    if not data.kcal or data.kcal <= 0:
        return send_error("Hace falta un objetivo de calorías para generar el plan", code=422)

    aliments = _catalogo_generador(db, org).all()
    if not aliments:
        return send_error("No hay alimentos en el catálogo para construir la dieta", code=422)

    restricciones, avisos, patologias = [], [], []
    if data.client_id:
        from app.models.user import UserDetail
        detail = db.query(UserDetail).filter(UserDetail.id == data.client_id).first()
        if detail:
            restricciones = diet_builder.parse_restrictions(
                detail.allergies, detail.intolerances, detail.dislikes
            )
            patologias = [p.name for p in (detail.pathologies or [])]
            # Las patologías excluyen familias enteras de alimentos (celiaquía →
            # trigo, pan, pasta…), no solo lo que aparezca escrito en su nombre.
            restricciones += diet_builder.exclusions_for(patologias)
            avisos = diet_builder.warnings_for(patologias)
    # Lo que el coach quiera evitar solo en esta dieta, sin tocar la ficha.
    if data.avoid:
        restricciones += diet_builder.parse_restrictions(data.avoid)

    try:
        plan = diet_builder.build_diet(
            aliments=aliments, kcal=data.kcal, proteins=data.proteins,
            carbs=data.carbs, fats=data.fats, meal_count=data.meal_count,
            restrictions=restricciones,
            # La semilla sale del cliente, no de un 0 fijo: si no, la primera
            # dieta de todos los clientes salía con los mismos alimentos.
            # Sigue siendo reproducible — mismo cliente y misma variante, mismo
            # plan — pero deja de ser la misma para todo el mundo.
            seed=_stable_seed(data.client_id or "", data.seed or 0),
            distribution=data.distribution,
        )
    except ValueError as e:
        return send_error(str(e), code=422)

    if not plan["meals"]:
        return send_error("No se pudo construir el plan con los alimentos disponibles", code=422)

    total = plan["totals"]["calories"]
    desvio = round((total - data.kcal) / data.kcal * 100) if data.kcal else 0

    notas = "Plan generado automáticamente a partir de tus objetivos. Revísalo y ajústalo antes de asignarlo."
    if avisos:
        # Los avisos van también en las notas para que viajen con la dieta y
        # salgan en el PDF, no solo en la pantalla de propuesta.
        notas += "\n\nAvisos por patologías:\n" + "\n".join(
            f"· {a['pathology']}: {a['text']}" for a in avisos
        )

    return send_response(
        {
            "title": f"Plan {round(data.kcal)} kcal",
            "notes": notas,
            "warnings": avisos,
            "pathologies": patologias,
            "foods": plan["meals"],
            "totals": plan["totals"],
            "target": {"calories": round(data.kcal), "deviation_pct": desvio},
        },
        "Dieta generada",
    )


@router.post("/ai-generate", summary="Generar una dieta con IA", description="Propone un plan diario con los alimentos del catálogo, ajustado a los objetivos calculados en Nutrición y a los datos del cliente.")
def ai_generate(
    data: _AIGenerateBody,
    db: Session = Depends(get_db),
    current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH)),
    org: OrgContext = Depends(get_org_context),
):
    from app.core import ai_diet

    if not ai_diet.ai_enabled():
        return send_error(
            f"La generación con IA está desactivada. Actívala con AI_DIET_ENABLED=true y una "
            f"{ai_diet.key_var_name()} en las variables de entorno del servidor.",
            code=503,
        )
    if not data.kcal or data.kcal <= 0:
        return send_error("Hace falta un objetivo de calorías para generar el plan", code=422)

    # Catálogo del coach: solo alimentos con calorías, que son los que sirven.
    aliments = _catalogo_generador(db, org).limit(1000).all()

    # Cuántos caben en el prompt. El tier gratuito de Groq son 12.000 tokens por
    # minuto y cada alimento ronda los 20, así que el catálogo entero no entra:
    # se recorta a un subconjunto equilibrado en vez de fallar con un 413.
    from app.config import settings

    tope = settings.GROQ_DIET_MAX_ALIMENTS if ai_diet._proveedor() == "groq" else data.max_aliments
    aliments = _pick_catalog(
        aliments, max(20, min(tope, 400)),
        seed=_stable_seed(data.client_id or "", data.seed or 0),
    )
    if not aliments:
        return send_error("No hay alimentos en el catálogo para construir la dieta", code=422)

    client_ctx = _client_context(db, data.client_id) if data.client_id else {}
    target = {
        "kcal": data.kcal, "proteins": data.proteins, "carbs": data.carbs,
        "fats": data.fats, "fiber": data.fiber, "meal_count": data.meal_count,
    }

    try:
        plan = ai_diet.generate_diet(
            client=client_ctx, target=target, aliments=aliments, extra=data.notes
        )
    except Exception as e:
        return send_error(f"No se pudo generar la dieta: {e}", code=502)

    # Los totales NO se toman del modelo: se recalculan con la base de datos,
    # que es la misma fuente que usa el resto de la aplicación.
    meals, totals = [], [0.0, 0.0, 0.0, 0.0]
    for m in plan.get("meals", []):
        detail = []
        for f in m.get("foods", []):
            # El modelo responde por número de catálogo; fuera de rango se
            # descarta en vez de romper el plan.
            n = f.get("n")
            if not isinstance(n, int) or not (0 <= n < len(aliments)):
                continue
            al = aliments[n]
            grams = round(float(f.get("grams") or 0))
            if grams <= 0:
                continue
            k, p, c, g = _macros_for(al, grams)
            totals = [totals[0] + k, totals[1] + p, totals[2] + c, totals[3] + g]
            # El modelo puede darle nombre de plato ("Merluza al horno"). Es solo
            # la etiqueta que lee el cliente: el alimento, sus macros y el id
            # siguen siendo los del catálogo, así que la dieta se puede editar y
            # los totales se recalculan igual.
            etiqueta = (f.get("label") or "").strip()
            nombre = etiqueta if 0 < len(etiqueta) <= 80 else al.name

            detail.append({
                "aliment_id": str(al.id), "name": nombre, "quantity_calc": grams,
                "calories": round(k), "proteins": round(p, 1),
                "carbohydrates": round(c, 1), "fats": round(g, 1),
            })
        if detail:
            meals.append({"name": m.get("name") or "Comida", "time": m.get("time"), "detail": detail})

    if not meals:
        return send_error("La IA no propuso alimentos válidos del catálogo. Inténtalo de nuevo.", code=502)

    desvio = round((totals[0] - data.kcal) / data.kcal * 100) if data.kcal else 0
    return send_response(
        {
            "title": plan.get("title") or "Plan generado con IA",
            "notes": plan.get("notes"),
            "foods": meals,
            "totals": {
                "calories": round(totals[0]), "proteins": round(totals[1], 1),
                "carbs": round(totals[2], 1), "fats": round(totals[3], 1),
            },
            "target": {"calories": round(data.kcal), "deviation_pct": desvio},
        },
        "Dieta generada",
    )


@router.get("/{id}/pdf", summary="Exportar dieta a PDF", description="Genera y descarga la dieta en formato PDF.")
def pdf(
    id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH, EDITOR_CONTENIDO_GLOBAL)),
    org: OrgContext = Depends(get_org_context),
):
    diet = _get_or_404(db, id)
    if not diet:
        return send_error("Dieta no encontrada")
    # Aquí no había ninguna comprobación: con acertar el id se descargaba la
    # dieta del cliente de otra cuenta.
    motivo = bloqueado_para_ver(diet, org, current_user, db, "esta dieta")
    if motivo:
        return send_error(motivo, code=403)
    try:
        pdf_bytes = generate_diet_pdf(diet)
    except Exception as e:
        return send_error(f"Error generando PDF: {str(e)}", code=500)
    safe_name = (diet.title or "dieta").replace(" ", "_").lower()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
    )


@router.post("/{client_id}/assigned", summary="Asignar dieta a cliente", description="Crea y asigna una dieta directamente a un cliente.")
def assigned(
    client_id: str,
    data: DietCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH)),
):
    from app.models.user import UserDetail
    client_detail = db.query(UserDetail).filter(UserDetail.id == client_id).first()
    if not client_detail:
        return send_error("Cliente no encontrado")

    diet = Diet(
        title=data.title,
        calories=data.calories,
        quantity=data.quantity,
        type_id=data.type_id,
        notes=data.notes,
        user_id=client_detail.user_id,
        created_user_id=current_user.id,
    )
    db.add(diet)
    db.flush()

    _save_detail(db, diet.id, data)
    _save_foods(db, diet.id, data.foods, current_user.id)
    _save_pathologies(db, diet.id, data.pathology_ids or [])
    db.commit()
    db.refresh(diet)
    return send_response(_serialize(diet), "Dieta asignada")


@router.get("/{id}/edit", summary="Ver dieta", description="Retorna el detalle completo de una dieta con alimentos y macros.")
def edit(
    id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH, EDITOR_CONTENIDO_GLOBAL)),
    org: OrgContext = Depends(get_org_context),
):
    diet = _get_or_404_with_pathologies(db, id)
    if not diet:
        return send_error("Dieta no encontrada")
    # Ver, no editar: el catálogo de plataforma sale en la Librería de todos y
    # con la comprobación de editar no se podía ni abrir.
    motivo = bloqueado_para_ver(diet, org, current_user, db, "esta dieta")
    if motivo:
        return send_error(motivo, code=403)
    return send_response(_serialize(diet), "OK")


def _save_detail(db: Session, diet_id: str, data: DietCreate):
    detail = db.query(DietDetail).filter(DietDetail.diet_id == diet_id).first()
    detail_fields = {
        "height": data.height,
        "weight": data.weight,
        "body_fat": data.body_fat,
        "level_activity_id": data.level_activity_id,
        "objective_id": data.objective_id,
        "proteins": data.proteins,
        "carbs": data.carbs,
        "fats": data.fats,
        "fiber": data.fiber,
        "deficit": data.deficit,
        "surplus": data.surplus,
    }
    if detail:
        for f, v in detail_fields.items():
            setattr(detail, f, v)
    else:
        db.add(DietDetail(diet_id=diet_id, **detail_fields))


@router.post("", summary="Crear dieta", description="Crea una nueva dieta con sus comidas, alimentos y distribución de macros.")
def create(
    data: DietCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH, EDITOR_CONTENIDO_GLOBAL)),
    org: OrgContext = Depends(get_org_context),
):
    diet = Diet(
        title=data.title,
        calories=data.calories,
        quantity=data.quantity,
        type_id=data.type_id,
        notes=data.notes,
        user_id=current_user.id,
        created_user_id=current_user.id,
        organization_id=org.org_id,
    )
    db.add(diet)
    db.flush()

    _save_detail(db, diet.id, data)
    _save_foods(db, diet.id, data.foods, current_user.id)
    _save_pathologies(db, diet.id, data.pathology_ids or [])
    db.commit()
    db.refresh(diet)
    return send_response(_serialize(diet), "Dieta creada")


@router.put("/{id}/update", summary="Actualizar dieta", description="Modifica una dieta existente, incluyendo sus comidas y alimentos.")
def updated(
    id: str,
    data: DietUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH, EDITOR_CONTENIDO_GLOBAL)),
    org: OrgContext = Depends(get_org_context),
):
    diet = _get_or_404(db, id)
    if not diet:
        return send_error("Dieta no encontrada")
    motivo = _bloqueado_para_editar(diet, org, current_user, db)
    if motivo:
        return send_error(motivo, code=403)

    if data.title is not None:
        diet.title = data.title
    if data.calories is not None:
        diet.calories = data.calories
    if data.quantity is not None:
        diet.quantity = data.quantity
    if data.type_id is not None:
        diet.type_id = data.type_id
    if data.notes is not None:
        diet.notes = data.notes
    diet.updated_user_id = current_user.id

    _save_detail(db, diet.id, data)
    _save_foods(db, diet.id, data.foods, current_user.id)
    _save_pathologies(db, diet.id, data.pathology_ids or [])
    db.commit()
    db.refresh(diet)
    return send_response(_serialize(diet), "Dieta actualizada")


@router.delete("/{id}", summary="Eliminar dieta", description="Elimina una dieta y todas sus comidas y alimentos asociados.")
def delete(
    id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH, EDITOR_CONTENIDO_GLOBAL)),
    org: OrgContext = Depends(get_org_context),
):
    diet = _get_or_404(db, id)
    if not diet:
        return send_error("Dieta no encontrada")
    motivo = _bloqueado_para_editar(diet, org, current_user, db)
    if motivo:
        return send_error(motivo, code=403)
    # Detach delivery records so the FK doesn't block the delete (history is kept)
    from app.models.plan import PlanDelivery
    db.query(PlanDelivery).filter(PlanDelivery.diet_id == id).update({"diet_id": None})
    # Las copias de alimento que solo existían para esta dieta se van con ella.
    huerfanos = _clones_de_dieta(db, id)
    db.delete(diet)
    _limpiar_clones(db, huerfanos)
    db.commit()
    return send_response(None, "Dieta eliminada")


class _AssignBody(DietCreate):
    client_id: str
    title: str = ""


def copy_diet_to_user(db: Session, source: Diet, target_user_id: int, created_user_id: int) -> Diet:
    """Copia una dieta (detalle + comidas) al usuario destino. No hace commit."""
    new_diet = Diet(
        title=source.title,
        calories=source.calories,
        quantity=source.quantity,
        type_id=source.type_id,
        user_id=target_user_id,
        created_user_id=created_user_id,
    )
    db.add(new_diet)
    db.flush()

    if source.detail:
        d = source.detail
        db.add(DietDetail(
            diet_id=new_diet.id,
            proteins=d.proteins, carbs=d.carbs, fats=d.fats, fiber=d.fiber,
            deficit=d.deficit, surplus=d.surplus,
            height=d.height, weight=d.weight, body_fat=d.body_fat,
            level_activity_id=d.level_activity_id, objective_id=d.objective_id,
        ))

    foods_data = [
        DietFoodCreate(
            name=food.name,
            # Sin esto el subtítulo se pierde justo al asignar la dieta: el
            # coach lo ve en su biblioteca y su cliente no.
            subtitle=food.subtitle,
            time=food.time,
            detail=[
                DietFoodAlimentCreate(
                    aliment_id=dfa.aliment_id,
                    quantity_calc=dfa.quantity,
                    order=dfa.order,
                )
                for dfa in food.detail
            ],
        )
        for food in source.foods
    ]
    _save_foods(db, new_diet.id, foods_data, created_user_id)
    return new_diet


@router.post("/{id}/assign", summary="Asignar dieta existente a cliente", description="Copia una dieta del catálogo del coach al cliente especificado.")
def assign_to_client(
    id: str,
    body: _AssignBody,
    db: Session = Depends(get_db),
    current_user=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH)),
    org: OrgContext = Depends(get_org_context),
):
    from app.models.user import UserDetail
    source = _get_or_404(db, id)
    if not source:
        return send_error("Dieta no encontrada")
    # Sin esto, un coach podía asignarle a su cliente la dieta privada de otra
    # organización con solo acertar el id.
    if not _visible_to(source, org):
        return send_error("No tienes acceso a esta dieta", code=403)
    client_detail = db.query(UserDetail).filter(UserDetail.id == body.client_id).first()
    if not client_detail:
        return send_error("Cliente no encontrado")

    new_diet = copy_diet_to_user(db, source, client_detail.user_id, current_user.id)
    # Con dos o más dietas hay que decir qué día come cada una: si no, todas
    # valen para los siete días y el cliente sólo ve una.
    from app.routers.weekly_menus import repartir_en_ciclo
    repartida = repartir_en_ciclo(db, client_detail, current_user.id)
    db.commit()
    db.refresh(new_diet)
    return send_response(
        _serialize(new_diet),
        # Se dice, porque el coach acaba de cambiarle la semana al cliente.
        "Dieta asignada y repartida por días" if repartida else "Dieta asignada al cliente",
    )
