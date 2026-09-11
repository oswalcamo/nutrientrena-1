/* La pantalla de Equipo del panel, como el prototipo.

   Lo que antes era una rejilla de fichas con la foto centrada arriba y un
   botón "Ver clientes" ahora tiene cabecera con recuento, cuatro cifras del
   equipo, filtro por oficio y tarjetas con su pie de dos acciones.

   Tres cosas que esta prueba sujeta y que son fáciles de romper sin notarlo:

     · Que las cifras de arriba sean del equipo ENTERO y no se recalculen al
       filtrar. Si se recalcularan, pulsar "Nutricionista" diría que la empresa
       gasta 950€ al mes en vez de 3170€, que es una respuesta falsa a una
       pregunta que nadie ha hecho.
     · Que "Ingreso/miembro" NO invente una cifra. No hay registro de cobros en
       el proyecto —la misma decisión ya está tomada para el MRR de las
       cuentas—, así que sumar tarifas aquí sería enseñar dinero que nadie ha
       cobrado, y justo donde se decide cuánto cobra la gente.
     · Que el filtro solo ofrezca los oficios que de verdad hay.

   Se carga la PÁGINA de verdad, con el servidor de mentira.
*/
const { chromium } = require('../_pw');

const STAFF = [
  { id: 'ud-1', name: 'Sergio', last_name: 'García', email: 'sergio@alzum.io', photo: null },
  { id: 'ud-2', name: 'Laura', last_name: 'Mínguez', email: 'laura@alzum.io', photo: null },
  { id: 'ud-3', name: 'Marcos', last_name: 'Ruiz', email: 'marcos@alzum.io', photo: null },
];
const TEAM = [
  { id: 1, user_detail_id: 'ud-1', role_label: 'Entrenador', client_count: 3, hours_week: 20,
    salary_fijo: 900, commission: 0, currency: 'EUR', permissions: { ver: 1 },
    notes: 'Tiempo parcial. Bonus trimestral si supera 15 clientes.' },
  { id: 2, user_detail_id: 'ud-2', role_label: 'Nutricionista', client_count: 2, hours_week: 25,
    salary_fijo: 800, commission: 150, currency: 'EUR', permissions: { ver: 1 },
    notes: 'Fijo + 50€ por cada cliente que cierre directamente.' },
  { id: 3, user_detail_id: 'ud-3', role_label: 'Coach mixto', client_count: 5, hours_week: 30,
    salary_fijo: 1100, commission: 220, currency: 'EUR', permissions: { ver: 1 },
    notes: 'Trabaja entrenamiento + nutrición. Comisión por adherencia.' },
];

(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1500, height: 1050 } })).newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(String(e)));
  p.on('console', m => { if (m.type() === 'error') errs.push('consola: ' + m.text()); });

  await p.addInitScript((d) => {
    if (window.top !== window) return;
    localStorage.setItem('token', 't'); localStorage.setItem('role_id', '2');
    localStorage.removeItem('org_context');
    const ok = (data) => ({ status: 200, ok: true, json: async () => ({ data }) });
    window.fetch = async (url) => {
      const u = String(url);
      if (u.includes('/auth/me')) return ok({ name: 'Admin', email: 'admin@alzum.io',
        roles: [{ id: 2, name: 'ADMIN' }], user_id: 1 });
      if (u.includes('/users/coach/findAll')) return ok(d.STAFF);
      if (/\/users\/(admin|setter|closer)\/findAll/.test(u)) return ok([]);
      if (u.includes('/team')) return ok(d.TEAM);
      if (u.includes('/chat/unread-count')) return ok({ total: 0, conversations: [] });
      return ok([]);
    };
  }, { STAFF, TEAM });

  await p.goto('file://' + __dirname + '/../../frontend/coaches.html');

  let f = 0;
  const ck = (n, c, x) => { console.log((c ? 'OK   ' : 'FALLO ') + n + (c ? '' : ' -> ' + JSON.stringify(x))); if (!c) f++; };

  let pintada = true;
  try {
    await p.waitForFunction(() => document.querySelectorAll('.member-card').length === 3, { timeout: 8000 });
  } catch (e) { pintada = false; }
  ck('el equipo se pinta', pintada, await p.textContent('#cardsGrid').catch(() => null));

  // ── La cabecera ──────────────────────────────────────────────────────────
  ck('lleva su rótulo de sección',
    (await p.textContent('.pg-sobre')).trim().toLowerCase() === 'coaches y colaboradores',
    await p.textContent('.pg-sobre'));
  ck('y el recuento sale de los datos, no escrito a mano',
    (await p.textContent('#pgSub')) === '3 miembros activos · 10 clientes atendidos en total',
    await p.textContent('#pgSub'));

  // ── Las cuatro cifras ────────────────────────────────────────────────────
  const cifras = () => p.$$eval('.res-card', ns => ns.map(n => ({
    v: n.querySelector('.res-v').textContent.trim(),
    l: n.querySelector('.res-l').textContent.trim(),
  })));
  const c0 = await cifras();
  ck('están las cuatro cifras del equipo', c0.length === 4, c0);
  ck('miembros', c0[0].v === '3', c0[0]);
  ck('COSTE MENSUAL SUMA SALARIOS Y COMISIONES', c0[1].v === '3170€', c0[1]);
  ck('permisos asignados, en porcentaje', c0[3].v === '100%', c0[3]);
  /* Sin registro de cobros no hay ingreso que enseñar. */
  ck('INGRESO/MIEMBRO NO SE INVENTA', c0[2].v === '—', c0[2]);
  ck('y dice por qué está vacío',
    (await p.textContent('.res-card:nth-child(3) .res-n')).includes('Sin registro de cobros'),
    await p.textContent('.res-card:nth-child(3) .res-n'));

  // ── El filtro ────────────────────────────────────────────────────────────
  const chips = () => p.$$eval('.flt-chip', ns => ns.map(n => n.textContent.trim()));
  ck('el filtro ofrece los oficios que hay, y nada más',
    (await chips()).join() === 'Todos,Entrenador,Nutricionista,Coach mixto', await chips());
  ck('empieza en Todos',
    (await p.textContent('.flt-chip.on')).trim() === 'Todos', await p.textContent('.flt-chip.on'));
  ck('con su cuenta', (await p.textContent('.flt-cuenta')).includes('3 de 3'),
    await p.textContent('.flt-cuenta'));

  await p.locator('.flt-chip', { hasText: 'Nutricionista' }).click();
  await p.waitForTimeout(300);
  const nombres = await p.$$eval('.member-card .card-name', ns => ns.map(n => n.textContent.trim()));
  ck('FILTRAR DEJA SOLO ESE OFICIO', nombres.join() === 'Laura Mínguez', nombres);
  ck('y la cuenta lo dice', (await p.textContent('.flt-cuenta')).includes('1 de 3'),
    await p.textContent('.flt-cuenta'));
  /* Lo importante: el coste del equipo NO baja por haber filtrado. */
  const c1 = await cifras();
  ck('LAS CIFRAS SIGUEN SIENDO LAS DEL EQUIPO ENTERO',
    JSON.stringify(c1) === JSON.stringify(c0), { antes: c0.map(c => c.v), despues: c1.map(c => c.v) });
  ck('y la tarjeta de añadir no cuelga de un filtro',
    (await p.locator('.add-card').count()) === 0);

  await p.locator('.flt-chip', { hasText: 'Todos' }).click();
  await p.waitForTimeout(300);
  ck('al volver a Todos vuelven los tres',
    (await p.locator('.member-card').count()) === 3);
  ck('y reaparece la tarjeta de añadir', (await p.locator('.add-card').count()) === 1);

  // ── La tarjeta ───────────────────────────────────────────────────────────
  const primera = p.locator('.member-card').first();
  ck('el oficio sale en su pastilla',
    (await primera.locator('.card-role-badge').textContent()).trim() === 'Entrenador',
    await primera.locator('.card-role-badge').textContent());
  ck('con sus clientes y sus horas',
    (await primera.locator('.card-datos').textContent()).replace(/\s+/g, ' ').includes('3 clientes')
    && (await primera.locator('.card-datos').textContent()).includes('20'),
    await primera.locator('.card-datos').textContent());
  /* `fmt()` ya traía el "/mes" pegado: al añadirlo otra vez para poder pintarlo
     en gris salía "900€/mes/mes". */
  ck('el sueldo no repite el "/mes"',
    !(await primera.locator('.salary-box').textContent()).includes('/mes/mes'),
    await primera.locator('.salary-box').textContent());
  ck('y el total se calcula, no se copia',
    (await p.locator('.member-card').nth(1).locator('.salary-val.total').textContent()).includes('950'),
    await p.locator('.member-card').nth(1).locator('.salary-val.total').textContent());

  const acciones = await primera.locator('.card-act').allTextContents();
  ck('el pie tiene las dos acciones del prototipo',
    acciones.map(t => t.trim()).join() === 'Permisos,Clientes (3)', acciones);

  // ── Permisos abre la ficha en su pestaña ─────────────────────────────────
  await primera.locator('.card-act', { hasText: 'Permisos' }).click();
  await p.waitForTimeout(400);
  ck('PERMISOS ABRE LA FICHA DEL MIEMBRO',
    await p.$eval('#modalOverlay', e => e.style.display === 'flex'),
    await p.$eval('#modalOverlay', e => e.style.display));
  ck('y directamente en su pestaña, sin pasar por salario y horas',
    await p.$eval('#tab3', e => e.classList.contains('active')));

  ck('sin errores de JS', errs.length === 0, errs);
  await b.close();
  process.exit(f ? 1 : 0);
})();
