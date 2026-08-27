$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ComposeRoot = Split-Path -Parent $ProjectRoot
$BackupRoot = Join-Path $env:USERPROFILE ".axio\backups"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupPath = Join-Path $BackupRoot "axio-cortex-$Timestamp.sql"

New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
Push-Location $ComposeRoot
try {
    docker compose exec -T axio-postgres pg_dump -U axio -d axio_cortex |
        Out-File -LiteralPath $BackupPath -Encoding utf8
    $DumpExit = $LASTEXITCODE
}
finally {
    Pop-Location
}

# A non-empty file is NOT proof of success: a mid-stream pg_dump/docker failure
# still writes partial output. Gate on the actual pg_dump exit code, and delete
# a bad dump so the rotation step below can never keep it over a good backup.
$BackupOk = ($DumpExit -eq 0) -and (Test-Path -LiteralPath $BackupPath) -and ((Get-Item -LiteralPath $BackupPath).Length -gt 0)
if (-not $BackupOk) {
    if (Test-Path -LiteralPath $BackupPath) { Remove-Item -LiteralPath $BackupPath -Force }
    throw "AXIO Cortex backup failed (pg_dump exit code $DumpExit)."
}

Get-ChildItem -LiteralPath $BackupRoot -Filter "axio-cortex-*.sql" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 14 |
    Remove-Item -Force
