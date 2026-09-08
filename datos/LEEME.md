# Datos para cargas de una sola vez

## `alimentos-catalogo.csv`

El catálogo de alimentos que prepara el cliente: **1.441 filas** en 28
categorías, con las marcas separadas del nombre, el momento sugerido de cada
alimento y la marca de si entra o no en el generador de dietas.

Está aquí y no en el ordenador de nadie para que la carga se pueda repetir y
comprobar: con el fichero suelto en Descargas, la ruta cambia según quién lo
lance y nadie sabe después qué se cargó exactamente. Este fichero ES lo que
hay en producción.

No lleva datos personales: son alimentos, sus macros y sus fuentes.

### Cosas del fichero que conviene saber

  · **Una celda vacía es SIN DATO, no un cero.** La ficha del alimento pinta
    una rayita cuando no hay dato; un cero inventado diría "este alimento no
    tiene vitamina D", que es una afirmación que nadie ha hecho.
  · **Hay nombres repetidos, y está bien.** Son el genérico y sus versiones de
    marca: "Avena", "Avena · Brüggen" y "Avena · Max Protein" son tres
    alimentos distintos con macros distintos. El buscador enseña la marca al
    lado del nombre, así que se distinguen.
  · `momento_sugerido` viene con las etiquetas largas ("Media mañana /
    merienda") y el importador las traduce a las claves que comparan los chips
    del formulario. Vacío significa que vale para cualquier momento.
  · `usar_en_generador` en `False` deja al alimento fuera del generador de
    dietas. Son alimentos apartados a propósito, uno a uno.
  · Las columnas `tiene_micros` y `es_duplicado` son notas de trabajo del
    cliente: el importador no las usa.

### Cómo se carga

    python scripts/copia_seguridad.py             # primero esto. No se deshace.
    python scripts/limpiar_y_cargar_alimentos.py --inspeccionar
    python scripts/limpiar_y_cargar_alimentos.py  # ensayo: cuenta, no escribe
    python scripts/limpiar_y_cargar_alimentos.py --ejecutar
    python scripts/limpiar_y_cargar_alimentos.py --verificar

Sin `--csv` coge este fichero. Y ojo: la carga **sustituye el catálogo entero**
y se lleva por delante dietas, recetas, rutinas y menús, porque apuntaban a
alimentos que dejan de existir. El historial de entrenos de los clientes se
conserva.

## `ejercicios-pendientes.csv` y `ejercicios-imagenes.json`

Los **132 ejercicios** de la biblioteca de Notion «Biblioteca de ejercicios —
Alzum» que todavía no estaban en la plataforma, con su descripción, sus
músculos, su material y su vídeo. Vienen con **130 imágenes** aparte.

### Cosas del fichero que conviene saber

  · **Lleva BOM** —lo abre Excel—, así que se lee con `utf-8-sig`. Con `utf-8`
    a secas la primera columna se llama `﻿nombre_ejercicio` y no la encuentra
    nadie: todas las filas saldrían sin nombre.
  · **La descripción trae saltos de línea DENTRO de la celda.** Hay que leerlo
    con un parser de CSV de verdad; partirlo por líneas rompe esa celda y cada
    paso entra como una fila.
  · `grupo_muscular_secundario` y `equipamiento` traen **varios valores
    separados por «, »** en la misma celda.
  · Las etiquetas vienen en castellano —«Compuesto», «Gimnasio»,
    «Intermedio»— y la tabla guarda códigos: `compound`, `gym`, `2`. La
    traducción está en el script, no en la pantalla: en la base ya hay
    ejercicios con esos códigos y mezclarlos partiría los filtros en dos.
  · **Huecos reales, no errores:** 1 fila sin vídeo (Burpees) y 2 sin imagen
    («Jalón al pecho con agarre supino», «Elevación de piernas colgado»).
    Quedan vacíos en destino.
  · La carpeta de imágenes trae un `_decisiones-miniaturas.md` que es un
    informe interno, no un ejercicio. Se filtra por extensión.

Las 130 imágenes **ya están en R2**, subidas conservando el nombre de archivo
del CSV, así que la URL de cada una es la base más el nombre y no hace falta
ningún mapa. La base está escrita en `scripts/cargar_ejercicios.py`
(`BASE_IMAGENES`) y no se pasa por la línea de órdenes: es la ruta de lo que
hay en producción, y con ella a mano la carga daría un resultado distinto
según quién la lance.

`ejercicios-imagenes.json` solo hace falta para imágenes subidas con OTRO
nombre —lo que deja `subir_imagenes_ejercicios.py`, que les pone un hash—.
Si existe, manda sobre la base. Sirve para las dos que todavía no están
generadas.

### Cómo se carga

La comprobación de las imágenes va primero y aparte: no toca la base, y es la
única forma de saber que las 130 están donde el CSV dice. Un acento perdido o
un `.jpg` guardado como `.png` deja la ficha del ejercicio con un hueco, y eso
no lo ve nadie hasta que un cliente la abre en el gimnasio.

    # 1. Que las 130 imágenes estén donde dice el CSV. No toca la base.
    python scripts/cargar_ejercicios.py --comprobar-imagenes

    # 2. Los ejercicios, a la base.
    python scripts/copia_seguridad.py            # primero esto
    python scripts/cargar_ejercicios.py --inspeccionar
    python scripts/cargar_ejercicios.py          # ensayo: cuenta, no escribe
    python scripts/cargar_ejercicios.py --ejecutar
    python scripts/cargar_ejercicios.py --verificar

Un ejercicio que **ya existe con el mismo nombre se actualiza** con lo del
CSV: la entrega es la versión buena. Esta carga no borra nada.

`--inspeccionar` es el paso que importa: saca los grupos musculares del CSV
que **no existen** en la base. No se crean solos — si el CSV dice
«Isquiotibiales» y en la base pone «Femoral», crear uno nuevo deja el catálogo
partido en dos sin que nadie se entere. Esos hay que resolverlos a mano antes.
