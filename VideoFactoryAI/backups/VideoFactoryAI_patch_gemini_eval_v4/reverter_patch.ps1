# Reverte apenas o módulo do avaliador Gemini v4
$ErrorActionPreference = "Stop"
$patchDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $patchDir
$backup = Read-Host "Cole o caminho completo da pasta _backup_gemini_eval_v4_..."
$source = Join-Path $backup "gemini_webchat_image.py"
if (!(Test-Path $source)) { throw "Backup inválido ou sem gemini_webchat_image.py: $backup" }
Copy-Item $source (Join-Path $projectDir "gemini_webchat_image.py") -Force
Write-Host "Módulo restaurado. Nenhum outro arquivo foi alterado." -ForegroundColor Green
