/* La pantalla de fin del entreno, en el rol de cliente.

   Al darle a «Terminar» salía una ventanita con cinco caras sobre un fondo
   gris: ni una cifra de lo que acababa de hacer. Ahora se le enseña el resumen
   de la sesión —duración, series, volumen y récords— y se le pregunta por ella
   en dos escalas de 1 a 10: con qué energía llegó y cuánto se esforzó.

   Lo que hay que dejar sujeto:

     · Que al terminar salga el resumen, con las cuatro cifras del servidor.
     · Que las dos escalas se puedan contestar y se vean contestadas.
     · Que lo que responde VIAJE: la energía no tenía dónde ir y se perdía.
     · Que contestar siga siendo opcional, y que volver a la sesión no guarde.

   Se carga la PÁGINA de verdad, con el servidor de mentira.
*/
const { chromium } = require('../_pw');

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.setViewportSize({ width: 420, height: 900 });
  const errs = []; p.on('pageerror', e => errs.push(String(e)));

  await p.addInitScript(() => {
    localStorage.setItem('token', 't'); localStorage.setItem('role_id', '6');
    window.__enviado = [];
    window.fetch = async (url, opts) => {
      const u = String(url); opts = opts || {};
      if (opts.method === 'POST') {
        const cuerpo = opts.body ? JSON.parse(opts.body) : null;
        window.__enviado.push({ url: u, cuerpo: cuerpo });
        if (u.includes('/workout-summary')) {
          return { status: 200, ok: true, json: async () => ({
            data: { sets: 5, volume: 4820.5, records: 2, record_exercises: [] } }) };
        }
        return { status: 200, ok: true, json: async () => ({ data: { id: 1 } }) };
      }
      return { status: 200, ok: true, json: async () => ({ data: {} }) };
    };
  });

  await p.goto('file://' + __dirname + '/../../frontend/client-entrena.html');
  await p.waitForFunction(() => typeof window.finishWorkout === 'function', { timeout: 8000 });

  let f = 0;
  const ck = (n, c, x) => { console.log((c ? 'OK   ' : 'FALLO ') + n + (c ? '' : ' -> ' + JSON.stringify(x))); if (!c) f++; };

  // Una sesión en marcha, con dos series marcadas.
  /* `_ws` es un `let` del script: se asigna sin `window.` para que sea ESA
     variable y no una propiedad nueva que la página no mira. Se vuelve a
     sembrar en cada escenario porque guardar cierra la sesión. */
  const sembrar = () => p.evaluate(() => {
    _ws = {
      routineId: 1, dayName: 'Empuje A', startMs: Date.now() - 20000,
      exercises: [{ training_id: 7, name: 'Press banca', muscle: 'Pecho', note: '', sets: [
        { reps: '8', kg: '80', rpe: '', done: true },
        { reps: '8', kg: '80', rpe: '', done: true },
        { reps: '8', kg: '80', rpe: '', done: false },
      ] }],
    };
  });
  await sembrar();

  // ── Terminar ─────────────────────────────────────────────────────────────
  await p.evaluate(() => { window.__fin = finishWorkout(); });
  await p.waitForTimeout(400);

  ck('al terminar sale la pantalla de fin',
    await p.locator('#finBack').evaluate(n => n.classList.contains('open')));
  ck('con el titulo de sesion terminada',
    (await p.textContent('#finTitulo')).includes('Sesión terminada'), await p.textContent('#finTitulo'));
  ck('y el dia que ha entrenado', await p.textContent('#finDia') === 'Empuje A',
    await p.textContent('#finDia'));

  // ── Las cuatro cifras ────────────────────────────────────────────────────
  ck('la duracion, en minutos y segundos',
    /^\d+:\d\d$/.test((await p.textContent('#finTiempo')).trim()), await p.textContent('#finTiempo'));
  ck('LAS SERIES, VOLUMEN Y RECORDS SALEN DEL SERVIDOR',
    (await p.textContent('#finSeries')) === '5'
    && (await p.textContent('#finVolumen')) === '4821kg'
    && (await p.textContent('#finRecords')) === '2',
    [await p.textContent('#finSeries'), await p.textContent('#finVolumen'), await p.textContent('#finRecords')]);

  const pedido = (await p.evaluate(() => window.__enviado)).find(e => e.url.includes('/workout-summary'));
  ck('y se piden mandando lo que acaba de hacer',
    !!pedido && (pedido.cuerpo.exercises || []).length === 1
    && pedido.cuerpo.exercises[0].sets.length === 3, pedido && pedido.cuerpo);

  // ── Las dos escalas ──────────────────────────────────────────────────────
  ck('la escala de energia va del 1 al 10',
    await p.locator('#finEnergia .fin-n').count() === 10);
  ck('la de esfuerzo tambien',
    await p.locator('#finEsfuerzo .fin-n').count() === 10);
  ck('sin contestar, no se enseña ninguna cifra',
    (await p.textContent('#finEnergiaV')).startsWith('—'), await p.textContent('#finEnergiaV'));

  await p.locator('#finEnergia .fin-n').nth(6).click();     // el 7
  await p.locator('#finEsfuerzo .fin-n').nth(7).click();    // el 8
  ck('al contestar se ve el numero elegido',
    (await p.textContent('#finEnergiaV')).startsWith('7')
    && (await p.textContent('#finEsfuerzoV')).startsWith('8'),
    [await p.textContent('#finEnergiaV'), await p.textContent('#finEsfuerzoV')]);
  ck('y se pintan todos los anteriores, como un termometro',
    await p.locator('#finEnergia .fin-n.on').count() === 7
    && await p.locator('#finEsfuerzo .fin-n.on').count() === 8,
    [await p.locator('#finEnergia .fin-n.on').count(), await p.locator('#finEsfuerzo .fin-n.on').count()]);

  // Sigue estando la pregunta de las caras.
  await p.locator('.fin-cara[data-n="4"]').click();
  ck('la cara elegida se marca', await p.locator('.fin-cara.sel').count() === 1);

  // ── Guardar ──────────────────────────────────────────────────────────────
  await p.locator('#finGuardar').click();
  await p.evaluate(() => window.__fin);
  await p.waitForTimeout(300);

  const guardado = (await p.evaluate(() => window.__enviado)).find(e => e.url.includes('/workout-session'));
  ck('se guarda el entreno', !!guardado, await p.evaluate(() => window.__enviado.map(e => e.url)));
  const c = (guardado || {}).cuerpo || {};
  ck('LA ENERGIA CON LA QUE LLEGO VIAJA', c.energy === 7, c.energy);
  ck('EL ESFUERZO VA COMO RPE DE LA SESION', c.rpe === 8, c.rpe);
  ck('y el animo tambien', c.mood === 4, c.mood);
  ck('con el dia y la duracion', c.day_name === 'Empuje A' && c.duration_min >= 1,
    { day_name: c.day_name, duration_min: c.duration_min });
  ck('y las series que hizo', (c.exercises || []).length === 1, c.exercises);
  ck('la pantalla se cierra al guardar',
    !(await p.locator('#finBack').evaluate(n => n.classList.contains('open'))));

  // ── Volver a la sesión no guarda ─────────────────────────────────────────
  await sembrar();
  await p.evaluate(() => { window.__enviado = []; window.__fin2 = finishWorkout(); });
  await p.waitForTimeout(300);
  await p.locator('.fin-cancel').click();
  await p.waitForTimeout(200);
  const tras = await p.evaluate(() => window.__enviado.filter(e => e.url.includes('/workout-session')));
  ck('VOLVER A LA SESION NO GUARDA NADA', tras.length === 0, tras.map(e => e.url));

  // ── Y contestar sigue siendo opcional ────────────────────────────────────
  await sembrar();
  await p.evaluate(() => { window.__enviado = []; window.__fin3 = finishWorkout(); });
  await p.waitForTimeout(300);
  await p.locator('#finGuardar').click();
  await p.waitForTimeout(300);
  const sinResponder = (await p.evaluate(() => window.__enviado)).find(e => e.url.includes('/workout-session'));
  ck('se puede guardar sin contestar', !!sinResponder, sinResponder);
  ck('y lo que no contesta va VACIO, no inventado',
    sinResponder && sinResponder.cuerpo.energy === null && sinResponder.cuerpo.mood === null,
    sinResponder && { energy: sinResponder.cuerpo.energy, mood: sinResponder.cuerpo.mood });

  ck('sin errores de JS', errs.length === 0, errs);
  await b.close();
  process.exit(f ? 1 : 0);
})();
