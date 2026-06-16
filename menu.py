# menu.py for Foundry Nuke
# Registers a custom icon inside Nuke's left-side Node toolbar.

import nuke
import os
import sys

# Ensure frontend path is in sys.path on startup
plugin_dir = os.path.dirname(os.path.abspath(__file__))
frontend_path = os.path.join(plugin_dir, "frontend")
if frontend_path not in sys.path:
    sys.path.append(frontend_path)

try:
    import nuke_tracker
    
    # Create a dedicated, distinct category in Nuke's left-side Node toolbar
    toolbar = nuke.menu("Nodes")
    custom_menu = toolbar.addMenu("Face Tracker", icon="Tracker.png")
    custom_menu.addCommand(
        "Face Tracker", 
        "nuke_tracker.create_face_tracker_node()", 
        icon="Tracker.png"
    )
except Exception as e:
    print(f"[NukeFaceTracker] Failed to load menu: {e}")
