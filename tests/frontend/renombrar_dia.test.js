/* Renombrar un día de la rutina.

   Al pulsar el lápiz, el nombre se convierte en un recuadro con el texto
   seleccionado. Pero hacer clic DENTRO del recuadro —para poner el cursor
   entre dos letras y corregir solo una parte— no funcionaba: el clic subía
   hasta la tarjeta del día, que llama a `selectDay` y repinta la lista
   entera. El recuadro desaparecía.

   Y lo grave no es que se pierda la selección: es que si ya habías escrito
   algo, se pierde. La lista se vuelve a pintar con el nombre viejo.

   Lo que hay que dejar sujeto:

     · Que un clic dentro del recuadro no cierre la edición.
     · Que lo escrito hasta ese momento siga ahí.
     · Que se pueda escribir en medio del texto, que es de lo que se trata.
     · Y que lo de antes siga: seleccionar el día al tocar la tarjeta, y
       guardar el nombre al salir.
*/
const { chromium } = require('../_pw');

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  const errs = []; p.on('pageerror', e => errs.push(String(e)));
  await p.goto('file://' + __dirname + '/harness.html');

  let f = 0;
  const ck = (n, c, x) => { console.log((c ? 'OK   ' : 'FALLO ') + n + (c ? '' : ' -> ' + JSON.stringify(x))); if (!c) f++; };

  const chip = (i) => p.locator('.day-chip').nth(i);
  const caja = () => p.locator('.day-chip-input');

  // ── Se abre el recuadro ──────────────────────────────────────────────────
  await chip(1).locator('.day-edit-btn').click();
  await p.waitForTimeout(80);
  ck('el lápiz abre el recuadro', await caja().count() === 1);
  ck('con el nombre dentro y seleccionado',
    await caja().inputValue() === 'Martes'
    && await p.evaluate(() => {
      const i = document.querySelector('.day-chip-input');
      return i.selectionStart === 0 && i.selectionEnd === i.value.length;
    }), await caja().inputValue());

  // ── Un clic dentro no puede cerrarlo ─────────────────────────────────────
  const bb = await caja().boundingBox();
  await p.mouse.click(bb.x + 18, bb.y + bb.height / 2);   // entre las primeras letras
  await p.waitForTimeout(120);
  ck('UN CLIC DENTRO NO CIERRA LA EDICIÓN', await caja().count() === 1);
  ck('y no cambia de día seleccionado', await p.evaluate(() => __sel()) === 0,
    await p.evaluate(() => __sel()));

  // ── Y se puede corregir solo una parte ───────────────────────────────────
  await p.evaluate(() => {
    const i = document.querySelector('.day-chip-input');
    i.setSelectionRange(3, 3);            // «Mar|tes»
  });
  await p.keyboard.type('ZZ');
  ck('SE PUEDE ESCRIBIR EN MEDIO DEL TEXTO',
    await caja().inputValue() === 'MarZZtes', await caja().inputValue());

  // Y un clic más, con lo escrito ya dentro: no se puede perder.
  const bb2 = await caja().boundingBox();
  await p.mouse.click(bb2.x + 10, bb2.y + bb2.height / 2);
  await p.waitForTimeout(120);
  ck('LO ESCRITO NO SE PIERDE AL VOLVER A HACER CLIC',
    await caja().count() === 1 && await caja().inputValue() === 'MarZZtes',
    { cajas: await caja().count(), valor: await caja().count() ? await caja().inputValue() : null });

  // ── Al salir se guarda ───────────────────────────────────────────────────
  await p.locator('body').click({ position: { x: 5, y: 400 } });
  await p.waitForTimeout(150);
  ck('al salir del recuadro se guarda el nombre',
    JSON.stringify(await p.evaluate(() => __orden())) === '["Lunes","MarZZtes","Miércoles"]',
    await p.evaluate(() => __orden()));
  ck('y el recuadro se cierra', await caja().count() === 0);

  // ── Lo de antes sigue funcionando ────────────────────────────────────────
  await chip(2).click();
  await p.waitForTimeout(80);
  ck('tocar una tarjeta sigue seleccionando su día',
    await p.evaluate(() => __sel()) === 2, await p.evaluate(() => __sel()));

  /* El doble clic sobre el nombre —lo que promete su propio tooltip— sobre el
     día que ya está seleccionado. Sobre OTRO día el primer clic lo selecciona,
     que es lo que cualquiera espera al pulsar una tarjeta; para renombrar ése
     está el lápiz, que funciona en todos. */
  await chip(2).locator('.day-chip-name').dblclick();
  await p.waitForTimeout(80);
  ck('el doble clic sobre el nombre también renombra', await caja().count() === 1);
  await p.keyboard.press('Escape');
  await p.waitForTimeout(120);
  ck('y Escape lo deja como estaba',
    JSON.stringify(await p.evaluate(() => __orden())) === '["Lunes","MarZZtes","Miércoles"]',
    await p.evaluate(() => __orden()));

  ck('sin errores de JS', errs.length === 0, errs);
  await b.close();
  process.exit(f ? 1 : 0);
})();
