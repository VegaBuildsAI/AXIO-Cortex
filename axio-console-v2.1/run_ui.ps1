$ErrorActionPreference = "Stop"

$AxioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $AxioRoot ".venv\Scripts\python.exe"
$UiRoot = Join-Path $AxioRoot "ui"
$DataRoot = Join-Path $env:USERPROFILE ".axio"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "AXIO Python environment is missing. Create .venv and install requirements.txt."
}
if (-not (Test-Path -LiteralPath (Join-Path $UiRoot "node_modules"))) {
    throw "AXIO UI dependencies are missing. Run npm install inside ui."
}

$env:AXIO_DATA_ROOT = $DataRoot
$env:AXIO_UI_DATA_DIR = Join-Path $DataRoot "ui"
New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null

$Backend = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList "-m", "uvicorn", "web_api.main:app", "--host", "127.0.0.1", "--port", "8765" `
    -WorkingDirectory $AxioRoot `
    -WindowStyle Hidden `
    -PassThru

$Frontend = Start-Process `
    -FilePath "npm.cmd" `
    -ArgumentList "run", "dev", "--", "--hostname", "127.0.0.1" `
    -WorkingDirectory $UiRoot `
    -WindowStyle Hidden `
    -PassThru

try {
    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        try {
            $Response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:3000" -TimeoutSec 1
            if ($Response.StatusCode -eq 200 -and $Response.Content -match 'class="console') {
                $CssMatch = [regex]::Match(
                    $Response.Content,
                    'href="([^"]+\.css[^"]*)"'
                )
                if ($CssMatch.Success) {
                    $CssUri = [Uri]::new(
                        [Uri]"http://127.0.0.1:3000",
                        $CssMatch.Groups[1].Value
                    )
                    $CssResponse = Invoke-WebRequest `
                        -UseBasicParsing `
                        -Uri $CssUri `
                        -TimeoutSec 1
                    if ($CssResponse.Headers["Content-Type"] -match '^text/css') {
                        $Ready = $true
                        break
                    }
                }
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $Ready) {
        throw "AXIO UI did not become ready with valid HTML and CSS on http://127.0.0.1:3000."
    }
    Start-Process "http://127.0.0.1:3000"
    Write-Host "AXIO Console is running locally at http://127.0.0.1:3000"
    Write-Host "Press Enter to stop AXIO Console."
    Read-Host
}
finally {
    if (-not $Frontend.HasExited) { Stop-Process -Id $Frontend.Id }
    if (-not $Backend.HasExited) { Stop-Process -Id $Backend.Id }
}
