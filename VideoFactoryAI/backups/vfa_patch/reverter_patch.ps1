$ErrorActionPreference = 'Stop'
$ProjectDir = Get-Location
$TargetFile = Join-Path $ProjectDir 'media_research_agent.py'
$backup = Get-ChildItem -LiteralPath $ProjectDir -Filter 'media_research_agent.py.bak_ffprobe_*' -File |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $backup) { throw "Nenhum backup media_research_agent.py.bak_ffprobe_* encontrado em $ProjectDir" }
Copy-Item -LiteralPath $backup.FullName -Destination $TargetFile -Force
Write-Host "Arquivo restaurado de: $($backup.FullName)" -ForegroundColor Green
