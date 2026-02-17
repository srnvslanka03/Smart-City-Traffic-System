@echo off
nsetlocal enabledelayedexpansion

echo =======================================
echo  Adaptive Traffic Light Control System
echo =======================================

REM Check Python version
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check if virtual environment exists, create if not
if not exist "venv\" (
    echo [INFO] Creating Python virtual environment...
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate virtual environment
call venv\Scripts\activate

REM Update pip to latest version
echo [INFO] Updating pip...
python -m pip install --upgrade pip

REM Install requirements
echo [INFO] Installing dependencies (this may take a few minutes)...
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install dependencies
    echo Please check your internet connection and try again
    pause
    exit /b 1
)

REM Check for YOLO weights
if not exist "bin\yolo.weights" (
    echo [WARNING] YOLO weights not found in bin/ directory
    echo Please download the weights from:
    echo https://drive.google.com/file/d/1flTehMwmGg-PMEeQCsDS2VWRLGzV6Wdo/view?usp=sharing
    echo And place them in the bin/ directory
    echo Press any key to continue with simulation mode (limited functionality)...
    pause >nul
)

REM Run the application
echo [INFO] Starting web application...
echo =======================================
echo  Access the application at: http://localhost:5000
echo  Press Ctrl+C to stop the server
echo =======================================

python web_app.py

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to start the application
    echo Please check if port 5000 is available or another instance is running
)

pause
