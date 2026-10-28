@echo off

cd /d "%~dp0"

git add .

git commit -m "AutoSave %date% %time%"

git push

if errorlevel 1 (
    echo.
    echo Tentando criar upstream automaticamente...
    git push --set-upstream origin HEAD
)

echo.
echo Backup enviado para GitHub.
pause