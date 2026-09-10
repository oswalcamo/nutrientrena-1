/* Globito de mensajes sin leer en el enlace de Chat del menú.

   Vivía copiado, byte a byte, en las 38 páginas del frontend. Ahora vive aquí.

   Cambio de comportamiento: el sondeo se PARA cuando la pestaña no está a la
   vista. Antes cada pestaña abierta pedía /chat/unread-count cada 20 segundos
   para siempre, aunque estuviera de fondo o el portátil cerrado. Con veinte
   usuarios eso son 60 peticiones por minuto sin que nadie mire la pantalla:
   gasto continuo y, sobre todo, los logs del servidor quedaban sepultados
   bajo esa misma línea repetida, que es donde se esconden los errores de
   verdad cuando hay que diagnosticar algo. */
(function(){
  var API=API_BASE;
  var token=localStorage.getItem('token'); if(!token) return;
  var INTERVALO=20000;

  /* TODOS los enlaces al chat, no el primero.

     En el móvil el cliente tiene dos: el del cajón lateral y el de la barra de
     abajo, que es el que ve. Con querySelector el globito se colgaba del
     primero del DOM —el escondido— y en la barra no aparecía nunca: había
     mensajes sin leer y ninguna señal. */
  function attach(){
    var enlaces=[].slice.call(
      document.querySelectorAll('a[href="chat.html"], a[href="client-chat.html"]'));
    if(!enlaces.length){ return; }

    /* Si el enlace ya trae su propio hueco para el globito —la barra de abajo
       lo pone, con su sitio y su tamaño—, se reutiliza en vez de meterle otro
       encima con estilos que allí no encajan. */
    var dots=enlaces.map(function(link){
      var propio=link.querySelector('[data-chat-unread]');
      if(propio) return propio;
      var dot=document.createElement('span');
      dot.setAttribute('data-chat-unread','');
      dot.style.cssText='display:none;margin-left:auto;min-width:18px;height:18px;padding:0 5px;border-radius:9px;background:#DC2626;color:#fff;font-size:10px;font-weight:700;line-height:18px;text-align:center;';
      link.appendChild(dot);
      return dot;
    });

    function refresh(){
      return fetch(API+'/chat/unread-count',{headers:{Authorization:'Bearer '+token}})
        .then(function(r){return r.json();})
        .then(function(d){
          var n=(d&&d.data&&d.data.total)||0;
          dots.forEach(function(dot){
            if(n>0){ dot.style.display='inline-block'; dot.textContent=n>99?'99+':String(n); }
            else { dot.style.display='none'; dot.textContent=''; }
          });
        }).catch(function(){});
    }

    var timer=null;
    function arrancar(){
      if(timer) return;
      refresh();                                   // al volver, dato fresco ya
      timer=setInterval(refresh, INTERVALO);
    }
    function parar(){
      if(!timer) return;
      clearInterval(timer); timer=null;
    }

    // Se deja expuesta para que las pantallas de chat la llamen al leer.
    window.refreshChatUnread=refresh;

    document.addEventListener('visibilitychange', function(){
      if(document.hidden) parar(); else arrancar();
    });

    if(document.hidden) refresh();   // una vez, para pintar el globito
    else arrancar();
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',attach);
  else attach();
})();
