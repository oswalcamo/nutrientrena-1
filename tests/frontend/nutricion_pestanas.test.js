/* Nutrición del cliente: las dos pestañas del prototipo.

   Tres cosas que la pantalla no tenía:

     · "Mi plan" y "Recetas". El catálogo lo suben el coach y el centro y
       existe desde hace tiempo, pero el cliente no podía verlo por ningún
       lado —ningún endpoint de recetas le dejaba entrar—, así que la pestaña
       no se podía ni dibujar.
     · "Ver recetas para cambiar una comida", y el 🔄 de cada comida, que
       llevan a la segunda pestaña ya filtrada por la comida que se cambia.
     · "Marcar día como completado", que es lo que mueve la barra de
       "consumido hoy" — y por eso decía siempre 0.

   Se carga la PÁGINA de verdad, con el servidor de mentira.
*/
const { chromium } = require('../_pw');

const COMIDAS = [
  { name: 'Desayuno', time: '08:00', kcal: 520, subtitle: 'Avena con plátano y claras',
    foods: [{ name: 'Avena', quantity: 80, unit: 'g' }] },
  { name: 'Comida', time: '14:00', kcal: 680, subtitle: 'Lentejas con arroz', foods: [] },
  { name: 'Cena', time: '20:30', kcal: 470, subtitle: 'Salmón al horno', foods: [] },
];

/* Lunes de una semana con hoy en medio: hacen falta un día pasado, hoy y uno
   futuro para poder comprobar los tres estados del botón. */
const HOY = new Date();
const iso = (d) => d.toISOString().slice(0, 10);
const masDias = (n) => { const d = new Date(HOY); d.setDate(d.getDate() + n); return iso(d); };

const DIAS = [
  { day_index: 0, label: 'L', name: 'Ayer', date: masDias(-1), is_today: false,
    has_diet: true, completed: false, kcal: 2100, protein: 175, carbs: 210, fats: 65, meals: COMIDAS },
  { day_index: 1, label: 'M', name: 'Hoy', date: masDias(0), is_today: true,
    has_diet: true, completed: false, kcal: 2100, protein: 175, carbs: 210, fats: 65, meals: COMIDAS },
  { day_index: 2, label: 'X', name: 'Mañana', date: masDias(1), is_today: false,
    has_diet: true, completed: false, kcal: 2100, protein: 175, carbs: 210, fats: 65, meals: COMIDAS },
];

const RECETAS = [
  { id: 1, name: 'Arroz con pollo', image: null, kcal: 540, prep_time: 30, meal_type: 'Comida' },
  { id: 2, name: 'Yogur con fruta', image: null, kcal: 320, prep_time: 5, meal_type: 'Desayuno' },
  { id: 3, name: 'Salmón al horno', image: null, kcal: 480, prep_time: 25, meal_type: 'Cena' },
  { id: 4, name: 'Merluza a la plancha', image: null, kcal: 300, prep_time: 15, meal_type: 'Cena' },
];

(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 420, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(String(e)));

  await p.addInitScript((d) => {
    if (window.top !== window) return;
    localStorage.setItem('token', 't'); localStorage.setItem('role_id', '6');
    window.__post = [];
    const ok = (data) => ({ status: 200, ok: true, json: async () => ({ data }) });
    window.fetch = async (url, opt) => {
      const u = String(url);
      const metodo = (opt && opt.method) || 'GET';
      if (metodo === 'POST') {
        window.__post.push({ url: u, body: opt && opt.body });
        return ok({});
      }
      if (u.includes('/auth/me')) return ok({ name: 'Carlos', user_id: 9 });
      if (u.includes('/client/recipes')) {
        const q = new URLSearchParams(u.split('?')[1] || '');
        let items = d.RECETAS;
        if (q.get('meal_type')) items = items.filter(r => r.meal_type === q.get('meal_type'));
        if (q.get('search')) items = items.filter(
          r => r.name.toLowerCase().includes(q.get('search').toLowerCase()));
        return ok({ items, total: items.length, page: 1, per_page: 24, last_page: 1,
                    meal_types: ['Desayuno', 'Comida', 'Cena'] });
      }
      if (u.includes('/client/nutrition')) return ok({
        menu: { name: 'Plan' }, week_start: d.DIAS[0].date, plan_semanal: true, days: d.DIAS });
      if (u.includes('/chat/unread-count')) return ok({ total: 0, conversations: [] });
      return ok({});
    };
  }, { RECETAS, DIAS });

  await p.goto('file://' + __dirname + '/../../frontend/client-nutricion.html');

  let f = 0;
  const ck = (n, c, x) => { console.log((c ? 'OK   ' : 'FALLO ') + n + (c ? '' : ' -> ' + JSON.stringify(x))); if (!c) f++; };

  let pintada = true;
  try {
    await p.waitForFunction(() => document.querySelectorAll('.meal-card').length > 0, { timeout: 8000 });
  } catch (e) { pintada = false; }
  ck('el plan se pinta', pintada, await p.textContent('#daybox'));

  // ── Las dos pestañas ─────────────────────────────────────────────────────
  const rotulos = () => p.$$eval('.nt-tab', ns => ns.map(n => n.textContent.trim()));
  ck('HAY DOS PESTAÑAS', (await rotulos()).length === 2, await rotulos());
  ck('y la de recetas dice cuántas hay',
    (await p.textContent('#tabRecetas')).includes('(4)'), await p.textContent('#tabRecetas'));
  ck('se entra por Mi plan',
    await p.$eval('#panelPlan', e => e.style.display !== 'none'));

  // ── Consumido hoy ────────────────────────────────────────────────────────
  ck('"consumido hoy" empieza a cero',
    (await p.textContent('.cons-fila span')).replace(/\s+/g, ' ').trim() === '0 / 2100 kcal',
    await p.textContent('.cons-fila span'));
  ck('y la barra está vacía',
    await p.$eval('.cons-barra i', e => e.style.width === '0%'),
    await p.$eval('.cons-barra i', e => e.style.width));

  // ── Marcar el día ────────────────────────────────────────────────────────
  await p.click('#btnDia');
  await p.waitForTimeout(600);
  const llamadas = await p.evaluate(() => window.__post);
  ck('MARCAR EL DÍA LO GUARDA EN EL SERVIDOR',
    llamadas.some(l => l.url.includes('/client/nutrition/day/') && l.url.includes('/completado')
                  && String(l.body).includes('true')), llamadas);
  ck('el botón pasa a decir que está hecho',
    (await p.textContent('#btnDia')).includes('completado')
    && await p.$eval('#btnDia', e => e.classList.contains('hecho')),
    await p.textContent('#btnDia'));
  ck('Y LA BARRA SE LLENA, que es lo que decía 0 para siempre',
    (await p.textContent('.cons-fila span')).replace(/\s+/g, ' ').trim() === '2100 / 2100 kcal',
    await p.textContent('.cons-fila span'));

  await p.click('#btnDia');
  await p.waitForTimeout(600);
  const post2 = await p.evaluate(() => window.__post);
  ck('se puede desmarcar, no es un botón de un solo sentido',
    String(post2[post2.length - 1].body).includes('false'), post2[post2.length - 1]);
  ck('y vuelve a cero',
    (await p.textContent('.cons-fila span')).replace(/\s+/g, ' ').trim() === '0 / 2100 kcal',
    await p.textContent('.cons-fila span'));

  // ── Un día que todavía no ha llegado ─────────────────────────────────────
  await p.locator('.wday, .weekbar > *').nth(2).click();
  await p.waitForTimeout(400);
  ck('el día de mañana no se puede marcar',
    await p.$eval('#btnDia', e => e.disabled), await p.textContent('#btnDia'));
  await p.locator('.wday, .weekbar > *').nth(1).click();
  await p.waitForTimeout(400);

  // ── Cambiar una comida ───────────────────────────────────────────────────
  await p.click('.btn-cambiar');
  await p.waitForTimeout(800);
  ck('"VER RECETAS PARA CAMBIAR UNA COMIDA" LLEVA A LA PESTAÑA DE RECETAS',
    await p.$eval('#panelRecetas', e => e.style.display !== 'none')
    && await p.$eval('#panelPlan', e => e.style.display === 'none'));
  ck('y la lista de la compra, que es del plan, se quita de en medio',
    await p.$eval('#btnLista', e => e.style.display === 'none'));

  const tarjetas = () => p.$$eval('.rc-card .rc-nm', ns => ns.map(n => n.textContent.trim()));
  ck('salen todas las recetas', (await tarjetas()).length === 4, await tarjetas());

  // ── El 🔄 de UNA comida ──────────────────────────────────────────────────
  await p.click('#tabPlan');
  await p.waitForTimeout(400);
  /* La de LA COMIDA CUYO 🔄 se pulsa, no la primera: mirando otra tarjeta la
     comprobación pasa siempre, haya o no `stopPropagation`. */
  const abiertaAntes = await p.locator('.meal-card').nth(2)
    .evaluate(e => e.classList.contains('open'));
  await p.locator('.meal-card').nth(2).locator('.meal-swap').click();   // Cena
  await p.waitForTimeout(900);
  ck('EL 🔄 DE UNA COMIDA LLEVA A RECETAS FILTRADA POR ESA COMIDA',
    (await tarjetas()).every(n => ['Salmón al horno', 'Merluza a la plancha'].includes(n)),
    await tarjetas());
  ck('y las que encajan se marcan',
    (await p.locator('.rc-encaja').count()) === 2
    && (await p.locator('.rc-encaja').first().textContent()).toLowerCase().includes('cena'),
    await p.locator('.rc-encaja').first().textContent().catch(() => null));
  ck('la pastilla de esa comida queda encendida',
    (await p.locator('.rc-chip.on').textContent()) === 'Cena',
    await p.locator('.rc-chip.on').textContent());

  // Tocar el 🔄 no puede además abrir o cerrar la comida de debajo.
  await p.click('#tabPlan');
  await p.waitForTimeout(400);
  ck('el 🔄 no abre ni cierra la comida al pulsarlo',
    await p.locator('.meal-card').nth(2)
      .evaluate(e => e.classList.contains('open')) === abiertaAntes,
    { antes: abiertaAntes });

  // ── El buscador ──────────────────────────────────────────────────────────
  await p.click('#tabRecetas');
  await p.waitForTimeout(500);
  await p.fill('#rcBuscar', 'yogur');
  await p.waitForTimeout(900);
  ck('el buscador filtra',
    (await tarjetas()).join() === 'Yogur con fruta', await tarjetas());
  await p.fill('#rcBuscar', 'zzzzz');
  await p.waitForTimeout(900);
  ck('y sin resultados lo dice, no se queda en blanco',
    (await p.textContent('#rcGrid')).includes('Ninguna receta'),
    await p.textContent('#rcGrid'));

  ck('sin errores de JS', errs.length === 0, errs);
  await b.close();
  process.exit(f ? 1 : 0);
})();
