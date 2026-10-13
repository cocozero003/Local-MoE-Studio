@echo off
setlocal
cd /d "%~dp0\.."
set "PYTHONPATH=%CD%\src"
py -3 -m unittest discover -s tests -v
