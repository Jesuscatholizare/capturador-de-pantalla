@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Abre el Capturador con Python, sin crear el .exe.
rem La primera vez instala las librerias (tarda unos minutos).
if not exist .venv\Scripts\python.exe (
  echo Primera vez: preparando el programa...
  set "PY=py -3"
  py -3 --version >/dev/null 2>&1
  if errorlevel 1 set "PY=python"
)
if not exist .venv\Scripts\python.exe (
  %PY% -m venv .venv
  if errorlevel 1 goto error
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  if errorlevel 1 goto error
)
call .venv\Scripts\activate.bat
echo Abriendo el Capturador... (no cierres esta ventana mientras lo usas)
python Capturador.py
if errorlevel 1 goto error
exit /b 0
:error
echo.
echo Algo fallo. Copia el texto de arriba y enviamelo.
pause
exit /b 1
