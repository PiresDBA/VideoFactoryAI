@echo off
setlocal EnableExtensions
chcp 65001 >nul

REM Abre a interface usando o Python do ambiente do VideoFactoryAI.
REM Prioridade: ambiente conhecido do usuario, venv local, ambiente ativo e PATH.

cd /d "%~dp0"
set "PYTHON_EXE="

REM 1) Ambiente Python informado pelo usuario.
if exist "C:\Docling\venv\Scripts\python.exe" set "PYTHON_EXE=C:\Docling\venv\Scripts\python.exe"

REM 2) Ambiente virtual dentro da pasta do projeto.
if not defined PYTHON_EXE if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"

REM 3) Ambiente virtual ativo, se houver.
if not defined PYTHON_EXE if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" set "PYTHON_EXE=%VIRTUAL_ENV%\Scripts\python.exe"

REM 4) Ultimo recurso: Python encontrado no PATH.
if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)

if not defined PYTHON_EXE (
    echo [ERRO] Nao encontrei o Python.
    echo Ative o ambiente virtual do VideoFactoryAI ou ajuste o caminho neste arquivo .bat.
    pause
    exit /b 1
)

if not exist "%~dp0videofactory_gui.py" (
    echo [ERRO] Nao encontrei videofactory_gui.py nesta pasta:
    echo %~dp0
    echo Coloque este .bat na mesma pasta de videofactory_gui.py.
    pause
    exit /b 1
)

echo Python selecionado: "%PYTHON_EXE%"
"%PYTHON_EXE%" -c "import tkinter; print('Tkinter OK:', tkinter.__file__)"
if errorlevel 1 (
    echo.
    echo [ERRO] Este Python nao conseguiu importar tkinter.
    echo Verifique o componente Tcl/Tk da instalacao Python selecionada.
    pause
    exit /b 1
)

echo Iniciando a interface do VideoFactoryAI...
"%PYTHON_EXE%" "%~dp0videofactory_gui.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo A interface terminou com codigo %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%
