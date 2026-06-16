@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   NukeFaceTracker - Virtual Env Setup (MVP)
echo ===================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in system PATH!
    echo Please install Python 3.10+ and ensure it is added to your environment variables.
    pause
    exit /b 1
)

:: Create virtual environment
if not exist .venv (
    echo [INFO] Creating virtual environment .venv...
    python -m venv .venv
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [INFO] Virtual environment .venv already exists.
)

:: Activate venv and install requirements
echo [INFO] Activating virtual environment and installing packages...
call .venv\Scripts\activate.bat

echo [INFO] Upgrading pip...
python -m pip install --upgrade pip

echo [INFO] Installing requirements from requirements.txt...
pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo [ERROR] Installation failed.
    pause
    exit /b 1
)

:: Download model file
echo [INFO] Checking MediaPipe Face Landmarker model file...
if not exist backend mkdir backend
python -c "import os; import requests; url='https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'; dest='backend/face_landmarker.task'; print('Downloading model...' if not os.path.exists(dest) else 'Model already exists.'); os.makedirs('backend', exist_ok=True); open(dest, 'wb').write(requests.get(url).content) if not os.path.exists(dest) else None"

echo.
echo [SUCCESS] Environment setup completed successfully!
echo face_landmarker.task model is stored in the 'backend' folder.
echo.
pause
exit /b 0
