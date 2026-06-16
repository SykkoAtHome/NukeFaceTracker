# init.py for Foundry Nuke
# Registers frontend and backend directories in Nuke's plugin paths.

import nuke
import os

plugin_dir = os.path.dirname(os.path.abspath(__file__))
frontend_path = os.path.join(plugin_dir, "frontend")
backend_path = os.path.join(plugin_dir, "backend")

nuke.pluginAddPath(frontend_path)
nuke.pluginAddPath(backend_path)
