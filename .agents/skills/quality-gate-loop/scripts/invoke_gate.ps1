param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryRoot
)

$ErrorActionPreference = "Continue"
$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$pytestTemp = Join-Path (
    [System.IO.Path]::GetTempPath()
) ("ai4binance-pytest-" + [guid]::NewGuid().ToString("N"))
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Repository-local Python was not found: $python"
}

$results = [ordered]@{}

Push-Location -LiteralPath $root
try {
    & $python -m pytest --basetemp $pytestTemp
    $results["pytest"] = $LASTEXITCODE

    & $python -m ruff check .
    $results["ruff"] = $LASTEXITCODE

    & $python -m mypy
    $results["mypy"] = $LASTEXITCODE
}
finally {
    Pop-Location
}

Write-Output "QUALITY_GATE_SUMMARY"
foreach ($entry in $results.GetEnumerator()) {
    Write-Output ("{0}={1}" -f $entry.Key, $entry.Value)
}

$failures = @($results.Values | Where-Object { $_ -ne 0 })
if ($failures.Count -gt 0) {
    exit 1
}
exit 0
