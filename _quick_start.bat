@echo off
echo Starting ALU Timing Tool...
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; & '.\venv\Scripts\Activate.ps1'; python -X utf8 -u main.py 2>&1 | Tee-Object -FilePath 'data\debug_log.txt' }"
