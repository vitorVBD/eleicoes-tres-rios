@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0venv\Scripts\python.exe" (
  echo Nao encontrei o Python desta pasta.
  echo Quem configura o computador, uma vez so, roda:
  echo   py -3.12 -m venv venv
  echo   venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)
"%~dp0venv\Scripts\python.exe" "%~dp0gerar.py" %*
