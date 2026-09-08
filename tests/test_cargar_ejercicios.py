"""La carga de los 132 ejercicios que entrega el cliente.

El fichero viene de Notion y trae trampas de formato: BOM al principio —lo
abre Excel—, saltos de línea DENTRO de la celda de la descripción, listas
separadas por «, » en dos columnas, y etiquetas en castellano donde la tabla
guarda códigos en inglés. Cada una de esas cosas tiene una forma obvia de
hacerse mal y ninguna avisa: el ejercicio entra igual, mal.

Lo que hay que dejar sujeto:

  · Que la descripción multi-línea llegue ENTERA.
  · Que las etiquetas se traduzcan a los códigos que ya hay en la base, y que
    una etiqueta desconocida se avise en vez de colarse.
  · Que un hueco del CSV —sin vídeo, sin imagen— quede vacío y no reviente.
  · Que los grupos musculares se busquen por nombre y los que no existan se
    avisen: crearlos en silencio parte el catálogo en dos.
  · Y que un ejercicio que ya existe se ACTUALICE, que es lo acordado.
"""
import json
import os
import sys
import uuid

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))

import cargar_ejercicios as ce                                   # noqa: E402

from app.database import SessionLocal                            # noqa: E402
from app.models.muscle_group import MuscleGroup                  # noqa: E402
from app.models.training import Training                         # noqa: E402


CABECERA = ",".join(ce.COLUMNAS)

# Una fila con la descripción tal como la entrega el cliente: pasos numerados,
# un separador de errores comunes y viñetas, todo dentro de la misma celda.
DESCRIPCION = (
    "1. Túmbate en el banco con los pies apoyados.\n"
    "2. Baja la barra de forma controlada al pecho.\n"
    "3. Empuja hasta extender los codos.\n"
    "⚠️ Errores comunes\n"
    "* Rebotar la barra en el pecho.\n"
    "* Despegar la cadera del banco."
)

FILAS = [
    # nombre, otros, tipo, principal, secundarios, sitio, video, desc, imagen,
    # equipo, nivel, patrón, recomendación
    ["Press banca", "Bench press", "Compuesto", "Pecho", "Tríceps, Hombro",
     "Gimnasio", "https://player.mediadelivery.net/play/1/abc", DESCRIPCION,
     "press-banca.png", "Barra, Banco", "Intermedio", "Empuje horizontal",
     "3-4 series de 8-12 repeticiones, descanso 90s"],
    # El hueco real de la entrega: Burpees no tiene vídeo.
    ["Burpees", "", "Cardio", "Cuerpo completo", "", "Casa", "",
     "1. De pie.\n2. Al suelo.", "burpees.png", "Sin equipo", "Avanzado",
     "Cuerpo completo", ""],
    # Y los dos que no tienen imagen generada.
    ["Elevación de piernas colgado", "", "Aislamiento", "Core", "",
     "Gimnasio", "https://player.mediadelivery.net/play/1/def",
     "1. Cuélgate.", "", "Barra de dominadas", "Avanzado", "Flexión de cadera",
     "3 series de 10 reps"],
]


def _csv(tmp_path, filas=None, cabecera=CABECERA):
    """El fichero como lo entrega el cliente: UTF-8 CON BOM y comillas."""
    import csv as _csv_mod
    import io
    buf = io.StringIO()
    w = _csv_mod.writer(buf)
    w.writerow(cabecera.split(","))
    for f in (filas if filas is not None else FILAS):
        w.writerow(f)
    ruta = tmp_path / "ejercicios.csv"
    ruta.write_text(buf.getvalue(), encoding="utf-8-sig")
    return str(ruta)


# ── Leer el fichero ────────────────────────────────────────────────────────

def test_EL_BOM_NO_SE_COME_LA_PRIMERA_COLUMNA(tmp_path):
    """Con `utf-8` a secas la primera columna se llamaría "﻿nombre_ejercicio"
    y no la encontraría nadie: todas las filas saldrían sin nombre."""
    filas = ce.leer_csv(_csv(tmp_path))
    assert filas[0]["nombre_ejercicio"] == "Press banca"


def test_LA_DESCRIPCION_MULTILINEA_LLEGA_ENTERA(tmp_path):
    """Es la trampa del fichero: partirlo por líneas rompería la celda y cada
    paso entraría como una fila distinta."""
    d = ce.leer_csv(_csv(tmp_path))[0]["descripcion"]
    assert d.count("\n") == 5, repr(d)
    assert "Errores comunes" in d
    assert d.strip().endswith("Despegar la cadera del banco.")


def test_si_falta_una_columna_lo_dice_en_vez_de_cargar_a_medias(tmp_path):
    import pytest
    corta = ",".join(c for c in ce.COLUMNAS if c != "patron_movimiento")
    ruta = _csv(tmp_path, filas=[["x"] * 12], cabecera=corta)
    with pytest.raises(SystemExit) as e:
        ce.leer_csv(ruta)
    assert "patron_movimiento" in str(e.value)


# ── Traducir ───────────────────────────────────────────────────────────────

def test_LAS_ETIQUETAS_SE_TRADUCEN_A_LOS_CODIGOS_DE_LA_BASE(tmp_path):
    """En la base ya hay ejercicios con «compound» y «gym». Meter «Compuesto»
    al lado partiría los filtros en dos."""
    fila = ce.leer_csv(_csv(tmp_path))[0]
    d = ce.a_columnas(fila, {}, {})
    assert d["exercise_type"] == "compound"
    assert d["location"] == "gym"
    assert d["difficulty"] == 2 and d["difficulty_levels"] == "2"


def test_los_grupos_musculares_se_buscan_por_nombre(tmp_path):
    fila = ce.leer_csv(_csv(tmp_path))[0]
    d = ce.a_columnas(fila, {}, {"pecho": 10, "triceps": 11, "hombro": 12})
    assert d["muscle_group_id"] == 10
    assert d["secondary_muscle_group_ids"] == "11,12"
    assert d["secondary_muscle_group_id"] == 11, "el primero, por compatibilidad"


def test_UN_HUECO_DEL_CSV_QUEDA_VACIO_NO_REVIENTA(tmp_path):
    """Burpees sin vídeo y la elevación de piernas sin imagen son huecos de
    contenido reales, no errores de formato."""
    filas = ce.leer_csv(_csv(tmp_path))
    burpees = ce.a_columnas(filas[1], {}, {})
    assert burpees["video_url"] is None
    sin_foto = ce.a_columnas(filas[2], {"press-banca.png": "https://x/1.png"}, {})
    assert sin_foto["image"] is None


def test_LA_IMAGEN_CUELGA_DE_LA_BASE_CON_SU_NOMBRE(tmp_path):
    """Las 130 se subieron a R2 conservando el nombre del CSV, así que la URL
    es la base más el nombre y no hace falta ningún mapa."""
    fila = ce.leer_csv(_csv(tmp_path))[0]
    assert ce.a_columnas(fila, {}, {})["image"] == \
        ce.BASE_IMAGENES + "press-banca.png"


def test_la_base_apunta_a_donde_estan_de_verdad():
    """La URL que el cliente comprobó en el navegador. Si esto cambia sin que
    nadie lo mire, 130 ejercicios se quedan con la foto rota."""
    assert ce.url_de_imagen("abdominales-bicicleta.png") == (
        "https://pub-397ed3b6f1d1480d8c17d960513a3c78.r2.dev"
        "/imagenes-ejercicios/abdominales-bicicleta.png")


def test_y_una_subida_con_otro_nombre_manda_sobre_la_base(tmp_path):
    """La salida de subir_imagenes_ejercicios.py, que pone un hash en la clave.
    Sirve para las dos que faltan por generar."""
    fila = ce.leer_csv(_csv(tmp_path))[0]
    d = ce.a_columnas(fila, {"press-banca.png": "https://cdn/ejercicios/press-abc.png"}, {})
    assert d["image"] == "https://cdn/ejercicios/press-abc.png"


def test_el_equipamiento_se_junta_en_una_celda(tmp_path):
    fila = ce.leer_csv(_csv(tmp_path))[0]
    assert ce.a_columnas(fila, {}, {})["material"] == "Barra, Banco"


def test_LO_QUE_NO_CABE_SE_AVISA_NO_SE_RECORTA(tmp_path):
    """Recortar deja media frase con pinta de dato bueno, y nadie repasa 132
    filas a mano para descubrir cuál se quedó por la mitad."""
    filas = ce.leer_csv(_csv(tmp_path))
    filas[0]["equipamiento"] = ", ".join(["Mancuernas"] * 30)
    assert len(ce.a_columnas(filas[0], {}, {})["material"]) > ce.LARGOS["material"], \
        "lo ha recortado en vez de dejarlo como está"
    no_caben = ce.revisar(filas, {}, [])["no_cabe"]
    assert [(n, c) for n, c, _l, _t in no_caben] == [("Press banca", "material")], no_caben


# ── Las recomendaciones, que vienen en una sola celda ──────────────────────

def test_LA_FORMA_DE_LAS_99_FILAS():
    """El molde que sigue el fichero en casi todas: «N series de N
    repeticiones, N seg de descanso»."""
    assert ce.recomendaciones("3 series de 10 repeticiones, 60 seg de descanso") == \
        ("3", "10", "60 seg")
    assert ce.recomendaciones("3 series de 10 repeticiones") == ("3", "10", None)


def test_UNA_RONDA_NO_ES_UNA_SERIE():
    """«8-10 rondas» y «6-8 sprints» conservan la palabra: no son series y el
    cliente lee la diferencia. Y lo de dentro tampoco son repeticiones."""
    assert ce.recomendaciones("8-10 rondas de 30 seg de trabajo, 30 seg de descanso") == \
        ("8-10 rondas", "30 seg de trabajo", "30 seg")
    assert ce.recomendaciones("6-8 sprints de 15-20 seg, 60-90 seg de descanso") == \
        ("6-8 sprints", "15-20 seg", "60-90 seg")


def test_LO_QUE_MATIZA_EL_EJERCICIO_NO_SE_TIRA():
    """«por lado» y «lentas» cambian lo que hay que hacer. Quedarse solo con
    la cifra convierte dos ejercicios distintos en el mismo."""
    assert ce.recomendaciones("2-3 series de 8-10 repeticiones por lado") == \
        ("2-3", "8-10 por lado", None)
    assert ce.recomendaciones("1-2 series de 8-10 repeticiones lentas") == \
        ("1-2", "8-10 lentas", None)


def test_las_dos_formas_de_escribir_el_descanso():
    """El fichero pone «60 seg de descanso»; cualquiera teclea «descanso 90s».
    Sin la segunda se quedaba pegada a las repeticiones."""
    assert ce.recomendaciones("3 series de 8-12 reps, 60 seg de descanso")[2] == "60 seg"
    assert ce.recomendaciones("3 series de 8-12 reps, descanso 90s") == ("3", "8-12", "90s")


def test_la_forma_corta_sin_palabras():
    assert ce.recomendaciones("4x10") == ("4", "10", None)


def test_LO_QUE_NO_SE_ENTIENDE_NO_SE_INVENTA():
    """Un ejercicio de cardio no se prescribe en series y repeticiones. El
    reparto inventado le enseñaría al cliente cifras que nadie escribió: se
    guarda entero y la pantalla lo pinta tal cual."""
    for texto in ("Continuo: 20-30 min a ritmo constante",
                  "30 seg de trabajo por lado",
                  "Según sensaciones"):
        s, r, d = ce.recomendaciones(texto)
        assert (s, r, d) == (texto, None, None), texto
    assert ce.recomendaciones("") == (None, None, None)


def test_repeticiones_no_se_come_las_letras():
    """`reps?` antes que `repeticiones?` en la alternativa casaba «rep» y
    dejaba «eticiones» pegado a la cifra, en las 99 filas del molde común."""
    assert ce.recomendaciones("3 series de 10 repeticiones")[1] == "10"


# ── Los avisos, que es lo que se mira antes de escribir ────────────────────

def test_UN_GRUPO_MUSCULAR_QUE_NO_EXISTE_SE_AVISA(tmp_path):
    """Crearlo en silencio deja el catálogo partido: «Isquiotibiales» del CSV
    y «Femoral» de la base serían dos grupos para el mismo músculo."""
    filas = ce.leer_csv(_csv(tmp_path))
    avisos = ce.revisar(filas, {}, ["Pecho", "Tríceps"])
    assert "Hombro" in avisos["grupos_desconocidos"]
    assert "Core" in avisos["grupos_desconocidos"]
    assert "Pecho" not in avisos["grupos_desconocidos"]


def test_los_acentos_no_hacen_que_un_grupo_parezca_nuevo(tmp_path):
    filas = ce.leer_csv(_csv(tmp_path))
    avisos = ce.revisar(filas, {}, ["Pecho", "TRICEPS", "hombro ", "Cuerpo completo", "Core"])
    assert avisos["grupos_desconocidos"] == {}


def test_se_avisa_de_los_huecos_de_la_entrega(tmp_path):
    """Los que el cliente ya dijo que faltan. Que la imagen ESTÉ subida no lo
    sabe el CSV —solo R2—, y eso se pregunta con --comprobar-imagenes."""
    avisos = ce.revisar(ce.leer_csv(_csv(tmp_path)), {}, [])
    assert avisos["sin_imagen"] == ["Elevación de piernas colgado"]
    assert avisos["sin_video"] == ["Burpees"]


def test_un_nombre_repetido_dentro_del_csv_se_avisa(tmp_path):
    """Dos filas con el mismo nombre: la segunda pisaría a la primera sin que
    nadie se entere de que se ha perdido una."""
    filas = ce.leer_csv(_csv(tmp_path, filas=FILAS + [FILAS[0]]))
    avisos = ce.revisar(filas, {}, [])
    assert len(avisos["repetidos"]) == 1
    assert avisos["repetidos"][0][0] == "Press banca"


# ── Y contra la base ───────────────────────────────────────────────────────

def _grupo(nombre):
    db = SessionLocal()
    try:
        g = MuscleGroup(name=nombre)
        db.add(g); db.commit()
        return g.id
    finally:
        db.close()


def test_UN_EJERCICIO_QUE_YA_EXISTE_SE_ACTUALIZA(client, seed):
    """Lo acordado: la entrega es la versión buena. Antes de esto el catálogo
    tenía la ficha a medias y el CSV la trae entera."""
    suf = uuid.uuid4().hex[:8]
    nombre = f"Press banca {suf}"
    db = SessionLocal()
    try:
        db.add(Training(name=nombre, description="apunte viejo"))
        db.commit()
        antes = db.query(Training).filter(Training.name == nombre).count()
    finally:
        db.close()
    assert antes == 1

    pecho = _grupo(f"Pecho {suf}")
    fila = dict(zip(ce.COLUMNAS, FILAS[0]))
    fila["nombre_ejercicio"] = nombre
    fila["grupo_muscular_principal"] = f"Pecho {suf}"
    fila["grupo_muscular_secundario"] = ""
    datos = ce.a_columnas(fila, {"press-banca.png": "https://x/press.png"},
                          {ce._norm(f"Pecho {suf}"): pecho})

    db = SessionLocal()
    try:
        t = db.query(Training).filter(Training.name == nombre).first()
        for campo, valor in datos.items():
            setattr(t, campo, valor)
        db.commit()

        assert db.query(Training).filter(Training.name == nombre).count() == 1, \
            "se ha creado uno nuevo en vez de actualizar el que había"
        t = db.query(Training).filter(Training.name == nombre).first()
        assert "Errores comunes" in t.description, "no se ha traído la descripción"
        assert t.muscle_group_id == pecho
        assert t.image == "https://x/press.png"
        assert t.exercise_type == "compound" and t.location == "gym"
    finally:
        db.close()


# ── Comprobar que las imágenes están de verdad ─────────────────────────────
#
# Las 130 dieron 403 la primera vez y no faltaba ninguna: el comprobador
# preguntaba con `User-Agent: Python-urllib`, y Cloudflare —que está delante de
# r2.dev— eso lo rechaza. Un fallo del que pregunta parecía un fallo de lo
# preguntado, y detrás de eso hay alguien buscando 130 imágenes que sí estaban.

import threading                                                  # noqa: E402
from http.server import BaseHTTPRequestHandler, HTTPServer         # noqa: E402


def _servidor(manejador):
    s = HTTPServer(("127.0.0.1", 0), manejador)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_port}"


def test_UN_HEAD_RECHAZADO_NO_ES_UNA_IMAGEN_QUE_FALTE():
    """Es lo que pasó de verdad: 403 a las 130 y estaban todas."""
    class Cerrado(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_error(403)
        def do_GET(self):
            self.send_response(206); self.send_header("Content-Length", "1")
            self.end_headers(); self.wfile.write(b"x")
        def log_message(self, *a): pass

    s, base = _servidor(Cerrado)
    try:
        assert ce._estado_de(base + "/gato-camello.png") == 206
    finally:
        s.shutdown()


def test_una_que_NO_esta_se_sigue_viendo():
    """El arreglo no puede tragarse el caso que importa."""
    class Vacio(BaseHTTPRequestHandler):
        def do_HEAD(self): self.send_error(404)
        def do_GET(self): self.send_error(404)
        def log_message(self, *a): pass

    s, base = _servidor(Vacio)
    try:
        assert ce._estado_de(base + "/no-existe.png") == 404
    finally:
        s.shutdown()


def test_se_pregunta_como_pregunta_un_navegador():
    """Sin esto Cloudflare contesta 403 aunque el fichero esté."""
    vistos = []

    class Mira(BaseHTTPRequestHandler):
        def do_HEAD(self):
            vistos.append(self.headers.get("User-Agent"))
            self.send_response(200); self.end_headers()
        def log_message(self, *a): pass

    s, base = _servidor(Mira)
    try:
        ce._estado_de(base + "/x.png")
        assert vistos and "Mozilla" in vistos[0], vistos
    finally:
        s.shutdown()
