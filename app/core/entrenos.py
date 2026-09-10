"""Las cuentas del historial de entrenos.

Aquí vive lo que la pantalla de Sesiones necesita saber y no está guardado tal
cual: el tonelaje, el estado de cada sesión y qué se programó frente a qué se
hizo. Se calcula en un solo sitio porque son cuentas con filo — cada una tiene
una forma obvia de hacerse mal.

Lo que se decidió con el cliente:

  · Lo PROGRAMADO sale de su calendario (tareas de tipo `rutina`). Es lo que el
    coach planificó de verdad; deducirlo de "días por semana × semanas" sería
    una estimación que no sabe de vacaciones ni de cambios de plan.
  · Una sesión SALTADA no existe en la base: es un día programado sin sesión
    registrada. Se construye al leer, no se guarda.
"""
import re
from datetime import date, timedelta

# Una serie de 40 segundos no son 40 repeticiones. Si se colara, el tonelaje de
# una plancha de 40s con 20 kg saldría como 800 kg de una sentada.
_TIEMPO = re.compile(r"\d\s*(s|seg|segs|segundos|min|m|'|\")\b", re.I)
_PRIMER_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")


def repeticiones(texto):
    """Las repeticiones de una serie, del texto que escribió el cliente.

    Admite "8", "8-10", "10 reps". De un rango se coge el PRIMERO: es lo que
    de verdad marcó como hecho, y quedarse con el mayor infla el tonelaje.
    Devuelve None cuando no son repeticiones (una serie por tiempo).
    """
    t = str(texto or "").strip()
    if not t or _TIEMPO.search(t):
        return None
    m = _PRIMER_NUMERO.search(t)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def tonelaje(sesion):
    """Kilos levantados: peso × repeticiones, sumando SOLO las series hechas.

    Contar las no marcadas diría que el cliente levantó lo que dejó a medias, y
    justo en las sesiones parciales —donde más importa— sería lo más falso.
    """
    total = 0.0
    for ex in (sesion.exercises or []):
        for st in (ex.sets or []):
            if not st.done or st.weight is None:
                continue
            reps = repeticiones(st.reps)
            if reps:
                total += float(st.weight) * reps
    return round(total, 1)


def series(sesion):
    """(hechas, registradas) de una sesión."""
    todas = [st for ex in (sesion.exercises or []) for st in (ex.sets or [])]
    return sum(1 for st in todas if st.done), len(todas)


def estado(hechas, previstas):
    """Completada, parcial o saltada.

    `previstas` es lo que el coach dejó puesto en la rutina de ese día; cuando
    no se sabe, se usan las registradas, y entonces "completada" significa que
    marcó todo lo que apuntó.
    """
    if not previstas:
        return "completada" if hechas else "saltada"
    if hechas <= 0:
        return "saltada"
    return "completada" if hechas >= previstas else "parcial"


def semana_del_programa(dia, inicio):
    """En qué semana del programa cae esa fecha. La primera es la 1."""
    if not dia or not inicio:
        return None
    dias = (dia - inicio).days
    if dias < 0:
        return None
    return dias // 7 + 1


def racha_semanas(fechas, hoy=None):
    """Semanas seguidas, hasta hoy, con al menos un entreno.

    Se cuenta hacia atrás desde la semana en curso. La semana actual no rompe
    la racha si aún no se ha entrenado: es miércoles, quedan días.
    """
    if not fechas:
        return 0
    hoy = hoy or date.today()
    lunes_actual = hoy - timedelta(days=hoy.weekday())
    con_entreno = {f - timedelta(days=f.weekday()) for f in fechas if f}

    racha = 0
    semana = lunes_actual
    if semana not in con_entreno:
        semana -= timedelta(days=7)      # la semana en curso aún puede llenarse
    while semana in con_entreno:
        racha += 1
        semana -= timedelta(days=7)
    return racha


# ── Fuerza: lo que se calcula por ejercicio ────────────────────────────────

def rm_estimado(peso, reps):
    """1RM estimado por la fórmula de Epley: peso × (1 + reps/30).

    Es la que cuadra con los números del prototipo del cliente —77,5 kg a 6
    repeticiones dan 93 kg, y así en las seis filas—, así que es la que se usa
    y no otra: dos fórmulas distintas dan cifras distintas para el mismo
    levantamiento, y el coach compara con lo que ya tenía anotado.

    Una serie por tiempo no tiene 1RM: devuelve None.
    """
    if peso is None or not reps:
        return None
    try:
        return round(float(peso) * (1 + float(reps) / 30), 1)
    except (TypeError, ValueError):
        return None


def rir_de_rpe(rpe):
    """Repeticiones en recámara, del esfuerzo percibido: RIR = 10 − RPE.

    No es un dato aparte: el cliente marca RPE al entrenar y son dos formas de
    decir lo mismo. Un RPE de 8,5 son 1,5 repeticiones en recámara, que es
    justo el "RIR promedio" del prototipo.
    """
    if rpe is None:
        return None
    try:
        return round(max(0.0, 10 - float(rpe)), 1)
    except (TypeError, ValueError):
        return None


def es_por_tiempo(sets):
    """Si el ejercicio se mide en segundos y no en repeticiones.

    Una plancha no tiene peso top ni 1RM; enseñarle "0 kg" al coach sería
    decirle que el cliente no levantó nada, cuando lo que pasa es que ahí no
    se levanta.
    """
    marcadas = [s for s in (sets or []) if s.done]
    if not marcadas:
        return False
    return all(repeticiones(s.reps) is None for s in marcadas)


def segundos(texto):
    """Los segundos de una serie por tiempo: "40s" -> 40, "1 min" -> 60."""
    t = str(texto or "").strip().lower()
    if not t:
        return None
    m = _PRIMER_NUMERO.search(t)
    if not m:
        return None
    try:
        n = float(m.group(0).replace(",", "."))
    except ValueError:
        return None
    if re.search(r"\d\s*(min|m|')", t):
        return n * 60
    return n


def mmss(total):
    """135 segundos -> "2:15", que es como se lee un tiempo."""
    if total is None:
        return None
    total = int(round(total))
    return f"{total // 60}:{total % 60:02d}"


# ── Récords: la mejor marca de un ejercicio ────────────────────────────────

def mejor_marca(sets):
    """El mejor 1RM estimado de un ejercicio, de sus series MARCADAS.

    Se compara por 1RM y no por el peso a secas porque 80 kg × 8 es más que
    100 kg × 1, y decirle al cliente que ha bajado cuando ha subido es peor que
    no decirle nada. Una serie por tiempo —una plancha— no tiene 1RM y no
    cuenta: devuelve None si no queda ninguna serie con peso y repeticiones.
    """
    marcas = []
    for st in (sets or []):
        if not getattr(st, "done", False):
            continue
        rm = rm_estimado(getattr(st, "weight", None), repeticiones(getattr(st, "reps", None)))
        if rm is not None:
            marcas.append(rm)
    return max(marcas) if marcas else None


def clave_ejercicio(nombre):
    """Con qué nombre se agrupa un ejercicio en el historial.

    El cliente escribe «Press banca» y «press  Banca» la semana que viene. Sin
    normalizar, la segunda no encuentra su historia y sale como récord siempre.
    """
    return " ".join(str(nombre or "").split()).lower()


def records_de(ejercicios, marcas_previas):
    """Qué ejercicios de esta sesión superan lo mejor que había antes.

    `marcas_previas` es {clave: 1RM} del historial del cliente. Un ejercicio
    que NUNCA se había hecho cuenta como récord: es la primera marca, y es lo
    que espera quien lo acaba de levantar. Empatar no es superar.
    """
    hechos = []
    for ex in (ejercicios or []):
        marca = mejor_marca(getattr(ex, "sets", None))
        if marca is None:
            continue
        clave = clave_ejercicio(getattr(ex, "name", None))
        if not clave:
            continue
        previa = marcas_previas.get(clave)
        if previa is None or marca > previa:
            hechos.append({"name": getattr(ex, "name", None), "rm1": marca, "previo": previa})
    return hechos


# ── Un ejercicio, sesión a sesión ──────────────────────────────────────────
#
# Esto lo calculaba la vista de Fuerza del coach dentro de su propio bucle. El
# cliente necesita exactamente lo mismo para su ficha del ejercicio —récords y
# evolución de carga—, y escribirlo dos veces es cómo acaban dos pantallas
# diciendo cifras distintas del mismo levantamiento. Vive aquí y lo usan los
# dos.

def fila_de_sesion(ex, sesion, descanso_s=None):
    """Qué dice UNA sesión de UN ejercicio, o None si no hay nada que decir.

    Un ejercicio por tiempo —una plancha— no tiene peso top ni 1RM: enseñar
    "0 kg" sería decir que no levantó nada, cuando lo que pasa es que ahí no
    se levanta.
    """
    marcadas = [st for st in (getattr(ex, "sets", None) or []) if st.done]
    if not marcadas:
        return None

    por_tiempo = es_por_tiempo(ex.sets)
    if por_tiempo:
        mejor = max((segundos(st.reps) or 0) for st in marcadas)
        fila = {"peso_top": None, "reps_top": None, "rm1": None,
                "volumen": None, "segundos": mejor, "tiempo": mmss(mejor)}
    else:
        # El peso top es el más pesado que MOVIÓ; las repeticiones que se
        # enseñan son las de esa serie, no las de la más larga: son las dos
        # cifras del mismo levantamiento.
        con_peso = [st for st in marcadas if st.weight is not None]
        if not con_peso:
            return None
        top = max(con_peso, key=lambda st: float(st.weight))
        reps_top = repeticiones(top.reps)
        vol = sum(float(st.weight) * (repeticiones(st.reps) or 0) for st in con_peso)
        fila = {
            "peso_top": round(float(top.weight), 1),
            "reps_top": int(reps_top) if reps_top else None,
            "rm1": rm_estimado(top.weight, reps_top),
            "volumen": round(vol, 1),
            "segundos": None, "tiempo": None,
        }

    rpes = [st.rpe for st in marcadas if st.rpe is not None]
    fila.update({
        "fecha": sesion.session_date.isoformat() if sesion.session_date else None,
        "series": len(marcadas),
        "rir": rir_de_rpe(sum(rpes) / len(rpes)) if rpes else None,
        "descanso_s": descanso_s,
        "detalle": [{
            "serie": st.set_number,
            "reps": st.reps,
            "peso": st.weight,
            "rpe": st.rpe,
        } for st in sorted(marcadas, key=lambda x: x.set_number or 0)],
    })
    return fila


def records_de_ejercicio(filas):
    """Los máximos históricos de un ejercicio, de sus filas por sesión.

    Vacío es vacío: un ejercicio que solo se ha hecho por tiempo no tiene
    récord de peso, y un 0 ahí se leería como un dato.
    """
    pesos = [f["peso_top"] for f in filas if f.get("peso_top") is not None]
    rms = [f["rm1"] for f in filas if f.get("rm1") is not None]
    vols = [f["volumen"] for f in filas if f.get("volumen") is not None]
    tiempos = [f["segundos"] for f in filas if f.get("segundos") is not None]
    return {
        "mayor_peso": max(pesos) if pesos else None,
        "mejor_rm1": max(rms) if rms else None,
        "mejor_volumen": max(vols) if vols else None,
        "mejor_tiempo_s": max(tiempos) if tiempos else None,
    }
