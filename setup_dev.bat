@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   ALU Timing Tool v5 - Developer Setup
echo ============================================
echo.

REM Check Python version (3.12 or 3.13 required)
for /f "tokens=2 delims= " %%a in ('python --version 2^>^&1') do set PYTHON_VERSION=%%a
echo Detected Python version: %PYTHON_VERSION%

set VALID_PYTHON=0
echo %PYTHON_VERSION% | findstr /B "3.12" >nul && set VALID_PYTHON=1
echo %PYTHON_VERSION% | findstr /B "3.13" >nul && set VALID_PYTHON=1

if %VALID_PYTHON%==0 (
    echo.
    echo ERROR: Python 3.12 or 3.13 is required.
    echo Current version: %PYTHON_VERSION%
    echo.
    echo Install Python 3.12 from Microsoft Store or:
    echo   winget install Python.Python.3.12
    echo.
    pause
    exit /b 1
)

echo Python version OK.
echo.

REM Backup existing venv if present
if exist venv (
    echo Existing venv found. Creating backup...
    if exist venvbak rmdir /s /q venvbak
    rename venv venvbak
    echo Backup created as venvbak
    echo.
)

REM Create new venv
echo Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)
echo Virtual environment created.
echo.

REM Activate venv
echo Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment.
    pause
    exit /b 1
)
echo Virtual environment activated.
echo.

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip
echo.

REM Install dependencies
echo Installing dependencies from requirements_dev.txt...
pip install -r requirements_dev.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Developer Setup Complete!
echo ============================================
echo.
echo Includes Jupyter/IPython for notebook development.
echo.
echo To run the timing tool:
echo   1. Activate venv:  venv\Scripts\activate.bat
echo   2. Run:            python main.py
echo.
echo To use Jupyter notebooks:
echo   jupyter notebook
echo.
pause
