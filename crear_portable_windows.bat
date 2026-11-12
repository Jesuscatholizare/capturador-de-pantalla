@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Capturador: preparar y crear Capturador.exe ===
call :preparar
if errorlevel 1 goto error
python -m pip install pyinstaller
if errorlevel 1 goto sin_exe
rem Se llama a PyInstaller por medio de python.exe: algunos equipos bloquean pyinstaller.exe
python -m PyInstaller --noconfirm --onefile --windowed --name Capturador Capturador.py
if errorlevel 1 goto sin_exe
if not exist dist\Capturador.exe goto sin_exe
echo.
echo Listo: dist\Capturador.exe
echo Puedes copiar ese archivo a cualquier carpeta o a una memoria USB.
echo Si al abrirlo Windows lo bloquea, usa ejecutar_sin_compilar.bat
pause
exit /b 0

:sin_exe
echo.
echo ------------------------------------------------------------------
echo  No se pudo crear Capturador.exe en este equipo (por ejemplo, porque
echo  una directiva de seguridad como Device Guard no lo permite).
echo  El programa SI esta instalado: abrelo con ejecutar_sin_compilar.bat
echo ------------------------------------------------------------------
pause
exit /b 0

:error
echo.
echo Algo fallo. Copia el texto de arriba y enviamelo.
pause
exit /b 1

:preparar
set "PY=py -3"
py -3 --version >/dev/null 2>&1
if errorlevel 1 set "PY=python"
%PY% --version >/dev/null 2>&1
if errorlevel 1 (
  echo No encuentro Python. Instalalo desde https://www.python.org/downloads/
  echo y marca la casilla "Add python.exe to PATH". Luego vuelve a ejecutar este archivo.
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  %PY% -m venv .venv
  if errorlevel 1 exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
exit /b %errorlevel%
