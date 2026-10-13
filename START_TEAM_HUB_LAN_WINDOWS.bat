@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
echo WARNING: LAN mode runs over unencrypted HTTP. Only use a trusted private LAN.
py -3 -m localmoestudio.headless --lan
if errorlevel 1 pause
