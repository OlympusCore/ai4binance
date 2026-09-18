param(
    [Parameter(Mandatory = $true)]
    [string]$SourceManifest,
    [string]$MirrorManifest = "",
    [string]$PolicyPath = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$srcPath = Join-Path $repoRoot "src"

if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $srcPath
} elseif ($env:PYTHONPATH -notlike "*$srcPath*") {
    $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH"
}

if ([string]::IsNullOrWhiteSpace($MirrorManifest)) {
    $MirrorManifest = Join-Path $repoRoot "runtime\artifacts\repository_validation\mirror\latest_inventory.json"
}
if ([string]::IsNullOrWhiteSpace($PolicyPath)) {
    $PolicyPath = Join-Path $repoRoot "config\governance\repository_mirror_policy.yaml"
}

$resolvedSourceManifest = (Resolve-Path -LiteralPath $SourceManifest).Path
$mirrorDirectory = Split-Path -Parent $MirrorManifest
New-Item -ItemType Directory -Path $mirrorDirectory -Force | Out-Null

& $python -m ai4binance.governance.repository_validator `
    --repository-root $repoRoot `
    --check-mirror-manifest $resolvedSourceManifest `
    --mirror-policy $PolicyPath `
    --quiet
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    throw "Mirror manifest import validation failed with exit code $exitCode"
}

Copy-Item -LiteralPath $resolvedSourceManifest -Destination $MirrorManifest -Force

[ordered]@{
    status = "IMPORTED"
    source_manifest = $resolvedSourceManifest
    mirror_manifest = $MirrorManifest
    execution_allowed = $false
    promotion_status = "RESEARCH_ONLY"
    live_eligibility_status = "LIVE_ORDER_BLOCKED"
} |
    ConvertTo-Json -Depth 4
