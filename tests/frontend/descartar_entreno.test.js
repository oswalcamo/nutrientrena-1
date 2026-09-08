/* Descartar un entrenamiento empezado por error.

   Se podía salir de la sesión, pero por la «X» de arriba y con un `confirm`
   del navegador que decía «¿Salir sin terminar?». Quien ha abierto la rutina
   sin querer no busca arriba una salida: llega al final de la lista y espera
   encontrar ahí qué hacer con lo que acaba de empezar.

   Descartar no se deshace, así que se pregunta. Pero solo cuando hay algo que
   perder: si no se ha marcado ni escrito nada, preguntar «se perderán las
   series, pesos y notas» es mentira y una puerta de más.

   Lo que hay que dejar sujeto:

     · Que el botón esté al final de la rutina, después de los ejercicios.
     · Que pregunte antes de tirar lo registrado, y que «Seguir entrenando»
       devuelva la sesión INTACTA.
     · Que descartar no guarde nada.
     · Que sin nada registrado no estorbe con una pregunta.
     · Y que la «X» de arriba pregunte lo MISMO: es la misma acción.

   Se carga la PÁGINA de verdad, con el servidor de mentira.
*/
const { chromium } = require('../_pw');

const sesion = () => ({
  routineId: 1, dayName: 'Empuje A', startMs: Date.now() - 20000,
  exercises: [
    { training_id: 7, name: 'Remo con barra', muscle: 'Espalda', image: null,
      video_url: null, rest: 60, target: '10', note: '', sets: [
        { reps: '', kg: '', rpe: '', done: false },
        { reps: '', kg: '', rpe: '', done: false },
      ] },
    { training_id: 8, name: 'Press militar', muscle: 'Hombro', image: null,
      video_url: null, rest: 60, target: '10', note: '', sets: [
        { reps: '', kg: '', rpe: '', done: false },
      ] },
  ],
});

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.setViewportSize({ width: 430, height: 900 });
  const errs = []; p.on('pageerror', e => errs.push(String(e)));

  await p.addInitScript(() => {
    if (window.top !== window) return;
    localStorage.setItem('token', 't'); localStorage.setItem('role_id', '6');
    window.__enviado = [];
    window.fetch = async (url, opts) => {
      opts = opts || {};
      if (opts.method === 'POST') {
        window.__enviado.push(String(url));
        return { status: 200, ok: true, json: async () => ({ data: { id: 1 } }) };
      }
      return { status: 200, ok: true, json: async () => ({ data: {} }) };
    };
    // Un `confirm` del navegador bloquea la prueba y, sobre todo, es lo que se
    // ha quitado: si vuelve, esto lo delata.
    window.__confirms = 0;
    window.confirm = () => { window.__confirms++; return true; };
  });

  await p.goto('file://' + __dirname + '/../../frontend/client-entrena.html');
  await p.waitForFunction(() => typeof window.finishWorkout === 'function', { timeout: 8000 });

  let f = 0;
  const ck = (n, c, x) => { console.log((c ? 'OK   ' : 'FALLO ') + n + (c ? '' : ' -> ' + JSON.stringify(x))); if (!c) f++; };
  const abrir = () => p.evaluate((s) => {
    _ws = s; renderWorkout();
    document.getElementById('wsOverlay').classList.add('open');
  }, sesion());
  const enSesion = () => p.evaluate(() => !!_ws);

  // ── El botón, al final ───────────────────────────────────────────────────
  await abrir();
  await p.waitForTimeout(150);
  ck('el botón de descartar está en la sesión',
    await p.locator('.ws-descartar').count() === 1);
  ck('CON LOS EJERCICIOS POR ENCIMA, al final de la rutina',
    await p.locator('.ws-descartar').evaluate(n => {
      const ult = document.querySelectorAll('.ws-ex');
      return ult.length > 0 &&
        n.getBoundingClientRect().top >= ult[ult.length - 1].getBoundingClientRect().bottom;
    }));

  // ── Sin nada registrado no estorba ───────────────────────────────────────
  await p.locator('.ws-descartar').click();
  await p.waitForTimeout(200);
  ck('sin nada registrado descarta sin preguntar',
    await p.locator('.desc-back.open').count() === 0 && !(await enSesion()));
  ck('y no guarda nada', (await p.evaluate(() => window.__enviado)).length === 0,
    await p.evaluate(() => window.__enviado));

  // ── Con algo registrado, pregunta ────────────────────────────────────────
  await abrir();
  await p.waitForTimeout(150);
  await p.evaluate(() => { _ws.exercises[0].sets[0].done = true; renderWorkout(); });
  await p.locator('.ws-descartar').click();
  await p.waitForTimeout(200);

  ck('CON ALGO REGISTRADO PREGUNTA ANTES DE TIRARLO',
    await p.locator('.desc-back.open').count() === 1);
  ck('con la pregunta y lo que se pierde',
    (await p.textContent('.desc-caja')).includes('Seguro que quieres descartar')
    && (await p.textContent('.desc-caja')).includes('series, pesos y notas'),
    await p.textContent('.desc-caja'));
  ck('y sin usar el confirm del navegador',
    await p.evaluate(() => window.__confirms) === 0);

  // ── Seguir entrenando devuelve la sesión intacta ─────────────────────────
  await p.locator('.desc-seguir').click();
  await p.waitForTimeout(200);
  ck('«Seguir entrenando» cierra la pregunta', await p.locator('.desc-back.open').count() === 0);
  ck('Y LA SESIÓN SIGUE, con lo registrado', await enSesion()
    && await p.evaluate(() => _ws.exercises[0].sets[0].done) === true);
  ck('sin haberse guardado nada', (await p.evaluate(() => window.__enviado)).length === 0);

  // ── Sí, descartar ────────────────────────────────────────────────────────
  await p.locator('.ws-descartar').click();
  await p.waitForTimeout(200);
  await p.locator('.desc-si').click();
  await p.waitForTimeout(250);
  ck('«Sí, descartar» cierra la sesión', !(await enSesion()));
  ck('Y NO LA GUARDA', (await p.evaluate(() => window.__enviado)).length === 0,
    await p.evaluate(() => window.__enviado));
  ck('la pantalla de la sesión se cierra',
    !(await p.locator('#wsOverlay').evaluate(n => n.classList.contains('open'))));

  // ── La «X» de arriba pregunta lo mismo ───────────────────────────────────
  await abrir();
  await p.waitForTimeout(150);
  await p.evaluate(() => { _ws.exercises[0].sets[0].done = true; renderWorkout(); });
  await p.locator('.ws-exit').click();
  await p.waitForTimeout(200);
  ck('la X de arriba abre LA MISMA pregunta',
    await p.locator('.desc-back.open').count() === 1);
  ck('y tampoco usa el confirm del navegador',
    await p.evaluate(() => window.__confirms) === 0);
  await p.locator('.desc-seguir').click();
  await p.waitForTimeout(150);
  ck('y se puede volver a la sesión desde ahí', await enSesion());

  ck('sin errores de JS', errs.length === 0, errs);
  await b.close();
  process.exit(f ? 1 : 0);
})();
