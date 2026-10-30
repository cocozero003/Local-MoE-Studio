@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
py -3 -c "from localmoestudio.thai_fda import status; import sys; s=status(); print('Thai FDA V3.17 ready' if s['available'] else 'Thai FDA setup required'); sys.exit(0 if s['available'] else 2)"
if errorlevel 1 (
  echo Run SETUP_THAI_FDA_WINDOWS.bat with the controlled V3.17 data ZIP first.
  pause
  exit /b 2
)
py -3 -m localmoestudio.headless
if errorlevel 1 pause
