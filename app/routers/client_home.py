"""Zona del cliente — endpoint agregado para la pantalla de Inicio.

Devuelve, en una sola llamada, lo que necesita el Inicio del cliente:
perfil, coach, adherencia de la semana, sesión/rutina, estado del
check-in y contador de notificaciones.

Se calcula siempre para el usuario autenticado (ownership implícito: el
cliente solo obtiene lo suyo).
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.dependencies import require_role_ids, SUPERADMIN, ADMIN, COACH, CLIENT
from app.core.responses import send_response, send_error
from app.core.macros import escalar, totales_de_dieta
from app.models.user import User, UserDetail, UserParent
from app.models.routine import Routine
from app.models.session_log import WorkoutSession
from app.models.checkin import WeeklyCheckin

router = APIRouter(prefix="/client", tags=["Client"])

_WEEKDAY_ES = ["L", "M", "X", "J", "V", "S", "D"]


def _client_detail(db: Session, user: User):
    return db.query(UserDetail).filter(UserDetail.user_id == user.id).first()


def _coach_of(db: Session, client_detail_id: str):
    """Coach (UserDetail) del cliente, vía user_parents. None si no tiene."""
    parent = db.query(UserParent).filter(
        UserParent.user_detail_id == client_detail_id
    ).first()
    if not parent:
        return None
    return db.query(UserDetail).filter(
        UserDetail.id == parent.parent_user_detail_id
    ).first()


_MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
_WEEKDAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _routine_day_muscles(day):
    """Grupos musculares únicos de un día de rutina (por orden de aparición)."""
    seen, out = set(), []
    for blk in (day.blocks or []):
        for ex in (blk.exercises or []):
            mg = ex.training.muscle_group.name if (ex.training and ex.training.muscle_group) else None
            if mg and mg not in seen:
                seen.add(mg)
                out.append(mg)
    return out


@router.get("/home", summary="Inicio del cliente", description="Datos agregados de la pantalla de inicio del cliente.")
def client_home(
    week_offset: int = Query(0),
    dia: Optional[str] = Query(
        None, description="Día que se está mirando, AAAA-MM-DD. Por defecto, hoy."),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role_ids(SUPERADMIN, ADMIN, COACH, CLIENT)),
):
    today = date.today()
    today_idx = today.weekday()  # 0 = lunes
    monday = today - timedelta(days=today_idx)
    week_start = monday + timedelta(days=week_offset * 7)
    week_end = week_start + timedelta(days=6)

    # Qué día se está mirando. La pantalla enseña una tira de siete días, y
    # hasta ahora eran adorno: se podía cambiar de semana pero no de día, y el
    # entrenamiento y el menú de abajo eran SIEMPRE los de hoy. Mirar el
    # miércoles y ver la comida del lunes es peor que no poder mirarlo.
    visto = today
    if dia:
        try:
            visto = date.fromisoformat(dia)
        except ValueError:
            visto = today          # una fecha ilegible no rompe la pantalla
    visto_idx = visto.weekday()
    lunes_visto = visto - timedelta(days=visto_idx)

    detail = _client_detail(db, current_user)

    # ── Perfil ──
    full_name = current_user.name if hasattr(current_user, "name") else None
    if detail:
        full_name = (f"{detail.name or ''} {detail.last_name or ''}").strip() or full_name
    full_name = full_name or getattr(current_user, "email", None) or "Cliente"
    parts = full_name.strip().split()
    initials = ((parts[0][:1] if parts else "C") + (parts[1][:1] if len(parts) > 1 else "")).upper()
    profile = {
        "name": full_name,
        # La foto vive en UserDetail, no en User.
        "photo": (detail.photo if detail else None),
        "initials": initials or "C",
    }

    # ── Coach ──
    coach = None
    coach_detail = _coach_of(db, detail.id) if detail else None
    if coach_detail:
        cname = (f"{coach_detail.name or ''} {coach_detail.last_name or ''}").strip() or "Coach"
        coach = {"name": cname, "first_name": (coach_detail.name or cname).split()[0] if cname else "Coach",
                 "initials": (cname.strip()[:1] or "C").upper()}

    # ── Semana visible (sesiones registradas por día) + racha ──
    all_sessions = []
    if detail:
        all_sessions = db.query(WorkoutSession).filter(
            WorkoutSession.client_user_detail_id == detail.id
        ).all()
    session_dates = {s.session_date for s in all_sessions}
    week = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        week.append({
            "date": d.isoformat(),
            "label": _WEEKDAY_ES[i],
            "day": d.day,
            "done": d in session_dates,
            "is_today": d == today,
            "is_future": d > today,
            # Cuál se está mirando. Puede no ser hoy, y puede no estar en esta
            # semana si se ha navegado: entonces no se marca ninguno.
            "is_selected": d == visto,
        })
    week_range = f"{week_start.day}–{week_end.day} {_MONTHS_ES[week_end.month - 1].capitalize()}"

    # Racha: días consecutivos con entreno terminando en hoy (o ayer si hoy aún no)
    streak = 0
    cursor = today if today in session_dates else today - timedelta(days=1)
    while cursor in session_dates:
        streak += 1
        cursor -= timedelta(days=1)

    # ── Rutina de HOY (día de la rutina según el día de la semana) ──
    routine = None
    r = db.query(Routine).filter(Routine.user_id == current_user.id).order_by(Routine.id.desc()).first()
    if r:
        days = r.days_list or []
        rd = days[visto_idx] if visto_idx < len(days) else None
        if rd:
            muscles = _routine_day_muscles(rd)
            routine = {
                "id": r.id,
                "name": rd.day_name or f"Día {visto_idx + 1}",
                "muscles": muscles,
                "focus": " · ".join(muscles) if muscles else (r.objective or r.training or None),
                "duration_min": r.time,
                "is_rest": False,
            }
        else:
            routine = {"id": r.id, "name": None, "muscles": [], "focus": None, "duration_min": None, "is_rest": True}

    # ── El plan de entrenamiento, no el día ──
    # La tarjeta de arriba dice qué toca HOY; en un día de descanso eso deja la
    # pantalla sin ninguna referencia a lo que el cliente está siguiendo. Esto
    # es el plan entero: cómo se llama, a qué apunta y cuántos días tiene.
    plan = None
    if r:
        # `days` lo escribe el coach al crear la rutina y puede estar vacío;
        # entonces se cuentan los días que de verdad tiene montados, que es el
        # mismo número visto desde el otro lado.
        plan = {
            "id": r.id,
            "name": r.name or None,
            "objective": r.objective or r.training or None,
            "days_per_week": r.days or (len(r.days_list or []) or None),
        }

    # ── Menú/dieta del día que se está mirando ──
    menu = None
    if detail:
        menu = _today_menu_summary(db, detail, current_user, visto_idx)

    # ── Check-in solicitado por el coach (pendiente si no hay uno esta semana) ──
    this_monday = lunes_visto
    this_sunday = lunes_visto + timedelta(days=6)
    checkin_done = False
    if detail:
        checkin_done = db.query(WeeklyCheckin).filter(
            WeeklyCheckin.client_user_detail_id == detail.id,
            WeeklyCheckin.checkin_date >= this_monday,
            WeeklyCheckin.checkin_date <= this_sunday,
        ).first() is not None
    checkin = {
        "status": "done" if checkin_done else "pending",
        "coach_name": coach["name"] if coach else None,
        "coach_initials": coach["initials"] if coach else None,
        "requested_fields": ["peso", "fotos", "medidas"],
    }

    return send_response({
        "profile": profile,
        "coach": coach,
        "today": {"weekday": _WEEKDAY_NAMES[today_idx], "day": today.day, "month": _MONTHS_ES[today.month - 1]},
        "dia_visto": {
            "fecha": visto.isoformat(),
            "weekday": _WEEKDAY_NAMES[visto_idx],
            "day": visto.day,
            "month": _MONTHS_ES[visto.month - 1],
            "es_hoy": visto == today,
        },
        "week": {"range": week_range, "days": week, "offset": week_offset},
        "streak": streak,
        "routine": routine,
        "plan": plan,
        "menu": menu,
        "checkin": checkin,
        "notifications_unread": 0,  # [pendiente] modelo de notificaciones
    }, "OK")


def _today_menu_summary(db: Session, detail, current_user: User, today_idx: int):
    """Resumen del menú/dieta de hoy: kcal y nº de comidas."""
    from app.models.client_menu import ClientMenu
    from app.models.weekly_menu import WeeklyMenu
    from app.models.nutrition.diet import Diet

    diet = None
    cm = db.query(ClientMenu).filter(
        ClientMenu.client_user_detail_id == detail.id
    ).order_by(ClientMenu.assigned_at.desc(), ClientMenu.id.desc()).first()
    menu_name = None
    if cm:
        wm = db.query(WeeklyMenu).filter(WeeklyMenu.id == cm.menu_id).first()
        if wm:
            menu_name = wm.name
            by_idx = {d.day_index: d for d in wm.days}
            md = by_idx.get(today_idx)
            if md and md.diet_id:
                diet = db.query(Diet).filter(Diet.id == md.diet_id).first()
    if not diet:
        diet = db.query(Diet).filter(
            Diet.user_id == current_user.id
        ).order_by(Diet.created_at.desc()).first()
    if not diet:
        return None

    meals, kcal, prot, carb, fat = _diet_meals_macros(diet)
    return {
        "diet_id": diet.id,
        "name": menu_name or diet.title,
        "kcal": round(kcal) if kcal else None,
        "meals_count": len(meals),
        "weekday": _WEEKDAY_NAMES[today_idx],
    }


_DAY_LABELS = ["L", "M", "X", "J", "V", "S", "D"]
_DAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _diet_meals_macros(diet):
    """Comidas (con kcal por comida) y macros de una dieta.

    Los macros salían SOLO de lo que el coach hubiera escrito como objetivo al
    crear la dieta. Con un plan montado en modo "kcal" —el más habitual: se
    escriben las kcal y no los macros— el cliente abría su nutrición y veía un
    guion en proteínas, carbohidratos y grasas, y el día sin kcal, con las
    comidas enteras debajo.

    Se enseña LO QUE HAY EN EL PLATO, no la meta que escribió el coach. Con la
    meta mandando, un día con 1164 kcal de objetivo y 1572 montadas le decía al
    cliente 1164: la cifra que tiene delante mientras come tiene que ser la de
    lo que se está comiendo. Y es la misma cuenta que ve su coach en la
    biblioteca, que si no cada uno lee un número distinto del mismo día.

    Sin nada montado no hay nada que sumar, y ahí queda lo escrito.
    """
    kcal = diet.calories
    prot = carb = fat = None
    if diet.detail:
        prot, carb, fat = diet.detail.proteins, diet.detail.carbs, diet.detail.fats
    tk, tp, tc, tf = totales_de_dieta(diet)
    if tk > 0:
        kcal = round(tk)
        prot = round(tp, 1)
        carb = round(tc, 1)
        fat = round(tf, 1)
    meals = []
    for food in diet.foods:
        mk = 0.0
        foods = []
        for dfa in food.detail:
            al = dfa.aliment
            if not al:
                continue
            if al.calories and dfa.quantity:
                mk += escalar(al.calories, al, dfa.quantity)
            foods.append({
                "name": al.name,
                "quantity": dfa.quantity,
                "unit": (al.quantity_unit or "g"),
                # Para agrupar la lista de la compra por pasillo. El alimento
                # de una dieta es una copia del catálogo, pero la copia se
                # lleva la categoría, así que sale de aquí sin ir al original.
                "category": (al.group_food.name if al.group_food else None),
            })
        meals.append({"name": food.name, "subtitle": food.subtitle, "time": food.time,
                      "kcal": round(mk) if mk else None, "foods": foods})
    meals.sort(key=lambda m: m["time"] or "~")
    return meals, kcal, prot, carb, fat




def _dias_cumplidos(db: Session, detail, data: dict) -> dict:
    """Marca en cada día si el cliente ya lo dio por cumplido.

    Va aquí y no dentro de cada uno de los tres caminos que arman la semana
    —calendario, menú semanal y dieta suelta— porque los tres devuelven la
    misma lista de días y uno de ellos se habría quedado sin la marca. Ese es
    justo el fallo que no se ve: el cliente marca el día, cambia de semana y al
    volver está desmarcado.
    """
    from app.models.nutrition_day import ClientNutritionDay

    dias = data.get("days") or []
    if not detail or not dias:
        return data
    fechas = [d["date"] for d in dias if d.get("date")]
    if not fechas:
        return data
    hechos = {
        f.day.isoformat() for f in
        db.query(ClientNutritionDay).filter(
            ClientNutritionDay.client_user_detail_id == detail.id,
            ClientNutritionDay.day.in_([date.fromisoformat(f) for f in fechas]),
        ).all()
    }
    for d in dias:
        d["completed"] = d.get("date") in hechos
    return data


def _semana_del_calendario(db, detail, week_start, today_idx):
    """La semana del cliente cuando la nutrición se programa día a día.

    Las dietas están puestas en su calendario como tareas de tipo `nutricion`,
    con `{"diet_id": ...}` dentro de `requirements`. Un día sin tarea es un día
    sin dieta, y se dice: mejor un hueco visible que el plan de otra semana.
    """
    import json

    from app.models.calendar_task import CalendarTask
    from app.models.nutrition.diet import Diet

    fin = week_start + timedelta(days=6)
    tareas = db.query(CalendarTask).filter(
        CalendarTask.client_user_detail_id == detail.id,
        CalendarTask.task_type == "nutricion",
        CalendarTask.task_date >= week_start,
        CalendarTask.task_date <= fin,
    ).order_by(CalendarTask.task_date.asc(), CalendarTask.id.asc()).all()

    por_dia = {}
    for t in tareas:
        try:
            req = json.loads(t.requirements) if t.requirements else {}
        except Exception:
            req = {}
        did = (req or {}).get("diet_id") if isinstance(req, dict) else None
        if not did:
            continue
        # Si hay varias en el mismo día se queda la primera: dos dietas el mismo
        # día no significan "come el doble".
        por_dia.setdefault((t.task_date - week_start).days, (did, t.title))

    days = []
    cache = {}
    for i in range(7):
        did, titulo = por_dia.get(i, (None, None))
        if did and did not in cache:
            cache[did] = db.query(Diet).filter(Diet.id == did).first()
        diet = cache.get(did)
        if diet:
            meals, kcal, prot, carb, fat = _diet_meals_macros(diet)
        else:
            meals, kcal, prot, carb, fat = [], None, None, None, None
        days.append({
            "day_index": i, "label": _DAY_LABELS[i],
            "name": (titulo or _DAY_NAMES[i]) if diet else _DAY_NAMES[i],
            "date": (week_start + timedelta(days=i)).isoformat(),
            "is_today": i == today_idx, "has_diet": diet is not None,
            "kcal": kcal, "protein": prot, "carbs": carb, "fats": fat, "meals": meals,
        })

    hay = any(d["has_diet"] for d in days)
    return {
        "menu": {"name": "Plan del calendario"} if hay else None,
        "week_start": week_start.isoformat(),
        # Cada día trae lo suyo, como un menú semanal: la pantalla no tiene que
        # avisar de que se repite, porque no se repite.
        "plan_semanal": True,
        "nutrition_mode": "calendario",
        "days": days,
    }



@router.get("/nutrition", summary="Nutrición del cliente", description="Plan nutricional (dietas) asignado al cliente autenticado, con totales y comidas por día de la semana.")
def client_nutrition(db: Session = Depends(get_db), current_user: User = Depends(require_role_ids(SUPERADMIN, ADMIN, COACH, CLIENT))):
    from app.models.client_menu import ClientMenu
    from app.models.weekly_menu import WeeklyMenu
    from app.models.nutrition.diet import Diet

    empty = {"menu": None, "week_start": None, "days": []}
    detail = _client_detail(db, current_user)
    if not detail:
        return send_response(empty, "Sin cliente")

    today = date.today()
    today_idx = today.weekday()  # 0 = lunes
    week_start = today - timedelta(days=today_idx)

    # 0) ¿Cómo se le programa la nutrición a este cliente?
    #
    #    Con el calendario activo, el plan semanal queda EN PAUSA. Eso tiene que
    #    ser de verdad: si el cliente siguiera viendo el plan semanal, el coach
    #    estaría programando en el calendario y su cliente comiendo otra cosa,
    #    sin que ninguno de los dos lo supiera.
    if (detail.nutrition_mode or "semanal") == "calendario":
        return send_response(_dias_cumplidos(
            db, detail, _semana_del_calendario(db, detail, week_start, today_idx)), "OK")

    # 1) Menú semanal asignado (ClientMenu → WeeklyMenu), si existe: cada día
    #    puede tener su propia dieta.
    cm = db.query(ClientMenu).filter(
        ClientMenu.client_user_detail_id == detail.id
    ).order_by(ClientMenu.assigned_at.desc(), ClientMenu.id.desc()).first()
    menu = db.query(WeeklyMenu).filter(WeeklyMenu.id == cm.menu_id).first() if cm else None

    if menu:
        by_idx = {d.day_index: d for d in menu.days}
        days = []
        for i in range(7):
            md = by_idx.get(i)
            diet = db.query(Diet).filter(Diet.id == md.diet_id).first() if (md and md.diet_id) else None
            if diet:
                meals, kcal, prot, carb, fat = _diet_meals_macros(diet)
            else:
                meals, kcal, prot, carb, fat = [], None, None, None, None
            days.append({
                "day_index": i, "label": _DAY_LABELS[i],
                "name": (md.name if (md and md.name) else _DAY_NAMES[i]),
                "date": (week_start + timedelta(days=i)).isoformat(),
                "is_today": i == today_idx, "has_diet": diet is not None,
                "kcal": kcal, "protein": prot, "carbs": carb, "fats": fat, "meals": meals,
            })
        return send_response(_dias_cumplidos(db, detail, {
            "menu": {"name": menu.name}, "week_start": week_start.isoformat(),
            "plan_semanal": True, "days": days}), "OK")

    # 2) Sin menú semanal: usar las dietas que el coach asignó directamente al
    #    cliente (Diet.user_id == cliente). Es el flujo real de client-profile.
    #    La dieta más reciente es el plan activo, mostrado todos los días.
    #
    #    Ojo con lo que esto significa: si el coach le asignó VARIAS dietas
    #    sueltas, el cliente solo ve la última, repetida los siete días, y las
    #    demás no aparecen por ninguna parte. Para comer distinto cada día hace
    #    falta un menú semanal (camino 1), que es el que reparte una dieta por
    #    día. Se devuelve `plan_semanal: False` para que la pantalla lo diga en
    #    vez de dejar al cliente cambiando de día sin ver ningún cambio.
    dietas = db.query(Diet).filter(
        Diet.user_id == current_user.id
    ).order_by(Diet.created_at.desc()).all()
    diet = dietas[0] if dietas else None
    if not diet:
        return send_response(empty, "Sin plan asignado")

    meals, kcal, prot, carb, fat = _diet_meals_macros(diet)
    days = []
    for i in range(7):
        days.append({
            "day_index": i, "label": _DAY_LABELS[i], "name": _DAY_NAMES[i],
            "date": (week_start + timedelta(days=i)).isoformat(),
            "is_today": i == today_idx, "has_diet": True,
            "kcal": kcal, "protein": prot, "carbs": carb, "fats": fat, "meals": meals,
        })
    return send_response(_dias_cumplidos(db, detail, {
        "menu": {"name": diet.title},
        "week_start": week_start.isoformat(),
        "plan_semanal": False,
        # Cuántas dietas sueltas tiene asignadas. Si son varias, el coach creó
        # material que el cliente no puede llegar a ver.
        "dietas_asignadas": len(dietas),
        "days": days,
    }), "OK")


class DiaCumplido(BaseModel):
    completado: bool = True


@router.post("/nutrition/day/{fecha}/completado",
             summary="Marcar (o desmarcar) un día de nutrición como cumplido")
def marcar_dia_nutricion(
    fecha: str,
    body: DiaCumplido,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role_ids(CLIENT)),
):
    """El botón del final de la pantalla de nutrición.

    Lo marca el CLIENTE y solo para sí mismo: no hay id de cliente en la ruta a
    propósito, porque el único que puede decir que ha comido lo del martes es
    quien comió.

    Se puede desmarcar. Un botón que solo va en un sentido convierte un toque
    sin querer en un dato falso que ya no hay forma de corregir.
    """
    from app.models.nutrition_day import ClientNutritionDay

    detail = _client_detail(db, current_user)
    if not detail:
        return send_error("Sin cliente", code=404)

    try:
        dia = date.fromisoformat(fecha)
    except ValueError:
        return send_error("Fecha no válida. Se espera AAAA-MM-DD.", code=422)

    # Marcar mañana no es marcar nada: todavía no ha pasado.
    if dia > date.today():
        return send_error("Ese día todavía no ha llegado", code=422)

    fila = db.query(ClientNutritionDay).filter(
        ClientNutritionDay.client_user_detail_id == detail.id,
        ClientNutritionDay.day == dia,
    ).first()

    if body.completado and not fila:
        db.add(ClientNutritionDay(client_user_detail_id=detail.id, day=dia))
        db.commit()
    elif not body.completado and fila:
        db.delete(fila)
        db.commit()

    return send_response({"date": dia.isoformat(), "completed": bool(body.completado)}, "OK")


@router.get("/recipes", summary="Recetas que el cliente puede ver",
            description="El catálogo de recetas de la plataforma y el de su centro, "
                        "con búsqueda por nombre y filtro por tipo de comida.")
def client_recipes(
    search: Optional[str] = Query(None),
    meal_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role_ids(CLIENT)),
):
    """La pestaña "Recetas" de la pantalla de nutrición.

    Hasta ahora TODOS los endpoints de recetas exigían admin, coach o editor:
    el cliente no podía leer ni una, aunque el catálogo se hizo para él. Este
    es su puerta, y es de solo lectura.

    Qué ve: las recetas de la plataforma (sin organización) y las de SU centro.
    Las de otro centro no, por el mismo motivo que no ve a sus clientes.
    """
    from sqlalchemy import or_
    from sqlalchemy.orm import selectinload
    from app.core.organizaciones import organizacion_de_detalle
    from app.models.nutrition.recipe import Recipe, RecipeDetail

    detail = _client_detail(db, current_user)
    coach = _coach_of(db, detail.id) if detail else None
    org = organizacion_de_detalle(db, coach) if coach else None

    q = db.query(Recipe).options(
        selectinload(Recipe.details).selectinload(RecipeDetail.aliment),
    ).filter(Recipe.state == 1)

    if org:
        q = q.filter(or_(Recipe.organization_id.is_(None),
                         Recipe.organization_id == org.id))
    else:
        # Sin centro, solo el catálogo de la plataforma. Enseñarle todas las
        # recetas de todos los centros sería abrir el material de otros.
        q = q.filter(Recipe.organization_id.is_(None))

    if search:
        q = q.filter(Recipe.name.ilike(f"%{search.strip()}%"))
    if meal_type:
        q = q.filter(Recipe.meal_type.ilike(f"%{meal_type.strip()}%"))

    total = q.count()
    filas = q.order_by(Recipe.name).offset((page - 1) * per_page).limit(per_page).all()

    # Solo lo que la tarjeta enseña. La receta entera —ingredientes, pasos,
    # notas del nutricionista— es otra pantalla y otra petición: mandarla aquí
    # serían veinticuatro recetas completas para pintar veinticuatro fotos.
    items = [{
        "id": r.id,
        "name": r.name,
        "image": r.image,
        "kcal": round(r.calories) if r.calories is not None else None,
        "prep_time": r.prep_time,
        "meal_type": r.meal_type,
        "difficulty": r.difficulty,
        "servings": r.servings,
    } for r in filas]

    return send_response({
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "last_page": max(1, (total + per_page - 1) // per_page),
        # Para las pastillas de arriba: los tipos que de verdad hay, no una
        # lista fija con categorías vacías que no llevan a ninguna parte.
        "meal_types": sorted({
            (t or "").strip() for (t,) in
            db.query(Recipe.meal_type).filter(
                Recipe.state == 1,
                Recipe.meal_type.isnot(None),
                Recipe.organization_id.is_(None) if not org else or_(
                    Recipe.organization_id.is_(None),
                    Recipe.organization_id == org.id),
            ).distinct().all() if (t or "").strip()
        }),
    }, "OK")


# ── Lista de la compra en PDF ──────────────────────────────────────────────
#
# Este endpoint DIBUJA, no calcula. Las cuentas —juntar el mismo alimento,
# sumar solo lo que comparte unidad, pasar de gramos a kilos— están en
# `frontend/js/lista-compra.js` y llegan aquí ya hechas. Rehacerlas en Python
# daría dos implementaciones que tienen que coincidir, y de esas dos siempre
# hay una que se queda atrás: el cliente vería una cantidad en la pantalla y
# otra distinta en el papel que se lleva al supermercado.
#
# Lo que llega es lo que el propio cliente acaba de ver en su pantalla y
# vuelve convertido en PDF para él: no da acceso a nada que no tuviera ya.

class _ItemCompra(BaseModel):
    nombre: str = Field(max_length=200)
    cantidad: str = Field(default="", max_length=60)


class _GrupoCompra(BaseModel):
    categoria: str = Field(default="Otros", max_length=120)
    items: List[_ItemCompra] = []


class ListaCompraPDF(BaseModel):
    titulo: str = Field(default="Lista de la compra", max_length=120)
    subtitulo: str = Field(default="", max_length=160)
    grupos: List[_GrupoCompra] = []


@router.post("/shopping-list/pdf", summary="Lista de la compra en PDF",
             description="Convierte en PDF la lista de la compra que el cliente ve en su plan nutricional.")
def shopping_list_pdf(
    data: ListaCompraPDF,
    _=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH, CLIENT)),
):
    from app.pdf.shopping_list_pdf import generar_lista_compra_pdf
    try:
        pdf = generar_lista_compra_pdf(
            data.titulo, data.subtitulo,
            [{"categoria": g.categoria,
              "items": [{"nombre": i.nombre, "cantidad": i.cantidad} for i in g.items]}
             for g in data.grupos])
    except Exception as e:
        return send_error(f"Error generando PDF: {e}", code=500)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="lista-compra.pdf"'},
    )


@router.get("/progress", summary="Progreso del cliente", description="Evolución del cliente: estadísticas, serie de peso y fotos de progreso.")
def client_progress(db: Session = Depends(get_db), current_user: User = Depends(require_role_ids(SUPERADMIN, ADMIN, COACH, CLIENT))):
    from app.models.checkin import WeeklyCheckin

    empty = {"stats": {"weeks": 0, "kg_lost": None, "workouts": 0},
             "weight": {"series": [], "delta": None, "latest": None},
             "photos": {"frontal": [], "lateral": [], "espalda": [], "total": 0}}
    detail = _client_detail(db, current_user)
    if not detail:
        return send_response(empty, "Sin cliente")

    checks = db.query(WeeklyCheckin).filter(
        WeeklyCheckin.client_user_detail_id == detail.id
    ).order_by(WeeklyCheckin.checkin_date.asc()).all()

    workouts = db.query(WorkoutSession).filter(
        WorkoutSession.client_user_detail_id == detail.id
    ).count()

    # Serie de peso
    with_w = [c for c in checks if c.weight is not None]
    series = [{"date": c.checkin_date.isoformat(), "weight": c.weight} for c in with_w]
    delta = latest = None
    if with_w:
        latest = with_w[-1].weight
        if len(with_w) >= 2 and with_w[0].weight is not None:
            delta = round(with_w[-1].weight - with_w[0].weight, 1)

    # Semanas de seguimiento
    weeks = 0
    if checks:
        span = (checks[-1].checkin_date - checks[0].checkin_date).days
        weeks = span // 7 + 1

    kg_lost = round(with_w[0].weight - with_w[-1].weight, 1) if len(with_w) >= 2 else None

    def _photos(attr):
        out = []
        for c in checks:
            url = getattr(c, attr, None)
            if url:
                # El id va porque sin él la foto no se puede borrar: la pantalla
                # tendría la imagen pero no sabría a qué check-in pertenece.
                out.append({"id": c.id, "date": c.checkin_date.isoformat(),
                            "url": url, "weight": c.weight})
        return out
    frontal, lateral, espalda = _photos("photo_url"), _photos("photo2"), _photos("photo3")

    # ── Métricas equivalentes a las del panel del coach ──
    peso_inicio = with_w[0].weight if with_w else None
    peso_actual = with_w[-1].weight if with_w else None
    perdido = round(peso_inicio - peso_actual, 1) if (peso_inicio is not None and peso_actual is not None) else None

    # Semanas: desde start_date del cliente si existe; si no, por el rango de check-ins
    semanas = None
    if getattr(detail, "start_date", None):
        sd = detail.start_date.date() if hasattr(detail.start_date, "date") else detail.start_date
        semanas = max(0, round((date.today() - sd).days / 7))
    elif len(checks) >= 2:
        semanas = max(1, round((checks[-1].checkin_date - checks[0].checkin_date).days / 7))

    ritmo_real = round(perdido / semanas, 2) if (perdido is not None and semanas) else None

    # Objetivo del cliente (ClientTarget) → proyección
    from app.models.client_target import ClientTarget
    tgt = db.query(ClientTarget).filter(ClientTarget.user_id == current_user.id).first()
    target_weight = tgt.target_weight if tgt else None
    a_perder = round(peso_actual - target_weight, 1) if (peso_actual is not None and target_weight is not None) else None
    estimacion_sem = None
    if a_perder is not None and ritmo_real and ritmo_real > 0:
        import math
        estimacion_sem = max(0, math.ceil(a_perder / ritmo_real))

    # ── Fuerza: evolución real por ejercicio (de las series registradas) ──
    strength = _strength_summary(db, detail, weeks_back=6)

    # ── Medidas corporales (último check-in con datos + evolución) ──
    _MEAS = [("body_fat", "% grasa"), ("muscle_mass", "Masa muscular"), ("waist", "Cintura"),
             ("chest", "Pecho"), ("hips", "Cadera"), ("arms", "Brazos"), ("legs", "Piernas")]
    measurements = []
    for field, label in _MEAS:
        vals = [(c.checkin_date, getattr(c, field, None)) for c in checks if getattr(c, field, None) is not None]
        if not vals:
            continue
        first_v, last_v = vals[0][1], vals[-1][1]
        measurements.append({
            "key": field, "label": label,
            "latest": last_v,
            "delta": round(last_v - first_v, 1) if len(vals) >= 2 else None,
            "series": [{"date": d.isoformat(), "value": v} for d, v in vals],
        })

    return send_response({
        "stats": {"weeks": weeks, "kg_lost": kg_lost, "workouts": workouts},
        # Cuándo fue el último. La pantalla de check-in lo usa para avisar de
        # que ya mandó uno hoy —sin bloquearle: puede haberse dejado las fotos—.
        # Se da la fecha suelta y no el check-in entero: ese formulario arranca
        # SIEMPRE en blanco, así que sus valores no le hacen falta.
        "ultimo_checkin": (checks[-1].checkin_date.isoformat()
                           if checks and checks[-1].checkin_date else None),
        "summary": {
            "peso_inicio": peso_inicio,
            "peso_actual": peso_actual,
            "perdido": perdido,
            "semanas": semanas,
            "ritmo_real": ritmo_real,
        },
        "target": {
            "target_weight": target_weight,
            "a_perder": a_perder,
            "ritmo_real": ritmo_real,
            "estimacion_sem": estimacion_sem,
            # Fechas del plan: permiten dibujar la línea de objetivo en paralelo
            # a la real (dónde debería estar vs dónde está).
            "start_date": (detail.start_date.date().isoformat() if getattr(detail, "start_date", None) else None),
            "end_date": (detail.end_date.date().isoformat() if getattr(detail, "end_date", None) else None),
            "start_weight": peso_inicio,
        },
        "weight": {"series": series, "delta": delta, "latest": latest},
        "strength": strength,
        "measurements": measurements,
        "photos": {
            "frontal": frontal, "lateral": lateral, "espalda": espalda,
            "total": len(frontal) + len(lateral) + len(espalda),
        },
    }, "OK")


def _strength_summary(db: Session, detail, weeks_back: int = 6):
    """Evolución de carga por ejercicio a partir de las series registradas.

    Para cada ejercicio devuelve la mejor serie (mayor peso) de cada sesión,
    en orden cronológico — es lo que alimenta el sparkline real.
    """
    from app.models.session_log import WorkoutSessionExercise, WorkoutSessionSet

    since = date.today() - timedelta(weeks=weeks_back)
    rows = (
        db.query(WorkoutSessionExercise, WorkoutSession.session_date)
        .join(WorkoutSession, WorkoutSession.id == WorkoutSessionExercise.session_id)
        .filter(
            WorkoutSession.client_user_detail_id == detail.id,
            WorkoutSession.session_date >= since,
        )
        .order_by(WorkoutSession.session_date.asc(), WorkoutSessionExercise.id.asc())
        .all()
    )

    by_ex = {}
    for wse, sdate in rows:
        key = wse.training_id or (wse.name or "?")
        best_w, best_reps = None, None
        for st in (wse.sets or []):
            if st.weight is None:
                continue
            if best_w is None or st.weight > best_w:
                best_w, best_reps = st.weight, st.reps
        if best_w is None:
            continue
        entry = by_ex.setdefault(str(key), {
            "training_id": wse.training_id, "name": wse.name or "Ejercicio",
            "muscle_group_name": wse.muscle_group_name, "points": [],
        })
        entry["points"].append({"date": sdate.isoformat() if sdate else None, "weight": best_w, "reps": best_reps})

    out = []
    for e in by_ex.values():
        pts = e["points"]
        first_w, last_w = pts[0]["weight"], pts[-1]["weight"]
        out.append({
            **e,
            "latest_weight": last_w,
            "latest_reps": pts[-1]["reps"],
            "delta": round(last_w - first_w, 1) if len(pts) >= 2 else None,
            "sessions": len(pts),
        })
    # Los que más han progresado primero, y con más sesiones registradas
    out.sort(key=lambda x: (-(x["delta"] or 0), -x["sessions"]))
    return out[:6]


class _ClientCheckinBody(BaseModel):
    weight: Optional[float] = None
    photo_frontal: Optional[str] = None
    photo_lateral: Optional[str] = None
    photo_espalda: Optional[str] = None
    body_fat: Optional[float] = None
    muscle_mass: Optional[float] = None
    waist: Optional[float] = None
    chest: Optional[float] = None
    hips: Optional[float] = None
    arms: Optional[float] = None
    legs: Optional[float] = None
    notes: Optional[str] = None
    # Cómo se ha sentido la semana, de 0 a 10. Sin esto el cliente solo podía
    # mandar números de báscula, y la bandeja del coach enseñaba las cuatro
    # puntuaciones siempre vacías.
    energy: Optional[int] = None
    effort: Optional[int] = None
    hunger: Optional[int] = None
    sleep: Optional[int] = None


@router.post("/checkin", summary="Registrar check-in (cliente)", description="El cliente registra/actualiza su check-in de hoy (peso, medidas o fotos).")
def client_checkin(body: _ClientCheckinBody, db: Session = Depends(get_db), current_user: User = Depends(require_role_ids(CLIENT))):
    from app.models.checkin import WeeklyCheckin
    detail = _client_detail(db, current_user)
    if not detail:
        return send_error("Perfil de cliente no encontrado")

    today = date.today()
    ck = db.query(WeeklyCheckin).filter(
        WeeklyCheckin.client_user_detail_id == detail.id,
        WeeklyCheckin.checkin_date == today,
    ).first()
    if not ck:
        coach = _coach_of(db, detail.id)
        ck = WeeklyCheckin(
            client_user_detail_id=detail.id,
            coach_user_detail_id=coach.id if coach else None,
            checkin_date=today,
        )
        db.add(ck)

    # Solo se actualizan los campos que llegan (peso, fotos o medidas)
    mapping = {
        "weight": body.weight, "photo_url": body.photo_frontal, "photo2": body.photo_lateral,
        "photo3": body.photo_espalda, "body_fat": body.body_fat, "muscle_mass": body.muscle_mass,
        "waist": body.waist, "chest": body.chest, "hips": body.hips, "arms": body.arms,
        "legs": body.legs, "notes": body.notes,
        "energy": body.energy, "effort": body.effort,
        "hunger": body.hunger, "sleep": body.sleep,
    }
    for field, value in mapping.items():
        if value is not None:
            setattr(ck, field, value)

    db.commit()
    db.refresh(ck)
    completed = _autocomplete_checkin_tasks(db, detail, ck)
    return send_response({
        "id": ck.id,
        "checkin_date": ck.checkin_date.isoformat(),
        "tasks_completed": completed,
    }, "Check-in guardado")


# El ángulo, como lo llama la pantalla, y la columna donde vive de verdad.
# `photo_url`/`photo2`/`photo3` son nombres heredados que no dicen nada; el
# cliente ve "frontal", "lateral" y "espalda".
FOTOS = {"frontal": "photo_url", "lateral": "photo2", "espalda": "photo3"}


@router.delete("/checkin/{checkin_id}/foto/{angulo}", summary="Borrar una foto de progreso (cliente)",
               description="Quita la foto de ese ángulo del check-in. Si el check-in se queda sin nada más, se borra entero.")
def borrar_foto_checkin(
    checkin_id: str, angulo: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role_ids(CLIENT)),
):
    """Deshacer una foto subida por error.

    Hacía falta porque no había vuelta atrás: el POST de check-in solo escribe
    los campos que LLEGAN, así que mandar la foto vacía no la borraba, la
    ignoraba. Una foto equivocada se quedaba en el progreso del cliente y en la
    bandeja del coach para siempre.
    """
    from app.models.checkin import WeeklyCheckin

    campo = FOTOS.get((angulo or "").lower())
    if not campo:
        return send_error("Ángulo desconocido. Usa frontal, lateral o espalda.", code=400)

    detail = _client_detail(db, current_user)
    if not detail:
        return send_error("Perfil de cliente no encontrado")

    ck = db.query(WeeklyCheckin).filter(
        WeeklyCheckin.id == checkin_id,
        # Un cliente solo borra lo suyo. Sin esta condición, cambiando el número
        # de la URL se borrarían las fotos de otra persona.
        WeeklyCheckin.client_user_detail_id == detail.id,
    ).first()
    if not ck:
        return send_error("Check-in no encontrado", code=404)

    url = getattr(ck, campo, None)
    if not url:
        # Ya no está. No es un error: dos clics seguidos no deben dar un fallo.
        return send_response({"borrada": False, "checkin_borrado": False}, "Esa foto ya no estaba")

    setattr(ck, campo, None)

    # Si el check-in existía SOLO para llevar esa foto, se va con ella. Dejarlo
    # vacío pondría un check-in en blanco en el historial del cliente y en la
    # bandeja del coach, que es justo lo que el cliente quería deshacer.
    campos = ["weight", "body_fat", "muscle_mass", "waist", "chest", "hips",
              "arms", "legs", "notes", "energy", "effort", "hunger", "sleep",
              *FOTOS.values()]
    vacio = all(getattr(ck, f, None) in (None, "") for f in campos)

    _desmarcar_tareas(db, detail, ck, borrado=vacio)
    if vacio:
        db.delete(ck)
    db.commit()

    # El fichero, después de soltar la referencia: si el almacén no contesta,
    # la foto ya ha dejado de verse igualmente.
    from app.routers.files import borrar_del_almacen
    borrar_del_almacen(url)

    return send_response({"borrada": True, "checkin_borrado": vacio}, "Foto eliminada")


def _desmarcar_tareas(db: Session, detail, checkin, borrado: bool) -> None:
    """Revisa las tareas que se dieron por hechas gracias a este check-in.

    Una tarea de check-in se marca sola cuando están todas las cosas que pedía.
    Si el cliente quita la foto, esa tarea ya no está cumplida, y dejarla en
    verde le diría que no tiene nada pendiente cuando sí lo tiene.
    """
    from app.models.calendar_task import CalendarTask

    dia = checkin.checkin_date
    wk_start = dia - timedelta(days=dia.weekday())
    tasks = db.query(CalendarTask).filter(
        CalendarTask.client_user_detail_id == detail.id,
        CalendarTask.task_type == "checkin",
        CalendarTask.done == True,  # noqa: E712
        CalendarTask.task_date >= wk_start,
        CalendarTask.task_date <= wk_start + timedelta(days=6),
    ).all()

    for t in tasks:
        items = (_task_requirements(t).get("items")) or ["peso"]
        estado = None if borrado else checkin
        if not all(_item_done(estado, it) for it in items):
            t.done = False
            t.done_at = None
        # La referencia se suelta siempre que el check-in desaparezca: apuntaría
        # a una fila que ya no existe.
        if borrado and t.checkin_id == checkin.id:
            t.checkin_id = None


def _autocomplete_checkin_tasks(db: Session, detail, checkin) -> list:
    """Marca hechas las tareas de check-in cuyos items pedidos ya están todos
    registrados, y las vincula al check-in. Así la alerta desaparece sola."""
    from datetime import datetime
    from app.models.calendar_task import CalendarTask

    wk_start = checkin.checkin_date - timedelta(days=checkin.checkin_date.weekday())
    wk_end = wk_start + timedelta(days=6)
    tasks = db.query(CalendarTask).filter(
        CalendarTask.client_user_detail_id == detail.id,
        CalendarTask.task_type == "checkin",
        CalendarTask.done == False,  # noqa: E712
        CalendarTask.task_date >= wk_start,
        CalendarTask.task_date <= wk_end,
    ).all()

    done_ids = []
    for t in tasks:
        items = (_task_requirements(t).get("items")) or ["peso"]
        if all(_item_done(checkin, it) for it in items):
            t.done = True
            t.done_at = datetime.utcnow()
            if not t.checkin_id:
                t.checkin_id = checkin.id
            done_ids.append(t.id)
    if done_ids:
        db.commit()
    return done_ids


class _SessionSetBody(BaseModel):
    reps: Optional[str] = None
    weight: Optional[float] = None
    rpe: Optional[float] = None
    done: Optional[bool] = False


class _SessionExerciseBody(BaseModel):
    training_id: Optional[int] = None
    name: Optional[str] = None
    muscle_group_name: Optional[str] = None
    notes: Optional[str] = None
    sets: Optional[list[_SessionSetBody]] = None


class _WorkoutSessionBody(BaseModel):
    routine_id: Optional[int] = None
    day_name: Optional[str] = Field(default=None, max_length=255)
    duration_min: Optional[int] = None
    rpe: Optional[float] = None
    # Cómo se ha sentido, de 1 a 5. Opcional: si prefiere no decirlo, se queda
    # vacío, y la ficha del coach enseña un hueco en vez de inventarse un
    # "normal" que el cliente nunca dio.
    mood: Optional[int] = Field(default=None, ge=1, le=5)
    # Con qué energía llegó, de 1 a 10. Se pregunta al terminar junto al
    # esfuerzo (`rpe`), y como aquél es opcional.
    energy: Optional[int] = Field(default=None, ge=1, le=10)
    notes: Optional[str] = None
    exercises: Optional[list[_SessionExerciseBody]] = None


@router.post("/workout-session", summary="Registrar entrenamiento (cliente)", description="El cliente registra una sesión completada hoy: duración, RPE, notas y el detalle de ejercicios con sus series (reps, kg, RPE).")
def client_workout_session(body: _WorkoutSessionBody, db: Session = Depends(get_db), current_user: User = Depends(require_role_ids(CLIENT))):
    from app.models.session_log import WorkoutSessionExercise, WorkoutSessionSet

    detail = _client_detail(db, current_user)
    if not detail:
        return send_error("Perfil de cliente no encontrado")
    session = WorkoutSession(
        client_user_detail_id=detail.id,
        routine_id=body.routine_id,
        day_name=body.day_name,
        session_date=date.today(),
        duration_min=body.duration_min,
        rpe=body.rpe,
        mood=body.mood,
        energy=body.energy,
        notes=body.notes,
    )
    db.add(session)
    db.flush()

    # Detalle: un registro por ejercicio y una fila por serie
    total_sets = 0
    for i, ex in enumerate(body.exercises or []):
        wse = WorkoutSessionExercise(
            session_id=session.id,
            training_id=ex.training_id,
            name=ex.name,
            muscle_group_name=ex.muscle_group_name,
            order_index=i,
            notes=(ex.notes or None),
        )
        db.add(wse)
        db.flush()
        for n, s in enumerate(ex.sets or [], start=1):
            db.add(WorkoutSessionSet(
                session_exercise_id=wse.id,
                set_number=n,
                reps=(s.reps or None),
                weight=s.weight,
                rpe=s.rpe,
                done=bool(s.done),
            ))
            total_sets += 1

    db.commit()
    db.refresh(session)
    return send_response({
        "id": session.id,
        "session_date": session.session_date.isoformat(),
        "exercises": len(body.exercises or []),
        "sets": total_sets,
    }, "Entrenamiento registrado")


class _SummaryBody(BaseModel):
    exercises: Optional[list[_SessionExerciseBody]] = None


@router.post("/workout-summary", summary="Resumen de la sesión antes de guardarla", description="Series hechas, volumen levantado y récords de la sesión que el cliente acaba de terminar. No guarda nada: es lo que se le enseña en la pantalla de fin para que lo vea antes de decidir.")
def client_workout_summary(
    body: _SummaryBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role_ids(CLIENT)),
):
    """Las cuentas de la pantalla de fin, en el servidor.

    Series y volumen podría sacarlos el navegador, pero entonces habría dos
    fórmulas para el mismo número: la del móvil al terminar y la del historial
    que ve el coach. Cuando divergen —un rango de repeticiones "8-10" contado
    por el mayor en un sitio y por el primero en otro— el cliente ve 12 000 kg
    y su coach 9 800, y nadie sabe cuál es.
    """
    from app.core.entrenos import clave_ejercicio, mejor_marca, records_de, repeticiones
    from app.models.session_log import WorkoutSessionExercise

    detail = _client_detail(db, current_user)
    if not detail:
        return send_error("Perfil de cliente no encontrado")

    ejercicios = body.exercises or []

    # La mejor marca de cada ejercicio en TODO lo que lleva registrado.
    previas = {}
    for ex in (db.query(WorkoutSessionExercise)
               .join(WorkoutSession, WorkoutSessionExercise.session_id == WorkoutSession.id)
               .filter(WorkoutSession.client_user_detail_id == detail.id).all()):
        clave = clave_ejercicio(ex.name)
        marca = mejor_marca(ex.sets)
        if not clave or marca is None:
            continue
        if marca > previas.get(clave, 0):
            previas[clave] = marca

    records = records_de(ejercicios, previas)

    # Solo lo MARCADO cuenta, igual que en el tonelaje del historial: sumar lo
    # que dejó a medias sería contarle kilos que no levantó.
    hechas = 0
    volumen = 0.0
    for ex in ejercicios:
        for st in (ex.sets or []):
            if not st.done:
                continue
            hechas += 1
            reps = repeticiones(st.reps)
            if st.weight is not None and reps:
                volumen += float(st.weight) * reps

    return send_response({
        "sets": hechas,
        "volume": round(volumen, 1),
        "records": len(records),
        "record_exercises": records,
    }, "OK")


def _lo_que_ha_hecho(db: Session, client_detail_id: str, training_id: int):
    """Las sesiones de ESE cliente con ESE ejercicio, de la más vieja a la más
    nueva, con el peso top, el 1RM, el volumen y el detalle de cada una.

    Se filtra por `training_id` y no por nombre: el cliente pregunta por el
    ejercicio que tiene delante, no por todos los que se llamen igual.
    """
    from app.core.entrenos import fila_de_sesion
    from app.models.routine import RoutineDayDetail
    from app.models.session_log import WorkoutSessionExercise

    # El descanso PRESCRITO, el que su coach puso en la rutina. No es lo que
    # descansó de verdad —eso no se mide— y la pantalla lo dice.
    descanso = (db.query(RoutineDayDetail.break_time)
                .filter(RoutineDayDetail.training_id == training_id,
                        RoutineDayDetail.break_time.isnot(None))
                .limit(1).scalar())

    filas = []
    ejercicios = (db.query(WorkoutSessionExercise)
                  .join(WorkoutSession,
                        WorkoutSessionExercise.session_id == WorkoutSession.id)
                  .filter(WorkoutSession.client_user_detail_id == client_detail_id,
                          WorkoutSessionExercise.training_id == training_id)
                  .order_by(WorkoutSession.session_date.asc(),
                            WorkoutSession.id.asc())
                  .all())
    for ex in ejercicios:
        fila = fila_de_sesion(ex, ex.session, descanso)
        if fila is None:
            continue
        # De qué día de la rutina fue, que es como el cliente lo reconoce.
        fila["sesion"] = ex.session.day_name
        filas.append(fila)
    return filas


NIVELES = {1: "Principiante", 2: "Intermedio", 3: "Avanzado"}
TIPOS = {"compound": "Compuesto", "isolation": "Aislamiento",
         "cardio": "Cardio", "mobility": "Movilidad"}
DONDE = {"gym": "Gimnasio", "home": "Casa", "outdoor": "Aire libre", "both": "Gimnasio o casa"}


@router.get("/exercise/{training_id}", summary="Ficha de un ejercicio (cliente)", description="Cómo se hace el ejercicio: descripción, músculos, material, patrón de movimiento y recomendaciones. Solo de los ejercicios que el cliente tiene en alguna de sus rutinas.")
def client_exercise(
    training_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role_ids(CLIENT)),
):
    """La ficha que el cliente ve al tocar la foto del ejercicio.

    Solo devuelve ejercicios que estén en ALGUNA de sus rutinas. El catálogo
    entero no es suyo: hay ejercicios privados de otras organizaciones, y
    dejarle pedir cualquier id sería enseñárselos con solo acertar un número.
    """
    from app.core.entrenos import records_de_ejercicio
    from app.models.muscle_group import MuscleGroup
    from app.models.routine import RoutineDayDetail
    from app.models.training import Training

    suyo = (db.query(RoutineDayDetail.id)
            .join(Routine, RoutineDayDetail.routine_id == Routine.id)
            .filter(Routine.user_id == current_user.id,
                    RoutineDayDetail.training_id == training_id)
            .first())
    if not suyo:
        return send_error("Ejercicio no encontrado", code=404)

    t = db.query(Training).filter(Training.id == training_id).first()
    if not t:
        return send_error("Ejercicio no encontrado", code=404)

    # Músculos secundarios: se guardan como ids separados por comas.
    sec_ids = [int(x) for x in str(t.secondary_muscle_group_ids or "").split(",")
               if str(x).strip().isdigit()]
    if not sec_ids and t.secondary_muscle_group_id:
        sec_ids = [t.secondary_muscle_group_id]
    nombres = {}
    if sec_ids:
        nombres = {g.id: g.name for g in
                   db.query(MuscleGroup).filter(MuscleGroup.id.in_(sec_ids)).all()}

    niveles = sorted({int(x) for x in str(t.difficulty_levels or "").split(",")
                      if str(x).strip().isdigit()})
    if not niveles and t.difficulty:
        niveles = [t.difficulty]

    # El historial cuelga del `user_detail`, no del usuario: es donde se
    # guardan las sesiones. Sin cliente no hay nada que contar, pero la ficha
    # del ejercicio se sigue pudiendo leer.
    detalle = _client_detail(db, current_user)
    filas = _lo_que_ha_hecho(db, detalle.id, training_id) if detalle else []
    records = records_de_ejercicio(filas)
    # La evolución de carga: el peso más alto de cada sesión, de la más vieja a
    # la más nueva. Una sesión por tiempo no aporta punto: la línea es de kilos.
    evolucion = [{"fecha": f["fecha"], "peso": f["peso_top"]}
                 for f in filas if f["peso_top"] is not None]
    # Y el historial, de la más reciente primero: es lo que se quiere ver.
    historial = list(reversed(filas))

    return send_response({
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "image": t.image,
        "video_url": t.video_url,
        "muscle_group_name": t.muscle_group.name if t.muscle_group else None,
        "secondary_muscle_names": [nombres[i] for i in sec_ids if i in nombres],
        "material": t.material,
        "movement_pattern": t.movement_pattern,
        # En palabras, no en códigos: "compound" y un 2 no le dicen nada a quien
        # está entrenando con el móvil en la mano.
        "exercise_type": TIPOS.get(t.exercise_type or ""),
        "location": DONDE.get(t.location or ""),
        "difficulty_names": [NIVELES[n] for n in niveles if n in NIVELES],
        "rec_series": t.rec_series,
        "rec_reps": t.rec_reps,
        "rec_rest": t.rec_rest,
        # Lo que el cliente ha hecho con este ejercicio: sus récords, cómo ha
        # ido subiendo la carga y las sesiones anteriores con sus series. Es la
        # MISMA cuenta que ve su coach en la pantalla de Fuerza —vive en
        # core/entrenos— para que no lean cifras distintas del mismo
        # levantamiento.
        "records": records,
        "evolucion": evolucion,
        "historial": historial,
    }, "OK")


@router.get("/exercise-history", summary="Historial de ejercicios (cliente)", description="Última sesión registrada de cada ejercicio indicado, para mostrar la columna 'Anterior'.")
def client_exercise_history(
    training_ids: Optional[str] = Query(None, description="IDs de ejercicio separados por coma"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role_ids(CLIENT)),
):
    from app.models.session_log import WorkoutSessionExercise, WorkoutSessionSet

    detail = _client_detail(db, current_user)
    if not detail:
        return send_response({}, "Sin cliente")

    ids = []
    for part in (training_ids or "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    if not ids:
        return send_response({}, "OK")

    # Última aparición de cada ejercicio en las sesiones del cliente
    rows = (
        db.query(WorkoutSessionExercise, WorkoutSession.session_date)
        .join(WorkoutSession, WorkoutSession.id == WorkoutSessionExercise.session_id)
        .filter(
            WorkoutSession.client_user_detail_id == detail.id,
            WorkoutSessionExercise.training_id.in_(ids),
        )
        .order_by(WorkoutSession.session_date.desc(), WorkoutSessionExercise.id.desc())
        .all()
    )

    out = {}
    for wse, sdate in rows:
        key = str(wse.training_id)
        if key in out:
            continue  # ya tenemos la más reciente
        sets = [{
            "set_number": s.set_number,
            "reps": s.reps,
            "weight": s.weight,
            "rpe": s.rpe,
        } for s in wse.sets if s.done or s.reps or s.weight]
        if not sets:
            continue
        out[key] = {"date": sdate.isoformat() if sdate else None, "sets": sets}
    return send_response(out, "OK")


_REQ_LABELS = {"peso": "Peso", "medidas": "Medidas corporales", "fotos": "Fotos de progreso"}
# Campos del check-in que satisfacen cada item pedido
_REQ_FIELDS = {
    "peso": ["weight"],
    "medidas": ["body_fat", "muscle_mass", "waist", "chest", "hips", "arms", "legs"],
    "fotos": ["photo_url", "photo2", "photo3"],
    "sensaciones": ["energy", "effort", "hunger", "sleep"],
}


def _asegurar_asignacion(db: Session, t, detail, req: dict, current_user):
    """La asignación de formulario que hay detrás de una tarea de calendario.

    Cuando el coach programa un formulario para un día, la tarea guarda el id de
    la PLANTILLA (`form_template_id`). Pero un cliente no rellena una plantilla:
    rellena una asignación suya, que es la que recoge sus respuestas. Ese salto
    no lo daba nadie, así que la tarea aparecía en su pantalla sin forma de
    abrirla: solo quedaba "marcar hecho", que es mentir sobre haberlo rellenado.

    La asignación se crea aquí, la primera vez que el cliente ve la tarea, y su
    id se guarda en la propia tarea para que no se cree otra en cada visita. Es
    una escritura dentro de una lectura, que no es bonito, pero es lo que arregla
    también las tareas que ya estaban creadas sin ella — que son las que el
    coach tiene hoy en pantalla.
    """
    from app.models.form import FormAssignment

    if not detail:
        return None

    ya = req.get("form_assignment_id")
    if ya:
        asign = db.query(FormAssignment).filter(FormAssignment.id == ya).first()
        if asign:
            return asign          # si se borró, se vuelve a crear más abajo

    plantilla_id = req.get("form_template_id")
    if not plantilla_id:
        return None
    try:
        plantilla_id = int(plantilla_id)
    except (TypeError, ValueError):
        return None

    # Si el coach ya se la había mandado por correo, se reutiliza esa: crear
    # una segunda le dejaría dos formularios iguales sin saber cuál rellenar.
    asign = (
        db.query(FormAssignment)
        .filter(
            FormAssignment.client_user_detail_id == detail.id,
            FormAssignment.form_template_id == plantilla_id,
        )
        .order_by(FormAssignment.created_at.desc())
        .first()
    )
    if not asign:
        asign = FormAssignment(
            form_template_id=plantilla_id,
            client_user_detail_id=detail.id,
            # Quien la programó fue el coach de la tarea, no quien mira ahora.
            assigned_by=t.coach_user_id or current_user.id,
            status="pending",
        )
        db.add(asign)
        db.flush()

    import json
    req["form_assignment_id"] = asign.id
    t.requirements = json.dumps(req)
    db.commit()
    return asign


def _task_requirements(t):
    """requirements de la tarea (JSON en texto) como dict."""
    import json
    if not getattr(t, "requirements", None):
        return {}
    try:
        val = json.loads(t.requirements)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _checkin_for(db: Session, detail, ref_date: date):
    """Check-in de la semana de ref_date (los datos se acumulan por semana)."""
    wk_start = ref_date - timedelta(days=ref_date.weekday())
    wk_end = wk_start + timedelta(days=6)
    return db.query(WeeklyCheckin).filter(
        WeeklyCheckin.client_user_detail_id == detail.id,
        WeeklyCheckin.checkin_date >= wk_start,
        WeeklyCheckin.checkin_date <= wk_end,
    ).order_by(WeeklyCheckin.checkin_date.desc()).first()


def _item_done(checkin, item: str) -> bool:
    if not checkin:
        return False
    return any(getattr(checkin, f, None) is not None for f in _REQ_FIELDS.get(item, []))


@router.get("/requests", summary="Lo que te pide tu coach", description="Tareas asignadas por el coach pendientes de cumplir, con el estado de cada cosa que pide (peso, medidas, fotos, formulario, rutina…).")
def client_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role_ids(CLIENT)),
):
    from app.models.calendar_task import CalendarTask, COLOR_MAP

    detail = _client_detail(db, current_user)
    if not detail:
        return send_response({"pending": 0, "items": []}, "Sin cliente")

    today = date.today()
    # Ventana: desde hace 14 días (para no perder lo atrasado) hasta hoy
    since = today - timedelta(days=14)
    tasks = db.query(CalendarTask).filter(
        CalendarTask.client_user_detail_id == detail.id,
        CalendarTask.task_date >= since,
        CalendarTask.task_date <= today,
    ).order_by(CalendarTask.task_date.desc(), CalendarTask.id.desc()).all()

    out = []
    for t in tasks:
        req = _task_requirements(t)
        entry = {
            "id": t.id,
            "date": t.task_date.isoformat() if t.task_date else None,
            "task_type": t.task_type,
            "title": t.title or (t.task_type or "Tarea").capitalize(),
            "notes": t.notes,
            "color": t.color or COLOR_MAP.get(t.task_type, "#9CA3AF"),
            "done": bool(t.done),
            "is_today": t.task_date == today,
            "overdue": bool(t.task_date and t.task_date < today and not t.done),
            "requirements": req or None,
            "checklist": [],
            "action": None,
        }

        if t.task_type == "checkin":
            ck = _checkin_for(db, detail, t.task_date or today)
            items = req.get("items") or ["peso"]
            for it in items:
                entry["checklist"].append({
                    "key": it,
                    "label": _REQ_LABELS.get(it, it.capitalize()),
                    "done": _item_done(ck, it),
                })
            entry["action"] = "checkin"
            # La tarea se considera cumplida cuando todo lo pedido está registrado
            if entry["checklist"] and all(c["done"] for c in entry["checklist"]):
                entry["done"] = True
        elif t.task_type in ("rutina", "cardio"):
            entry["action"] = "entrena"
        elif t.task_type == "nutricion":
            entry["action"] = "nutricion"
        elif t.task_type == "formulario":
            entry["action"] = "formulario"
            asignacion = _asegurar_asignacion(db, t, detail, req, current_user)
            if asignacion:
                entry["form_assignment_id"] = asignacion.id
                # Ya contestado: la tarea está cumplida aunque nadie le haya
                # dado a "marcar hecho".
                if asignacion.status == "submitted":
                    entry["done"] = True
            else:
                # Sin formulario detrás no se puede prometer un enlace. Se deja
                # como tarea normal en vez de llevar a una página rota.
                entry["action"] = None
        elif t.task_type == "mensaje":
            entry["action"] = "mensaje"

        out.append(entry)

    pending = [e for e in out if not e["done"]]
    return send_response({
        "pending": len(pending),
        "items": out,
    }, "OK")


@router.get("/calendar", summary="Calendario del cliente", description="Vista mensual con todo lo asignado por el coach: entrenamiento, nutrición y check-ins.")
def client_calendar(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role_ids(SUPERADMIN, ADMIN, COACH, CLIENT)),
):
    import calendar as _cal
    today = date.today()
    y = year or today.year
    m = month or today.month
    if m < 1 or m > 12:
        return send_error("Mes no válido", code=400)
    ndays = _cal.monthrange(y, m)[1]
    first = date(y, m, 1)
    last = date(y, m, ndays)

    detail = _client_detail(db, current_user)

    # Plantillas por día de la semana (la rutina/nutrición se repiten semanalmente)
    routine_tpl = {}   # weekday_idx -> {name, muscles, duration}
    r = db.query(Routine).filter(Routine.user_id == current_user.id).order_by(Routine.id.desc()).first()
    routine_name = r.name if r else None
    if r:
        for idx, rd in enumerate(r.days_list or []):
            if idx > 6:
                break
            routine_tpl[idx] = {
                "name": rd.day_name or f"Día {idx + 1}",
                "muscles": _routine_day_muscles(rd),
                "duration_min": r.time,
            }

    nutri_tpl = {}     # weekday_idx -> {kcal, meals_count} o None
    if detail:
        for idx in range(7):
            nutri_tpl[idx] = _today_menu_summary(db, detail, current_user, idx)

    # Fechas con entreno registrado / check-in dentro del mes
    session_dates, checkin_dates = set(), set()
    tasks_by_date = {}
    if detail:
        session_dates = {s.session_date for s in db.query(WorkoutSession).filter(
            WorkoutSession.client_user_detail_id == detail.id,
            WorkoutSession.session_date >= first, WorkoutSession.session_date <= last,
        ).all()}
        checkin_dates = {c.checkin_date for c in db.query(WeeklyCheckin).filter(
            WeeklyCheckin.client_user_detail_id == detail.id,
            WeeklyCheckin.checkin_date >= first, WeeklyCheckin.checkin_date <= last,
        ).all()}
        # Tareas asignadas por el coach en el calendario del cliente
        from app.models.calendar_task import CalendarTask, COLOR_MAP
        ctasks = db.query(CalendarTask).filter(
            CalendarTask.client_user_detail_id == detail.id,
            CalendarTask.task_date >= first, CalendarTask.task_date <= last,
        ).order_by(CalendarTask.task_date.asc(), CalendarTask.id.asc()).all()
        for t in ctasks:
            tasks_by_date.setdefault(t.task_date, []).append({
                "id": t.id,
                "title": t.title or (t.task_type or "Tarea").capitalize(),
                "task_type": t.task_type,
                "color": t.color or COLOR_MAP.get(t.task_type, "#9CA3AF"),
                "notes": t.notes,
                "done": bool(t.done),
            })

    days = []
    for dnum in range(1, ndays + 1):
        dt = date(y, m, dnum)
        wd = dt.weekday()
        days.append({
            "date": dt.isoformat(),
            "day": dnum,
            "weekday": wd,
            "is_today": dt == today,
            "is_past": dt < today,
            "training": routine_tpl.get(wd),
            "nutrition": nutri_tpl.get(wd) if detail else None,
            "workout_done": dt in session_dates,
            "checkin_done": dt in checkin_dates,
            "tasks": tasks_by_date.get(dt, []),
        })

    prev_m = (m - 1) or 12
    prev_y = y - 1 if m == 1 else y
    next_m = 1 if m == 12 else m + 1
    next_y = y + 1 if m == 12 else y

    return send_response({
        "year": y, "month": m,
        "month_name": _MONTHS_ES[m - 1].capitalize(),
        "first_weekday": first.weekday(),  # 0 = lunes
        "days_in_month": ndays,
        "routine_name": routine_name,
        "prev": {"year": prev_y, "month": prev_m},
        "next": {"year": next_y, "month": next_m},
        "days": days,
    }, "OK")


def _profile_out(db: Session, detail, user: User):
    full = (f"{detail.name or ''} {detail.last_name or ''}").strip() if detail else None
    return {
        "name": detail.name if detail else None,
        "last_name": detail.last_name if detail else None,
        "full_name": full or (getattr(user, "email", None) or "Cliente"),
        "phone": detail.phone if detail else None,
        "email": getattr(user, "email", None),
        "photo": detail.photo if detail else None,
    }


@router.get("/profile", summary="Perfil del cliente", description="Datos de perfil editables del cliente autenticado.")
def client_profile(db: Session = Depends(get_db), current_user: User = Depends(require_role_ids(CLIENT))):
    detail = _client_detail(db, current_user)
    if not detail:
        return send_error("Perfil de cliente no encontrado")
    return send_response(_profile_out(db, detail, current_user), "OK")


class _ClientProfileBody(BaseModel):
    name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    photo: Optional[str] = None


@router.patch("/profile", summary="Actualizar perfil (cliente)", description="El cliente actualiza su propio nombre, apellidos, teléfono y foto de perfil.")
def client_update_profile(body: _ClientProfileBody, db: Session = Depends(get_db), current_user: User = Depends(require_role_ids(CLIENT))):
    detail = _client_detail(db, current_user)
    if not detail:
        return send_error("Perfil de cliente no encontrado")
    if body.name is not None:
        nm = body.name.strip()
        if nm:
            detail.name = nm  # name es obligatorio: no se permite vaciarlo
    if body.last_name is not None:
        detail.last_name = body.last_name.strip() or None
    if body.phone is not None:
        detail.phone = body.phone.strip() or None
    if body.photo is not None:
        detail.photo = body.photo or None
    db.commit()
    db.refresh(detail)
    return send_response(_profile_out(db, detail, current_user), "Perfil actualizado")


@router.get("/routines", summary="Rutinas del cliente", description="Rutinas (planes) asignadas al cliente autenticado, con sus días y ejercicios.")
def client_routines(db: Session = Depends(get_db), current_user: User = Depends(require_role_ids(SUPERADMIN, ADMIN, COACH, CLIENT))):
    # Reutiliza el serializador del panel del coach (mismo formato de días/bloques/ejercicios).
    from app.routers.routines import _serialize as _serialize_routine
    rows = db.query(Routine).filter(
        Routine.user_id == current_user.id
    ).order_by(Routine.id.desc()).all()
    return send_response([_serialize_routine(r) for r in rows], "OK")


@router.get("/chat", summary="Conversación con el coach", description="Devuelve (creándola si no existe) la conversación individual entre el cliente y su coach.")
def client_chat(db: Session = Depends(get_db), current_user: User = Depends(require_role_ids(CLIENT))):
    """Localiza o crea el chat 1:1 del cliente con su coach.

    El cliente no elige con quién habla: siempre es su coach asignado
    (vía user_parents). Reutiliza el modelo de chat existente para que el
    coach vea la misma conversación desde su panel.
    """
    import uuid
    from datetime import datetime
    from app.models.chat import ChatConversation, ChatParticipant

    detail = _client_detail(db, current_user)
    coach_detail = _coach_of(db, detail.id) if detail else None
    if not coach_detail:
        return send_response({"conversation_id": None, "coach": None}, "Sin coach asignado")

    coach_user_id = coach_detail.user_id
    coach_name = (f"{coach_detail.name or ''} {coach_detail.last_name or ''}").strip() or "Tu coach"
    coach_info = {
        "user_id": coach_user_id,
        "name": coach_name,
        "photo": coach_detail.photo,
        "initials": (coach_name.strip()[:1] or "C").upper(),
    }

    # Conversación individual que contenga a ambos.
    my_conv_ids = [
        p.conversation_id for p in
        db.query(ChatParticipant).filter(ChatParticipant.user_id == current_user.id).all()
    ]
    conv = None
    if my_conv_ids:
        candidates = db.query(ChatConversation).filter(
            ChatConversation.id.in_(my_conv_ids),
            ChatConversation.type == "individual",
        ).all()
        for c in candidates:
            uids = {p.user_id for p in c.participants}
            if coach_user_id in uids:
                conv = c
                break

    if conv is None:
        now = datetime.utcnow()
        conv = ChatConversation(
            id=str(uuid.uuid4()), type="individual", name=None,
            created_by_user_id=current_user.id, created_at=now, updated_at=now,
        )
        db.add(conv)
        db.flush()
        db.add(ChatParticipant(conversation_id=conv.id, user_id=current_user.id, joined_at=now))
        db.add(ChatParticipant(conversation_id=conv.id, user_id=coach_user_id, joined_at=now))
        db.commit()
        db.refresh(conv)

    # Si el coach le desactivó el chat, la pantalla tiene que decirlo en vez de
    # enseñar un cuadro de escribir que no lleva a ninguna parte.
    return send_response({
        "conversation_id": conv.id,
        "coach": coach_info,
        "chat_enabled": bool(detail.chat_enabled) if detail else True,
    }, "OK")
