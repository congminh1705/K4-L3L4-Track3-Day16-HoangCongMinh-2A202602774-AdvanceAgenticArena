param([switch]$Evaluate)

$ErrorActionPreference = 'Stop'
$labRoot = Split-Path $PSScriptRoot -Parent
$savedEnvironment = @{}
foreach ($key in @('PYTHONUTF8', 'PYTHONIOENCODING', 'TEMP', 'TMP')) {
    $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}
Push-Location $labRoot
try {
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $labTemp = Join-Path $labRoot 'runs/tmp'
    New-Item -ItemType Directory -Force -Path $labTemp | Out-Null
    $env:TEMP = $labTemp
    $env:TMP = $labTemp
    $labPython = Join-Path $labRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $labPython)) {
        & python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Cannot create Python environment' }
    }
    & $labPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    & $labPython scripts/verify.py --full
    if ($LASTEXITCODE -ne 0) { throw 'Lab verification failed' }
    & $labPython scripts/run_practice.py --layers none --tag baseline --entry baseline --out runs/baseline.json
    if ($LASTEXITCODE -ne 0) { throw 'Baseline failed' }
    & $labPython scripts/run_practice.py --layers all --entry HoangCongMinh --out runs/HoangCongMinh.json --strict
    if ($LASTEXITCODE -ne 0) { throw 'Full stack failed' }
    if ($Evaluate) {
        & $labPython scripts/evaluate_layers.py
        if ($LASTEXITCODE -ne 0) { throw 'Layer evaluation failed' }
    }
} finally {
    foreach ($key in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key], 'Process')
    }
    Pop-Location
}
