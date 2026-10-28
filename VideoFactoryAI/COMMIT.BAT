@echo off

cd /d "%~dp0"

git add .

git commit -m "AutoSave %date% %time%"

git push

echo Backup enviado para GitHub.
timeout /t 3 >nul