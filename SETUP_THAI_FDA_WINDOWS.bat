@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: drag Thai_FDA_Precedent_Assistant_Local_V317_20261030.zip onto this file
  echo or run: SETUP_THAI_FDA_WINDOWS.bat "C:\path\to\Thai_FDA_Precedent_Assistant_Local_V317_20261030.zip"
  pause
  exit /b 2
)
py -3 -m pip install -e ".[thai-fda]"
if errorlevel 1 goto :fail
py -3 scripts\setup_thai_fda_precedent.py "%~1"
if errorlevel 1 goto :fail
echo Thai FDA precedent mode is installed.
echo Start a model in Local MoE Studio, then run START_TEAM_HUB_WINDOWS.bat.
pause
exit /b 0
:fail
echo Setup failed.
pause
exit /b 1
