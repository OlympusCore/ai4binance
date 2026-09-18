$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$venvRoot = Join-Path $root ".venv"
$venvScripts = Join-Path $venvRoot "Scripts"
$python = Join-Path $venvScripts "python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Repo venv Python is missing: $python"
}

$expectedVersion = "3.14.7"
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
$env:PIPAPI_PYTHON_LOCATION = $python

function global:pip-audit.exe {
    [CmdletBinding()]
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    $pipAuditExe = Join-Path $env:VIRTUAL_ENV "Scripts\pip-audit.exe"
    $pipAuditPython = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $pipAuditExe -PathType Leaf)) {
        throw "pip-audit executable is missing: $pipAuditExe"
    }
    if (-not (Test-Path -LiteralPath $pipAuditPython -PathType Leaf)) {
        throw "Repo venv Python is missing: $pipAuditPython"
    }

    $pipAuditBootstrap = (
        "import truststore; truststore.inject_into_ssl(); " +
        "from pip_audit._cli import audit; " +
        "audit()"
    )
    & $pipAuditPython -c $pipAuditBootstrap @Arguments
}

$pipCheckOutput = & $python -m pip check 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "pip check reported dependency issues for $python; activation continues. Use scripts\quality.ps1 for strict validation."
}

Write-Output "AI4BINANCE_DEV_ENV_OK"
Write-Output "python=$python"
Write-Output "version=$actualVersion"
if ($MyInvocation.InvocationName -ne ".") {
    Write-Output "To update the current shell, run: . .\scripts\activate_dev.ps1"
}
