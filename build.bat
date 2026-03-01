@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   ALU Timing Tool v5 - Build EXE
echo ============================================
echo.

REM Activate venv
if not exist venv\Scripts\activate.bat (
    echo ERROR: Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

REM Check PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller.
        pause
        exit /b 1
    )
    echo.
)

REM Clean previous build
echo Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo.

REM Build
echo Building ALU Timer...
echo.
pyinstaller ALUTimer.spec
if errorlevel 1 (
    echo.
    echo ERROR: Build failed. See output above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Build Complete!
echo ============================================
echo.
echo Output: dist\ALU Timer.exe
echo.
echo The exe is fully standalone. It creates a "runs" folder
echo next to itself on first launch for ghosts and config.
echo.
pause
