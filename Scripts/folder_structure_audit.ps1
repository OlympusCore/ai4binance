$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = "python"
}

& $python -m ai4binance.ops.folder_structure_audit `
    --repository-root $root `
    --output-directory (Join-Path $root "Artifacts\folder-structure-audit")
exit $LASTEXITCODE
