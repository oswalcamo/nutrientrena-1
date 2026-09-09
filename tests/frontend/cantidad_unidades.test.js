/* La cantidad de un alimento que va por unidades.

   Al añadir un Big Mac —1 ud, 590 kcal— el panel arrancaba en 1 y el «+» lo
   dejaba en 11, 21, 31: subía de diez en diez, que es el paso de los gramos.
   Y los atajos de debajo ofrecían 50ud, 100ud, 150ud.

   La causa: `diets.html` deducía la unidad por su cuenta y llamaba «unidad» a
   lo que el resto de la aplicación llama «ud». El catálogo guarda `ud`, `u` y
   `tz`, ninguno de ellos la palabra completa, así que la comprobación
   `unidad === 'unidad'` era falsa SIEMPRE y todo caía en el camino de los
   gramos. Ya existía `macrosAlimento.unidadDe()` para no tener siete formas
   de deducir lo mismo; ésta era la séptima.

   Lo que hay que dejar sujeto:

     · Que el «+» sume de uno en uno en lo que va por unidades.
     · Que los atajos sean 1, 2, 3… y no 50, 100, 150.
     · Que las escrituras del catálogo —«ud», «u», «tz»— cuenten todas.
     · Que los gramos sigan yendo de diez en diez y por medio kilo el cuarto.
     · Y que el aporte que se enseña no se mueva por esto.

   Se carga la PÁGINA de verdad, con el servidor de mentira.
*/
const { chromium } = require("../_pw");

const al = (id, nombre, unidad, porcion) => ({
  id,
  name: nombre,
  calories: 590,
  proteins: 25,
  carbohydrates: 46,
  fats: 34,
  fiber: 0,
  quantity: porcion,
  quantity_unit: unidad,
  group_food_id: 1,
  group_food: { name: "Platos preparados" },
});

const CATALOGO = [
  al("a-bigmac", "Big Mac", "ud", 1),
  al("a-huevo", "Huevo", "u", 1),
  al("a-taza", "Taza de arroz", "tz", 1),
  al("a-pollo", "Pollo", "gr", 100),
  al("a-aceite", "Aceite", "g", 100),
  al("a-leche", "Leche", "ml", 100),
];

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.setViewportSize({ width: 1400, height: 1000 });
  const errs = [];
  p.on("pageerror", (e) => errs.push(String(e)));

  await p.addInitScript((cat) => {
    if (window.top !== window) return;
    localStorage.setItem("token", "t");
    localStorage.setItem("role_id", "5");
    window.fetch = async (url, opts) => {
      const u = String(url);
      if ((opts || {}).method && opts.method !== "GET")
        return {
          status: 200,
          ok: true,
          json: async () => ({ data: { id: "x", foods: [] } }),
        };
      if (u.includes("/aliments/search") || u.includes("/aliments/findAll"))
        return { status: 200, ok: true, json: async () => ({ data: cat }) };
      return { status: 200, ok: true, json: async () => ({ data: [] }) };
    };
  }, CATALOGO);

  await p.goto("file://" + __dirname + "/../../frontend/diets.html");
  await p.waitForFunction(() => typeof window.fsmQtyStep === "function", {
    timeout: 8000,
  });

  let f = 0;
  const ck = (n, c, x) => {
    console.log(
      (c ? "OK   " : "FALLO ") + n + (c ? "" : " -> " + JSON.stringify(x)),
    );
    if (!c) f++;
  };

  // Se elige un alimento como lo hace la pantalla: por su ficha en la caché.
  const elegir = (id) =>
    p.evaluate(
      (datos) => {
        _fsmCache[datos.id] = datos.al;
        _fsmMid = 1;
        fsmSelect(datos.id);
      },
      { id, al: CATALOGO.find((a) => a.id === id) },
    );
  const cantidad = () => p.evaluate(() => _fsmQty);
  const atajos = () =>
    p.$$eval(".fsm-qty-preset", (ns) => ns.map((n) => n.textContent.trim()));
  const unidadEnPantalla = () => p.textContent("#fsmQtyUnit");

  // ── El caso de la captura ────────────────────────────────────────────────
  await elegir("a-bigmac");
  await p.waitForTimeout(150);
  ck("arranca en 1 unidad", (await cantidad()) === 1, await cantidad());
  ck(
    "y lo dice en la caja",
    (await unidadEnPantalla()).trim() === "ud",
    await unidadEnPantalla(),
  );

  await p.evaluate(() => fsmQtyStep(1));
  ck(
    "EL «+» SUMA DE UNO EN UNO, no de diez en diez",
    (await cantidad()) === 2,
    await cantidad(),
  );
  await p.evaluate(() => {
    fsmQtyStep(1);
    fsmQtyStep(1);
  });
  ck("y sigue: 3, 4", (await cantidad()) === 4, await cantidad());
  await p.evaluate(() => fsmQtyStep(-1));
  ck("el «−» resta igual", (await cantidad()) === 3, await cantidad());

  ck(
    "LOS ATAJOS SON 1, 2, 3… y no 50, 100, 150",
    JSON.stringify(await atajos()) ===
      JSON.stringify(["1 ud", "2 ud", "3 ud", "4 ud", "5 ud"]),
    await atajos(),
  );

  // ── Las otras formas de escribir lo mismo ────────────────────────────────
  await elegir("a-huevo");
  await p.waitForTimeout(120);
  await p.evaluate(() => fsmQtyStep(1));
  ck("«u» también es una unidad", (await cantidad()) === 2, await cantidad());

  await elegir("a-taza");
  await p.waitForTimeout(120);
  await p.evaluate(() => fsmQtyStep(1));
  ck(
    "y «tz», que es como el catálogo guarda las tazas",
    (await cantidad()) === 2,
    await cantidad(),
  );

  // ── Lo que va por peso no cambia ─────────────────────────────────────────
  for (const [id, nombre] of [
    ["a-pollo", "gr"],
    ["a-aceite", "g"],
    ["a-leche", "ml"],
  ]) {
    await elegir(id);
    await p.waitForTimeout(120);
    const antes = await cantidad();
    await p.evaluate(() => fsmQtyStep(1));
    ck(
      "en " + nombre + " sigue subiendo de diez en diez",
      (await cantidad()) === antes + 10,
      { antes, ahora: await cantidad() },
    );
  }
  await elegir("a-pollo");
  await p.waitForTimeout(120);
  ck(
    "con sus atajos en gramos",
    JSON.stringify(await atajos()) ===
      JSON.stringify(["50g", "100g", "150g", "200g", "250g"]),
    await atajos(),
  );

  // ── Y el aporte que se enseña no se mueve por esto ───────────────────────
  await elegir("a-bigmac");
  await p.waitForTimeout(120);
  await p.evaluate(() => fsmSetQty(2));
  ck(
    "dos Big Mac son 1180 kcal",
    (await p.textContent("#fsmPorK")).trim() === "1180",
    await p.textContent("#fsmPorK"),
  );
  await elegir("a-pollo");
  await p.waitForTimeout(120);
  await p.evaluate(() => fsmSetQty(200));
  ck(
    "y 200 g de pollo siguen siendo el doble de su ficha",
    (await p.textContent("#fsmPorK")).trim() === "1180",
    await p.textContent("#fsmPorK"),
  );

  ck("sin errores de JS", errs.length === 0, errs);
  await b.close();
  process.exit(f ? 1 : 0);
})();
