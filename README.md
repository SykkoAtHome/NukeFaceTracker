# MediaPipe Face Tracker for Foundry Nuke (MVP)

An advanced AI-powered face tracking plugin for Foundry Nuke that automatically tracks facial features using **Google MediaPipe Face Landmarker** and generates a native, fully keyframed **Tracker4** node.

By utilizing an **isolated subprocess and dedicated virtual environment (`.venv`) architecture**, the plugin eliminates binary C++ library conflicts (such as Qt, Protobuf, or NumPy version mismatches) that typically trigger Nuke crashes (`Segmentation Fault`), ensuring 100% host application stability.

---

## Key Features

- **Bulletproof Stability**: The machine learning model (MediaPipe) runs in a separate system subprocess, completely isolating Nuke from library conflicts.
- **Video & Image Sequence Support**: Works seamlessly with video formats (MP4, MOV) and VFX image sequences (PNG, JPG, EXR – including automatic LDR normalization for deep learning processing).
- **Coordinate Conversion & Subpixel Precision**: Automatically converts normalized coordinate spaces (MediaPipe's top-left origin) to absolute pixels in Nuke's native space (bottom-left origin).
- **Native Tracker4 Nodes via TCL**: Generates native `Tracker4` nodes populated with named tracker tracks and keyframed animation curves in less than a millisecond using TCL serialization.
- **Selective Landmark Tracking**: Allows the artist to select specific facial landmark groups (e.g., Nose, Eyes, Eyebrows, Mouth, Face Contour) to optimize performance.

---

## Installation

### Step 1: Initialize Virtual Environment and Download Model
Go to the plugin installation folder (`D:\code\NukeFaceTracker`) and double-click the setup file:
```bash
install_requirements.bat
```
This script will automatically:
1. Create a local Python `.venv/` virtual environment directory.
2. Upgrade `pip` and install required backend packages (`mediapipe`, `opencv-python-headless`, `requests`).
3. Download the official, pre-trained `face_landmarker.task` model file directly to the `backend/` folder.

### Step 2: Register the Plugin in Foundry Nuke
Add the following line to your user-specific `init.py` script located in your home `.nuke` directory (e.g., `C:\Users\<Your_Username>\.nuke\init.py`):

```python
nuke.pluginAddPath("d:/code/NukeFaceTracker")
```

---

## Workflows and Usage

1. Open Foundry Nuke.
2. Create a **Read** node and load your clip or image sequence containing a face.
3. Select the **Read** node.
4. From Nuke's top menu bar, select: **Antigravity** -> **MediaPipe Face Tracker**.
5. In the configuration dialog:
   - Verify the auto-detected frame range and format resolution.
   - Select the facial feature groups (Landmarks) you want to track (e.g., *Nose*, *Eyes*).
   - Set the temporary JSON output path (defaults to the plugin directory).
6. Click **OK**.
7. Nuke's native progress task bar will display the tracking progress. Once finished, a perfectly keyframed **Tracker4** node will be automatically created and connected to your **Read** node.

---

## Project Directory Layout

- `init.py` / `menu.py` - Startup scripts that register the plugin paths and the Nuke menu item.
- `install_requirements.bat` - Automates local virtualenv creation and package installation.
- `requirements.txt` - Python backend package dependencies.
- `backend/` - Background detection engine (MediaPipe + OpenCV).
  - `tracker_backend.py` - Main CLI tracking and JSON generation process.
  - `landmarks_config.py` - Mapping configurations from index numbers to recognizable English names.
  - `model_downloader.py` - Downloads the optimized `.task` model file.
- `frontend/` - Nuke UI panel and node builder.
  - `nuke_tracker.py` - PySide Python panel and Tracker4 TCL builder.

---

## Coordinate Transformations (Technical)

MediaPipe outputs coordinates in normalized space $[0.0, 1.0]$ with $(0,0)$ at the top-left corner. Nuke expects pixel-space coordinates with $(0,0)$ at the bottom-left corner of the format. The backend automatically handles this conversion:

$$X_{Nuke} = X_{MediaPipe} \times Width$$
$$Y_{Nuke} = Height - (Y_{MediaPipe} \times Height)$$
