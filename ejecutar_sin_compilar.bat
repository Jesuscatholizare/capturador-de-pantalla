@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Abre el Capturador con Python, sin crear el .exe.
rem La primera vez (y cuando hay librerias nuevas) las instala; tarda unos minutos.
if not exist .venv\Scripts\python.exe (
  echo Primera vez: preparando el programa...
  set "PY=py -3"
  py -3 --version >nul 2>&1
  if errorlevel 1 set "PY=python"
)
if not exist .venv\Scripts\python.exe (
  %PY% -m venv .venv
  if errorlevel 1 goto error
)
call .venv\Scripts\activate.bat
copy /b /y requirements.txt+requirements-ocr.txt .venv\pedido.txt >nul
fc /b .venv\pedido.txt .venv\instalado.txt >nul 2>&1
if errorlevel 1 (
  echo Instalando o actualizando librerias...
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  if errorlevel 1 goto error
  python -m pip install -r requirements-ocr.txt
  if errorlevel 1 (
    echo.
    echo Aviso: no se pudo instalar el OCR de Windows. El programa funciona igual, sin OCR.
    echo Se volvera a intentar la proxima vez que abras el programa.
    echo.
  ) else (
    copy /y .venv\pedido.txt .venv\instalado.txt >nul
  )
)
echo Abriendo el Capturador... (no cierres esta ventana mientras lo usas)
python Capturador.py
if errorlevel 1 goto error
exit /b 0
:error
echo.
echo Algo fallo. Copia el texto de arriba y enviamelo.
pause
exit /b 1
