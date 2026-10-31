@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run Setup.ps1 first to install the local app.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m photo_cache gui
