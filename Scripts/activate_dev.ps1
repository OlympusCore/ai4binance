$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$venvRoot = Join-Path $root ".venv"
$venvScripts = Join-Path $venvRoot "Scripts"
$python = Join-Path $venvScripts "python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Repo venv Python is missing: $python"
}

$expectedVersion = "3.12.10"
$actualVersion = & $python -c "import sys; print('.'.join(str(p) for p in sys.version_info[:3]))"
if ($actualVersion -ne $expectedVersion) {
    throw "Expected Python $expectedVersion, found $actualVersion at $python"
}

$pathParts = @($env:PATH -split [IO.Path]::PathSeparator | Where-Object {
        $_ -and ($_ -ine $venvScripts)
    })
$env:PATH = (@($venvScripts) + $pathParts) -join [IO.Path]::PathSeparator
$env:VIRTUAL_ENV = $venvRoot
$env:VIRTUAL_ENV_PROMPT = "(.venv)"
$env:PYTHONPATH = Join-Path $root "src"
$env:PYTHONUTF8 = "1"
$env:AI4BINANCE_ADVISORY_LLM_MODE = "RESEARCH_ONLY"
$env:AI4BINANCE_ALLOW_AUTO_LIVE_ORDERS = "false"

& $python -m pip check
if ($LASTEXITCODE -ne 0) {
    throw "pip check failed for $python"
}

Write-Output "AI4BINANCE_DEV_ENV_OK"
Write-Output "python=$python"
Write-Output "version=$actualVersion"
if ($MyInvocation.InvocationName -ne ".") {
    Write-Output "To update the current shell, run: . .\Scripts\activate_dev.ps1"
}
