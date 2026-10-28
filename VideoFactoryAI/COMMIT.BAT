@echo off

cd /d "%~dp0"

echo.
echo ======================================
echo VideoFactoryAI - Snapshot
echo ======================================
echo.

git add .

if errorlevel 1 goto erro

git commit -m "AutoSave %date% %time%"

if errorlevel 1 goto erro

git push

if errorlevel 1 goto erro

echo.
echo ======================================
echo SUCESSO
echo Commit enviado ao GitHub
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