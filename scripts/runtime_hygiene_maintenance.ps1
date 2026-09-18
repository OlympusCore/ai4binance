param(
    [switch]$Apply
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$cleanupScript = Join-Path $root "scripts\cleanup_generated_artifacts.ps1"
$python = Join-Path $root ".venv\Scripts\python.exe"
$reportRoot = Join-Path `
    $root "runtime\artifacts\maintenance_archive\runtime_hygiene"
$stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runRoot = Join-Path $reportRoot $stamp
$reportPath = Join-Path $runRoot "capacity-and-retention.json"
$latestPath = Join-Path $reportRoot "latest.json"
$retentionPath = Join-Path $runRoot "automatic-retention.json"
$mutex = [System.Threading.Mutex]::new(
    $false,
    "Local\AI4BINANCE-Runtime-Hygiene-Maintenance"
)
$mutexAcquired = $false

try {
    $mutexAcquired = $mutex.WaitOne(0)
    if (-not $mutexAcquired) {
        [pscustomobject]@{
            command = "runtime-hygiene-maintenance"
            status = "SKIPPED_ALREADY_RUNNING"
            applied = [bool]$Apply
            execution_allowed = $false
            promotion_status = "RESEARCH_ONLY"
            live_eligibility_status = "LIVE_ORDER_BLOCKED"
        } | ConvertTo-Json -Depth 4
        exit 0
    }
    if (-not (Test-Path -LiteralPath $cleanupScript -PathType Leaf)) {
        throw "Runtime hygiene cleanup script is unavailable: $cleanupScript"
    }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Repository Python runtime is unavailable: $python"
    }
    New-Item -ItemType Directory -Path $runRoot -Force | Out-Null

    $cleanupArguments = @{
        Mode = @("RuntimeTmpRetention", "RuntimeRunRetention")
        WhatIfSummaryPath = $retentionPath
    }
    if ($Apply) {
        $cleanupArguments["Apply"] = $true
        $cleanupArguments.Remove("WhatIfSummaryPath")
    }
    $retentionOutput = @(& $cleanupScript @cleanupArguments)
    $retentionInvocationSucceeded = $?
    if (-not $retentionInvocationSucceeded) {
        throw "Automatic retention cleanup invocation failed"
    }
    if ($Apply) {
        $retentionOutput | Set-Content -LiteralPath $retentionPath -Encoding UTF8
    }

    $previousArguments = @()
    if (Test-Path -LiteralPath $latestPath -PathType Leaf) {
        $previousArguments = @("--previous-report", $latestPath)
    }
    $previousPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = (Join-Path $root "src")
        $capacityOutput = @(
            & $python -B -m ai4binance.ops.runtime_hygiene `
                --repository-root $root `
                --output $reportPath `
                @previousArguments
        )
        $capacityInvocationSucceeded = $?
        $capacityExitCode = $LASTEXITCODE
    }
    finally {
        $env:PYTHONPATH = $previousPythonPath
    }
    if (-not $capacityInvocationSucceeded -or $capacityExitCode -ne 0) {
        throw "Runtime hygiene capacity review failed with exit code $capacityExitCode"
    }
    Copy-Item -LiteralPath $reportPath -Destination $latestPath -Force
    $capacityReport = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    $capacityAccessErrorCount = @(
        $capacityReport.capacity | ForEach-Object { $_.access_errors }
    ).Count
    $ownerReviewFamilyCount = @(
        $capacityReport.retention_review |
            Where-Object { $_.owner_review_required }
    ).Count
    [pscustomobject]@{
        command = "runtime-hygiene-maintenance"
        status = "COMPLETED"
        applied = [bool]$Apply
        retention_evidence_path = $retentionPath.Substring($root.Length + 1)
        capacity_evidence_path = $reportPath.Substring($root.Length + 1)
        latest_capacity_path = $latestPath.Substring($root.Length + 1)
        capacity_status = [string]$capacityReport.status
        capacity_access_error_count = $capacityAccessErrorCount
        owner_review_family_count = $ownerReviewFamilyCount
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Depth 6
}
finally {
    if ($null -ne $mutex) {
        if ($mutexAcquired) {
            $mutex.ReleaseMutex()
        }
        $mutex.Dispose()
    }
}
