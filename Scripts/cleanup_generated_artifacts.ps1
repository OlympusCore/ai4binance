param(
    [switch]$Apply,
    [switch]$IncludeCaches,
    [switch]$IncludeTestTemp,
    [switch]$IncludeLogs,
    [switch]$IncludeCoverage,
    [switch]$ForceAcl,
    [ValidateSet("Caches", "TestTempRetention", "LogsArchive", "Coverage", "All")]
    [string[]]$Mode = @(),
    [int]$RetentionDays = 2,
    [int]$LogRetentionDays = 7,
    [string]$WhatIfSummaryPath = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$archiveRoot = Join-Path $root "Artifacts\maintenance-archive"
$testTempRoot = Join-Path $root "Artifacts\TestTemp"
$stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runRoot = Join-Path $archiveRoot $stamp
$manifestPath = Join-Path $runRoot "generated-artifacts-cleanup.json"

function Assert-InRepoPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if (-not $fullPath.StartsWith($root + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside repository: $fullPath"
    }
    return $fullPath
}

function Get-RepoRelativePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $fullPath = Assert-InRepoPath -Path $Path
    return $fullPath.Substring($root.Length + 1)
}

function Assert-InTestTempPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $fullPath = Assert-InRepoPath -Path $Path
    $fullTestTempRoot = [System.IO.Path]::GetFullPath($testTempRoot)
    if (
        $fullPath -ne $fullTestTempRoot -and
        -not $fullPath.StartsWith($fullTestTempRoot + "\", [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "Refusing ACL-forced cleanup outside Artifacts\TestTemp: $fullPath"
    }
    return $fullPath
}

function Test-IsWindowsAdministrator {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [System.Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole(
        [System.Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

function Grant-TestTempCleanupAccess {
    param([Parameter(Mandatory = $true)][string]$Path)
    $resolved = Assert-InTestTempPath -Path $Path
    $principal = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

    if (-not (Test-IsWindowsAdministrator)) {
        throw "FORCE_ACL_REQUIRES_ELEVATED_POWERSHELL"
    }

    $takeownOutput = & takeown.exe /F $resolved /R /D Y 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "takeown failed for stale TestTemp path: $resolved :: $($takeownOutput -join '; ')"
    }

    $icaclsOutput = & icacls.exe $resolved /grant "${principal}:(OI)(CI)F" /T /C 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "icacls grant failed for stale TestTemp path: $resolved :: $($icaclsOutput -join '; ')"
    }
}

function New-CandidateRow {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Action,
        [Parameter(Mandatory = $true)][string]$Reason
    )
    $resolved = Assert-InRepoPath -Path $Path
    [pscustomobject]@{
        path = Get-RepoRelativePath -Path $resolved
        action = $Action
        reason = $Reason
        applied = $false
        forced_acl = $false
        skipped_reason = $null
    }
}

$now = [DateTimeOffset]::UtcNow
$candidates = @()
$selectedModes = [System.Collections.Generic.List[string]]::new()
foreach ($item in $Mode) {
    if ($item -eq "All") {
        foreach ($name in @("Caches", "TestTempRetention", "LogsArchive", "Coverage")) {
            if (-not $selectedModes.Contains($name)) {
                $selectedModes.Add($name)
            }
        }
        continue
    }
    if (-not $selectedModes.Contains($item)) {
        $selectedModes.Add($item)
    }
}
if ($IncludeCaches -and -not $selectedModes.Contains("Caches")) {
    $selectedModes.Add("Caches")
}
if ($IncludeTestTemp -and -not $selectedModes.Contains("TestTempRetention")) {
    $selectedModes.Add("TestTempRetention")
}
if ($IncludeLogs -and -not $selectedModes.Contains("LogsArchive")) {
    $selectedModes.Add("LogsArchive")
}
if ($IncludeCoverage -and -not $selectedModes.Contains("Coverage")) {
    $selectedModes.Add("Coverage")
}

if ($selectedModes.Contains("Caches")) {
    foreach ($relative in @(".mypy_cache", ".ruff_cache", ".pytest_cache", ".test-tmp")) {
        $path = Join-Path $root $relative
        if (Test-Path -LiteralPath $path -PathType Container) {
            $candidates += New-CandidateRow -Path $path -Action "REMOVE_DIRECTORY" -Reason "REPRODUCIBLE_TOOL_CACHE"
        }
    }
}

if ($selectedModes.Contains("TestTempRetention")) {
    if (Test-Path -LiteralPath $testTempRoot -PathType Container) {
        Get-ChildItem -LiteralPath $testTempRoot -Force -Directory |
            Where-Object {
                ($now - [DateTimeOffset]$_.LastWriteTimeUtc).TotalDays -ge $RetentionDays
            } |
            ForEach-Object {
                $candidates += New-CandidateRow -Path $_.FullName -Action "REMOVE_DIRECTORY" -Reason "STALE_TEST_TEMP"
            }
    }
}

if ($selectedModes.Contains("LogsArchive")) {
    $logsRoot = Join-Path $root "Logs"
    if (Test-Path -LiteralPath $logsRoot -PathType Container) {
        Get-ChildItem -LiteralPath $logsRoot -Force -File -Recurse |
            Where-Object {
                $_.Extension -in @(".jsonl", ".log") -and
                ($now - [DateTimeOffset]$_.LastWriteTimeUtc).TotalDays -ge $LogRetentionDays
            } |
            ForEach-Object {
                $candidates += New-CandidateRow -Path $_.FullName -Action "ARCHIVE_AND_REMOVE_FILE" -Reason "STALE_LOG"
            }
    }
}

if ($selectedModes.Contains("Coverage")) {
    foreach ($relative in @(".coverage", "coverage.xml")) {
        $path = Join-Path $root $relative
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $candidates += New-CandidateRow -Path $path -Action "REMOVE_FILE" -Reason "REPRODUCIBLE_COVERAGE_ARTIFACT"
        }
    }
    Get-ChildItem -LiteralPath $root -Force -File -Filter ".coverage.*" |
        Where-Object {
            $_.Name -ne ".coverage"
        } |
        ForEach-Object {
            $candidates += New-CandidateRow -Path $_.FullName -Action "REMOVE_FILE" -Reason "REPRODUCIBLE_COVERAGE_ARTIFACT"
        }
    $htmlCoverage = Join-Path $root "htmlcov"
    if (Test-Path -LiteralPath $htmlCoverage -PathType Container) {
        $candidates += New-CandidateRow -Path $htmlCoverage -Action "REMOVE_DIRECTORY" -Reason "REPRODUCIBLE_COVERAGE_ARTIFACT"
    }
}

if ($Apply -and @($candidates).Count -gt 0) {
    New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
    foreach ($row in $candidates) {
        $source = Assert-InRepoPath -Path (Join-Path $root $row.path)
        try {
            if ($row.action -eq "ARCHIVE_AND_REMOVE_FILE") {
                $archivePath = Join-Path $runRoot ($row.path + ".zip")
                New-Item -ItemType Directory -Path (Split-Path -Parent $archivePath) -Force | Out-Null
                Compress-Archive -LiteralPath $source -DestinationPath $archivePath -Force
                Remove-Item -LiteralPath $source -Force
                $row.applied = $true
                continue
            }
            if ($row.action -eq "REMOVE_DIRECTORY") {
                try {
                    Remove-Item -LiteralPath $source -Recurse -Force
                }
                catch {
                    if ($ForceAcl -and $row.reason -eq "STALE_TEST_TEMP") {
                        Grant-TestTempCleanupAccess -Path $source
                        Remove-Item -LiteralPath $source -Recurse -Force
                        $row.forced_acl = $true
                    }
                    else {
                        throw
                    }
                }
                $row.applied = $true
                continue
            }
            if ($row.action -eq "REMOVE_FILE") {
                Remove-Item -LiteralPath $source -Force
                $row.applied = $true
                continue
            }
            $row.skipped_reason = "UNKNOWN_ACTION"
        }
        catch {
            $row.applied = $false
            $row.skipped_reason = $_.Exception.Message
        }
    }
    [pscustomobject]@{
        command = "cleanup-generated-artifacts"
        applied = $true
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        modes = @($selectedModes)
        force_acl = [bool]$ForceAcl
        retention_days = $RetentionDays
        log_retention_days = $LogRetentionDays
        candidates = @($candidates)
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
}

if (-not $Apply) {
    if ([string]::IsNullOrWhiteSpace($WhatIfSummaryPath)) {
        New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
        $WhatIfSummaryPath = Join-Path $runRoot "generated-artifacts-cleanup-dry-run.json"
    }
    else {
        $WhatIfSummaryPath = Assert-InRepoPath -Path $WhatIfSummaryPath
        New-Item -ItemType Directory -Path (Split-Path -Parent $WhatIfSummaryPath) -Force | Out-Null
    }
    [pscustomobject]@{
        command = "cleanup-generated-artifacts"
        applied = $false
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        modes = @($selectedModes)
        force_acl = [bool]$ForceAcl
        retention_days = $RetentionDays
        log_retention_days = $LogRetentionDays
        candidates = @($candidates)
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $WhatIfSummaryPath -Encoding UTF8
}

[pscustomobject]@{
    command = "cleanup-generated-artifacts"
    applied = [bool]$Apply
    modes = @($selectedModes)
    force_acl = [bool]$ForceAcl
    retention_days = $RetentionDays
    log_retention_days = $LogRetentionDays
    candidate_count = @($candidates).Count
    applied_count = @($candidates | Where-Object { $_.applied }).Count
    archive_directory = if ($Apply -and (Test-Path -LiteralPath $runRoot)) {
        Get-RepoRelativePath -Path $runRoot
    }
    else {
        $null
    }
    dry_run_summary = if (-not $Apply -and -not [string]::IsNullOrWhiteSpace($WhatIfSummaryPath)) {
        Get-RepoRelativePath -Path $WhatIfSummaryPath
    }
    else {
        $null
    }
    candidates = @($candidates)
    execution_allowed = $false
    live_eligibility_status = "LIVE_ORDER_BLOCKED"
} | ConvertTo-Json -Depth 6
