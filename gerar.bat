: << 'END_WINDOWS_BAT'
@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "RAIZ=%~dp0"
set "PY=%RAIZ%venv\Scripts\python.exe"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "INTERATIVO=0"
if "%~1"=="" set "INTERATIVO=1"

if exist "%PY%" goto :checar
if exist "%RAIZ%venv" rmdir /s /q "%RAIZ%venv"
goto :criar

:checar
"%PY%" -c "import pandas,reportlab,matplotlib" >nul 2>&1
if errorlevel 1 goto :instalar
goto :rodar

:criar
set "MODO="
where py >nul 2>&1 && py -3 -c "import sys" >nul 2>&1 && set "MODO=py"
if not "%MODO%"=="" goto :fazer_venv
where python >nul 2>&1 && python -c "import sys" >nul 2>&1 && set "MODO=python"
if not "%MODO%"=="" goto :fazer_venv
where python3 >nul 2>&1 && python3 -c "import sys" >nul 2>&1 && set "MODO=python3"
if not "%MODO%"=="" goto :fazer_venv
echo Nao encontrei o Python neste computador.
echo Instale o Python 3 em https://www.python.org/downloads/
echo Na instalacao, marque a caixa "Add python.exe to PATH".
echo Depois, de dois cliques neste arquivo de novo.
goto :fim_erro

:fazer_venv
echo Preparando o programa. A primeira vez pode demorar alguns minutos.
if "%MODO%"=="py" (
  py -3 -m venv "%RAIZ%venv"
) else (
  "%MODO%" -m venv "%RAIZ%venv"
)
if errorlevel 1 goto :venv_falhou
if not exist "%PY%" goto :venv_falhou

:instalar
echo Instalando o que o programa precisa. Aguarde.
"%PY%" -m pip install --disable-pip-version-check -r "%RAIZ%requirements.txt"
if errorlevel 1 (
  echo Nao consegui instalar as bibliotecas. Confira a internet e tente de novo.
  goto :fim_erro
)

:rodar
"%PY%" "%RAIZ%gerar.py" %*
set "COD=%ERRORLEVEL%"
goto :fim

:venv_falhou
echo Nao consegui preparar o Python.
goto :fim_erro

:fim_erro
set "COD=1"

:fim
if "%INTERATIVO%"=="1" (
  echo.
  echo Aperte Enter para fechar esta janela.
  pause >nul
)
exit /b %COD%
END_WINDOWS_BAT

# O trecho acima e o Prompt de Comando do Windows.
# Daqui para baixo e o terminal do Linux. Os dois leem este mesmo arquivo.

RAIZ=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
cd "$RAIZ" || exit 1

INTERATIVO=0
if [ "$#" -eq 0 ]; then
  INTERATIVO=1
fi

encerrar() {
  if [ "$INTERATIVO" -eq 1 ] && [ -t 0 ]; then
    printf '\nAperte Enter para fechar esta janela.\n'
    read -r _ || true
  fi
  exit "$1"
}

achar_python() {
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    printf '%s\n' python
    return 0
  fi
  return 1
}

PY="$RAIZ/venv/bin/python"
if [ ! -x "$PY" ]; then
  if [ -d "$RAIZ/venv" ]; then
    echo "O ambiente antigo não serve neste computador. Vou preparar de novo."
    rm -rf "$RAIZ/venv"
  fi
  SYS_PY=$(achar_python) || {
    echo "Não encontrei o Python neste computador."
    echo "No Ubuntu, rode: sudo apt install python3 python3-venv python3-pip"
    echo "Depois, rode este arquivo de novo: bash gerar.bat"
    encerrar 1
  }
  echo "Preparando o programa. A primeira vez pode demorar alguns minutos."
  if ! "$SYS_PY" -m venv "$RAIZ/venv"; then
    echo "Não consegui preparar o Python."
    echo "No Ubuntu ou Debian, instale e tente de novo: sudo apt install python3-venv"
    encerrar 1
  fi
fi

if ! "$PY" -c "import pandas,reportlab,matplotlib" >/dev/null 2>&1; then
  echo "Instalando o que o programa precisa. Aguarde."
  if ! "$PY" -m pip install --disable-pip-version-check -r "$RAIZ/requirements.txt"; then
    echo "Não consegui instalar as bibliotecas. Confira a internet e tente de novo."
    encerrar 1
  fi
fi

export PYTHONUTF8=1
"$PY" "$RAIZ/gerar.py" "$@"
encerrar "$?"
