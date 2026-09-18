param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryRoot
)

$ErrorActionPreference = "Continue"
$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$qualityScript = Join-Path $root "scripts\quality.ps1"
if (-not (Test-Path -LiteralPath $qualityScript -PathType Leaf)) {
    throw "Canonical quality gate was not found: $qualityScript"
}

& powershell.exe `
    -NoLogo `
    -NoProfile `
    -NonInteractive `
    -ExecutionPolicy Bypass `
    -File $qualityScript `
    -Profile full
exit $LASTEXITCODE
