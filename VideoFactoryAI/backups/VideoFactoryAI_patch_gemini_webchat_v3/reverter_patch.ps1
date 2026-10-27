# Reverte o patch mais recente a partir do backup informado.
$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$backup = Read-Host "Cole o caminho completo da pasta _backup_gemini_patch_... criada pelo instalador"
if (!(Test-Path (Join-Path $backup "media_research_agent.py"))) { throw "Backup inválido: $backup" }
Copy-Item (Join-Path $backup "media_research_agent.py") (Join-Path $projectDir "media_research_agent.py") -Force
if (Test-Path (Join-Path $backup "gemini_webchat_image.py")) {
    Copy-Item (Join-Path $backup "gemini_webchat_image.py") (Join-Path $projectDir "gemini_webchat_image.py") -Force
}
Write-Host "Arquivos restaurados do backup: $backup" -ForegroundColor Green
