@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Capturador: preparar y crear Capturador.exe ===
set "PY=py -3"
py -3 --version >nul 2>&1
if errorlevel 1 set "PY=python"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo No encuentro Python. Instalalo desde https://www.python.org/downloads/
  echo y marca la casilla "Add python.exe to PATH". Luego vuelve a ejecutar este archivo.
  pause
  exit /b 1
)
if not exist .venv (
  %PY% -m venv .venv
  if errorlevel 1 goto error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error
pyinstaller --noconfirm --onefile --windowed --name Capturador Capturador.py
if errorlevel 1 goto error
echo.
echo Listo: dist\Capturador.exe
echo Puedes copiar ese archivo a cualquier carpeta o a una memoria USB.
pause
exit /b 0
:error
echo.
echo Algo fallo. Copia el texto de arriba y enviamelo.
pause
exit /b 1
