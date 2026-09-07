"""Cargar en el catálogo los ejercicios que entrega el cliente.

La entrega son 132 filas de la biblioteca de Notion que todavía no estaban en
la plataforma, con su descripción, sus músculos, su material y su vídeo. Las
imágenes se suben aparte —`scripts/subir_imagenes_ejercicios.py`— y aquí se
lee el mapa que aquél deja.

Un ejercicio que YA EXISTE con el mismo nombre se actualiza con lo del CSV.
Es lo acordado: la entrega es la versión buena.

Por defecto NO escribe nada: cuenta lo que haría y lo enseña.

    python scripts/cargar_ejercicios.py --inspeccionar   # qué trae el fichero
    python scripts/cargar_ejercicios.py                  # ensayo: cuenta, no escribe
    python scripts/cargar_ejercicios.py --ejecutar
    python scripts/cargar_ejercicios.py --verificar

Antes de `--ejecutar`: copia de seguridad (`python scripts/copia_seguridad.py`).
Esta carga no borra nada, pero la copia es barata.
"""
import argparse
import csv
import json
import os
import re
import sys
import unicodedata

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

CSV_POR_DEFECTO = os.path.join(RAIZ, "datos", "ejercicios-pendientes.csv")
MAPA_POR_DEFECTO = os.path.join(RAIZ, "datos", "ejercicios-imagenes.json")

COLUMNAS = [
    "nombre_ejercicio", "otros_nombres", "tipo_ejercicio",
    "grupo_muscular_principal", "grupo_muscular_secundario", "localizacion",
    "url_video", "descripcion", "imagen", "equipamiento", "nivel",
    "patron_movimiento", "series_recomendadas",
]

# Las etiquetas del cliente y los códigos que guarda la tabla. Se traduce aquí
# y no en la pantalla: en la base ya hay ejercicios con estos códigos, y meter
# "Compuesto" al lado de "compound" partiría los filtros en dos.
TIPOS = {"compuesto": "compound", "aislamiento": "isolation",
         "cardio": "cardio", "movilidad": "mobility"}
LUGARES = {"gimnasio": "gym", "casa": "home", "exterior": "outdoor",
           "aire libre": "outdoor", "ambos": "both"}
NIVELES = {"principiante": 1, "intermedio": 2, "avanzado": 3}

# `trainings.material` es VARCHAR(120). El equipamiento viene como lista y
# alguna fila puede pasarse; se avisa en vez de recortar en silencio.
LARGO_MATERIAL = 120


def _norm(texto):
    """Sin acentos, sin mayúsculas y sin espacios de más.

    Para comparar nombres, no para guardarlos. «Isquiotibiales » y
    «isquiotibiales» son el mismo grupo muscular y sin esto saldrían dos.
    """
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.split()).lower()


def _lista(celda):
    """Los valores de una celda que trae varios separados por «, »."""
    return [p.strip() for p in str(celda or "").split(",") if p.strip()]


# Las recomendaciones vienen en UNA celda de texto libre y la tabla tiene tres
# columnas. Se intenta separarlas; lo que no se entiende se guarda entero en
# `rec_series` en vez de inventar un reparto. La pantalla del cliente lo pinta
# tal cual, así que un texto sin trocear se sigue leyendo bien.
_NUM = r"\d+\s*(?:[-–]\s*\d+)?"
# "4x10" y "3-4 x 8-12": la forma corta, donde ni «series» ni «reps» aparecen.
_POR = re.compile(rf"({_NUM})\s*[x×]\s*({_NUM})", re.I)
_SERIES = re.compile(rf"({_NUM})\s*series?", re.I)
_REPS = re.compile(rf"({_NUM})\s*(?:reps?|repeticiones?)", re.I)
_DESC = re.compile(rf"(?:descanso|rest)\D{{0,4}}({_NUM}\s*(?:s|seg|segundos|min|'|\")?)", re.I)


def _limpia(texto):
    return " ".join(str(texto).split()).replace("–", "-").replace(" -", "-").replace("- ", "-")


def recomendaciones(texto):
    """(series, reps, descanso) de la celda libre. Lo que no se entiende va
    entero en la primera y las otras quedan vacías."""
    t = " ".join(str(texto or "").split())
    if not t:
        return None, None, None
    d = _DESC.search(t)
    descanso = _limpia(d.group(1)) if d else None

    corta = _POR.search(t)
    if corta:
        return _limpia(corta.group(1)), _limpia(corta.group(2)), descanso

    s = _SERIES.search(t)
    r = _REPS.search(t)
    if not s and not r:
        # Ni series ni repeticiones: no hay nada que repartir y repartirlo a
        # ojo le enseñaría al cliente unas cifras que nadie escribió.
        return t[:40], None, None
    return (_limpia(s.group(1)) if s else None,
            _limpia(r.group(1)) if r else None, descanso)


def leer_csv(ruta):
    """Las filas del CSV, como diccionarios.

    `utf-8-sig` porque el fichero lleva BOM —lo abre Excel— y sin eso la
    primera columna se llamaría "﻿nombre_ejercicio" y no la encontraría
    nadie. Y con el módulo `csv`, no partiendo por líneas: la descripción trae
    saltos de línea DENTRO de la celda.
    """
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        faltan = [c for c in COLUMNAS if c not in (lector.fieldnames or [])]
        if faltan:
            raise SystemExit(
                f"Al CSV le faltan columnas: {', '.join(faltan)}\n"
                f"Trae: {', '.join(lector.fieldnames or [])}")
        return [dict(fila) for fila in lector]


def revisar(filas, mapa_imagenes, grupos_conocidos):
    """Qué trae el fichero y qué no se va a poder traducir.

    Se mira ANTES de escribir porque lo que aquí sale como aviso, en la base
    sale como un ejercicio sin grupo muscular que nadie encuentra buscando.
    """
    avisos = {"sin_nombre": [], "grupos_desconocidos": {}, "tipos": set(),
              "lugares": set(), "niveles": set(), "sin_imagen": [],
              "imagen_no_subida": [], "sin_video": [], "material_largo": [],
              "repetidos": [], "rec_sin_trocear": []}
    vistos = {}
    conocidos = {_norm(g) for g in grupos_conocidos}

    for i, fila in enumerate(filas, start=2):     # 2 = primera fila de datos
        nombre = (fila.get("nombre_ejercicio") or "").strip()
        if not nombre:
            avisos["sin_nombre"].append(i)
            continue
        clave = _norm(nombre)
        if clave in vistos:
            avisos["repetidos"].append((nombre, vistos[clave], i))
        else:
            vistos[clave] = i

        for grupo in ([fila.get("grupo_muscular_principal")]
                      + _lista(fila.get("grupo_muscular_secundario"))):
            g = (grupo or "").strip()
            if g and _norm(g) not in conocidos:
                avisos["grupos_desconocidos"].setdefault(g, []).append(nombre)

        tipo = _norm(fila.get("tipo_ejercicio"))
        if tipo and tipo not in TIPOS:
            avisos["tipos"].add(fila.get("tipo_ejercicio"))
        lugar = _norm(fila.get("localizacion"))
        if lugar and lugar not in LUGARES:
            avisos["lugares"].add(fila.get("localizacion"))
        nivel = _norm(fila.get("nivel"))
        if nivel and nivel not in NIVELES:
            avisos["niveles"].add(fila.get("nivel"))

        imagen = (fila.get("imagen") or "").strip()
        if not imagen:
            avisos["sin_imagen"].append(nombre)
        elif imagen not in mapa_imagenes:
            avisos["imagen_no_subida"].append(imagen)
        if not (fila.get("url_video") or "").strip():
            avisos["sin_video"].append(nombre)

        material = ", ".join(_lista(fila.get("equipamiento")))
        if len(material) > LARGO_MATERIAL:
            avisos["material_largo"].append((nombre, len(material)))

        s, r, _d = recomendaciones(fila.get("series_recomendadas"))
        if s and not r:
            avisos["rec_sin_trocear"].append(nombre)

    return avisos


def a_columnas(fila, mapa_imagenes, grupos_por_nombre):
    """La fila del CSV, en los campos de `trainings`.

    Devuelve solo lo que el CSV dice. Un campo vacío en el CSV es vacío aquí:
    la mayoría del catálogo está a medio rellenar y un valor por defecto sería
    una afirmación que nadie ha hecho.
    """
    g = lambda c: (fila.get(c) or "").strip() or None

    principal = grupos_por_nombre.get(_norm(fila.get("grupo_muscular_principal")))
    secundarios = [grupos_por_nombre[_norm(x)]
                   for x in _lista(fila.get("grupo_muscular_secundario"))
                   if _norm(x) in grupos_por_nombre]

    nivel = NIVELES.get(_norm(fila.get("nivel")))
    material = ", ".join(_lista(fila.get("equipamiento")))[:LARGO_MATERIAL] or None
    rec_s, rec_r, rec_d = recomendaciones(fila.get("series_recomendadas"))
    imagen = (fila.get("imagen") or "").strip()

    return {
        "name": (fila.get("nombre_ejercicio") or "").strip(),
        "aliases": g("otros_nombres"),
        "description": g("descripcion"),
        "muscle_group_id": principal,
        "secondary_muscle_group_id": secundarios[0] if secundarios else None,
        "secondary_muscle_group_ids": ",".join(str(i) for i in secundarios) or None,
        "image": mapa_imagenes.get(imagen),
        "video_url": g("url_video"),
        "exercise_type": TIPOS.get(_norm(fila.get("tipo_ejercicio"))),
        "location": LUGARES.get(_norm(fila.get("localizacion"))),
        "material": material,
        "difficulty": nivel,
        "difficulty_levels": str(nivel) if nivel else None,
        "movement_pattern": g("patron_movimiento"),
        "rec_series": rec_s,
        "rec_reps": rec_r,
        "rec_rest": rec_d,
    }


# ── Lo que toca la base ────────────────────────────────────────────────────

def _contra_que_base():
    """Dónde va a escribir esto. Sin DATABASE_URL la aplicación se cae a una
    base local, y alguien podría lanzarlo creyendo que apunta a producción."""
    from app.config import SQLALCHEMY_DATABASE_URL
    url = SQLALCHEMY_DATABASE_URL
    if "@" in url:
        esquema, resto = url.split("://", 1)
        return f"{esquema}://…@{resto.split('@', 1)[1]}"
    return url


def _grupos(db):
    from app.models.muscle_group import MuscleGroup
    filas = db.query(MuscleGroup.id, MuscleGroup.name).all()
    return {_norm(n): i for i, n in filas}, [n for _i, n in filas]


def _pinta_avisos(avisos):
    hay = False
    def bloque(titulo, valores, formato=str):
        nonlocal hay
        if not valores:
            return
        hay = True
        print(f"\n{titulo} ({len(valores)}):")
        for v in list(valores)[:15]:
            print(f"  · {formato(v)}")
        if len(valores) > 15:
            print(f"  … y {len(valores) - 15} más")

    bloque("Filas SIN NOMBRE (se saltan)", avisos["sin_nombre"], lambda i: f"línea {i}")
    bloque("Nombres REPETIDOS dentro del CSV", avisos["repetidos"],
           lambda t: f"{t[0]} (líneas {t[1]} y {t[2]})")
    bloque("Grupos musculares que NO existen en la base", avisos["grupos_desconocidos"],
           lambda g: f"{g} → lo usan {len(avisos['grupos_desconocidos'][g])} ejercicios")
    bloque("Tipos de ejercicio no reconocidos", avisos["tipos"])
    bloque("Localizaciones no reconocidas", avisos["lugares"])
    bloque("Niveles no reconocidos", avisos["niveles"])
    bloque("Sin imagen en el CSV", avisos["sin_imagen"])
    bloque("Imagen del CSV que NO está subida a R2", avisos["imagen_no_subida"])
    bloque("Sin vídeo", avisos["sin_video"])
    bloque("Equipamiento más largo de lo que cabe (se recorta)",
           avisos["material_largo"], lambda t: f"{t[0]} ({t[1]} caracteres)")
    bloque("Recomendación que no se pudo trocear (va entera en «series»)",
           avisos["rec_sin_trocear"])
    if not hay:
        print("\nNada que avisar: el fichero se traduce entero.")
    return hay


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=CSV_POR_DEFECTO)
    ap.add_argument("--imagenes", default=MAPA_POR_DEFECTO,
                    help="El mapa que deja subir_imagenes_ejercicios.py")
    ap.add_argument("--inspeccionar", action="store_true",
                    help="Solo mirar el fichero: qué trae y qué no se traduce")
    ap.add_argument("--ejecutar", action="store_true", help="Escribe de verdad")
    ap.add_argument("--verificar", action="store_true",
                    help="Contar en la base cuántos de estos ejercicios están")
    ap.add_argument("--usuario", type=int, default=None,
                    help="created_user_id de los ejercicios nuevos")
    args = ap.parse_args()

    from app.database import SessionLocal
    from app.models.training import Training

    filas = leer_csv(args.csv)
    mapa = {}
    if os.path.exists(args.imagenes):
        with open(args.imagenes, encoding="utf-8") as f:
            mapa = json.load(f)

    print(f"CSV:      {args.csv}  ({len(filas)} filas)")
    print(f"Imágenes: {args.imagenes}  ({len(mapa)} subidas)")
    print(f"Base:     {_contra_que_base()}")

    db = SessionLocal()
    try:
        por_nombre, nombres = _grupos(db)

        if args.verificar:
            del_csv = {_norm(f.get("nombre_ejercicio")) for f in filas
                       if (f.get("nombre_ejercicio") or "").strip()}
            en_base = {_norm(n) for (n,) in db.query(Training.name).all()}
            estan = del_csv & en_base
            print(f"\nDe los {len(del_csv)} del CSV, en la base hay {len(estan)}.")
            faltan = sorted(del_csv - en_base)
            for n in faltan[:15]:
                print(f"  falta: {n}")
            con_imagen = db.query(Training).filter(
                Training.image.isnot(None),
                Training.name.in_([f["nombre_ejercicio"].strip() for f in filas
                                   if (f.get("nombre_ejercicio") or "").strip()])).count()
            print(f"Con imagen puesta: {con_imagen}")
            return

        avisos = _pinta_avisos(revisar(filas, mapa, nombres))
        if args.inspeccionar:
            return

        # Qué existe ya, por nombre normalizado.
        existentes = {}
        for t in db.query(Training).all():
            existentes.setdefault(_norm(t.name), t)

        nuevos = actualizados = 0
        for fila in filas:
            nombre = (fila.get("nombre_ejercicio") or "").strip()
            if not nombre:
                continue
            datos = a_columnas(fila, mapa, por_nombre)
            ya = existentes.get(_norm(nombre))
            if ya:
                actualizados += 1
                if args.ejecutar:
                    for campo, valor in datos.items():
                        setattr(ya, campo, valor)
            else:
                nuevos += 1
                if args.ejecutar:
                    t = Training(**datos, state=1, created_user_id=args.usuario)
                    db.add(t)
                    existentes[_norm(nombre)] = t

        print(f"\nNuevos:       {nuevos}")
        print(f"Actualizados: {actualizados}   (mismo nombre: manda el CSV)")

        if not args.ejecutar:
            print("\nEnsayo: no se ha escrito nada.")
            if avisos:
                print("Mira los avisos de arriba antes de seguir.")
            print("Cuando los números cuadren: copia de seguridad y --ejecutar.")
            return

        db.commit()
        print("\nHecho.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
