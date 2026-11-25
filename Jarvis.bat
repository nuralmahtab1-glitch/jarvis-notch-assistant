@echo off
rem Jarvis - made by Nur Al Mahtab. Starts the notch with no console window.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" "run.py"
