/* Los vídeos de los ejercicios se ven.

   El fallo: el reproductor salía en negro con un "403" enorme, en el panel del
   coach y en la pantalla del cliente. No era del código —el <iframe> se creaba
   bien y con la URL correcta— sino de Bunny: la biblioteca 713982 tiene
   protección de enlace y su lista de dominios permitidos incluye `alzum.io`
   pero NO `app.alzum.io`, que es desde donde se sirve la aplicación. El
   navegador manda ese dominio en la cabecera Referer y Bunny devuelve su
   página de error.

   Medido, un dominio por fila:

       https://alzum.io/       → reproduce  (48 347 bytes)
       https://app.alzum.io/   → 403        ( 2 841 bytes)
       sin Referer             → reproduce  (48 347 bytes)

   El arreglo de verdad es añadir el dominio en el panel de Bunny. Mientras
   tanto, los iframes piden el vídeo SIN mandar el dominio, que es el caso que
   Bunny sí deja pasar. Comprobado en un navegador real: el mismo vídeo, en la
   misma página, sale en 403 sin el atributo y reproduce con él.

   Esta prueba sujeta el atributo. Si alguien lo quita —o añade un cuarto sitio
   donde se incruste un vídeo y se le olvida—, los vídeos se apagan otra vez y
   no hay nada que lo avise hasta que un cliente lo dice.

   OJO: si algún día se bloquea también el acceso sin Referer en Bunny, esto
   deja de bastar y hay que arreglar la lista de dominios sí o sí.
*/
const { chromium } = require('../_pw');
const fs = require('fs');
const path = require('path');

const RAIZ = path.join(__dirname, '..', '..');
const BUNNY = 'https://player.mediadelivery.net/play/713982/cb1b8b06-4762-41c5-a900-3d56d83f1ad4';

const FICHA = {
  training_id: 7, name: 'Press de banca', description: 'Tumbado en el banco…',
  image: null, video_url: BUNNY,
  muscle_group_name: 'Pecho', secondary_muscle_names: ['Tríceps'],
  material: 'Barra', movement_pattern: 'Empuje horizontal',
  exercise_type: 'Compuesto', location: 'Gimnasio',
  records: {}, evolucion: [], historial: [],
};

(async () => {
  const b = await chromium.launch();
  let f = 0;
  const ck = (n, c, x) => { console.log((c ? 'OK   ' : 'FALLO ') + n + (c ? '' : ' -> ' + JSON.stringify(x))); if (!c) f++; };

  // ── Que no quede ningún <iframe> de vídeo sin el atributo ────────────────
  /* Se mira el FICHERO y no solo lo que se pinta: en el panel del coach el
     iframe está escrito en el HTML y en el cliente se arma desde JavaScript;
     una prueba que solo abriera una de las dos pantallas dejaría la otra
     suelta. */
  for (const fichero of ['ejercicios.html', 'client-entrena.html']) {
    const txt = fs.readFileSync(path.join(RAIZ, 'frontend', fichero), 'utf8');
    const marcos = txt.match(/<iframe/g) || [];
    const conAtributo = (txt.match(/referrerpolicy="no-referrer"/g) || []).length;
    ck(fichero + ': todos sus iframes piden el vídeo sin mandar el dominio',
      marcos.length > 0 && conAtributo === marcos.length,
      { iframes: marcos.length, conAtributo });
  }

  // ── Y que llegue de verdad al elemento que se pinta ──────────────────────
  const ctx = await b.newContext({ viewport: { width: 390, height: 800 } });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(String(e)));
  await p.addInitScript((d) => {
    if (window.top !== window) return;
    localStorage.setItem('token', 't'); localStorage.setItem('role_id', '6');
    const ok = (data) => ({ status: 200, ok: true, json: async () => ({ data }) });
    window.fetch = async (url) => {
      const u = String(url);
      if (u.includes('/auth/me')) return ok({ name: 'Carlos', user_id: 9 });
      if (u.includes('/client/exercise/')) return ok(d.FICHA);
      if (u.includes('/client/routines')) return ok([]);
      if (u.includes('/chat/unread-count')) return ok({ total: 0, conversations: [] });
      return ok({});
    };
  }, { FICHA });

  await p.goto('file://' + path.join(RAIZ, 'frontend', 'client-entrena.html'));
  await p.waitForFunction(() => typeof window.abrirFicha === 'function', { timeout: 8000 });
  await p.evaluate((url) => {
    _ws = { routineId: 1, dayName: 'Empuje A', startMs: Date.now(), exercises: [{
      training_id: 7, name: 'Press de banca', muscle: 'Pecho', image: null,
      video_url: url, rest: 90, target: '8-12', note: '',
      sets: [{ reps: '', kg: '', rpe: '', done: false }] }] };
    document.getElementById('wsOverlay').style.display = 'flex';
    renderWorkout();
  }, BUNNY);
  await p.waitForTimeout(300);
  await p.locator('.ws-thumb').first().click();
  await p.waitForTimeout(1000);

  const v = await p.evaluate(() => {
    const m = document.querySelector('#ejCuerpo .ej-media iframe');
    if (!m) return null;
    const r = m.getBoundingClientRect();
    return { src: m.getAttribute('src'), pol: m.getAttribute('referrerpolicy'),
             ancho: Math.round(r.width), alto: Math.round(r.height) };
  });

  ck('la ficha del ejercicio trae su reproductor', !!v, v);
  /* La URL de Bunny que guarda el catálogo es la de "play"; la que se puede
     incrustar es la de "embed". Traducirla mal daba una caja negra. */
  ck('con la URL que se puede incrustar, no la de la página de Bunny',
    v && v.src.startsWith('https://iframe.mediadelivery.net/embed/713982/'), v && v.src);
  ck('SIN MANDAR EL DOMINIO, que es lo que Bunny rechazaba',
    v && v.pol === 'no-referrer', v && v.pol);
  ck('y con tamaño, no aplastado a cero',
    v && v.ancho > 200 && v.alto > 100, v);

  ck('sin errores de JS', errs.length === 0, errs);
  await ctx.close();
  await b.close();
  process.exit(f ? 1 : 0);
})();
