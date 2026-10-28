@echo off

cd /d "%~dp0"

echo.
echo ======================================
echo VideoFactoryAI - Snapshot
echo ======================================
echo.

git diff --quiet

if %errorlevel%==0 (
    echo.
    echo Nenhuma alteracao encontrada.
    pause
    exit /b 0
)

git add .

if errorlevel 1 goto erro



git commit -m "AutoSave %date% %time%"

if errorlevel 1 goto erro

git push

if errorlevel 1 goto erro

for /f %%i in ('git rev-parse --short HEAD') do set HASH=%%i

echo.
echo ======================================
echo SUCESSO
echo Commit: %HASH%
echo ======================================
echo.
pause
exit /b 0

:erro

echo.
echo ======================================
echo ERRO
echo Falha durante backup
echo ======================================
echo.

pause
exit /b 1