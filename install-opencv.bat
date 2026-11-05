@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto error
)
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-opencv.txt
if errorlevel 1 goto error
echo OpenCV installiert. Tesseract muss separat installiert und im PATH sein.
pause
exit /b 0
:error
echo Installation fehlgeschlagen. Bitte Meldung oben pruefen.
pause
exit /b 1
