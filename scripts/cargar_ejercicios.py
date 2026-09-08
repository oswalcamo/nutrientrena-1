"""Cargar en el catálogo los ejercicios que entrega el cliente.

La entrega son 132 filas de la biblioteca de Notion que todavía no estaban en
la plataforma, con su descripción, sus músculos, su material y su vídeo. Las
130 imágenes ya están en R2 con su nombre de archivo, así que la URL de cada
una sale de `BASE_IMAGENES` más ese nombre.

Antes de cargar conviene `--comprobar-imagenes`: pregunta a R2 por las 130 y
dice cuáles no están. Es lo único que distingue una imagen que falta de una
que se subió con otro nombre, y las dos acaban igual — un hueco en la ficha.

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

CSV_POR_DEFECTO = os.path.join(RAIZ, "datos", "ejercicios_pendientes_alzum.csv")
MAPA_POR_DEFECTO = os.path.join(RAIZ, "datos", "ejercicios-imagenes.json")

# Dónde quedaron las imágenes de esta entrega. Se subieron a R2 conservando el
# nombre de archivo del CSV, así que la URL de cada una es esta base más el
# nombre y no hace falta ningún mapa. Se deja escrito aquí —y no en el
# ordenador de quien lance el script— porque ES la ruta de lo que hay en
# producción: con la base a mano, la carga da un resultado distinto según quién
# la lance y nadie sabe después qué se cargó.
BASE_IMAGENES = "https://pub-397ed3b6f1d1480d8c17d960513a3c78.r2.dev/imagenes-ejercicios/"

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

# Lo que cabe en cada columna de `trainings`. Se comprueba ANTES de escribir:
# un recorte silencioso deja media frase con pinta de dato bueno, y nadie mira
# 132 filas a mano para descubrir cuál se quedó a la mitad.
LARGOS = {"name": 255, "material": 120, "movement_pattern": 255,
          "rec_series": 120, "rec_reps": 120, "rec_rest": 120,
          "video_url": 500, "image": 500, "difficulty_levels": 100}
LARGO_MATERIAL = LARGOS["material"]


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
_NUM = r"\d+(?:\s*[-–]\s*\d+)?"
# El descanso va al final, y en el fichero viene con el número DELANTE:
# «…, 60 seg de descanso». La otra forma —«…, descanso 90s»— no está en esta
# entrega pero es la que teclea cualquiera, y sin ella se quedaría pegada a
# las repeticiones: «8-12, descanso 90s».
_DESCANSO = re.compile(
    rf",\s*(?:({_NUM}[^,]*?)\s+de\s+descanso|descanso\s*:?\s*([^,]+?))\s*$", re.I)
# «4x10» y «3-4 x 8-12»: la forma corta, sin las palabras.
_POR = re.compile(rf"^({_NUM})\s*[x×]\s*({_NUM})$", re.I)
# «3 series de …», «8-10 rondas de …», «6-8 sprints de …»: una cantidad, su
# unidad, y detrás lo que se hace en cada una.
_CABEZA = re.compile(rf"^({_NUM})\s*(series?|rondas?|sprints?|vueltas?)?\s+de\s+(.+)$", re.I)
# «10 repeticiones», «8-10 repeticiones por lado»: la palabra sobra —la columna
# ya se llama reps— pero lo que va detrás no.
# El orden importa: con `reps?` delante, «repeticiones» casa como «rep» y deja
# «eticiones» pegado a la cifra. La alternativa larga va primero.
_REPS = re.compile(rf"^({_NUM})\s*(?:repeticiones?|reps?)\s*(.*)$", re.I)


def _limpia(texto):
    t = " ".join(str(texto or "").split()).replace("–", "-")
    return re.sub(r"\s*-\s*", "-", t)


def recomendaciones(texto):
    """(series, reps, descanso) de la celda de texto libre.

    El fichero trae trece formas distintas y casi todas siguen el mismo molde:
    «3 series de 10 repeticiones, 60 seg de descanso». Se separa por ese molde
    y se conserva LO QUE NO ES RUIDO: «por lado», «lentas» o «de trabajo»
    cambian el ejercicio y se quedan pegadas a su cifra.

    Lo que no encaja —«Continuo: 20-30 min a ritmo constante»— se guarda
    entero. Repartirlo a ojo le enseñaría al cliente unas cifras que nadie
    escribió.
    """
    t = " ".join(str(texto or "").split())
    if not t:
        return None, None, None

    descanso = None
    m = _DESCANSO.search(t)
    if m:
        descanso = _limpia(m.group(1) or m.group(2))
        t = t[:m.start()].strip()

    corto = _POR.match(t)
    if corto:
        return _limpia(corto.group(1)), _limpia(corto.group(2)), descanso

    cabeza = _CABEZA.match(t)
    if not cabeza:
        # Ni cantidad ni unidad: no hay molde que aplicar.
        return t, None, descanso

    cifra, unidad, resto = cabeza.groups()
    # «3 series» → «3», que la columna ya se llama series. «8-10 rondas» y
    # «6-8 sprints» conservan la palabra: no son lo mismo y el cliente lo lee.
    series = _limpia(cifra) if (unidad or "").lower().startswith("serie") \
        else _limpia(f"{cifra} {unidad}" if unidad else cifra)

    reps = _REPS.match(resto.strip())
    if reps:
        cola = reps.group(2).strip()
        return series, _limpia(f"{reps.group(1)} {cola}" if cola else reps.group(1)), descanso
    return series, _limpia(resto), descanso


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


def url_de_imagen(nombre, mapa=None, base=BASE_IMAGENES):
    """La URL pública de la imagen que nombra el CSV.

    Una sola regla, en un solo sitio: si alguien la subió con otro nombre está
    en el mapa y manda el mapa; si no, la imagen conserva su nombre y cuelga de
    la base. Sin nombre en el CSV no hay imagen — son dos ejercicios de la
    entrega que todavía no la tienen, y un hueco es un hueco.
    """
    nombre = (nombre or "").strip()
    if not nombre:
        return None
    if mapa and nombre in mapa:
        return mapa[nombre]
    if not base:
        return None
    return base.rstrip("/") + "/" + nombre


def revisar(filas, mapa_imagenes, grupos_conocidos):
    """Qué trae el fichero y qué no se va a poder traducir.

    Se mira ANTES de escribir porque lo que aquí sale como aviso, en la base
    sale como un ejercicio sin grupo muscular que nadie encuentra buscando.
    """
    avisos = {"sin_nombre": [], "grupos_desconocidos": {}, "tipos": set(),
              "lugares": set(), "niveles": set(), "sin_imagen": [],
              "sin_video": [], "no_cabe": [],
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

        # Que el CSV nombre una imagen no quiere decir que esté subida: eso
        # solo lo sabe R2, y se pregunta con --comprobar-imagenes.
        if not (fila.get("imagen") or "").strip():
            avisos["sin_imagen"].append(nombre)
        if not (fila.get("url_video") or "").strip():
            avisos["sin_video"].append(nombre)

        # Lo que no cabe se dice por su nombre y por su columna: recortar deja
        # media frase con pinta de dato bueno.
        for campo, valor in a_columnas(fila, mapa_imagenes, {}).items():
            tope = LARGOS.get(campo)
            if tope and isinstance(valor, str) and len(valor) > tope:
                avisos["no_cabe"].append((nombre, campo, len(valor), tope))

        s, r, _d = recomendaciones(fila.get("series_recomendadas"))
        if s and not r and not _d:
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
    material = ", ".join(_lista(fila.get("equipamiento"))) or None
    rec_s, rec_r, rec_d = recomendaciones(fila.get("series_recomendadas"))
    imagen = (fila.get("imagen") or "").strip()

    return {
        "name": (fila.get("nombre_ejercicio") or "").strip(),
        "aliases": g("otros_nombres"),
        "description": g("descripcion"),
        "muscle_group_id": principal,
        "secondary_muscle_group_id": secundarios[0] if secundarios else None,
        "secondary_muscle_group_ids": ",".join(str(i) for i in secundarios) or None,
        "image": url_de_imagen(imagen, mapa_imagenes),
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
    bloque("Sin vídeo", avisos["sin_video"])
    bloque("NO CABE en su columna (hay que arreglarlo antes de cargar)",
           avisos["no_cabe"],
           lambda t: f"{t[0]}: {t[1]} tiene {t[2]} caracteres y caben {t[3]}")
    bloque("Recomendación que no se pudo trocear (va entera en «series»)",
           avisos["rec_sin_trocear"])
    if not hay:
        print("\nNada que avisar: el fichero se traduce entero.")
    return hay


# Cloudflare está delante de r2.dev y contesta 403 a lo que no parece un
# navegador: con `Python-urllib/3.11` fallaban las 130 aunque estuvieran todas.
# El navegador del cliente sí las va a poder cargar, así que hay que preguntar
# como pregunta él.
_COMO_UN_NAVEGADOR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
}


def _estado_de(url):
    """El código que devuelve pedir esa imagen, o el motivo si no hubo respuesta.

    Prueba con HEAD, que no descarga el fichero. Si lo rechazan —hay servidores
    que solo admiten GET— repite pidiendo el primer byte: sirve igual para
    saber si está y sigue sin traerse la imagen entera 130 veces.
    """
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError

    def pedir(metodo, cabeceras):
        with urlopen(Request(url, method=metodo, headers=cabeceras), timeout=20) as r:
            return r.status

    try:
        return pedir("HEAD", _COMO_UN_NAVEGADOR)
    except HTTPError as e:
        if e.code not in (403, 405, 400):
            return e.code
    except URLError as e:
        return str(e.reason)

    try:
        return pedir("GET", dict(_COMO_UN_NAVEGADOR, Range="bytes=0-0"))
    except HTTPError as e:
        return e.code
    except URLError as e:
        return str(e.reason)


def _comprobar_imagenes(filas, mapa):
    """Pide cada imagen y dice cuáles no están. Devuelve 1 si falta alguna.

    Con 130 ficheros subidos a mano basta un acento perdido o un `.jpg` que se
    guardó como `.png` para que la ficha del ejercicio salga con un hueco. Eso
    no lo ve nadie hasta que un cliente abre esa ficha en el gimnasio.
    """
    pendientes = []
    for fila in filas:
        n = (fila.get("imagen") or "").strip()
        if n:
            pendientes.append((fila.get("nombre_ejercicio"), n, url_de_imagen(n, mapa)))

    print(f"\nComprobando {len(pendientes)} imágenes…")
    faltan = []
    for i, (ejercicio, archivo, url) in enumerate(pendientes, 1):
        estado = _estado_de(url)
        if not (isinstance(estado, int) and estado < 400):
            faltan.append((ejercicio, archivo, estado))
        if i % 25 == 0:
            print(f"  {i}/{len(pendientes)}…")

    if not faltan:
        print(f"\nLas {len(pendientes)} están. La carga puede poner la imagen de todas.")
        return 0

    print(f"\nNO ESTÁN {len(faltan)} de {len(pendientes)}:")
    for ejercicio, archivo, motivo in faltan[:20]:
        print(f"  · {archivo}  ({ejercicio}) → {motivo}")
    if len(faltan) > 20:
        print(f"  … y {len(faltan) - 20} más")

    # Fallan TODAS con el mismo código: no es que falten ficheros, es que no se
    # puede entrar. Decirlo evita salir a buscar 130 imágenes que sí están.
    motivos = {m for _e, _a, m in faltan}
    if len(faltan) == len(pendientes) and len(motivos) == 1:
        unico = motivos.pop()
        print(f"\nFallan LAS {len(faltan)}, todas con {unico}. Eso no son 130 ficheros")
        print("que falten: es que el bucket no deja entrar. En Cloudflare → R2 →")
        print("el bucket → Settings → Public Development URL tiene que estar")
        print("habilitada (o un dominio propio conectado). Compruébalo abriendo")
        print("una de esas URLs en una ventana de incógnito: si ahí tampoco se ve,")
        print("es eso.")
    else:
        print("\nEsos ejercicios entrarían con un hueco donde va la foto.")
    return 1


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
    ap.add_argument("--comprobar-imagenes", action="store_true",
                    help="Pedir cada imagen a R2 para ver que está de verdad")
    args = ap.parse_args()

    filas = leer_csv(args.csv)
    mapa = {}
    if os.path.exists(args.imagenes):
        with open(args.imagenes, encoding="utf-8") as f:
            mapa = json.load(f)

    print(f"CSV:      {args.csv}  ({len(filas)} filas)")
    print(f"Imágenes: {BASE_IMAGENES}")
    if mapa:
        print(f"          + {len(mapa)} con nombre propio en {args.imagenes}")

    # Va antes de tocar la base: no necesita base de datos y es la única forma
    # de saber que las 130 están DONDE dice el CSV. Una imagen renombrada al
    # subirla se ve como un hueco en el móvil del cliente y nadie se entera.
    if args.comprobar_imagenes:
        raise SystemExit(_comprobar_imagenes(filas, mapa))

    from app.database import SessionLocal
    from app.models.training import Training

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
