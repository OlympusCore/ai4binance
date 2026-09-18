param(
    [string]$MirrorManifest = "",
    [string]$PolicyPath = "",
    [string]$OutputJson = "",
    [string]$OutputMarkdown = "",
    [string]$CleanupPlan = "",
    [switch]$Required
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if ([string]::IsNullOrWhiteSpace($MirrorManifest)) {
    $MirrorManifest = Join-Path $repoRoot "runtime\artifacts\repository_validation\mirror\latest_inventory.json"
}
if ([string]::IsNullOrWhiteSpace($PolicyPath)) {
    $PolicyPath = Join-Path $repoRoot "config\governance\repository_mirror_policy.yaml"
}
if ([string]::IsNullOrWhiteSpace($OutputJson)) {
    $OutputJson = Join-Path $repoRoot "runtime\artifacts\repository_validation\mirror_hygiene_report.json"
}
if ([string]::IsNullOrWhiteSpace($OutputMarkdown)) {
    $OutputMarkdown = Join-Path $repoRoot "runtime\reports\repository_validation\mirror_hygiene_report.md"
}
if ([string]::IsNullOrWhiteSpace($CleanupPlan)) {
    $CleanupPlan = Join-Path $repoRoot "runtime\artifacts\repository_validation\mirror_cleanup_plan.json"
}

if (-not (Test-Path -LiteralPath $MirrorManifest -PathType Leaf)) {
    Write-Output "MIRROR_REMOTE_CHECK=NOT_VERIFIED"
    Write-Output "mirror_manifest=$MirrorManifest"
    if ($Required) {
        throw "Mirror manifest is required but was not found."
    }
    exit 0
}

& $python -m ai4binance.governance.repository_validator `
    --repository-root $repoRoot `
    --check-mirror-manifest $MirrorManifest `
    --mirror-policy $PolicyPath `
    --output-json $OutputJson `
    --output-markdown $OutputMarkdown `
    --output-cleanup-plan $CleanupPlan `
    --quiet
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    throw "Mirror hygiene validation failed with exit code $exitCode"
}

Write-Output "MIRROR_REMOTE_CHECK=VERIFIED"
Write-Output "mirror_hygiene_report=$OutputJson"
Write-Output "mirror_cleanup_plan=$CleanupPlan"
