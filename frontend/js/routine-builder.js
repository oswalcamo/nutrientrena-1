/* ══════════════════════════════════════════════════════════════════════════
   Constructor de rutinas — código compartido

   Lo usan dos pantallas: rutinas.html (biblioteca) y client-profile.html (el
   plan del cliente). Antes cada una tenía su copia, y la de client-profile se
   quedó congelada: le faltaban el buscador de ejercicios nuevo, mover
   ejercicios, los contadores por día y el arrastre. Se desincronizaban solas
   cada vez que alguien tocaba una.

   Lo que NO vive aquí, porque es distinto en cada pantalla:
   - Guardar (una crea/actualiza la rutina de la biblioteca, la otra la del
     cliente ya asignado).
   - Abrir y cerrar el editor.
   - El listado y sus filtros.

   La página debe declarar antes de usarlo:
     routineData, selectedDayIdx, pickerTargetBlockIdx, pickerReplaceEi
   y aportar API, esc() y showToast().
   ══════════════════════════════════════════════════════════════════════════ */

/* Cabeceras de autenticación: rutinas.html las llama authHeaders() y
   client-profile.html h(). Se resuelve en caliente para no obligar a ninguna de
   las dos a renombrar la suya. */
function _rbHeaders() {
  if (typeof authHeaders === 'function') return authHeaders();
  if (typeof h === 'function') return h();
  return {};
}

function addDay(){const idx=routineData.days_list.length;routineData.days_list.push({day_name:`Día ${idx+1}`,description:'',blocks:[]});renderDaysList();selectDay(routineData.days_list.length-1);}
function removeDay(idx){if(!confirm('¿Eliminar este día y todos sus ejercicios?'))return;routineData.days_list.splice(idx,1);if(selectedDayIdx>=routineData.days_list.length)selectedDayIdx=Math.max(0,routineData.days_list.length-1);renderDaysList();renderBlocks();}
function duplicateDay(idx){
  const src=routineData.days_list[idx];
  const newName=`Día ${routineData.days_list.length+1}`;
  const copy={
    day_name:newName,
    description:src.description||'',
    blocks:src.blocks.map(blk=>({
      block_type:blk.block_type,
      content:blk.content||'',
      order_index:blk.order_index,
      exercises:blk.exercises.map(ex=>({...ex}))
    }))
  };
  routineData.days_list.splice(idx+1,0,copy);
  selectDay(idx+1);
}
function selectDay(idx){selectedDayIdx=idx;renderDaysList();renderBlocks();}
function renderDaysList(){
  const container=document.getElementById('daysList');container.innerHTML='';
  const GRIP='<svg width="12" height="16" fill="currentColor" viewBox="0 0 16 16"><circle cx="5" cy="3" r="1.4"/><circle cx="11" cy="3" r="1.4"/><circle cx="5" cy="8" r="1.4"/><circle cx="11" cy="8" r="1.4"/><circle cx="5" cy="13" r="1.4"/><circle cx="11" cy="13" r="1.4"/></svg>';
  routineData.days_list.forEach((day,i)=>{
    const nBlocks=day.blocks.length;
    const nEx=day.blocks.reduce((s,b)=>s+(b.exercises?b.exercises.length:0),0);
    const chip=document.createElement('div');chip.className=`day-chip${i===selectedDayIdx?' active':''}`;
    chip.innerHTML=`<span class="day-grip" title="Arrastrar">${GRIP}</span><div class="day-chip-main"><span class="day-chip-name" title="Doble clic para renombrar">${esc(day.day_name)}</span><span class="day-chip-sub">${nBlocks} ${nBlocks===1?'bloque':'bloques'} · ${nEx} ${nEx===1?'ejercicio':'ejercicios'}</span></div><div class="day-actions"><button class="day-edit-btn" title="Renombrar día"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button><button class="day-dup-btn" title="Duplicar día"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button><button class="day-rm" title="Eliminar día"><svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button></div>`;
    chip.querySelector('.day-chip-name').addEventListener('dblclick',(e)=>{e.stopPropagation();startRenameDay(i,chip);});
    chip.querySelector('.day-edit-btn').addEventListener('click',(e)=>{e.stopPropagation();startRenameDay(i,chip);});
    chip.querySelector('.day-dup-btn').addEventListener('click',(e)=>{e.stopPropagation();duplicateDay(i);});
    chip.querySelector('.day-rm').addEventListener('click',(e)=>{e.stopPropagation();removeDay(i);});
    chip.addEventListener('click',()=>{
      // Tras arrastrar de verdad no hay que seleccionar: el puntero acaba
      // sobre otra tarjeta y cambiaría de día sin que nadie lo pida.
      if(_dayDrag.justDragged)return;
      /* Ya seleccionado: no hay nada que cambiar, y repintar la lista sí tiene
         consecuencias. Se lleva por delante el recuadro de renombrar, y hacía
         que el doble clic sobre el nombre —lo que promete su propio tooltip—
         no funcionara nunca: el primer clic repintaba y el segundo caía sobre
         un elemento recién creado que nunca llegaba a ver el doble clic. */
      if(i===selectedDayIdx)return;
      selectDay(i);
    });
    container.appendChild(chip);
  });
  setupDayDrag();
}

/* ── Arrastrar días para reordenarlos ──────────────────────────────────────
   El asa ya estaba pintada y con cursor:grab, pero era decorativa: no había
   ni atributo draggable ni manejadores, así que no se movía nada. Se resuelve
   con el mismo patrón de pointer events que ya usan los ejercicios (fantasma
   flotante + hueco que guarda el sitio), para no meter una segunda forma de
   arrastrar distinta en el mismo editor. */
let _dayDrag={ghost:null,srcChip:null,chipMap:null,offX:0,offY:0,moved:false,startX:0,startY:0,justDragged:false};

function _dayAbortDrag(){
  if(_dayDrag.ghost){_dayDrag.ghost.remove();_dayDrag.ghost=null;}
  if(_dayDrag.srcChip){_dayDrag.srcChip.classList.remove('day-placeholder');_dayDrag.srcChip=null;}
  _dayDrag.moved=false;
}

document.addEventListener('keydown',e=>{if(e.key==='Escape'&&_dayDrag.srcChip){_dayAbortDrag();renderDaysList();}});

document.addEventListener('pointermove',e=>{
  const d=_dayDrag;
  if(!d.srcChip)return;
  if(!d.moved){
    if(Math.hypot(e.clientX-d.startX,e.clientY-d.startY)<5)return;  // un clic no es un arrastre
    d.moved=true;
    const rect=d.srcChip.getBoundingClientRect();
    d.ghost=d.srcChip.cloneNode(true);
    Object.assign(d.ghost.style,{
      position:'fixed',top:rect.top+'px',left:rect.left+'px',
      width:rect.width+'px',margin:'0',zIndex:'9999',pointerEvents:'none',
      background:'#fff',borderRadius:'12px',
      boxShadow:'0 16px 48px rgba(0,0,0,.22),0 4px 12px rgba(0,0,0,.12)',
      transform:'rotate(2deg) scale(1.03)',opacity:'0',transition:'opacity .08s',
    });
    document.body.appendChild(d.ghost);
    requestAnimationFrame(()=>{if(d.ghost)d.ghost.style.opacity='.97';});
    d.srcChip.classList.add('day-placeholder');
  }
  if(!d.ghost)return;
  d.ghost.style.top=(e.clientY-d.offY)+'px';
  d.ghost.style.left=(e.clientX-d.offX)+'px';

  const el=document.elementFromPoint(e.clientX,e.clientY);
  if(!el)return;
  const tgt=el.closest('.day-chip');
  if(!tgt||tgt===d.srcChip)return;
  const list=document.getElementById('daysList');
  if(!list||tgt.parentNode!==list)return;
  const tr=tgt.getBoundingClientRect();
  if(e.clientY<tr.top+tr.height/2)list.insertBefore(d.srcChip,tgt);
  else list.insertBefore(d.srcChip,tgt.nextSibling);
});

document.addEventListener('pointerup',()=>{
  const d=_dayDrag;
  if(!d.srcChip)return;
  if(!d.moved){_dayAbortDrag();return;}  // clic en el asa sin mover

  const list=document.getElementById('daysList');
  if(!list){_dayAbortDrag();return;}

  // La selección tiene que seguir al DÍA, no al índice: si no, arrastrar un
  // día te deja editando los bloques de otro.
  const diaSeleccionado=routineData.days_list[selectedDayIdx];
  const nuevoOrden=[...list.querySelectorAll('.day-chip')].map(c=>d.chipMap.get(c)).filter(Boolean);
  if(nuevoOrden.length===routineData.days_list.length){
    routineData.days_list=nuevoOrden;
    const idx=nuevoOrden.indexOf(diaSeleccionado);
    if(idx>=0)selectedDayIdx=idx;
  }

  const movido=d.chipMap.get(d.srcChip);
  const idxMovido=routineData.days_list.indexOf(movido);

  if(d.ghost){
    const finalRect=d.srcChip.getBoundingClientRect();
    Object.assign(d.ghost.style,{
      transition:'top .22s cubic-bezier(.22,1,.36,1),left .22s cubic-bezier(.22,1,.36,1),transform .2s,opacity .15s .05s,box-shadow .2s',
      top:finalRect.top+'px',left:finalRect.left+'px',
      transform:'rotate(0deg) scale(1)',opacity:'0',boxShadow:'0 2px 8px rgba(0,0,0,.06)',
    });
    const g=d.ghost; d.ghost=null;
    setTimeout(()=>g.remove(),280);
  }

  d.srcChip.classList.remove('day-placeholder');
  d.srcChip=null; d.moved=false;

  // El click llega justo después del pointerup; sin esta bandera seleccionaría
  // el día que hubiera debajo del puntero al soltar.
  d.justDragged=true;
  setTimeout(()=>{d.justDragged=false;},0);

  renderDaysList();
  renderBlocks();
  if(idxMovido>=0){
    const asentado=document.querySelectorAll('#daysList .day-chip')[idxMovido];
    if(asentado){asentado.classList.add('day-settle');setTimeout(()=>asentado.classList.remove('day-settle'),600);}
  }
});

function setupDayDrag(){
  _dayDrag.chipMap=new Map();
  const chips=document.querySelectorAll('#daysList .day-chip');
  chips.forEach((chip,i)=>{
    _dayDrag.chipMap.set(chip,routineData.days_list[i]);
    const grip=chip.querySelector('.day-grip');
    if(!grip)return;
    grip.addEventListener('pointerdown',e=>{
      e.preventDefault();
      _dayAbortDrag();
      _dayDrag.srcChip=chip;
      _dayDrag.startX=e.clientX; _dayDrag.startY=e.clientY;
      const rect=chip.getBoundingClientRect();
      _dayDrag.offX=e.clientX-rect.left; _dayDrag.offY=e.clientY-rect.top;
      _dayDrag.moved=false;
      grip.setPointerCapture(e.pointerId);
    });
  });
}
function startRenameDay(idx,chip){
  const nameSpan=chip.querySelector('.day-chip-name');if(!nameSpan)return;
  const input=document.createElement('input');input.className='day-chip-input';input.value=routineData.days_list[idx].day_name;
  nameSpan.replaceWith(input);input.focus();input.select();
  /* El recuadro vive DENTRO de la tarjeta del día, y la tarjeta entera
     selecciona su día al hacer clic —lo que repinta la lista y se lleva por
     delante este recuadro con lo que hubiera escrito—. Así que un clic aquí
     dentro se queda aquí: es para poner el cursor entre dos letras y corregir
     una parte, no para cambiar de día. */
  ['pointerdown','mousedown','click','dblclick'].forEach(ev=>
    input.addEventListener(ev,e=>e.stopPropagation()));
  const commit=()=>{const newName=input.value.trim()||routineData.days_list[idx].day_name;routineData.days_list[idx].day_name=newName;renderDaysList();if(idx===selectedDayIdx){const titleEl=document.getElementById('selectedDayName');if(titleEl)titleEl.textContent=newName;}};
  input.addEventListener('blur',commit);
  input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();input.blur();}if(e.key==='Escape'){input.value=routineData.days_list[idx].day_name;input.blur();}});
}

const BLOCK_LABELS={
  warmup:'<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 2c0 6-6 8-6 14a6 6 0 0 0 12 0c0-6-6-8-6-14z"/><path d="M12 12c0 3-2 4-2 7a2 2 0 0 0 4 0c0-3-2-4-2-7z"/></svg> Calentamiento',
  normal:'<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="2" width="6" height="4" rx="1"/><path d="M5 4h2a2 2 0 0 1 2 2v0a2 2 0 0 0 2 2h6a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/></svg> Normal',
  superset:'<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg> Superserie',
  circuit:'<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> Circuito',
  text:'<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/></svg> Texto',
};
const BLK_META={
  warmup:{label:'Calentamiento',desc:'Movilidad, activación y preparación articular antes del entrenamiento principal',ico:'<svg width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 2c0 6-6 8-6 14a6 6 0 0 0 12 0c0-6-6-8-6-14z"/><path d="M12 12c0 3-2 4-2 7a2 2 0 0 0 4 0c0-3-2-4-2-7z"/></svg>'},
  normal:{label:'Bloque normal',desc:'Ejercicios principales del entrenamiento',ico:'<svg width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>'},
  superset:{label:'Superserie',desc:'Dos ejercicios seguidos sin descanso entre ellos',ico:'<svg width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>'},
  circuit:{label:'Circuito',desc:'Varios ejercicios en secuencia, repitiendo rondas',ico:'<svg width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>'},
  text:{label:'Texto',desc:'Instrucciones o notas para el día',ico:'<svg width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/></svg>'},
};
const EX_DUMBBELL='<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6.5 6.5 17.5 17.5M4 12l-1.5 1.5a2.12 2.12 0 0 0 3 3L7 18M17 6l1-1a2.12 2.12 0 0 1 3 3l-1 1"/><path d="m8 8 8 8"/></svg>';
function moveExercise(bi,ei,dir){const arr=routineData.days_list[selectedDayIdx].blocks[bi].exercises;const j=ei+dir;if(j<0||j>=arr.length)return;const t=arr[ei];arr[ei]=arr[j];arr[j]=t;arr.forEach((e,i)=>e.order_index=i);renderBlocks();}
function toggleBlockCollapse(bi){const el=document.querySelector('.blk[data-bi="'+bi+'"]');if(el)el.classList.toggle('collapsed');}
function toggleBlockMenu(){document.getElementById('blockTypeMenu').classList.toggle('open');}
document.addEventListener('click',(e)=>{if(!e.target.closest('.add-block-wrap'))document.getElementById('blockTypeMenu')?.classList.remove('open');});
function addBlock(type='normal'){if(!routineData.days_list.length){showToast('Agrega un día primero','error');return;}const day=routineData.days_list[selectedDayIdx];day.blocks.push({block_type:type,content:'',order_index:day.blocks.length,exercises:[]});renderBlocks();}
function updateBlockContent(bi,value){routineData.days_list[selectedDayIdx].blocks[bi].content=value;}
function removeBlock(blockIdx){const blk=routineData.days_list[selectedDayIdx].blocks[blockIdx];const msg=blk?.block_type==='text'?'¿Eliminar este bloque de texto?':'¿Eliminar este bloque y todos sus ejercicios?';if(!confirm(msg))return;routineData.days_list[selectedDayIdx].blocks.splice(blockIdx,1);renderBlocks();}
function updateDayNote(value){if(routineData.days_list[selectedDayIdx])routineData.days_list[selectedDayIdx].description=value;}
function renderBlocks(){
  const container=document.getElementById('blocksList');const titleEl=document.getElementById('selectedDayName');
  const addRow=document.getElementById('blockAddRow');const notesCard=document.getElementById('dayNotesCard');const notesTa=document.getElementById('dayNotes');
  if(!routineData.days_list.length){
    titleEl.textContent='Sin días';
    container.innerHTML=`<div class="empty-day"><div class="ed-ico"><svg width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg></div><div class="ed-title">Añade un día para empezar</div><div class="ed-sub">Pulsa «+ Añadir día» en el panel de la izquierda.</div></div>`;
    if(addRow)addRow.style.display='none';if(notesCard)notesCard.style.display='none';return;
  }
  const day=routineData.days_list[selectedDayIdx];titleEl.textContent=day.day_name;
  renderDaysList();  // refresca los contadores "X bloques · Y ejercicios"
  if(addRow)addRow.style.display='';if(notesCard)notesCard.style.display='';
  if(notesTa&&notesTa.value!==(day.description||''))notesTa.value=day.description||'';
  if(!day.blocks.length){container.innerHTML=`<div class="empty-day"><div class="ed-ico"><svg width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg></div><div class="ed-title">Añade bloques para construir este día</div><div class="ed-sub">Un bloque puede ser calentamiento, normal, superserie o circuito.</div></div>`;return;}
  const CHEV='<svg class="blk-chev" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>';
  const XICO='<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
  const UP='<svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.4" viewBox="0 0 24 24"><polyline points="18 15 12 9 6 15"/></svg>';
  const DOWN='<svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.4" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>';
  const COPY='<svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
  const TRASH='<svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>';
  const INT_OPTS=(v)=>['','rpe','rir','pct1rm','weight'].map(o=>{const lbl={'':'—',rpe:'RPE',rir:'RIR',pct1rm:'%1RM',weight:'Peso'}[o];return `<option value="${o}"${(v||'')===o?' selected':''}>${lbl}</option>`;}).join('');

  container.innerHTML=day.blocks.map((blk,bi)=>{
    const meta=BLK_META[blk.block_type]||BLK_META.normal;
    const head=`<div class="blk-head" onclick="toggleBlockCollapse(${bi})">${CHEV}<span class="blk-ico">${meta.ico}</span><span class="blk-title">${meta.label}</span><span class="blk-desc">${meta.desc}</span><button class="blk-del" onclick="event.stopPropagation();removeBlock(${bi})">${XICO} Eliminar bloque</button></div>`;
    if(blk.block_type==='text'){
      return`<div class="blk text" data-bi="${bi}">${head}<div class="blk-body"><textarea class="blk-textarea" placeholder="Escribe instrucciones, indicaciones o notas para este día…" oninput="updateBlockContent(${bi},this.value)">${esc(blk.content)}</textarea></div></div>`;
    }
    const rows=blk.exercises.map((ex,ei)=>{
      const nm=ex.training_name?`<span class="ex-nm2">${esc(ex.training_name)}</span>`:`<span class="ex-nm2 empty">Elegir ejercicio</span>`;
      const mg=`<span class="ex-mg2">${ex.muscle_group_name?esc(ex.muscle_group_name)+' · ':''}<span class="ex-change">cambiar</span></span>`;
      const ico=ex.image?`<img src="${esc(ex.image)}" alt="">`:EX_DUMBBELL;
      return`<div class="ex-row2" data-bi="${bi}" data-ei="${ei}">`
        +`<div class="ex-move"><button title="Subir" onclick="moveExercise(${bi},${ei},-1)">${UP}</button><button title="Bajar" onclick="moveExercise(${bi},${ei},1)">${DOWN}</button></div>`
        +`<div class="ex-id" onclick="openPicker(${bi},${ei})" title="Cambiar ejercicio"><span class="ex-ico2">${ico}</span><span class="ex-idtxt">${nm}${mg}</span></div>`
        +`<div class="ex-cell"><input type="number" min="1" max="20" value="${esc(ex.series)}" placeholder="—" onchange="updateEx(${bi},${ei},'series',this.value)"></div>`
        +`<div class="ex-cell"><input type="text" value="${esc(ex.repetitions)}" placeholder="8-12" onchange="updateEx(${bi},${ei},'repetitions',this.value)"></div>`
        +`<div class="ex-cell"><input type="number" value="${esc(ex.break_time)}" placeholder="seg" onchange="updateEx(${bi},${ei},'break_time',this.value)"></div>`
        +`<div class="ex-cell"><select onchange="updateEx(${bi},${ei},'intensity_type',this.value)">${INT_OPTS(ex.intensity_type)}</select></div>`
        +`<div class="ex-cell"><input type="text" value="${esc(ex.intensity_value)}" placeholder="Val." onchange="updateEx(${bi},${ei},'intensity_value',this.value)"></div>`
        +`<div class="ex-cell ex-notes2"><input type="text" value="${esc(ex.notes)}" placeholder="Nota…" onchange="updateEx(${bi},${ei},'notes',this.value)"></div>`
        +`<div class="ex-act"><button title="Subir" onclick="moveExercise(${bi},${ei},-1)">${UP}</button><button title="Bajar" onclick="moveExercise(${bi},${ei},1)">${DOWN}</button><button title="Duplicar" onclick="duplicateExercise(${bi},${ei})">${COPY}</button><button class="del" title="Eliminar" onclick="removeExercise(${bi},${ei})">${TRASH}</button></div>`
        +`</div>`;
    }).join('');
    const header=blk.exercises.length?`<div class="ex-head-row"><div class="exh exh-name">Ejercicio</div><div class="exh">Series</div><div class="exh">Reps</div><div class="exh">Desc.</div><div class="exh">Intensidad</div><div class="exh">Valor</div><div class="exh">Notas</div><div class="exh"></div></div>`:'';
    return`<div class="blk ${blk.block_type}" data-bi="${bi}">${head}<div class="blk-body">${header}${rows}<button class="blk-addex" onclick="openPicker(${bi})"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>Añadir ejercicio</button></div></div>`;
  }).join('');
}
function updateEx(bi,ei,field,value){const ex=routineData.days_list[selectedDayIdx].blocks[bi].exercises[ei];if(field==='series'||field==='break_time')ex[field]=parseInt(value)||null;else ex[field]=value;}
function removeExercise(bi,ei){if(!confirm('¿Eliminar este ejercicio?'))return;routineData.days_list[selectedDayIdx].blocks[bi].exercises.splice(ei,1);renderBlocks();}

function duplicateExercise(bi,ei){
  const blk=routineData.days_list[selectedDayIdx].blocks[bi];
  const src=blk.exercises[ei];
  // Copy specs only — exercise identity is chosen via picker
  const copy={
    training_id:null,training_name:'',muscle_group_name:'',
    series:src.series,repetitions:src.repetitions,break_time:src.break_time,
    intensity_type:src.intensity_type,intensity_value:src.intensity_value,
    notes:src.notes,order_index:ei+1
  };
  blk.exercises.splice(ei+1,0,copy);
  blk.exercises.forEach((e,i)=>{e.order_index=i;});
  renderBlocks();
  // Open picker in replace mode so the user picks which exercise goes in this slot
  openPicker(bi,ei+1);
}

// ── Exercise drag state (module-level so document listeners are added once) ──
let _exDrag={ghost:null,srcRow:null,srcBi:null,rowMap:null,offX:0,offY:0,moved:false,startX:0,startY:0};

function _exAbortDrag(){
  if(_exDrag.ghost){_exDrag.ghost.remove();_exDrag.ghost=null;}
  if(_exDrag.srcRow){_exDrag.srcRow.classList.remove('ex-placeholder');_exDrag.srcRow=null;}
  _exDrag.srcBi=null; _exDrag.moved=false;
}

document.addEventListener('keydown',e=>{if(e.key==='Escape'&&_exDrag.srcRow)_exAbortDrag();});

// pointermove and pointerup live on document — never miss an event regardless of where pointer lands
document.addEventListener('pointermove',e=>{
  const d=_exDrag;
  if(!d.srcRow)return;
  if(!d.moved){
    if(Math.hypot(e.clientX-d.startX,e.clientY-d.startY)<5)return;
    d.moved=true;
    const rect=d.srcRow.getBoundingClientRect();
    const tbl=document.createElement('table');
    tbl.className='exercise-table';
    tbl.style.cssText=`width:${rect.width}px;border-collapse:collapse;table-layout:fixed;`;
    const tb=document.createElement('tbody');
    tb.appendChild(d.srcRow.cloneNode(true));
    tbl.appendChild(tb);
    d.ghost=document.createElement('div');
    d.ghost.appendChild(tbl);
    Object.assign(d.ghost.style,{
      position:'fixed',top:rect.top+'px',left:rect.left+'px',
      width:rect.width+'px',zIndex:'9999',pointerEvents:'none',
      borderRadius:'8px',background:'#fff',overflow:'hidden',
      boxShadow:'0 16px 48px rgba(0,0,0,.22),0 4px 12px rgba(0,0,0,.12)',
      transform:'rotate(2deg) scale(1.03)',opacity:'0',transition:'opacity .08s',
    });
    document.body.appendChild(d.ghost);
    requestAnimationFrame(()=>{if(d.ghost)d.ghost.style.opacity='.97';});
    d.srcRow.classList.add('ex-placeholder');
  }
  if(!d.ghost)return;
  d.ghost.style.top=(e.clientY-d.offY)+'px';
  d.ghost.style.left=(e.clientX-d.offX)+'px';

  const el=document.elementFromPoint(e.clientX,e.clientY);
  if(!el)return;
  const tgt=el.closest('tr.ex-row');
  if(!tgt||tgt===d.srcRow||parseInt(tgt.dataset.bi)!==d.srcBi)return;
  const tr=tgt.getBoundingClientRect();
  const tbody=tgt.closest('tbody');
  if(e.clientY<tr.top+tr.height/2){tbody.insertBefore(d.srcRow,tgt);}
  else{tbody.insertBefore(d.srcRow,tgt.nextSibling);}
});

document.addEventListener('pointerup',()=>{
  const d=_exDrag;
  if(!d.srcRow)return;
  if(!d.moved){_exAbortDrag();return;} // tap on handle with no movement

  const tbody=d.srcRow.closest('tbody');
  if(!tbody){_exAbortDrag();return;} // row was detached mid-drag

  const newOrder=[...tbody.querySelectorAll('tr.ex-row')].map(r=>d.rowMap.get(r)).filter(Boolean);
  routineData.days_list[selectedDayIdx].blocks[d.srcBi].exercises=newOrder;
  newOrder.forEach((ex,i)=>{ex.order_index=i;});

  const movedEx=d.rowMap.get(d.srcRow);
  const newEi=newOrder.indexOf(movedEx);
  const si=d.srcBi;

  if(d.ghost){
    const finalRect=d.srcRow.getBoundingClientRect();
    Object.assign(d.ghost.style,{
      transition:'top .22s cubic-bezier(.22,1,.36,1),left .22s cubic-bezier(.22,1,.36,1),transform .2s,opacity .15s .05s,box-shadow .2s',
      top:finalRect.top+'px',left:finalRect.left+'px',
      transform:'rotate(0deg) scale(1)',opacity:'0',boxShadow:'0 2px 8px rgba(0,0,0,.06)',
    });
    const g=d.ghost; d.ghost=null;
    setTimeout(()=>g.remove(),280);
  }

  d.srcRow.classList.remove('ex-placeholder');
  d.srcRow=null; d.srcBi=null; d.moved=false;

  renderBlocks();
  if(newEi>=0){
    const settled=document.querySelector(`tr.ex-row[data-bi="${si}"][data-ei="${newEi}"]`);
    if(settled){settled.classList.add('ex-settle');setTimeout(()=>settled.classList.remove('ex-settle'),600);}
  }
});

function setupExerciseDrag(){
  // Rebuild rowMap each time blocks are rendered
  _exDrag.rowMap=new Map();
  document.querySelectorAll('.ex-row').forEach(row=>{
    const bi=parseInt(row.dataset.bi),ei=parseInt(row.dataset.ei);
    _exDrag.rowMap.set(row,routineData.days_list[selectedDayIdx].blocks[bi].exercises[ei]);
  });

  document.querySelectorAll('.ex-drag-handle').forEach(handle=>{
    handle.addEventListener('pointerdown',e=>{
      e.preventDefault();
      _exAbortDrag(); // clear any stale state
      const row=handle.closest('tr');
      if(!row)return;
      _exDrag.srcRow=row;
      _exDrag.srcBi=parseInt(row.dataset.bi);
      _exDrag.startX=e.clientX; _exDrag.startY=e.clientY;
      const rect=row.getBoundingClientRect();
      _exDrag.offX=e.clientX-rect.left; _exDrag.offY=e.clientY-rect.top;
      _exDrag.moved=false;
      // Capture on handle so pointer events still route through the global document listeners
      handle.setPointerCapture(e.pointerId);
    });
  });
}

let pickerMgFilter=null;let pickerSearchTimeout=null;
let _pkTrainings=null,_pkGroups=[],_pkView=[],_pkLoading=false;
const PK_ICO='<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6.5 6.5 17.5 17.5M4 12l-1.5 1.5a2.12 2.12 0 0 0 3 3L7 18M17 6l1-1a2.12 2.12 0 0 1 3 3l-1 1"/><path d="m8 8 8 8"/></svg>';

function openPicker(blockIdx,replaceEi=null){
  pickerTargetBlockIdx=blockIdx;pickerReplaceEi=replaceEi;
  document.getElementById('pickerSearch').value='';
  document.getElementById('pickerOverlay').classList.add('open');
  loadPickerCatalog();
  setTimeout(()=>document.getElementById('pickerSearch').focus(),50);
}
function closePicker(){document.getElementById('pickerOverlay').classList.remove('open');}

function buildPkGroups(){
  const order=[],map={};
  (_pkTrainings||[]).forEach(t=>{const nm=t.muscle_group_name||'Otros';if(!map[nm]){map[nm]={name:nm,count:0};order.push(nm);}map[nm].count++;});
  _pkGroups=order.map(nm=>map[nm]);
}
async function loadPickerCatalog(){
  if(_pkTrainings){ if(pickerMgFilter==null&&_pkGroups.length)pickerMgFilter=_pkGroups[0].name; renderPicker(); return; }
  if(_pkLoading)return;_pkLoading=true;
  document.getElementById('pickerResults').innerHTML='<div class="picker-empty">Cargando ejercicios…</div>';
  try{
    const r=await fetch(`${API}/trainings/search?per_page=1000`,{headers:_rbHeaders()});
    const d=await r.json();
    _pkTrainings=(d.data&&d.data.data)||d.data||[];
    buildPkGroups();
    if(_pkGroups.length)pickerMgFilter=_pkGroups[0].name;
    renderPicker();
  }catch{document.getElementById('pickerResults').innerHTML='<div class="picker-empty">Error al cargar el catálogo.</div>';}
  finally{_pkLoading=false;}
}
function renderPicker(){renderPkMgs();renderPkGrid();}
function renderPkMgs(){
  const box=document.getElementById('pickerMgs');
  box.innerHTML='<div class="picker-mgs-lbl">Grupos musculares</div>'+_pkGroups.map((g,i)=>
    `<div class="pk-mg${pickerMgFilter===g.name?' active':''}" onclick="pkSetMg(${i})"><span>${esc(g.name)}</span><span class="pk-count">${g.count}</span></div>`).join('');
}
function pkSetMg(i){pickerMgFilter=_pkGroups[i].name;document.getElementById('pickerSearch').value='';renderPicker();}
function searchPicker(){clearTimeout(pickerSearchTimeout);pickerSearchTimeout=setTimeout(renderPkGrid,120);}
function renderPkGrid(){
  const box=document.getElementById('pickerResults');
  const q=(document.getElementById('pickerSearch').value||'').trim().toLowerCase();
  let items;
  // Este buscador filtra en el navegador, no llama al servidor: si aquí no se
  // miran los otros nombres, el sinónimo funciona en la página de Ejercicios y
  // no al montar una rutina, que es donde más se busca.
  if(q){ items=(_pkTrainings||[]).filter(t=>`${t.name||''} ${t.aliases||''}`.toLowerCase().includes(q)); renderPkMgs(); }
  else { items=(_pkTrainings||[]).filter(t=>(t.muscle_group_name||'Otros')===pickerMgFilter); }
  _pkView=items;
  if(!items.length){box.innerHTML='<div class="picker-empty">No se encontraron ejercicios.</div>';return;}
  box.innerHTML=items.map((ex,i)=>
    `<div class="pk-card" onclick="pkPick(${i})"><div class="pk-ico">${ex.image?`<img src="${esc(ex.image)}" alt="">`:PK_ICO}</div><div><div class="pk-name">${esc(ex.name)}</div><div class="pk-mg-name">${esc(ex.muscle_group_name||'—')}</div></div></div>`).join('');
}
function pkPick(i){const ex=_pkView[i];if(ex)selectExercise(ex.id,ex.name,ex.muscle_group_name||'',ex.image||null,ex);}

/* Las series recomendadas del ejercicio, traducidas a lo que espera cada
   casilla de la rutina.

   Se guardan como texto libre ("3-4", "8-12", "60-90s") porque son una
   recomendación, y la rutina quiere números en series y descanso. Se coge el
   primero: de "3-4 series" salen 3, y las repeticiones se copian tal cual
   porque "8-12" es exactamente lo que el coach escribiría a mano. */
function _primerNumero(v){
  const m=String(v==null?'':v).match(/\d+/);
  return m?parseInt(m[0],10):null;
}
function recomendacionDe(t){
  return {
    series:_primerNumero(t&&t.rec_series),
    repetitions:String((t&&t.rec_reps)||'').trim(),
    break_time:_primerNumero(t&&t.rec_rest),
  };
}

function selectExercise(trainingId,name,muscleName,image,training){
  if(pickerTargetBlockIdx===null)return;
  const day=routineData.days_list[selectedDayIdx];const blk=day.blocks[pickerTargetBlockIdx];
  const rec=recomendacionDe(training);
  if(pickerReplaceEi!==null){
    const ex=blk.exercises[pickerReplaceEi];
    ex.training_id=trainingId;ex.training_name=name;ex.muscle_group_name=muscleName;ex.image=image||null;
    // Al CAMBIAR el ejercicio solo se rellena lo que esté vacío: si el coach ya
    // había escrito sus series, son suyas y no las pisa una recomendación.
    if(ex.series==null||ex.series==='')ex.series=rec.series;
    if(!ex.repetitions)ex.repetitions=rec.repetitions;
    if(ex.break_time==null||ex.break_time==='')ex.break_time=rec.break_time;
    pickerReplaceEi=null;
  }else{
    blk.exercises.push({training_id:trainingId,training_name:name,muscle_group_name:muscleName,image:image||null,series:rec.series,repetitions:rec.repetitions,break_time:rec.break_time,intensity_type:'',intensity_value:null,notes:'',order_index:blk.exercises.length});
  }
  closePicker();renderBlocks();
}

async function loadMuscleGroupsForFilters(){
  // Precarga silenciosa del catálogo para que el picker abra al instante.
  if(_pkTrainings)return;
  try{
    const r=await fetch(`${API}/trainings/search?per_page=1000`,{headers:_rbHeaders()});
    const d=await r.json();
    _pkTrainings=(d.data&&d.data.data)||d.data||[];
    buildPkGroups();
  }catch{}
}

// ── Assign modal ──────────────────────────────────────────────────────────────
