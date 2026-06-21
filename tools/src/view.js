'use strict';
// Presentation: canvas drawing, visibility, DOM panel rendering, and UI helpers
// (toast/dialog/panel resize). References geometry, grid, and model functions at
// call time and shared state from state.js.

function el(id){return document.getElementById(id)}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function uid(p='id'){return p+'_'+Date.now()+'_'+Math.random().toString(36).slice(2)}
function uiClamp(value,min,max){return Math.max(min,Math.min(max,value))}
function maxLeftPanelWidth(){return Math.max(260,Math.min(560,window.innerWidth-260))}
function appToast(message,type='info'){
  const stack=el('toastStack');
  const item=document.createElement('div');
  item.className='toast'+(type==='error'?' error':type==='ok'?' ok':'');
  item.textContent=message;
  stack.appendChild(item);
  requestAnimationFrame(()=>item.classList.add('show'));
  setTimeout(()=>{item.classList.remove('show'); setTimeout(()=>item.remove(),200);},2600);
}
function appDialog({title,message='',value='',input=false,okText='OK',danger=false}){
  return new Promise(resolve=>{
    const backdrop=el('dialogBackdrop'), inputEl=el('dialogInput'), ok=el('dialogOk'), cancel=el('dialogCancel');
    el('dialogTitle').textContent=title;
    el('dialogMessage').textContent=message;
    inputEl.value=value;
    inputEl.style.display=input?'block':'none';
    ok.textContent=okText;
    ok.className=danger?'danger':'primary';
    backdrop.classList.add('open');
    const finish=result=>{
      backdrop.classList.remove('open');
      ok.onclick=null; cancel.onclick=null; backdrop.onclick=null; inputEl.onkeydown=null;
      resolve(result);
    };
    ok.onclick=()=>finish(input?inputEl.value:true);
    cancel.onclick=()=>finish(input?null:false);
    backdrop.onclick=e=>{if(e.target===backdrop)finish(input?null:false);};
    inputEl.onkeydown=e=>{if(e.key==='Enter')finish(inputEl.value); if(e.key==='Escape')finish(null);};
    if(input)inputEl.focus(); else ok.focus();
  });
}
function appConfirm(message,title='Confirm',okText='OK',danger=false){return appDialog({title,message,okText,danger});}
function appPrompt(title,value=''){return appDialog({title,value,input:true,okText:'Save'});}
function loadUiState(){
  try{
    const saved=JSON.parse(localStorage.getItem(UI_STORAGE_KEY)||'{}');
    return {leftWidth:Number(saved.leftWidth)||300,rightOpen:saved.rightOpen!==false};
  }catch(e){
    return {leftWidth:300,rightOpen:true};
  }
}
function saveUiState(){
  try{localStorage.setItem(UI_STORAGE_KEY,JSON.stringify(uiState));}catch(e){}
}
function applyUiState(){
  if(isGridProfile()&&uiState.leftWidth<380)uiState.leftWidth=380;
  uiState.leftWidth=uiClamp(uiState.leftWidth,220,maxLeftPanelWidth());
  document.documentElement.style.setProperty('--left-panel-width',uiState.leftWidth+'px');
  document.body.classList.toggle('rightDrawerOpen',uiState.rightOpen);
  const toggle=el('toggleRightPanel'), drawer=el('rightPanel');
  if(toggle){
    const label=uiState.rightOpen?'Hide tools':'Show tools';
    toggle.querySelector('span').textContent=uiState.rightOpen?'>':'<';
    toggle.title=label;
    toggle.setAttribute('aria-label',label);
    toggle.classList.toggle('activeBtn',uiState.rightOpen);
    toggle.setAttribute('aria-expanded',String(uiState.rightOpen));
  }
  if(drawer)drawer.setAttribute('aria-hidden',String(!uiState.rightOpen));
  const handle=el('leftResizeHandle');
  if(handle){
    handle.setAttribute('aria-valuemax',String(maxLeftPanelWidth()));
    handle.setAttribute('aria-valuenow',String(Math.round(uiState.leftWidth)));
  }
  requestAnimationFrame(resize);
}
function setRightDrawer(open){
  uiState.rightOpen=!!open;
  applyUiState();
  saveUiState();
}
function initPanelControls(){
  const leftPanel=el('leftPanel'), handle=el('leftResizeHandle'), toggle=el('toggleRightPanel'), close=el('closeRightPanel');
  if(toggle)toggle.onclick=()=>setRightDrawer(!uiState.rightOpen);
  if(close)close.onclick=()=>setRightDrawer(false);
  window.addEventListener('keydown',e=>{
    const dialog=el('dialogBackdrop');
    if(e.key==='Escape'&&uiState.rightOpen&&!(dialog&&dialog.classList.contains('open')))setRightDrawer(false);
  });
  if(!leftPanel||!handle)return;
  let startX=0,startWidth=0;
  const stopDrag=()=>{
    document.body.classList.remove('resizingLeft');
    window.removeEventListener('pointermove',drag);
    saveUiState();
  };
  const drag=e=>{
    uiState.leftWidth=uiClamp(startWidth+e.clientX-startX,220,maxLeftPanelWidth());
    applyUiState();
  };
  handle.addEventListener('pointerdown',e=>{
    if(window.matchMedia('(max-width: 760px)').matches)return;
    e.preventDefault();
    startX=e.clientX;
    startWidth=leftPanel.getBoundingClientRect().width;
    document.body.classList.add('resizingLeft');
    handle.setPointerCapture(e.pointerId);
    window.addEventListener('pointermove',drag);
    window.addEventListener('pointerup',stopDrag,{once:true});
  });
  handle.addEventListener('keydown',e=>{
    const step=e.shiftKey?48:16;
    if(e.key==='ArrowLeft'||e.key==='ArrowRight'){
      e.preventDefault();
      uiState.leftWidth=uiClamp(uiState.leftWidth+(e.key==='ArrowRight'?step:-step),220,maxLeftPanelWidth());
      applyUiState();
      saveUiState();
    }
    if(e.key==='Home'||e.key==='End'){
      e.preventDefault();
      uiState.leftWidth=e.key==='Home'?220:maxLeftPanelWidth();
      applyUiState();
      saveUiState();
    }
  });
}
function updateProfileHint(){const h=el('profileHint'); if(h)h.textContent=PROFILE_HINTS[currentProfile]||'Profiles keep separate group sets.';}
function updateProfileUi(){const grid=isGridProfile(); const parentSection=el('parentSection'), childSection=el('childSection'), manualSection=el('manualSection'), groupsTitle=el('groupsTitle'), view=el('viewMode'), unwrap=el('unwrapStrength'); if(parentSection)parentSection.style.display=grid?'none':''; if(childSection)childSection.style.display=grid?'none':''; if(manualSection)manualSection.style.display=grid?'none':''; if(groupsTitle)groupsTitle.textContent=grid?'Grid':'Groups'; if(grid){viewMode='unwrap'; if(view)view.value='unwrap'; if(unwrap)unwrap.disabled=true; setUnwrapStrength(1,true);} if(view)view.disabled=grid; if(!grid&&unwrap)unwrap.disabled=false; updateViewControls();}
function updateViewControls(){
  const control=document.querySelector('.rangeControl');
  if(control)control.classList.toggle('hidden',viewMode!=='unwrap');
  const symmetry=el('toggleGridSymmetry');
  if(symmetry){
    symmetry.style.display=isGridProfile()?'':'none';
    symmetry.textContent='Symmetry: '+(showGridSymmetry?'ON':'OFF');
    symmetry.classList.toggle('activeBtn',showGridSymmetry);
  }
}
function pointInParent(id,parentId){const s=childIdsOfParent(parentId); return [...childIdsForPoint(id)].some(cid=>s.has(cid));}
function pointVisibility(id){const cids=childIdsForPoint(id), hasAny=cids.size>0; if(filter.mode==='all')return {visible:true, alpha:hasAny?0.96:0.82}; if(filter.mode==='unassigned')return {visible:!hasAny, alpha:hasAny?0.03:1}; if(filter.mode==='showChild')return {visible:true, alpha:cids.has(filter.childId)?1:0.08}; if(filter.mode==='soloChild')return {visible:cids.has(filter.childId), alpha:1}; if(filter.mode==='showParent')return {visible:true, alpha:pointInParent(id,filter.parentId)?1:0.08}; if(filter.mode==='soloParent')return {visible:pointInParent(id,filter.parentId), alpha:1}; return {visible:true,alpha:1};}
function faceVisibility(face){if(filter.mode==='all')return .16; let alphas=face.map(id=>pointVisibility(id)).filter(v=>v.visible).map(v=>v.alpha); if(!alphas.length)return 0; return Math.max(.02, Math.min(.18, Math.max(...alphas)*.16));}
function drawRotoContours(){if(!isRotoProfile())return; ctx.save(); ctx.lineCap='round'; ctx.lineJoin='round'; for(const c of allChildren()){if(c.ids.length<2)continue; const childFilter=filter.mode==='showChild'||filter.mode==='soloChild', parentFilter=filter.mode==='showParent'||filter.mode==='soloParent'; if(childFilter&&filter.childId!==c.id)continue; if(parentFilter&&filter.parentId!==c.parent.id)continue; const first=toScreen(c.ids[0]); ctx.beginPath(); ctx.moveTo(first[0],first[1]); for(const id of c.ids.slice(1)){const p=toScreen(id); ctx.lineTo(p[0],p[1]);} if(!c.openSpline&&c.ids.length>2)ctx.closePath(); ctx.strokeStyle=c.color||'#7cc7ff'; ctx.globalAlpha=(filter.mode==='all'||filter.mode==='showChild'||filter.mode==='showParent')?.82:1; ctx.lineWidth=(c.id===activeChild?3.2:2.1)*devicePixelRatio; ctx.stroke();} ctx.restore();}
// Grid edge colors used for canvas drawing. Mirrors the --c-edge-* CSS vars in
// styles.css; kept as a separate JS constant because the canvas render path cannot
// read CSS custom properties cheaply (getComputedStyle per frame). If you change
// one set, update the other to match.
const GRID_EDGE_COLORS={top:'#ffbf4d',bottom:'#b48cff',left:'#58d68d',right:'#ff7aa2'};
function gridEdgeColumnMap(c){const firstIsLeft=gridLeftEdgeIsFirst(c); return {left:firstIsLeft?0:c.grid.cols-1,right:firstIsLeft?c.grid.cols-1:0};}
function drawGridEdgePath(points,color){ctx.strokeStyle=color; ctx.globalAlpha=1; ctx.lineWidth=4*devicePixelRatio; ctx.beginPath(); points.map(worldToScreen).forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1])); ctx.stroke();}
function drawColoredGridEdges(c){const edgeCols=gridEdgeColumnMap(c); drawGridEdgePath(Array.from({length:c.grid.cols},(_,col)=>gridPoint(c,0,col)),GRID_EDGE_COLORS.top); drawGridEdgePath(Array.from({length:c.grid.cols},(_,col)=>gridPoint(c,c.grid.rows-1,col)),GRID_EDGE_COLORS.bottom); drawGridEdgePath(Array.from({length:c.grid.rows},(_,r)=>gridPoint(c,r,edgeCols.left)),GRID_EDGE_COLORS.left); drawGridEdgePath(Array.from({length:c.grid.rows},(_,r)=>gridPoint(c,r,edgeCols.right)),GRID_EDGE_COLORS.right);}
function drawGridOverlays(){if(!isGridProfile())return; const c=ensureGridProfileRoot(); ctx.save(); ctx.lineCap='round'; ctx.lineJoin='round'; if(showGridSymmetry){ctx.strokeStyle='#ffd079'; ctx.globalAlpha=.9; ctx.lineWidth=2*devicePixelRatio; const axis=GRID_SYMMETRY_AXIS_IDS.map(toScreen); ctx.beginPath(); axis.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1])); ctx.stroke();} const color=c.color||'#7cc7ff', unsetColor='#ff6b6b'; ctx.strokeStyle=color; ctx.fillStyle=color; ctx.globalAlpha=.1; for(let r=0;r<c.grid.rows-1;r++){for(let col=0;col<c.grid.cols-1;col++){const pts=[gridPoint(c,r,col),gridPoint(c,r,col+1),gridPoint(c,r+1,col+1),gridPoint(c,r+1,col)].map(worldToScreen); ctx.beginPath(); pts.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1])); ctx.closePath(); ctx.fill();}} ctx.globalAlpha=.82; ctx.lineWidth=1.6*devicePixelRatio; for(let r=0;r<c.grid.rows;r++){ctx.beginPath(); for(let col=0;col<c.grid.cols;col++){const p=worldToScreen(gridPoint(c,r,col)); col?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]);} ctx.stroke();} for(let col=0;col<c.grid.cols;col++){ctx.beginPath(); for(let r=0;r<c.grid.rows;r++){const p=worldToScreen(gridPoint(c,r,col)); r?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]);} ctx.stroke();} drawColoredGridEdges(c); ctx.globalAlpha=1; ctx.font=`${10*devicePixelRatio}px ui-monospace,monospace`; for(const gp of c.grid.points){const p=worldToScreen(gp), active=gridDrag&&gridDrag.index===gridIndex(c,gp.row,gp.col), unset=gp.id==null; ctx.beginPath(); ctx.fillStyle=unset?unsetColor:color; ctx.arc(p[0],p[1],(active?7:5)*devicePixelRatio,0,Math.PI*2); ctx.fill(); ctx.strokeStyle=active?'#ffd079':(unset?'#6b1717':'#10151f'); ctx.lineWidth=1.5*devicePixelRatio; ctx.stroke(); if(gp.id!=null){ctx.fillStyle='#e8edf5'; ctx.fillText(String(gp.id),p[0]+7*devicePixelRatio,p[1]-7*devicePixelRatio);}} ctx.restore();}
function drawMesh(){if(!showMesh)return; ctx.lineWidth=Math.max(1,devicePixelRatio); for(const f of FACES){const a=faceVisibility(f); if(a<=0)continue; ctx.strokeStyle=`rgba(145,160,185,${a})`; ctx.beginPath(); f.forEach((id,k)=>{const [x,y]=toScreen(id); k?ctx.lineTo(x,y):ctx.moveTo(x,y)}); ctx.closePath(); ctx.stroke();}}
function drawPoints(){for(let i=0;i<MAX_LANDMARKS;i++){const vis=pointVisibility(i); if(!vis.visible)continue; const cid=primaryChildIdForPoint(i), [x,y]=toScreen(i), found=cid?findChild(cid):null; ctx.globalAlpha=vis.alpha; ctx.beginPath(); ctx.fillStyle=cid?(found?.child.color||'#a7afbd'):'#e8edf5'; ctx.arc(x,y,(cid?4.8:(IRIS_IDS.has(i)?4.2:3.3))*devicePixelRatio,0,Math.PI*2); ctx.fill(); ctx.globalAlpha=1; if(i===hovered||i===selected){ctx.strokeStyle=i===selected?'#e8edf5':'#ffd079';ctx.lineWidth=2*devicePixelRatio;ctx.beginPath();ctx.arc(x,y,9*devicePixelRatio,0,Math.PI*2);ctx.stroke();} if(showLabels||i===hovered||i===selected){const labelScale=labelZoomScale(), labelPad=6*labelScale*devicePixelRatio; ctx.fillStyle='#e8edf5';ctx.font=`${10*labelScale*devicePixelRatio}px ui-monospace,monospace`;ctx.fillText(String(i),x+labelPad,y-labelPad);}}}
function draw(){ctx.clearRect(0,0,canvas.width,canvas.height); if(!canvas.width)return; drawMesh(); drawRotoContours(); drawGridOverlays(); drawPoints();}
function stats(){el('assignedCount').textContent=assigned.size; el('freeCount').textContent=MAX_LANDMARKS-assigned.size;}
function renderParentSelect(){const s=el('parentSelect'); const val=s.value; s.innerHTML=''; for(const p of parents){const o=document.createElement('option'); o.value=p.id; o.textContent=p.name; s.appendChild(o);} if(parents.some(p=>p.id===val))s.value=val;}
function setFilter(mode,parentId=null,childId=null){filter={mode,parentId,childId}; renderGroups(); draw();}
function gridEdgeButtons(side,placement,edgeClass,vertical,addDisabled,removeDisabled,addTitle,removeTitle){return `<div class="gridEdgeControls ${placement} ${edgeClass}${vertical?' vertical':''}"><button class="gridAddButton ${edgeClass}" data-grid-add="${side}" title="${addTitle}"${addDisabled?' disabled':''}>+</button><button class="gridAddButton ${edgeClass}" data-grid-remove="${side}" title="${removeTitle}"${removeDisabled?' disabled':''}>-</button></div>`;}
function formatGridPreview(c){ensureGridChild(c); const axis=gridMiniAxisPercent(c).toFixed(2), firstIsLeft=gridLeftEdgeIsFirst(c), visualLeft=firstIsLeft?'gridEdgeLeft':'gridEdgeRight', visualRight=firstIsLeft?'gridEdgeRight':'gridEdgeLeft', cells=c.grid.points.map(p=>`<div class="gridMiniCell ${p.id==null?'':'snapped'}" title="r${p.row+1} c${p.col+1}${p.id==null?'':' landmark '+p.id}">${p.id==null?'':p.id}</div>`).join(''), topControls=gridEdgeButtons('top','gridAddTop','gridEdgeTop',false,c.grid.rows>=GRID_LIMITS.rows.max,c.grid.rows<=GRID_LIMITS.rows.min,'Add row above','Remove top row'), bottomControls=gridEdgeButtons('bottom','gridAddBottom','gridEdgeBottom',false,c.grid.rows>=GRID_LIMITS.rows.max,c.grid.rows<=GRID_LIMITS.rows.min,'Add row below','Remove bottom row'), leftControls=gridEdgeButtons('left','gridAddLeft','gridEdgeLeft',true,c.grid.cols>=GRID_LIMITS.cols.max,c.grid.cols<=GRID_LIMITS.cols.min,'Add column on FaceMesh left side','Remove FaceMesh left column'), rightControls=gridEdgeButtons('right','gridAddRight','gridEdgeRight',true,c.grid.cols>=GRID_LIMITS.cols.max,c.grid.cols<=GRID_LIMITS.cols.min,'Add column on FaceMesh right side','Remove FaceMesh right column'); return `<div class="gridExpandWrap">${topControls}${leftControls}<div class="gridMini" style="grid-template-columns:repeat(${c.grid.cols},minmax(16px,1fr))"><span class="gridMiniEdge gridMiniEdgeTop"></span><span class="gridMiniEdge gridMiniEdgeBottom"></span><span class="gridMiniEdge gridMiniEdgeLeft ${visualLeft}"></span><span class="gridMiniEdge gridMiniEdgeRight ${visualRight}"></span><span class="gridMiniAxis" style="left:${axis}%"></span>${cells}</div>${rightControls}${bottomControls}</div><div class="gridLegend"><span class="gridLegendItem gridEdgeTop"><span class="gridLegendSwatch"></span>top</span><span class="gridLegendItem gridEdgeBottom"><span class="gridLegendSwatch"></span>bottom</span><span class="gridLegendItem gridEdgeLeft"><span class="gridLegendSwatch"></span>face left</span><span class="gridLegendItem gridEdgeRight"><span class="gridLegendSwatch"></span>face right</span><span>${c.grid.rows} x ${c.grid.cols}</span></div>`;}
function formatChildIds(c){if(!c.ids.length)return 'none'; if(isGridProfile())return `${c.ids.length} points`; return isRotoProfile()?c.ids.map((id,i)=>`${i+1}:${id}`).join(' -> '):c.ids.join(', ');}
function renderSingleGrid(){const box=el('groups'), c=ensureGridProfileRoot(), grid=gridStats(c); box.innerHTML=`<div class="gridPanel"><div class="childTitle"><span class="dot" style="background:${c.color}"></span><div class="childName">Grid overlay</div><span class="badge">${grid.snapped}/${grid.total} snapped</span></div><div class="small" style="margin-top:8px">Set a starting size or expand from the mini grid. Drag canvas handles onto landmarks; Symmetry mirrors across the FaceMesh axis. Grid mode is locked to Unwrap.</div><div class="row gridControls"><label class="inlineCheck">Columns<input id="gridCols" type="number" min="2" max="33" step="1" value="${grid.cols}"></label><label class="inlineCheck">Rows<input id="gridRowsInput" type="number" min="2" max="32" value="${grid.rows}"></label></div><div class="actions" style="opacity:1"><button class="primary" data-a="createGrid">Create grid</button><button data-a="clearSnaps">Clear snaps</button><button class="danger" data-a="resetGrid">Reset overlay</button></div><div class="gridMeta"><span class="badge">${grid.cols} cols</span><span class="badge">${grid.rows} rows</span><span class="badge">${grid.quads} complete quads</span></div>${formatGridPreview(c)}</div>`; box.querySelector('[data-a="createGrid"]').onclick=()=>setGridSize(c,box.querySelector('#gridCols').value,box.querySelector('#gridRowsInput').value); box.querySelector('[data-a="clearSnaps"]').onclick=()=>{for(const p of c.grid.points)p.id=null; syncGridAssigned(c); refresh();}; box.querySelector('[data-a="resetGrid"]').onclick=()=>setGridSize(c,c.grid.cols,c.grid.rows); for(const btn of box.querySelectorAll('[data-grid-add]'))btn.onclick=()=>addGridEdge(c,btn.dataset.gridAdd); for(const btn of box.querySelectorAll('[data-grid-remove]'))btn.onclick=()=>removeGridEdge(c,btn.dataset.gridRemove);}
function renderGroups(){
  renderParentSelect();
  const box=el('groups'); box.innerHTML='';
  if(isGridProfile()){renderSingleGrid(); return;}
  if(!parents.length){box.innerHTML=isRotoProfile()?'<div class="small">No roto contours. Create a parent such as eyes, lips, or face, then add a child such as left_eye_outer. Click landmarks in outline order.</div>':'<div class="small">No parent groups. Create one, for example nose, then add a child such as left_nostril.</div>';return}
  for(const p of parents) renderParent(p, box);
}
function renderParent(p, box){
  const total=p.children.reduce((s,c)=>s+c.ids.length,0), collapsed=!!p.collapsed;
  const div=document.createElement('div'); div.className='parent'+(collapsed?' collapsed':'');
  div.innerHTML=`<div class="parentHead"><button class="toggleParent" data-pa="toggle" title="${collapsed?'Expand':'Collapse'} parent">${collapsed?'+':'-'}</button><div class="parentName">${esc(p.name)}</div><span class="badge">${p.children.length} child</span><span class="badge">${total}</span></div>${collapsed?'':`<div class="childWrap"><div class="parentActions"><button data-pa="add">+ child</button><button data-pa="show" class="${filter.mode==='showParent'&&filter.parentId===p.id?'activeBtn':''}">Show</button><button data-pa="solo" class="${filter.mode==='soloParent'&&filter.parentId===p.id?'activeBtn':''}">Solo</button><button data-pa="rename">Rename</button><button data-pa="delete">Delete parent</button></div><div data-children></div></div>`}`;
  div.querySelector('[data-pa="toggle"]').onclick=()=>{p.collapsed=!p.collapsed;renderGroups();};
  if(collapsed){box.appendChild(div); return;}
  div.querySelector('[data-pa="add"]').onclick=()=>{el('parentSelect').value=p.id; el('childName').focus();};
  div.querySelector('[data-pa="show"]').onclick=()=>setFilter('showParent',p.id,null);
  div.querySelector('[data-pa="solo"]').onclick=()=>setFilter('soloParent',p.id,null);
  div.querySelector('[data-pa="rename"]').onclick=async()=>{const n=await appPrompt('Rename parent',p.name); if(n&&n.trim()){p.name=n.trim();renderGroups();exportJson();appToast('Parent renamed.','ok');}};
  div.querySelector('[data-pa="delete"]').onclick=async()=>{if(await appConfirm('Delete this parent and all child groups? Shared points remain in other groups.','Delete parent','Delete',true)){for(const c of p.children){for(const id of c.ids)removePointFromChild(id,c.id); if(activeChild===c.id)activeChild=null;} parents=parents.filter(x=>x.id!==p.id); if(!activeChild)activeChild=allChildren()[0]?.id||null; refresh();appToast('Parent deleted.','ok');}};
  const cb=div.querySelector('[data-children]');
  if(!p.children.length){cb.innerHTML='<div class="small" style="margin-top:8px">No child groups.</div>';} else for(const c of p.children) renderChild(c, p, cb);
  box.appendChild(div);
}
function renderChild(c, p, cb){
  const cd=document.createElement('div'); cd.className='child'+(c.id===activeChild?' active':''); const openChecked=c.openSpline?' checked':'';
  const rotoActions=isRotoProfile()?`<label class="inlineCheck" title="Do not close this contour in Roto export"><input data-a="openSpline" type="checkbox"${openChecked}> Open spline</label><button data-a="movePrev">Move selected -</button><button data-a="moveNext">Move selected +</button><button data-a="reverse">Reverse</button>`:'';
  cd.innerHTML=`<div class="childTitle"><span class="dot" style="background:${c.color}"></span><div class="childName">${esc(c.name)}</div><span class="badge">${c.ids.length}</span></div><div class="ids">${formatChildIds(c)}</div><div class="actions"><button data-a="active">Set active</button><button data-a="show" class="${filter.mode==='showChild'&&filter.childId===c.id?'activeBtn':''}">Show</button><button data-a="solo" class="${filter.mode==='soloChild'&&filter.childId===c.id?'activeBtn':''}">Solo</button>${rotoActions}<button data-a="rename">Rename</button><button data-a="clear">Clear</button><button data-a="delete">Delete</button></div>`;
  cd.querySelector('[data-a="active"]').onclick=()=>{activeChild=c.id;renderGroups();draw();};
  cd.querySelector('[data-a="show"]').onclick=()=>setFilter('showChild',null,c.id);
  cd.querySelector('[data-a="solo"]').onclick=()=>setFilter('soloChild',null,c.id);
  const openSpline=cd.querySelector('[data-a="openSpline"]'), movePrev=cd.querySelector('[data-a="movePrev"]'), moveNext=cd.querySelector('[data-a="moveNext"]'), reverse=cd.querySelector('[data-a="reverse"]');
  if(openSpline)openSpline.onchange=e=>{c.openSpline=!!e.target.checked; draw();exportJson();};
  if(movePrev)movePrev.onclick=()=>moveSelectedInChild(c,-1);
  if(moveNext)moveNext.onclick=()=>moveSelectedInChild(c,1);
  if(reverse)reverse.onclick=()=>{c.ids.reverse(); renderGroups();draw();exportJson();appToast('Contour order reversed.','ok');};
  cd.querySelector('[data-a="rename"]').onclick=async()=>{const n=await appPrompt('Rename child',c.name); if(n&&n.trim()){c.name=n.trim();renderGroups();exportJson();appToast('Child renamed.','ok');}};
  cd.querySelector('[data-a="clear"]').onclick=()=>{for(const id of [...c.ids])removePointFromChild(id,c.id); c.ids=[]; refresh();};
  cd.querySelector('[data-a="delete"]').onclick=async()=>{if(await appConfirm('Delete this child group? Shared points remain in other groups.','Delete child','Delete',true)){for(const id of c.ids)removePointFromChild(id,c.id); p.children=p.children.filter(x=>x.id!==c.id); if(activeChild===c.id)activeChild=allChildren()[0]?.id||null; refresh();appToast('Child deleted.','ok');}};
  cb.appendChild(cd);
}