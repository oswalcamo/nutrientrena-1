#!/usr/bin/env python3
"""Genera el banco de pruebas del arrastre de días extrayendo el código REAL
de frontend/rutinas.html (no una copia), y lo deja en el mismo directorio.

Uso:  python3 tests/frontend/generar_harness.py && node tests/frontend/dias_arrastrar.test.js
"""
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = open(os.path.join(RAIZ, 'frontend', 'rutinas.html')).read()
MODULO = open(os.path.join(RAIZ, 'frontend', 'js', 'routine-builder.js')).read()
MODULO_CSS = open(os.path.join(RAIZ, 'frontend', 'css', 'routine-builder.css')).read()

css = '\n'.join(re.findall(r'<style>(.*?)</style>', src, re.S)) + '\n' + MODULO_CSS

# El constructor vive en el módulo compartido, no en la página.
i = MODULO.index('function renderDaysList(){')
j = MODULO.index('\n  setupDayDrag();\n}\n', i) + len('\n  setupDayDrag();\n}\n')
render = MODULO[i:j]

a = MODULO.index('/* \u2500\u2500 Arrastrar d\u00edas')
b = MODULO.index('function startRenameDay(', a)
drag = MODULO[a:b]

# Renombrar un día va en el mismo banco: es el otro sitio donde un clic sobre
# la tarjeta hace algo distinto de seleccionarla.
c = MODULO.index('const BLOCK_LABELS=', b)
renombrar = MODULO[b:c]

harness = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head>
<body>
<div class="days-panel" style="width:260px"><div class="days-list" id="daysList"></div></div>
<script>
function esc(s){return String(s||'');}
let selectedDayIdx=0;
let routineData={days_list:[
  {day_name:'Lunes',blocks:[{exercises:[1,2,3]},{exercises:[4,5]}]},
  {day_name:'Martes',blocks:[{exercises:[1,2,3]},{exercises:[4,5]}]},
  {day_name:'Mi\u00e9rcoles',blocks:[{exercises:[1,2,3]}]},
]};
function renderBlocks(){}
function duplicateDay(){}
function removeDay(){}
function selectDay(idx){selectedDayIdx=idx;renderDaysList();renderBlocks();}
%s
%s
%s
window.__orden=()=>routineData.days_list.map(d=>d.day_name);
window.__sel=()=>selectedDayIdx;
renderDaysList();
</script></body></html>""" % (css, render, drag, renombrar)

destino = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'harness.html')
open(destino, 'w').write(harness)
print('harness generado en', destino)

# ── Harness de las fechas del programa (client-profile.html) ────────────────
perfil = open(os.path.join(RAIZ, 'frontend', 'client-profile.html')).read()
a = perfil.index('/* Fechas en local, sin pasar por UTC')
b = perfil.index('async function saveDates()')
logica = perfil[a:b]

fechas = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<input id="dt_start" type="date"><input id="dt_end" type="date"><input id="dt_weeks" type="number">
<div id="datesError"></div>
<script>
%s
</script></body></html>""" % logica

destino2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fechas.html')
open(destino2, 'w').write(fechas)
print('harness generado en', destino2)


# ── Harness del estado de carga al asignar planes (client-profile.html) ─────
css = '\n'.join(re.findall(r'<style>(.*?)</style>', perfil, re.S))
a = perfil.index('/* Animaci\u00f3n de la pantalla de carga')
b = perfil.index('async function renderEntrenamientoTab()')
carga = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>
<div id="entrenamientoContent"></div><div id="nutricionContent"></div>
<script>
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');}
%s
</script></body></html>""" % (css, perfil[a:b])

destino3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'carga.html')
open(destino3, 'w').write(carga)
print('harness generado en', destino3)


# ── Harness del constructor embebido en la ficha del cliente ───────────────
def _bloque(html, marca):
    i = html.index(marca); seg = html[i:]; prof = 0; j = 0
    while j < len(seg):
        if seg.startswith('<div', j): prof += 1
        elif seg.startswith('</div>', j):
            prof -= 1
            if prof == 0: j += 6; break
        j += 1
    return seg[:j]

cssp = ('\n'.join(re.findall(r'<style>(.*?)</style>', perfil, re.S))
        + '\n' + open(os.path.join(RAIZ, 'frontend', 'css', 'routine-builder.css')).read())
overlay = _bloque(perfil, '<div class="ne-backdrop" id="entBuilderOverlay">')
picker = _bloque(perfil, '<div class="picker-overlay" id="pickerOverlay"')
# El constructor ya no está inline: vive en el módulo compartido.
codigo = open(os.path.join(RAIZ, 'frontend', 'js', 'routine-builder.js')).read()

builder = """<!doctype html><html><head><meta charset="utf-8"><style>%s
.ne-backdrop{display:block !important;opacity:1 !important;visibility:visible !important;}
</style></head><body>
%s
%s
<script>
const API='http://x';
function h(){return{};}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');}
function showToast(m){window.__toast=m;}
let pickerTargetBlockIdx=null, pickerReplaceEi=null;
let selectedDayIdx=0;
let routineData={name:'Rutina de fuerza',training:'Gimnasio',days_list:[
 {day_name:'Lunes',description:'',blocks:[
   {block_type:'normal',content:'',order_index:0,exercises:[
     {training_id:1,training_name:'Press de banca',muscle_group_name:'Pecho',series:3,repetitions:'12',break_time:60,intensity_type:'RPE',intensity_value:8,notes:'',order_index:0},
     {training_id:2,training_name:'Dominadas',muscle_group_name:'Espalda',series:3,repetitions:'8-12',break_time:60,intensity_type:'',intensity_value:null,notes:'',order_index:1}]},
   {block_type:'superset',content:'',order_index:1,exercises:[
     {training_id:3,training_name:'Extensiones triceps',muscle_group_name:'Triceps',series:2,repetitions:'10',break_time:60,intensity_type:'RPE',intensity_value:8,notes:'',order_index:0}]}]},
 {day_name:'Martes',description:'',blocks:[{block_type:'normal',content:'',order_index:0,exercises:[
     {training_id:4,training_name:'Sentadilla',muscle_group_name:'Pierna',series:4,repetitions:'8',break_time:90,intensity_type:'',intensity_value:null,notes:'',order_index:0}]}]},
 {day_name:'Mi\u00e9rcoles',description:'',blocks:[]}
]};
%s
window.__orden=()=>routineData.days_list.map(d=>d.day_name);
window.__ejercicios=()=>routineData.days_list[selectedDayIdx].blocks.map(b=>b.exercises.map(e=>e.training_name));
renderDaysList(); renderBlocks();
</script></body></html>""" % (cssp, overlay, picker, codigo)

destino4 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'builder.html')
open(destino4, 'w').write(builder)
print('harness generado en', destino4)


def _modulo(nombre):
    """Un fichero de `frontend/js/`, para incrustarlo en el harness.

    Los harness no tienen servidor: no pueden cargar `<script src>`. Y las
    páginas ya no llevan la cuenta de macros dentro — está en un módulo
    compartido con el servidor. Sin incrustarlo aquí, el harness revienta con
    "macrosAlimento is undefined" mientras la página real funciona.
    """
    return open(os.path.join(RAIZ, 'frontend', 'js', nombre)).read()


# ── Harness del previo de dietas al asignar ────────────────────────────────
i = perfil.index('/* Cantidad de una fila y su unidad')
j = perfil.index('function toggleDietPreview(', i)

prev = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head>
<body><div class="dietpick-detail" id="out"></div>
<script>%s</script>
<script>
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
%s
window.__pinta=(m)=>{document.getElementById('out').innerHTML=_dietpickComida(m);};
</script></body></html>""" % (cssp, _modulo('macros-alimento.js'), perfil[i:j])

destino5 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'preview.html')
open(destino5, 'w').write(prev)
print('harness generado en', destino5)


# ── Harness de la biblioteca agrupada por organización (diets.html) ────────
dts = open(os.path.join(RAIZ, 'frontend', 'diets.html')).read()
cssd = '\n'.join(re.findall(r'<style>(.*?)</style>', dts, re.S))
a = dts.index('/* \u2500\u2500 Biblioteca agrupada por organizaci\u00f3n')
b = dts.index('function renderTable(diets) {')
logica = dts[a:b]
c = dts.index('function renderTable(diets) {')
d = dts.index('\n}\n', dts.index("return;\n  }\n  tb.innerHTML = grupos.map", c)) + 3
render = dts[c:d]

grupos = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>
<div class="lib-table-wrap"><table class="lib-table"><tbody id="dietsTbody"></tbody></table></div>
<span id="dietTotalLabel"></span><span id="subcountDietas"></span>
<script>
var API='http://x', token='t', allDiets=[];
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');}
function dietRow(d){return '<tr class="fila" data-org="'+(d.organization_id==null?'plat':d.organization_id)+'"><td colspan="8">'+esc(d.title)+'</td></tr>';}
function applyFilter(){ renderTable(window.__datos); }
%s
%s
window.__pinta=(datos,nombres)=>{window.__datos=datos;_orgNombres=nombres;_grpCerrados={};renderTable(datos);};
</script></body></html>""" % (cssd, logica, render)

destino6 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'grupos.html')
open(destino6, 'w').write(grupos)
print('harness generado en', destino6)


# ── Harness de la ejecución de un ejercicio ────────────────────────────────
# Se saca el pintado de la pantalla real, no una copia: si diverge, la copia
# pasaría las pruebas mientras la página se rompe.
ejs = open(os.path.join(RAIZ, 'frontend', 'ejercicios.html')).read()
csse = '\n'.join(re.findall(r'<style>(.*?)</style>', ejs, re.S))
a = ejs.index('  // Hacer caso a lo que el autor escribió')
b = ejs.index("    :'';", ejs.index('const execHtml=', a)) + len("    :'';")
pintado = ejs[a:b]

pasos = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>
<div id="out"></div>
<script>%s</script>
<script>
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
window.__pinta=(texto)=>{
  const ex={description:texto};
%s
  document.getElementById('out').innerHTML=execHtml;
};
</script></body></html>""" % (csse, _modulo('pasos-ejecucion.js'), pintado)

destino7 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pasos.html')
open(destino7, 'w').write(pasos)
print('harness generado en', destino7)


# ── Harness de la lista de la compra ───────────────────────────────────────
# Solo el módulo: las cuentas son lo que puede salir mal, y no necesitan
# pantalla para comprobarse.
lista = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<script>%s</script>
</body></html>""" % _modulo('lista-compra.js')

destino8 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lista.html')
open(destino8, 'w').write(lista)
print('harness generado en', destino8)


# ── Harness del Resumen de Progreso ────────────────────────────────────────
# El alto de la gráfica es lo que se comprueba, y el alto solo existe cuando
# hay una pantalla midiendo: en el código fuente no se ve. Por eso se saca la
# página real con su CSS y se mide con el navegador.
a = perfil.index('function _renderPgResumen() {')
b = perfil.index('/* ══', perfil.index('function _buildLatestCiSection()'))
resumen_js = perfil[a:b]

resumen = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head>
<body style="margin:0">
<div id="marco" style="width:1400px">
  <div class="pg-subtabs-bar">
    <button class="pg-stab active" onclick="showProgresoSubtab('resumen',this)">Resumen</button>
    <button class="pg-stab" onclick="showProgresoSubtab('fuerza',this)">Fuerza</button>
    <button class="pg-stab" onclick="showProgresoSubtab('checkins',this)">Check-ins</button>
  </div>
  <div id="pg-pane-resumen" class="pg-subpane"></div>
  <div id="pg-pane-fuerza" class="pg-subpane" style="display:none">fuerza</div>
  <div id="pg-pane-checkins" class="pg-subpane" style="display:none">checkins</div>
</div>
<script>
const API='http://x'; const clientId=1;
function h(){return{};}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function openTargetModal(){window.__metas=true;}
function showProgresoSubtab(name,btn){
  document.querySelectorAll('.pg-stab').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.pg-subpane').forEach(p=>p.style.display='none');
  if(btn) btn.classList.add('active');
  const pane=document.getElementById('pg-pane-'+name); if(pane) pane.style.display='';
}
var checkins=[], clientData={}, _target=null, clientRoutines=[];
var _fzDatos=null, _fzCargando=false;
%s
window.__pinta=(ck,cd,tg,fz)=>{
  checkins=ck; clientData=cd||{}; _target=tg; _fzDatos=(fz===undefined?[]:fz);
  _resFzError=false; _renderPgResumen();
};
</script></body></html>""" % (cssp, resumen_js)

destino9 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resumen.html')
open(destino9, 'w').write(resumen)
print('harness generado en', destino9)


# ── Harness de la unidad del alimento y del previo de la dieta ─────────────
# El previo se saca de diets.html tal cual, no copiado: el fallo era
# justamente que esa pantalla deducía la unidad por su cuenta y de forma
# distinta al editor que hay dos clics más allá.
dts2 = open(os.path.join(RAIZ, 'frontend', 'diets.html')).read()
# `dppMeals` se pinta en tres sitios de la pagina; el que interesa es el que
# lleva la unidad, asi que se ancla ahi y se retrocede hasta su principio.
ancla = dts2.index("var itemKcal = Math.round(window.macrosAlimento.escalar(al.calories, al, qty));")
i = dts2.rindex("document.getElementById('dppMeals').innerHTML =", 0, ancla)
j = dts2.index("    var title = esc(d.title || '');", ancla)
pinta_previo = dts2[i:j]

unidades = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<div id="dppMeals"></div>
<script>%s</script>
<script>
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
window.__previo=(d)=>{
%s
};
</script></body></html>""" % (_modulo('macros-alimento.js'), pinta_previo)

destino10 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'unidades.html')
open(destino10, 'w').write(unidades)
print('harness generado en', destino10)


# ── Harness de las fotos de progreso del cliente ───────────────────────────
# Se saca el pintado y el borrado de client-progreso.html tal cual: lo que hay
# que comprobar es que el boton aparece, que pregunta antes y que pide el
# borrado del angulo correcto.
prg = open(os.path.join(RAIZ, 'frontend', 'client-progreso.html')).read()
cssg = '\n'.join(re.findall(r'<style>(.*?)</style>', prg, re.S))
a = prg.index('  function setTab(t){')
b = prg.index('  function render(){')
pinta = prg[a:b]
# Se ancla en la variable, no en el comentario: el mismo texto encabeza el
# bloque de CSS, y buscando el comentario se extraia media pagina.
c = prg.rindex('/*', 0, prg.index('  var _porBorrar = null;'))
d = prg.index("  function pickPhoto(){")
borra = prg[c:d]
dialogo = _bloque(prg, '<div class="ask-back" id="askBack">')

fotos = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>
<button class="ptab sel" id="tab-frontal"></button>
<button class="ptab" id="tab-lateral"></button>
<button class="ptab" id="tab-espalda"></button>
<div id="photos"></div>
%s
<div class="toast" id="toast"></div>
<script>
const API='http://x';
function headers(){return{'Content-Type':'application/json'};}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/'/g,'&#39;');}
function fmtDate(d){return String(d||'');}
function toast(m,e){window.__toast=m;window.__err=!!e;}
var _tab='frontal', _data={};
window.__llamadas=[];
window.fetch=function(url,opt){
  window.__llamadas.push({url:url,metodo:(opt&&opt.metodo)||(opt&&opt.method)||'GET'});
  return Promise.resolve({ok:!window.__falla, json:()=>Promise.resolve({})});
};
async function loadProgress(){ window.__recargado=(window.__recargado||0)+1; }
%s
%s
window.__pinta=(datos,tab)=>{_data=datos;_tab=tab||'frontal';renderPhotos();};
document.getElementById('askSi').onclick = borrarFoto;
</script></body></html>""" % (cssg, dialogo, pinta, borra)

destino11 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fotos.html')
open(destino11, 'w').write(fotos)
print('harness generado en', destino11)


# ── Harness de la hoja del RPE ─────────────────────────────────────────────
# Se extrae de client-entrena.html el pintado de la sesion y la hoja, tal
# cual: lo que hay que comprobar es que el numero que se guarda sigue siendo
# el RPE de siempre aunque al cliente se le pregunte por repeticiones.
ent = open(os.path.join(RAIZ, 'frontend', 'client-entrena.html')).read()
csse2 = '\n'.join(re.findall(r'<style>(.*?)</style>', ent, re.S))
a = ent.index('  function prevText(e, si){')
b = ent.index('  function wsToggle(ei, si){')
codigo_ws = ent[a:b]
hoja_html = _bloque(ent, '<div class="rpe-back" id="rpeBack"')

rpe = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>
<div id="wsInner"></div>
%s
<script>
function esc(s){ if(s==null)return''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
var _ws=null;
function _wsThumb(e){ return '<div class="ws-thumb"></div>'; }
%s
window.__pinta=(ex)=>{_ws={exercises:ex};renderWorkout();};
window.__series=()=>_ws.exercises.map(e=>e.sets.map(s=>s.rpe));
</script></body></html>""" % (csse2, hoja_html, codigo_ws)

destino12 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rpe.html')
open(destino12, 'w').write(rpe)
print('harness generado en', destino12)


# ── Harness del menú de "…" de la fila ─────────────────────────────────────
# Se monta la tabla REAL con su CSS real, porque el fallo no estaba en el
# menú sino en el `overflow` de la tabla que lo contenía: con una tabla de
# mentira no se reproduciria.
dts3 = open(os.path.join(RAIZ, 'frontend', 'diets.html')).read()
cssm = '\n'.join(re.findall(r'<style>(.*?)</style>', dts3, re.S))

filas = ''.join(["""<tr class="fila"><td class="lib-td-name">Dieta %d</td>
  <td class="lib-actions">
    <button class="lib-btn-assign">Asignar</button>
    <div class="lib-menu-wrap">
      <button class="lib-icon-btn mas-btn" onclick="menuFila.abrir(event,this)">...</button>
      <div class="lib-menu-dd">
        <div class="lib-menu-item">Editar</div>
        <div class="lib-menu-item">Duplicar</div>
        <div class="lib-menu-item danger">Eliminar</div>
      </div>
    </div>
  </td></tr>""" % i for i in range(1, 31)])

menu = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head>
<body style="margin:0">
<div class="main" style="height:100vh">
  <div class="lib-table-wrap" id="wrap">
    <table class="lib-table"><tbody id="cuerpo">%s</tbody></table>
  </div>
</div>
<script>%s</script>
<script>
/* Como lo hace ejercicios.html: se fabrica el menu y se cuelga del body. */
window.__suelto=(btn)=>{
  var m=document.createElement('div');
  m.className='row-menu';
  m.style.cssText='position:fixed;background:#fff;border:1px solid #E5E7EB;border-radius:10px;'+
    'box-shadow:0 8px 24px rgba(0,0,0,.12);z-index:300;min-width:170px;overflow:hidden;';
  // Con los estilos EN LÍNEA que pone ejercicios.html: sin ellos los botones
  // salen de 7 px, el menú entero cabe en cualquier hueco y la prueba no
  // distingue nada.
  var est='display:flex;align-items:center;gap:8px;width:100%%;padding:10px 14px;'+
    'font-size:13px;color:#374151;background:none;border:none;cursor:pointer;text-align:left;';
  m.innerHTML=['Editar','Ver video','Duplicar','Archivar','Eliminar'].map(function(t){
    return '<button class="lib-menu-item" style="'+est+'">'+t+'</button>';
  }).join('');
  document.body.appendChild(m);
  menuFila.suelto(m, btn);
};
window.__soloUna=()=>{
  var c=document.getElementById('cuerpo');
  Array.prototype.slice.call(c.rows,1).forEach(function(r){c.removeChild(r);});
};
</script></body></html>""" % (cssm, filas, _modulo('menu-fila.js'))

destino13 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'menu.html')
open(destino13, 'w').write(menu)
print('harness generado en', destino13)


# ── Harness del selector de modo de programación ───────────────────────────
# Se saca de client-profile.html el selector y el cambio de modo tal cual. Lo
# que hay que comprobar es que las dos areas (nutricion y entrenamiento) son
# independientes, y eso solo se ve ejecutando el codigo de verdad.
a = perfil.index('var _nutModo = null;')
b = perfil.index('/* La calculadora, con el resumen en la cabecera')
tarjetas = perfil[a:b]
c = perfil.index('/* \u2500\u2500 Cambiar de modo \u2500')
d = perfil.index('/* Re-renderiza solo el planificador')
cambio = perfil[c:d]
modal = _bloque(perfil, '<div class="cmodo-back" id="cmodoBack"')

modos = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>
<div id="nutricionContent"></div>
<div id="entrenamientoContent"></div>
%s
<script>
const API='http://x'; const clientId='cli-1';
function h(){return{};}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');}
function showToast(m,t){window.__toast=m;window.__toastTipo=t;}
function showTab(n){window.__pestana=n;}
function renderCalendarioTab(){window.__calendario=(window.__calendario||0)+1;}
async function renderNutricionTab(){document.getElementById('nutricionContent').innerHTML=_nutModoCardHTML();}
async function renderEntrenamientoTab(){document.getElementById('entrenamientoContent').innerHTML=_entModoCardHTML();}
var clientData={};
window.__puestas=[];
window.fetch=function(url,opt){
  window.__puestas.push({url:url, metodo:opt&&opt.method, cuerpo:opt&&opt.cuerpo||opt&&opt.body});
  return Promise.resolve({ok:!window.__falla, json:()=>Promise.resolve({})});
};
%s
%s
window.__pinta=(nut,ent)=>{
  _nutModo=nut; _entModo=ent; _calSalirEnfoque=false; window.__puestas=[];
  document.getElementById('nutricionContent').innerHTML=_nutModoCardHTML();
  document.getElementById('entrenamientoContent').innerHTML=_entModoCardHTML();
};
window.__modos=()=>({nut:_nutModo, ent:_entModo});
</script></body></html>""" % (cssp, modal, tarjetas, cambio)

destino14 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modos.html')
open(destino14, 'w').write(modos)
print('harness generado en', destino14)


# ── Harness del carril de la distribución semanal ──────────────────────────
# Se saca de client-profile.html el carril y la etiqueta del modal, tal cual:
# el punto de todo esto es que las dos llamen igual a la misma dieta, y con
# una copia eso no se comprueba.
a = perfil.index('/* El carril de la izquierda: la distribución semanal')
b = perfil.index('function _renderNutUI() {')
carril = perfil[a:b]
c = perfil.index('function _wdEtiqueta(d, i) {')
d = perfil.index('\n}\n', c) + 3
etiqueta = perfil[c:d]

dist = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>
<div class="nut-day-side" id="carril" style="width:175px"></div>
<script>
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
const _NUT_DAY_ABV  = ['LUN','MAR','MI\u00c9','JUE','VIE','S\u00c1B','DOM'];
var clientDiets=[], _nutFoco='dia', _nutDayIdx=0, _nutActiveDietIdx=0;
window.__clicks=[];
function selectNutDay(i){window.__clicks.push('dia:'+i);}
function selectNutDiet(i){window.__clicks.push('dieta:'+i);}
function openWeekDistModal(){window.__clicks.push('distribucion');}
function openAssignDietModal(){window.__clicks.push('anadir');}
%s
%s
window.__pinta=(dietas, dias, foco, idx)=>{
  clientDiets=dietas; _nutFoco=foco||'dia';
  if(foco==='dieta') _nutActiveDietIdx=idx||0; else _nutDayIdx=idx||0;
  window.__clicks=[];
  document.getElementById('carril').innerHTML=_nutCarrilHTML(dias);
};
</script></body></html>""" % (cssp, etiqueta, carril)

destino15 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'distribucion.html')
open(destino15, 'w').write(dist)
print('harness generado en', destino15)


# ── Harness del panel del plan (cabecera + comidas) ────────────────────────
# Se saca de client-profile.html el pintado del plan tal cual, para poder
# comprobar las cifras, las unidades de cada fila y a dónde llevan los botones.
# Ojo: "Planificador de macros" aparece tambien en el CSS, mucho antes. Se
# busca DESPUES de la funcion, o el corte sale vacio.
a = perfil.index('function _nutTotalesDe(detail) {')
b = perfil.index('let _nutPlanner = null;', a)
totales = perfil[a:b]
a2 = perfil.index('/* La cabecera del plan: el degradado')
b2 = perfil.index('function _renderNutUI() {')
hero = perfil[a2:b2]
c = perfil.index("        }).join('')}</div>")
c0 = perfil.rindex('foods.map(meal=>{', 0, c)
comidas = perfil[c0:c]

plan = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head>
<body style="margin:0;background:#F8FAFC"><div id="plan" style="padding:18px;max-width:900px"></div>
<script>%s</script>
<script>
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function _nutMealKcal(meal){return (meal.detail||[]).reduce((s,i)=>{const a=i.aliment||{};
  return s+window.macrosAlimento.escalar(a.calories,a,i.quantity_calc||0);},0);}
function _nutTotalKcal(d){return (d.foods||[]).reduce((s,m)=>s+_nutMealKcal(m),0);}
var _HORAS={'Desayuno':'08:00','Media mañana':'11:00','Comida':'14:00'};
function _nutMealTime(n){return _HORAS[n]||'';}
window.__acciones=[];
function openNutEditor(){window.__acciones.push('editar');}
const API='http://x';
var _nutMenuVeces=null, _nutFoco='dia', _nutDayIdx=0, _nutActiveDietIdx=0;
var clientDiets=[], _nutDetail=null, _nutMenu=null;
function _nutMenuDays(){return _nutMenuVeces;}
function showToast(m,t){window.__acciones.push('toast:'+m);}
function _downloadPlanPdf(url,fichero){window.__acciones.push('pdf:'+url+'|'+fichero);}
%s
function removeNutPlan(){window.__acciones.push('borrar');}
%s
%s
window.__estado=(menu,foco,dia,dietas,det)=>{
  _nutMenuVeces=menu; _nutFoco=foco||'dia'; _nutDayIdx=dia||0;
  clientDiets=dietas||[]; _nutDetail=det||null; window.__acciones=[];
};
window.__pinta=(det,mirandoDia,dayName)=>{
  window.__acciones=[];
  const totalKcal=Math.round(_nutTotalKcal(det))||Math.round(det.calories||0);
  const foods=det.foods||[];
  document.getElementById('plan').innerHTML=
    _nutHeroHTML(det,{mirandoDia:!!mirandoDia,dayName:dayName||'Lunes',dayHasDiet:true,totalKcal})
    + '<div class="nut-meals-area">' + %s}).join('') + '</div>';
};
</script></body></html>"""

d0 = perfil.index('function _downloadNutPdf(ev) {')
d1 = perfil.index('\n}\n', d0) + 3
descarga = perfil[d0:d1]

destino16 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plan.html')
open(destino16, 'w').write(
    plan % (cssp, _modulo('macros-alimento.js'), descarga, totales, hero, comidas))
print('harness generado en', destino16)


# ── Harness del plan de entrenamiento ──────────────────────────────────────
# El carril y la tabla del día, sacados de client-profile.html. Lo que hay que
# comprobar es el REPARTO: qué día de la semana toca cada día de la rutina.
a = perfil.index('/* Los días de la semana, para el carril y para el PDF. */')
b = perfil.index('function selectEntDay(')
ent = perfil[a:b]

entre = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head>
<body style="margin:0;background:#F8FAFC">
<div id="entrenamientoContent" style="padding:16px;max-width:1100px"></div>
<script>
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
var clientRoutines=[], clientData={}, _entSelectedDay=0, _entModo='semanal';
window.__acciones=[];
function _entModoCardHTML(){return '';}
function loadSessions(){}
function openSessionModal(){}
function openEntBuilder(i){window.__acciones.push('editor:'+i);}
function _downloadEntPdf(){window.__acciones.push('pdf');}
function changeEntPlan(){window.__acciones.push('cambiar');}
function removeEntPlan(){window.__acciones.push('borrar');}
function selectEntDay(i){_entSelectedDay=i;_renderEntTrainingUI();}
%s
window.__pinta=(rutina,sel)=>{
  clientRoutines=[rutina]; _entSelectedDay=sel||0; window.__acciones=[];
  _renderEntTrainingUI();
};
</script></body></html>""" % (cssp, ent)

destino17 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'entreno.html')
open(destino17, 'w').write(entre)
print('harness generado en', destino17)


# ── Harness del chat dentro de la ficha del cliente ────────────────────────
# Se saca el panel y su lógica de client-profile.html tal cual: lo que hay que
# comprobar es que abre la conversación que YA existe y que un mensaje no se
# pierde si el envío falla.
a = perfil.index('/* \u2550\u2550\u2550')
a = perfil.index('Chat con el cliente, dentro de su ficha')
a = perfil.rindex('/*', 0, a)
b = perfil.index('/* \u2500\u2500 Progreso tab \u2500\u2500 */')
chat_js = perfil[a:b]
panel = _bloque(perfil, '<div class="tab-pane" id="tab-chat">')

chat = """<!doctype html><html><head><meta charset="utf-8"><style>%s
/* El panel vive dentro de una pestaña, y el CSS de la página las oculta
   mientras no estén activas. Aquí siempre lo está. */
.tab-pane{display:block !important;}
</style></head>
<body style="margin:0;background:#F8FAFC"><div style="padding:16px;max-width:900px">
%s
</div>
<script>
const API='http://x'; const clientId='cli-1';
function h(){return{};}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function showToast(m,t){window.__toast=m;window.__toastTipo=t;}
function _renderHeaderControls(){}
var clientData={user_id:77, first_name:'Carlos', last_name:'Gonz\u00e1lez', chat_enabled:true};
window.__llamadas=[]; window.__mensajes=[]; window.__falla=null;
window.fetch=function(url,opt){
  const metodo=(opt&&opt.method)||'GET';
  window.__llamadas.push({url:url, metodo:metodo, cuerpo:opt&&opt.body});
  if (window.__falla && String(url).includes(window.__falla))
    return Promise.resolve({ok:false, status:500, json:()=>Promise.resolve({})});
  let data={};
  if (String(url).includes('/chat/con/')) data={id:'conv-1', type:'individual', creada:false};
  else if (String(url).includes('/messages') && metodo==='GET') data={messages:window.__mensajes};
  return Promise.resolve({ok:true, json:()=>Promise.resolve({data:data})});
};
async function toggleChatEnabled(){
  clientData.chat_enabled = !clientData.chat_enabled;
  window.__llamadas.push({url:'chat-enabled', metodo:'PUT'});
  _cpChatPintaEstado();
}
%s
window.__reset=(msgs,activo)=>{
  _cpChat=null; _cpChatMsgs=[]; _cpChatCargando=false;
  window.__mensajes=msgs||[]; window.__llamadas=[]; window.__toast=null;
  clientData.chat_enabled = activo !== false;
};
</script></body></html>""" % (cssp, panel, chat_js)

destino18 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chatficha.html')
open(destino18, 'w').write(chat)
print('harness generado en', destino18)


# ── Harness de Progreso · Fotos ────────────────────────────────────────────
# Se saca de client-profile.html el pintado entero de la pestaña. Lo que hay
# que comprobar es el reparto de las tomas por fecha y a dónde lleva cada
# clic, y eso solo se ve ejecutando el código de verdad.
a = perfil.index('var FT_ANGULOS = [')
b = perfil.index('function showProgresoSubtab(')
fotos_js = perfil[a:b]

fotos = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head>
<body style="margin:0;background:#F8FAFC">
<div id="pg-pane-fotos" style="padding:16px;max-width:1100px"></div>
<script>
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
var checkins=[];
/* La frecuencia sale del módulo de check-ins, que aquí no hace falta. */
function _ckFrecuencia(){return 'frecuencia quincenal';}
%s
window.__pinta=(cks)=>{
  checkins=cks; _ftAngulo='frente'; _ftIni=null; _ftAct=null; _ftHistFiltro='todos';
  _renderPgFotos();
};
window.__estado=()=>({angulo:_ftAngulo, ini:_ftIni, act:_ftAct, filtro:_ftHistFiltro});
</script></body></html>""" % (cssp, fotos_js)

# `fotos.html` ya lo usa el banco de la pantalla del cliente; este es el de la
# ficha del coach y necesita su propio nombre o uno pisa al otro.
destino19 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fotoscoach.html')
open(destino19, 'w').write(fotos)
print('harness generado en', destino19)


# ── Harness de las tarjetas de partida del plan de comidas ─────────────────
# Se saca de diets.html el `goToStep` de verdad, el `clearForm` de verdad y las
# líneas que cargan las comidas de una dieta guardada: el fallo estaba en la
# decisión de cuándo inventar comidas, y eso solo se ve ejecutándola.
dts4 = open(os.path.join(RAIZ, 'frontend', 'diets.html')).read()

i = dts4.index('function goToStep(n) {')
j = dts4.index('\n}\n', dts4.index('renderMealsBoard();', i)) + 3
goto = dts4[i:j]

i = dts4.index('function clearForm() {')
j = dts4.index('\n}\n', i) + 3
clear = dts4[i:j]

# Lo que hace openForm con una dieta que ya existe.
# Se corta por `_restoreDistribution()`, que está con arreglo y sin él: si el
# corte dependiera de la línea que arregla el fallo, quitar el arreglo rompería
# el generador en vez de hacer fallar la prueba, y la prueba no valdría nada.
i = dts4.index("      _meals = []; _mealSeq = 0; _rowSeq = 0;\n"
               "      document.getElementById('mealsContainer')")
j = dts4.index('_restoreDistribution();', i)
cargar = dts4[i:j]

comidas = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<div id="dpStep1"></div><div id="dpStep2"></div>
<div id="step1Btn"></div><div id="step2Btn"></div>
<span id="mealCountVal">5</span>
<div id="mealsContainer"></div><div id="pm2List"></div><div id="pathoBody"></div>
<div id="pathoArrow"></div>
<input id="f_title"><input id="f_calories"><input id="f_proteins"><input id="f_carbs">
<input id="f_fats"><input id="f_fiber"><input id="f_deficit"><input id="f_surplus">
<select id="f_type"></select><select id="f_style"></select><textarea id="f_notes"></textarea>
<script>
var _meals=[], _mealSeq=0, _rowSeq=0, _refClientId=null, _activeMealId=null;
var _pm2Sembrado=false;
/* Pintar la tarjeta no es lo que se comprueba aqui; que se cree, si. */
function addMeal(food){
  _meals.push({id:++_mealSeq, name:(food&&food.name)||'Comida',
               db_id:(food&&food.id)||null,
               rows:((food&&food.detail)||[]).map(function(){return {aliment_id:'x'};})});
}
function renderMealsBoard(){}
function saveAllMealDOMState(){}
function setGoalMode(){}
function _renderPathoGrid(){}
function updateDistPanel(){}
function recalcTotalMacros(){}
function updatePreview(){}
function renderMealSidebar(){}
function _restoreDistribution(){}
%s
%s

/* removeMeal, tal cual la pagina pero sin el confirm ni el DOM de la tarjeta. */
function quitarComida(mid){
  if (_activeMealId == mid) _activeMealId = null;
  _meals = _meals.filter(function(m){ return m.id != mid; });
}

window.__nueva=()=>{ clearForm(); };
window.__abrirGuardada=(foods)=>{ clearForm(); (function(d){ %s })({foods:foods}); };
window.__comidas=()=>_meals.map(m=>({nombre:m.name, db_id:m.db_id, filas:m.rows.length}));
window.__quitar=(i)=>quitarComida(_meals[i].id);
</script></body></html>""" % (goto, clear, cargar)

destino20 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'comidas.html')
open(destino20, 'w').write(comidas)
print('harness generado en', destino20)


# ── Harness del desplegable de micronutrientes ─────────────────────────────
# El panel lo pinta el módulo compartido; lo que se saca de diets.html es el
# `fsmSelect` de verdad, que es quien tiene que llamarlo al elegir un alimento.
dts5 = open(os.path.join(RAIZ, 'frontend', 'diets.html')).read()
cssm = open(os.path.join(RAIZ, 'frontend', 'css', 'micros-alimento.css')).read()
cssd5 = '\n'.join(re.findall(r'<style>(.*?)</style>', dts5, re.S))

i = dts5.index('function _fsmPresetsFor(unit) {')
j = dts5.index('function fsmConfirmAdd(')
seleccion = dts5[i:j]

micros = """<!doctype html><html><head><meta charset="utf-8">
<style>%s</style><style>%s</style></head>
<body style="margin:0">
<div class="fsm-detail" id="fsmDetail" style="display:none;width:360px">
  <div class="fsm-detail-body">
    <div class="fsm-detail-name" id="fsmDetName">-</div>
    <span class="fsm-item-chip" id="fsmDetChip" style="display:none;"></span>
    <div class="fsm-qty-box"><input id="fsmQtyInput" type="number"><span id="fsmQtyUnit"></span></div>
    <div class="fsm-qty-presets" id="fsmQtyPresets"></div>
    <div class="fsm-portion">
      <div class="fsm-portion-row"><span>Calorías</span><b id="fsmPorK">0</b></div>
      <div class="fsm-portion-row"><span>Proteínas</span><b id="fsmPorP">0</b></div>
      <div class="fsm-portion-row"><span>Carbohidratos</span><b id="fsmPorC">0</b></div>
      <div class="fsm-portion-row"><span>Grasas</span><b id="fsmPorF">0</b></div>
      <div class="fsm-portion-row"><span>Fibra</span><b id="fsmPorFib">0</b></div>
    </div>
    <div id="fsmMicros" style="display:none;"></div>
  </div>
  <button class="fsm-add-btn" id="fsmAddBtn"></button>
</div>
<script>%s</script>
<script>%s</script>
<script>
var _fsmCache = {}, _fsmSelId = null, _fsmQty = 0, _fsmMid = 1;
var _fsmGroups = [{id: 3, name: 'Proteínas'}];
var _meals = [{id: 1, name: 'Desayuno'}];
/* La unidad y su factor los resuelve la pagina con sus propias funciones; aqui
   no es lo que se mide. */
function _unitFromAliment(a){
  var u = window.macrosAlimento.unidadDe(a);
  return u === 'ud' ? 'unidad' : u;
}
function getUnitMult(){ return 1; }
%s
window.__pinta = (al) => { _fsmCache[al.id] = al; fsmSelect(al.id); };
window.__racion = () => ({
  k: document.getElementById('fsmPorK').textContent,
  p: document.getElementById('fsmPorP').textContent,
  fib: document.getElementById('fsmPorFib').textContent,
});
</script></body></html>""" % (cssd5, cssm, _modulo('macros-alimento.js'),
                              _modulo('micros-alimento.js'), seleccion)

destino21 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'micros.html')
open(destino21, 'w').write(micros)
print('harness generado en', destino21)


# ── Harness del creador de recetas: la tarjeta de alimentos ────────────────
# Se saca el CSS y el markup REALES de la pantalla, y el `renderIngrTable` de
# verdad: lo que falla es cómo encaja la tarjeta en la columna, y eso solo se
# ve montando la página tal cual.
rcp = open(os.path.join(RAIZ, 'frontend', 'recipes.html')).read()
cssr = '\n'.join(re.findall(r'<style>(.*?)</style>', rcp, re.S))

i = rcp.index('<div class="fv-body">')
j = rcp.index('<div class="fv-sidebar">', i)
cuerpo = rcp[i:j] + '<div class="fv-sidebar"></div></div>'

i = rcp.index("var FOOD_ICO='")
j = rcp.index('function rcpFocusSearch(', i)
tabla = rcp[i:j]

receta = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head>
<body style="margin:0">
<div style="display:flex;flex-direction:column;height:100vh">
  <div class="fv-bar"><span class="fv-title">Nueva receta</span></div>
  <div class="fv-header"><input class="fv-name" placeholder="Nombre de la receta..."></div>
  %s
</div>
<!-- La cuenta de macros vive en el modulo compartido, como en la pagina. -->
<script>%s</script>
<script>
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
var _ingrRows=[];
function openFoodSearch(){ window.__abierto=true; }
function autoGrow(){}
%s
window.__pinta=(n)=>{
  _ingrRows=[];
  for(var i=1;i<=n;i++) _ingrRows.push({id:i, aliment_id:'a'+i,
    aliment_name:'Alimento '+i, group_food_name:'Lacteos',
    quantity:200, calories:139, proteins:6.4, carbohydrates:5.4, fats:10.2, fiber:0});
  renderIngrTable(); recalcMacros();
};
</script></body></html>""" % (cssr, cuerpo, _modulo('macros-alimento.js'), tabla)

destino22 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'receta.html')
open(destino22, 'w').write(receta)
print('harness generado en', destino22)


# ── Harness del panel de detalle de la receta ──────────────────────────────
# El panel entero —markup y `openRecipePreview`— sale de recipes.html: lo que
# se comprueba es que cada línea diga QUÉ ingrediente es, que la preparación
# salga, y que no se rompa cuando faltan datos.
rcp2 = open(os.path.join(RAIZ, 'frontend', 'recipes.html')).read()
cssr2 = '\n'.join(re.findall(r'<style>(.*?)</style>', rcp2, re.S))

i = rcp2.index('  <div class="rdp-overlay" id="rdpOverlay"')
j = rcp2.index('  <div id="formView">', i)
panel = rcp2[i:j]

i = rcp2.index('function _rcpRaciones(n) {')
j = rcp2.index('function closeRecipePreview(){')
logica = rcp2[i:j]

detalle = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head>
<body style="margin:0">
%s
<script>%s</script>
<script>
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
var _lastRecipes=[];
function openEdit(){ window.__accion='editar'; }
function openDel(){ window.__accion='borrar'; }
%s
window.__pinta=(r)=>{ _lastRecipes=[r]; openRecipePreview(r.id); };
</script></body></html>""" % (cssr2, panel, _modulo('macros-alimento.js'), logica)

destino23 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'detalle-receta.html')
open(destino23, 'w').write(detalle)
print('harness generado en', destino23)


# ── Harness del formulario de receta: etiquetas y opciones clínicas ────────
# Se saca de recipes.html el markup del formulario y su lógica de verdad: lo
# que se comprueba es qué se marca, qué se guarda y qué se recupera al abrir
# una receta ya escrita.
rcp3 = open(os.path.join(RAIZ, 'frontend', 'recipes.html')).read()
cssr3 = '\n'.join(re.findall(r'<style>(.*?)</style>', rcp3, re.S))

i = rcp3.index('        <div class="sec-card">\n          <div class="sec-card-head">Etiquetas y notas</div>')
j = rcp3.index('      </div>\n      <div class="fv-sidebar">', i)
tarjetas = rcp3[i:j]

i = rcp3.index('        <div class="sb-card">\n          <div class="sb-title">Dificultad</div>')
j = rcp3.index('<div id="fFormError"', i)
lateral = rcp3[i:j]

i = rcp3.index('var RCP_TAGS = [')
j = rcp3.index('function _ingMac(row){')
logica = rcp3[i:j]

form = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head>
<body style="margin:0"><div class="fv-main">%s</div><div class="fv-sidebar">%s</div>
<script>
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
var API='http://x';
function headers(){return {};}
/* El catálogo de patologías, como lo devuelve /pathologies/findAll. */
var __PATOS=[{id:1,name:'Celiaquía',grupo:'Intolerancias'},
             {id:2,name:'Intolerancia a la lactosa',grupo:'Intolerancias'},
             {id:3,name:'SII / FODMAP',grupo:'Digestivo'},
             {id:4,name:'Diabetes tipo 2',grupo:'Metabólico'},
             {id:5,name:'Hipertensión',grupo:'Cardiovascular'},
             {id:9,name:'Algo raro',grupo:'Grupo inventado'}];
window.fetch=async()=>({json:async()=>({data:__PATOS})});
%s
window.__abre=(r)=>{
  rcpCargaEtiquetas(r||null);
  document.getElementById('fNotes').value=(r&&r.notes)||'';
  document.getElementById('fDifficulty').value=(r&&r.difficulty)||'facil';
  document.getElementById('fGI').value=(r&&r.glycemic_index)||'';
  document.getElementById('fNa').value=(r&&r.sodium_level)||'';
  document.getElementById('fFiber').value=(r&&r.fiber!=null)?r.fiber:'';
};
window.__sel=()=>JSON.parse(JSON.stringify(_rcpSel));
</script></body></html>""" % (cssr3, tarjetas, lateral, logica)

destino24 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'form-receta.html')
open(destino24, 'w').write(form)
print('harness generado en', destino24)


# ── Harness del resumen nutricional del día (diets.html) ───────────────────
# Se saca el markup de la ventana y la lógica de verdad de diets.html: lo que
# se comprueba es QUÉ se manda a sumar y qué se pinta con lo que vuelve.
dts6 = open(os.path.join(RAIZ, 'frontend', 'diets.html')).read()
cssd6 = '\n'.join(re.findall(r'<style>(.*?)</style>', dts6, re.S))
cssm6 = open(os.path.join(RAIZ, 'frontend', 'css', 'micros-alimento.css')).read()

i = dts6.index('<!-- ── Resumen nutricional del día ── -->')
j = dts6.index('<!-- ── Food Search Modal ── -->')
ventana = dts6[i:j]

i = dts6.index('async function abrirResumenNutricional() {')
j = dts6.index('/* ── Detail panel: select food', i)
logica_rn = dts6[i:j]

resumen = """<!doctype html><html><head><meta charset="utf-8">
<style>%s</style><style>%s</style></head>
<body style="margin:0">
<button class="rn-abrir" onclick="abrirResumenNutricional()">Información nutricional completa</button>
%s
<script>%s</script>
<script>
var API='http://x', token='t';
var _meals=[];
function saveAllMealDOMState(){}
window.__llamadas=[];
window.__respuesta={calories:0,proteins:0,carbohydrates:0,fats:0,micros:{},sin_datos:0};
window.__falla=false;
window.fetch=async(url,opc)=>{
  window.__llamadas.push({url:url, cuerpo:JSON.parse((opc&&opc.body)||'null')});
  if(window.__falla) return {ok:false,json:async()=>({message:'boom'})};
  return {ok:true,json:async()=>({data:window.__respuesta})};
};
%s
window.__comidas=(m)=>{_meals=m;};
</script></body></html>""" % (cssd6, cssm6, ventana, _modulo('micros-alimento.js'), logica_rn)

destino25 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resumen-dia.html')
open(destino25, 'w').write(resumen)
print('harness generado en', destino25)


# ── Harness de las capas de ejercicios.html ────────────────────────────────
# El CSS y el markup reales de la pantalla: lo que se comprueba es qué queda
# ENCIMA de qué, y eso solo lo sabe el navegador.
ejs2 = open(os.path.join(RAIZ, 'frontend', 'ejercicios.html')).read()
csse2 = '\n'.join(re.findall(r'<style>(.*?)</style>', ejs2, re.S))

i = ejs2.index('<div class="modal-overlay" id="videoOverlay"')
j = ejs2.index('\n', ejs2.index('</div>\n</div>', i) + len('</div>\n</div>'))
ventana_video = ejs2[i:j]

capas = """<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head>
<body style="margin:0">
<div style="padding:20px">Lista de ejercicios</div>

<!-- El cajon de detalle, como en la pagina -->
<div class="xv-overlay" id="xvOverlay"></div>
<div class="xv-panel" id="xvPanel">
  <div style="padding:20px" id="xvContenido">Dominadas agarre prono - descripcion del ejercicio</div>
</div>

<!-- El formulario a pantalla completa -->
<div class="xf-panel" id="xfPanel"><div style="padding:20px">Formulario</div></div>

%s

<div class="toast" id="toast">Un aviso</div>

<script>
window.__abreCajon=()=>{
  document.getElementById('xvOverlay').classList.add('open');
  document.getElementById('xvPanel').classList.add('open');
};
window.__abreFormulario=()=>{ document.getElementById('xfPanel').classList.add('open'); };
window.__abreVideo=()=>{ document.getElementById('videoOverlay').classList.add('open'); };
window.__avisa=()=>{ document.getElementById('toast').classList.add('show'); };
/* Quien manda en un punto de la pantalla: es lo que ve y toca el usuario. */
window.__encima=(sel)=>{
  const c=document.querySelector(sel).getBoundingClientRect();
  const el=document.elementFromPoint(c.left+c.width/2, c.top+c.height/2);
  return el ? (el.closest('#videoOverlay') ? 'video'
             : el.closest('#xfPanel') ? 'formulario'
             : el.closest('#xvPanel') ? 'cajon'
             : el.id || el.className || el.tagName) : 'nada';
};
</script></body></html>""" % (csse2, ventana_video)

destino26 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'capas-ejercicios.html')
open(destino26, 'w').write(capas)
print('harness generado en', destino26)
