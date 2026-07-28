$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$pytestTempRoot = Join-Path $PSScriptRoot "..\Artifacts\TestTemp"
New-Item -ItemType Directory -Path $pytestTempRoot -Force | Out-Null
$pytestTemp = Join-Path (
    $pytestTempRoot
) ("ai4binance-pytest-" + [guid]::NewGuid().ToString("N"))

function Invoke-QualityStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $python @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode"
    }
}

Invoke-QualityStep "Dependency check" @("-m", "pip", "check")
Invoke-QualityStep "Ruff format" @("-m", "ruff", "format", "--check", ".")
Invoke-QualityStep "Ruff lint" @("-m", "ruff", "check", ".")
Invoke-QualityStep "MyPy" @("-m", "mypy")
Invoke-QualityStep "Pytest" @("-m", "pytest", "--basetemp", $pytestTemp)
Invoke-QualityStep "Bandit" @("-m", "bandit", "-q", "-r", "src")
