"""Subir a R2 las imágenes de los ejercicios y anotar dónde quedó cada una.

La entrega del cliente trae una carpeta con las miniaturas y un CSV que las
nombra por su nombre de archivo. En la base no se guarda el fichero: se guarda
la URL pública, igual que cuando el editor sube una foto a mano desde la
pantalla de Ejercicios.

Este paso va SEPARADO de la carga a la base a propósito. Subir 130 ficheros
depende de la red y de las credenciales; escribir en la base, no. Con el mapa
`nombre de archivo → URL` guardado en el repositorio, la carga se puede
repetir, comprobar y deshacer sin volver a subir un solo byte — y si la carga
falla a la mitad, no hay que empezar por el principio.

    python scripts/subir_imagenes_ejercicios.py --carpeta ~/entrega/imagenes-ejercicios
    python scripts/subir_imagenes_ejercicios.py --carpeta ~/entrega/imagenes-ejercicios --ejecutar

Sin `--ejecutar` no sube nada: dice qué subiría y qué ya está subido.

Necesita en el entorno, de las variables del servicio en Railway:

    AWS_ACCESS_KEY_ID  AWS_SECRET_ACCESS_KEY  AWS_BUCKET  R2_PUBLIC_URL
"""
import argparse
import hashlib
import json
import mimetypes
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

MAPA_POR_DEFECTO = os.path.join(RAIZ, "datos", "ejercicios-imagenes.json")

# La carpeta de la entrega trae un informe interno junto a las imágenes. Se
# filtra por extensión, así que cae solo; se nombra aquí para que quien lea
# esto sepa que no es un descuido.
EXTENSIONES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Dónde viven dentro del bucket. Aparte de `uploads/`, que es el cajón de todo
# lo que se sube a mano: así se ve de un vistazo qué entró en esta carga y se
# puede revisar —o retirar— sin tocar nada de lo demás.
CARPETA_R2 = "ejercicios"


def imagenes_de(carpeta):
    """Los ficheros de imagen de la carpeta, ordenados y sin el informe."""
    if not os.path.isdir(carpeta):
        raise SystemExit(f"No existe la carpeta: {carpeta}")
    nombres = [n for n in sorted(os.listdir(carpeta))
               if os.path.splitext(n)[1].lower() in EXTENSIONES]
    return nombres


def clave_de(nombre, contenido):
    """La ruta dentro del bucket.

    Lleva un trozo del hash del contenido para que volver a lanzar esto NO
    duplique ficheros ni pise una imagen distinta con el mismo nombre: mismo
    contenido, misma clave, misma URL. Y como la URL cambia si la imagen
    cambia, las cachés de un año que pone la API no dejan la vieja pegada.
    """
    base, ext = os.path.splitext(nombre)
    firma = hashlib.sha256(contenido).hexdigest()[:12]
    limpio = "".join(c if (c.isalnum() or c in "-_") else "-" for c in base.lower())
    return f"{CARPETA_R2}/{limpio}-{firma}{ext.lower()}"


def _cliente_r2(settings):
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=settings.AWS_ENDPOINT_URL
        or "https://77925e3b1a6f6513bce155f71f6aa790.r2.cloudflarestorage.com",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def cargar_mapa(ruta):
    if not os.path.exists(ruta):
        return {}
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def guardar_mapa(ruta, mapa):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--carpeta", required=True,
                    help="La carpeta imagenes-ejercicios/ de la entrega")
    ap.add_argument("--mapa", default=MAPA_POR_DEFECTO,
                    help="Dónde se anota nombre de archivo → URL pública")
    ap.add_argument("--ejecutar", action="store_true",
                    help="Sube de verdad. Sin esto solo dice qué haría.")
    args = ap.parse_args()

    from app.config import settings

    nombres = imagenes_de(args.carpeta)
    mapa = cargar_mapa(args.mapa)
    print(f"Carpeta:  {args.carpeta}")
    print(f"Imágenes: {len(nombres)}")
    print(f"Ya en el mapa: {len(mapa)}")

    faltan = [n for n in nombres if n not in mapa]
    print(f"Por subir: {len(faltan)}")
    if not args.ejecutar:
        for n in faltan[:10]:
            print(f"  · {n}")
        if len(faltan) > 10:
            print(f"  … y {len(faltan) - 10} más")
        print("\nEnsayo. Repite con --ejecutar para subirlas.")
        return

    base = (settings.R2_PUBLIC_URL or "").rstrip("/")
    if not settings.AWS_BUCKET or not base or not settings.AWS_ACCESS_KEY_ID:
        raise SystemExit(
            "Falta configuración del almacén. Se necesitan en el entorno:\n"
            "  AWS_ACCESS_KEY_ID  AWS_SECRET_ACCESS_KEY  AWS_BUCKET  R2_PUBLIC_URL")

    r2 = _cliente_r2(settings)
    subidas = 0
    for i, nombre in enumerate(faltan, 1):
        with open(os.path.join(args.carpeta, nombre), "rb") as f:
            contenido = f.read()
        clave = clave_de(nombre, contenido)
        tipo = mimetypes.guess_type(nombre)[0] or "image/png"
        r2.put_object(Bucket=settings.AWS_BUCKET, Key=clave, Body=contenido,
                      ContentType=tipo, CacheControl="public, max-age=31536000")
        mapa[nombre] = f"{base}/{clave}"
        subidas += 1
        # Se guarda sobre la marcha: si esto se corta en la imagen 90, las 89
        # de antes no hay que volver a subirlas.
        if subidas % 10 == 0:
            guardar_mapa(args.mapa, mapa)
            print(f"  {i}/{len(faltan)}…")

    guardar_mapa(args.mapa, mapa)
    print(f"\nSubidas {subidas}. El mapa está en {args.mapa} — súbelo al repositorio.")


if __name__ == "__main__":
    main()
