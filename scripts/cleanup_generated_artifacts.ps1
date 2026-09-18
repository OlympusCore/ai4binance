param(
    [switch]$Apply,
    [switch]$IncludeCaches,
    [switch]$IncludeTestTemp,
    [switch]$IncludeLogs,
    [switch]$IncludeCoverage,
    [switch]$ForceAcl,
    [ValidateSet("Caches", "RuntimeCacheRetention", "RuntimeTestRetention", "RuntimeTmpRetention", "RuntimeRunRetention", "SourceGenerated", "TestTempRetention", "ProcessTempRetention", "LogsArchive", "Coverage", "All")]
    [string[]]$Mode = @(),
    [int]$RetentionDays = 2,
    [int]$LogRetentionDays = 7,
    [string]$WhatIfSummaryPath = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$archiveRoot = Join-Path $root "runtime\artifacts\maintenance_archive"
$testTempRoot = Join-Path $root "runtime\tmp\test_temp"
$runtimeArtifactLayoutManifestPath = Join-Path `
    $root "config\governance\runtime_artifact_layout_manifest.json"
if (-not (Test-Path -LiteralPath $runtimeArtifactLayoutManifestPath -PathType Leaf)) {
    throw "Runtime artifact layout manifest is unavailable: $runtimeArtifactLayoutManifestPath"
}
$runtimeArtifactLayout = Get-Content `
    -LiteralPath $runtimeArtifactLayoutManifestPath -Raw |
    ConvertFrom-Json
$processTempRelativePath = [string]$runtimeArtifactLayout.roots.tmp_process
if ($processTempRelativePath.Replace("\\", "/") -ne "runtime/tmp/process") {
    throw "Runtime artifact layout manifest must define tmp_process as runtime/tmp/process"
}
$processTempRoot = Join-Path $root ($processTempRelativePath.Replace("/", "\\"))
$pytestTempRelativePath = [string]$runtimeArtifactLayout.roots.tmp_process_pytest
if ($pytestTempRelativePath.Replace("\\", "/") -ne "runtime/tmp/process/pytest") {
    throw "Runtime artifact layout manifest must define tmp_process_pytest as runtime/tmp/process/pytest"
}
$pytestTempRoot = Join-Path $root ($pytestTempRelativePath.Replace("/", "\\"))
$legacyPytestTempRoot = Join-Path $root "runtime\tmp\pytest"
$runtimeTmpRoot = Join-Path $root "runtime\tmp"
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
    $fullPytestTempRoot = [System.IO.Path]::GetFullPath($pytestTempRoot)
    $fullLegacyPytestTempRoot = [System.IO.Path]::GetFullPath($legacyPytestTempRoot)
    $allowedPrefixes = @(
        $fullTestTempRoot,
        $fullPytestTempRoot,
        $fullLegacyPytestTempRoot
    )
    $rootEntries = @()
    if (Test-Path -LiteralPath $root -PathType Container) {
        $rootEntries += Get-ChildItem -LiteralPath $root -Force -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like ".pytest*" } |
            ForEach-Object { [System.IO.Path]::GetFullPath($_.FullName) }
    }
    $runtimeRoot = Join-Path $root "runtime"
    if (Test-Path -LiteralPath $runtimeRoot -PathType Container) {
        $rootEntries += Get-ChildItem -LiteralPath $runtimeRoot -Force -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "pytest*" } |
            ForEach-Object { [System.IO.Path]::GetFullPath($_.FullName) }
    }
    foreach ($entry in $rootEntries) {
        if (-not $allowedPrefixes.Contains($entry)) {
            $allowedPrefixes += $entry
        }
    }
    $isAllowed = $false
    foreach ($prefix in $allowedPrefixes) {
        if (
            $fullPath -eq $prefix -or
            $fullPath.StartsWith($prefix + "\", [System.StringComparison]::OrdinalIgnoreCase)
        ) {
            $isAllowed = $true
            break
        }
    }
    if (-not $isAllowed) {
        throw "Refusing ACL-forced cleanup outside approved pytest and test temp roots: $fullPath"
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
        Write-Warning "FORCE_ACL_REQUIRES_ELEVATED_POWERSHELL"
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

function Remove-ReparsePointChildren {
    param([Parameter(Mandatory = $true)][string]$Path)
    Get-ChildItem -LiteralPath $Path -Force -Recurse -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint } |
        Sort-Object FullName -Descending |
        ForEach-Object {
            $quotedPath = '"' + $_.FullName + '"'
            $command = "rmdir $quotedPath"
            $output = & cmd.exe /d /c $command 2>&1
            if ($LASTEXITCODE -ne 0 -and (Test-Path -LiteralPath $_.FullName)) {
                throw "cmd rmdir failed for reparse point: $($_.FullName) :: $($output -join '; ')"
            }
        }
}

function Remove-DirectoryViaMirrorFallback {
    param([Parameter(Mandatory = $true)][string]$Path)
    $parent = Split-Path -Parent $Path
    $empty = Join-Path $parent ("empty-cleanup-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $empty -Force | Out-Null
    try {
        $mirrorOutput = & robocopy.exe $empty $Path /MIR /R:1 /W:1 /NFL /NDL /NJH /NJS /NP 2>&1
        if ($LASTEXITCODE -ge 8) {
            throw "robocopy mirror failed for directory: $Path :: $($mirrorOutput -join '; ')"
        }
        if (Test-Path -LiteralPath $Path) {
            try {
                Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop -Confirm:$false
            }
            catch {
                if (Test-Path -LiteralPath $Path) {
                    throw
                }
            }
        }
    }
    finally {
        if (Test-Path -LiteralPath $empty) {
            Remove-Item -LiteralPath $empty -Recurse -Force -ErrorAction SilentlyContinue -Confirm:$false
        }
    }
}

function Remove-DirectoryArtifact {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][bool]$AllowAclForce
    )
    try {
        Remove-ReparsePointChildren -Path $Path
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop -Confirm:$false
    }
    catch {
        if (-not $AllowAclForce) {
            $quotedPath = '"' + $Path + '"'
            $command = "rmdir /s /q $quotedPath"
            $output = & cmd.exe /d /c $command 2>&1
            if ($LASTEXITCODE -ne 0 -and (Test-Path -LiteralPath $Path)) {
                Remove-DirectoryViaMirrorFallback -Path $Path
            }
            return
        }
        Grant-TestTempCleanupAccess -Path $Path
        try {
            Remove-ReparsePointChildren -Path $Path
        }
        catch {
            Write-Warning "Unable to remove reparse-point children before ACL cleanup: $Path :: $($_.Exception.Message)"
        }
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop -Confirm:$false
        }
        catch {
            Remove-DirectoryViaMirrorFallback -Path $Path
        }
        if (Test-Path -LiteralPath $Path) {
            Remove-DirectoryViaMirrorFallback -Path $Path
        }
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
$blockedCandidates = [System.Collections.Generic.List[object]]::new()
$activeProcessCommandLines = $null
$activeProcessInspectionFailed = $false
$selectedModes = [System.Collections.Generic.List[string]]::new()
foreach ($item in $Mode) {
    if ($item -eq "All") {
        foreach ($name in @("Caches", "RuntimeCacheRetention", "RuntimeTestRetention", "RuntimeTmpRetention", "RuntimeRunRetention", "SourceGenerated", "TestTempRetention", "ProcessTempRetention", "LogsArchive", "Coverage")) {
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
if ($IncludeTestTemp -and -not $selectedModes.Contains("ProcessTempRetention")) {
    $selectedModes.Add("ProcessTempRetention")
}
if ($IncludeLogs -and -not $selectedModes.Contains("LogsArchive")) {
    $selectedModes.Add("LogsArchive")
}
if ($IncludeCoverage -and -not $selectedModes.Contains("Coverage")) {
    $selectedModes.Add("Coverage")
}

if ($selectedModes.Contains("Caches")) {
    foreach ($relative in @(
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".test-tmp",
        ".tmp",
        ".tmp-alias-check"
    )) {
        $path = Join-Path $root $relative
        if (Test-Path -LiteralPath $path -PathType Container) {
            $candidates += New-CandidateRow -Path $path -Action "REMOVE_DIRECTORY" -Reason "REPRODUCIBLE_TOOL_CACHE"
        }
    }
}

if ($selectedModes.Contains("RuntimeCacheRetention")) {
    foreach ($relative in @("runtime\cache", "runtime\uv-cache")) {
        $cacheRoot = Join-Path $root $relative
        if (-not (Test-Path -LiteralPath $cacheRoot -PathType Container)) {
            continue
        }
        Get-ChildItem -LiteralPath $cacheRoot -Force |
            Where-Object {
                ($now - [DateTimeOffset]$_.LastWriteTimeUtc).TotalDays -ge $RetentionDays
            } |
            ForEach-Object {
                $action = if ($_.PSIsContainer) { "REMOVE_DIRECTORY" } else { "REMOVE_FILE" }
                $candidates += New-CandidateRow -Path $_.FullName -Action $action -Reason "STALE_REGENERABLE_RUNTIME_CACHE"
            }
    }
}

if ($selectedModes.Contains("RuntimeTestRetention")) {
    $runtimeTestRoot = Join-Path $root "runtime\test"
    if (Test-Path -LiteralPath $runtimeTestRoot -PathType Container) {
        Get-ChildItem -LiteralPath $runtimeTestRoot -Force |
            Where-Object {
                ($now - [DateTimeOffset]$_.LastWriteTimeUtc).TotalDays -ge $RetentionDays
            } |
            ForEach-Object {
                $action = if ($_.PSIsContainer) { "REMOVE_DIRECTORY" } else { "REMOVE_FILE" }
                $candidates += New-CandidateRow -Path $_.FullName -Action $action -Reason "STALE_RUNTIME_TEST_EVIDENCE"
            }
    }
}

function Get-LatestTreeWriteTimeUtc {
    param([Parameter(Mandatory = $true)][string]$Path)

    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    $latest = [DateTimeOffset]$item.LastWriteTimeUtc
    if (-not $item.PSIsContainer) {
        return $latest
    }
    Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction Stop |
        ForEach-Object {
            $modified = [DateTimeOffset]$_.LastWriteTimeUtc
            if ($modified -gt $latest) {
                $latest = $modified
            }
        }
    return $latest
}

function Test-PathReferencedByActiveProcess {
    param([Parameter(Mandatory = $true)][string]$Path)

    $resolved = Assert-InRepoPath -Path $Path
    if ($null -eq $script:activeProcessCommandLines) {
        try {
            $script:activeProcessCommandLines = @(
                Get-CimInstance Win32_Process -ErrorAction Stop |
                    ForEach-Object { [string]$_.CommandLine } |
                    Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
            )
        }
        catch {
            $script:activeProcessInspectionFailed = $true
            $script:activeProcessCommandLines = @()
        }
    }
    if ($script:activeProcessInspectionFailed) {
        return $true
    }
    foreach ($commandLine in $script:activeProcessCommandLines) {
            $normalizedCommandLine = $commandLine.Replace("/", "\")
            if (
                $normalizedCommandLine.IndexOf(
                    $resolved,
                    [System.StringComparison]::OrdinalIgnoreCase
                ) -ge 0
            ) {
                return $true
            }
    }
    return $false
}

function Test-GitMetadataPresent {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath (Join-Path $Path ".git")) {
        return $true
    }
    foreach (
        $child in Get-ChildItem `
            -LiteralPath $Path `
            -Directory `
            -Force `
            -ErrorAction SilentlyContinue
    ) {
        if (Test-Path -LiteralPath (Join-Path $child.FullName ".git")) {
            return $true
        }
    }
    return $false
}

function Test-ActiveProcessTempOwner {
    param([Parameter(Mandatory = $true)][string]$Path)

    $ownerPath = Join-Path $Path ".ai4binance-process-owner.json"
    if (-not (Test-Path -LiteralPath $ownerPath -PathType Leaf)) {
        return $false
    }
    try {
        $owner = Get-Content -LiteralPath $ownerPath -Raw | ConvertFrom-Json
        $expiresAt = [DateTimeOffset]::Parse([string]$owner.expires_at_utc)
        if ($expiresAt -le [DateTimeOffset]::UtcNow) {
            return $false
        }
        $ownerPid = [int]$owner.pid
        $process = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            return $false
        }
        $recordedStart = [string]$owner.process_started_at_utc
        if (-not [string]::IsNullOrWhiteSpace($recordedStart)) {
            $expectedStart = [DateTimeOffset]::Parse($recordedStart)
            $actualStart = [DateTimeOffset]$process.StartTime.ToUniversalTime()
            if ([Math]::Abs(($actualStart - $expectedStart).TotalSeconds) -gt 2) {
                return $false
            }
        }
        return $true
    }
    catch {
        # An unreadable ownership record fails closed to preserve a potentially active run.
        return $true
    }
}

function Add-BlockedCandidate {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Reason
    )
    $script:blockedCandidates.Add([pscustomobject]@{
        path = Get-RepoRelativePath -Path (Assert-InRepoPath -Path $Path)
        reason = $Reason
    })
}

if ($selectedModes.Contains("RuntimeTmpRetention")) {
    $policy = $runtimeArtifactLayout.retention.runtime_tmp
    if (
        $null -eq $policy -or
        [string]$policy.cleanup_mode -ne "RuntimeTmpRetention" -or
        -not [bool]$policy.automatic_cleanup
    ) {
        throw "Runtime temp retention policy is unavailable or not automatic"
    }
    $policyRoot = Assert-InRepoPath -Path (
        Join-Path $root ([string]$policy.path).Replace("/", "\\")
    )
    if ($policyRoot -ne [System.IO.Path]::GetFullPath($runtimeTmpRoot)) {
        throw "Runtime temp retention policy path must be runtime/tmp"
    }
    $minimumAgeDays = [int]$policy.minimum_age_days
    if ($minimumAgeDays -lt 1) {
        throw "Runtime temp retention minimum_age_days must be at least 1"
    }
    $protectedNames = @(".gitkeep", "process", "pytest", "test_temp")
    Get-ChildItem -LiteralPath $runtimeTmpRoot -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notin $protectedNames } |
        ForEach-Object {
            if ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                Add-BlockedCandidate `
                    -Path $_.FullName `
                    -Reason "RUNTIME_TMP_REPARSE_POINT_REVIEW_REQUIRED"
                return
            }
            try {
                $latest = Get-LatestTreeWriteTimeUtc -Path $_.FullName
            }
            catch {
                Add-BlockedCandidate `
                    -Path $_.FullName `
                    -Reason "RUNTIME_TMP_SCAN_FAILED"
                return
            }
            if (($now - $latest).TotalDays -lt $minimumAgeDays) {
                return
            }
            if ($_.PSIsContainer -and (Test-GitMetadataPresent -Path $_.FullName)) {
                Add-BlockedCandidate `
                    -Path $_.FullName `
                    -Reason "RUNTIME_TMP_GIT_WORKTREE_REVIEW_REQUIRED"
                return
            }
            if (
                $_.PSIsContainer -and
                (Test-ActiveProcessTempOwner -Path $_.FullName)
            ) {
                Add-BlockedCandidate `
                    -Path $_.FullName `
                    -Reason "RUNTIME_TMP_ACTIVE_OWNER"
                return
            }
            if (Test-PathReferencedByActiveProcess -Path $_.FullName) {
                Add-BlockedCandidate `
                    -Path $_.FullName `
                    -Reason "RUNTIME_TMP_ACTIVE_PROCESS_REFERENCE"
                return
            }
            $action = if ($_.PSIsContainer) { "REMOVE_DIRECTORY" } else { "REMOVE_FILE" }
            $candidates += New-CandidateRow `
                -Path $_.FullName `
                -Action $action `
                -Reason "STALE_UNOWNED_RUNTIME_TEMP"
        }
}

if ($selectedModes.Contains("RuntimeRunRetention")) {
    $policy = $runtimeArtifactLayout.retention.repository_validator_test_runs
    if (
        $null -eq $policy -or
        [string]$policy.cleanup_mode -ne "RuntimeRunRetention" -or
        -not [bool]$policy.automatic_cleanup
    ) {
        throw "Runtime run retention policy is unavailable or not automatic"
    }
    $runPolicyRoot = Assert-InRepoPath -Path (
        Join-Path $root ([string]$policy.path).Replace("/", "\\")
    )
    $expectedRunPolicyRoot = [System.IO.Path]::GetFullPath(
        (Join-Path $root "runtime\test\repository-validator\runs")
    )
    if ($runPolicyRoot -ne $expectedRunPolicyRoot) {
        throw (
            "Runtime run retention policy path must be " +
            "runtime/test/repository-validator/runs"
        )
    }
    $keepLatest = [int]$policy.keep_latest
    $minimumAgeDays = [int]$policy.minimum_age_days
    if ($keepLatest -lt 1 -or $minimumAgeDays -lt 1) {
        throw "Runtime run retention bounds must be at least 1"
    }
    if (Test-Path -LiteralPath $runPolicyRoot -PathType Container) {
        $runRows = @(
            Get-ChildItem -LiteralPath $runPolicyRoot -Directory -Force |
                ForEach-Object {
                    if (
                        $_.Attributes -band
                        [System.IO.FileAttributes]::ReparsePoint
                    ) {
                        Add-BlockedCandidate `
                            -Path $_.FullName `
                            -Reason "RUNTIME_RUN_REPARSE_POINT_REVIEW_REQUIRED"
                        return
                    }
                    [pscustomobject]@{
                        item = $_
                        latest = Get-LatestTreeWriteTimeUtc -Path $_.FullName
                    }
                } |
                Sort-Object latest -Descending
        )
        for ($index = $keepLatest; $index -lt $runRows.Count; $index++) {
            $row = $runRows[$index]
            if (($now - $row.latest).TotalDays -lt $minimumAgeDays) {
                continue
            }
            if (
                (Test-GitMetadataPresent -Path $row.item.FullName) -or
                (Test-ActiveProcessTempOwner -Path $row.item.FullName) -or
                (Test-PathReferencedByActiveProcess -Path $row.item.FullName)
            ) {
                Add-BlockedCandidate `
                    -Path $row.item.FullName `
                    -Reason "RUNTIME_RUN_ACTIVE_OR_PROTECTED"
                continue
            }
            $candidates += New-CandidateRow `
                -Path $row.item.FullName `
                -Action "REMOVE_DIRECTORY" `
                -Reason "STALE_RUNTIME_TEST_RUN"
        }
    }
}

if ($selectedModes.Contains("SourceGenerated")) {
    $sourceRoot = Join-Path $root "src"
    if (Test-Path -LiteralPath $sourceRoot -PathType Container) {
        Get-ChildItem -LiteralPath $sourceRoot -Force -Directory -Recurse -Filter "__pycache__" |
            ForEach-Object {
                $candidates += New-CandidateRow -Path $_.FullName -Action "REMOVE_DIRECTORY" -Reason "REPRODUCIBLE_SOURCE_GENERATED_ARTIFACT"
            }
        Get-ChildItem -LiteralPath $sourceRoot -Force -Directory -Recurse -Filter "*.egg-info" |
            ForEach-Object {
                $candidates += New-CandidateRow -Path $_.FullName -Action "REMOVE_DIRECTORY" -Reason "REPRODUCIBLE_SOURCE_GENERATED_ARTIFACT"
            }
        Get-ChildItem -LiteralPath $sourceRoot -Force -File -Recurse |
            Where-Object {
                $_.Extension -in @(".pyc", ".pyo") -and
                $_.FullName -notmatch "\\__pycache__\\"
            } |
            ForEach-Object {
                $candidates += New-CandidateRow -Path $_.FullName -Action "REMOVE_FILE" -Reason "REPRODUCIBLE_SOURCE_GENERATED_ARTIFACT"
            }
    }
    $runtimeTmpRoot = Join-Path $root "runtime\tmp"
    if (Test-Path -LiteralPath $runtimeTmpRoot -PathType Container) {
        Get-ChildItem -LiteralPath $runtimeTmpRoot -Force -Directory |
            Where-Object {
                $_.Name -like "debug_*" -or $_.Name -like "debug-*"
            } |
            ForEach-Object {
                $candidates += New-CandidateRow -Path $_.FullName -Action "REMOVE_DIRECTORY" -Reason "REPRODUCIBLE_RUNTIME_DEBUG_ARTIFACT"
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
    if (Test-Path -LiteralPath $legacyPytestTempRoot -PathType Container) {
        $candidates += New-CandidateRow -Path $legacyPytestTempRoot -Action "REMOVE_DIRECTORY" -Reason "LEGACY_PYTEST_TEMP"
    }
    Get-ChildItem -LiteralPath $root -Force -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like ".pytest*" } |
        ForEach-Object {
            $candidates += New-CandidateRow -Path $_.FullName -Action "REMOVE_DIRECTORY" -Reason "REPRODUCIBLE_PYTEST_TEMP"
        }
    $runtimeRoot = Join-Path $root "runtime"
    if (Test-Path -LiteralPath $runtimeRoot -PathType Container) {
        Get-ChildItem -LiteralPath $runtimeRoot -Force -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "pytest*" } |
            ForEach-Object {
                $candidates += New-CandidateRow -Path $_.FullName -Action "REMOVE_DIRECTORY" -Reason "REPRODUCIBLE_PYTEST_TEMP"
            }
    }
}

if ($selectedModes.Contains("ProcessTempRetention")) {
    if (Test-Path -LiteralPath $processTempRoot -PathType Container) {
        $processEntries = @(
            Get-ChildItem -LiteralPath $processTempRoot -Force |
                Where-Object { $_.Name -notin @(".gitkeep", "pytest") }
        )
        if (Test-Path -LiteralPath $pytestTempRoot -PathType Container) {
            $processEntries += @(
                Get-ChildItem -LiteralPath $pytestTempRoot -Force |
                    Where-Object { $_.Name -ne ".gitkeep" }
            )
        }
        $processEntries |
            ForEach-Object {
                try {
                    $latest = Get-LatestTreeWriteTimeUtc -Path $_.FullName
                }
                catch {
                    Add-BlockedCandidate `
                        -Path $_.FullName `
                        -Reason "PROCESS_TEMP_SCAN_FAILED"
                    return
                }
                if (($now - $latest).TotalDays -lt $RetentionDays) {
                    return
                }
                if ($_.PSIsContainer) {
                    if (Test-ActiveProcessTempOwner -Path $_.FullName) {
                        Add-BlockedCandidate `
                            -Path $_.FullName `
                            -Reason "PROCESS_TEMP_ACTIVE_OWNER"
                        return
                    }
                    if (Test-PathReferencedByActiveProcess -Path $_.FullName) {
                        Add-BlockedCandidate `
                            -Path $_.FullName `
                            -Reason "PROCESS_TEMP_ACTIVE_PROCESS_REFERENCE"
                        return
                    }
                    $candidates += New-CandidateRow `
                        -Path $_.FullName `
                        -Action "REMOVE_DIRECTORY" `
                        -Reason "STALE_PROCESS_TEMP"
                }
                else {
                    $candidates += New-CandidateRow `
                        -Path $_.FullName `
                        -Action "REMOVE_FILE" `
                        -Reason "STALE_PROCESS_TEMP"
                }
            }
    }
}

if ($selectedModes.Contains("LogsArchive")) {
    $logsRoot = Join-Path $root "runtime\logs"
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
                Remove-Item -LiteralPath $source -Force -Confirm:$false
                $row.applied = $true
                continue
            }
            if ($row.action -eq "REMOVE_DIRECTORY") {
                $allowAclForce = $ForceAcl -and $row.reason -in @(
                    "STALE_TEST_TEMP",
                    "REPRODUCIBLE_PYTEST_TEMP",
                    "LEGACY_PYTEST_TEMP"
                )
                Remove-DirectoryArtifact -Path $source -AllowAclForce $allowAclForce
                if ($allowAclForce) {
                    $row.forced_acl = $true
                }
                $row.applied = $true
                continue
            }
            if ($row.action -eq "REMOVE_FILE") {
                Remove-Item -LiteralPath $source -Force -Confirm:$false
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
        blocked_candidates = @($blockedCandidates)
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
        blocked_candidates = @($blockedCandidates)
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
    blocked_count = @($blockedCandidates).Count
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
    blocked_candidates = @($blockedCandidates)
    execution_allowed = $false
    live_eligibility_status = "LIVE_ORDER_BLOCKED"
} | ConvertTo-Json -Depth 6


