'use strict';
// Geometry: projections, bounds, unwrap layout, symmetry, and screen transforms.
// Reads shared state (viewMode, pan, scale, unwrapStrength, transformCache) from state.js
// and mesh data from data.js. BASE_UV_LAYOUT/UNWRAP_LAYOUT/FREE3D_BOUNDS are computed at
// load time, so this file must load after data.js and state.js.

function centeredPoint(v){return [v[0]-MODEL_CENTER_3D[0],v[1]-MODEL_CENTER_3D[1],v[2]-MODEL_CENTER_3D[2]];}
function free3dBounds(){let radius=0; for(let i=0;i<MAX_LANDMARKS;i++){const v=centeredPoint(landmarkPoint(i)); radius=Math.max(radius,Math.hypot(v[0],v[1],v[2]));} return {minX:-radius,maxX:radius,minY:-radius,maxY:radius};}
const FREE3D_BOUNDS = free3dBounds();
function frontPoint(id){const v=landmarkPoint(id); return [v[0],-v[1]];}
function flatBounds(points){
  let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
  for(const p of points){minX=Math.min(minX,p[0]); maxX=Math.max(maxX,p[0]); minY=Math.min(minY,p[1]); maxY=Math.max(maxY,p[1]);}
  return {minX,maxX,minY,maxY};
}
function normalizedPoints(points){
  const b=flatBounds(points), cx=(b.minX+b.maxX)/2, cy=(b.minY+b.maxY)/2, s=UNWRAP_UV_SCALE/Math.max(b.maxX-b.minX,b.maxY-b.minY||1);
  return points.map(p=>[(p[0]-cx)*s,(p[1]-cy)*s]);
}
function baseUvPoint(id){
  if(id<BASE_UV_468.length)return BASE_UV_LAYOUT[id];
  const left=id>=468&&id<=472;
  const a=IRIS_EYE_ANCHOR_IDS[left?'left':'right'];
  const inner=BASE_UV_LAYOUT[a.inner], outer=BASE_UV_LAYOUT[a.outer], top=BASE_UV_LAYOUT[a.top], bottom=BASE_UV_LAYOUT[a.bottom];
  const center=[(inner[0]+outer[0]+top[0]+bottom[0])*.25,(inner[1]+outer[1]+top[1]+bottom[1])*.25];
  const rx=[(outer[0]-inner[0])*IRIS_RX_SCALE,(outer[1]-inner[1])*IRIS_RX_SCALE], ry=[(top[0]-bottom[0])*IRIS_RY_SCALE,(top[1]-bottom[1])*IRIS_RY_SCALE];
  const o=IRIS_RING_OFFSETS[id-(left?469:474)]||[0,0];
  return [center[0]+rx[0]*o[0]+ry[0]*o[1],center[1]+rx[1]*o[0]+ry[1]*o[1]];
}
function computeUnwrapLayout(){
  const front=Array.from({length:MAX_LANDMARKS},(_,id)=>frontPoint(id));
  const normalizedFront=normalizedPoints(front);
  const t=Math.max(0,Math.min(1,unwrapStrength));
  return normalizedFront.map((p,id)=>{const uv=baseUvPoint(id); return [p[0]+(uv[0]-p[0])*t,p[1]+(uv[1]-p[1])*t];});
}
const BASE_UV_LAYOUT = normalizedPoints(BASE_UV_468);
let UNWRAP_LAYOUT = computeUnwrapLayout();
let UNWRAP_BOUNDS = flatBounds(UNWRAP_LAYOUT);
function updateUnwrapStrengthUi(){
  const input=el('unwrapStrength'), label=el('unwrapStrengthValue');
  if(input)input.value=String(unwrapStrength);
  if(label)label.textContent=unwrapStrength.toFixed(2);
}
function rebuildUnwrapLayout(){
  UNWRAP_LAYOUT=computeUnwrapLayout();
  UNWRAP_BOUNDS=flatBounds(UNWRAP_LAYOUT);
  transformCache=null;
  draw();
}
function setUnwrapStrength(value,immediate=false){
  unwrapStrength=Math.max(0,Math.min(1,Number(value)||0));
  updateUnwrapStrengthUi();
  clearTimeout(unwrapRecalcTimer);
  if(immediate){rebuildUnwrapLayout(); return;}
  unwrapRecalcTimer=setTimeout(rebuildUnwrapLayout,40);
}
function rotateFree3d(v){
  v=centeredPoint(v);
  const cy=Math.cos(freeRot.yaw), sy=Math.sin(freeRot.yaw), cp=Math.cos(freeRot.pitch), sp=Math.sin(freeRot.pitch);
  const x=v[0]*cy+v[2]*sy, z=v[2]*cy-v[0]*sy, y=v[1]*cp-z*sp;
  return [x,y,z*cp+v[1]*sp];
}
function project(v,id=null){if(viewMode==='unwrap'&&id!=null)return UNWRAP_LAYOUT[id]; if(viewMode==='free3d'){const p=rotateFree3d(v); return [p[0],-p[1]];} if(viewMode==='side')return [v[2],-v[1]]; if(viewMode==='top')return [v[0],-v[2]]; return [v[0],-v[1]];}
function bounds(){
  if(viewMode==='free3d')return FREE3D_BOUNDS;
  if(viewMode==='unwrap')return UNWRAP_BOUNDS;
  return flatBounds(Array.from({length:MAX_LANDMARKS},(_,id)=>project(landmarkPoint(id),id)));
}
function tx(){const key=viewMode+'|'+scale+'|'+canvas.width+'|'+canvas.height; if(transformCache&&transformCache.key===key)return transformCache; const b=bounds(), w=canvas.width, h=canvas.height, s=Math.min(w/(b.maxX-b.minX),h/(b.maxY-b.minY))*0.82*scale; transformCache={key,s,cx:(b.minX+b.maxX)/2,cy:(b.minY+b.maxY)/2,w,h}; return transformCache;}
function toScreen(id){const [x,y]=project(landmarkPoint(id),id); const t=tx(); return [(x-t.cx)*t.s+t.w/2+pan.x*devicePixelRatio,(y-t.cy)*t.s+t.h/2+pan.y*devicePixelRatio];}
function worldToScreen(p){const t=tx(); return [(p.x-t.cx)*t.s+t.w/2+pan.x*devicePixelRatio,(p.y-t.cy)*t.s+t.h/2+pan.y*devicePixelRatio];}
function screenToWorld(pos){const t=tx(); return {x:(pos.x-t.w/2-pan.x*devicePixelRatio)/t.s+t.cx,y:(pos.y-t.h/2-pan.y*devicePixelRatio)/t.s+t.cy};}
function fromEvent(e){const r=canvas.getBoundingClientRect(); return {x:(e.clientX-r.left)*devicePixelRatio,y:(e.clientY-r.top)*devicePixelRatio};}
function nearest(pos){let best=null,bd=1e9; for(let i=0;i<MAX_LANDMARKS;i++){const [x,y]=toScreen(i), d=Math.hypot(x-pos.x,y-pos.y); if(d<bd){bd=d;best=i}} return bd<14*devicePixelRatio?best:null;}
function nearestLandmarkWorld(p){let best=0,bd=Infinity; for(let i=0;i<MAX_LANDMARKS;i++){const q=UNWRAP_LAYOUT[i], d=(q[0]-p.x)*(q[0]-p.x)+(q[1]-p.y)*(q[1]-p.y); if(d<bd){bd=d; best=i;}} return best;}
function snapGridPointToWorld(point,p){const id=nearestLandmarkWorld(p), q=UNWRAP_LAYOUT[id]; point.x=q[0]; point.y=q[1]; point.id=id;}
function axisPolylineWorld(){return GRID_SYMMETRY_AXIS_IDS.map(id=>({x:UNWRAP_LAYOUT[id][0],y:UNWRAP_LAYOUT[id][1]}));}
function reflectAcrossSegment(p,a,b){const dx=b.x-a.x, dy=b.y-a.y, len=dx*dx+dy*dy||1, t=Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/len)), px=a.x+dx*t, py=a.y+dy*t; return {x:2*px-p.x,y:2*py-p.y};}
function reflectAcrossSymmetryAxis(p){const axis=axisPolylineWorld(); let best=null,bd=Infinity; for(let i=0;i<axis.length-1;i++){const r=reflectAcrossSegment(p,axis[i],axis[i+1]), dx=r.x-p.x, dy=r.y-p.y, d=dx*dx+dy*dy; if(d<bd){bd=d; best=r;}} return best||{x:p.x,y:p.y};}
function labelZoomScale(){return 1+(Math.max(1,Math.min(12,scale))-1)/11*2;}
function zoomAt(pos,nextScale){const oldScale=scale, ratio=nextScale/oldScale, cx=canvas.width/2, cy=canvas.height/2; pan.x=(pos.x-cx-(pos.x-cx-pan.x*devicePixelRatio)*ratio)/devicePixelRatio; pan.y=(pos.y-cy-(pos.y-cy-pan.y*devicePixelRatio)*ratio)/devicePixelRatio; scale=nextScale;}