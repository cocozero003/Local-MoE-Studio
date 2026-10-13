@echo off
setlocal
cd /d "%~dp0\.."
py -3 -m pip install --upgrade pip pyinstaller
if errorlevel 1 exit /b 1
py -3 -m PyInstaller --clean --noconfirm --onedir --windowed --name LocalMoEStudio --paths src --add-data "src\localmoestudio\web;localmoestudio\web" scripts\entrypoint.py
if errorlevel 1 exit /b 1
echo Build in dist\LocalMoEStudio
