'use strict';
// Grid model + geometry: the expandable overlay used in the 'grid' profile.
// Reads UNWRAP_LAYOUT/UNWRAP_BOUNDS (geometry.js), shared state (state.js), and
// calls makeChild/findChild (model.js) and refresh (grouper.js) at call time.

const GRID_LIMITS={cols:{min:2,max:33},rows:{min:2,max:32}};
function clampInt(v,min,max,def){return Math.max(min,Math.min(max,Math.round(Number(v)||def)));}
function normalizeGridCols(cols){return clampInt(cols,GRID_LIMITS.cols.min,GRID_LIMITS.cols.max,3);}
function normalizeGridRows(rows){return clampInt(rows,GRID_LIMITS.rows.min,GRID_LIMITS.rows.max,2);}

function ensureGridProfileRoot(){if(!isGridProfile())return null; let p=parents[0]; if(!p){p={id:uid('p'),name:'grid',children:[],collapsed:false}; parents=[p]; profiles.grid.parents=parents;} let c=p.children[0]; if(!c){c=makeChild('grid',COLORS[0]); p.children=[c];} ensureGridChild(c); syncGridAssigned(c); activeChild=c.id; profiles.grid.activeChild=activeChild; return c;}
function ensureGridChild(c){if(!c.grid||!Array.isArray(c.grid.points))createGrid(c,Number(c.grid?.cols)||3,Number(c.grid?.rows)||2); return c;}
function gridIndex(c,row,col){return row*c.grid.cols+col;}
function gridPoint(c,row,col){return c.grid.points[gridIndex(c,row,col)];}
function gridIdsMatrix(c){ensureGridChild(c); const out=[]; for(let r=0;r<c.grid.rows;r++){const row=[]; for(let col=0;col<c.grid.cols;col++)row.push(gridPoint(c,r,col).id??null); out.push(row);} return out;}
function gridCompleteQuads(c){ensureGridChild(c); const quads=[]; for(let r=0;r<c.grid.rows-1;r++){for(let col=0;col<c.grid.cols-1;col++){const ids=[gridPoint(c,r,col).id,gridPoint(c,r,col+1).id,gridPoint(c,r+1,col+1).id,gridPoint(c,r+1,col).id]; if(ids.every(id=>id!=null))quads.push(ids);}} return quads;}
function gridStats(c){ensureGridChild(c); const snapped=c.grid.points.filter(p=>p.id!=null).length; return {cols:c.grid.cols,rows:c.grid.rows,total:c.grid.points.length,snapped,quads:gridCompleteQuads(c).length};}
function syncGridAssigned(c){assigned=new Map(); c.ids=[]; for(const p of c.grid.points){if(p.id==null)continue; c.ids.push(p.id); if(!assigned.has(p.id))assigned.set(p.id,new Set()); assigned.get(p.id).add(c.id);} profiles.grid.assigned=assigned;}
function createGrid(c,cols=3,rows=2){cols=normalizeGridCols(cols); rows=normalizeGridRows(rows); const b=UNWRAP_BOUNDS, padX=(b.maxX-b.minX)*.12, padY=(b.maxY-b.minY)*.1, minX=b.minX+padX, maxX=b.maxX-padX, minY=b.minY+padY, maxY=b.maxY-padY, points=[]; for(let r=0;r<rows;r++){for(let col=0;col<cols;col++){const x=minX+(maxX-minX)*col/(cols-1), y=minY+(maxY-minY)*r/(rows-1); points.push({row:r,col,x,y,id:null});}} c.grid={cols,rows,points}; c.ids=[]; syncGridAssigned(c); return c;}
function setGridSize(c,cols,rows){createGrid(c,cols,rows); refresh();}
function cloneGridPoint(p,row,col){return {row,col,x:p.x,y:p.y,id:p.id??null};}
function avgColumnX(c,col){let sum=0; for(let r=0;r<c.grid.rows;r++)sum+=gridPoint(c,r,col).x; return sum/c.grid.rows;}
function gridHorizontalCenterX(c){let sum=0; for(const p of c.grid.points)sum+=p.x; return sum/c.grid.points.length;}
function gridSymmetryCenterX(){return GRID_SYMMETRY_AXIS_IDS.reduce((sum,id)=>sum+UNWRAP_LAYOUT[id][0],0)/GRID_SYMMETRY_AXIS_IDS.length;}
function gridLeftEdgeIsFirst(c){const first=avgColumnX(c,0), last=avgColumnX(c,c.grid.cols-1); if(Math.abs(first-last)>.000001)return first<last; return first<=Math.min(gridHorizontalCenterX(c),gridSymmetryCenterX());}
function gridMiniAxisPercent(c){const first=avgColumnX(c,0), last=avgColumnX(c,c.grid.cols-1), min=Math.min(first,last), max=Math.max(first,last), span=max-min; if(span<=.000001)return 50; return Math.max(0,Math.min(100,(gridSymmetryCenterX()-min)/span*100));}
function normalizeGridPointIndexes(c){for(let r=0;r<c.grid.rows;r++){for(let col=0;col<c.grid.cols;col++){const p=gridPoint(c,r,col); p.row=r; p.col=col;}}}
// dir=-1 extrapolates before a (a-(b-a)); dir=+1 extrapolates after b (b+(b-a)). Merges the
// former extrapolateBefore/extrapolateAfter pair (review #2).
function extrapolate(a,b,dir,row,col){const dx=b.x-a.x, dy=b.y-a.y; return {row,col,x:(dir<0?a.x:b.x)+dir*dx,y:(dir<0?a.y:b.y)+dir*dy,id:null};}
function addGridEdge(c,side){ensureGridChild(c); const cols=c.grid.cols, rows=c.grid.rows; if((side==='left'||side==='right')&&cols>=GRID_LIMITS.cols.max)return; if((side==='top'||side==='bottom')&&rows>=GRID_LIMITS.rows.max)return; const points=[]; if(side==='top'){for(let col=0;col<cols;col++){points.push(extrapolate(gridPoint(c,0,col),gridPoint(c,1,col),-1,0,col));} for(let r=0;r<rows;r++){for(let col=0;col<cols;col++)points.push(cloneGridPoint(gridPoint(c,r,col),r+1,col));} c.grid.rows=rows+1; c.grid.points=points;} else if(side==='bottom'){for(let r=0;r<rows;r++){for(let col=0;col<cols;col++)points.push(cloneGridPoint(gridPoint(c,r,col),r,col));} for(let col=0;col<cols;col++){points.push(extrapolate(gridPoint(c,rows-2,col),gridPoint(c,rows-1,col),+1,rows,col));} c.grid.rows=rows+1; c.grid.points=points;} else {const addAtStart=side==='left'?gridLeftEdgeIsFirst(c):!gridLeftEdgeIsFirst(c); for(let r=0;r<rows;r++){if(addAtStart)points.push(extrapolate(gridPoint(c,r,0),gridPoint(c,r,1),-1,r,0)); for(let col=0;col<cols;col++)points.push(cloneGridPoint(gridPoint(c,r,col),r,col+(addAtStart?1:0))); if(!addAtStart)points.push(extrapolate(gridPoint(c,r,cols-2),gridPoint(c,r,cols-1),+1,r,cols));} c.grid.cols=cols+1; c.grid.points=points;} normalizeGridPointIndexes(c); syncGridAssigned(c); refresh();}
function removeGridEdge(c,side){ensureGridChild(c); const cols=c.grid.cols, rows=c.grid.rows; if((side==='left'||side==='right')&&cols<=GRID_LIMITS.cols.min)return; if((side==='top'||side==='bottom')&&rows<=GRID_LIMITS.rows.min)return; const points=[]; if(side==='top'){for(let r=1;r<rows;r++){for(let col=0;col<cols;col++)points.push(cloneGridPoint(gridPoint(c,r,col),r-1,col));} c.grid.rows=rows-1; c.grid.points=points;} else if(side==='bottom'){for(let r=0;r<rows-1;r++){for(let col=0;col<cols;col++)points.push(cloneGridPoint(gridPoint(c,r,col),r,col));} c.grid.rows=rows-1; c.grid.points=points;} else {const removeAtStart=side==='left'?gridLeftEdgeIsFirst(c):!gridLeftEdgeIsFirst(c), removeCol=removeAtStart?0:cols-1; for(let r=0;r<rows;r++){for(let col=0;col<cols;col++){if(col===removeCol)continue; points.push(cloneGridPoint(gridPoint(c,r,col),r,col-(col>removeCol?1:0)));}} c.grid.cols=cols-1; c.grid.points=points;} normalizeGridPointIndexes(c); syncGridAssigned(c); refresh();}
function buildGridExport(){const c=profiles.grid.parents[0]?.children[0]; if(!c)return {cols:3,rows:2,points:[],ids:[],quads:[],symmetryAxis:GRID_SYMMETRY_AXIS_IDS}; ensureGridChild(c); return {cols:c.grid.cols,rows:c.grid.rows,points:c.grid.points.map(p=>({row:p.row,col:p.col,id:p.id??null,x:p.x,y:p.y})),ids:gridIdsMatrix(c),quads:gridCompleteQuads(c),symmetryAxis:GRID_SYMMETRY_AXIS_IDS};}
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
function gridHitTest(pos){if(!isGridProfile())return null; const c=ensureGridProfileRoot(); let best=null,bd=Infinity; for(let i=0;i<c.grid.points.length;i++){const p=worldToScreen(c.grid.points[i]), d=Math.hypot(p[0]-pos.x,p[1]-pos.y); if(d<bd){bd=d; best=i;}} return bd<=12*devicePixelRatio?{child:c,index:best}:null;}
function applyGridDrag(pos){if(!gridDrag)return; const c=gridDrag.child, point=c.grid.points[gridDrag.index], world=screenToWorld(pos); snapGridPointToWorld(point,world); if(showGridSymmetry){const mirrorCol=c.grid.cols-1-point.col; if(mirrorCol!==point.col){const mirror=gridPoint(c,point.row,mirrorCol), reflected=reflectAcrossSymmetryAxis({x:point.x,y:point.y}); snapGridPointToWorld(mirror,reflected);}} syncGridAssigned(c); refresh();}