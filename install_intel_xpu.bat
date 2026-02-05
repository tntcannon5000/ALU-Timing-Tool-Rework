@echo off
setlocal enabledelayedexpansion

echo ========================================
echo ALU Timing Tool - Intel XPU Setup
echo ========================================
echo.

:: Check for Python 3.12 or 3.13
echo [1/5] Checking Python version...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    goto :python_install_prompt
)

:: Get Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i

:: Extract major.minor version
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set PYTHON_MAJOR=%%a
    set PYTHON_MINOR=%%b
)

echo Found Python %PYTHON_VERSION%

:: Check if version is 3.12 or 3.13
if "%PYTHON_MAJOR%"=="3" (
    if "%PYTHON_MINOR%"=="12" goto :python_ok
    if "%PYTHON_MINOR%"=="13" goto :python_ok
)

echo ERROR: Python 3.12 or 3.13 is required
echo Current version: %PYTHON_VERSION%
goto :python_install_prompt

:python_install_prompt
echo.
echo Please install Python 3.12 using the following command:
echo.
echo     winget install -e --id Python.Python.3.12
echo.
echo After installation, restart this script.
pause
exit /b 1

:python_ok
echo [OK] Python %PYTHON_VERSION% is compatible
echo.

:: Check if venv exists
echo [2/5] Checking for existing virtual environment...
if exist "venv" (
    echo WARNING: Existing 'venv' folder found
    echo.
    
    :: Check if venvbak already exists
    if exist "venvbak" (
        echo ERROR: 'venvbak' folder already exists
        echo Please manually remove or rename 'venvbak' before continuing
        pause
        exit /b 1
    )
    
    echo Renaming 'venv' to 'venvbak'...
    rename venv venvbak
    if errorlevel 1 (
        echo ERROR: Failed to rename venv folder
        pause
        exit /b 1
    )
    
    echo [OK] Old venv backed up to 'venvbak'
    echo.
    echo NOTE: To revert, delete 'venv' and run: rename venvbak venv
    echo.
) else (
    echo [OK] No existing venv found
    echo.
)

:: Create new venv
echo [3/5] Creating new virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment created
echo.

:: Activate venv
echo [4/5] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment activated
echo.

:: Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip --quiet
echo.

:: Install PyTorch with XPU support
echo [5/5] Installing dependencies...
echo.
echo Installing PyTorch with Intel XPU support (this may take a few minutes)...
pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/xpu
if errorlevel 1 (
    echo ERROR: Failed to install PyTorch with XPU support
    pause
    exit /b 1
)
echo [OK] PyTorch with XPU support installed
echo.

:: Install core dependencies
echo Installing core dependencies...
pip install numpy opencv-python Pillow easyocr dxcam-cpp dxcam pywin32
if errorlevel 1 (
    echo ERROR: Failed to install core dependencies
    pause
    exit /b 1
)
echo [OK] Core dependencies installed
echo.

:: Install remaining dependencies from requirements.txt
echo Installing remaining dependencies from requirements.txt...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo WARNING: Some packages from requirements.txt may have failed
    echo The core dependencies are installed, you can continue
)
echo.

:: Verify XPU is available
echo ========================================
echo Verifying Intel XPU installation...
echo ========================================
python -c "import torch; print(f'PyTorch version: {torch.__version__}'); xpu_available = hasattr(torch, 'xpu') and torch.xpu.is_available(); print(f'XPU available: {xpu_available}'); print(f'XPU device count: {torch.xpu.device_count() if xpu_available else 0}'); print(f'XPU device: {torch.xpu.get_device_name(0) if xpu_available and torch.xpu.device_count() > 0 else \"N/A\"}')"
if errorlevel 1 (
    echo.
    echo WARNING: Could not verify XPU installation
    echo Please check that Intel GPU drivers are installed
    echo.
) else (
    echo.
    echo [OK] XPU verification complete
    echo.
)

echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Next steps:
echo   1. Make sure Intel GPU drivers are installed
echo      https://www.intel.com/content/www/us/en/download/785597/intel-arc-iris-xe-graphics-windows.html
echo.
echo   2. To activate the virtual environment, run:
echo      venv\Scripts\activate.bat
echo.
echo   3. To run the application:
echo      python main.py
echo.
echo   4. To deactivate when done:
echo      deactivate
echo.
if exist "venvbak" (
    echo NOTE: Your old environment is backed up in 'venvbak'
    echo To revert: delete 'venv' and rename the venvbak folder back to 'venv'
    echo.
)
echo ========================================
pause
