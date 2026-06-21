'use strict';
// Shared mutable state and UI constants for the landmark grouper.
// Centralized here so every module references the same bindings. Loaded right
// after data.js so load-time const computations in geometry.js can read unwrapStrength.

const COLORS=['#7cc7ff','#55d68a','#ffcc66','#ff7aa2','#b6f36b','#93c5fd','#d8b4fe','#fdba74','#a7f3d0','#fca5a5','#f0abfc','#67e8f9'];
const PROFILE_NAMES=['full','dense','sparse','roto','grid'];
const PROFILE_HINTS={
  full:'Full profile uses regular unordered landmark groups.',
  dense:'Dense profile uses separate regular landmark groups.',
  sparse:'Sparse profile uses separate regular landmark groups.',
  roto:'Roto profile is for face-part contours. Click landmarks in outline order; use Open spline for nose bridge.',
  grid:'Grid profile builds an expandable overlay in Unwrap view. Drag grid handles onto landmarks; Symmetry moves the mirrored handle too.'
};
const UI_STORAGE_KEY='mediapipeLandmarkGrouper.ui';

function emptyProfile(){return {parents:[],assigned:new Map(),activeChild:null}}
const profiles=Object.fromEntries(PROFILE_NAMES.map(name=>[name,emptyProfile()]));

// View / interaction state
let viewMode='front', scale=1, pan={x:0,y:0}, freeRot={yaw:0,pitch:0}, dragMode=null, last={x:0,y:0}, moved=false;
let showMesh=true, showLabels=false, showGridSymmetry=true, gridDrag=null;
let unwrapStrength=0, unwrapRecalcTimer=null;
let transformCache=null;
let uiState; // initialized in bootstrap via loadUiState()

// Profile data state
let currentProfile='full', parents=profiles.full.parents, assigned=profiles.full.assigned, activeChild=profiles.full.activeChild, selected=null, hovered=null;
let filter={mode:'all', parentId:null, childId:null};