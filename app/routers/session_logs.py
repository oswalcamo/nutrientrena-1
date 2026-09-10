from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

from app.database import get_db
from app.core.dependencies import require_role_ids, SUPERADMIN, ADMIN, COACH
from app.core.responses import send_response, send_error
from app.models.session_log import WorkoutSession

router = APIRouter(prefix="/session-logs", tags=["Session Logs"])


class SessionCreate(BaseModel):
    client_user_detail_id: str
    routine_id: Optional[int] = None
    session_date: date
    duration_min: Optional[int] = None
    rpe: Optional[float] = None
    mood: Optional[int] = None
    notes: Optional[str] = None


class SessionUpdate(BaseModel):
    routine_id: Optional[int] = None
    session_date: Optional[date] = None
    duration_min: Optional[int] = None
    rpe: Optional[float] = None
    mood: Optional[int] = None
    notes: Optional[str] = None


def _out(s: WorkoutSession) -> dict:
    # Detalle registrado por el cliente (ejercicios con sus series)
    exercises = []
    for ex in (s.exercises or []):
        exercises.append({
            "id": ex.id,
            "training_id": ex.training_id,
            "name": ex.name,
            "muscle_group_name": ex.muscle_group_name,
            "notes": ex.notes,
            "sets": [{
                "set_number": st.set_number,
                "reps": st.reps,
                "weight": st.weight,
                "rpe": st.rpe,
                "done": bool(st.done),
            } for st in (ex.sets or [])],
        })
    return {
        "id": s.id,
        "client_user_detail_id": s.client_user_detail_id,
        "routine_id": s.routine_id,
        "routine_name": s.routine.name if s.routine else None,
        "session_date": s.session_date.isoformat() if s.session_date else None,
        "day_name": s.day_name,
        "duration_min": s.duration_min,
        "rpe": s.rpe,
        "energy": s.energy,
        "mood": s.mood,
        "notes": s.notes,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "exercises": exercises,
        "exercise_count": len(exercises),
        "set_count": sum(len(e["sets"]) for e in exercises),
    }


@router.get("/client/{client_user_detail_id}", summary="Sesiones del cliente", description="Retorna el historial de sesiones de entrenamiento de un cliente.")
def list_sessions(
    client_user_detail_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH)),
):
    sessions = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.client_user_detail_id == client_user_detail_id)
        .order_by(WorkoutSession.session_date.desc())
        .all()
    )
    return send_response([_out(s) for s in sessions], "OK")


@router.post("", summary="Registrar sesión", description="Registra una nueva sesión de entrenamiento completada por el cliente.")
def create_session(
    data: SessionCreate,
    db: Session = Depends(get_db),
    _=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH)),
):
    s = WorkoutSession(**data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return send_response(_out(s), "Sesión registrada")


@router.put("/{id}", summary="Actualizar sesión", description="Modifica los datos de una sesión de entrenamiento registrada.")
def update_session(
    id: int,
    data: SessionUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH)),
):
    s = db.query(WorkoutSession).filter(WorkoutSession.id == id).first()
    if not s:
        return send_error("Sesión no encontrada")
    for f, v in data.model_dump(exclude_unset=True).items():
        setattr(s, f, v)
    db.commit()
    db.refresh(s)
    return send_response(_out(s), "Sesión actualizada")


@router.delete("/{id}", summary="Eliminar sesión", description="Elimina un registro de sesión de entrenamiento.")
def delete_session(
    id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH)),
):
    s = db.query(WorkoutSession).filter(WorkoutSession.id == id).first()
    if not s:
        return send_error("Sesión no encontrada")
    db.delete(s)
    db.commit()
    return send_response(None, "Sesión eliminada")


# ── La pantalla de Sesiones del coach ──────────────────────────────────────
#
# Una sola llamada con todo lo que esa pantalla enseña: las cinco cifras de
# arriba, el volumen por semana y la tabla. Se calcula aquí y no en el
# navegador porque hay que cruzar las sesiones con el CALENDARIO —lo que el
# coach programó— para saber qué se saltó, y eso son dos consultas que no
# tiene sentido resolver a base de peticiones sueltas.

@router.get("/client/{client_user_detail_id}/historial",
            summary="Historial de sesiones con sus cifras",
            description="Sesiones registradas y días programados sin registrar, con tonelaje, adherencia y volumen por semana.")
def historial(
    client_user_detail_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH)),
):
    import json as _json

    from app.core.entrenos import (
        estado as _estado, racha_semanas, semana_del_programa, series, tonelaje,
    )
    from app.models.calendar_task import CalendarTask
    from app.models.routine import Routine, RoutineDay
    from app.models.user import UserDetail

    detalle = db.query(UserDetail).filter(UserDetail.id == client_user_detail_id).first()
    if not detalle:
        return send_error("Cliente no encontrado", code=404)
    # `start_date` se guarda como fecha y hora; las sesiones, como fecha suelta.
    # Restarlas sin igualar el tipo revienta con "can't subtract datetime from
    # date", y justo en el cliente que sí tiene fecha de inicio.
    inicio = getattr(detalle, "start_date", None)
    if isinstance(inicio, datetime):
        inicio = inicio.date()

    sesiones = (db.query(WorkoutSession)
                .filter(WorkoutSession.client_user_detail_id == client_user_detail_id)
                .order_by(WorkoutSession.session_date.desc(), WorkoutSession.id.desc())
                .all())

    # Lo PROGRAMADO: las tareas de rutina de su calendario.
    tareas = (db.query(CalendarTask)
              .filter(CalendarTask.client_user_detail_id == client_user_detail_id,
                      CalendarTask.task_type == "rutina")
              .order_by(CalendarTask.task_date.desc())
              .all())

    # Cuántas series lleva cada día de rutina: es contra eso que una sesión
    # está completa o a medias. Sin este dato, "completada" solo diría que el
    # cliente marcó todo lo que él mismo apuntó.
    previstas_por_dia = {}
    for rid, did, nombre, desc in db.query(
            RoutineDay.routine_id, RoutineDay.id, RoutineDay.day_name, RoutineDay.description).all():
        previstas_por_dia[did] = {"routine_id": rid, "nombre": nombre, "desc": desc}

    def _nombre_dia(t):
        """Lo que se lee en la columna SESIÓN: "Día 4" y su enfoque."""
        try:
            req = _json.loads(t.requirements) if t and t.requirements else {}
        except Exception:
            req = {}
        did = (req or {}).get("routine_day_id") if isinstance(req, dict) else None
        d = previstas_por_dia.get(did) if did else None
        if d:
            return d["nombre"], d["desc"]
        return (t.title if t else None), None

    # Un día con sesión registrada no es un día saltado.
    dias_con_sesion = {s.session_date for s in sesiones if s.session_date}

    filas = []
    for s in sesiones:
        hechas, registradas = series(s)
        # El día concreto si se guardó; si no, la rutina. Lo segundo repite
        # el mismo texto en todas las filas, pero es mejor que "Entreno".
        nombre = s.day_name or (s.routine.name if s.routine else None)
        filas.append({
            "id": s.id,
            "fecha": s.session_date.isoformat() if s.session_date else None,
            "semana": semana_del_programa(s.session_date, inicio),
            "hora": s.created_at.strftime("%H:%M") if s.created_at else None,
            "sesion": nombre or "Entreno",
            "enfoque": ", ".join(sorted({e.muscle_group_name for e in (s.exercises or [])
                                         if e.muscle_group_name})) or None,
            "estado": _estado(hechas, registradas),
            "duracion_min": s.duration_min,
            "series_hechas": hechas,
            "series_previstas": registradas,
            "tonelaje": tonelaje(s),
            "rpe": s.rpe,
            "energy": s.energy,
            "mood": s.mood,
            "registrada": True,
        })

    # Y los días que se programaron y no se registraron: las saltadas.
    for t in tareas:
        if t.task_date in dias_con_sesion:
            continue
        if t.task_date > date.today():
            continue          # lo que aún no ha llegado no está saltado
        nombre, enfoque = _nombre_dia(t)
        filas.append({
            "id": None,
            "fecha": t.task_date.isoformat(),
            "semana": semana_del_programa(t.task_date, inicio),
            "hora": None,
            "sesion": nombre or "Entreno",
            "enfoque": enfoque,
            "estado": "saltada",
            "duracion_min": None,
            "series_hechas": 0,
            "series_previstas": None,
            "tonelaje": None,
            "rpe": None,
            "energy": None,
            "mood": None,
            "registrada": False,
        })

    filas.sort(key=lambda f: f["fecha"] or "", reverse=True)

    hechas_n = len([f for f in filas if f["estado"] != "saltada"])
    programadas = len(filas)
    saltadas = programadas - hechas_n
    duraciones = [f["duracion_min"] for f in filas if f["duracion_min"]]
    rpes = [f["rpe"] for f in filas if f["rpe"] is not None]

    # Volumen por semana del programa. Sin fecha de inicio no hay semanas del
    # programa que valgan, y se dice en vez de inventarse una.
    volumen = []
    if inicio:
        por_semana = {}
        for f in filas:
            if f["semana"] and f["tonelaje"]:
                por_semana[f["semana"]] = por_semana.get(f["semana"], 0) + f["tonelaje"]
        if por_semana:
            volumen = [{"semana": n, "tonelaje": round(por_semana.get(n, 0), 1)}
                       for n in range(1, max(por_semana) + 1)]

    return send_response({
        "inicio": inicio.isoformat() if inicio else None,
        "resumen": {
            "sesiones": hechas_n,
            "programadas": programadas,
            "saltadas": saltadas,
            # Sin nada programado no hay adherencia que calcular: 100% con cero
            # sesiones sería una nota excelente por no haber hecho nada.
            "adherencia": round(hechas_n * 100 / programadas) if programadas else None,
            "duracion_media": round(sum(duraciones) / len(duraciones)) if duraciones else None,
            "tonelaje_total": round(sum(f["tonelaje"] or 0 for f in filas), 1),
            "rpe_medio": round(sum(rpes) / len(rpes), 1) if rpes else None,
            "racha_semanas": racha_semanas([s.session_date for s in sesiones]),
        },
        "volumen_semanal": volumen,
        "sesiones": filas,
    }, "OK")


# ── Progreso · Fuerza ──────────────────────────────────────────────────────
#
# Un renglón por ejercicio y sesión, con todo lo que la pantalla puede pedir:
# peso top, 1RM estimado, volumen, repeticiones y RIR. Se devuelven las CINCO
# métricas juntas y no la elegida, porque cambiar de métrica en la pantalla no
# debería costar una ida y vuelta al servidor: son los mismos datos mirados de
# otra forma.

@router.get("/client/{client_user_detail_id}/fuerza",
            summary="Progreso de fuerza por ejercicio",
            description="Historial por ejercicio: peso top, 1RM estimado, volumen, repeticiones y RIR de cada sesión.")
def fuerza(
    client_user_detail_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_role_ids(SUPERADMIN, ADMIN, COACH)),
):
    from app.core.entrenos import (
        es_por_tiempo, fila_de_sesion, mmss, repeticiones, rir_de_rpe,
        rm_estimado, segundos,
    )
    from app.models.routine import RoutineDayDetail
    from app.models.session_log import WorkoutSessionExercise
    from app.models.user import UserDetail

    if not db.query(UserDetail).filter(UserDetail.id == client_user_detail_id).first():
        return send_error("Cliente no encontrado", code=404)

    sesiones = (db.query(WorkoutSession)
                .filter(WorkoutSession.client_user_detail_id == client_user_detail_id)
                .order_by(WorkoutSession.session_date.asc())
                .all())

    # El descanso PRESCRITO, el que el coach puso al montar la rutina. No es lo
    # que el cliente descansó de verdad —eso no se mide— y la pantalla lo dice.
    descansos = {}
    for tid, seg in db.query(RoutineDayDetail.training_id, RoutineDayDetail.break_time)\
            .filter(RoutineDayDetail.training_id.isnot(None),
                    RoutineDayDetail.break_time.isnot(None)).all():
        descansos.setdefault(tid, seg)

    por_ejercicio = {}
    for s in sesiones:
        for ex in (s.exercises or []):
            nombre = (ex.name or "").strip()
            if not nombre:
                continue
            marcadas = [st for st in (ex.sets or []) if st.done]
            if not marcadas:
                continue

            # El cálculo vive en core/entrenos: el cliente lo necesita igual
            # para su ficha del ejercicio, y escribirlo dos veces es cómo
            # acaban dos pantallas diciendo cifras distintas del mismo
            # levantamiento.
            fila = fila_de_sesion(ex, s, descansos.get(ex.training_id))
            if fila is None:
                continue

            clave = nombre.lower()
            e = por_ejercicio.setdefault(clave, {
                "nombre": nombre,
                "grupo": ex.muscle_group_name,
                "tipo": "tiempo" if es_por_tiempo(ex.sets) else "peso_reps",
                "sesiones": [],
            })
            e["sesiones"].append(fila)

    salida = []
    for e in por_ejercicio.values():
        fs = e["sesiones"]
        if not fs:
            continue
        pesos = [f["peso_top"] for f in fs if f["peso_top"] is not None]
        rms = [f["rm1"] for f in fs if f["rm1"] is not None]
        reps = [f["reps_top"] for f in fs if f["reps_top"] is not None]
        rirs = [f["rir"] for f in fs if f["rir"] is not None]
        tiempos = [f["segundos"] for f in fs if f["segundos"] is not None]
        salida.append({
            **e,
            "n_sesiones": len(fs),
            "pr_peso": max(pesos) if pesos else None,
            "rm1_max": max(rms) if rms else None,
            "reps_max": max(reps) if reps else None,
            "volumen_ultimo": fs[-1]["volumen"],
            "rir_medio": round(sum(rirs) / len(rirs), 1) if rirs else None,
            "mejor_tiempo": max(tiempos) if tiempos else None,
        })

    # Los que más veces se han entrenado, primero: son los que el coach mira.
    salida.sort(key=lambda e: (-e["n_sesiones"], e["nombre"]))
    return send_response({"ejercicios": salida}, "OK")
