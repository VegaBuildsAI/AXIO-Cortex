$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repoRoot "docker-compose.searxng.yml"
$secretBytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($secretBytes)
$env:SEARXNG_SECRET = [Convert]::ToHexString($secretBytes).ToLowerInvariant()

try {
    docker compose -f $composeFile up -d
} finally {
    Remove-Item Env:SEARXNG_SECRET -ErrorAction SilentlyContinue
}

Write-Host "AXIO SearXNG is available at http://127.0.0.1:8080"
