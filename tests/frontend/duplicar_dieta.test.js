/* Duplicar una dieta, desde el editor.

   «Duplicar» no copia nada en el servidor: abre el editor con la dieta
   cargada, le quita el identificador y deja que el coach guarde. Pero el
   editor viene de la OTRA dieta, y cada comida y cada fila seguía llevando el
   identificador de aquélla. Al guardar, el servidor buscaba esas comidas entre
   las de una dieta que acababa de crear —donde no existe ninguna— y se las
   saltaba: la copia se creaba con su título y VACÍA.

   Aquí se mira lo que sale por el cable: el payload que manda la pantalla.

   Se carga la PÁGINA de verdad, con el servidor de mentira.
*/
const { chromium } = require('../_pw');

const al = (id, nombre) => ({
  id, name: nombre, calories: 165, proteins: 10, carbohydrates: 1, fats: 5,
  quantity: 100, quantity_unit: 'g', group_food_id: 1,
});

// La dieta de la que se copia: dos comidas, tres alimentos, con sus ids.
const DIETA = {
  id: 'd-original', title: 'Volumen', calories: 2200, notes: 'sin lactosa',
  type_id: null, detail: { proteins: 180, carbs: 220, fats: 70 }, pathologies: [],
  foods: [
    { id: 11, name: 'Desayuno', time: '08:00', subtitle: 'Huevos revueltos', detail: [
      { id: 101, aliment_id: 'a-huevo', quantity: 3, order: 0, aliment: al('a-huevo', 'Huevo') },
    ] },
    { id: 12, name: 'Comida', time: '14:00', subtitle: null, detail: [
      { id: 102, aliment_id: 'a-pollo', quantity: 150, order: 0, aliment: al('a-pollo', 'Pollo') },
      { id: 103, aliment_id: 'a-arroz', quantity: 80,  order: 1, aliment: al('a-arroz', 'Arroz') },
    ] },
  ],
};

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.setViewportSize({ width: 1400, height: 1000 });
  const errs = []; p.on('pageerror', e => errs.push(String(e)));

  await p.addInitScript((dieta) => {
    localStorage.setItem('token', 't'); localStorage.setItem('role_id', '5');
    window.__enviado = [];
    window.fetch = async (url, opts) => {
      const u = String(url);
      opts = opts || {};
      if (opts.method && opts.method !== 'GET') {
        window.__enviado.push({ url: u, metodo: opts.method,
                                cuerpo: opts.body ? JSON.parse(opts.body) : null });
        return { status: 200, ok: true,
                 json: async () => ({ data: { id: 'd-copia', title: 'Volumen (Copia)', foods: [] } }) };
      }
      let data = [];
      if (u.includes('/diets/' + dieta.id + '/edit')) data = dieta;
      else if (u.includes('/auth/me')) data = { id: 1, name: 'Coach', role_id: 5 };
      return { status: 200, ok: true, json: async () => ({ data }) };
    };
  }, DIETA);

  await p.goto('file://' + __dirname + '/../../frontend/diets.html');
  await p.waitForFunction(() => typeof window.duplicateDiet === 'function', { timeout: 8000 });

  let f = 0;
  const ck = (n, c, x) => { console.log((c ? 'OK   ' : 'FALLO ') + n + (c ? '' : ' -> ' + JSON.stringify(x))); if (!c) f++; };

  // ── Se duplica ───────────────────────────────────────────────────────────
  await p.evaluate(() => duplicateDiet('d-original'));
  await p.waitForTimeout(300);

  ck('el editor se abre en modo copia',
    await p.textContent('#formViewTitle') === 'Duplicar dieta',
    await p.textContent('#formViewTitle'));
  ck('con el título marcado',
    (await p.inputValue('#f_title')).endsWith('(Copia)'), await p.inputValue('#f_title'));
  ck('y el botón dice crear, que no se está editando nada',
    (await p.textContent('#dpSaveLbl')).toLowerCase().includes('crear'),
    await p.textContent('#dpSaveLbl'));

  // ── Lo que sale por el cable ─────────────────────────────────────────────
  await p.evaluate(() => saveDiet());
  await p.waitForTimeout(300);
  const envios = await p.evaluate(() => window.__enviado);
  ck('se manda una sola petición', envios.length === 1, envios.map(e => e.url + ' ' + e.metodo));

  const env = envios[0] || {};
  ck('SE CREA UNA DIETA NUEVA, no se actualiza la original',
    env.metodo === 'POST' && /\/diets$/.test(env.url), env.url + ' ' + env.metodo);

  const cuerpo = env.cuerpo || {};
  ck('la copia no dice ser la original', !cuerpo.id, cuerpo.id);
  ck('LLEVA SUS DOS COMIDAS, no se manda vacía',
    (cuerpo.foods || []).length === 2, (cuerpo.foods || []).map(c => c.name));
  ck('con sus tres alimentos',
    (cuerpo.foods || []).reduce((n, c) => n + (c.detail || []).length, 0) === 3,
    (cuerpo.foods || []).map(c => (c.detail || []).length));

  // Lo que hacía que el servidor las descartara.
  const idsComida = (cuerpo.foods || []).map(c => c.id).filter(x => x != null);
  const idsFila = (cuerpo.foods || []).flatMap(c => (c.detail || []).map(d => d.id)).filter(x => x != null);
  ck('NINGUNA COMIDA LLEVA EL IDENTIFICADOR DE LA ORIGINAL', idsComida.length === 0, idsComida);
  ck('NINGUNA FILA TAMPOCO', idsFila.length === 0, idsFila);

  // Y lo que sí tiene que viajar: el contenido.
  const nombres = (cuerpo.foods || []).map(c => c.name).join(',');
  ck('las comidas son las de la dieta copiada', nombres === 'Desayuno,Comida', nombres);
  ck('con su hora y su subtítulo',
    (cuerpo.foods || [])[0] && cuerpo.foods[0].time === '08:00'
    && cuerpo.foods[0].subtitle === 'Huevos revueltos', (cuerpo.foods || [])[0]);
  const cantidades = (cuerpo.foods || []).flatMap(c => (c.detail || []).map(d => d.quantity_calc));
  ck('y las cantidades de cada alimento',
    JSON.stringify(cantidades) === JSON.stringify([3, 150, 80]), cantidades);
  const alimentos = (cuerpo.foods || []).flatMap(c => (c.detail || []).map(d => d.aliment_id));
  ck('apuntando a los mismos alimentos del catálogo',
    JSON.stringify(alimentos) === JSON.stringify(['a-huevo', 'a-pollo', 'a-arroz']), alimentos);
  ck('y con los objetivos de la original', cuerpo.calories === 2200 && cuerpo.notes === 'sin lactosa',
    { calories: cuerpo.calories, notes: cuerpo.notes });

  ck('sin errores de JS', errs.length === 0, errs);
  await b.close();
  process.exit(f ? 1 : 0);
})();
