import os
import sys
import json
import re
import subprocess
import tempfile
import shutil
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

try:
    import tracker_backend
except ImportError:
    tracker_backend = None


def find_upstream_read(node):
    """Recursively traverses upstream following the active image pipeline to find the
    first node with a 'file' knob (e.g., Read, Write, DeepRead) to ensure we always
    use the active image stream.
    """
    if not node:
        return None

    # If the node has a 'file' knob, we've found our image source leaf
    if node.knob('file') is not None:
        return node

    # Check for Switch/Dissolve nodes which select a specific active input
    if node.Class() in ('Switch', 'Dissolve') and node.knob('which') is not None:
        try:
            active_index = int(node['which'].evaluate())
            if 0 <= active_index < node.inputs():
                active_input = node.input(active_index)
                if active_input:
                    result = find_upstream_read(active_input)
                    if result:
                        return result
        except Exception as e:
            print("[FaceTracker] Warning evaluating switch node '{}': {}".format(node.name(), str(e)))

    # For standard nodes, follow the primary input (input 0 / B-pipe in Nuke) first
    if node.inputs() > 0:
        primary_input = node.input(0)
        if primary_input:
            result = find_upstream_read(primary_input)
            if result:
                return result

        # If input 0 is not connected, check other inputs as fallback (e.g., Merge with only A connected)
        for i in range(1, node.inputs()):
            other_input = node.input(i)
            if other_input:
                result = find_upstream_read(other_input)
                if result:
                    return result

    return None


def _resolve_output_json_path(node):
    """Pure resolver: returns the output JSON path for the node without mutating state."""
    # Check if we should write results to a custom file
    write_to_file = node['write_to_file'].value() if 'write_to_file' in node.knobs() else False

    if not write_to_file:
        # Default to a safe, stable path inside Nuke's native temp directory
        try:
            temp_dir = nuke.temp_dir()
        except Exception:
            temp_dir = tempfile.gettempdir()
        return os.path.join(temp_dir, f"facetracker_{node.name()}_data.json").replace("\\", "/")

    current_val = node['output_json'].value()
    if not current_val or "temp_tracker_data" in current_val:
        directory = os.path.dirname(current_val) if current_val else plugin_dir
        return os.path.join(directory, "temp_tracker_data_{}.json".format(node.name())).replace("\\", "/")
    return current_val


def _ensure_unique_output_json(node):
    """Resolves a unique output JSON path and writes it back to the node when stale/empty.

    Only the custom-file (write_to_file) branch mutates the knob, matching the
    historical behavior of the original get_unique_output_json_path helper.
    """
    write_to_file = node['write_to_file'].value() if 'write_to_file' in node.knobs() else False
    if not write_to_file:
        # Non-custom path never mutates the knob.
        return _resolve_output_json_path(node)

    unique_path = _resolve_output_json_path(node)
    current_val = node['output_json'].value()
    if current_val != unique_path:
        node['output_json'].setValue(unique_path)
    return unique_path


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



def _resolve_input_frame_range(input_node):
    """Resolve the effective frame range of an input node.

    Cascades: input first/last -> if degenerate find_upstream_read -> if still 0
    use root first/last. Returns (start, end).
    """
    start = int(input_node.firstFrame())
    end = int(input_node.lastFrame())

    # If the frame range is default/invalid or single-frame, try to find an upstream Read node
    # to get the true sequence range
    if (start == end and start <= 1) or (start == 0 and end == 0):
        read_node = find_upstream_read(input_node)
        if read_node:
            start = int(read_node.firstFrame())
            end = int(read_node.lastFrame())

    # Fallback to root settings if still default/invalid
    if start == end and start == 0:
        start = int(nuke.root().firstFrame())
        end = int(nuke.root().lastFrame())

    return start, end


def set_range_to_input(node):
    """Callback function to sync the node's frame range to its active upstream input."""
    input_node = node.input(0)
    if not input_node:
        nuke.message("No input node connected to this Face Tracker.\nPlease connect it to a Read node pipeline.")
        return

    start, end = _resolve_input_frame_range(input_node)

    node['start_frame'].setValue(start)
    node['end_frame'].setValue(end)


def get_active_tracker_parts(node):
    active_parts = []
    knob_to_part = (
        ("track_nose", "Nose"),
        ("track_eyes", "Eyes"),
        ("track_eyebrows", "Eyebrows"),
        ("track_mouth", "Mouth"),
        ("track_contour", "Face Shape"),
    )

    for knob_name, part_name in knob_to_part:
        try:
            if node[knob_name].value():
                active_parts.append(part_name)
        except Exception:
            pass

    return active_parts


def get_roto_contour_knob_specs():
    # landmarks_config.ROTO_CONTOUR_KNOB_SPECS is the single source of truth. If the
    # backend import failed (landmarks_config is None) the plugin is non-functional
    # anyway; the direct dereference fails cleanly, matching the rest of this module.
    return landmarks_config.ROTO_CONTOUR_KNOB_SPECS


ROTO_CONTOUR_OPTIONS = tuple(
    (knob_name, contour_name)
    for knob_name, contour_name, _, _ in get_roto_contour_knob_specs()
)

def get_roto_export_contour_names():
    return [contour_name for _, contour_name in ROTO_CONTOUR_OPTIONS]


def get_selected_roto_contours(node):
    selected_contours = []

    for knob_name, contour_name in ROTO_CONTOUR_OPTIONS:
        try:
            if node[knob_name].value():
                selected_contours.append(contour_name)
        except Exception:
            pass

    return selected_contours


def get_names_to_track_for_analysis(node):
    # get_landmarks_for_analysis() is defined unconditionally in landmarks_config and
    # takes no arguments; the import-guard (landmarks_config is None) is handled by
    # run_tracking_on_node before this function is called.
    selected_names = list(landmarks_config.get_landmarks_for_analysis().keys())

    # Roto export choices can be changed after tracking, so record every contour
    # exposed by the Roto tab during analysis and filter only during export.
    selected_names.extend(get_roto_export_contour_names())

    return list(dict.fromkeys(selected_names))


def _build_tracking_tab(node, start_frame, end_frame):
    """Build the 'Analyze Face' tracking settings tab on the node (mutates node)."""
    tracking_tab = nuke.Tab_Knob("tracking_tab", "Analyze Face")
    node.addKnob(tracking_tab)

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

    backtrack_knob = nuke.Boolean_Knob("backtrack", "Backtrack", False)
    backtrack_knob.setTooltip("Runs tracking in both forward and backward directions, averaging the detected coordinates. This also helps patch frames where tracking might have failed in one of the directions.")
    node.addKnob(backtrack_knob)

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

    write_to_file_knob = nuke.Boolean_Knob("write_to_file", "Write Results to File", False)
    write_to_file_knob.setTooltip("If enabled, saves the final tracking JSON data to a custom path of your choice.\nOtherwise, the tracking data is saved in Nuke's temporary directory automatically.")
    node.addKnob(write_to_file_knob)

    # Construct path cleanly to use forward slashes
    temp_json = os.path.join(plugin_dir, "temp_tracker_data.json").replace("\\", "/")
    output_json_knob = nuke.File_Knob("output_json", "Output JSON File")
    output_json_knob.setValue(temp_json)
    node.addKnob(output_json_knob)
    output_json_knob.setVisible(False)

    node.addKnob(nuke.Text_Knob("divider_action", "", ""))

    # Main action button
    track_btn = nuke.PyScript_Knob("track_btn", "Track Face", "import nuke_tracker; nuke_tracker.run_tracking_on_node(nuke.thisNode())")
    track_btn.setFlag(nuke.STARTLINE)
    node.addKnob(track_btn)


def _build_tracker_tab(node):
    """Build the 'Tracker' node generation tab on the node (mutates node)."""
    tracker_tab = nuke.Tab_Knob("tracker_tab", "Tracker")
    node.addKnob(tracker_tab)

    density_labels = getattr(
        landmarks_config,
        "TRACKER_DENSITY_LABELS",
        ["Sparse (Standard)", "Dense (Feature Contours)", "Surface (Face Regions)", "Full (Entire Mesh & Iris - 478 pts)"]
    )
    density_knob = nuke.Enumeration_Knob("landmark_density", "Landmark Density", density_labels)
    density_knob.setTooltip("Sparse: standard facial features.\nDense: ordered feature contours for eyes, brows, lips, nose, and face oval.\nSurface: broader facial regions including cheeks, forehead, jaw, and feature surfaces.\nFull: high-fidelity mesh topology (up to 478 points).")
    node.addKnob(density_knob)

    divider_landmarks = nuke.Text_Knob("divider_landmarks", "Select Landmarks to Track", "")
    node.addKnob(divider_landmarks)

    track_nose = nuke.Boolean_Knob("track_nose", "Nose (Tip, Bridge, Alar, Nostrils)", True)
    track_eyes = nuke.Boolean_Knob("track_eyes", "Eyes & Iris (Corners, Eyelids, Iris Centers)", True)
    track_eyebrows = nuke.Boolean_Knob("track_eyebrows", "Eyebrows (Left & Right)", False)
    track_mouth = nuke.Boolean_Knob("track_mouth", "Mouth (Lip contours & Corners)", True)
    track_contour = nuke.Boolean_Knob("track_contour", "Face Contour (Oval, Chin, Forehead, Cheeks)", True)

    track_eyes.setFlag(nuke.STARTLINE)
    track_eyebrows.setFlag(nuke.STARTLINE)
    track_mouth.setFlag(nuke.STARTLINE)
    track_contour.setFlag(nuke.STARTLINE)

    node.addKnob(track_nose)
    node.addKnob(track_eyes)
    node.addKnob(track_eyebrows)
    node.addKnob(track_mouth)
    node.addKnob(track_contour)

    info_full_mesh = nuke.Text_Knob("info_full_mesh", "", "<span style='color:#ffa500'><b>Warning:</b> Tracking all 478 landmarks will create 478 point tracks.<br>This may slow down Foundry Nuke's viewport and node properties panel.</span>")
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

    export_cornerpin_tracker = nuke.Boolean_Knob("export_cornerpin_tracker", "Corner Pin", False)
    export_cornerpin_tracker.setTooltip("Export 4 calculated corner pin tracking points (Corner_BL, Corner_BR, Corner_TR, Corner_TL) defining the facial bounding box.")
    export_cornerpin_tracker.setFlag(nuke.STARTLINE)
    node.addKnob(export_cornerpin_tracker)

    node.addKnob(nuke.Text_Knob("divider_tracker_action", "", ""))

    create_tracker_btn = nuke.PyScript_Knob("create_tracker_btn", "Export Tracker", "import nuke_tracker; nuke_tracker.generate_tracker_node_from_panel(nuke.thisNode())")
    create_tracker_btn.setFlag(nuke.STARTLINE)
    node.addKnob(create_tracker_btn)


def _build_roto_tab(node):
    """Build the 'Roto' node generation tab on the node (mutates node)."""
    roto_tab = nuke.Tab_Knob("roto_tab", "Roto")
    node.addKnob(roto_tab)

    divider_roto = nuke.Text_Knob("divider_roto_landmarks", "Select Contours for Roto Splines", "")
    node.addKnob(divider_roto)

    for idx, (knob_name, _contour_name, label, default_value) in enumerate(get_roto_contour_knob_specs()):
        roto_knob = nuke.Boolean_Knob(knob_name, label, default_value)
        if idx % 2 == 0:
            roto_knob.setFlag(nuke.STARTLINE)
        else:
            roto_knob.clearFlag(nuke.STARTLINE)
        node.addKnob(roto_knob)

    node.addKnob(nuke.Text_Knob("divider_roto_action", "", ""))

    # Bezier Spline Toggle (Cusped Bezier)
    roto_bezier = nuke.Boolean_Knob("roto_bezier", "Cusped Bezier", False)
    roto_bezier.setFlag(nuke.STARTLINE)
    roto_bezier.setTooltip("If enabled, export Roto shapes as sharp linear/cusped polylines instead of smooth Bezier curves.")
    node.addKnob(roto_bezier)

    create_roto_btn = nuke.PyScript_Knob("create_roto_btn", "Export Roto", "import nuke_tracker; nuke_tracker.generate_roto_node_from_panel(nuke.thisNode())")
    create_roto_btn.setFlag(nuke.STARTLINE)
    node.addKnob(create_roto_btn)


def _build_cornerpin_tab(node):
    """Build the 'CornerPin' node generation tab on the node (mutates node)."""
    cornerpin_tab = nuke.Tab_Knob("cornerpin_tab", "CornerPin")
    node.addKnob(cornerpin_tab)

    node.addKnob(nuke.Text_Knob("divider_cornerpin", "CornerPin Export Settings", ""))

    ref_frame_knob = nuke.Int_Knob("ref_frame", "Reference Frame")
    ref_frame_knob.setValue(int(nuke.frame()))
    node.addKnob(ref_frame_knob)

    current_frame_btn = nuke.PyScript_Knob("set_ref_current", "Current Frame", "import nuke_tracker; nuke_tracker.set_ref_frame_to_current(nuke.thisNode())")
    node.addKnob(current_frame_btn)

    node.addKnob(nuke.Text_Knob("divider_cornerpin_action", "", ""))

    create_cornerpin_btn = nuke.PyScript_Knob("create_cornerpin_btn", "Export CornerPin", "import nuke_tracker; nuke_tracker.generate_cornerpin_node_from_panel(nuke.thisNode())")
    create_cornerpin_btn.setFlag(nuke.STARTLINE)
    node.addKnob(create_cornerpin_btn)


def _build_knob_changed_script():
    """Return the multi-line knobChanged callback script that drives dynamic knob
    visibility (anchor_stiffness / info_full_mesh / output_json)."""
    return (
        "n = nuke.thisNode()\n"
        "k = nuke.thisKnob()\n"
        "if k.name() == 'refine_smartvectors':\n"
        "    n['anchor_stiffness'].setVisible(k.value())\n"
        "elif k.name() == 'landmark_density':\n"
        "    density = k.value()\n"
        "    is_full = ('Full' in density)\n"
        "    n['info_full_mesh'].setVisible(is_full)\n"
        "elif k.name() == 'write_to_file':\n"
        "    n['output_json'].setVisible(k.value())\n"
    )


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

    # Resolve initial ranges based on selected nodes or project
    start_frame = 1
    end_frame = 100

    input_node = node.input(0)
    if input_node:
        start_frame, end_frame = _resolve_input_frame_range(input_node)

    # Build the four tabs in order, then attach the dynamic knobChanged script.
    _build_tracking_tab(node, start_frame, end_frame)
    _build_tracker_tab(node)
    _build_roto_tab(node)
    _build_cornerpin_tab(node)

    # Dynamic visibility callback script set on the knobChanged callback
    node['knobChanged'].setValue(_build_knob_changed_script())

    # Force the first tab ('Tracking') to be the default active tab on creation
    node.setTab(0)

    # Initialize the output JSON path to be unique from the start
    _ensure_unique_output_json(node)

    return node


def _validate_tracking_inputs(node):
    """Section 1: Pipeline and Refinement Validation.

    Validates the FaceTracker node's inputs and collects every parameter the
    tracking run needs. Returns a params dict on success, or None after showing
    a nuke.message explaining the failure.
    """
    input_node = node.input(0)
    if not input_node:
        nuke.message("Please connect the Face Tracker node to an input node first.")
        return None

    refine_enabled = node['refine_smartvectors'].value()
    backtrack_enabled = node['backtrack'].value() if 'backtrack' in node.knobs() else False
    vector_node = None
    u_channel = None
    v_channel = None
    if refine_enabled:
        vector_node = node.input(1)
        if not vector_node:
            nuke.message("SmartVector refinement is enabled but no node is connected to the 'SmartVector' input.")
            return None
        # Validate channels (automatically scan for best vector channels)
        u_channel, v_channel = find_vector_channels(vector_node)
        if not u_channel or not v_channel:
            nuke.message("The connected SmartVector node does not contain any recognizable vector channels.\n"
                         "Expected layers like 'smartvector_fwd', 'smartvector', 'forward', or 'motion' containing .u/.v or .x/.y channels.")
            return None

    # Retrieve parameters directly from custom knobs
    start_frame = int(node['start_frame'].value())
    end_frame = int(node['end_frame'].value())
    if start_frame > end_frame:
        nuke.message("Start frame cannot be greater than end frame!")
        return None

    output_json = _resolve_output_json_path(node)
    if not output_json:
        nuke.message("Please specify a valid path for the output JSON file.")
        return None

    # Resolve all possible landmarks and contours to track everything in one go
    if not landmarks_config:
        nuke.message("Landmarks configuration could not be imported. Please verify backend/landmarks_config.py.")
        return None

    selected_names = get_names_to_track_for_analysis(node)
    landmarks_str = ",".join(selected_names)
    if not landmarks_str:
        nuke.message("Please select at least one landmark or contour group to track!")
        return None

    # Determine immediate input dimensions for precise viewport scaling
    width = input_node.format().width()
    height = input_node.format().height()

    return {
        'node': node,
        'input_node': input_node,
        'refine_enabled': refine_enabled,
        'backtrack_enabled': backtrack_enabled,
        'vector_node': vector_node,
        'u_channel': u_channel,
        'v_channel': v_channel,
        'start_frame': start_frame,
        'end_frame': end_frame,
        'output_json': output_json,
        'landmarks_str': landmarks_str,
        'width': width,
        'height': height,
    }


def _locate_venv_python():
    """Section 2: Locate Virtual Environment Python.

    Returns the venv python executable path, or None after showing a
    nuke.message when the interpreter is missing.
    """
    if sys.platform == "win32":
        python_exe = os.path.join(plugin_dir, ".venv", "Scripts", "python.exe")
    else:
        python_exe = os.path.join(plugin_dir, ".venv", "bin", "python")

    if not os.path.exists(python_exe):
        nuke.message(f"Virtual environment python not found at:\n{python_exe}\n\nPlease run 'install_requirements.bat' to set it up.")
        return None
    return python_exe


def _build_backend_command(params):
    """Section 3: Compile backend parameters.

    Builds the base argv list for the tracker_backend subprocess from the
    validated params dict. Reads mode/quality/fps off params['node'] and uses
    params['python_exe'] / params['temp_file_pattern'] for the invocation.
    """
    node = params['node']
    backend_script = os.path.join(plugin_dir, "backend", "tracker_backend.py")

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

    return [
        params['python_exe'],
        backend_script,
        "--input", params['temp_file_pattern'],
        "--start", str(params['start_frame']),
        "--end", str(params['end_frame']),
        "--width", str(params['width']),
        "--height", str(params['height']),
        "--landmarks", params['landmarks_str'],
        "--export-type", "trackers",
        "--mode", mode_val,
        "--fps", str(nuke_fps),
        "--min-det-confidence", str(min_det_conf),
        "--min-track-confidence", str(min_track_conf),
    ]


def _render_input_stream(node, start_frame, end_frame, temp_file_pattern):
    """Section 4: Set up temporary render directory (Write node + synchronous render).

    Creates a temporary Write node inside the FaceTracker Group context, points
    it at the JPEG temp render pattern, and synchronously renders the active
    image stream. Returns the Write node so the caller can delete it in its
    finally block. Raises on missing internal Source node.
    """
    # Create temporary Write node inside the Group context to render the active stream
    with node:
        internal_source = node.node("Source")
        if not internal_source:
            raise ValueError("Internal 'Source' input node not found within FaceTracker Group.")

        write_node = nuke.nodes.Write()
        write_node.setInput(0, internal_source)
        write_node['file'].setValue(temp_file_pattern)
        write_node['file_type'].setValue('jpeg')

        # Set JPEG quality to high to preserve fine details for landmark detection
        if 'quality' in write_node.knobs():
            write_node['quality'].setValue(0.9)
        elif '_jpeg_quality' in write_node.knobs():
            write_node['_jpeg_quality'].setValue(0.9)

    # Synchronously execute the temporary render in Nuke
    nuke.execute(write_node, start_frame, end_frame)
    return write_node


def _run_tracking_passes(passes_to_run, task, start_frame, end_frame):
    """Run the backend subprocess passes sequentially, parsing progress output.

    Keeps the N3 non-blocking stdout reader (daemon thread + queue) so the Nuke
    Cancel button stays responsive even when the backend stalls. Returns True
    when every pass succeeds, False (after nuke.message) on failure or cancel.
    """
    # Hide console terminal window on Windows platforms
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE

    # Execute each pass sequentially
    for p_info in passes_to_run:
        task.setMessage(f"Initializing face detection engine ({p_info['name']} pass)...")

        try:
            process = subprocess.Popen(
                p_info["cmd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                startupinfo=startupinfo,
                bufsize=1
            )
        except Exception as e:
            nuke.message(f"Failed to start backend subprocess for {p_info['name']} pass:\n{str(e)}")
            return False

        error_logs = []
        pass_success = False

        # N3: Read subprocess stdout from a daemon thread into a queue so the
        # Nuke main thread can poll with a short timeout. This keeps the Cancel
        # button responsive even when the backend stalls and produces no output
        # (a blocking readline() would otherwise freeze Nuke's UI indefinitely).
        import threading
        import queue as _queue

        stdout_q = _queue.Queue()

        def _stdout_reader(stream, q):
            try:
                for line in iter(stream.readline, ""):
                    q.put(line)
            except Exception:
                pass
            finally:
                # Sentinel: stdout closed (EOF) or reader failed.
                q.put(None)

        reader_thread = threading.Thread(target=_stdout_reader, args=(process.stdout, stdout_q))
        reader_thread.daemon = True
        reader_thread.start()

        while True:
            if task.isCancelled():
                # B2: terminate, then wait for the child to actually exit so it
                # cannot keep holding the output JSON files open when the finally
                # block runs shutil.rmtree(temp_dir). On Windows TerminateProcess
                # is async, so we must wait; escalate to kill if it hangs.
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                nuke.message("Face tracking cancelled by user.")
                return False

            try:
                line = stdout_q.get(timeout=0.1)
            except _queue.Empty:
                line = None

            if line is None:
                # Sentinel: reader thread hit EOF (or failed). If we already
                # consumed all output this is the normal end-of-stream signal.
                break

            line = line.strip()
            print(f"[MediaPipe Backend {p_info['name']}] {line}")

            if "[ERROR]" in line or "Error:" in line or "Traceback" in line:
                error_logs.append(line)

            if line.startswith("PROGRESS:"):
                match = re.search(r'PROGRESS:\s*(\d+)%', line)
                if match:
                    progress_val = int(match.group(1))
                    mapped_progress = int(p_info["offset"] * 100 + progress_val * p_info["weight"])
                    task.setProgress(mapped_progress)
                    task.setMessage(f"Tracking face ({p_info['name']})... frames {start_frame}-{end_frame} ({progress_val}%)")
            elif line.startswith("[INFO]"):
                task.setMessage(line)
            elif line.startswith("[SUCCESS]"):
                pass_success = True
                task.setMessage(line)

        process.wait()

        if process.returncode != 0 or not pass_success:
            err_msg = "\n".join(error_logs[-10:]) if error_logs else "Unknown error occurred in the background process."
            nuke.message(f"Backend {p_info['name']} pass failed (Exit Code: {process.returncode}):\n\n{err_msg}")
            return False

    return True


def _merge_backtrack_passes(output_fwd, output_bwd, output_json, task):
    """Merge forward/backward tracking JSON outputs via tracker_backend.merge_results.

    Returns True on success, False (after nuke.message) on any read/merge/write
    failure. The merged result is written to output_json.
    """
    task.setMessage("Merging forward and backward tracking results...")

    try:
        with open(output_fwd, "r") as f:
            fwd_data = json.load(f)
    except Exception as e:
        nuke.message(f"Failed to read forward tracking JSON for merging:\n{str(e)}")
        return False

    try:
        with open(output_bwd, "r") as f:
            bwd_data = json.load(f)
    except Exception as e:
        nuke.message(f"Failed to read backward tracking JSON for merging:\n{str(e)}")
        return False

    if not tracker_backend or not landmarks_config:
        nuke.message("Failed to reference backend modules (tracker_backend or landmarks_config) for merging.")
        return False

    try:
        contours_to_track = dict(landmarks_config.CONTOUR_GROUPS)
        landmarks_to_track = landmarks_config.get_landmarks_for_analysis()

        merged_data = tracker_backend.merge_results(
            fwd_data,
            bwd_data,
            contours_to_track,
            landmarks_to_track
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        nuke.message(f"Error during results merging:\n{str(e)}")
        return False

    try:
        os.makedirs(os.path.dirname(output_json), exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(merged_data, f, indent=2)
    except Exception as e:
        nuke.message(f"Failed to save merged tracking JSON:\n{str(e)}")
        return False

    return True


def run_tracking_on_node(node):
    """Reads options from the FaceTracker node, processes tracking on a
    temporarily rendered JPEG stream of the exact input pixel flow (supporting
    all upstream grades, warps, stabilization, and switch nodes), and saves
    the keyframed data.
    """
    # 1. Pipeline and Refinement Validation
    params = _validate_tracking_inputs(node)
    if params is None:
        return False

    # 2. Locate Virtual Environment Python
    python_exe = _locate_venv_python()
    if python_exe is None:
        return False
    params['python_exe'] = python_exe

    # 4. Set up temporary render directory for active image stream caching.
    # Dynamically query Nuke's native temp directory to respect custom fast scratch disks.
    try:
        nuke_temp = nuke.temp_dir()
    except Exception:
        nuke_temp = None

    import time
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    temp_dir = tempfile.mkdtemp(dir=nuke_temp, prefix=f"nuke_facetracker_{timestamp}_")
    temp_file_pattern = os.path.join(temp_dir, "frame_%04d.jpg").replace("\\", "/")
    params['temp_file_pattern'] = temp_file_pattern

    # Trigger Subprocess tracking with a native Nuke progress modal
    task = nuke.ProgressTask("MediaPipe Face Tracker")
    task.setMessage("Rendering active image stream to temporary cache...")

    start_frame = params['start_frame']
    end_frame = params['end_frame']
    output_json = params['output_json']
    backtrack_enabled = params['backtrack_enabled']
    refine_enabled = params['refine_enabled']

    output_fwd = None
    output_bwd = None
    write_node = None
    success = False

    try:
        write_node = _render_input_stream(node, start_frame, end_frame, temp_file_pattern)

        # Setup output paths for dual-pass tracking if backtrack is enabled (stored inside temp_dir)
        output_fwd = os.path.join(temp_dir, "output_fwd.json").replace("\\", "/")
        output_bwd = os.path.join(temp_dir, "output_bwd.json").replace("\\", "/")

        # 3. Compile backend parameters
        base_cmd = _build_backend_command(params)

        # Compile list of tracking passes to run
        passes_to_run = []
        if backtrack_enabled:
            weight = 0.4 if refine_enabled else 0.5
            passes_to_run.append({
                "cmd": base_cmd + ["--output", output_fwd],
                "name": "Forward",
                "weight": weight,
                "offset": 0.0,
                "output": output_fwd
            })
            passes_to_run.append({
                "cmd": base_cmd + ["--output", output_bwd, "--backward"],
                "name": "Backward",
                "weight": weight,
                "offset": weight,
                "output": output_bwd
            })
        else:
            weight = 0.8 if refine_enabled else 1.0
            passes_to_run.append({
                "cmd": base_cmd + ["--output", output_json],
                "name": "Forward",
                "weight": weight,
                "offset": 0.0,
                "output": output_json
            })

        # Execute passes sequentially
        if not _run_tracking_passes(passes_to_run, task, start_frame, end_frame):
            return False

        # If backtracking was enabled, merge the two JSON outputs
        if backtrack_enabled:
            if not _merge_backtrack_passes(output_fwd, output_bwd, output_json, task):
                return False

        success = True

        # 5. SmartVector refinement phase
        if refine_enabled:
            task.setMessage("Refining tracking coordinates with SmartVectors...")
            try:
                with open(output_json, "r") as f:
                    tracker_data = json.load(f)
            except Exception as e:
                nuke.message(f"Failed to read tracking JSON for refinement:\n{str(e)}")
                return False

            success_refine = apply_smartvector_refinement(node, tracker_data, start_frame, end_frame, params['u_channel'], params['v_channel'], task)
            if not success_refine:
                return False

            try:
                with open(output_json, "w") as f:
                    json.dump(tracker_data, f, indent=2)
            except Exception as e:
                nuke.message(f"Failed to save refined JSON:\n{str(e)}")
                return False

    finally:
        # Cleanup temporary Write node inside the Group context
        if write_node:
            try:
                with node:
                    nuke.delete(write_node)
            except Exception:
                pass
        # Cleanup temporary directory and cached JPEG files
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

        # Cleanup temporary forward/backward JSON files if they exist
        for tmp_file in [output_fwd, output_bwd]:
            if tmp_file and os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass

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


def _init_or_get_prev(track_name, frame_data, frame_str):
    """Initialize a previous_refined entry from raw tracker data at frame_str.

    Returns a deep-ish copy of the frame value (list of points or single point),
    or None when frame_str is not present in frame_data.
    """
    if frame_str not in frame_data:
        return None
    val = frame_data[frame_str]
    if isinstance(val[0], list):
        # Roto group: list of points
        return [list(pt) for pt in val]
    # Tracker point
    return list(val)


def _refine_point(prev_xy, mp_xy, u, v, w):
    """Spring-anchor blend: advect prev by motion (u, v), then pull toward the
    MediaPipe anchor mp_xy by stiffness w. Returns [x_ref, y_ref] (rounded)."""
    x_prev, y_prev = prev_xy[0], prev_xy[1]
    x_motion = x_prev + u
    y_motion = y_prev + v
    if mp_xy is not None:
        x_mp, y_mp = mp_xy[0], mp_xy[1]
        x_ref = (1.0 - w) * x_motion + w * x_mp
        y_ref = (1.0 - w) * y_motion + w * y_mp
    else:
        x_ref = x_motion
        y_ref = y_motion
    return [round(x_ref, 3), round(y_ref, 3)]


def _refine_point_list(prev_pts, mp_pts, vector_node, u_channel, v_channel, w,
                       track_name=None, frame=None, start_frame=None):
    """Refine a contour (list of points) sampling motion vectors per point."""
    refined_pts = []
    for idx, pt in enumerate(prev_pts):
        x_prev, y_prev = pt[0], pt[1]
        u = vector_node.sample(u_channel, x_prev + 0.5, y_prev + 0.5)
        v = vector_node.sample(v_channel, x_prev + 0.5, y_prev + 0.5)

        if frame is not None and start_frame is not None and frame < start_frame + 6 and idx == 0:
            print(f"[SmartVector Refine] Frame {frame} - Roto '{track_name}' sampled motion: ({u:.4f}, {v:.4f})")

        mp_xy = mp_pts[idx] if (mp_pts and idx < len(mp_pts)) else None
        refined_pts.append(_refine_point(pt, mp_xy, u, v, w))

    return refined_pts


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
        init_val = _init_or_get_prev(track_name, frame_data, first_frame_str)
        if init_val is not None:
            previous_refined[track_name] = init_val

    # B3: Track whether force_node has already been deleted by an earlier cleanup
    # path (cancel/success) so the finally below does not double-delete it.
    force_node_deleted = False

    # Chronological loop
    try:
        for f_idx, frame in enumerate(range(start_frame + 1, end_frame + 1)):
            if task and task.isCancelled():
                if force_node and not force_node_deleted:
                    try:
                        nuke.delete(force_node)
                        force_node_deleted = True
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
                    init_val = _init_or_get_prev(track_name, frame_data, frame_str)
                    if init_val is not None:
                        previous_refined[track_name] = init_val
                    continue

                prev_val = previous_refined[track_name]

                if isinstance(prev_val[0], list):
                    # Roto group: list of points
                    mp_pts = frame_data.get(frame_str)
                    refined_pts = _refine_point_list(
                        prev_val, mp_pts, vector_node, u_channel, v_channel, w,
                        track_name=track_name, frame=frame, start_frame=start_frame,
                    )
                    frame_data[frame_str] = refined_pts
                    previous_refined[track_name] = refined_pts

                else:
                    # Tracker point
                    x_prev, y_prev = prev_val[0], prev_val[1]

                    u = vector_node.sample(u_channel, x_prev + 0.5, y_prev + 0.5)
                    v = vector_node.sample(v_channel, x_prev + 0.5, y_prev + 0.5)

                    if frame < start_frame + 6:
                        print(f"[SmartVector Refine] Frame {frame} - Tracker '{track_name}' sampled motion: ({u:.4f}, {v:.4f})")

                    mp_pt = frame_data.get(frame_str)
                    refined_pt = _refine_point(prev_val, mp_pt, u, v, w)

                    frame_data[frame_str] = refined_pt
                    previous_refined[track_name] = refined_pt

            if task:
                progress_pct = 80 + int((f_idx + 1) / float(total_frames) * 20)
                task.setProgress(progress_pct)
                task.setMessage(f"Refining coordinates... frame {frame} of {end_frame} ({progress_pct}%)")

        # Cleanup temporary force node
        if force_node and not force_node_deleted:
            try:
                nuke.delete(force_node)
                force_node_deleted = True
            except Exception:
                pass

        nuke.frame(orig_frame)
        return True
    finally:
        # B3: On ANY exception (or early return paths above) make sure the
        # temporary CurveTool force_node is removed and the current frame is
        # restored, so we never orphan force_node in the user's group DAG or
        # leave the timeline stuck. Do not swallow the exception — re-raise.
        if force_node and not force_node_deleted:
            try:
                nuke.delete(force_node)
            except Exception:
                pass
        try:
            nuke.frame(orig_frame)
        except Exception:
            pass


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


def calculate_cornerpin_data(tracker_data, start_frame, end_frame, width=1920, height=1080):
    """Calculates the 4 corner points [BL, BR, TR, TL] of the oriented bounding box of ALL landmarks
    for each frame from start_frame to end_frame, taking face rotation into account.
    First interpolates all available landmarks to ensure continuity.
    Returns:
        dict: mapping frame_number (int) -> [[bl_x, bl_y], [br_x, br_y], [tr_x, tr_y], [tl_x, tl_y]]
    """
    import math
    interpolated_tracks = {}
    for name, data in tracker_data.items():
        if not data:
            continue
        # interpolate_missing_frames detects the single-point vs list-of-points
        # format internally, so both contour groups and single landmarks share
        # one code path here.
        interpolated_tracks[name] = interpolate_missing_frames(data, start_frame, end_frame)

    bbox_per_frame = {}
    for frame in range(start_frame, end_frame + 1):
        f_str = str(frame)
        pts = []
        for name, data in interpolated_tracks.items():
            val = data.get(f_str)
            if val:
                if isinstance(val[0], list):
                    for pt in val:
                        pts.append(pt)
                else:
                    pts.append(val)

        if pts:
            # Calculate rotation angle based on eye line orientation
            theta = 0.0
            right_inner = interpolated_tracks.get("Right_Eye_Inner", {}).get(f_str)
            right_outer = interpolated_tracks.get("Right_Eye_Outer", {}).get(f_str)
            left_inner = interpolated_tracks.get("Left_Eye_Inner", {}).get(f_str)
            left_outer = interpolated_tracks.get("Left_Eye_Outer", {}).get(f_str)

            if right_inner and right_outer and left_inner and left_outer:
                right_eye = [(right_inner[0] + right_outer[0]) / 2.0, (right_inner[1] + right_outer[1]) / 2.0]
                left_eye = [(left_inner[0] + left_outer[0]) / 2.0, (left_inner[1] + left_outer[1]) / 2.0]
                dx = left_eye[0] - right_eye[0]
                dy = left_eye[1] - right_eye[1]
                theta = math.atan2(dy, dx)

            # Compute center of the face
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)

            # Rotate all points around center by -theta to align face horizontally
            cos_t = math.cos(-theta)
            sin_t = math.sin(-theta)
            rotated_pts = []
            for x, y in pts:
                dx = x - cx
                dy = y - cy
                rx = cx + dx * cos_t - dy * sin_t
                ry = cy + dx * sin_t + dy * cos_t
                rotated_pts.append([rx, ry])

            # Find AABB in rotated space
            r_xs = [p[0] for p in rotated_pts]
            r_ys = [p[1] for p in rotated_pts]
            x_min_rot = min(r_xs)
            y_min_rot = min(r_ys)
            x_max_rot = max(r_xs)
            y_max_rot = max(r_ys)

            # Define corners in rotated space: BL, BR, TR, TL
            corners_rot = [
                [x_min_rot, y_min_rot],
                [x_max_rot, y_min_rot],
                [x_max_rot, y_max_rot],
                [x_min_rot, y_max_rot]
            ]

            # Rotate corners back to image space by +theta
            cos_back = math.cos(theta)
            sin_back = math.sin(theta)
            corners_orig = []
            for rx, ry in corners_rot:
                dx = rx - cx
                dy = ry - cy
                ox = cx + dx * cos_back - dy * sin_back
                oy = cy + dx * sin_back + dy * cos_back
                corners_orig.append([round(ox, 3), round(oy, 3)])

            bbox_per_frame[frame] = corners_orig
        else:
            bbox_per_frame[frame] = [[0, 0], [width, 0], [width, height], [0, height]]

    return bbox_per_frame


def _load_tracker_json(json_path):
    """Load a tracker JSON file.

    Returns (data, None) on success or (None, error_msg) when the file is
    missing or cannot be parsed. Callers are responsible for presenting the
    error_msg to the user via nuke.message and returning False.
    """
    if not os.path.exists(json_path):
        return None, f"Output JSON file not found:\n{json_path}"
    try:
        with open(json_path, "r") as f:
            return json.load(f), None
    except Exception as e:
        return None, f"Failed to parse JSON file:\n{str(e)}"


def generate_cornerpin_node(parent_node, json_path, width, height):
    """Loads JSON tracking results, calculates bounding boxes, and generates an animated CornerPin2D node."""
    tracker_data, err = _load_tracker_json(json_path)
    if err is not None:
        nuke.message(err)
        return False

    try:
        start_frame = int(parent_node['start_frame'].value())
        end_frame = int(parent_node['end_frame'].value())
        ref_frame = int(parent_node['ref_frame'].value())
    except Exception:
        start_frame = 1
        end_frame = 100
        ref_frame = 1

    # Calculate corner pin data per frame (returns BL, BR, TR, TL points per frame)
    bbox_per_frame = calculate_cornerpin_data(tracker_data, start_frame, end_frame, width, height)

    # Resolve bounding box on the reference frame (clamped to available range)
    ref_clamped = max(start_frame, min(end_frame, ref_frame))
    ref_bbox = bbox_per_frame.get(ref_clamped, [[0, 0], [width, 0], [width, height], [0, height]])

    # N4: Resolve the parent group BEFORE deselecting, then deselect inside that
    # group so nodes nested within the FaceTracker's parent are deselected too.
    parent_group = parent_node.parent()

    # Deselect all nodes to cleanly connect the new CornerPin2D node
    for n in nuke.allNodes(parent_group):
        n.setSelected(False)

    parent_node.setSelected(True)

    # Create the CornerPin2D Node in the parent canvas context
    with parent_group:
        cornerpin = nuke.createNode('CornerPin2D')
    cornerpin.setName(f"CornerPin_Face_{parent_node.name()}")

    # Set 'to' knobs (constant, represent coordinates at reference frame)
    cornerpin['to1'].setValue(ref_bbox[0]) # BL
    cornerpin['to2'].setValue(ref_bbox[1]) # BR
    cornerpin['to3'].setValue(ref_bbox[2]) # TR
    cornerpin['to4'].setValue(ref_bbox[3]) # TL

    # Enable animation on 'from' knobs
    for i in range(1, 5):
        cornerpin[f'from{i}'].setAnimated()

    # Populate keyframes on 'from' knobs for each frame
    for frame, corners in bbox_per_frame.items():
        # corners is [BL, BR, TR, TL] where each is [x, y]
        cornerpin['from1'].setValueAt(corners[0][0], frame, 0) # BL x
        cornerpin['from1'].setValueAt(corners[0][1], frame, 1) # BL y

        cornerpin['from2'].setValueAt(corners[1][0], frame, 0) # BR x
        cornerpin['from2'].setValueAt(corners[1][1], frame, 1) # BR y

        cornerpin['from3'].setValueAt(corners[2][0], frame, 0) # TR x
        cornerpin['from3'].setValueAt(corners[2][1], frame, 1) # TR y

        cornerpin['from4'].setValueAt(corners[3][0], frame, 0) # TL x
        cornerpin['from4'].setValueAt(corners[3][1], frame, 1) # TL y

    # Set the label on CornerPin to remind the user of the reference frame
    cornerpin['label'].setValue(f"Ref Frame: {ref_frame}")

    parent_node.setSelected(True)
    cornerpin.setSelected(True)
    return True


def _is_tracker_point_value(value):
    return (
        isinstance(value, (list, tuple))
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    )


def _get_contour_point_spec(point_name):
    if not landmarks_config:
        return None, None

    # landmarks_config.resolve_contour_point parses the GroupName_N convention and
    # returns (group_name, idx_in_group) where idx_in_group is the 0-based position
    # within the group's point list -- exactly the per-frame contour track index.
    resolved = landmarks_config.resolve_contour_point(point_name)
    if resolved is None:
        return None, None
    return resolved


def _extract_contour_point_track(contour_data, point_index):
    point_track = {}

    for frame, points in contour_data.items():
        if not isinstance(points, (list, tuple)) or point_index >= len(points):
            continue

        coords = points[point_index]
        if _is_tracker_point_value(coords):
            point_track[frame] = coords

    return point_track


def _resolve_active_tracker_tracks(tracker_data, selected_landmarks):
    active_tracks = {}

    for name in selected_landmarks:
        data = tracker_data.get(name)
        if data:
            first_val = next(iter(data.values()), None)
            if _is_tracker_point_value(first_val):
                active_tracks[name] = data
                continue

        group_name, point_index = _get_contour_point_spec(name)
        if group_name is None:
            continue

        contour_data = tracker_data.get(group_name)
        if not contour_data:
            continue

        point_track = _extract_contour_point_track(contour_data, point_index)
        if point_track:
            active_tracks[name] = point_track

    return active_tracks


def _dedupe_landmark_names_by_index(resolved_landmarks):
    selected_names = []
    seen_indices = set()

    for name, landmark_index in resolved_landmarks.items():
        if landmark_index in seen_indices:
            continue

        selected_names.append(name)
        seen_indices.add(landmark_index)

    return selected_names


# Tracker4 database column schema. Hoisted out of generate_tracker_node so the
# generator body stays focused on track serialization.
TRACKER4_COLUMN_DEFINITIONS = (
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


def generate_tracker_node(parent_node, json_path, width, height):
    """Loads JSON tracking results and serializes them into a keyframed Nuke Tracker4 node."""
    tracker_data, err = _load_tracker_json(json_path)
    if err is not None:
        nuke.message(err)
        return False

    # Resolve selected landmarks based on CURRENT options in the properties panel
    density = parent_node['landmark_density'].value()

    active_parts = get_active_tracker_parts(parent_node)
    resolved_landmarks = landmarks_config.get_landmarks_for_density(density, active_parts)
    selected_landmarks = _dedupe_landmark_names_by_index(resolved_landmarks)

    try:
        start_frame = int(parent_node['start_frame'].value())
        end_frame = int(parent_node['end_frame'].value())
    except Exception:
        start_frame = 1
        end_frame = 100

    resolved_tracks = _resolve_active_tracker_tracks(tracker_data, selected_landmarks)
    active_tracks = {}
    for name, data in resolved_tracks.items():
        interpolated_data = interpolate_missing_frames(data, start_frame, end_frame)
        if interpolated_data:
            active_tracks[name] = interpolated_data

    # Inject corner pin tracker points if requested
    if parent_node['export_cornerpin_tracker'].value():
        bbox_per_frame = calculate_cornerpin_data(tracker_data, start_frame, end_frame, width, height)

        # Build 4 separate tracking datasets
        corner_bl = {}
        corner_br = {}
        corner_tr = {}
        corner_tl = {}

        for frame, corners in bbox_per_frame.items():
            f_str = str(frame)
            corner_bl[f_str] = corners[0] # BL [x, y]
            corner_br[f_str] = corners[1] # BR [x, y]
            corner_tr[f_str] = corners[2] # TR [x, y]
            corner_tl[f_str] = corners[3] # TL [x, y]

        active_tracks["Corner_BL"] = corner_bl
        active_tracks["Corner_BR"] = corner_br
        active_tracks["Corner_TR"] = corner_tr
        active_tracks["Corner_TL"] = corner_tl
    if not active_tracks:
        nuke.message("Please select at least one tracking landmark to export, or ensure you have tracked first.")
        return False

    # N4: Resolve the parent group BEFORE deselecting, then deselect inside that
    # group so nodes nested within the FaceTracker's parent are deselected too.
    parent_group = parent_node.parent()

    # Deselect all nodes to cleanly connect the new Tracker4 node to our custom node
    for n in nuke.allNodes(parent_group):
        n.setSelected(False)

    parent_node.setSelected(True)

    # Create the Tracker4 Node in the parent canvas context
    with parent_group:
        tracker = nuke.createNode('Tracker4')
    tracker.setName(f"Tracker_Face_{parent_node.name()}")

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
    from_script_str = f"{{ 1 31 {num_tracks} }} \n{TRACKER4_COLUMN_DEFINITIONS} \n{tracker_strings_combined}\n"

    try:
        tracker['tracks'].fromScript(from_script_str)
    except Exception as e:
        nuke.message(f"Failed to populate Tracker4 node tracks using fromScript:\n{str(e)}")
        return False

    # N2: fromScript can silently produce empty/corrupt tracks without raising.
    # Validate that the actual track count matches what we built. In real Nuke
    # the tracks knob value is a sized list; we only validate when the accessor
    # returns an actual sequence so an unexpected value type does not produce a
    # false negative.
    try:
        actual_tracks = tracker['tracks'].value()
    except Exception:
        actual_tracks = None
    if isinstance(actual_tracks, (list, tuple)):
        actual_count = len(actual_tracks)
        if actual_count != num_tracks:
            nuke.message(
                f"Tracker4 track population failed validation: expected {num_tracks} "
                f"tracks but {actual_count} were created. fromScript may have produced "
                f"empty or corrupt tracks. Please retry the export."
            )
            return False

    parent_node.setSelected(True)
    tracker.setSelected(True)

    return True


def _get_keyable_anim_point(shape_point, attr_names):
    """Returns the first point-like attribute that supports Nuke position curves."""
    for attr_name in attr_names:
        try:
            anim_point = getattr(shape_point, attr_name)
        except Exception:
            continue

        if callable(getattr(anim_point, "getPositionAnimCurve", None)):
            return anim_point

    return None


def _add_position_key(anim_point, frame, x_value, y_value):
    x_curve = anim_point.getPositionAnimCurve(0, "")
    y_curve = anim_point.getPositionAnimCurve(1, "")
    x_curve.addKey(frame, x_value)
    y_curve.addKey(frame, y_value)


def _calculate_closed_bezier_tangent(points, idx, tension=0.25):
    prev_coords = points[(idx - 1) % len(points)]
    next_coords = points[(idx + 1) % len(points)]
    return (
        (next_coords[0] - prev_coords[0]) * tension,
        (next_coords[1] - prev_coords[1]) * tension,
    )


def generate_roto_node(parent_node, json_path, width, height):
    """Loads JSON contour tracking results and generates a native, animated closed Roto node."""
    roto_data, err = _load_tracker_json(json_path)
    if err is not None:
        nuke.message(err)
        return False

    # Resolve selected contours based on CURRENT options in the properties panel
    selected_contours = get_selected_roto_contours(parent_node)

    # Read Bezier preference (Cusped Bezier: checked = no bezier/linear; unchecked = bezier/smooth)
    try:
        bezier_enabled = not bool(parent_node['roto_bezier'].value())
    except Exception:
        bezier_enabled = True

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

    original_frame = None
    try:
        original_frame = int(nuke.frame())
    except Exception:
        pass

    build_frame = min(
        int(frame)
        for frame_data in active_contours.values()
        for frame in frame_data.keys()
    )

    try:
        try:
            nuke.frame(build_frame)
        except Exception:
            pass

        # N4: Resolve the parent group BEFORE deselecting, then deselect inside
        # that group so nodes nested within the FaceTracker's parent are
        # deselected too.
        parent_group = parent_node.parent()

        # Deselect all nodes to cleanly connect the new Roto node to our custom node
        for n in nuke.allNodes(parent_group):
            n.setSelected(False)

        parent_node.setSelected(True)

        # Create the Roto Node in the parent canvas context
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

            is_closed = group_name not in getattr(landmarks_config, "OPEN_CONTOUR_GROUPS", set())

            # N1: Set the contour open/closed state. Try the private _curvelib
            # attribute set FIRST (the author deliberately uses _curvelib for Nuke 15+
            # compatibility, where the public FlagType.eOpenFlag path is present but
            # inconsistent across builds), and only fall back to the public
            # shape.setFlag(eOpenFlag) when _curvelib is unavailable. This preserves
            # the proven Nuke-15 behavior exactly and only diverges on versions where
            # _curvelib fails. If BOTH paths fail, warn loudly instead of silently
            # passing (the old code swallowed the failure and left the shape closed).
            shape_closure_set = False
            try:
                import _curvelib
                shape.getAttributes().set(0, _curvelib.AnimAttributes.kClosedAttribute, 1.0 if is_closed else 0.0)
                shape_closure_set = True
            except Exception:
                # _curvelib unavailable on this Nuke version — try the public flag API.
                pass

            if not shape_closure_set:
                try:
                    # eOpenFlag True means the shape is open; pass (not is_closed).
                    shape.setFlag(nuke.rotopaint.FlagType.eOpenFlag, not is_closed)
                    shape_closure_set = True
                except Exception as e:
                    print(
                        f"[NukeFaceTracker] WARNING: Could not set open/closed state "
                        f"for contour '{group_name}' (is_closed={is_closed}): {e}. "
                        f"Both the _curvelib and public setFlag(eOpenFlag) paths failed."
                    )

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
                    _add_position_key(anim_point, frame, coords[0], coords[1])

                    feather_center = _get_keyable_anim_point(
                        shape_point,
                        ("featherCenter", "featherPoint", "feather")
                    )
                    if feather_center is not None:
                        # Nuke feather points are relative to the main control point.
                        # Keep the feather edge aligned with the main spline by keying zero offset.
                        _add_position_key(feather_center, frame, 0.0, 0.0)

                    # If Bezier is enabled and there are enough points, calculate smooth tangents
                    if is_closed and bezier_enabled and num_points > 2:
                        tx, ty = _calculate_closed_bezier_tangent(points, idx)

                        # Left tangent handle (incoming)
                        _add_position_key(shape_point.leftTangent, frame, -tx, -ty)

                        # Right tangent handle (outgoing)
                        _add_position_key(shape_point.rightTangent, frame, tx, ty)

                        feather_left_tangent = _get_keyable_anim_point(
                            shape_point,
                            ("featherLeftTangent", "leftFeatherTangent", "featherLeft")
                        )
                        if feather_left_tangent is not None:
                            _add_position_key(feather_left_tangent, frame, -tx, -ty)

                        feather_right_tangent = _get_keyable_anim_point(
                            shape_point,
                            ("featherRightTangent", "rightFeatherTangent", "featherRight")
                        )
                        if feather_right_tangent is not None:
                            _add_position_key(feather_right_tangent, frame, tx, ty)

        # Force Nuke to evaluate and refresh the curves in the viewer
        curves_knob.changed()

        parent_node.setSelected(True)
        roto_node.setSelected(True)
    finally:
        if original_frame is not None:
            try:
                nuke.frame(original_frame)
            except Exception:
                pass

    return True


def _resolve_input_dimensions(node):
    """Resolve the (width, height) of the node's active input, falling back to the
    root format when there is no input or the input format cannot be evaluated."""
    input_node = node.input(0)
    if input_node:
        try:
            return input_node.format().width(), input_node.format().height()
        except Exception:
            pass
    return nuke.root().format().width(), nuke.root().format().height()


def _export_from_panel(node, builder):
    """Shared export-from-panel flow: resolve the output JSON path, validate it,
    resolve input dimensions, then delegate to ``builder(node, json_path, w, h)``."""
    json_path = _resolve_output_json_path(node)
    if not json_path:
        nuke.message("Please specify a valid output JSON file path first.")
        return False
    width, height = _resolve_input_dimensions(node)
    return builder(node, json_path, width, height)


def generate_tracker_node_from_panel(node):
    """Callback triggered from the Tracker tab. Loads JSON and builds the Tracker4 node."""
    return _export_from_panel(node, generate_tracker_node)


def generate_roto_node_from_panel(node):
    """Callback triggered from the Roto tab. Loads JSON and builds the Roto node."""
    return _export_from_panel(node, generate_roto_node)


def generate_cornerpin_node_from_panel(node):
    """Callback triggered from the CornerPin tab. Loads JSON, calculates corner pin data and builds the CornerPin2D node."""
    return _export_from_panel(node, generate_cornerpin_node)


def set_ref_frame_to_current(node):
    """Sets the 'ref_frame' knob to the current frame on the timeline."""
    node['ref_frame'].setValue(int(nuke.frame()))


