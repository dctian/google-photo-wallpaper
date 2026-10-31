@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup.ps1"
if errorlevel 1 (
  echo Setup failed. Read the message above.
  pause
  exit /b 1
)
echo Setup complete. Open Start-App.cmd.
pause
