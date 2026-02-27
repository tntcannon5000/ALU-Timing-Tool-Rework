@echo off
echo Starting ALU Timing Tool...

:: Change to script directory
cd /d "%~dp0"

:: Activate virtual environment and run
call venv\Scripts\activate.bat && python main.py

:: Keep window open on exit
echo.
echo Tool has stopped.
pause