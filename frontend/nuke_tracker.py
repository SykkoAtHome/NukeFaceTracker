import os
import sys
import json
import re
import subprocess
import nuke

# Add backend directory to sys.path to import landmarks config
plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_dir = os.path.join(plugin_dir, "backend")
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

try:
    import landmarks_config
except ImportError:
    landmarks_config = None


def find_upstream_read(node):
    """Recursively traverses upstream to find the first Read node."""
    if not node:
        return None
    if node.Class() == "Read":
        return node
    
    # Traverse all upstream inputs
    for i in range(node.inputs()):
        parent = node.input(i)
        result = find_upstream_read(parent)
        if result:
            return result
    return None


def find_vector_channels(node):
    """Scans a node's channels to find the best horizontal (U/X) and vertical (V/Y) 
    vector channel pair.
    
    Prioritizes:
    1. Layers containing 'smartvector' (e.g. smartvector_fwd, smartvector) with .u/.v or .x/.y
    2. Layers containing 'forward' (e.g. forward) with .u/.v or .x/.y
    3. Layers containing 'motion' (e.g. motion) with .u/.v or .x/.y
    4. Any layer with .u/.v or .x/.y
    
    Returns:
        (u_channel, v_channel) if found, otherwise (None, None)
    """
    if not node:
        return None, None
        
    try:
        channels = node.channels()
    except Exception:
        return None, None
    
    # Extract unique layer names
    layers = set()
    for ch in channels:
        if '.' in ch:
            layers.add(ch.split('.')[0])
            
    # Define channel suffix pairs in order of preference
    suffix_pairs = [('.u', '.v'), ('.x', '.y')]
    
    # We will score each layer to find the best match
    best_score = -1
    best_pair = (None, None)
    
    for layer in layers:
        for suffix_u, suffix_v in suffix_pairs:
            ch_u = f"{layer}{suffix_u}"
            ch_v = f"{layer}{suffix_v}"
            if ch_u in channels and ch_v in channels:
                # Score this layer based on its name
                score = 0
                lower_layer = layer.lower()
                if 'smartvector' in lower_layer:
                    score = 100
                    # Give higher preference to f01 or f1 (frame distance 1) over larger distances
                    if '_f01' in lower_layer or '_f1' in lower_layer:
                        score += 20
                    elif 'fwd' in lower_layer:
                        score += 10
                elif 'forward' in lower_layer:
                    score = 50
                elif 'motion' in lower_layer:
                    score = 30
                else:
                    score = 10
                    
                if score > best_score:
                    best_score = score
                    best_pair = (ch_u, ch_v)
                    
    return best_pair



def set_range_to_input(node):
    """Callback function to sync the node's frame range to its active upstream input."""
    input_node = node.input(0)
    if not input_node:
        nuke.message("No input node connected to this Face Tracker.\nPlease connect it to a Read node pipeline.")
        return
        
    start = int(input_node.firstFrame())
    end = int(input_node.lastFrame())
    
    # Handle default/invalid frame range by falling back to root settings
    if start == end and start == 0:
        start = int(nuke.root().firstFrame())
        end = int(nuke.root().lastFrame())
        
    node['start_frame'].setValue(start)
    node['end_frame'].setValue(end)


def create_face_tracker_node():
    """Factory function that spawns the FaceTracker custom node on the canvas,
    populating it with all standard tracking knobs.
    """
    # Create Group Node which serves as pass-through
    node = nuke.createNode('Group')
    node.setName("FaceTracker", True)
    
    # Give it a nice, distinctive orange/copper tile color for identification in DAG
    node['tile_color'].setValue(0xff8c00ff)
    
    # Setup internal pipeline for the Group node
    with node:
        input_source = nuke.createNode('Input', inpanel=False)
        input_source.setName("Source")
        
        input_vectors = nuke.createNode('Input', inpanel=False)
        input_vectors.setName("SmartVector")
        
        output = nuke.createNode('Output', inpanel=False)
        output.setInput(0, input_source)
    
    # 1. Tracking Settings Tab
    tracking_tab = nuke.Tab_Knob("tracking_tab", "Tracking")
    node.addKnob(tracking_tab)
    
    # Resolve initial ranges based on selected nodes or project
    start_frame = 1
    end_frame = 100
    
    input_node = node.input(0)
    if input_node:
        start_frame = int(input_node.firstFrame())
        end_frame = int(input_node.lastFrame())
        if start_frame == end_frame and start_frame == 0:
            start_frame = int(nuke.root().firstFrame())
            end_frame = int(nuke.root().lastFrame())
            
    # Frame Range Knobs
    start_knob = nuke.Int_Knob("start_frame", "Start Frame")
    start_knob.setValue(start_frame)
    node.addKnob(start_knob)
    
    end_knob = nuke.Int_Knob("end_frame", "End Frame")
    end_knob.setValue(end_frame)
    node.addKnob(end_knob)
    
    range_btn = nuke.PyScript_Knob("set_range", "Set to Input Range", "import nuke_tracker; nuke_tracker.set_range_to_input(nuke.thisNode())")
    node.addKnob(range_btn)
    
    # Settings Section
    node.addKnob(nuke.Text_Knob("divider_settings", "Settings", ""))
    
    mode_knob = nuke.Enumeration_Knob("mode", "Tracking Mode", ["Video (Smooth / Stabilized)", "Image (Frame-by-Frame)"])
    mode_knob.setTooltip("Video mode uses temporal tracking (Kalman filters) to eliminate frame-to-frame landmark jitter.\n\nImage mode runs raw face detection on each frame independently.")
    node.addKnob(mode_knob)
    
    quality_knob = nuke.Enumeration_Knob("quality", "Tracking Quality", ["Standard", "High Quality", "Maximum"])
    quality_knob.setTooltip("Higher quality levels increase the confidence thresholds to prevent tracking drift or false detections.")
    node.addKnob(quality_knob)
    
    # Refinement Section
    node.addKnob(nuke.Text_Knob("divider_refine", "Refinement", ""))
    refine_knob = nuke.Boolean_Knob("refine_smartvectors", "Refine with SmartVectors", False)
    refine_knob.setTooltip("Enables high-precision local refinement of tracking coordinates using motion vectors from the 'SmartVector' input.")
    node.addKnob(refine_knob)
    
    stiffness_knob = nuke.Double_Knob("anchor_stiffness", "Anchor Stiffness")
    stiffness_knob.setValue(0.1)
    stiffness_knob.setRange(0.01, 0.5)
    stiffness_knob.setTooltip("Controls the blend ratio between local motion tracking and global MediaPipe anchors on each frame.\nLower values (e.g. 0.05) lock tight to physical skin textures but may accumulate drift.\nHigher values (e.g. 0.25) snap strongly back to MediaPipe landmarks.")
    node.addKnob(stiffness_knob)
    stiffness_knob.setVisible(False)
    
    # Output File Section
    node.addKnob(nuke.Text_Knob("divider_output", "Output Options", ""))
    
    # Construct path cleanly to use forward slashes
    temp_json = os.path.join(plugin_dir, "temp_tracker_data.json").replace("\\", "/")
    output_json_knob = nuke.File_Knob("output_json", "Output JSON File")
    output_json_knob.setValue(temp_json)
    node.addKnob(output_json_knob)
    
    node.addKnob(nuke.Text_Knob("divider_action", "", ""))
    
    # Main action button
    track_btn = nuke.PyScript_Knob("track_btn", "Track Face", "import nuke_tracker; nuke_tracker.run_tracking_on_node(nuke.thisNode())")
    track_btn.setFlag(nuke.STARTLINE)
    node.addKnob(track_btn)
    
    # 2. Tracker Node Generation Tab
    tracker_tab = nuke.Tab_Knob("tracker_tab", "Tracker")
    node.addKnob(tracker_tab)
    
    density_knob = nuke.Enumeration_Knob("landmark_density", "Landmark Density", ["Sparse (Standard - 29 pts)", "Dense (Contours - 128 pts)", "Full (Entire Mesh - 468 pts)"])
    density_knob.setTooltip("Sparse: Tracks up to 29 standard facial features.\nDense: Tracks up to 128 sequential contour points.\nFull: Tracks the entire 468-point face mesh topology.")
    node.addKnob(density_knob)
    
    divider_landmarks = nuke.Text_Knob("divider_landmarks", "Select Landmarks to Track", "")
    node.addKnob(divider_landmarks)
    
    track_nose = nuke.Boolean_Knob("track_nose", "Nose (Tip, Bridge, Alar)", True)
    track_eyes = nuke.Boolean_Knob("track_eyes", "Eyes (Corners, Eyelids)", True)
    track_eyebrows = nuke.Boolean_Knob("track_eyebrows", "Eyebrows (Left & Right)", False)
    track_mouth = nuke.Boolean_Knob("track_mouth", "Mouth (Lip contours & Corners)", True)
    track_contour = nuke.Boolean_Knob("track_contour", "Face Contour (Chin, Forehead, Cheeks)", True)
    
    track_eyes.setFlag(nuke.STARTLINE)
    track_eyebrows.setFlag(nuke.STARTLINE)
    track_mouth.setFlag(nuke.STARTLINE)
    track_contour.setFlag(nuke.STARTLINE)
    
    node.addKnob(track_nose)
    node.addKnob(track_eyes)
    node.addKnob(track_eyebrows)
    node.addKnob(track_mouth)
    node.addKnob(track_contour)
    
    info_full_mesh = nuke.Text_Knob("info_full_mesh", "", "<span style='color:#ffa500'><b>Warning:</b> Tracking all 468 landmarks will create 468 point tracks.<br>This may slow down Foundry Nuke's viewport and node properties panel.</span>")
    node.addKnob(info_full_mesh)
    info_full_mesh.setVisible(False)
    
    node.addKnob(nuke.Text_Knob("divider_flags", "Export Transform Flags", ""))
    export_t = nuke.Boolean_Knob("export_t", "T (Translate)", True)
    export_r = nuke.Boolean_Knob("export_r", "R (Rotation)", False)
    export_s = nuke.Boolean_Knob("export_s", "S (Scale)", False)
    export_r.clearFlag(nuke.STARTLINE)
    export_s.clearFlag(nuke.STARTLINE)
    node.addKnob(export_t)
    node.addKnob(export_r)
    node.addKnob(export_s)
    
    node.addKnob(nuke.Text_Knob("divider_tracker_action", "", ""))
    
    create_tracker_btn = nuke.PyScript_Knob("create_tracker_btn", "Export Tracker", "import nuke_tracker; nuke_tracker.generate_tracker_node_from_panel(nuke.thisNode())")
    create_tracker_btn.setFlag(nuke.STARTLINE)
    node.addKnob(create_tracker_btn)
    
    # 3. Roto Node Generation Tab
    roto_tab = nuke.Tab_Knob("roto_tab", "Roto")
    node.addKnob(roto_tab)
    
    divider_roto = nuke.Text_Knob("divider_roto_landmarks", "Select Contours for Roto Splines", "")
    node.addKnob(divider_roto)
    
    roto_oval = nuke.Boolean_Knob("roto_oval", "Face Oval (36 pts)", True)
    roto_lips_outer = nuke.Boolean_Knob("roto_lips_outer", "Lips Outer (20 pts)", True)
    roto_lips_inner = nuke.Boolean_Knob("roto_lips_inner", "Lips Inner (20 pts)", False)
    roto_left_eye = nuke.Boolean_Knob("roto_left_eye", "Left Eye (16 pts)", False)
    roto_right_eye = nuke.Boolean_Knob("roto_right_eye", "Right Eye (16 pts)", False)
    roto_left_eyebrow = nuke.Boolean_Knob("roto_left_eyebrow", "Left Eyebrow (10 pts)", False)
    roto_right_eyebrow = nuke.Boolean_Knob("roto_right_eyebrow", "Right Eyebrow (10 pts)", False)
    
    roto_lips_outer.setFlag(nuke.STARTLINE)
    roto_lips_inner.setFlag(nuke.STARTLINE)
    roto_left_eye.setFlag(nuke.STARTLINE)
    roto_right_eye.setFlag(nuke.STARTLINE)
    roto_left_eyebrow.setFlag(nuke.STARTLINE)
    roto_right_eyebrow.setFlag(nuke.STARTLINE)
    
    node.addKnob(roto_oval)
    node.addKnob(roto_lips_outer)
    node.addKnob(roto_lips_inner)
    node.addKnob(roto_left_eye)
    node.addKnob(roto_right_eye)
    node.addKnob(roto_left_eyebrow)
    node.addKnob(roto_right_eyebrow)
    
    node.addKnob(nuke.Text_Knob("divider_roto_action", "", ""))
    
    create_roto_btn = nuke.PyScript_Knob("create_roto_btn", "Export Roto", "import nuke_tracker; nuke_tracker.generate_roto_node_from_panel(nuke.thisNode())")
    create_roto_btn.setFlag(nuke.STARTLINE)
    node.addKnob(create_roto_btn)
    
    # Dynamic visibility callback script set on the knobChanged callback
    knob_changed_script = (
        "n = nuke.thisNode()\n"
        "k = nuke.thisKnob()\n"
        "if k.name() == 'refine_smartvectors':\n"
        "    n['anchor_stiffness'].setVisible(k.value())\n"
        "elif k.name() == 'landmark_density':\n"
        "    density = k.value()\n"
        "    is_full = ('Full' in density)\n"
        "    n['info_full_mesh'].setVisible(is_full)\n"
    )
    node['knobChanged'].setValue(knob_changed_script)
    
    # Force the first tab ('Tracking') to be the default active tab on creation
    node.setTab(0)
    
    return node


def run_tracking_on_node(node):
    """Reads options from the FaceTracker node, processes tracking,
    and saves the keyframed data. Does not auto-generate nodes.
    """
    # 1. Pipeline and Refinement Validation
    input_node = node.input(0)
    if not input_node:
        nuke.message("Please connect the Face Tracker node to an input node (e.g. Read node) first.")
        return False
        
    read_node = find_upstream_read(input_node)
    if not read_node:
        nuke.message("Could not find an upstream 'Read' node connected to this pipeline.\n"
                     "Please make sure your footage flows from a valid 'Read' node.")
        return False
        
    refine_enabled = node['refine_smartvectors'].value()
    vector_node = None
    u_channel = None
    v_channel = None
    if refine_enabled:
        vector_node = node.input(1)
        if not vector_node:
            nuke.message("SmartVector refinement is enabled but no node is connected to the 'SmartVector' input.")
            return False
        # Validate channels (automatically scan for best vector channels)
        u_channel, v_channel = find_vector_channels(vector_node)
        if not u_channel or not v_channel:
            nuke.message("The connected SmartVector node does not contain any recognizable vector channels.\n"
                         "Expected layers like 'smartvector_fwd', 'smartvector', 'forward', or 'motion' containing .u/.v or .x/.y channels.")
            return False
        
    # Retrieve resolved filename pattern (evaluates relative paths and TCL but keeps frame patterns like #### or %04d)
    try:
        input_path = nuke.filename(read_node)
    except Exception:
        input_path = read_node['file'].value()
        
    if not input_path:
        nuke.message("The upstream Read node does not contain a valid file path.")
        return False
        
    # Retrieve parameters directly from custom knobs
    start_frame = int(node['start_frame'].value())
    end_frame = int(node['end_frame'].value())
    if start_frame > end_frame:
        nuke.message("Start frame cannot be greater than end frame!")
        return False
        
    output_json = node['output_json'].value()
    if not output_json:
        nuke.message("Please specify a valid path for the output JSON file.")
        return False
        
    # Resolve all possible landmarks and contours to track everything in one go
    if not landmarks_config:
        nuke.message("Landmarks configuration could not be imported. Please verify backend/landmarks_config.py.")
        return False
        
    selected_names = []
    
    # 1. All sparse standard landmarks
    for group in landmarks_config.LANDMARK_GROUPS.values():
        selected_names.extend(group.keys())
        
    # 2. All dense contour landmarks
    for group_name, pts in landmarks_config.CONTOUR_GROUPS.items():
        selected_names.extend([f"{group_name}_{i}" for i in range(len(pts))])
        
    # 3. All full mesh landmarks
    selected_names.extend([f"Mesh_{i}" for i in range(468)])
    
    # 4. All Roto contour groups
    selected_names.extend(landmarks_config.CONTOUR_GROUPS.keys())
        
    # Filter unique list
    selected_names = list(set(selected_names))
    landmarks_str = ",".join(selected_names)
    if not landmarks_str:
        nuke.message("Please select at least one landmark or contour group to track!")
        return False
        
    # Determine immediate input dimensions for precise viewport scaling
    width = input_node.format().width()
    height = input_node.format().height()
    
    # 2. Locate Virtual Environment Python
    if sys.platform == "win32":
        python_exe = os.path.join(plugin_dir, ".venv", "Scripts", "python.exe")
    else:
        python_exe = os.path.join(plugin_dir, ".venv", "bin", "python")
        
    if not os.path.exists(python_exe):
        nuke.message(f"Virtual environment python not found at:\n{python_exe}\n\nPlease run 'install_requirements.bat' to set it up.")
        return False
        
    backend_script = os.path.join(plugin_dir, "backend", "tracker_backend.py")
    
    # 3. Compile backend parameters
    mode_val = "video" if "Video" in node['mode'].value() else "image"
    
    quality_val = node['quality'].value()
    min_det_conf = 0.5
    min_track_conf = 0.5
    
    if quality_val == "High Quality":
        min_det_conf = 0.6
        min_track_conf = 0.65
    elif quality_val == "Maximum":
        min_det_conf = 0.7
        min_track_conf = 0.8
        
    nuke_fps = 24.0
    try:
        nuke_fps = nuke.root().fps()
    except Exception:
        pass
        
    cmd = [
        python_exe,
        backend_script,
        "--input", input_path,
        "--output", output_json,
        "--start", str(start_frame),
        "--end", str(end_frame),
        "--width", str(width),
        "--height", str(height),
        "--landmarks", landmarks_str,
        "--export-type", "trackers",
        "--mode", mode_val,
        "--fps", str(nuke_fps),
        "--min-det-confidence", str(min_det_conf),
        "--min-track-confidence", str(min_track_conf)
    ]
    
    # Hide console terminal window on Windows platforms
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0 # SW_HIDE
        
    # 4. Trigger Subprocess tracking with a native Nuke progress modal
    task = nuke.ProgressTask("MediaPipe Face Tracker")
    task.setMessage("Initializing face detection engine...")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            startupinfo=startupinfo,
            bufsize=1
        )
    except Exception as e:
        nuke.message(f"Failed to start backend subprocess:\n{str(e)}")
        return False
        
    success = False
    error_logs = []
    
    while True:
        if task.isCancelled():
            process.terminate()
            nuke.message("Face tracking cancelled by user.")
            return False
            
        line = process.stdout.readline()
        if not line:
            break
            
        line = line.strip()
        print(f"[MediaPipe Backend] {line}")
        
        if "[ERROR]" in line or "Error:" in line or "Traceback" in line:
            error_logs.append(line)
            
        if line.startswith("PROGRESS:"):
            match = re.search(r'PROGRESS:\s*(\d+)%', line)
            if match:
                progress_val = int(match.group(1))
                if refine_enabled:
                    mapped_progress = int(progress_val * 0.8)
                else:
                    mapped_progress = progress_val
                task.setProgress(mapped_progress)
                task.setMessage(f"Tracking face... frames {start_frame}-{end_frame} ({progress_val}%)")
        elif line.startswith("[INFO]"):
            task.setMessage(line)
        elif line.startswith("[SUCCESS]"):
            success = True
            task.setMessage(line)
            
    process.wait()
    
    if process.returncode != 0 or not success:
        err_msg = "\n".join(error_logs[-10:]) if error_logs else "Unknown error occurred in the background process."
        nuke.message(f"Backend process failed (Exit Code: {process.returncode}):\n\n{err_msg}")
        return False
        
    # 5. SmartVector refinement phase
    if refine_enabled:
        task.setMessage("Refining tracking coordinates with SmartVectors...")
        try:
            with open(output_json, "r") as f:
                tracker_data = json.load(f)
        except Exception as e:
            nuke.message(f"Failed to read tracking JSON for refinement:\n{str(e)}")
            return False
            
        success_refine = apply_smartvector_refinement(node, tracker_data, start_frame, end_frame, u_channel, v_channel, task)
        if not success_refine:
            return False
            
        try:
            with open(output_json, "w") as f:
                json.dump(tracker_data, f, indent=2)
        except Exception as e:
            nuke.message(f"Failed to save refined JSON:\n{str(e)}")
            return False
            
    # 6. Success message - printed to the script editor to avoid blocking modal dialogs
    print("[NukeFaceTracker] Face tracking completed successfully! Switch to 'Tracker' or 'Roto' tab to export.")
    return True


def get_landmarks_bbox(tracker_data, frame, width, height, padding=50):
    """Calculates the bounding box [x_min, y_min, x_max, y_max] of all landmarks
    on a given frame, clamped to the image dimensions with a safety padding.
    """
    frame_str = str(frame)
    xs = []
    ys = []
    for track_name, frame_data in tracker_data.items():
        val = frame_data.get(frame_str)
        if val:
            if isinstance(val[0], list):
                for pt in val:
                    xs.append(pt[0])
                    ys.append(pt[1])
            else:
                xs.append(val[0])
                ys.append(val[1])
                
    if not xs or not ys:
        return [0, 0, width, height]
        
    x_min = max(0, int(min(xs) - padding))
    y_min = max(0, int(min(ys) - padding))
    x_max = min(width, int(max(xs) + padding))
    y_max = min(height, int(max(ys) + padding))
    
    # Handle collapsed or zero-size bbox
    if x_min >= x_max:
        x_min = max(0, x_min - 10)
        x_max = min(width, x_max + 10)
    if y_min >= y_max:
        y_min = max(0, y_min - 10)
        y_max = min(height, y_max + 10)
        
    return [x_min, y_min, x_max, y_max]


def apply_smartvector_refinement(node, tracker_data, start_frame, end_frame, u_channel=None, v_channel=None, task=None):
    """Applies the Spring-Anchor blending algorithm to refine MediaPipe landmark
    coordinates using local motion vectors from the connected SmartVector node.
    """
    vector_node = node.input(1)
    if not vector_node:
        return False
        
    if not u_channel or not v_channel:
        u_channel, v_channel = find_vector_channels(vector_node)
        if not u_channel or not v_channel:
            nuke.message("Could not auto-detect recognizable vector channels for refinement.")
            return False
        
    w = node['anchor_stiffness'].value()
    
    # Determine format dimensions defensively
    try:
        width = vector_node.format().width()
        height = vector_node.format().height()
    except Exception:
        try:
            width = nuke.root().format().width()
            height = nuke.root().format().height()
        except Exception:
            width = 1920
            height = 1080
    
    # Create temporary in-memory CurveTool to force evaluation of the upstream pipeline at each frame.
    # To prevent the node from appearing in the user's Node Graph (DAG) and causing visual confusion,
    # we create it INSIDE the FaceTracker group's internal DAG context (using 'with node:')
    # and connect it to the internal "SmartVector" Input node.
    force_node = None
    try:
        with node:
            internal_vector_node = node.node("SmartVector")
            if not internal_vector_node:
                internal_vector_node = vector_node
            force_node = nuke.nodes.CurveTool()
            force_node.setInput(0, internal_vector_node)
            force_node["ROI"].setValue([0, 0, width, height])
    except Exception as e:
        print(f"[SmartVector Refine] Warning: Failed to create hidden in-memory CurveTool: {str(e)}")
    
    # Store original frame to restore later
    orig_frame = nuke.frame()
    
    total_frames = end_frame - start_frame + 1
    previous_refined = {}
    
    # Initialize previous_refined at the first frame of tracking
    first_frame_str = str(start_frame)
    for track_name, frame_data in tracker_data.items():
        if first_frame_str in frame_data:
            val = frame_data[first_frame_str]
            if isinstance(val[0], list):
                # Roto group: list of points
                previous_refined[track_name] = [list(pt) for pt in val]
            else:
                # Tracker point
                previous_refined[track_name] = list(val)
                
    # Chronological loop
    for f_idx, frame in enumerate(range(start_frame + 1, end_frame + 1)):
        if task and task.isCancelled():
            if force_node:
                try:
                    nuke.delete(force_node)
                except Exception:
                    pass
            nuke.frame(orig_frame)
            nuke.message("SmartVector refinement cancelled by user.")
            return False
            
        # Force evaluate upstream vector node at frame f-1
        if force_node:
            try:
                # Calculate dynamic bounding box of all landmarks on frame f-1 to restrict evaluation area
                bbox = get_landmarks_bbox(tracker_data, frame - 1, width, height)
                force_node["ROI"].setValue(bbox)
                nuke.execute(force_node, frame - 1, frame - 1)
            except Exception as e:
                pass
            
        # Evaluate upstream vectors at frame f-1 to compute motion to frame f
        nuke.frame(frame - 1)
        frame_str = str(frame)
        
        for track_name, frame_data in tracker_data.items():
            if track_name not in previous_refined:
                if frame_str in frame_data:
                    val = frame_data[frame_str]
                    if isinstance(val[0], list):
                        previous_refined[track_name] = [list(pt) for pt in val]
                    else:
                        previous_refined[track_name] = list(val)
                continue
                
            prev_val = previous_refined[track_name]
            
            if isinstance(prev_val[0], list):
                # Roto group: list of points
                refined_pts = []
                mp_pts = frame_data.get(frame_str)
                
                for idx, pt in enumerate(prev_val):
                    x_prev, y_prev = pt[0], pt[1]
                    
                    # Sample motion vectors with standard pixel center offset
                    u = vector_node.sample(u_channel, x_prev + 0.5, y_prev + 0.5)
                    v = vector_node.sample(v_channel, x_prev + 0.5, y_prev + 0.5)
                    
                    if frame < start_frame + 6 and idx == 0:
                        print(f"[SmartVector Refine] Frame {frame} - Roto '{track_name}' sampled motion: ({u:.4f}, {v:.4f})")
                    
                    # Advection
                    x_motion = x_prev + u
                    y_motion = y_prev + v
                    
                    # Correction
                    if mp_pts and idx < len(mp_pts):
                        x_mp, y_mp = mp_pts[idx][0], mp_pts[idx][1]
                        x_ref = (1.0 - w) * x_motion + w * x_mp
                        y_ref = (1.0 - w) * y_motion + w * y_mp
                    else:
                        x_ref = x_motion
                        y_ref = y_motion
                        
                    refined_pts.append([round(x_ref, 3), round(y_ref, 3)])
                    
                frame_data[frame_str] = refined_pts
                previous_refined[track_name] = refined_pts
                
            else:
                # Tracker point
                x_prev, y_prev = prev_val[0], prev_val[1]
                
                u = vector_node.sample(u_channel, x_prev + 0.5, y_prev + 0.5)
                v = vector_node.sample(v_channel, x_prev + 0.5, y_prev + 0.5)
                
                if frame < start_frame + 6:
                    print(f"[SmartVector Refine] Frame {frame} - Tracker '{track_name}' sampled motion: ({u:.4f}, {v:.4f})")
                
                x_motion = x_prev + u
                y_motion = y_prev + v
                
                mp_pt = frame_data.get(frame_str)
                if mp_pt:
                    x_mp, y_mp = mp_pt[0], mp_pt[1]
                    x_ref = (1.0 - w) * x_motion + w * x_mp
                    y_ref = (1.0 - w) * y_motion + w * y_mp
                else:
                    x_ref = x_motion
                    y_ref = y_motion
                    
                refined_pt = [round(x_ref, 3), round(y_ref, 3)]
                
                frame_data[frame_str] = refined_pt
                previous_refined[track_name] = refined_pt
                
        if task:
            progress_pct = 80 + int((f_idx + 1) / float(total_frames) * 20)
            task.setProgress(progress_pct)
            task.setMessage(f"Refining coordinates... frame {frame} of {end_frame} ({progress_pct}%)")
            
    # Cleanup temporary force node
    if force_node:
        try:
            nuke.delete(force_node)
        except Exception:
            pass
            
    nuke.frame(orig_frame)
    return True


def interpolate_missing_frames(frame_data, start_frame, end_frame):
    """Fills in missing frames in frame_data from start_frame to end_frame using linear interpolation
    for gaps and constant extrapolation for missing frames at the boundaries.
    Supports both single points [x, y] and lists of points [[x1, y1], [x2, y2], ...].
    """
    sorted_existing = sorted([int(f) for f in frame_data.keys() if str(f) in frame_data])
    if not sorted_existing:
        return {} # No data at all to interpolate
        
    new_frame_data = {}
    
    # Helper to check if a value is a list of points
    first_val = frame_data[str(sorted_existing[0])]
    is_list_of_points = isinstance(first_val[0], list)
    
    for f in range(start_frame, end_frame + 1):
        f_str = str(f)
        if f_str in frame_data:
            # Already exists, just copy
            new_frame_data[f_str] = frame_data[f_str]
        else:
            # Needs interpolation or extrapolation
            # Find the closest lower frame and closest higher frame
            lower_frames = [lf for lf in sorted_existing if lf < f]
            higher_frames = [hf for hf in sorted_existing if hf > f]
            
            if not lower_frames:
                # Extrapolate from the first available frame (constant extrapolation)
                closest_f = sorted_existing[0]
                new_frame_data[f_str] = frame_data[str(closest_f)]
            elif not higher_frames:
                # Extrapolate from the last available frame (constant extrapolation)
                closest_f = sorted_existing[-1]
                new_frame_data[f_str] = frame_data[str(closest_f)]
            else:
                # Interpolate between lower and higher
                f_prev = lower_frames[-1]
                f_next = higher_frames[0]
                val_prev = frame_data[str(f_prev)]
                val_next = frame_data[str(f_next)]
                
                # Interpolation factor
                t = (f - f_prev) / float(f_next - f_prev)
                
                if is_list_of_points:
                    # Interpolate list of points
                    interp_pts = []
                    for p_prev, p_next in zip(val_prev, val_next):
                        x = p_prev[0] + t * (p_next[0] - p_prev[0])
                        y = p_prev[1] + t * (p_next[1] - p_prev[1])
                        interp_pts.append([round(x, 3), round(y, 3)])
                    new_frame_data[f_str] = interp_pts
                else:
                    # Interpolate single point
                    x = val_prev[0] + t * (val_next[0] - val_prev[0])
                    y = val_prev[1] + t * (val_next[1] - val_prev[1])
                    new_frame_data[f_str] = [round(x, 3), round(y, 3)]
                    
    return new_frame_data


def generate_tracker_node(parent_node, json_path, width, height):
    """Loads JSON tracking results and serializes them into a keyframed Nuke Tracker4 node."""
    if not os.path.exists(json_path):
        nuke.message(f"Output JSON file not found:\n{json_path}")
        return False
        
    try:
        with open(json_path, "r") as f:
            tracker_data = json.load(f)
    except Exception as e:
        nuke.message(f"Failed to parse JSON file:\n{str(e)}")
        return False
        
    # Resolve selected landmarks based on CURRENT options in the properties panel
    density = parent_node['landmark_density'].value()
    selected_landmarks = []
    
    if "Sparse" in density:
        if parent_node['track_nose'].value():
            selected_landmarks.extend(landmarks_config.LANDMARK_GROUPS["Nose"].keys())
        if parent_node['track_eyes'].value():
            selected_landmarks.extend(landmarks_config.LANDMARK_GROUPS["Eyes"].keys())
        if parent_node['track_eyebrows'].value():
            selected_landmarks.extend(landmarks_config.LANDMARK_GROUPS["Eyebrows"].keys())
        if parent_node['track_mouth'].value():
            selected_landmarks.extend(landmarks_config.LANDMARK_GROUPS["Mouth"].keys())
        if parent_node['track_contour'].value():
            selected_landmarks.extend(landmarks_config.LANDMARK_GROUPS["Face Shape"].keys())
    elif "Dense" in density:
        if parent_node['track_nose'].value():
            selected_landmarks.extend(landmarks_config.LANDMARK_GROUPS["Nose"].keys())
        if parent_node['track_eyes'].value():
            selected_landmarks.extend([f"Left_Eye_{i}" for i in range(len(landmarks_config.CONTOUR_GROUPS["Left_Eye"]))])
            selected_landmarks.extend([f"Right_Eye_{i}" for i in range(len(landmarks_config.CONTOUR_GROUPS["Right_Eye"]))])
        if parent_node['track_eyebrows'].value():
            selected_landmarks.extend([f"Left_Eyebrow_{i}" for i in range(len(landmarks_config.CONTOUR_GROUPS["Left_Eyebrow"]))])
            selected_landmarks.extend([f"Right_Eyebrow_{i}" for i in range(len(landmarks_config.CONTOUR_GROUPS["Right_Eyebrow"]))])
        if parent_node['track_mouth'].value():
            selected_landmarks.extend([f"Lips_Outer_{i}" for i in range(len(landmarks_config.CONTOUR_GROUPS["Lips_Outer"]))])
            selected_landmarks.extend([f"Lips_Inner_{i}" for i in range(len(landmarks_config.CONTOUR_GROUPS["Lips_Inner"]))])
        if parent_node['track_contour'].value():
            selected_landmarks.extend([f"Face_Oval_{i}" for i in range(len(landmarks_config.CONTOUR_GROUPS["Face_Oval"]))])
    elif "Full" in density:
        selected_landmarks.extend([f"Mesh_{i}" for i in range(468)])

    try:
        start_frame = int(parent_node['start_frame'].value())
        end_frame = int(parent_node['end_frame'].value())
    except Exception:
        start_frame = 1
        end_frame = 100

    active_tracks = {}
    for name, data in tracker_data.items():
        if name in selected_landmarks and data:
            first_val = list(data.values())[0]
            if isinstance(first_val[0], (int, float)):
                interpolated_data = interpolate_missing_frames(data, start_frame, end_frame)
                if interpolated_data:
                    active_tracks[name] = interpolated_data
                
    if not active_tracks:
        nuke.message("Please select at least one tracking landmark to export, or ensure you have tracked first.")
        return False
        
    # Deselect all nodes to cleanly connect the new Tracker4 node to our custom node
    for n in nuke.allNodes():
        n.setSelected(False)
        
    parent_node.setSelected(True)
    
    # Create the Tracker4 Node in the parent canvas context
    parent_group = parent_node.parent()
    with parent_group:
        tracker = nuke.createNode('Tracker4')
    tracker.setName(f"Tracker_Face_{parent_node.name()}")
    
    # Define Tracker4 database columns
    column_definitions = (
        "{\n"
        " { 5 1 20 enable e 1 }\n"
        " { 3 1 75 name name 1 }\n"
        " { 2 1 58 track_x track_x 1 }\n"
        " { 2 1 58 track_y track_y 1 }\n"
        " { 2 1 63 offset_x offset_x 1 }\n"
        " { 2 1 63 offset_y offset_y 1 }\n"
        " { 4 1 27 T T 1 }\n"
        " { 4 1 27 R R 1 }\n"
        " { 4 1 27 S S 1 }\n"
        " { 2 0 45 error error 1 }\n"
        " { 1 1 0 error_min error_min 1 }\n"
        " { 1 1 0 error_max error_max 1 }\n"
        " { 1 1 0 pattern_x pattern_x 1 }\n"
        " { 1 1 0 pattern_y pattern_y 1 }\n"
        " { 1 1 0 pattern_r pattern_r 1 }\n"
        " { 1 1 0 pattern_t pattern_t 1 }\n"
        " { 1 1 0 search_x search_x 1 }\n"
        " { 1 1 0 search_y search_y 1 }\n"
        " { 1 1 0 search_r search_r 1 }\n"
        " { 1 1 0 search_t search_t 1 }\n"
        " { 2 1 0 key_track key_track 1 }\n"
        " { 2 1 0 key_search_x key_search_x 1 }\n"
        " { 2 1 0 key_search_y key_search_y 1 }\n"
        " { 2 1 0 key_search_r key_search_r 1 }\n"
        " { 2 1 0 key_search_t key_search_t 1 }\n"
        " { 2 1 0 key_track_x key_track_x 1 }\n"
        " { 2 1 0 key_track_y key_track_y 1 }\n"
        " { 2 1 0 key_track_r key_track_r 1 }\n"
        " { 2 1 0 key_track_t key_track_t 1 }\n"
        " { 2 1 0 key_centre_offset_x key_centre_offset_x 1 }\n"
        " { 2 1 0 key_centre_offset_y key_centre_offset_y 1 }\n"
        "}"
    )
    
    tracker_strings = []
    num_tracks = len(active_tracks)
    
    t_val = 1 if parent_node['export_t'].value() else 0
    r_val = 1 if parent_node['export_r'].value() else 0
    s_val = 1 if parent_node['export_s'].value() else 0

    for point_name, frame_data in active_tracks.items():
        sorted_frames = sorted([int(f) for f in frame_data.keys()])
        if not sorted_frames:
            continue
            
        first_frame = sorted_frames[0]
        
        x_curve_parts = []
        y_curve_parts = []
        for frame in sorted_frames:
            coords = frame_data[str(frame)]
            x_curve_parts.append(f"x{frame} {coords[0]}")
            y_curve_parts.append(f"x{frame} {coords[1]}")
            
        x_curve_str = " ".join(x_curve_parts)
        y_curve_str = " ".join(y_curve_parts)
        
        tracker_str = (
            f"{{ {{curve K x{first_frame} 1}} \"{point_name}\" "
            f"{{curve {x_curve_str}}} {{curve {y_curve_str}}} "
            f"{{curve K x{first_frame} 0}} {{curve K x{first_frame} 0}} {t_val} {r_val} {s_val} "
            f"{{curve x{first_frame} 0}} 1 0 -15 -15 15 15 -10 -10 10 10 "
            f"{{}} {{}} {{}} {{}} {{}} {{}} {{}} {{}} {{}} {{}} {{}} }}"
        )
        tracker_strings.append(tracker_str)
        
    tracker_strings_combined = "{\n" + "\n".join(tracker_strings) + "\n}"
    from_script_str = f"{{ 1 31 {num_tracks} }} \n{column_definitions} \n{tracker_strings_combined}\n"
    
    try:
        tracker['tracks'].fromScript(from_script_str)
    except Exception as e:
        nuke.message(f"Failed to populate Tracker4 node tracks using fromScript:\n{str(e)}")
        return False
        
    parent_node.setSelected(True)
    tracker.setSelected(True)
    
    return True


def generate_roto_node(parent_node, json_path, width, height):
    """Loads JSON contour tracking results and generates a native, animated closed Roto node."""
    if not os.path.exists(json_path):
        nuke.message(f"Output JSON file not found:\n{json_path}")
        return False
        
    try:
        with open(json_path, "r") as f:
            roto_data = json.load(f)
    except Exception as e:
        nuke.message(f"Failed to parse JSON file:\n{str(e)}")
        return False
        
    # Resolve selected contours based on CURRENT options in the properties panel
    selected_contours = []
    if parent_node['roto_oval'].value():
        selected_contours.append("Face_Oval")
    if parent_node['roto_lips_outer'].value():
        selected_contours.append("Lips_Outer")
    if parent_node['roto_lips_inner'].value():
        selected_contours.append("Lips_Inner")
    if parent_node['roto_left_eye'].value():
        selected_contours.append("Left_Eye")
    if parent_node['roto_right_eye'].value():
        selected_contours.append("Right_Eye")
    if parent_node['roto_left_eyebrow'].value():
        selected_contours.append("Left_Eyebrow")
    if parent_node['roto_right_eyebrow'].value():
        selected_contours.append("Right_Eyebrow")

    try:
        start_frame = int(parent_node['start_frame'].value())
        end_frame = int(parent_node['end_frame'].value())
    except Exception:
        start_frame = 1
        end_frame = 100

    active_contours = {}
    for name, data in roto_data.items():
        if name in selected_contours and data:
            first_val = list(data.values())[0]
            if isinstance(first_val[0], list):
                interpolated_data = interpolate_missing_frames(data, start_frame, end_frame)
                if interpolated_data:
                    active_contours[name] = interpolated_data
                
    if not active_contours:
        nuke.message("Please select at least one contour group to export, or ensure you have tracked first.")
        return False
        
    try:
        import nuke.rotopaint as rp
    except ImportError:
        nuke.message("Failed to import nuke.rotopaint. Cannot generate Roto node.")
        return False
        
    # Deselect all nodes to cleanly connect the new Roto node to our custom node
    for n in nuke.allNodes():
        n.setSelected(False)
        
    parent_node.setSelected(True)
    
    # Create the Roto Node in the parent canvas context
    parent_group = parent_node.parent()
    with parent_group:
        roto_node = nuke.createNode('Roto')
    roto_node.setName(f"Roto_Face_{parent_node.name()}")
    
    curves_knob = roto_node['curves']
    root_layer = curves_knob.rootLayer
    
    # Process each active contour group
    for group_name, frame_data in active_contours.items():
        sorted_frames = sorted([int(f) for f in frame_data.keys()])
        if not sorted_frames:
            continue
            
        first_frame = sorted_frames[0]
        first_points = frame_data[str(first_frame)]
        num_points = len(first_points)
        
        # 1. Create the Shape object
        shape = rp.Shape(curves_knob)
        shape.name = group_name
        
        # Set the shape to be closed using the low-level _curvelib API
        try:
            import _curvelib
            shape.getAttributes().set(0, _curvelib.AnimAttributes.kClosedAttribute, 1.0)
        except Exception as e:
            print(f"[NukeFaceTracker] Failed to set closed attribute via _curvelib: {e}")
        
        # 2. Add control points initialized at first frame coordinates
        for coords in first_points:
            cp = rp.AnimControlPoint(coords[0], coords[1])
            shape.append(cp)
            
        # Add the shape to the root layer first so its curves are registered with the knob
        root_layer.append(shape)
        
        # 3. Animate each control point over the available frames
        for frame in sorted_frames:
            points = frame_data[str(frame)]
            if len(points) != num_points:
                continue # Safety skip
                
            for idx, coords in enumerate(points):
                shape_point = shape[idx]
                anim_point = shape_point.center
                
                # Set coordinate keyframes using AnimCurve.addKey
                x_curve = anim_point.getPositionAnimCurve(0, "")
                y_curve = anim_point.getPositionAnimCurve(1, "")
                x_curve.addKey(frame, coords[0])
                y_curve.addKey(frame, coords[1])
                
    # Force Nuke to evaluate and refresh the curves in the viewer
    curves_knob.changed()
    
    parent_node.setSelected(True)
    roto_node.setSelected(True)
    
    return True


def generate_tracker_node_from_panel(node):
    """Callback triggered from the Tracker tab. Loads JSON and builds the Tracker4 node."""
    json_path = node['output_json'].value()
    if not json_path:
        nuke.message("Please specify a valid output JSON file path first.")
        return False
        
    input_node = node.input(0)
    if input_node:
        try:
            width = input_node.format().width()
            height = input_node.format().height()
        except Exception:
            width = nuke.root().format().width()
            height = nuke.root().format().height()
    else:
        width = nuke.root().format().width()
        height = nuke.root().format().height()
        
    return generate_tracker_node(node, json_path, width, height)


def generate_roto_node_from_panel(node):
    """Callback triggered from the Roto tab. Loads JSON and builds the Roto node."""
    json_path = node['output_json'].value()
    if not json_path:
        nuke.message("Please specify a valid output JSON file path first.")
        return False
        
    input_node = node.input(0)
    if input_node:
        try:
            width = input_node.format().width()
            height = input_node.format().height()
        except Exception:
            width = nuke.root().format().width()
            height = nuke.root().format().height()
    else:
        width = nuke.root().format().width()
        height = nuke.root().format().height()
        
    return generate_roto_node(node, json_path, width, height)

