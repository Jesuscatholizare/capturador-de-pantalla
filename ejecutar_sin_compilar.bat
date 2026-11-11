@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
  echo Primero ejecuta crear_portable_windows.bat
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python Capturador.py
if errorlevel 1 pause
