/* La ficha del ejercicio, mientras el cliente entrena.

   Al tocar la foto de un ejercicio a mitad de la serie solo se abría el vídeo.
   Después se le puso todo lo que el coach había escrito, pero en una sola
   columna: el vídeo, la prescripción, la descripción entera con sus cinco
   pasos y sus errores comunes, y los chips. Con eso, los récords quedaban a
   dos pantallazos de scroll — y son justo lo que quiere ver quien está entre
   dos series.

   Ahora son tres pestañas: lo que ha conseguido, lo que ya hizo y cómo se
   hace.

   Lo que hay que dejar sujeto:

     · Que tocar la foto abra la ficha, y por Resumen.
     · Que el vídeo SIGA estando: es lo que más se mira.
     · Que se vea lo que le toca HOY, que es a lo que ha venido.
     · Que Resumen enseñe sus récords y la evolución de carga.
     · Que Historial enseñe las sesiones con sus series, peso y RPE.
     · Que Indicaciones enseñe los pasos numerados y, aparte, los errores.
     · Que abrir otro ejercicio vuelva a Resumen.
     · Y que un ejercicio sin historial lo diga en vez de salir vacío.

   Se carga la PÁGINA de verdad, con el servidor de mentira.
*/
const { chromium } = require("../_pw");

const DESCRIPCION =
  "1. Túmbate en el banco con los pies apoyados.\n" +
  "2. Agarra la barra algo más ancho que los hombros.\n" +
  "3. Baja la barra de forma controlada hasta el pecho.\n" +
  "⚠️ Errores comunes\n" +
  "* Abrir los codos a 90°: estresa el hombro.\n" +
  "* Rebotar la barra en el pecho.";

const FICHA = {
  id: 7,
  name: "Press de banca",
  description: DESCRIPCION,
  image: null,
  video_url: "https://youtu.be/abc123",
  muscle_group_name: "Pecho",
  secondary_muscle_names: ["Tríceps", "Hombro"],
  material: "Barra",
  movement_pattern: "Empuje horizontal",
  exercise_type: "Compuesto",
  location: "Gimnasio",
  difficulty_names: ["Intermedio"],
  rec_series: "3-4",
  rec_reps: "8-12",
  rec_rest: "90s",
  records: {
    mayor_peso: 70,
    mejor_rm1: 82,
    mejor_volumen: 2800,
    mejor_tiempo_s: null,
  },
  evolucion: [
    { fecha: "2026-06-10", peso: 60 },
    { fecha: "2026-07-01", peso: 65 },
    { fecha: "2026-07-16", peso: 65 },
    { fecha: "2026-07-30", peso: 70 },
  ],
  historial: [
    {
      sesion: "Empuje A",
      fecha: "2026-07-30",
      series: 3,
      peso_top: 70,
      detalle: [
        { serie: 1, peso: 60, reps: "10", rpe: 8 },
        { serie: 2, peso: 65, reps: "8", rpe: null },
        { serie: 3, peso: 70, reps: "6", rpe: 9 },
      ],
    },
    {
      sesion: "Empuje A",
      fecha: "2026-07-16",
      series: 2,
      peso_top: 65,
      detalle: [
        { serie: 1, peso: 55, reps: "10", rpe: null },
        { serie: 2, peso: 65, reps: "8", rpe: 8.5 },
      ],
    },
  ],
};

// Uno que nunca ha entrenado y sin nada escrito.
const PELADO = {
  id: 9,
  name: "Plancha",
  description: null,
  image: null,
  video_url: null,
  muscle_group_name: "Core",
  secondary_muscle_names: [],
  material: null,
  movement_pattern: null,
  exercise_type: null,
  location: null,
  difficulty_names: [],
  rec_series: null,
  rec_reps: null,
  rec_rest: null,
  records: {
    mayor_peso: null,
    mejor_rm1: null,
    mejor_volumen: null,
    mejor_tiempo_s: null,
  },
  evolucion: [],
  historial: [],
};

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.setViewportSize({ width: 430, height: 900 });
  const errs = [];
  p.on("pageerror", (e) => errs.push(String(e)));

  /* El <iframe> del vídeo carga YouTube de verdad, y su propio código revienta
     al no poder leer localStorage desde `file://`. Es ruido del banco de
     pruebas, no de la aplicación: se corta la petición y se comprueba el `src`,
     que es lo que la página decide. */
  await p.route("**://*.youtube.com/**", (r) => r.abort());

  await p.addInitScript(
    (fichas) => {
      // Esto corre en TODOS los marcos, y el del vídeo tiene origen opaco: ahí
      // `localStorage` lanza. Solo interesa la página.
      if (window.top !== window) return;
      localStorage.setItem("token", "t");
      localStorage.setItem("role_id", "6");
      window.__pedidos = [];
      window.fetch = async (url) => {
        const u = String(url);
        if (u.includes("/client/exercise/")) {
          window.__pedidos.push(u);
          const id = u.split("/client/exercise/")[1].split("?")[0];
          const d = fichas[id];
          if (!d)
            return {
              status: 404,
              ok: false,
              json: async () => ({ message: "no" }),
            };
          return { status: 200, ok: true, json: async () => ({ data: d }) };
        }
        return { status: 200, ok: true, json: async () => ({ data: {} }) };
      };
    },
    { 7: FICHA, 9: PELADO },
  );

  await p.goto("file://" + __dirname + "/../../frontend/client-entrena.html");
  await p.waitForFunction(() => typeof window.abrirFicha === "function", {
    timeout: 8000,
  });

  let f = 0;
  const ck = (n, c, x) => {
    console.log(
      (c ? "OK   " : "FALLO ") + n + (c ? "" : " -> " + JSON.stringify(x)),
    );
    if (!c) f++;
  };
  const cuerpo = () => p.textContent("#ejCuerpo");
  const cargada = () =>
    p.waitForFunction(
      () =>
        !document.querySelector("#ejCuerpo").textContent.includes("Cargando"),
      { timeout: 5000 },
    );

  await p.evaluate(() => {
    _ws = {
      routineId: 1,
      dayName: "Empuje A",
      startMs: Date.now(),
      exercises: [
        {
          training_id: 7,
          name: "Press de banca",
          muscle: "Pecho",
          image: null,
          video_url: "https://youtu.be/abc123",
          rest: 90,
          target: "8-12",
          note: "",
          sets: [0, 0, 0, 0].map(() => ({
            reps: "",
            kg: "",
            rpe: "",
            done: false,
          })),
        },
        {
          training_id: 9,
          name: "Plancha",
          muscle: "Core",
          image: null,
          video_url: null,
          rest: null,
          target: "40s",
          note: "",
          sets: [{ reps: "", kg: "", rpe: "", done: false }],
        },
        {
          training_id: 99,
          name: "Remo",
          muscle: "Espalda",
          image: null,
          video_url: null,
          rest: null,
          target: "10",
          note: "",
          sets: [{ reps: "", kg: "", rpe: "", done: false }],
        },
      ],
    };
    renderWorkout();
    document.getElementById("wsOverlay").classList.add("open");
  });
  await p.waitForTimeout(200);

  // ── Tocar la foto ────────────────────────────────────────────────────────
  ck(
    "la foto del ejercicio se puede tocar",
    (await p.locator('.ws-thumb[role="button"]').count()) === 3,
    await p.locator('.ws-thumb[role="button"]').count(),
  );

  await p.locator(".ws-thumb").first().click();
  ck(
    "SE ABRE LA FICHA, no solo el video",
    await p.locator("#ejBack").evaluate((n) => n.classList.contains("open")),
  );
  ck(
    "el modal de solo-video NO se abre",
    !(await p
      .locator("#vidModal")
      .evaluate((n) => n.classList.contains("open"))),
  );
  ck(
    "con el nombre del ejercicio",
    (await p.textContent("#ejTit")) === "Press de banca",
    await p.textContent("#ejTit"),
  );
  ck(
    "y su musculo",
    (await p.textContent("#ejMus")) === "Pecho",
    await p.textContent("#ejMus"),
  );

  ck(
    "LAS TRES PESTAÑAS ESTAN",
    JSON.stringify(
      await p.$$eval(".ej-tab", (ns) => ns.map((n) => n.textContent.trim())),
    ) === JSON.stringify(["Resumen", "Historial", "Indicaciones"]),
    await p.$$eval(".ej-tab", (ns) => ns.map((n) => n.textContent.trim())),
  );
  ck(
    "y abre por Resumen",
    (await p.textContent(".ej-tab.sel")) === "Resumen",
    await p.textContent(".ej-tab.sel"),
  );

  // Lo que ya está en el móvil se pinta sin esperar al servidor.
  const hoy = await p.$$eval(".ej-cifras .v", (ns) =>
    ns.map((n) => n.textContent.trim()),
  );
  ck(
    "LO QUE LE TOCA HOY SALE AL INSTANTE: 4 series, 8-12 reps, 90s",
    JSON.stringify(hoy) === JSON.stringify(["4", "8-12", "90s"]),
    hoy,
  );
  ck(
    "EL VIDEO SIGUE ESTANDO, dentro de la ficha",
    (await p.locator(".ej-media iframe").count()) === 1,
  );
  ck(
    "y es el del ejercicio",
    (await p.getAttribute(".ej-media iframe", "src")).includes("abc123"),
  );

  // ── Resumen: récords y evolución ─────────────────────────────────────────
  await cargada();
  const recs = await p.$$eval(".ej-rec-fila", (ns) =>
    ns.map((n) => n.textContent.replace(/\s+/g, " ").trim()),
  );
  ck(
    "RESUMEN ENSEÑA SUS RECORDS",
    recs.some((r) => r.includes("Mayor peso") && r.includes("70 kg")) &&
      recs.some((r) => r.includes("Mejor 1RM") && r.includes("82 kg")) &&
      recs.some((r) => r.includes("Mejor volumen") && r.includes("2800 kg")),
    recs,
  );
  ck(
    "y no inventa un record de tiempo que no tiene",
    !recs.some((r) => r.includes("Mejor tiempo")),
    recs,
  );
  ck(
    "con la evolucion de carga dibujada",
    (await p.locator(".ej-graf svg polyline").count()) === 1,
  );
  ck(
    "y un punto por sesion",
    (await p.locator(".ej-graf svg circle").count()) === 4,
    await p.locator(".ej-graf svg circle").count(),
  );
  ck(
    "la descripcion NO esta en Resumen: tiene su pestaña",
    !(await cuerpo()).includes("Túmbate en el banco"),
    await cuerpo(),
  );

  // ── Historial ────────────────────────────────────────────────────────────
  await p.locator('.ej-tab[data-t="historial"]').click();
  await p.waitForTimeout(150);
  ck(
    "HISTORIAL ENSEÑA UNA TARJETA POR SESION",
    (await p.locator(".ej-ses").count()) === 2,
    await p.locator(".ej-ses").count(),
  );
  const primera = await p.locator(".ej-ses").first().textContent();
  ck(
    "con el dia y la fecha, en letra",
    primera.includes("Empuje A") && primera.includes("30 jul 2026"),
    primera,
  );
  // El número de serie y lo que se levantó son dos elementos: se comprueban
  // por separado, que es además cómo se leen en pantalla.
  const filas = await p
    .locator(".ej-ses")
    .first()
    .locator(".ej-ses-fila")
    .evaluateAll((ns) =>
      ns.map((n) => [
        n.querySelector("b").textContent.trim(),
        n.querySelector("span").textContent.trim(),
      ]),
    );
  ck(
    "Y SUS SERIES CON PESO, REPS Y RPE",
    JSON.stringify(filas) ===
      JSON.stringify([
        ["1", "60 kg × 10 @ 8 rpe"],
        ["2", "65 kg × 8"],
        ["3", "70 kg × 6 @ 9 rpe"],
      ]),
    filas,
  );
  ck("la serie sin RPE no lo inventa", filas[1][1] === "65 kg × 8", filas[1]);
  ck(
    "lo mas reciente primero",
    (await p.locator(".ej-ses").nth(1).textContent()).includes("16 jul"),
    await p.locator(".ej-ses").nth(1).textContent(),
  );

  // ── Indicaciones ─────────────────────────────────────────────────────────
  await p.locator('.ej-tab[data-t="indicaciones"]').click();
  await p.waitForTimeout(150);
  const pasos = await p.$$eval(".ej-paso", (ns) =>
    ns.map((n) => n.textContent.trim()),
  );
  ck(
    "INDICACIONES ENSEÑA LOS PASOS, uno por uno",
    pasos.length === 3 && pasos[0].startsWith("Túmbate en el banco"),
    pasos,
  );
  ck(
    "sin arrastrar el numero, que lo pone la lista",
    !pasos[0].startsWith("1."),
    pasos[0],
  );
  const mal = await p.$$eval(".ej-errores li", (ns) =>
    ns.map((n) => n.textContent.trim()),
  );
  ck(
    "Y LOS ERRORES COMUNES APARTE, que son lo contrario de un paso",
    mal.length === 2 && mal[0].includes("Abrir los codos"),
    mal,
  );
  ck(
    "con el aviso del peso total en los ejercicios con barra",
    (await cuerpo()).includes("incluida la barra"),
    await cuerpo(),
  );
  ck(
    "y el video tambien aqui, que es para seguir los pasos",
    (await p.locator(".ej-media iframe").count()) === 1,
  );

  // ── Abrir otro ejercicio vuelve a Resumen ────────────────────────────────
  await p.locator(".ej-x").click();
  await p.waitForTimeout(150);
  await p.locator(".ws-thumb").nth(1).click();
  await p.waitForTimeout(200);
  ck(
    "ABRIR OTRO EJERCICIO VUELVE A RESUMEN",
    (await p.textContent(".ej-tab.sel")) === "Resumen",
    await p.textContent(".ej-tab.sel"),
  );

  // ── Uno que nunca ha entrenado ───────────────────────────────────────────
  await cargada();
  ck(
    "SIN HISTORIAL LO DICE, no sale vacio",
    (await cuerpo()).includes("Aún no has entrenado"),
    await cuerpo(),
  );
  ck(
    "y sin evolucion no dibuja una linea de un punto",
    (await p.locator(".ej-graf").count()) === 0,
  );
  await p.locator('.ej-tab[data-t="historial"]').click();
  await p.waitForTimeout(150);
  ck(
    "su historial tambien lo dice",
    (await cuerpo()).includes("Aún no has entrenado"),
    await cuerpo(),
  );
  await p.locator('.ej-tab[data-t="indicaciones"]').click();
  await p.waitForTimeout(150);
  ck(
    "y sin indicaciones escritas, tambien",
    (await cuerpo()).includes("no ha escrito las indicaciones"),
    await cuerpo(),
  );

  // ── Cuando el servidor no la da ──────────────────────────────────────────
  await p.locator(".ej-x").click();
  await p.waitForTimeout(150);
  await p.locator(".ws-thumb").nth(2).click();
  await cargada();
  ck(
    "si no se puede cargar, lo dice",
    (await cuerpo()).includes("No se pudo cargar"),
    await cuerpo(),
  );
  ck(
    "y aun asi enseña lo que le toca hoy",
    (await cuerpo()).includes("Reps"),
    await cuerpo(),
  );

  // Que falle no puede convertirse en pedirlo una y otra vez cada vez que abre.
  await p.locator(".ej-x").click();
  await p.waitForTimeout(150);
  await p.locator(".ws-thumb").nth(2).click();
  await p.waitForTimeout(400);
  const fallidos = await p.evaluate(() =>
    window.__pedidos.filter((u) => u.endsWith("/99")),
  );
  ck("TAMPOCO SE REPITE LA QUE FALLA", fallidos.length === 1, fallidos);

  // Ni la que fue bien.
  await p.locator(".ej-x").click();
  await p.waitForTimeout(150);
  await p.locator(".ws-thumb").first().click();
  await p.waitForTimeout(400);
  const pedidos = await p.evaluate(() =>
    window.__pedidos.filter((u) => u.endsWith("/7")),
  );
  ck("la ficha se pide UNA vez por ejercicio", pedidos.length === 1, pedidos);

  // ── Cerrar ───────────────────────────────────────────────────────────────
  await p.locator(".ej-x").click();
  await p.waitForTimeout(150);
  ck(
    "se cierra",
    !(await p.locator("#ejBack").evaluate((n) => n.classList.contains("open"))),
  );
  ck(
    "Y EL VIDEO DEJA DE SONAR DEBAJO",
    (await p.locator(".ej-media iframe").count()) === 0,
  );

  ck("sin errores de JS", errs.length === 0, errs);
  await b.close();
  process.exit(f ? 1 : 0);
})();
