@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
py -3 -m localmoestudio
if errorlevel 1 pause
