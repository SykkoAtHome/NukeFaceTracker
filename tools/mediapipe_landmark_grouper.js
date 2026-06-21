'use strict';
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
const canvas=document.getElementById('canvas'), ctx=canvas.getContext('2d');
function el(id){return document.getElementById(id)}
function uiClamp(value,min,max){return Math.max(min,Math.min(max,value))}
function maxLeftPanelWidth(){return Math.max(260,Math.min(560,window.innerWidth-260))}
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
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function uid(p='id'){return p+'_'+Date.now()+'_'+Math.random().toString(36).slice(2)}
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
function isRotoProfile(name=currentProfile){return name==='roto'}
function isGridProfile(name=currentProfile){return name==='grid'}
function updateProfileHint(){const h=el('profileHint'); if(h)h.textContent=PROFILE_HINTS[currentProfile]||'Profiles keep separate group sets.';}
function updateProfileUi(){const grid=isGridProfile(); const parentSection=el('parentSection'), childSection=el('childSection'), manualSection=el('manualSection'), groupsTitle=el('groupsTitle'), view=el('viewMode'), unwrap=el('unwrapStrength'); if(parentSection)parentSection.style.display=grid?'none':''; if(childSection)childSection.style.display=grid?'none':''; if(manualSection)manualSection.style.display=grid?'none':''; if(groupsTitle)groupsTitle.textContent=grid?'Grid':'Groups'; if(grid){viewMode='unwrap'; if(view)view.value='unwrap'; if(unwrap)unwrap.disabled=true; setUnwrapStrength(1,true);} if(view)view.disabled=grid; if(!grid&&unwrap)unwrap.disabled=false; updateViewControls();}
function ensureGridProfileRoot(){if(!isGridProfile())return null; let p=parents[0]; if(!p){p={id:uid('p'),name:'grid',children:[],collapsed:false}; parents=[p]; profiles.grid.parents=parents;} let c=p.children[0]; if(!c){c=makeChild('grid',COLORS[0]); p.children=[c];} ensureGridChild(c); syncGridAssigned(c); activeChild=c.id; profiles.grid.activeChild=activeChild; return c;}
function saveProfileState(){profiles[currentProfile].parents=parents; profiles[currentProfile].assigned=assigned; profiles[currentProfile].activeChild=activeChild}
function useProfile(name){saveProfileState(); currentProfile=PROFILE_NAMES.includes(name)?name:'full'; const state=profiles[currentProfile]; parents=state.parents; assigned=state.assigned; activeChild=state.activeChild; filter={mode:'all',parentId:null,childId:null}; selected=null; hovered=null; updateProfileHint(); updateProfileUi(); ensureGridProfileRoot(); renderGroups();stats();draw();exportJson();}
function resetCurrentProfile(){parents=[]; assigned=new Map(); activeChild=null; profiles[currentProfile]= {parents,assigned,activeChild}; selected=null; filter={mode:'all',parentId:null,childId:null}; ensureGridProfileRoot();}
function resetAllProfiles(){for(const name of PROFILE_NAMES)profiles[name]=emptyProfile(); currentProfile='full'; parents=profiles.full.parents; assigned=profiles.full.assigned; activeChild=null; selected=null; filter={mode:'all',parentId:null,childId:null}; const ps=el('profileSelect'); if(ps)ps.value=currentProfile; updateProfileHint(); updateProfileUi();}
function allChildren(){return parents.flatMap(p=>p.children.map(c=>({...c,parent:p})))}
function findChild(id){for(const p of parents){const c=p.children.find(x=>x.id===id); if(c)return {parent:p,child:c};} return null}
function childIdsOfParent(pid){const p=parents.find(x=>x.id===pid); return new Set((p?.children||[]).map(c=>c.id))}
function childIdsForPoint(id){return assigned.get(id)||new Set()}
function pointHasChild(id,cid){return childIdsForPoint(id).has(cid)}
function primaryChildIdForPoint(id){const ids=[...childIdsForPoint(id)]; return ids.includes(activeChild)?activeChild:(ids[0]||null)}
function ensureGridChild(c){if(!c.grid||!Array.isArray(c.grid.points))createGrid(c,Number(c.grid?.cols)||3,Number(c.grid?.rows)||2); return c;}
function gridIndex(c,row,col){return row*c.grid.cols+col;}
function gridPoint(c,row,col){return c.grid.points[gridIndex(c,row,col)];}
function gridIdsMatrix(c){ensureGridChild(c); const out=[]; for(let r=0;r<c.grid.rows;r++){const row=[]; for(let col=0;col<c.grid.cols;col++)row.push(gridPoint(c,r,col).id??null); out.push(row);} return out;}
function gridCompleteQuads(c){ensureGridChild(c); const quads=[]; for(let r=0;r<c.grid.rows-1;r++){for(let col=0;col<c.grid.cols-1;col++){const ids=[gridPoint(c,r,col).id,gridPoint(c,r,col+1).id,gridPoint(c,r+1,col+1).id,gridPoint(c,r+1,col).id]; if(ids.every(id=>id!=null))quads.push(ids);}} return quads;}
function gridStats(c){ensureGridChild(c); const snapped=c.grid.points.filter(p=>p.id!=null).length; return {cols:c.grid.cols,rows:c.grid.rows,total:c.grid.points.length,snapped,quads:gridCompleteQuads(c).length};}
function syncGridAssigned(c){assigned=new Map(); c.ids=[]; if(!c)return; for(const p of c.grid.points){if(p.id==null)continue; c.ids.push(p.id); if(!assigned.has(p.id))assigned.set(p.id,new Set()); assigned.get(p.id).add(c.id);} profiles.grid.assigned=assigned;}
function normalizeGridCols(cols){return Math.max(2,Math.min(33,Math.round(Number(cols)||3)));}
function normalizeGridRows(rows){return Math.max(2,Math.min(32,Math.round(Number(rows)||2)));}
function createGrid(c,cols=3,rows=2){cols=normalizeGridCols(cols); rows=normalizeGridRows(rows); const b=UNWRAP_BOUNDS, padX=(b.maxX-b.minX)*.12, padY=(b.maxY-b.minY)*.1, minX=b.minX+padX, maxX=b.maxX-padX, minY=b.minY+padY, maxY=b.maxY-padY, points=[]; for(let r=0;r<rows;r++){for(let col=0;col<cols;col++){const x=minX+(maxX-minX)*col/(cols-1), y=minY+(maxY-minY)*r/(rows-1); points.push({row:r,col,x,y,id:null});}} c.grid={cols,rows,points}; c.ids=[]; syncGridAssigned(c); return c;}
function setGridSize(c,cols,rows){createGrid(c,cols,rows); renderGroups();stats();draw();exportJson();}
function cloneGridPoint(p,row,col){return {row,col,x:p.x,y:p.y,id:p.id??null};}
function avgColumnX(c,col){let sum=0; for(let r=0;r<c.grid.rows;r++)sum+=gridPoint(c,r,col).x; return sum/c.grid.rows;}
function gridHorizontalCenterX(c){let sum=0; for(const p of c.grid.points)sum+=p.x; return sum/c.grid.points.length;}
function gridSymmetryCenterX(){return GRID_SYMMETRY_AXIS_IDS.reduce((sum,id)=>sum+UNWRAP_LAYOUT[id][0],0)/GRID_SYMMETRY_AXIS_IDS.length;}
function gridLeftEdgeIsFirst(c){const first=avgColumnX(c,0), last=avgColumnX(c,c.grid.cols-1); if(Math.abs(first-last)>.000001)return first<last; return first<=Math.min(gridHorizontalCenterX(c),gridSymmetryCenterX());}
function gridMiniAxisPercent(c){const first=avgColumnX(c,0), last=avgColumnX(c,c.grid.cols-1), min=Math.min(first,last), max=Math.max(first,last), span=max-min; if(span<=.000001)return 50; return Math.max(0,Math.min(100,(gridSymmetryCenterX()-min)/span*100));}
function normalizeGridPointIndexes(c){for(let r=0;r<c.grid.rows;r++){for(let col=0;col<c.grid.cols;col++){const p=gridPoint(c,r,col); p.row=r; p.col=col;}}}
function extrapolateBefore(a,b,row,col){return {row,col,x:a.x-(b.x-a.x),y:a.y-(b.y-a.y),id:null};}
function extrapolateAfter(a,b,row,col){return {row,col,x:b.x+(b.x-a.x),y:b.y+(b.y-a.y),id:null};}
function addGridEdge(c,side){ensureGridChild(c); const cols=c.grid.cols, rows=c.grid.rows; if((side==='left'||side==='right')&&cols>=33)return; if((side==='top'||side==='bottom')&&rows>=32)return; const points=[]; if(side==='top'){for(let col=0;col<cols;col++){points.push(extrapolateBefore(gridPoint(c,0,col),gridPoint(c,1,col),0,col));} for(let r=0;r<rows;r++){for(let col=0;col<cols;col++)points.push(cloneGridPoint(gridPoint(c,r,col),r+1,col));} c.grid.rows=rows+1; c.grid.points=points;} else if(side==='bottom'){for(let r=0;r<rows;r++){for(let col=0;col<cols;col++)points.push(cloneGridPoint(gridPoint(c,r,col),r,col));} for(let col=0;col<cols;col++){points.push(extrapolateAfter(gridPoint(c,rows-2,col),gridPoint(c,rows-1,col),rows,col));} c.grid.rows=rows+1; c.grid.points=points;} else {const addAtStart=side==='left'?gridLeftEdgeIsFirst(c):!gridLeftEdgeIsFirst(c); for(let r=0;r<rows;r++){if(addAtStart)points.push(extrapolateBefore(gridPoint(c,r,0),gridPoint(c,r,1),r,0)); for(let col=0;col<cols;col++)points.push(cloneGridPoint(gridPoint(c,r,col),r,col+(addAtStart?1:0))); if(!addAtStart)points.push(extrapolateAfter(gridPoint(c,r,cols-2),gridPoint(c,r,cols-1),r,cols));} c.grid.cols=cols+1; c.grid.points=points;} normalizeGridPointIndexes(c); syncGridAssigned(c); renderGroups();stats();draw();exportJson();}
function removeGridEdge(c,side){ensureGridChild(c); const cols=c.grid.cols, rows=c.grid.rows; if((side==='left'||side==='right')&&cols<=2)return; if((side==='top'||side==='bottom')&&rows<=2)return; const points=[]; if(side==='top'){for(let r=1;r<rows;r++){for(let col=0;col<cols;col++)points.push(cloneGridPoint(gridPoint(c,r,col),r-1,col));} c.grid.rows=rows-1; c.grid.points=points;} else if(side==='bottom'){for(let r=0;r<rows-1;r++){for(let col=0;col<cols;col++)points.push(cloneGridPoint(gridPoint(c,r,col),r,col));} c.grid.rows=rows-1; c.grid.points=points;} else {const removeAtStart=side==='left'?gridLeftEdgeIsFirst(c):!gridLeftEdgeIsFirst(c), removeCol=removeAtStart?0:cols-1; for(let r=0;r<rows;r++){for(let col=0;col<cols;col++){if(col===removeCol)continue; points.push(cloneGridPoint(gridPoint(c,r,col),r,col-(col>removeCol?1:0)));}} c.grid.cols=cols-1; c.grid.points=points;} normalizeGridPointIndexes(c); syncGridAssigned(c); renderGroups();stats();draw();exportJson();}
function removePointFromChild(id,cid){const found=findChild(cid); if(found){found.child.ids=found.child.ids.filter(x=>x!==id); if(isGridProfile()&&found.child.grid){for(const p of found.child.grid.points){if(p.id===id)p.id=null;}}} const ids=assigned.get(id); if(ids){ids.delete(cid); if(!ids.size)assigned.delete(id);}}
function resize(){const r=canvas.getBoundingClientRect(); canvas.width=Math.max(1,Math.floor(r.width*devicePixelRatio)); canvas.height=Math.max(1,Math.floor(r.height*devicePixelRatio)); draw();}
window.addEventListener('resize',()=>{applyUiState();});
function pointVisibility(id){const cids=childIdsForPoint(id), hasAny=cids.size>0; if(filter.mode==='all')return {visible:true, alpha:hasAny?0.96:0.82}; if(filter.mode==='unassigned')return {visible:!hasAny, alpha:hasAny?0.03:1}; if(filter.mode==='showChild')return {visible:true, alpha:cids.has(filter.childId)?1:0.08}; if(filter.mode==='soloChild')return {visible:cids.has(filter.childId), alpha:1}; if(filter.mode==='showParent'){const s=childIdsOfParent(filter.parentId), inParent=[...cids].some(cid=>s.has(cid)); return {visible:true, alpha:inParent?1:0.08};} if(filter.mode==='soloParent'){const s=childIdsOfParent(filter.parentId), inParent=[...cids].some(cid=>s.has(cid)); return {visible:inParent, alpha:1};} return {visible:true,alpha:1};}
function faceVisibility(face){if(filter.mode==='all')return .16; let alphas=face.map(id=>pointVisibility(id)).filter(v=>v.visible).map(v=>v.alpha); if(!alphas.length)return 0; return Math.max(.02, Math.min(.18, Math.max(...alphas)*.16));}
function drawRotoContours(){if(!isRotoProfile())return; ctx.save(); ctx.lineCap='round'; ctx.lineJoin='round'; for(const c of allChildren()){if(c.ids.length<2)continue; const childFilter=filter.mode==='showChild'||filter.mode==='soloChild', parentFilter=filter.mode==='showParent'||filter.mode==='soloParent'; if(childFilter&&filter.childId!==c.id)continue; if(parentFilter&&filter.parentId!==c.parent.id)continue; const first=toScreen(c.ids[0]); ctx.beginPath(); ctx.moveTo(first[0],first[1]); for(const id of c.ids.slice(1)){const p=toScreen(id); ctx.lineTo(p[0],p[1]);} if(!c.openSpline&&c.ids.length>2)ctx.closePath(); ctx.strokeStyle=c.color||'#7cc7ff'; ctx.globalAlpha=(filter.mode==='all'||filter.mode==='showChild'||filter.mode==='showParent')?.82:1; ctx.lineWidth=(c.id===activeChild?3.2:2.1)*devicePixelRatio; ctx.stroke();} ctx.restore();}
function gridEdgeColumnMap(c){const firstIsLeft=gridLeftEdgeIsFirst(c); return {left:firstIsLeft?0:c.grid.cols-1,right:firstIsLeft?c.grid.cols-1:0};}
function drawGridEdgePath(points,color){ctx.strokeStyle=color; ctx.globalAlpha=1; ctx.lineWidth=4*devicePixelRatio; ctx.beginPath(); points.map(worldToScreen).forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1])); ctx.stroke();}
function drawColoredGridEdges(c){const edgeCols=gridEdgeColumnMap(c); drawGridEdgePath(Array.from({length:c.grid.cols},(_,col)=>gridPoint(c,0,col)),GRID_EDGE_COLORS.top); drawGridEdgePath(Array.from({length:c.grid.cols},(_,col)=>gridPoint(c,c.grid.rows-1,col)),GRID_EDGE_COLORS.bottom); drawGridEdgePath(Array.from({length:c.grid.rows},(_,r)=>gridPoint(c,r,edgeCols.left)),GRID_EDGE_COLORS.left); drawGridEdgePath(Array.from({length:c.grid.rows},(_,r)=>gridPoint(c,r,edgeCols.right)),GRID_EDGE_COLORS.right);}
function drawGridOverlays(){if(!isGridProfile())return; const c=ensureGridProfileRoot(); ctx.save(); ctx.lineCap='round'; ctx.lineJoin='round'; if(showGridSymmetry){ctx.strokeStyle='#ffd079'; ctx.globalAlpha=.9; ctx.lineWidth=2*devicePixelRatio; const axis=GRID_SYMMETRY_AXIS_IDS.map(toScreen); ctx.beginPath(); axis.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1])); ctx.stroke();} const color=c.color||'#7cc7ff', unsetColor='#ff6b6b'; ctx.strokeStyle=color; ctx.fillStyle=color; ctx.globalAlpha=.1; for(let r=0;r<c.grid.rows-1;r++){for(let col=0;col<c.grid.cols-1;col++){const pts=[gridPoint(c,r,col),gridPoint(c,r,col+1),gridPoint(c,r+1,col+1),gridPoint(c,r+1,col)].map(worldToScreen); ctx.beginPath(); pts.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1])); ctx.closePath(); ctx.fill();}} ctx.globalAlpha=.82; ctx.lineWidth=1.6*devicePixelRatio; for(let r=0;r<c.grid.rows;r++){ctx.beginPath(); for(let col=0;col<c.grid.cols;col++){const p=worldToScreen(gridPoint(c,r,col)); col?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]);} ctx.stroke();} for(let col=0;col<c.grid.cols;col++){ctx.beginPath(); for(let r=0;r<c.grid.rows;r++){const p=worldToScreen(gridPoint(c,r,col)); r?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]);} ctx.stroke();} drawColoredGridEdges(c); ctx.globalAlpha=1; ctx.font=`${10*devicePixelRatio}px ui-monospace,monospace`; for(const gp of c.grid.points){const p=worldToScreen(gp), active=gridDrag&&gridDrag.index===gridIndex(c,gp.row,gp.col), unset=gp.id==null; ctx.beginPath(); ctx.fillStyle=unset?unsetColor:color; ctx.arc(p[0],p[1],(active?7:5)*devicePixelRatio,0,Math.PI*2); ctx.fill(); ctx.strokeStyle=active?'#ffd079':(unset?'#6b1717':'#10151f'); ctx.lineWidth=1.5*devicePixelRatio; ctx.stroke(); if(gp.id!=null){ctx.fillStyle='#e8edf5'; ctx.fillText(String(gp.id),p[0]+7*devicePixelRatio,p[1]-7*devicePixelRatio);}} ctx.restore();}
function draw(){ctx.clearRect(0,0,canvas.width,canvas.height); if(!canvas.width)return; if(showMesh){ctx.lineWidth=Math.max(1,devicePixelRatio); for(const f of FACES){const a=faceVisibility(f); if(a<=0)continue; ctx.strokeStyle=`rgba(145,160,185,${a})`; ctx.beginPath(); f.forEach((id,k)=>{const [x,y]=toScreen(id); k?ctx.lineTo(x,y):ctx.moveTo(x,y)}); ctx.closePath(); ctx.stroke();}}
  drawRotoContours();
  drawGridOverlays();
  for(let i=0;i<MAX_LANDMARKS;i++){const vis=pointVisibility(i); if(!vis.visible)continue; const cid=primaryChildIdForPoint(i), [x,y]=toScreen(i), found=cid?findChild(cid):null; ctx.globalAlpha=vis.alpha; ctx.beginPath(); ctx.fillStyle=cid?(found?.child.color||'#a7afbd'):'#e8edf5'; ctx.arc(x,y,(cid?4.8:(IRIS_IDS.has(i)?4.2:3.3))*devicePixelRatio,0,Math.PI*2); ctx.fill(); ctx.globalAlpha=1; if(i===hovered||i===selected){ctx.strokeStyle=i===selected?'#e8edf5':'#ffd079';ctx.lineWidth=2*devicePixelRatio;ctx.beginPath();ctx.arc(x,y,9*devicePixelRatio,0,Math.PI*2);ctx.stroke();} if(showLabels||i===hovered||i===selected){const labelScale=labelZoomScale(), labelPad=6*labelScale*devicePixelRatio; ctx.fillStyle='#e8edf5';ctx.font=`${10*labelScale*devicePixelRatio}px ui-monospace,monospace`;ctx.fillText(String(i),x+labelPad,y-labelPad);}}
}
function stats(){el('assignedCount').textContent=assigned.size; el('freeCount').textContent=MAX_LANDMARKS-assigned.size;}
function renderParentSelect(){const s=el('parentSelect'); const val=s.value; s.innerHTML=''; for(const p of parents){const o=document.createElement('option'); o.value=p.id; o.textContent=p.name; s.appendChild(o);} if(parents.some(p=>p.id===val))s.value=val;}
function setFilter(mode,parentId=null,childId=null){filter={mode,parentId,childId}; renderGroups(); draw();}
function gridEdgeButtons(side,placement,edgeClass,vertical,addDisabled,removeDisabled,addTitle,removeTitle){return `<div class="gridEdgeControls ${placement} ${edgeClass}${vertical?' vertical':''}"><button class="gridAddButton ${edgeClass}" data-grid-add="${side}" title="${addTitle}"${addDisabled?' disabled':''}>+</button><button class="gridAddButton ${edgeClass}" data-grid-remove="${side}" title="${removeTitle}"${removeDisabled?' disabled':''}>-</button></div>`;}
function formatGridPreview(c){ensureGridChild(c); const axis=gridMiniAxisPercent(c).toFixed(2), firstIsLeft=gridLeftEdgeIsFirst(c), visualLeft=firstIsLeft?'gridEdgeLeft':'gridEdgeRight', visualRight=firstIsLeft?'gridEdgeRight':'gridEdgeLeft', cells=c.grid.points.map(p=>`<div class="gridMiniCell ${p.id==null?'':'snapped'}" title="r${p.row+1} c${p.col+1}${p.id==null?'':' landmark '+p.id}">${p.id==null?'':p.id}</div>`).join(''), topControls=gridEdgeButtons('top','gridAddTop','gridEdgeTop',false,c.grid.rows>=32,c.grid.rows<=2,'Add row above','Remove top row'), bottomControls=gridEdgeButtons('bottom','gridAddBottom','gridEdgeBottom',false,c.grid.rows>=32,c.grid.rows<=2,'Add row below','Remove bottom row'), leftControls=gridEdgeButtons('left','gridAddLeft','gridEdgeLeft',true,c.grid.cols>=33,c.grid.cols<=2,'Add column on FaceMesh left side','Remove FaceMesh left column'), rightControls=gridEdgeButtons('right','gridAddRight','gridEdgeRight',true,c.grid.cols>=33,c.grid.cols<=2,'Add column on FaceMesh right side','Remove FaceMesh right column'); return `<div class="gridExpandWrap">${topControls}${leftControls}<div class="gridMini" style="grid-template-columns:repeat(${c.grid.cols},minmax(16px,1fr))"><span class="gridMiniEdge gridMiniEdgeTop"></span><span class="gridMiniEdge gridMiniEdgeBottom"></span><span class="gridMiniEdge gridMiniEdgeLeft ${visualLeft}"></span><span class="gridMiniEdge gridMiniEdgeRight ${visualRight}"></span><span class="gridMiniAxis" style="left:${axis}%"></span>${cells}</div>${rightControls}${bottomControls}</div><div class="gridLegend"><span class="gridLegendItem gridEdgeTop"><span class="gridLegendSwatch"></span>top</span><span class="gridLegendItem gridEdgeBottom"><span class="gridLegendSwatch"></span>bottom</span><span class="gridLegendItem gridEdgeLeft"><span class="gridLegendSwatch"></span>face left</span><span class="gridLegendItem gridEdgeRight"><span class="gridLegendSwatch"></span>face right</span><span>${c.grid.rows} x ${c.grid.cols}</span></div>`;}
function formatChildIds(c){if(!c.ids.length)return 'none'; if(isGridProfile())return `${c.ids.length} points`; return isRotoProfile()?c.ids.map((id,i)=>`${i+1}:${id}`).join(' -> '):c.ids.join(', ');}
function renderSingleGrid(){const box=el('groups'), c=ensureGridProfileRoot(), grid=gridStats(c); box.innerHTML=`<div class="gridPanel"><div class="childTitle"><span class="dot" style="background:${c.color}"></span><div class="childName">Grid overlay</div><span class="badge">${grid.snapped}/${grid.total} snapped</span></div><div class="small" style="margin-top:8px">Set a starting size or expand from the mini grid. Drag canvas handles onto landmarks; Symmetry mirrors across the FaceMesh axis. Grid mode is locked to Unwrap.</div><div class="row gridControls"><label class="inlineCheck">Columns<input id="gridCols" type="number" min="2" max="33" step="1" value="${grid.cols}"></label><label class="inlineCheck">Rows<input id="gridRowsInput" type="number" min="2" max="32" value="${grid.rows}"></label></div><div class="actions" style="opacity:1"><button class="primary" data-a="createGrid">Create grid</button><button data-a="clearSnaps">Clear snaps</button><button class="danger" data-a="resetGrid">Reset overlay</button></div><div class="gridMeta"><span class="badge">${grid.cols} cols</span><span class="badge">${grid.rows} rows</span><span class="badge">${grid.quads} complete quads</span></div>${formatGridPreview(c)}</div>`; box.querySelector('[data-a="createGrid"]').onclick=()=>setGridSize(c,box.querySelector('#gridCols').value,box.querySelector('#gridRowsInput').value); box.querySelector('[data-a="clearSnaps"]').onclick=()=>{for(const p of c.grid.points)p.id=null; syncGridAssigned(c); renderGroups();stats();draw();exportJson();}; box.querySelector('[data-a="resetGrid"]').onclick=()=>setGridSize(c,c.grid.cols,c.grid.rows); for(const btn of box.querySelectorAll('[data-grid-add]'))btn.onclick=()=>addGridEdge(c,btn.dataset.gridAdd); for(const btn of box.querySelectorAll('[data-grid-remove]'))btn.onclick=()=>removeGridEdge(c,btn.dataset.gridRemove);}
function renderGroups(){renderParentSelect(); const box=el('groups'); box.innerHTML=''; if(isGridProfile()){renderSingleGrid(); return;} if(!parents.length){box.innerHTML=isRotoProfile()?'<div class="small">No roto contours. Create a parent such as eyes, lips, or face, then add a child such as left_eye_outer. Click landmarks in outline order.</div>':'<div class="small">No parent groups. Create one, for example nose, then add a child such as left_nostril.</div>';return}
  for(const p of parents){const total=p.children.reduce((s,c)=>s+c.ids.length,0), collapsed=!!p.collapsed; const div=document.createElement('div'); div.className='parent'+(collapsed?' collapsed':''); div.innerHTML=`<div class="parentHead"><button class="toggleParent" data-pa="toggle" title="${collapsed?'Expand':'Collapse'} parent">${collapsed?'+':'-'}</button><div class="parentName">${esc(p.name)}</div><span class="badge">${p.children.length} child</span><span class="badge">${total}</span></div>${collapsed?'':`<div class="childWrap"><div class="parentActions"><button data-pa="add">+ child</button><button data-pa="show" class="${filter.mode==='showParent'&&filter.parentId===p.id?'activeBtn':''}">Show</button><button data-pa="solo" class="${filter.mode==='soloParent'&&filter.parentId===p.id?'activeBtn':''}">Solo</button><button data-pa="rename">Rename</button><button data-pa="delete">Delete parent</button></div><div data-children></div></div>`}`;
    div.querySelector('[data-pa="toggle"]').onclick=()=>{p.collapsed=!p.collapsed;renderGroups();};
    if(collapsed){box.appendChild(div); continue;}
    div.querySelector('[data-pa="add"]').onclick=()=>{el('parentSelect').value=p.id; el('childName').focus();};
    div.querySelector('[data-pa="show"]').onclick=()=>setFilter('showParent',p.id,null);
    div.querySelector('[data-pa="solo"]').onclick=()=>setFilter('soloParent',p.id,null);
    div.querySelector('[data-pa="rename"]').onclick=async()=>{const n=await appPrompt('Rename parent',p.name); if(n&&n.trim()){p.name=n.trim();renderGroups();exportJson();appToast('Parent renamed.','ok');}};
    div.querySelector('[data-pa="delete"]').onclick=async()=>{if(await appConfirm('Delete this parent and all child groups? Shared points remain in other groups.','Delete parent','Delete',true)){for(const c of p.children){for(const id of c.ids)removePointFromChild(id,c.id); if(activeChild===c.id)activeChild=null;} parents=parents.filter(x=>x.id!==p.id); if(!activeChild)activeChild=allChildren()[0]?.id||null; renderGroups();stats();draw();exportJson();appToast('Parent deleted.','ok');}};
    const cb=div.querySelector('[data-children]');
    if(!p.children.length){cb.innerHTML='<div class="small" style="margin-top:8px">No child groups.</div>';} else for(const c of p.children){const cd=document.createElement('div'); cd.className='child'+(c.id===activeChild?' active':''); const openChecked=c.openSpline?' checked':''; const rotoActions=isRotoProfile()?`<label class="inlineCheck" title="Do not close this contour in Roto export"><input data-a="openSpline" type="checkbox"${openChecked}> Open spline</label><button data-a="movePrev">Move selected -</button><button data-a="moveNext">Move selected +</button><button data-a="reverse">Reverse</button>`:''; cd.innerHTML=`<div class="childTitle"><span class="dot" style="background:${c.color}"></span><div class="childName">${esc(c.name)}</div><span class="badge">${c.ids.length}</span></div><div class="ids">${formatChildIds(c)}</div><div class="actions"><button data-a="active">Set active</button><button data-a="show" class="${filter.mode==='showChild'&&filter.childId===c.id?'activeBtn':''}">Show</button><button data-a="solo" class="${filter.mode==='soloChild'&&filter.childId===c.id?'activeBtn':''}">Solo</button>${rotoActions}<button data-a="rename">Rename</button><button data-a="clear">Clear</button><button data-a="delete">Delete</button></div>`;
      cd.querySelector('[data-a="active"]').onclick=()=>{activeChild=c.id;renderGroups();draw();};
      cd.querySelector('[data-a="show"]').onclick=()=>setFilter('showChild',null,c.id);
      cd.querySelector('[data-a="solo"]').onclick=()=>setFilter('soloChild',null,c.id);
      const openSpline=cd.querySelector('[data-a="openSpline"]'), movePrev=cd.querySelector('[data-a="movePrev"]'), moveNext=cd.querySelector('[data-a="moveNext"]'), reverse=cd.querySelector('[data-a="reverse"]');
      if(openSpline)openSpline.onchange=e=>{c.openSpline=!!e.target.checked; draw();exportJson();};
      if(movePrev)movePrev.onclick=()=>moveSelectedInChild(c,-1);
      if(moveNext)moveNext.onclick=()=>moveSelectedInChild(c,1);
      if(reverse)reverse.onclick=()=>{c.ids.reverse(); renderGroups();draw();exportJson();appToast('Contour order reversed.','ok');};
      cd.querySelector('[data-a="rename"]').onclick=async()=>{const n=await appPrompt('Rename child',c.name); if(n&&n.trim()){c.name=n.trim();renderGroups();exportJson();appToast('Child renamed.','ok');}};
      cd.querySelector('[data-a="clear"]').onclick=()=>{for(const id of [...c.ids])removePointFromChild(id,c.id); c.ids=[]; renderGroups();stats();draw();exportJson();};
      cd.querySelector('[data-a="delete"]').onclick=async()=>{if(await appConfirm('Delete this child group? Shared points remain in other groups.','Delete child','Delete',true)){for(const id of c.ids)removePointFromChild(id,c.id); p.children=p.children.filter(x=>x.id!==c.id); if(activeChild===c.id)activeChild=allChildren()[0]?.id||null; renderGroups();stats();draw();exportJson();appToast('Child deleted.','ok');}};
      cb.appendChild(cd);
    }
    box.appendChild(div);
  }
}
function addParent(name){name=(name||el('parentName').value).trim(); if(!name){appToast('Enter a parent group name.','error');return null} if(parents.some(p=>p.name===name)){appToast('That parent already exists.','error');return parents.find(p=>p.name===name)} const p={id:uid('p'),name,children:[],collapsed:false}; parents.push(p); el('parentName').value=''; renderGroups(); exportJson(); appToast('Parent created.','ok'); return p;}
function makeChild(name,color){const c={id:uid('c'),name,color:color||COLORS[allChildren().length%COLORS.length],ids:[],openSpline:false}; if(isGridProfile())createGrid(c,3,2); return c;}
function addChild(parentId,name,color){parentId=parentId||el('parentSelect').value; const p=parents.find(x=>x.id===parentId); if(!p){appToast('Create a parent first.','error');return null} name=(name||el('childName').value).trim(); if(!name){appToast('Enter a child group name.','error');return null} if(p.children.some(c=>c.name===name)){appToast('That child already exists in this parent.','error');return p.children.find(c=>c.name===name)} const c=makeChild(name,color||el('childColor').value||COLORS[allChildren().length%COLORS.length]); p.collapsed=false; p.children.push(c); activeChild=c.id; el('childName').value=''; el('childColor').value=COLORS[(allChildren().length+1)%COLORS.length]; renderGroups();stats();draw();exportJson(); appToast('Child created.','ok'); return c;}
function getOrCreateParent(name){let p=parents.find(x=>x.name===name); if(!p){p={id:uid('p'),name,children:[],collapsed:false}; parents.push(p);} return p;}
function getOrCreateChild(parentName,childName,color){const p=getOrCreateParent(parentName); let c=p.children.find(x=>x.name===childName); if(!c){c=makeChild(childName,color||COLORS[allChildren().length%COLORS.length]); p.children.push(c);} return c;}
function moveSelectedInChild(c,delta){if(selected==null){appToast('Select a landmark first.','error');return} const idx=c.ids.indexOf(selected); if(idx<0){appToast('Selected landmark is not in this contour.','error');return} const next=idx+delta; if(next<0||next>=c.ids.length)return; [c.ids[idx],c.ids[next]]=[c.ids[next],c.ids[idx]]; renderGroups();draw();exportJson();}
function orderIds(ids){return isRotoProfile()?[...new Set(ids)]:[...new Set(ids)].sort((a,b)=>a-b)}
function assign(id,cid=activeChild){if(isGridProfile())return false; if(!cid||id<0||id>=MAX_LANDMARKS)return false; const found=findChild(cid); if(!found||found.child.ids.includes(id))return false; if(!assigned.has(id))assigned.set(id,new Set()); assigned.get(id).add(cid); found.child.ids.push(id); found.child.ids=orderIds(found.child.ids); renderGroups();stats();draw();exportJson();return true;}
function unassign(id,cid=activeChild){if(cid&&pointHasChild(id,cid)){removePointFromChild(id,cid);} else {for(const childId of [...childIdsForPoint(id)])removePointFromChild(id,childId);} renderGroups();stats();draw();exportJson();}
function addIdsToChild(c,ids){for(const n of ids){const id=Number(n); if(Number.isInteger(id)&&id>=0&&id<MAX_LANDMARKS&&!c.ids.includes(id)){if(!assigned.has(id))assigned.set(id,new Set()); assigned.get(id).add(c.id); c.ids.push(id);}} c.ids=orderIds(c.ids); if(!activeChild)activeChild=c.id;}
function parseIds(txt){const out=[]; for(const part of txt.split(/[ ,;\n]+/).filter(Boolean)){if(/^\d+-\d+$/.test(part)){let [a,b]=part.split('-').map(Number); if(a>b)[a,b]=[b,a]; for(let i=a;i<=b;i++)out.push(i)} else if(/^\d+$/.test(part))out.push(Number(part));} return [...new Set(out)].filter(i=>i>=0&&i<MAX_LANDMARKS);}
function buildNested(parentList=parents,profileName=currentProfile){const root={}; for(const p of parentList){root[p.name]={}; for(const c of p.children){if(isRotoProfile(profileName)){root[p.name][c.name]={ids:[...c.ids],openSpline:!!c.openSpline};} else {root[p.name][c.name]=[...c.ids].sort((a,b)=>a-b);}}} return root;}
function buildGridExport(){const c=profiles.grid.parents[0]?.children[0]; if(!c)return {cols:3,rows:2,points:[],ids:[],quads:[],symmetryAxis:GRID_SYMMETRY_AXIS_IDS}; ensureGridChild(c); return {cols:c.grid.cols,rows:c.grid.rows,points:c.grid.points.map(p=>({row:p.row,col:p.col,id:p.id??null,x:p.x,y:p.y})),ids:gridIdsMatrix(c),quads:gridCompleteQuads(c),symmetryAxis:GRID_SYMMETRY_AXIS_IDS};}
function buildProfileExport(){saveProfileState(); if(isGridProfile())ensureGridProfileRoot(); const root={profiles:{}}; for(const name of PROFILE_NAMES)root.profiles[name]=isGridProfile(name)?buildGridExport():buildNested(profiles[name].parents,name); return root;}
function isProfileExport(data){return data&&typeof data==='object'&&!Array.isArray(data)&&data.profiles&&typeof data.profiles==='object'&&!Array.isArray(data.profiles);}
function exportJson(){const data=buildProfileExport(); el('jsonBox').value=JSON.stringify(data,null,2); validateMappingObject(data); return data;}
function gridIdsForImport(node){if(!node||typeof node!=='object')return []; if(Array.isArray(node.points))return node.points.map(p=>Number(p.id)).filter(Number.isInteger); if(Array.isArray(node.ids))return node.ids.flat?node.ids.flat(Infinity).map(Number).filter(Number.isInteger):[]; return [];}
function flattenForImport(obj){const items=[]; function addLeaf(path,ids,meta={}){if(path.length===0)items.push(['grid','grid',ids,meta]); else if(path.length===1)items.push([path[0],'all',ids,meta]); else items.push([path.slice(0,-1).join('.'),path[path.length-1],ids,meta]);} function walk(node,path){if(Array.isArray(node)){addLeaf(path,node); return;} if(node&&typeof node==='object'&&Number.isInteger(Number(node.cols))&&Number.isInteger(Number(node.rows))){addLeaf(path,gridIdsForImport(node),{}); return;} if(node&&typeof node==='object'&&Array.isArray(node.ids)){addLeaf(path,node.ids,{openSpline:!!node.openSpline}); return;} if(node&&typeof node==='object'){for(const [k,v] of Object.entries(node))walk(v,path.concat(k));}}
  walk(obj,[]); return items;}
function validateProfileMapping(data,label){const seen=new Map(), shared=[], invalid=[]; let total=0; for(const [pname,cname,ids] of flattenForImport(data)){const path=`${pname}.${cname}`; if(!Array.isArray(ids)){invalid.push(`${path}: not an array`); continue;} for(const raw of ids){const id=Number(raw); if(!Number.isInteger(id)||id<0||id>=MAX_LANDMARKS){invalid.push(`${path}: ${raw}`); continue;} total++; if(seen.has(id)){shared.push(`${id}: ${seen.get(id)} + ${path}`);} else seen.set(id,path);}}
  const lines=[`Profile: ${label}`,`Unique IDs: ${seen.size}`,`Total entries: ${total}`,`Free IDs: ${MAX_LANDMARKS-seen.size}`];
  if(shared.length)lines.push('',`Shared IDs (${shared.length}):`,...shared.slice(0,40),shared.length>40?'...':''); else lines.push('Shared IDs: none');
  if(invalid.length)lines.push('',`Out of range / invalid (${invalid.length}):`,...invalid.slice(0,40),invalid.length>40?'...':''); else lines.push('Out of range / invalid: none');
  return {lines,sharedCount:shared.length,invalidCount:invalid.length};
}
function validateMappingObject(data){const mappings=isProfileExport(data)?data.profiles:{[currentProfile]:data}; const lines=[`Range: 0-${MAX_LANDMARKS-1}`]; let sharedCount=0, invalidCount=0; for(const name of Object.keys(mappings)){const report=validateProfileMapping(mappings[name]||{},name); sharedCount+=report.sharedCount; invalidCount+=report.invalidCount; lines.push('',...report.lines);}
  el('validationBox').textContent=lines.filter(Boolean).join('\n');
  return {sharedCount, invalidCount};
}
function validateJsonBox(){let data; try{data=JSON.parse(el('jsonBox').value)}catch(e){el('validationBox').textContent='Invalid JSON: '+e.message; return null;} return validateMappingObject(data);}
function importGridMapping(mapping){
  const c=getOrCreateChild('grid','grid',COLORS[0]), cols=normalizeGridCols(mapping?.cols), rows=normalizeGridRows(mapping?.rows);
  createGrid(c,cols,rows);
  if(Array.isArray(mapping?.points)){
    for(const item of mapping.points){
      const row=Number(item.row), col=Number(item.col);
      if(!Number.isInteger(row)||!Number.isInteger(col)||row<0||row>=c.grid.rows||col<0||col>=c.grid.cols)continue;
      const p=gridPoint(c,row,col), x=Number(item.x), y=Number(item.y), hasStoredPosition=Number.isFinite(x)&&Number.isFinite(y), id=Number(item.id);
      if(hasStoredPosition){
        p.x=x;
        p.y=y;
      }
      if(Number.isInteger(id)&&id>=0&&id<MAX_LANDMARKS){
        p.id=id;
        if(!hasStoredPosition){
          p.x=UNWRAP_LAYOUT[id][0];
          p.y=UNWRAP_LAYOUT[id][1];
        }
      }
    }
  } else if(Array.isArray(mapping?.ids)){
    const ids=mapping.ids;
    for(let r=0;r<Math.min(c.grid.rows,ids.length);r++){
      const row=Array.isArray(ids[r])?ids[r]:[];
      for(let col=0;col<Math.min(c.grid.cols,row.length);col++){
        const id=Number(row[col]);
        if(Number.isInteger(id)&&id>=0&&id<MAX_LANDMARKS)snapGridPointToWorld(gridPoint(c,r,col),{x:UNWRAP_LAYOUT[id][0],y:UNWRAP_LAYOUT[id][1]});
      }
    }
  }
  syncGridAssigned(c);
  activeChild=c.id;
}
function replaceProfileFromMapping(name,mapping){const previous={currentProfile,parents,assigned,activeChild}; profiles[name]=emptyProfile(); currentProfile=name; parents=profiles[name].parents; assigned=profiles[name].assigned; activeChild=null; if(isGridProfile(name)){importGridMapping(mapping||{});} else {let i=0; for(const [pname,cname,ids,meta] of flattenForImport(mapping||{})){const c=getOrCreateChild(pname,cname,COLORS[i++%COLORS.length]); if(isRotoProfile(name))c.openSpline=!!meta.openSpline; addIdsToChild(c,ids);}} saveProfileState(); currentProfile=previous.currentProfile; if(previous.currentProfile===name){parents=profiles[name].parents; assigned=profiles[name].assigned; activeChild=profiles[name].activeChild;} else {parents=previous.parents; assigned=previous.assigned; activeChild=previous.activeChild;}}
async function importJson(){let data; try{data=JSON.parse(el('jsonBox').value)}catch(e){appToast('Invalid JSON.','error');return} const report=validateMappingObject(data); if(report.invalidCount&&!(await appConfirm('JSON contains invalid IDs. Import will skip out-of-range points. Continue?','Import JSON','Import',true)))return; const keepProfile=currentProfile; if(isProfileExport(data)){for(const name of PROFILE_NAMES)replaceProfileFromMapping(name,data.profiles[name]||{}); currentProfile=PROFILE_NAMES.includes(keepProfile)?keepProfile:'full';} else {replaceProfileFromMapping(currentProfile,data);} parents=profiles[currentProfile].parents; assigned=profiles[currentProfile].assigned; activeChild=profiles[currentProfile].activeChild; ensureGridProfileRoot(); el('profileSelect').value=currentProfile; updateProfileHint(); updateProfileUi(); renderGroups();stats();draw();exportJson(); appToast('JSON imported.','ok');}
function loadInitialProfiles(){for(const name of PROFILE_NAMES)replaceProfileFromMapping(name,INITIAL_PROFILE_EXPORT.profiles[name]||{}); currentProfile='roto'; parents=profiles.roto.parents; assigned=profiles.roto.assigned; activeChild=profiles.roto.activeChild; selected=null; hovered=null; filter={mode:'all',parentId:null,childId:null}; const ps=el('profileSelect'); if(ps)ps.value=currentProfile; updateProfileHint(); updateProfileUi(); renderGroups();stats();draw();exportJson();}
function gridHitTest(pos){if(!isGridProfile())return null; const c=ensureGridProfileRoot(); let best=null,bd=Infinity; for(let i=0;i<c.grid.points.length;i++){const p=worldToScreen(c.grid.points[i]), d=Math.hypot(p[0]-pos.x,p[1]-pos.y); if(d<bd){bd=d; best=i;}} return bd<=12*devicePixelRatio?{child:c,index:best}:null;}
function applyGridDrag(pos){if(!gridDrag)return; const c=gridDrag.child, point=c.grid.points[gridDrag.index], world=screenToWorld(pos); snapGridPointToWorld(point,world); if(showGridSymmetry){const mirrorCol=c.grid.cols-1-point.col; if(mirrorCol!==point.col){const mirror=gridPoint(c,point.row,mirrorCol), reflected=reflectAcrossSymmetryAxis({x:point.x,y:point.y}); snapGridPointToWorld(mirror,reflected);}} syncGridAssigned(c); renderGroups();stats();draw();exportJson();}
canvas.addEventListener('mousemove',e=>{const pos=fromEvent(e); if(gridDrag){moved=true; applyGridDrag(pos); return;} if(dragMode){const dx=e.clientX-last.x,dy=e.clientY-last.y; if(Math.hypot(dx,dy)>1)moved=true; if(dragMode==='rotate'){freeRot.yaw+=dx*.005; freeRot.pitch=Math.max(-Math.PI*.49,Math.min(Math.PI*.49,freeRot.pitch+dy*.005));} else {pan.x+=dx; pan.y+=dy;} last={x:e.clientX,y:e.clientY}; draw(); return;} const hit=gridHitTest(pos); if(hit){const p=hit.child.grid.points[hit.index]; el('info').innerHTML=`<b>Grid r${p.row+1} c${p.col+1}</b><br>${p.id==null?'not snapped':'landmark '+p.id}`; canvas.style.cursor='grab'; draw(); return;} canvas.style.cursor='crosshair'; hovered=nearest(pos); if(hovered==null)el('info').textContent='Hover a point'; else {const memberships=[...childIdsForPoint(hovered)].map(cid=>findChild(cid)).filter(Boolean), v=landmarkPoint(hovered), virtual=IRIS_IDS.has(hovered)?'<br>virtual iris point':'', memberHtml=memberships.length?memberships.map(x=>`<br>${esc(x.parent.name)}: <span style="color:${x.child.color||'#e8edf5'}">${esc(x.child.name)}</span>`).join(''):'free'; el('info').innerHTML=`<b>ID ${hovered}</b>${virtual}<br>x ${v[0].toFixed(3)}<br>y ${v[1].toFixed(3)}<br>z ${v[2].toFixed(3)}<br>${memberHtml}`;} draw();});
canvas.addEventListener('mousedown',e=>{moved=false;last={x:e.clientX,y:e.clientY}; const hit=gridHitTest(fromEvent(e)); if(hit){gridDrag=hit; canvas.style.cursor='grabbing'; applyGridDrag(fromEvent(e)); return;} dragMode=(viewMode==='free3d'&&e.button===0&&!e.shiftKey)?'rotate':'pan';});
canvas.addEventListener('contextmenu',e=>e.preventDefault());
window.addEventListener('mouseup',()=>{dragMode=null; gridDrag=null; canvas.style.cursor='crosshair';});
canvas.addEventListener('click',e=>{if(isGridProfile())return; if(moved)return; const id=nearest(fromEvent(e)); if(id==null)return; selected=id; if(e.altKey){unassign(id);return} if(!activeChild){appToast('Create or select a child group first.','error');return} if(!assign(id))draw();});
canvas.addEventListener('wheel',e=>{e.preventDefault(); const nextScale=Math.max(.2,Math.min(12,scale*(e.deltaY<0?1.1:.9))); if(nextScale!==scale)zoomAt(fromEvent(e),nextScale); draw();},{passive:false});
el('addParent').onclick=()=>addParent(); el('parentName').addEventListener('keydown',e=>{if(e.key==='Enter')addParent();});
el('addChild').onclick=()=>addChild(); el('childName').addEventListener('keydown',e=>{if(e.key==='Enter')addChild();});
el('addManual').onclick=()=>{if(!activeChild){appToast('Select a child group first.','error');return} for(const id of parseIds(el('manualIds').value))assign(id); el('manualIds').value='';};
el('profileSelect').onchange=e=>useProfile(e.target.value);
el('exportBtn').onclick=exportJson; el('validateBtn').onclick=validateJsonBox; el('importBtn').onclick=importJson; el('downloadBtn').onclick=()=>{const blob=new Blob([JSON.stringify(exportJson(),null,2)],{type:'application/json'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='mediapipe_landmark_profiles.json'; a.click(); URL.revokeObjectURL(a.href);};
el('clearAll').onclick=async()=>{if(await appConfirm('Clear current profile?','Clear profile','Clear',true)){resetCurrentProfile();renderGroups();stats();draw();exportJson();appToast('Profile cleared.','ok');}};
el('resetView').onclick=()=>{scale=1;pan={x:0,y:0};freeRot={yaw:0,pitch:0};draw();}; el('toggleMesh').onclick=e=>{showMesh=!showMesh;e.target.textContent='Mesh: '+(showMesh?'ON':'OFF');draw();}; el('toggleLabels').onclick=e=>{showLabels=!showLabels;e.target.textContent='ID: '+(showLabels?'ON':'OFF');draw();}; el('toggleGridSymmetry').onclick=()=>{showGridSymmetry=!showGridSymmetry;updateViewControls();draw();}; el('showAll').onclick=()=>setFilter('all'); el('showUnassigned').onclick=()=>setFilter('unassigned'); el('unassignSelected').onclick=()=>{if(selected!=null)unassign(selected);}; el('viewMode').onchange=e=>{viewMode=isGridProfile()?'unwrap':e.target.value; if(isGridProfile())e.target.value='unwrap'; scale=1;pan={x:0,y:0};updateViewControls();draw();};
el('unwrapStrength').oninput=e=>setUnwrapStrength(e.target.value);
el('unwrapStrength').onchange=e=>setUnwrapStrength(e.target.value,true);
uiState=loadUiState(); initPanelControls(); updateUnwrapStrengthUi(); updateViewControls(); updateProfileHint(); applyUiState(); resize(); loadInitialProfiles();
