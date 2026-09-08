/* El objetivo de la dieta: lo escrito frente a lo sumado.

   La lista rellena las cifras que el coach no escribió con lo que suman los
   alimentos —una dieta sin objetivo no sale con cuatro guiones al lado de sus
   comidas—, y `/edit` devuelve esa misma respuesta rellena.

   El editor cargaba ESO en las casillas del objetivo. Al guardar, la suma
   quedaba almacenada como si alguien la hubiera tecleado, y desde ese momento
   la cifra estaba congelada: se duplicaba la dieta, se le añadía un alimento
   y la lista seguía diciendo las kcal de la original.

   Lo que hay que dejar sujeto:

     · Que las casillas del objetivo lleven lo ESCRITO, no lo sumado.
     · Que guardar una dieta sin objetivo no le invente uno.
     · Y que una con objetivo de verdad lo conserve.

   Se carga la PÁGINA de verdad, con el servidor de mentira.
*/
const { chromium } = require('../_pw');

const al = (id, nombre, kcal) => ({
  id, name: nombre, calories: kcal, proteins: 0.5, carbohydrates: 3, fats: 99,
  quantity: 100, quantity_unit: 'g', group_food_id: 1,
});

// «dia martes» de la captura: sin objetivo escrito. `calories` y `detail`
// vienen RELLENOS con lo que suman sus alimentos, que es lo que engañaba.
const SIN_OBJETIVO = {
  id: 'd-libre', title: 'dia martes', goal_mode: 'libre',
  calories: 1572, notes: null, type_id: null, pathologies: [],
  detail: { proteins: 8, carbs: 0, fats: 171 },
  objetivo: { calories: null, proteins: null, carbs: null, fats: null, fiber: null },
  foods: [{ id: 11, name: 'Media mañana', time: '11:00', subtitle: null, detail: [
    { id: 101, aliment_id: 'a-aceite', quantity: 100, order: 0, aliment: al('a-aceite', 'Aceite de cacahuete', 899) },
    { id: 102, aliment_id: 'a-tocino', quantity: 100, order: 1, aliment: al('a-tocino', 'Tocino', 673) },
  ] }],
};

// Una plantilla de verdad: el coach escribió 1800 kcal y 120 g de proteína.
const CON_OBJETIVO = Object.assign({}, SIN_OBJETIVO, {
  id: 'd-meta', title: 'Plantilla 1800', goal_mode: 'macros',
  calories: 1800, detail: { proteins: 120, carbs: 0, fats: 171 },
  objetivo: { calories: 1800, proteins: 120, carbs: null, fats: null, fiber: null },
});

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.setViewportSize({ width: 1400, height: 1000 });
  const errs = []; p.on('pageerror', e => errs.push(String(e)));

  await p.addInitScript((dietas) => {
    if (window.top !== window) return;
    localStorage.setItem('token', 't'); localStorage.setItem('role_id', '5');
    window.__enviado = [];
    window.fetch = async (url, opts) => {
      const u = String(url); opts = opts || {};
      if (opts.method && opts.method !== 'GET') {
        window.__enviado.push({ url: u, cuerpo: opts.body ? JSON.parse(opts.body) : null });
        return { status: 200, ok: true, json: async () => ({ data: { id: 'd-nueva', foods: [] } }) };
      }
      const id = Object.keys(dietas).find(k => u.includes('/diets/' + k + '/edit'));
      if (id) return { status: 200, ok: true, json: async () => ({ data: dietas[id] }) };
      if (u.includes('/auth/me')) return { status: 200, ok: true, json: async () => ({ data: { id: 1, role_id: 5 } }) };
      return { status: 200, ok: true, json: async () => ({ data: [] }) };
    };
  }, { 'd-libre': SIN_OBJETIVO, 'd-meta': CON_OBJETIVO });

  await p.goto('file://' + __dirname + '/../../frontend/diets.html');
  await p.waitForFunction(() => typeof window.duplicateDiet === 'function', { timeout: 8000 });

  let f = 0;
  const ck = (n, c, x) => { console.log((c ? 'OK   ' : 'FALLO ') + n + (c ? '' : ' -> ' + JSON.stringify(x))); if (!c) f++; };
  const ultimo = async () => (await p.evaluate(() => window.__enviado)).slice(-1)[0] || {};

  // ── Una dieta sin objetivo escrito ───────────────────────────────────────
  await p.evaluate(() => openForm('d-libre'));
  await p.waitForTimeout(350);

  const casillas = await p.evaluate(() => ({
    kcal: document.getElementById('f_calories').value,
    prot: document.getElementById('f_proteins').value,
    grasa: document.getElementById('f_fats').value,
  }));
  ck('LAS CASILLAS DEL OBJETIVO SALEN VACIAS, no con la suma de los alimentos',
    casillas.kcal === '' && casillas.prot === '' && casillas.grasa === '', casillas);
  ck('y el objetivo queda en «libre»',
    await p.evaluate(() => _goalMode) === 'libre', await p.evaluate(() => _goalMode));

  // ── Se duplica y se le añade un alimento ─────────────────────────────────
  await p.evaluate(() => duplicateDiet('d-libre'));
  await p.waitForTimeout(350);
  await p.evaluate(() => {
    addFoodRow(_meals[0].id, { aliment_id: 'a-acedera', aliment_name: 'Acedera',
      calories: 33, proteins: 2, carbohydrates: 3, fats: 0, porcion: 100, quantity: 100 });
  });
  await p.evaluate(() => saveDiet());
  await p.waitForTimeout(350);

  const copia = await ultimo();
  ck('la copia se crea', /\/diets$/.test(copia.url || ''), copia.url);
  ck('con los tres alimentos', (copia.cuerpo.foods[0].detail || []).length === 3,
    (copia.cuerpo.foods[0].detail || []).length);
  ck('NO SE LE CUELA UN OBJETIVO QUE NADIE ESCRIBIO',
    copia.cuerpo.calories === null && copia.cuerpo.proteins === null
    && copia.cuerpo.carbs === null && copia.cuerpo.fats === null,
    { kcal: copia.cuerpo.calories, prot: copia.cuerpo.proteins,
      carb: copia.cuerpo.carbs, grasa: copia.cuerpo.fats });

  // ── Y una con objetivo de verdad ─────────────────────────────────────────
  await p.evaluate(() => { window.__enviado = []; openForm('d-meta'); });
  await p.waitForTimeout(350);
  const meta = await p.evaluate(() => ({
    kcal: document.getElementById('f_calories').value,
    prot: document.getElementById('f_proteins').value,
    carb: document.getElementById('f_carbs').value,
    modo: _goalMode,
  }));
  ck('lo que el coach SI escribio sale en su casilla',
    meta.kcal === '1800' && meta.prot === '120', meta);
  ck('y lo que no escribio sigue vacio, aunque la lista lo rellene',
    meta.carb === '', meta.carb);
  ck('con su modo', meta.modo === 'macros', meta.modo);

  await p.evaluate(() => saveDiet());
  await p.waitForTimeout(350);
  const guardada = await ultimo();
  ck('AL GUARDARLA CONSERVA SU OBJETIVO',
    guardada.cuerpo.calories === 1800 && guardada.cuerpo.proteins === 120,
    { kcal: guardada.cuerpo.calories, prot: guardada.cuerpo.proteins });
  ck('y no se le inventan los macros que no tenia',
    guardada.cuerpo.carbs === null && guardada.cuerpo.fats === null,
    { carb: guardada.cuerpo.carbs, grasa: guardada.cuerpo.fats });

  ck('sin errores de JS', errs.length === 0, errs);
  await b.close();
  process.exit(f ? 1 : 0);
})();
