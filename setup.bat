@echo off
if exist .venv (
    echo Virtual environment already exists
) else (
    echo Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
python setup.py