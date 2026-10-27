[CmdletBinding()]
param([string]$ProjectRoot = "", [string]$BackupPath = "")
$ErrorActionPreference = 'Stop'
$PatchDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot = Split-Path -Parent $PatchDir }
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
if ([string]::IsNullOrWhiteSpace($BackupPath)) {
    $backupBase = Join-Path $ProjectRoot 'backups'
    $latest = Get-ChildItem $backupBase -Directory -Filter 'gemini_webchat_v2_*' -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $latest) { throw "Nenhum backup gemini_webchat_v2 encontrado em $backupBase" }
    $BackupPath = $latest.FullName
}
$manifestPath = Join-Path $BackupPath 'manifest.json'
if (-not (Test-Path $manifestPath -PathType Leaf)) { throw "Manifesto não encontrado: $manifestPath" }
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
foreach ($entry in $manifest.files) {
    $target = Join-Path $ProjectRoot $entry.name
    if ($entry.existed -and $entry.backup -and (Test-Path $entry.backup -PathType Leaf)) {
        Copy-Item -LiteralPath $entry.backup -Destination $target -Force
        Write-Host "Restaurado: $($entry.name)"
    } elseif (Test-Path $target -PathType Leaf) {
        Remove-Item -LiteralPath $target -Force
        Write-Host "Removido arquivo criado pelo patch: $($entry.name)"
    }
}
Write-Host "Reversão concluída. Backup preservado em: $BackupPath" -ForegroundColor Green
