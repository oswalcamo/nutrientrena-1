/* La barra de navegación de abajo, en las diez pantallas del cliente.

   Se pinta desde aquí y no se escribe en cada página a propósito. El menú
   lateral ya vivió copiado en 21 páginas con siete variantes que solo se
   diferenciaban en espacios y comillas, y arreglar algo obligaba a acordarse
   de las veintiuna. Aquí es una lista y un bucle.

   Cinco destinos, no siete. Calendario y Perfil se quedan fuera: a 390 píxeles
   siete pestañas dejan cada una en 55px, y el texto no cabe. Se llega a ellas
   desde Inicio —la foto va a Perfil y la cabecera de la semana al Calendario—,
   que es a un toque más y no a costa de que no se lea ninguna.

   En escritorio esto no se ve: manda la barra lateral de siempre. Lo decide el
   CSS, no este fichero. */
(function () {
  var DESTINOS = [
    { href: 'client-home.html', texto: 'Inicio',
      icono: '<path d="M3 9.5 12 3l9 6.5"/><path d="M5 10v10h14V10"/>' },
    { href: 'client-entrena.html', texto: 'Entrena',
      icono: '<path d="M6.5 6.5 17.5 17.5M4 12l-1.5 1.5a2.12 2.12 0 0 0 3 3L7 18M17 6l1-1a2.12 2.12 0 0 1 3 3l-1 1"/><path d="m8 8 8 8"/>' },
    { href: 'client-nutricion.html', texto: 'Nutrición',
      icono: '<path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4Z"/><path d="M6 2v2M10 2v2M14 2v2"/>' },
    { href: 'client-progreso.html', texto: 'Progreso',
      icono: '<path d="M3 3v18h18"/><path d="M7 14l3-3 3 3 5-5"/>' },
    { href: 'client-chat.html', texto: 'Chat',
      icono: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>' }
  ];

  /* Qué pestaña se enciende. Se compara solo el nombre del fichero: la página
     puede abrirse con parámetros (?dia=…) o desde una ruta distinta según se
     sirva, y comparar la URL entera dejaba la barra sin ninguna encendida. */
  function pagina() {
    var p = (location.pathname || '').split('/').pop();
    return p || 'client-home.html';
  }

  /* Pantallas que no son pestaña pero cuelgan de una: estando en ellas se
     enciende la de su sección, en vez de dejar la barra apagada como si no
     estuvieras en ninguna parte. */
  var DE_QUIEN_CUELGA = {
    'client-checkin.html': 'client-progreso.html',
    'client-calendario.html': 'client-home.html',
    'client-perfil.html': 'client-home.html'
  };

  function pintar() {
    if (document.querySelector('.nav-abajo')) return;   // ya está

    var actual = pagina();
    var encendida = DE_QUIEN_CUELGA[actual] || actual;

    var barra = document.createElement('nav');
    barra.className = 'nav-abajo';
    barra.setAttribute('aria-label', 'Navegación principal');
    barra.innerHTML = '<div class="nav-abajo-fila">' + DESTINOS.map(function (d) {
      var sel = d.href === encendida;
      var punto = d.href === 'client-chat.html'
        ? '<span class="nav-punto" data-chat-unread></span>' : '';
      return '<a href="' + d.href + '"' + (sel ? ' class="sel" aria-current="page"' : '') + '>'
        + punto
        + '<svg width="21" height="21" fill="none" stroke="currentColor" stroke-width="2"'
        + ' stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24" aria-hidden="true">'
        + d.icono + '</svg>'
        + '<span class="nav-txt">' + d.texto + '</span></a>';
    }).join('') + '</div>';

    document.body.appendChild(barra);
    document.body.classList.add('con-nav-abajo');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', pintar);
  } else {
    pintar();
  }
})();
