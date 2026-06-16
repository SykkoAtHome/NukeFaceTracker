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
    # Create NoOp Node which serves as pass-through
    node = nuke.createNode('NoOp')
    node.setName("FaceTracker", True)
    
    # Give it a nice, distinctive orange/copper tile color for identification in DAG
    node['tile_color'].setValue(0xff8c00ff)
    
    # Create the Custom Properties tab
    tab_knob = nuke.Tab_Knob("face_tracker_tab", "Face Tracker")
    node.addKnob(tab_knob)
    

    
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
    
    export_type_knob = nuke.Enumeration_Knob("export_type", "Export Type", ["Tracker4 Node", "Roto Node (Masks)"])
    export_type_knob.setTooltip("Select whether to generate a keyframed Tracker4 node for standard point tracking, or a native Roto node with closed, animated Bezier mask splines.")
    node.addKnob(export_type_knob)
    
    # Landmarks Section (Standard Trackers)
    node.addKnob(nuke.Text_Knob("divider_landmarks", "Select Landmarks to Track", ""))
    
    track_nose = nuke.Boolean_Knob("track_nose", "Nose (Tip, Bridge, Alar)", True)
    track_eyes = nuke.Boolean_Knob("track_eyes", "Eyes (Corners, Eyelids)", True)
    track_eyebrows = nuke.Boolean_Knob("track_eyebrows", "Eyebrows (Left & Right)", False)
    track_mouth = nuke.Boolean_Knob("track_mouth", "Mouth (Lip contours & Corners)", False)
    track_contour = nuke.Boolean_Knob("track_contour", "Face Contour (Chin, Forehead, Cheeks)", False)
    
    track_eyes.setFlag(nuke.STARTLINE)
    track_eyebrows.setFlag(nuke.STARTLINE)
    track_mouth.setFlag(nuke.STARTLINE)
    track_contour.setFlag(nuke.STARTLINE)
    
    node.addKnob(track_nose)
    node.addKnob(track_eyes)
    node.addKnob(track_eyebrows)
    node.addKnob(track_mouth)
    node.addKnob(track_contour)
    
    # Landmarks Section (Roto Contours - Hidden by default)
    divider_roto = nuke.Text_Knob("divider_roto_landmarks", "Select Contours to Track", "")
    node.addKnob(divider_roto)
    divider_roto.setVisible(False)
    
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
    
    for r_knob in [roto_oval, roto_lips_outer, roto_lips_inner, roto_left_eye, roto_right_eye, roto_left_eyebrow, roto_right_eyebrow]:
        node.addKnob(r_knob)
        r_knob.setVisible(False)
        
    # Dynamic visibility callback script set on the knobChanged callback
    knob_changed_script = (
        "n = nuke.thisNode()\n"
        "k = nuke.thisKnob()\n"
        "if k.name() == 'export_type':\n"
        "    is_roto = (k.value() == 'Roto Node (Masks)')\n"
        "    n['divider_landmarks'].setVisible(not is_roto)\n"
        "    n['track_nose'].setVisible(not is_roto)\n"
        "    n['track_eyes'].setVisible(not is_roto)\n"
        "    n['track_eyebrows'].setVisible(not is_roto)\n"
        "    n['track_mouth'].setVisible(not is_roto)\n"
        "    n['track_contour'].setVisible(not is_roto)\n"
        "    n['divider_roto_landmarks'].setVisible(is_roto)\n"
        "    n['roto_oval'].setVisible(is_roto)\n"
        "    n['roto_lips_outer'].setVisible(is_roto)\n"
        "    n['roto_lips_inner'].setVisible(is_roto)\n"
        "    n['roto_left_eye'].setVisible(is_roto)\n"
        "    n['roto_right_eye'].setVisible(is_roto)\n"
        "    n['roto_left_eyebrow'].setVisible(is_roto)\n"
        "    n['roto_right_eyebrow'].setVisible(is_roto)\n"
    )
    node['knobChanged'].setValue(knob_changed_script)
    
    # Output File Section
    node.addKnob(nuke.Text_Knob("divider_output", "Output Options", ""))
    
    # Construct path cleanly to use forward slashes
    temp_json = os.path.join(plugin_dir, "temp_tracker_data.json").replace("\\", "/")
    output_json_knob = nuke.File_Knob("output_json", "Output JSON File")
    output_json_knob.setValue(temp_json)
    node.addKnob(output_json_knob)
    
    node.addKnob(nuke.Text_Knob("divider_action", "", ""))
    
    # Main action button
    track_btn = nuke.PyScript_Knob("track_btn", "<b>Track Face</b>", "import nuke_tracker; nuke_tracker.run_tracking_on_node(nuke.thisNode())")
    track_btn.setFlag(nuke.STARTLINE)
    node.addKnob(track_btn)
    
    return node


def run_tracking_on_node(node):
    """Reads options from the FaceTracker node, processes tracking,

    and generates the keyframed Tracker4 node.
    """
    # 1. Pipeline Validation
    input_node = node.input(0)
    if not input_node:
        nuke.message("Please connect the Face Tracker node to an input node (e.g. Read node) first.")
        return False
        
    read_node = find_upstream_read(input_node)
    if not read_node:
        nuke.message("Could not find an upstream 'Read' node connected to this pipeline.\n"
                     "Please make sure your footage flows from a valid 'Read' node.")
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
        
    # Resolve selected landmarks or contours based on export type
    if not landmarks_config:
        nuke.message("Landmarks configuration could not be imported. Please verify backend/landmarks_config.py.")
        return False
        
    is_roto_mode = (node['export_type'].value() == "Roto Node (Masks)")
    
    selected_names = []
    if is_roto_mode:
        if node['roto_oval'].value():
            selected_names.append("Face_Oval")
        if node['roto_lips_outer'].value():
            selected_names.append("Lips_Outer")
        if node['roto_lips_inner'].value():
            selected_names.append("Lips_Inner")
        if node['roto_left_eye'].value():
            selected_names.append("Left_Eye")
        if node['roto_right_eye'].value():
            selected_names.append("Right_Eye")
        if node['roto_left_eyebrow'].value():
            selected_names.append("Left_Eyebrow")
        if node['roto_right_eyebrow'].value():
            selected_names.append("Right_Eyebrow")
    else:
        if node['track_nose'].value():
            selected_names.extend(landmarks_config.LANDMARK_GROUPS["Nose"].keys())
        if node['track_eyes'].value():
            selected_names.extend(landmarks_config.LANDMARK_GROUPS["Eyes"].keys())
        if node['track_eyebrows'].value():
            selected_names.extend(landmarks_config.LANDMARK_GROUPS["Eyebrows"].keys())
        if node['track_mouth'].value():
            selected_names.extend(landmarks_config.LANDMARK_GROUPS["Mouth"].keys())
        if node['track_contour'].value():
            selected_names.extend(landmarks_config.LANDMARK_GROUPS["Face Shape"].keys())
        
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
        "--export-type", "roto" if is_roto_mode else "trackers",
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
                task.setProgress(progress_val)
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
        
    # 5. Populate and connect standard Tracker4 node or Roto node
    if is_roto_mode:
        return generate_roto_node(node, output_json, width, height)
    else:
        return generate_tracker_node(node, output_json, width, height)


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
        
    active_tracks = {name: data for name, data in tracker_data.items() if data}
    if not active_tracks:
        nuke.message("Face detected but failed to track any landmarks in the specified frame range.")
        return False
        
    # Deselect all nodes to cleanly connect the new Tracker4 node to our custom node
    for n in nuke.allNodes():
        n.setSelected(False)
        
    parent_node.setSelected(True)
    
    # Create the Tracker4 Node
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
            f"{{curve K x{first_frame} 0}} {{curve K x{first_frame} 0}} 1 0 0 "
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
    
    nuke.message(f"Success!\nGenerated Tracker4 node '{tracker.name()}' downstream from '{parent_node.name()}' with {len(active_tracks)} track points.")
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
        
    active_contours = {name: data for name, data in roto_data.items() if data}
    if not active_contours:
        nuke.message("Face detected but failed to track any contours in the specified frame range.")
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
    
    # Create the Roto Node
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
        shape.closed = True
        
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
                anim_point.x.addKey(frame, coords[0])
                anim_point.y.addKey(frame, coords[1])
                
    # Force Nuke to evaluate and refresh the curves in the viewer
    curves_knob.changed()
    
    parent_node.setSelected(True)
    roto_node.setSelected(True)
    
    nuke.message(f"Success!\nGenerated Roto node '{roto_node.name()}' downstream from '{parent_node.name()}' with {len(active_contours)} closed animated shapes.")
    return True
