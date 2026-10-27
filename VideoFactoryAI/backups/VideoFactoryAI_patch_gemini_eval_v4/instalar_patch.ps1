# VideoFactoryAI — Patch corretivo do avaliador Gemini v4
$ErrorActionPreference = "Stop"
$patchDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $patchDir
$target = Join-Path $projectDir "gemini_webchat_image.py"
$replacement = Join-Path $patchDir "gemini_webchat_image.py"
if (!(Test-Path (Join-Path $projectDir "media_research_agent.py"))) { throw "Não encontrei media_research_agent.py. Extraia esta pasta diretamente dentro de VideoFactoryAI." }
if (!(Test-Path $replacement)) { throw "Arquivo de patch ausente: $replacement" }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $projectDir ("_backup_gemini_eval_v4_" + $stamp)
New-Item -ItemType Directory -Path $backupDir | Out-Null
if (Test-Path $target) { Copy-Item $target (Join-Path $backupDir "gemini_webchat_image.py") }
Write-Host "Backup criado em: $backupDir" -ForegroundColor Green
Copy-Item $replacement $target -Force
$python = "C:\Docling\venv\Scripts\python.exe"
if (!(Test-Path $python)) { throw "Python do projeto não encontrado: $python. O backup está em $backupDir" }
& $python -m py_compile $target
if ($LASTEXITCODE -ne 0) {
  Write-Warning "Falha de sintaxe; restaurando módulo original."
  if (Test-Path (Join-Path $backupDir "gemini_webchat_image.py")) { Copy-Item (Join-Path $backupDir "gemini_webchat_image.py") $target -Force }
  throw "Patch revertido automaticamente. Backup: $backupDir"
}
Write-Host "Patch v4 instalado. media_research_agent.py e L1-L3 não foram alterados." -ForegroundColor Green
Write-Host "O diagnóstico JSON será gravado em logs\gemini_eval_debug.jsonl após avaliações." -ForegroundColor Cyan
Write-Host "Para reverter, use reverter_patch.ps1 e informe: $backupDir"
