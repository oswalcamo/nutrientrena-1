/* Encender y apagar la luz, en las ocho pantallas del cliente.

   Dos cosas, y el orden importa:

     1. Aplicar el tema guardado ANTES de que se pinte nada. Este fichero se
        carga en el <head>, así que cuando el navegador dibuja el primer píxel
        el atributo ya está puesto. Hacerlo al final —en DOMContentLoaded—
        enseña la página en blanco y la apaga medio segundo después, que es un
        fogonazo en la cara a quien abre la aplicación de noche.

     2. Poner el botón en la barra de arriba, al lado de la campana. Eso sí
        espera al DOM, porque hace falta la barra.

   La elección se guarda por navegador, no en el servidor: es una preferencia
   de este teléfono —la misma persona puede querer la pantalla clara en el
   portátil del trabajo y oscura en el móvil de noche— y guardarla en la cuenta
   le impondría una en los dos.
*/
(function () {
  var CLAVE = 'tema_cliente';
  var NOCHE = 'noche', DIA = 'dia';

  function guardado() {
    try { return localStorage.getItem(CLAVE); } catch (e) { return null; }
  }

  /* Sin elección hecha, manda lo que el sistema pida. Quien tiene el móvil en
     modo oscuro espera que las aplicaciones lo estén; preguntárselo otra vez
     es no haber escuchado la primera. */
  function preferido() {
    var elegido = guardado();
    if (elegido === NOCHE || elegido === DIA) return elegido;
    try {
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) return NOCHE;
    } catch (e) {}
    return DIA;
  }

  function aplicar(tema) {
    var raiz = document.documentElement;
    if (tema === NOCHE) raiz.setAttribute('data-tema', NOCHE);
    else raiz.removeAttribute('data-tema');
    pintarBoton(tema);
  }

  function esNoche() {
    return document.documentElement.getAttribute('data-tema') === NOCHE;
  }

  function alternar() {
    var nuevo = esNoche() ? DIA : NOCHE;
    try { localStorage.setItem(CLAVE, nuevo); } catch (e) {}
    aplicar(nuevo);
  }

  // ── El botón ─────────────────────────────────────────────────────────────
  var LUNA = '<svg width="17" height="17" fill="none" stroke="currentColor" stroke-width="2"'
    + ' stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24" aria-hidden="true">'
    + '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  var SOL = '<svg width="17" height="17" fill="none" stroke="currentColor" stroke-width="2"'
    + ' stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24" aria-hidden="true">'
    + '<circle cx="12" cy="12" r="4.2"/><path d="M12 1.8v2.4M12 19.8v2.4M4.2 12H1.8M22.2 12h-2.4'
    + 'M5.6 5.6 3.9 3.9M20.1 20.1l-1.7-1.7M18.4 5.6l1.7-1.7M3.9 20.1l1.7-1.7"/></svg>';

  function pintarBoton(tema) {
    var b = document.getElementById('btnTema');
    if (!b) return;
    var noche = tema === NOCHE;
    // De día se ofrece la luna (apagar la luz); de noche, el sol.
    b.innerHTML = noche ? SOL : LUNA;
    b.title = noche ? 'Volver al modo claro' : 'Modo noche';
    b.setAttribute('aria-label', b.title);
    b.setAttribute('aria-pressed', noche ? 'true' : 'false');
  }

  /* Dónde cabe el botón. Se prueba por orden: al lado de la campana, que es
     donde lo pone el prototipo; si la página no tiene campana, al final de la
     barra de arriba. Si no hay barra, no se pinta — y no pasa nada, porque el
     tema ya está aplicado y se puede cambiar desde cualquier otra pantalla. */
  function colocar() {
    if (document.getElementById('btnTema')) return;

    var campana = document.querySelector('.bell, #bell');
    var barra = document.querySelector('.topbar');
    if (!campana && !barra) return;

    var b = document.createElement('button');
    b.id = 'btnTema';
    b.className = 'btn-tema';
    b.type = 'button';
    b.addEventListener('click', alternar);

    if (campana && campana.parentNode) campana.parentNode.insertBefore(b, campana);
    else barra.appendChild(b);

    pintarBoton(esNoche() ? NOCHE : DIA);
  }

  // Lo primero, y sin esperar a nadie: si no, la página se enseña clara y se
  // apaga después.
  aplicar(preferido());

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', colocar);
  else colocar();

  /* Si nunca se ha elegido a mano, seguir al sistema cuando cambie: el móvil
     pasa a oscuro al anochecer y la aplicación va detrás. En cuanto alguien
     toca el botón, manda su elección y esto deja de mover nada. */
  try {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var alCambiar = function (e) { if (!guardado()) aplicar(e.matches ? NOCHE : DIA); };
    if (mq.addEventListener) mq.addEventListener('change', alCambiar);
    else if (mq.addListener) mq.addListener(alCambiar);
  } catch (e) {}

  window.temaCliente = { alternar: alternar, esNoche: esNoche };
})();
