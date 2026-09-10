/* El chat del cliente: sus conversaciones, no solo la de su coach.

   La pantalla pedía /client/chat —que devuelve UNA conversación, la del
   coach— y pintaba esa. Si el coach o el centro montaban un grupo, el cliente
   entraba dentro (el servidor le creaba su fila de participante), le contaban
   los mensajes en el globito rojo del menú… y no tenía ninguna pantalla donde
   abrirlo. Aquí se comprueba que la lista está, que se puede buscar en ella y
   que dentro de un grupo cada mensaje sale de quien es.

   Se carga la PÁGINA de verdad, con el servidor de mentira.
*/
const { chromium } = require('../_pw');

const YO = 77, COACH = 5, OTRO = 88;

const msg = (id, quien, texto, nombre) => ({
  id: id + '-' + quien + '-' + texto.length, conversation_id: id, content: texto,
  sender_user_id: quien, sender_name: nombre, created_at: '2026-09-10T10:00:00',
  attachment_url: null, attachment_name: null, attachment_type: null, attachment_size: null,
});

const CONVS = [
  { id: 'c-coach', type: 'individual', name: null, broadcast: false, puedo_escribir: true,
    participants: [{ user_id: YO, name: 'Ana' }, { user_id: COACH, name: 'Coach Marta', photo: null }],
    participantes_total: 2,
    last_message: msg('c-coach', COACH, 'Mañana toca pierna', 'Coach Marta') },
  { id: 'c-reto', type: 'group', name: 'Reto 30 días', broadcast: false, puedo_escribir: true,
    participants: [{ user_id: YO, name: 'Ana' }, { user_id: COACH, name: 'Coach Marta' },
                   { user_id: OTRO, name: 'Luis' }],
    participantes_total: 3,
    last_message: msg('c-reto', OTRO, 'Yo ya he acabado', 'Luis') },
  { id: 'c-avisos', type: 'group', name: 'Avisos del centro', broadcast: true, puedo_escribir: false,
    participants: [{ user_id: YO, name: 'Ana' }, { user_id: COACH, name: 'Coach Marta' }],
    participantes_total: null,
    last_message: msg('c-avisos', COACH, 'Cerramos el 15', 'Coach Marta') },
];

const MENSAJES = {
  'c-coach': [msg('c-coach', COACH, 'Mañana toca pierna', 'Coach Marta')],
  'c-reto': [
    msg('c-reto', COACH, 'Empieza el reto', 'Coach Marta'),
    msg('c-reto', OTRO, 'Yo ya he acabado', 'Luis'),
    msg('c-reto', YO, 'Voy por el día 12', 'Ana'),
  ],
  'c-avisos': [msg('c-avisos', COACH, 'Cerramos el 15', 'Coach Marta')],
};

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.setViewportSize({ width: 1400, height: 1000 });
  const errs = []; p.on('pageerror', e => errs.push(String(e)));

  await p.addInitScript((d) => {
    if (window.top !== window) return;
    localStorage.setItem('token', 't'); localStorage.setItem('role_id', '6');
    const ok = (data) => ({ status: 200, ok: true, json: async () => ({ data }) });
    window.fetch = async (url) => {
      const u = String(url);
      if (u.includes('/auth/me')) return ok({ name: 'Ana', user_id: d.YO });
      if (u.includes('/client/chat')) return ok({
        conversation_id: 'c-coach',
        coach: { user_id: d.COACH, name: 'Coach Marta', initials: 'C' },
        chat_enabled: true });
      if (u.includes('/chat/conversations/') && u.includes('/messages')) {
        const id = u.split('/conversations/')[1].split('/')[0];
        return ok({ messages: d.MENSAJES[id] || [], total: (d.MENSAJES[id] || []).length });
      }
      if (u.includes('/chat/unread-count')) return ok({
        total: 4, conversations: [{ conversation_id: 'c-reto', count: 4 }] });
      if (u.includes('/chat/conversations')) return ok(d.CONVS);
      return ok({});
    };
  }, { YO, COACH, CONVS, MENSAJES });

  await p.goto('file://' + __dirname + '/../../frontend/client-chat.html');

  let f = 0;
  const ck = (n, c, x) => { console.log((c ? 'OK   ' : 'FALLO ') + n + (c ? '' : ' -> ' + JSON.stringify(x))); if (!c) f++; };

  let pintada = true;
  try {
    await p.waitForFunction(() => document.querySelectorAll('.conv-item').length > 0, { timeout: 8000 });
  } catch (e) { pintada = false; }
  ck('el cliente tiene una lista de conversaciones', pintada, await p.textContent('#convList'));

  const nombres = () => p.$$eval('.conv-item .conv-name', ns => ns.map(n => n.textContent.trim()));

  // ── Lo que faltaba ───────────────────────────────────────────────────────
  const todas = await nombres();
  ck('EL GRUPO QUE MONTÓ EL COACH SE VE DESDE EL ROL CLIENTE',
    todas.includes('Reto 30 días'), todas);
  ck('y el del centro también', todas.includes('Avisos del centro'), todas);
  ck('junto a la conversación con su coach', todas.includes('Coach Marta'), todas);

  // ── Al entrar se abre la del coach, que es lo normal ──────────────────────
  ck('al entrar está abierta la del coach',
    (await p.textContent('#coachName')).includes('Coach Marta'), await p.textContent('#coachName'));
  ck('con el cuadro de escribir puesto',
    await p.$eval('#composerInner', e => e.style.display !== 'none'));

  // ── El buscador ──────────────────────────────────────────────────────────
  await p.fill('#convBuscar', 'reto');
  ck('HAY BUSCADOR Y FILTRA', (await nombres()).join() === 'Reto 30 días', await nombres());
  await p.fill('#convBuscar', 'zzz');
  ck('y si no hay nada lo dice, no se queda en blanco',
    (await p.textContent('#convList')).includes('Ninguna conversación'),
    await p.textContent('#convList'));
  await p.fill('#convBuscar', '');
  ck('al borrar vuelven todas', (await nombres()).length === 3, await nombres());

  // ── Los no leídos por conversación ───────────────────────────────────────
  ck('el grupo enseña sus mensajes sin leer',
    (await p.textContent('.conv-item[data-conv="c-reto"]')).includes('4'),
    await p.textContent('.conv-item[data-conv="c-reto"]'));

  // ── Entrar en el grupo ───────────────────────────────────────────────────
  await p.click('.conv-item[data-conv="c-reto"]');
  await p.waitForTimeout(800);
  ck('se puede entrar en el grupo',
    (await p.textContent('#coachName')) === 'Reto 30 días', await p.textContent('#coachName'));
  ck('y la cabecera dice cuánta gente hay',
    (await p.textContent('#coachStatus')).includes('3 personas'), await p.textContent('#coachStatus'));

  // ── Quién ha escrito cada cosa ───────────────────────────────────────────
  /* El fallo de antes: se daba por hecho que todo lo que no escribía el coach
     lo escribía yo. En un grupo eso pinta el mensaje de otro cliente como si
     fuera mío, del lado derecho y en azul. */
  const mios = await p.locator('#chatInner .msg.me').count();
  ck('EN UN GRUPO SOLO ES MÍO LO QUE ESCRIBÍ YO', mios === 1, mios);
  const suyos = await p.$$eval('#chatInner .msg.them .msg-sender', ns => ns.map(n => n.textContent.trim()));
  ck('y lo demás sale con el nombre de quien lo escribió',
    suyos.join() === 'Coach Marta,Luis', suyos);

  // ── El grupo de avisos ───────────────────────────────────────────────────
  await p.click('.conv-item[data-conv="c-avisos"]');
  await p.waitForTimeout(800);
  ck('en un grupo de avisos no se puede escribir',
    await p.$eval('#composerInner', e => e.style.display === 'none'));
  ck('y se dice por qué, en vez de dejar un cuadro que devuelve error',
    (await p.textContent('#chatOff')).includes('solo escribe quien lo creó'),
    await p.textContent('#chatOff'));

  // ── Volver al coach ──────────────────────────────────────────────────────
  await p.click('.conv-item[data-conv="c-coach"]');
  await p.waitForTimeout(800);
  ck('se vuelve a la del coach y el cuadro de escribir regresa',
    await p.$eval('#composerInner', e => e.style.display !== 'none'));
  ck('con su estado de siempre',
    /chat activo/i.test(await p.textContent('#coachStatus')), await p.textContent('#coachStatus'));

  ck('sin errores de JS', errs.length === 0, errs);
  await b.close();
  process.exit(f ? 1 : 0);
})();
