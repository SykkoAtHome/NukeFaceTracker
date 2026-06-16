# init.py for Foundry Nuke
# Registers frontend and backend directories in Nuke's plugin paths and Python sys.path.

import nuke
import os
import sys

plugin_dir = os.path.dirname(os.path.abspath(__file__))
frontend_path = os.path.join(plugin_dir, "frontend")
backend_path = os.path.join(plugin_dir, "backend")

nuke.pluginAddPath(frontend_path)
nuke.pluginAddPath(backend_path)

if frontend_path not in sys.path:
    sys.path.append(frontend_path)
if backend_path not in sys.path:
    sys.path.append(backend_path)
