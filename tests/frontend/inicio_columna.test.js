/* El Inicio, en una columna.

   El saludo vivía en una franja blanca a todo lo ancho, con su raya debajo, y
   las tarjetas en otra caja aparte: la pantalla quedaba partida en dos antes
   de empezar a leer, y en un monitor grande las tarjetas se estiraban hasta
   perder la relación entre sus cifras.

   Ahora la cabecera y las tarjetas son la MISMA columna, centrada. Eso se
   sostiene con dos cosas que cualquiera puede romper sin darse cuenta —tocar
   el relleno de una y no el de la otra—, así que se miden:

     · Que el saludo empiece justo donde empieza la primera tarjeta.
     · Y que en una pantalla ancha la columna no se estire hasta los bordes.

   Se carga la PÁGINA de verdad, con el servidor de mentira.
*/
const { chromium } = require('../_pw');

const RESP = {
  '/api/auth/me': { data: { name: 'Oswal', roles: [{ name: 'Superadmin' }] } },
  '/api/analytics/overview': { data: { active_clients: 5, new_this_month: 0, total_clients: 9 } },
  '/api/checkins/bandeja': { data: { recibidos: [{ id: 1 }], esperando: [] } },
  '/api/events/search': { data: [] },
  '/api/users/clients/portfolio': { data: { stats: { activos: 5 }, clients: [
    { id: 'c1', name: 'María', last_name: 'García', sin_plan: true,
      lifecycle_status: 'activo', alta: '2026-09-05T10:00:00', precio: 250 },
  ] } },
};

const izquierda = (p, sel) => p.locator(sel).first().evaluate(n => Math.round(n.getBoundingClientRect().left));
const derecha = (p, sel) => p.locator(sel).first().evaluate(n => Math.round(n.getBoundingClientRect().right));

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  const errs = []; p.on('pageerror', e => errs.push(String(e)));

  await p.addInitScript((resp) => {
    if (window.top !== window) return;
    localStorage.setItem('token', 't'); localStorage.setItem('role_id', '1');
    window.fetch = async (url) => {
      const clave = Object.keys(resp).find(k => String(url).includes(k));
      return { status: 200, ok: true, json: async () => (clave ? resp[clave] : { data: {} }) };
    };
  }, RESP);

  let f = 0;
  const ck = (n, c, x) => { console.log((c ? 'OK   ' : 'FALLO ') + n + (c ? '' : ' -> ' + JSON.stringify(x))); if (!c) f++; };

  // ── En una pantalla ancha ────────────────────────────────────────────────
  await p.setViewportSize({ width: 1900, height: 1000 });
  await p.goto('file://' + __dirname + '/../../frontend/dashboard.html');
  await p.waitForFunction(() => document.querySelectorAll('.kpi-card').length > 0, { timeout: 8000 });
  await p.waitForTimeout(300);

  const saludoIzq = await izquierda(p, '#greetMsg');
  const tarjetaIzq = await izquierda(p, '.kpi-card');
  ck('EL SALUDO EMPIEZA DONDE EMPIEZA LA PRIMERA TARJETA',
    Math.abs(saludoIzq - tarjetaIzq) <= 1, { saludo: saludoIzq, tarjeta: tarjetaIzq });

  const ayudaDer = await derecha(p, '.head-ayuda');
  const gridDer = await derecha(p, '.kpi-grid');
  ck('y el botón de ayuda acaba donde acaban las tarjetas',
    Math.abs(ayudaDer - gridDer) <= 1, { ayuda: ayudaDer, tarjetas: gridDer });

  const ancho = await p.locator('.kpi-grid').evaluate(n => Math.round(n.getBoundingClientRect().width));
  ck('LA COLUMNA NO SE ESTIRA HASTA LOS BORDES en una pantalla ancha',
    ancho < 1300, { ancho, pantalla: 1900 });
  ck('pero tampoco se queda en un hilo', ancho > 900, ancho);

  // La franja blanca con su raya ya no está: la cabecera es página, no barra.
  const cabecera = await p.locator('.topbar').evaluate(n => {
    const e = getComputedStyle(n);
    return { fondo: e.backgroundColor, raya: e.borderBottomWidth };
  });
  ck('la cabecera ya no es una franja aparte',
    /rgba\(0, 0, 0, 0\)|transparent/.test(cabecera.fondo) && cabecera.raya === '0px', cabecera);

  // ── Y en una estrecha, sin márgenes de más ───────────────────────────────
  await p.setViewportSize({ width: 700, height: 1000 });
  await p.waitForTimeout(250);
  const estrechoIzq = await izquierda(p, '.kpi-card');
  ck('en una pantalla estrecha las tarjetas siguen cerca del borde',
    estrechoIzq < 40, estrechoIzq);
  /* Aquí quien abre la columna es el botón de menú, que en el móvil va delante
     del saludo. Es él el que tiene que alinearse con las tarjetas: si se
     alineara el título, el botón asomaría por fuera de la columna. */
  ck('y la cabecera empieza en la misma columna que ellas',
    Math.abs(await izquierda(p, '.menu-btn') - estrechoIzq) <= 1,
    { menu: await izquierda(p, '.menu-btn'), tarjeta: estrechoIzq });

  ck('sin errores de JS', errs.length === 0, errs);
  await b.close();
  process.exit(f ? 1 : 0);
})();
