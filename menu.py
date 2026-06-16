# menu.py for Foundry Nuke
# Registers menu items to easily access the Face Tracker plugin from the GUI.

import nuke
import os

try:
    import nuke_tracker
    
    # Locate or create the "Antigravity" top-level menu
    menubar = nuke.menu("Nuke")
    antigravity_menu = menubar.findItem("Antigravity")
    if not antigravity_menu:
        antigravity_menu = menubar.addMenu("Antigravity")
        
    # Append the face tracker command to the menu
    antigravity_menu.addCommand(
        "MediaPipe Face Tracker", 
        "nuke_tracker.show_dialog()", 
        icon="Tracker.png"
    )
    print("[NukeFaceTracker] Successfully initialized NukeFaceTracker menu.")
except Exception as e:
    print(f"[NukeFaceTracker] Failed to load menu: {e}")
