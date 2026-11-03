@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto error
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto error
.venv\Scripts\python.exe app.py --open-browser
if errorlevel 1 goto error
exit /b 0
:error
echo Start fehlgeschlagen. Bitte die Meldung oben pruefen.
pause
exit /b 1
