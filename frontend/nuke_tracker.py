import os
import sys
import json
import re
import subprocess
import nuke
import nukescripts

# Add backend directory to sys.path to import landmarks config
plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_dir = os.path.join(plugin_dir, "backend")
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

try:
    import landmarks_config
except ImportError:
    # Fallback if path mapping fails in specific environments
    landmarks_config = None

class FaceTrackerPanel(nukescripts.PythonPanel):
    def __init__(self, selected_node):
        super(FaceTrackerPanel, self).__init__("MediaPipe Face Tracker (MVP)", "com.antigravity.facetracker")
        
        self.node = selected_node
        
        # Set default values based on the selected Read node
        self.input_file = ""
        self.start_fr = 1
        self.end_fr = 100
        self.width = 1920
        self.height = 1080
        
        if self.node and self.node.Class() == "Read":
            self.input_file = self.node['file'].value()
            self.start_fr = int(self.node['first'].value())
            self.end_fr = int(self.node['last'].value())
            self.width = self.node.format().width()
            self.height = self.node.format().height()
            
        # 1. Input Node (Read-only)
        self.node_knob = nuke.String_Knob("node_name", "Input Read Node:", self.node.name() if self.node else "None")
        self.node_knob.setEnabled(False)
        self.addKnob(self.node_knob)
        
        # 2. File Path (Read-only, for verification)
        self.path_knob = nuke.String_Knob("input_path", "File Path:", self.input_file)
        self.path_knob.setEnabled(False)
        self.addKnob(self.path_knob)
        
        # 3. Resolution
        self.resolution_knob = nuke.String_Knob("resolution", "Resolution:", f"{self.width}x{self.height}")
        self.resolution_knob.setEnabled(False)
        self.addKnob(self.resolution_knob)
        
        # Spacer / Divider
        self.divider = nuke.Text_Knob("div", "", "")
        self.addKnob(self.divider)
        
        # 4. Frame Range
        self.start_knob = nuke.Int_Knob("start_frame", "Start Frame:", self.start_fr)
        self.end_knob = nuke.Int_Knob("end_frame", "End Frame:", self.end_fr)
        self.addKnob(self.start_knob)
        self.addKnob(self.end_knob)
        
        # Section Divider
        self.divider2 = nuke.Text_Knob("div2", "Select Landmarks to Track:", "")
        self.addKnob(self.divider2)
        
        # 5. Landmark Group Selection
        self.track_nose = nuke.Boolean_Knob("track_nose", "Nose (Tip, Bridge, Alar)", True)
        self.track_eyes = nuke.Boolean_Knob("track_eyes", "Eyes (Corners, Eyelids)", True)
        self.track_eyebrows = nuke.Boolean_Knob("track_eyebrows", "Eyebrows (Left & Right Eyebrows)", False)
        self.track_mouth = nuke.Boolean_Knob("track_mouth", "Mouth (Lip contours & Corners)", False)
        self.track_contour = nuke.Boolean_Knob("track_contour", "Face Contour (Chin, Forehead, Cheeks)", False)
        
        self.addKnob(self.track_nose)
        self.addKnob(self.track_eyes)
        self.addKnob(self.track_eyebrows)
        self.addKnob(self.track_mouth)
        self.addKnob(self.track_contour)
        
        # Section Divider
        self.divider3 = nuke.Text_Knob("div3", "Output Options:", "")
        self.addKnob(self.divider3)
        
        # 6. Output JSON Path
        temp_json = os.path.join(plugin_dir, "temp_tracker_data.json")
        self.output_json_knob = nuke.File_Knob("output_json", "Output JSON File")
        self.output_json_knob.setValue(temp_json)
        self.addKnob(self.output_json_knob)
        
    def get_selected_landmarks_string(self):
        """Collects selected landmark names based on checkboxes."""
        if not landmarks_config:
            return ""
            
        selected_names = []
        if self.track_nose.value():
            selected_names.extend(landmarks_config.LANDMARK_GROUPS["Nose"].keys())
        if self.track_eyes.value():
            selected_names.extend(landmarks_config.LANDMARK_GROUPS["Eyes"].keys())
        if self.track_eyebrows.value():
            selected_names.extend(landmarks_config.LANDMARK_GROUPS["Eyebrows"].keys())
        if self.track_mouth.value():
            selected_names.extend(landmarks_config.LANDMARK_GROUPS["Mouth"].keys())
        if self.track_contour.value():
            selected_names.extend(landmarks_config.LANDMARK_GROUPS["Face Shape"].keys())
            
        return ",".join(selected_names)

    def run_tracking(self):
        """Invokes the backend process and generates the Tracker4 node."""
        # 1. Input Validation
        if not self.node or self.node.Class() != "Read":
            nuke.message("Please select a valid 'Read' node before running the tracker.")
            return False
            
        input_path = self.input_file
        if not input_path:
            nuke.message("The selected Read node does not contain a valid file path.")
            return False
            
        start_frame = self.start_knob.value()
        end_frame = self.end_knob.value()
        if start_frame > end_frame:
            nuke.message("Start frame cannot be greater than end frame!")
            return False
            
        output_json = self.output_json_knob.value()
        if not output_json:
            nuke.message("Please specify a valid path for the output JSON file.")
            return False
            
        landmarks_str = self.get_selected_landmarks_string()
        if not landmarks_str:
            nuke.message("Please select at least one landmark group to track!")
            return False
            
        # 2. Locate Python executable in .venv
        if sys.platform == "win32":
            python_exe = os.path.join(plugin_dir, ".venv", "Scripts", "python.exe")
        else:
            python_exe = os.path.join(plugin_dir, ".venv", "bin", "python")
            
        if not os.path.exists(python_exe):
            nuke.message(f"Virtual environment python not found at:\n{python_exe}\n\nPlease run 'install_requirements.bat' to set it up.")
            return False
            
        backend_script = os.path.join(plugin_dir, "backend", "tracker_backend.py")
        
        # 3. Build command line
        cmd = [
            python_exe,
            backend_script,
            "--input", input_path,
            "--output", output_json,
            "--start", str(start_frame),
            "--end", str(end_frame),
            "--width", str(self.width),
            "--height", str(self.height),
            "--landmarks", landmarks_str
        ]
        
        # Hide cmd console window on Windows
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0 # SW_HIDE
            
        # 4. Run subprocess with Nuke ProgressTask
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
            print(f"[MediaPipe Backend] {line}") # Print to Nuke Script Editor console
            
            # Capture logs in case of error
            if "[ERROR]" in line or "Error:" in line or "Traceback" in line:
                error_logs.append(line)
                
            # Parse progress
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
            
        # 5. Generate Tracker4 Node in Nuke
        return self.generate_tracker_node(output_json)
        
    def generate_tracker_node(self, json_path):
        """Loads JSON data and generates a fully keyframed Tracker4 node using TCL fromScript serialization."""
        if not os.path.exists(json_path):
            nuke.message(f"Output JSON file not found:\n{json_path}")
            return False
            
        try:
            with open(json_path, "r") as f:
                tracker_data = json.load(f)
        except Exception as e:
            nuke.message(f"Failed to parse JSON file:\n{str(e)}")
            return False
            
        # Find active tracking tracks containing data
        active_tracks = {name: data for name, data in tracker_data.items() if data}
        if not active_tracks:
            nuke.message("Face detected but failed to track any landmarks in the specified frame range.")
            return False
            
        # Deselect all nodes to cleanly connect the new Tracker4 node to the Read node
        for n in nuke.allNodes():
            n.setSelected(False)
            
        self.node.setSelected(True)
        
        # Create Tracker4 Node
        tracker = nuke.createNode('Tracker4')
        tracker.setName("FaceTracker_MediaPipe1")
        
        # Construct the TCL string for the 'tracks' knob (31 columns per track)
        # Modern Nuke Tracker4 expects a 3-part serialization layout:
        # Part 1: Header list defining the version/multiplier and actual track count { 1 31 <num_tracks> }
        # Part 2: Column definitions block (defining names, types, flags for all 31 table columns)
        # Part 3: Data block containing each track row
        
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
            # Sort frames to ensure chronological order
            sorted_frames = sorted([int(f) for f in frame_data.keys()])
            if not sorted_frames:
                continue
                
            first_frame = sorted_frames[0]
            
            # Build X and Y curve expressions in Nuke TCL format: curve xFrame val xFrame val ...
            x_curve_parts = []
            y_curve_parts = []
            for frame in sorted_frames:
                coords = frame_data[str(frame)]
                x_curve_parts.append(f"x{frame} {coords[0]}")
                y_curve_parts.append(f"x{frame} {coords[1]}")
                
            x_curve_str = " ".join(x_curve_parts)
            y_curve_str = " ".join(y_curve_parts)
            
            # Format the individual tracker Tcl script string (exactly 31 columns wide)
            tracker_str = (
                f"{{ {{curve K x{first_frame} 1}} \"{point_name}\" "
                f"{{curve {x_curve_str}}} {{curve {y_curve_str}}} "
                f"{{curve K x{first_frame} 0}} {{curve K x{first_frame} 0}} 1 0 0 "
                f"{{curve x{first_frame} 0}} 1 0 -15 -15 15 15 -10 -10 10 10 "
                f"{{}} {{}} {{}} {{}} {{}} {{}} {{}} {{}} {{}} {{}} {{}} }}"
            )
            tracker_strings.append(tracker_str)
            
        # Combine everything into the correct 3-part layout
        tracker_strings_combined = "{\n" + "\n".join(tracker_strings) + "\n}"
        from_script_str = f"{{ 1 31 {num_tracks} }} \n{column_definitions} \n{tracker_strings_combined}\n"
        
        # Inject the TCL string into the 'tracks' knob
        try:
            tracker['tracks'].fromScript(from_script_str)
        except Exception as e:
            nuke.message(f"Failed to populate Tracker4 node tracks using fromScript:\n{str(e)}")
            return False
            
        # Select both nodes for artist convenience
        self.node.setSelected(True)
        tracker.setSelected(True)
        
        nuke.message(f"Success!\nGenerated Tracker4 node '{tracker.name()}' with {len(active_tracks)} track points.")
        return True

def show_dialog():
    """Helper function to show the dialog panel from Nuke menu."""
    selected_nodes = nuke.selectedNodes()
    
    read_node = None
    if selected_nodes:
        for node in selected_nodes:
            if node.Class() == "Read":
                read_node = node
                break
                
    if not read_node:
        all_reads = nuke.allNodes("Read")
        if all_reads:
            read_node = all_reads[0]
            
    if not read_node:
        nuke.message("No 'Read' node found in the script.\nPlease create and select a 'Read' node with your footage before running the tracker.")
        return
        
    panel = FaceTrackerPanel(read_node)
    if panel.showModalDialog():
        panel.run_tracking()
