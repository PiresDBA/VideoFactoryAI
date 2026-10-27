$ErrorActionPreference = 'Stop'
$ProjectDir = Get-Location
$PatchFile = Join-Path $PSScriptRoot 'media_research_agent.py'
$TargetFile = Join-Path $ProjectDir 'media_research_agent.py'

if (-not (Test-Path $PatchFile)) { throw "Arquivo do patch não encontrado: $PatchFile. Extraia o ZIP e execute este script na pasta extraída." }
if (-not (Test-Path $TargetFile)) { throw "Não encontrei $TargetFile. Abra o PowerShell na pasta C:\Fabrica-de-videos\VideoFactoryAI e execute o script usando o caminho completo." }

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = "$TargetFile.bak_ffprobe_$stamp"
Copy-Item -LiteralPath $TargetFile -Destination $backup
Copy-Item -LiteralPath $PatchFile -Destination $TargetFile -Force

Write-Host "Backup criado: $backup" -ForegroundColor Green
Write-Host "Patch instalado: $TargetFile" -ForegroundColor Green
Write-Host "Próximo passo: teste primeiro uma execução curta do pipeline. Se houver problema, use reverter_patch.ps1 ou restaure o backup." -ForegroundColor Yellow
