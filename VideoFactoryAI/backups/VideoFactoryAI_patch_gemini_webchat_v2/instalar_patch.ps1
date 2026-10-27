[CmdletBinding()]
param([string]$ProjectRoot = "")
$ErrorActionPreference = 'Stop'
$PatchDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot = Split-Path -Parent $PatchDir }
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$required = @('media_research_agent.py', 'gemini_webchat_image.py')
foreach ($name in $required) {
    if (-not (Test-Path (Join-Path $PatchDir $name) -PathType Leaf)) { throw "Arquivo do patch ausente: $name" }
}
$targetMedia = Join-Path $ProjectRoot 'media_research_agent.py'
if (-not (Test-Path $targetMedia -PathType Leaf)) { throw "Não encontrei $targetMedia. Informe a raiz correta usando -ProjectRoot." }
$python = 'C:\Docling\venv\Scripts\python.exe'
if (-not (Test-Path $python -PathType Leaf)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source } else { throw 'Python não encontrado. Instalação cancelada.' }
}
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $ProjectRoot (Join-Path 'backups' ("gemini_webchat_v2_" + $stamp))
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$manifest = [ordered]@{ created = (Get-Date).ToString('o'); project_root = $ProjectRoot; files = @() }
foreach ($name in $required) {
    $target = Join-Path $ProjectRoot $name
    $existed = Test-Path $target -PathType Leaf
    $entry = [ordered]@{ name = $name; existed = $existed; backup = $null }
    if ($existed) {
        $backup = Join-Path $backupRoot $name
        Copy-Item -LiteralPath $target -Destination $backup -Force
        $entry.backup = $backup
    }
    $manifest.files += $entry
}
$manifestPath = Join-Path $backupRoot 'manifest.json'
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
try {
    foreach ($name in $required) { Copy-Item -LiteralPath (Join-Path $PatchDir $name) -Destination (Join-Path $ProjectRoot $name) -Force }
    $targets = @((Join-Path $ProjectRoot 'media_research_agent.py'), (Join-Path $ProjectRoot 'gemini_webchat_image.py'))
    & $python -c "import ast,pathlib,sys; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8')) for p in sys.argv[1:]]" @targets
    if ($LASTEXITCODE -ne 0) { throw 'A validação sintática falhou.' }
    Write-Host ''
    Write-Host 'PATCH INSTALADO E SINTAXE VALIDADA.' -ForegroundColor Green
    Write-Host "Projeto: $ProjectRoot"
    Write-Host "Backup:  $backupRoot"
    Write-Host 'Próximo passo: teste com 1–2 cenas antes da produção completa.'
} catch {
    Write-Warning "Falha durante instalação: $($_.Exception.Message)"
    foreach ($entry in $manifest.files) {
        $target = Join-Path $ProjectRoot $entry.name
        if ($entry.existed -and $entry.backup -and (Test-Path $entry.backup)) { Copy-Item -LiteralPath $entry.backup -Destination $target -Force }
        elseif (Test-Path $target) { Remove-Item -LiteralPath $target -Force }
    }
    throw 'Instalação revertida automaticamente a partir do backup.'
}
