/* La ficha del ejercicio, mientras el cliente entrena.

   Al tocar la foto de un ejercicio a mitad de la serie solo se abría el vídeo.
   Todo lo demás que el coach había escrito —cómo se hace, qué músculos
   trabaja, con qué material, qué patrón de movimiento— estaba guardado y el
   cliente no podía verlo en ninguna parte.

   Lo que hay que dejar sujeto:

     · Que tocar la foto abra la ficha, no solo el vídeo.
     · Que el vídeo SIGA estando: es lo que había y lo que más se mira.
     · Que se vea lo que le toca HOY, que es a lo que ha venido.
     · Que abra al instante y lo que hay que ir a buscar llegue después.
     · Que un ejercicio a medio rellenar lo diga en vez de salir vacío.
     · Y que la ficha se pida UNA vez por ejercicio, no en cada toque.

   Se carga la PÁGINA de verdad, con el servidor de mentira.
*/
const { chromium } = require('../_pw');

const FICHA = {
  id: 7, name: 'Press banca',
  description: 'Tumbado en el banco, baja la barra al pecho y empuja.',
  image: null, video_url: 'https://youtu.be/abc123',
  muscle_group_name: 'Pecho', secondary_muscle_names: ['Tríceps', 'Hombro'],
  material: 'Barra', movement_pattern: 'Empuje horizontal',
  exercise_type: 'Compuesto', location: 'Gimnasio',
  difficulty_names: ['Intermedio'],
  rec_series: '3-4', rec_reps: '8-12', rec_rest: '90s',
};

const PELADO = {
  id: 9, name: 'Plancha', description: null, image: null, video_url: null,
  muscle_group_name: 'Core', secondary_muscle_names: [], material: null,
  movement_pattern: null, exercise_type: null, location: null,
  difficulty_names: [], rec_series: null, rec_reps: null, rec_rest: null,
};

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.setViewportSize({ width: 420, height: 900 });
  const errs = []; p.on('pageerror', e => errs.push(String(e)));

  /* El <iframe> del vídeo carga YouTube de verdad, y su propio código revienta
     al no poder leer localStorage desde `file://`. Es ruido del banco de
     pruebas, no de la aplicación: se corta la petición y se comprueba el `src`,
     que es lo que la página decide. */
  await p.route('**://*.youtube.com/**', r => r.abort());

  await p.addInitScript((fichas) => {
    // Esto corre en TODOS los marcos, y el del vídeo tiene origen opaco: ahí
    // `localStorage` lanza. Solo interesa la página.
    if (window.top !== window) return;
    localStorage.setItem('token', 't'); localStorage.setItem('role_id', '6');
    window.__pedidos = [];
    window.fetch = async (url, opts) => {
      const u = String(url);
      if (u.includes('/client/exercise/')) {
        window.__pedidos.push(u);
        const id = u.split('/client/exercise/')[1].split('?')[0];
        const d = fichas[id];
        if (!d) return { status: 404, ok: false, json: async () => ({ message: 'no' }) };
        return { status: 200, ok: true, json: async () => ({ data: d }) };
      }
      return { status: 200, ok: true, json: async () => ({ data: {} }) };
    };
  }, { 7: FICHA, 9: PELADO });

  await p.goto('file://' + __dirname + '/../../frontend/client-entrena.html');
  await p.waitForFunction(() => typeof window.abrirFicha === 'function', { timeout: 8000 });

  let f = 0;
  const ck = (n, c, x) => { console.log((c ? 'OK   ' : 'FALLO ') + n + (c ? '' : ' -> ' + JSON.stringify(x))); if (!c) f++; };

  // Una sesión en marcha, con dos ejercicios.
  await p.evaluate(() => {
    _ws = { routineId: 1, dayName: 'Empuje A', startMs: Date.now(), exercises: [
      { training_id: 7, name: 'Press banca', muscle: 'Pecho', image: null,
        video_url: 'https://youtu.be/abc123', rest: 90, target: '8-12', note: '',
        sets: [{reps:'',kg:'',rpe:'',done:false},{reps:'',kg:'',rpe:'',done:false},
               {reps:'',kg:'',rpe:'',done:false},{reps:'',kg:'',rpe:'',done:false}] },
      { training_id: 9, name: 'Plancha', muscle: 'Core', image: null,
        video_url: null, rest: null, target: '40s', note: '',
        sets: [{reps:'',kg:'',rpe:'',done:false}] },
      // Uno cuya ficha el servidor no da: el gimnasio sin cobertura.
      { training_id: 99, name: 'Remo', muscle: 'Espalda', image: null,
        video_url: null, rest: null, target: '10', note: '',
        sets: [{reps:'',kg:'',rpe:'',done:false}] },
    ] };
    renderWorkout();
    document.getElementById('wsOverlay').classList.add('open');
  });
  await p.waitForTimeout(200);

  // ── Tocar la foto ────────────────────────────────────────────────────────
  ck('la foto del ejercicio se puede tocar',
    await p.locator('.ws-thumb[role="button"]').count() === 3,
    await p.locator('.ws-thumb[role="button"]').count());

  await p.locator('.ws-thumb').first().click();
  ck('SE ABRE LA FICHA, no solo el video',
    await p.locator('#ejBack').evaluate(n => n.classList.contains('open')));
  ck('el modal de solo-video NO se abre',
    !(await p.locator('#vidModal').evaluate(n => n.classList.contains('open'))));
  ck('con el nombre del ejercicio', await p.textContent('#ejTit') === 'Press banca',
    await p.textContent('#ejTit'));
  ck('y su musculo', await p.textContent('#ejMus') === 'Pecho', await p.textContent('#ejMus'));

  // Lo que ya está en el móvil se pinta al momento, sin esperar al servidor.
  ck('LO QUE LE TOCA HOY SALE AL INSTANTE',
    (await p.textContent('#ejCuerpo')).includes('Series')
    && (await p.textContent('#ejCuerpo')).includes('Descanso'),
    await p.textContent('#ejCuerpo'));
  const hoy = await p.$$eval('.ej-hoy .v', ns => ns.map(n => n.textContent.trim()));
  ck('con sus cifras: 4 series, 8-12 reps, 90s',
    JSON.stringify(hoy) === JSON.stringify(['4', '8-12', '90s']), hoy);

  // ── El vídeo sigue estando ───────────────────────────────────────────────
  ck('EL VIDEO SIGUE ESTANDO, dentro de la ficha',
    await p.locator('.ej-media iframe').count() === 1,
    await p.locator('.ej-media').count());
  ck('y es el del ejercicio',
    (await p.getAttribute('.ej-media iframe', 'src')).includes('abc123'),
    await p.getAttribute('.ej-media iframe', 'src'));

  // ── Y lo que hay que ir a buscar ─────────────────────────────────────────
  await p.waitForFunction(() => !document.querySelector('#ejCuerpo').textContent.includes('Cargando'),
    { timeout: 5000 });
  const cuerpo = await p.textContent('#ejCuerpo');
  ck('la descripcion de como se hace', cuerpo.includes('baja la barra al pecho'), cuerpo);
  const chips = await p.$$eval('.ej-chip', ns => ns.map(n => n.textContent.replace(/\s+/g, ' ').trim()));
  ck('los musculos secundarios',
    chips.some(c => c.includes('También trabaja') && c.includes('Tríceps, Hombro')), chips);
  ck('el material', chips.some(c => c.includes('Material:') && c.includes('Barra')), chips);
  ck('el patron de movimiento',
    chips.some(c => c.includes('Patrón:') && c.includes('Empuje horizontal')), chips);
  ck('el tipo y el nivel, en palabras',
    chips.some(c => c.includes('Compuesto')) && chips.some(c => c.includes('Intermedio')), chips);
  ck('y la referencia general, aparte de lo que le puso su coach',
    (await p.textContent('.ej-ref')).includes('3-4 series'), await p.textContent('.ej-ref'));

  /* Ese campo admite texto libre: el catálogo del cliente trae filas con
     «Según sensaciones» en vez de una cifra, y añadirle "series" detrás la
     dejaba en «Según sensaciones series». */
  const libre = await p.evaluate(() => _fichaHTML(
    { name: 'X', sets: [], target: null, rest: null, video_url: null, image: null },
    { rec_series: 'Según sensaciones', rec_reps: null, rec_rest: null,
      secondary_muscle_names: [], difficulty_names: [] }));
  ck('una recomendacion en palabras no se queda en "… series"',
    libre.includes('Según sensaciones') && !libre.includes('sensaciones series'), libre);

  // ── Cerrar ───────────────────────────────────────────────────────────────
  await p.locator('.ej-x').click();
  await p.waitForTimeout(150);
  ck('se cierra', !(await p.locator('#ejBack').evaluate(n => n.classList.contains('open'))));
  ck('Y EL VIDEO DEJA DE SONAR DEBAJO', await p.locator('.ej-media iframe').count() === 0);

  // ── No se pregunta dos veces por lo mismo ────────────────────────────────
  await p.locator('.ws-thumb').first().click();
  await p.waitForTimeout(400);
  const pedidos = await p.evaluate(() => window.__pedidos.filter(u => u.endsWith('/7')));
  ck('la ficha se pide UNA vez por ejercicio', pedidos.length === 1, pedidos);
  ck('y al reabrirla sigue estando entera',
    (await p.textContent('#ejCuerpo')).includes('baja la barra al pecho'));
  await p.locator('.ej-x').click();
  await p.waitForTimeout(150);

  // ── Un ejercicio a medio rellenar ────────────────────────────────────────
  await p.locator('.ws-thumb').nth(1).click();
  await p.waitForFunction(() => !document.querySelector('#ejCuerpo').textContent.includes('Cargando'),
    { timeout: 5000 });
  const pelado = await p.textContent('#ejCuerpo');
  ck('UNO SIN DATOS LO DICE, no se queda en blanco',
    pelado.includes('no ha escrito más detalles'), pelado);
  ck('pero sigue enseñando lo que le toca hoy', pelado.includes('Reps'), pelado);
  ck('y sin video no hay caja de video', await p.locator('.ej-media').count() === 0);

  await p.locator('.ej-x').click();
  await p.waitForTimeout(150);

  // ── Cuando el servidor no la da ──────────────────────────────────────────
  await p.locator('.ws-thumb').nth(2).click();
  await p.waitForFunction(() => !document.querySelector('#ejCuerpo').textContent.includes('Cargando'),
    { timeout: 5000 });
  ck('si no se puede cargar, lo dice',
    (await p.textContent('#ejCuerpo')).includes('No se pudo cargar'), await p.textContent('#ejCuerpo'));
  ck('y aun asi enseña lo que le toca hoy',
    (await p.textContent('#ejCuerpo')).includes('Reps'), await p.textContent('#ejCuerpo'));

  // Que falle no puede convertirse en pedirlo una y otra vez cada vez que abre.
  await p.locator('.ej-x').click();
  await p.waitForTimeout(150);
  await p.locator('.ws-thumb').nth(2).click();
  await p.waitForTimeout(400);
  const fallidos = await p.evaluate(() => window.__pedidos.filter(u => u.endsWith('/99')));
  ck('TAMPOCO SE REPITE LA QUE FALLA', fallidos.length === 1, fallidos);
  await p.locator('.ej-x').click();

  ck('sin errores de JS', errs.length === 0, errs);
  await b.close();
  process.exit(f ? 1 : 0);
})();
