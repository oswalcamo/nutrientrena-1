/* La navegación del cliente en el móvil: barra abajo, no cajón lateral.

   El cliente usa esto con el teléfono en la mano. El menú vivía detrás de una
   hamburguesa en la esquina de arriba a la izquierda —donde el pulgar no
   llega—, así que sus cinco pantallas estaban a dos gestos. Ahora están abajo
   y a un toque.

   Lo que se comprueba aquí es que las dos navegaciones no se pisan: en el
   móvil manda la de abajo y el cajón se va entero; en escritorio, al revés.
   Enseñar las dos a la vez, o ninguna, son los dos fallos posibles.

   Se cargan las PÁGINAS de verdad, con el servidor de mentira.
*/
const { chromium } = require('../_pw');

const PAG = __dirname + '/../../frontend/';

const STUB = () => {
  if (window.top !== window) return;
  localStorage.setItem('token', 't'); localStorage.setItem('role_id', '6');
  const ok = (data) => ({ status: 200, ok: true, json: async () => ({ data }) });
  window.fetch = async (url) => {
    const u = String(url);
    if (u.includes('/auth/me')) return ok({ name: 'Carlos González', user_id: 9 });
    if (u.includes('/chat/unread-count')) return ok({ total: 3, conversations: [] });
    if (u.includes('/client/chat')) return ok({ conversation_id: null, coach: null, chat_enabled: true });
    if (u.includes('/chat/conversations')) return ok([]);
    if (u.includes('/client/home')) return ok({
      profile: { name: 'Carlos González', initials: 'CG' },
      today: { weekday: 'Domingo', day: 23, month: 'Ago', es_hoy: true },
      week: { range: '17–23 Ago', days: [], offset: 0 },
      streak: 3, routine: { is_rest: true },
      plan: { id: 1, name: 'Full body', objective: 'Fuerza', days_per_week: 3 },
      menu: { weekday: 'Domingo', kcal: 2100, meals_count: 5 },
      checkin: { status: 'pending', coach_name: 'Sergio', coach_initials: 'S',
                 requested_fields: ['peso'] },
    });
    return ok({});
  };
};

(async () => {
  const b = await chromium.launch();
  let f = 0;
  const errs = [];
  const ck = (n, c, x) => { console.log((c ? 'OK   ' : 'FALLO ') + n + (c ? '' : ' -> ' + JSON.stringify(x))); if (!c) f++; };

  async function abrir(pagina, ancho) {
    const ctx = await b.newContext({ viewport: { width: ancho, height: 780 } });
    const p = await ctx.newPage();
    p.on('pageerror', e => errs.push(pagina + ': ' + e));
    await p.addInitScript(STUB);
    await p.goto('file://' + PAG + pagina);
    await p.waitForTimeout(1200);
    return { p, ctx };
  }

  const estado = (p) => p.evaluate(() => {
    const vis = (s) => {
      const el = document.querySelector(s);
      return !!el && getComputedStyle(el).display !== 'none';
    };
    const sel = document.querySelector('.nav-abajo a.sel');
    return {
      barra: vis('.nav-abajo'),
      lateral: vis('.sidebar'),
      hamburguesa: vis('.menu-btn'),
      encendida: sel ? sel.getAttribute('href') : null,
      pestanas: [].map.call(document.querySelectorAll('.nav-abajo .nav-txt'), n => n.textContent),
    };
  });

  // ── En el móvil ──────────────────────────────────────────────────────────
  let { p, ctx } = await abrir('client-home.html', 390);
  let e = await estado(p);
  ck('EN EL MÓVIL LA NAVEGACIÓN ESTÁ ABAJO', e.barra, e);
  ck('y el cajón lateral se va entero', !e.lateral, e);
  ck('con su hamburguesa, que ya no lleva a ninguna parte', !e.hamburguesa, e);
  ck('las cinco pantallas que más usa',
    e.pestanas.join() === 'Inicio,Entrena,Nutrición,Progreso,Chat', e.pestanas);
  ck('con la de esta página encendida', e.encendida === 'client-home.html', e.encendida);

  /* Que el último elemento de la página quede POR ENCIMA de la barra. Una
     barra fija tapando la última tarjeta es el fallo clásico de esto, y no se
     ve hasta que alguien baja del todo. */
  const tapado = await p.evaluate(() => {
    const c = document.querySelector('.content');
    if (c) c.scrollTop = c.scrollHeight;
    const ultimo = document.querySelector('.streak');
    const barra = document.querySelector('.nav-abajo');
    if (!ultimo || !barra) return null;
    return { fin: Math.round(ultimo.getBoundingClientRect().bottom),
             barra: Math.round(barra.getBoundingClientRect().top) };
  });
  ck('LA ÚLTIMA TARJETA NO QUEDA DEBAJO DE LA BARRA',
    tapado && tapado.fin <= tapado.barra, tapado);

  // El plan del prototipo, que antes no estaba.
  ck('sale el plan de entrenamiento, no solo el día',
    (await p.textContent('.hr-row.plan')).includes('Fuerza · 3 días/semana'),
    await p.textContent('#homeBody'));

  await ctx.close();

  // ── En escritorio no cambia nada ─────────────────────────────────────────
  ({ p, ctx } = await abrir('client-home.html', 1400));
  e = await estado(p);
  ck('EN ESCRITORIO MANDA LA BARRA LATERAL', e.lateral, e);
  ck('y la de abajo no aparece', !e.barra, e);
  await ctx.close();

  // ── Cada página enciende la suya ─────────────────────────────────────────
  for (const [pagina, esperada] of [
    ['client-entrena.html', 'client-entrena.html'],
    ['client-nutricion.html', 'client-nutricion.html'],
    ['client-chat.html', 'client-chat.html'],
    // Estas dos no son pestaña: cuelgan de una, y encienden la de su sección
    // en vez de dejar la barra apagada como si no estuvieras en ningún sitio.
    ['client-checkin.html', 'client-progreso.html'],
    ['client-perfil.html', 'client-home.html'],
  ]) {
    ({ p, ctx } = await abrir(pagina, 390));
    e = await estado(p);
    ck('en ' + pagina + ' se enciende ' + esperada, e.encendida === esperada, e.encendida);
    await ctx.close();
  }

  // ── El globito de mensajes sin leer ──────────────────────────────────────
  /* Vivía colgado del PRIMER enlace al chat del documento, que en el móvil es
     el del cajón escondido: había mensajes sin leer y ninguna señal. */
  ({ p, ctx } = await abrir('client-home.html', 390));
  await p.waitForTimeout(1200);
  const globito = await p.evaluate(() => {
    const d = document.querySelector('.nav-abajo [data-chat-unread]');
    return d ? { texto: d.textContent, visible: getComputedStyle(d).display !== 'none' } : null;
  });
  ck('EL GLOBITO DE NO LEÍDOS CAE EN LA BARRA DE ABAJO',
    globito && globito.visible && globito.texto === '3', globito);
  await ctx.close();

  ck('sin errores de JS', errs.length === 0, errs);
  await b.close();
  process.exit(f ? 1 : 0);
})();
