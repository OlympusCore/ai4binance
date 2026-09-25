param(
    [ValidateSet("fast", "standard", "full")]
    [string]$Profile = "full",
    [Alias("ApprovalRecordPath")]
    [string]$ApprovalRecordReportPath = "",
    [string]$ApprovalBy = "",
    [string[]]$ApprovalRoles = @(),
    [int]$ApprovalExpiryHours = 24
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$coverageReaderScript = Join-Path $PSScriptRoot "read_coverage_percent.py"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$qualityGateHashAlgorithm = [System.Security.Cryptography.SHA256]::Create()
try {
    $qualityGateMutexSuffix = [BitConverter]::ToString(
        $qualityGateHashAlgorithm.ComputeHash(
            [System.Text.Encoding]::UTF8.GetBytes($repoRoot.ToLowerInvariant())
        )
    ).Replace("-", "")
}
finally {
    $qualityGateHashAlgorithm.Dispose()
}
$qualityGateMutexName = "Local\AI4BinanceQualityGate-" + $qualityGateMutexSuffix
$qualityGateMutex = [System.Threading.Mutex]::new($false, $qualityGateMutexName)
$qualityGateMutexAcquired = $false
try {
    $qualityGateMutexAcquired = $qualityGateMutex.WaitOne(0)
}
catch [System.Threading.AbandonedMutexException] {
    $qualityGateMutexAcquired = $true
}
if (-not $qualityGateMutexAcquired) {
    $qualityGateMutex.Dispose()
    throw "QUALITY_GATE_ALREADY_RUNNING: concurrent quality runs are blocked to protect run-scoped coverage artifacts."
}
$pytestTempRoot = Join-Path $env:TEMP "pytest"
New-Item -ItemType Directory -Path $pytestTempRoot -Force | Out-Null
$dmypyStatusDirectory = Join-Path $repoRoot "runtime\tmp\dmypy"
New-Item -ItemType Directory -Path $dmypyStatusDirectory -Force | Out-Null
$dmypyStatusFile = Join-Path $dmypyStatusDirectory "dmypy.json"
$pytestTempRunId = [guid]::NewGuid().ToString("N")
$pytestTemp = Join-Path $pytestTempRoot ("ai4binance-pytest-" + $pytestTempRunId)
New-Item -ItemType Directory -Path $pytestTemp -Force | Out-Null
[ordered]@{
    schema_version = 1
    component = "pytest"
    run_id = $pytestTempRunId
    pid = $PID
    process_started_at_utc = (
        Get-Process -Id $PID -ErrorAction Stop
    ).StartTime.ToUniversalTime().ToString("o")
    expires_at_utc = [DateTimeOffset]::UtcNow.AddHours(6).ToString("o")
} | ConvertTo-Json | Set-Content `
    -LiteralPath (Join-Path $pytestTemp ".ai4binance-process-owner.json") `
    -Encoding UTF8
$coverageFile = Join-Path $pytestTemp ".coverage"
$coverageJsonPath = Join-Path $pytestTemp "coverage.json"
$pytestOutputPath = $null
$qualityEvidencePath = Join-Path $repoRoot "runtime\artifacts\quality\gate\latest.json"
$coveragePolicyConfigPath = Join-Path $repoRoot "config\quality\coverage-targets.json"
$coveragePolicySummaryPath = Join-Path $repoRoot "runtime\artifacts\quality\gate\coverage_summary.json"
$coveragePolicyMarkdownPath = Join-Path $repoRoot "runtime\artifacts\quality\gate\coverage_summary.md"
$qualityRuntimeDirectory = Join-Path $repoRoot "runtime\quality"
$qualityGateArtifactDirectory = Join-Path $repoRoot "runtime\artifacts\quality\gate"
$qualityGateProfileConfigPath = Join-Path $repoRoot "config\quality\gates.yaml"
$qualityPerformanceLatestPath = Join-Path $qualityGateArtifactDirectory "performance_latest.json"
$qualityPerformanceHistoryPath = Join-Path $qualityGateArtifactDirectory "performance_history.jsonl"
$qualityBudgetLatestPath = Join-Path $qualityGateArtifactDirectory "quality_budget_latest.json"
$qualityBudgetHistoryPath = Join-Path $qualityGateArtifactDirectory "quality_budget_history.jsonl"
$repositoryValidatorReportPath = Join-Path (
    $qualityGateArtifactDirectory
) "repository_validator_latest.json"
$deterministicQualityGateReportPath = Join-Path (
    $qualityGateArtifactDirectory
) "deterministic_quality_gate_latest.json"
$approvalRecordPath = Join-Path (
    $qualityGateArtifactDirectory
) "approval_record_latest.json"
$humanGovernanceClosureRequestPath = Join-Path (
    $qualityGateArtifactDirectory
) "c3_human_governance_closure_request_latest.json"
$humanGovernanceClosureRequestMarkdownPath = Join-Path (
    $qualityGateArtifactDirectory
) "c3_human_governance_closure_request_latest.md"
$governanceGateReportPath = Join-Path (
    $qualityGateArtifactDirectory
) "governance_gate_latest.json"
$repositoryValidatorRunStartedAt = Get-Date
$repositoryValidatorRunId = (
    $repositoryValidatorRunStartedAt.ToString("yyyyMMddTHHmmssK")
).Replace(":", "")
$repositoryValidatorRunRoot = Join-Path (
    $repoRoot
) "runtime\test\repository-validator\runs"
$repositoryValidatorRunDirectory = Join-Path (
    $repositoryValidatorRunRoot
) $repositoryValidatorRunId
$repositoryValidatorRunMetadataPath = Join-Path (
    $repositoryValidatorRunDirectory
) "metadata.json"
$repositoryValidatorRunResultPath = Join-Path (
    $repositoryValidatorRunDirectory
) "result.json"
$repositoryValidatorRunFindingsJsonPath = Join-Path (
    $repositoryValidatorRunDirectory
) "findings.json"
$repositoryValidatorRunPolicySnapshotPath = Join-Path (
    $repositoryValidatorRunDirectory
) "policy-snapshot.json"
$repositoryValidatorRunMarkdownPath = Join-Path (
    $repositoryValidatorRunDirectory
) "report.md"
$repositoryValidatorRunMigrationJsonPath = Join-Path (
    $repositoryValidatorRunDirectory
) "migration.json"
$repositoryValidatorRunMigrationMarkdownPath = Join-Path (
    $repositoryValidatorRunDirectory
) "migration.md"
$qualityRunTimestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$qualityRuntimeRunDirectory = Join-Path $qualityRuntimeDirectory $qualityRunTimestamp
$qualityRuntimeLatestPath = Join-Path $qualityRuntimeDirectory "latest.json"
$qualityRuntimeHistoryPath = Join-Path $qualityRuntimeDirectory "history.jsonl"
$qualityRuntimeRunSummaryPath = Join-Path $qualityRuntimeRunDirectory "summary.json"
$qualityRuntimeRunTimingsPath = Join-Path $qualityRuntimeRunDirectory "timings.json"
$qualityRuntimePytestLogPath = Join-Path $qualityRuntimeRunDirectory "pytest.log"
$qualityRuntimeBanditLogPath = Join-Path $qualityRuntimeRunDirectory "bandit.log"
$qualityRunDirectory = Join-Path (
    $qualityGateArtifactDirectory
) ("runs\" + $qualityRunTimestamp)
$qualityRunOutputPath = Join-Path (
    $qualityGateArtifactDirectory
) ("quality_run_" + $qualityRunTimestamp + ".md")
$qualityRunMetadataPath = Join-Path (
    $qualityGateArtifactDirectory
) ("quality_run_" + $qualityRunTimestamp + ".json")
$durablePytestOutputPath = Join-Path $qualityRunDirectory "pytest-output.txt"
$pytestOutputPath = $durablePytestOutputPath
$durableCoverageJsonPath = Join-Path $qualityRunDirectory "coverage.json"
$banditOutputPath = Join-Path $qualityRunDirectory "bandit-output.txt"
$approvalReplayGovernanceReportPath = Join-Path (
    $qualityRunDirectory
) "governance-gate-approval-required.json"
$approvalReplayQualityReportPath = Join-Path (
    $qualityRunDirectory
) "deterministic-quality-gate.json"
$approvalReplayValidatorReportPath = Join-Path (
    $qualityRunDirectory
) "repository-validator.json"
$durableCoverageSummaryPath = Join-Path (
    $qualityRunDirectory
) "coverage-summary.json"
$durableCoverageMarkdownPath = Join-Path (
    $qualityRunDirectory
) "coverage-summary.md"
$repositoryMutationEvidencePath = Join-Path (
    $qualityRuntimeRunDirectory
) "repository-mutation.json"
New-Item -ItemType Directory -Path $qualityRunDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $qualityRuntimeRunDirectory -Force | Out-Null
$mirrorManifestPath = Join-Path $repoRoot "runtime\artifacts\repository_validation\mirror\latest_inventory.json"
$mirrorHygieneReportPath = Join-Path $repoRoot "runtime\artifacts\repository_validation\mirror_hygiene_report.json"
$mirrorCleanupPlanPath = Join-Path $repoRoot "runtime\artifacts\repository_validation\mirror_cleanup_plan.json"
$repositoryValidatorPolicyPath = Join-Path $repoRoot "policies\repository-validator\manifest-policy.json"
$repositoryValidatorModulePath = Join-Path $repoRoot "src\ai4binance\governance\repository_validator.py"
$qualityGateScriptPath = $PSCommandPath
$repositoryValidatorCacheDirectory = Join-Path (
    $repoRoot
) "runtime\cache\quality\repository-validator"
$repositoryValidatorCacheMetadataPath = Join-Path (
    $repositoryValidatorCacheDirectory
) "metadata.json"
$repositoryValidatorCacheResultPath = Join-Path (
    $repositoryValidatorCacheDirectory
) "result.json"
$repositoryValidatorCacheFindingsPath = Join-Path (
    $repositoryValidatorCacheDirectory
) "findings.json"
$repositoryValidatorCachePolicySnapshotPath = Join-Path (
    $repositoryValidatorCacheDirectory
) "policy-snapshot.json"
$repositoryValidatorCacheMirrorManifestPath = Join-Path (
    $repositoryValidatorCacheDirectory
) "mirror-manifest.json"
$repositoryValidatorCacheMarkdownPath = Join-Path (
    $repositoryValidatorCacheDirectory
) "report.md"
$repositoryValidatorCacheMigrationMarkdownPath = Join-Path (
    $repositoryValidatorCacheDirectory
) "migration.md"
$mirrorRemoteCheck = "NOT_VERIFIED"
$qualityRunStatus = "RUNNING"
$qualityRunCurrentStep = "INITIALIZING"
$qualityRunError = $null
$qualityRunFailedStep = $null
$qualityGateExitCode = 0
$previousPythonDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
$previousPythonPath = $env:PYTHONPATH
$script:qualityInvocationParameters = @{} + $PSBoundParameters
$script:cachedRepositoryValidatorReport = $null
$script:cachedGovernanceGateReport = $null
$script:qualityGateProfile = $Profile.ToLowerInvariant()
$script:qualityStepExitCodes = [ordered]@{}
$script:qualityStepTelemetry = @()
$script:qualityRunStartedAtUtc = [DateTimeOffset]::UtcNow
$script:qualityRunStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$script:pytestExitCode = $null
$script:pytestEvidencePath = $null
$script:pytestEvidenceSha256 = $null
$script:pytestOutputTail = $null
$script:qualitySelectedPytestArguments = @()
$script:qualityInitialWorkspaceAttestation = $null
$script:qualityGateGitWriteLeasePath = $null
$script:qualityReplayPytestPassCount = $null
$script:qualityReplayCoveragePercent = $null
$script:repositoryValidatorCacheStatus = "NOT_EVALUATED"
$script:repositoryValidatorCacheReason = "repository validator cache has not been evaluated"
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
    (Join-Path $repoRoot "src")
} else {
    (Join-Path $repoRoot "src") + [IO.Path]::PathSeparator + $previousPythonPath
}
$env:PYTHONDONTWRITEBYTECODE = "1"

function Get-QualityCommandText {
    $parts = @(
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        ".\scripts\quality.ps1"
    )
    $parts += @("-Profile", $script:qualityGateProfile)
    if (-not [string]::IsNullOrWhiteSpace($ApprovalRecordReportPath)) {
        $parts += @("-ApprovalRecordPath", $ApprovalRecordReportPath)
    }
    return $parts -join " "
}

function Get-QualityProfileVerificationStatus {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Status
    )

    if ($Status -eq "QUALITY_GATE_FAILED") {
        return "NOT_VERIFIED"
    }
    if ($script:qualityGateProfile -eq "fast") {
        return "FAST_VERIFIED"
    }
    if ($script:qualityGateProfile -eq "standard") {
        return "STANDARD_VERIFIED"
    }
    return "FULL_VERIFIED"
}

function Remove-ApprovalRecordArtifact {
    if (Test-Path -LiteralPath $approvalRecordPath -PathType Leaf) {
        Remove-Item -LiteralPath $approvalRecordPath -Force
    }
}

function Assert-NoInlineApprovalGenerationRequested {
    if ($script:qualityInvocationParameters.ContainsKey("ApprovalBy")) {
        throw (
            "Inline approval generation is no longer allowed. " +
            "Provide -ApprovalRecordPath to an independently prepared approval artifact."
        )
    }
    if ($script:qualityInvocationParameters.ContainsKey("ApprovalRoles")) {
        throw (
            "Inline approval role synthesis is no longer allowed. " +
            "Provide -ApprovalRecordPath to an independently prepared approval artifact."
        )
    }
    if ($script:qualityInvocationParameters.ContainsKey("ApprovalExpiryHours")) {
        throw (
            "Inline approval expiry synthesis is no longer allowed. " +
            "Provide -ApprovalRecordPath to an independently prepared approval artifact."
        )
    }
}

function Resolve-ApprovalRecordPathForGovernanceGate {
    if ([string]::IsNullOrWhiteSpace($ApprovalRecordReportPath)) {
        return $null
    }
    $candidate = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath(
        $ApprovalRecordReportPath
    )
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Approval record artifact was not found: $ApprovalRecordReportPath"
    }
    return $candidate
}

function Write-HumanGovernanceClosureRequestArtifact {
    if (-not (Test-Path -LiteralPath $governanceGateReportPath -PathType Leaf)) {
        throw "Human governance closure request requires governance gate report"
    }
    $closureRequestScript = Join-Path `
        $PSScriptRoot `
        "prepare_c3_human_governance_closure_request.py"
    if (-not (Test-Path -LiteralPath $closureRequestScript -PathType Leaf)) {
        throw "Closure request preparation script was not found: $closureRequestScript"
    }
    $frozenArtifacts = @(
        [ordered]@{
            source = $governanceGateReportPath
            destination = $approvalReplayGovernanceReportPath
        },
        [ordered]@{
            source = $deterministicQualityGateReportPath
            destination = $approvalReplayQualityReportPath
        },
        [ordered]@{
            source = $repositoryValidatorReportPath
            destination = $approvalReplayValidatorReportPath
        },
        [ordered]@{
            source = $coveragePolicySummaryPath
            destination = $durableCoverageSummaryPath
        },
        [ordered]@{
            source = $coveragePolicyMarkdownPath
            destination = $durableCoverageMarkdownPath
        }
    )
    foreach ($artifact in $frozenArtifacts) {
        if (-not (Test-Path -LiteralPath $artifact.source -PathType Leaf)) {
            throw "Approval replay source artifact is missing: $($artifact.source)"
        }
        Copy-Item `
            -LiteralPath $artifact.source `
            -Destination $artifact.destination `
            -Force
    }
    & $python `
        $closureRequestScript `
        "--repository-root" `
        $repoRoot `
        "--governance-gate-report" `
        $approvalReplayGovernanceReportPath `
        "--output-json" `
        $humanGovernanceClosureRequestPath `
        "--output-markdown" `
        $humanGovernanceClosureRequestMarkdownPath |
        Out-Null
    if (-not $?) {
        $exitCode = if ($null -eq $LASTEXITCODE) { -1 } else { $LASTEXITCODE }
        throw "Closure request preparation failed with exit code $exitCode"
    }
}

function Remove-GeneratedCoverageArtifacts {
    $coverageCandidates = @(
        (Join-Path $repoRoot ".coverage"),
        (Join-Path $repoRoot "coverage.xml")
    )
    foreach ($candidate in $coverageCandidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            Remove-Item -LiteralPath $candidate -Force
        }
    }
    Get-ChildItem -LiteralPath $repoRoot -Force -File -Filter ".coverage.*" |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Force
        }
    $htmlCoverage = Join-Path $repoRoot "htmlcov"
    if (Test-Path -LiteralPath $htmlCoverage -PathType Container) {
        Remove-Item -LiteralPath $htmlCoverage -Recurse -Force
    }
}

function Invoke-CleanupScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [hashtable]$Arguments
    )

    $cleanupScript = Join-Path $PSScriptRoot "cleanup_generated_artifacts.ps1"
    $stepStartedAtUtc = [DateTimeOffset]::UtcNow
    $stepStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $exitCode = $null
    $stepStatus = "ERROR"
    $stepId = ConvertTo-QualityStepId -Name $Name
    $stepOutputPath = Join-Path $qualityRunDirectory ($stepId + "-output.txt")
    $stepArtifactPath = (
        "runtime\artifacts\quality\gate\runs\" +
        $qualityRunTimestamp +
        "\" +
        $stepId +
        "-output.txt"
    )
    try {
        $global:LASTEXITCODE = 0
        Remove-Item -LiteralPath $stepOutputPath -Force -ErrorAction SilentlyContinue
        & $cleanupScript @Arguments *> $stepOutputPath
        $invocationSucceeded = $?
        if ($invocationSucceeded) {
            $exitCode = 0
        }
        else {
            $exitCode = $LASTEXITCODE
            if ($null -eq $exitCode) {
                $exitCode = -1
            }
        }
        if (-not $invocationSucceeded) {
            $stepStatus = "FAIL"
            throw "$Name failed with exit code $exitCode. Evidence: $stepArtifactPath"
        }
        $stepStatus = "PASS"
    }
    finally {
        Add-QualityStepTelemetry `
            -Name $Name `
            -StartedAtUtc $stepStartedAtUtc `
            -Stopwatch $stepStopwatch `
            -ExitCode $exitCode `
            -Status $stepStatus `
            -OutputPath $stepOutputPath `
            -ArtifactPath $stepArtifactPath
    }
}

function Invoke-GeneratedArtifactCleanup {
    $arguments = @{
        Apply = $true
        Mode = @("Coverage", "SourceGenerated")
    }
    Invoke-CleanupScript -Name "Generated artifact cleanup" -Arguments $arguments
}

function Test-IsWindowsAdministrator {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [System.Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole(
        [System.Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

function Invoke-TestTempRetentionCleanup {
    $arguments = @{
        Apply = $true
        Mode = @("TestTempRetention")
    }
    if (Test-IsWindowsAdministrator) {
        $arguments["ForceAcl"] = $true
    }
    Invoke-CleanupScript -Name "Test temp retention cleanup" -Arguments $arguments
}

function Invoke-ProcessTempRetentionCleanup {
    $arguments = @{
        Apply = $true
        Mode = @("ProcessTempRetention")
    }
    Invoke-CleanupScript -Name "Process temp retention cleanup" -Arguments $arguments
}

function Invoke-SourceGeneratedArtifactCleanup {
    $arguments = @{
        Apply = $true
        Mode = @("SourceGenerated")
    }
    Invoke-CleanupScript -Name "Source-generated artifact cleanup" -Arguments $arguments
}

function Invoke-QualityStepWithAllowedExitCodes {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [int[]]$AllowedExitCodes = @(0),
        [hashtable]$StatusByExitCode = @{}
    )

    $stepStartedAtUtc = [DateTimeOffset]::UtcNow
    $stepStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $exitCode = $null
    $stepStatus = "ERROR"
    $stepId = ConvertTo-QualityStepId -Name $Name
    $stepOutputPath = Join-Path $qualityRunDirectory ($stepId + "-output.txt")
    $stepArtifactPath = (
        "runtime\artifacts\quality\gate\runs\" +
        $qualityRunTimestamp +
        "\" +
        $stepId +
        "-output.txt"
    )
    try {
        $script:qualityRunCurrentStep = $Name
        Write-QualityRunMetadata -Status "RUNNING" -CurrentStep $script:qualityRunCurrentStep
        Remove-Item -LiteralPath $stepOutputPath -Force -ErrorAction SilentlyContinue
        & $python -B @Arguments *> $stepOutputPath
        $exitCode = $LASTEXITCODE
        $script:qualityStepExitCodes[$Name] = $exitCode
        if ($AllowedExitCodes -notcontains $exitCode) {
            $stepStatus = "FAIL"
            throw "$Name failed with exit code $exitCode. Evidence: $stepArtifactPath"
        }
        if ($StatusByExitCode.ContainsKey($exitCode)) {
            $stepStatus = [string]$StatusByExitCode[$exitCode]
        }
        else {
            $stepStatus = "PASS"
        }
        return $exitCode
    }
    finally {
        Add-QualityStepTelemetry `
            -Name $Name `
            -StartedAtUtc $stepStartedAtUtc `
            -Stopwatch $stepStopwatch `
            -ExitCode $exitCode `
            -Status $stepStatus `
            -OutputPath $stepOutputPath `
            -ArtifactPath $stepArtifactPath
        Write-QualityRunMetadata -Status "RUNNING" -CurrentStep $script:qualityRunCurrentStep
    }
}

function Invoke-QualityStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    [void](Invoke-QualityStepWithAllowedExitCodes `
        -Name $Name `
        -Arguments $Arguments `
        -AllowedExitCodes @(0))
}

function Reset-DmypyStatusFile {
    if (Test-Path -LiteralPath $dmypyStatusFile -PathType Leaf) {
        Remove-Item -LiteralPath $dmypyStatusFile -Force -ErrorAction SilentlyContinue
    }
}

function Test-PytestSelectionArgument {
    param([Parameter(Mandatory = $true)][string]$Argument)

    return (
        $Argument.EndsWith(".py", [System.StringComparison]::OrdinalIgnoreCase) -or
        $Argument.Contains(".py::")
    )
}

function Get-FileTailText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [int64]$MaxBytes = 65536
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }

    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
    $fileInfo = Get-Item -LiteralPath $resolvedPath
    if ($fileInfo.Length -le 0) {
        return ""
    }

    $prefixLength = [Math]::Min($fileInfo.Length, 4)
    $prefix = [byte[]]::new([int]$prefixLength)
    $prefixStream = [System.IO.File]::Open(
        $resolvedPath,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite
    )
    try {
        [void]$prefixStream.Read($prefix, 0, [int]$prefixLength)
    }
    finally {
        $prefixStream.Dispose()
    }

    $usesWideEncoding = (
        ($prefixLength -ge 2 -and $prefix[0] -eq 0xff -and $prefix[1] -eq 0xfe) -or
        ($prefixLength -ge 2 -and $prefix[0] -eq 0xfe -and $prefix[1] -eq 0xff) -or
        ($prefixLength -ge 4 -and
            $prefix[0] -eq 0xff -and
            $prefix[1] -eq 0xfe -and
            $prefix[2] -eq 0x00 -and
            $prefix[3] -eq 0x00) -or
        ($prefixLength -ge 4 -and
            $prefix[0] -eq 0x00 -and
            $prefix[1] -eq 0x00 -and
            $prefix[2] -eq 0xfe -and
            $prefix[3] -eq 0xff)
    )
    if ($usesWideEncoding) {
        $reader = [System.IO.StreamReader]::new($resolvedPath, $true)
        try {
            $text = $reader.ReadToEnd()
        }
        finally {
            $reader.Dispose()
        }
        if ($text.Length -gt $MaxBytes) {
            return $text.Substring($text.Length - [int]$MaxBytes)
        }
        return $text
    }

    $bytesToRead = [Math]::Min($fileInfo.Length, $MaxBytes)
    $buffer = [byte[]]::new([int]$bytesToRead)
    $stream = [System.IO.File]::Open(
        $resolvedPath,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite
    )
    try {
        if ($fileInfo.Length -gt $bytesToRead) {
            [void]$stream.Seek(-1 * $bytesToRead, [System.IO.SeekOrigin]::End)
        }
        $bytesRead = $stream.Read($buffer, 0, [int]$bytesToRead)
    }
    finally {
        $stream.Dispose()
    }

    if ($bytesRead -le 0) {
        return ""
    }

    $text = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $bytesRead)
    if ($fileInfo.Length -gt $bytesToRead) {
        $firstNewlineIndex = $text.IndexOf("`n")
        if ($firstNewlineIndex -ge 0 -and ($firstNewlineIndex + 1) -lt $text.Length) {
            $text = $text.Substring($firstNewlineIndex + 1)
        }
    }
    return $text
}

function Protect-QualityConsoleText {
    param([AllowEmptyString()][string]$Value = "")

    return [regex]::Replace(
        $Value,
        '(?i)(api[_-]?key|secret|token|password|authorization)(\s*[:=]\s*)(\S+)',
        '$1$2[REDACTED]'
    )
}

function Get-FirstActionableQualityError {
    param(
        [AllowEmptyString()][string]$Value = "",
        [int]$MaxCharacters = 500
    )

    $sanitized = Protect-QualityConsoleText -Value $Value
    $lines = @($sanitized -split "`r?`n")
    $actionablePattern = '(error|failed|traceback|assertionerror|^\s*>>\s*issue:)'
    $actionableOptions = (
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase -bor
        [System.Text.RegularExpressions.RegexOptions]::CultureInvariant
    )
    $candidate = $lines |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace($_) -and
            [regex]::IsMatch(
                [string]$_,
                $actionablePattern,
                $actionableOptions
            )
        } |
        Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        $candidate = $lines |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            Select-Object -First 1
    }
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        return ""
    }
    $candidate = $candidate.Trim()
    if ($candidate.Length -gt $MaxCharacters) {
        return $candidate.Substring(0, $MaxCharacters)
    }
    return $candidate
}

function ConvertTo-QualityStepId {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $normalized = $Name.Trim().ToLowerInvariant() -replace "[^a-z0-9]+", "_"
    return $normalized.Trim("_")
}

function Get-QualityRunDurationMs {
    if ($null -eq $script:qualityRunStopwatch) {
        return $null
    }
    return [int64]$script:qualityRunStopwatch.ElapsedMilliseconds
}

function Get-FileSizeBytes {
    param(
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $null
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    return [int64](Get-Item -LiteralPath $Path).Length
}

function ConvertTo-CompactQualityStepSummary {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Step
    )

    return [ordered]@{
        step_id = $Step.step_id
        status = $Step.status
        wall_time_ms = $Step.wall_time_ms
        exit_code = $Step.exit_code
        artifact_path = $Step.artifact_path
    }
}

function Add-QualityStepTelemetry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [DateTimeOffset]$StartedAtUtc,
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Stopwatch]$Stopwatch,
        [int]$ExitCode = -1,
        [Parameter(Mandatory = $true)]
        [string]$Status,
        [string]$OutputPath,
        [string]$ArtifactPath,
        [string]$CacheMode = "UNMEASURED"
    )

    if ($Stopwatch.IsRunning) {
        $Stopwatch.Stop()
    }
    $endedAtUtc = [DateTimeOffset]::UtcNow
    $outputTail = Get-FileTailText -Path $OutputPath -MaxBytes 16384
    $outputDigest = if (
        -not [string]::IsNullOrWhiteSpace($OutputPath) -and
        (Test-Path -LiteralPath $OutputPath -PathType Leaf)
    ) {
        Get-Sha256Hex -Path $OutputPath
    }
    else {
        ""
    }
    $actionableError = if ($Status -in @("PASS", "PASSED")) {
        ""
    }
    else {
        Get-FirstActionableQualityError -Value $outputTail
    }
    $script:qualityStepTelemetry += [ordered]@{
        step_id = ConvertTo-QualityStepId -Name $Name
        name = $Name
        started_at_utc = $StartedAtUtc.ToString("o")
        ended_at_utc = $endedAtUtc.ToString("o")
        wall_time_ms = [int64]$Stopwatch.ElapsedMilliseconds
        exit_code = $ExitCode
        status = $Status
        output_bytes = Get-FileSizeBytes -Path $OutputPath
        artifact_path = $ArtifactPath
        output_sha256 = $outputDigest
        first_actionable_error = $actionableError
        cache_mode = $CacheMode
    }
}

function Get-Sha256String {
    param([Parameter(Mandatory = $true)][string]$Value)

    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        $hashBytes = $algorithm.ComputeHash($bytes)
    }
    finally {
        $algorithm.Dispose()
    }
    return [System.BitConverter]::ToString($hashBytes).
        Replace("-", "").
        ToLowerInvariant()
}

function Get-CachedJsonArtifact {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$CacheVariableName
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Set-Variable -Scope Script -Name $CacheVariableName -Value $null
        return $null
    }

    $item = Get-Item -LiteralPath $Path
    $cache = Get-Variable `
        -Scope Script `
        -Name $CacheVariableName `
        -ValueOnly `
        -ErrorAction SilentlyContinue
    if (
        $null -ne $cache -and
        $cache.path -eq $item.FullName -and
        $cache.length -eq $item.Length -and
        $cache.last_write_time_utc_ticks -eq $item.LastWriteTimeUtc.Ticks
    ) {
        return $cache.payload
    }

    $payload = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    Set-Variable -Scope Script -Name $CacheVariableName -Value (
        [pscustomobject]@{
            path = $item.FullName
            length = $item.Length
            last_write_time_utc_ticks = $item.LastWriteTimeUtc.Ticks
            payload = $payload
        }
    )
    return $payload
}

function Get-PytestPassCount {
    if ($null -ne $script:qualityReplayPytestPassCount) {
        return [int]$script:qualityReplayPytestPassCount
    }
    $pytestOutputTail = Get-FileTailText -Path $pytestOutputPath
    if ($null -eq $pytestOutputTail) {
        return $null
    }

    $matches = [regex]::Matches($pytestOutputTail, "(\d+)\s+passed")
    if ($matches.Count -eq 0) {
        return $null
    }
    return [int]$matches[$matches.Count - 1].Groups[1].Value
}

function Get-CoveragePercent {
    if ($null -ne $script:qualityReplayCoveragePercent) {
        return [double]$script:qualityReplayCoveragePercent
    }
    if (-not (Test-Path -LiteralPath $coverageJsonPath -PathType Leaf)) {
        return $null
    }
    $coverageValue = & $python -B $coverageReaderScript $coverageJsonPath
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    return [double]$coverageValue
}

function Get-CoveragePolicySummary {
    $summaryPath = $durableCoverageSummaryPath
    if (-not (Test-Path -LiteralPath $summaryPath -PathType Leaf)) {
        $summaryPath = $coveragePolicySummaryPath
    }
    if (-not (Test-Path -LiteralPath $summaryPath -PathType Leaf)) {
        return $null
    }
    return Get-Content -LiteralPath $summaryPath -Raw |
        ConvertFrom-Json
}

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "SHA256 source is missing: $Path"
    }

    $hashCommand = Get-Command -Name "Get-FileHash" -ErrorAction SilentlyContinue
    if ($null -ne $hashCommand) {
        return (
            Get-FileHash -LiteralPath $Path -Algorithm SHA256
        ).Hash.ToLowerInvariant()
    }

    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
    $stream = [System.IO.File]::OpenRead($resolvedPath)
    try {
        $algorithm = [System.Security.Cryptography.SHA256]::Create()
        try {
            $hashBytes = $algorithm.ComputeHash($stream)
        }
        finally {
            $algorithm.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }

    return [System.BitConverter]::ToString($hashBytes).
        Replace("-", "").
        ToLowerInvariant()
}

function Get-CoverageRealismProof {
    if (-not (Test-Path -LiteralPath $coveragePolicyMarkdownPath -PathType Leaf)) {
        return $null
    }
    return [ordered]@{
        markdown_path = "runtime\artifacts\quality\gate\coverage_summary.md"
        markdown_sha256 = Get-Sha256Hex -Path $coveragePolicyMarkdownPath
        evidence_type = "GOVERNED_MARKDOWN_COVERAGE_REALISM_PROOF"
    }
}

function Get-RepositoryRelativeArtifactPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $rootPrefix = (Resolve-Path -LiteralPath $repoRoot).Path.TrimEnd("\", "/")
    if ($resolved.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        return $resolved.Substring($rootPrefix.Length).TrimStart("\", "/")
    }
    throw "Artifact path is outside repository root: $Path"
}

function Get-ArtifactLineage {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$EvidenceSource
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Artifact lineage source is missing: $Path"
    }
    return [ordered]@{
        evidence_source = $EvidenceSource
        evidence_path = Get-RepositoryRelativeArtifactPath -Path $Path
        evidence_sha256 = Get-Sha256Hex -Path $Path
    }
}

function Get-PytestEvidenceArtifactPath {
    if (Test-Path -LiteralPath $durablePytestOutputPath -PathType Leaf) {
        return $durablePytestOutputPath
    }
    if (Test-Path -LiteralPath $pytestOutputPath -PathType Leaf) {
        return $pytestOutputPath
    }
    throw "Pytest evidence artifact is missing."
}

function Publish-QualityRunEvidenceArtifacts {
    New-Item -ItemType Directory -Path $qualityRunDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path $qualityRuntimeRunDirectory -Force | Out-Null
    $requiredCoverageArtifacts = @(
        $coverageJsonPath,
        $coveragePolicySummaryPath,
        $coveragePolicyMarkdownPath
    )
    foreach ($artifactPath in $requiredCoverageArtifacts) {
        if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
            throw "Coverage evidence artifact is missing: $artifactPath"
        }
    }
    if (-not [string]::Equals(
            $pytestOutputPath,
            $durablePytestOutputPath,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        Copy-Item -LiteralPath $pytestOutputPath -Destination $durablePytestOutputPath -Force
    }
    Copy-Item -LiteralPath $coverageJsonPath -Destination $durableCoverageJsonPath -Force
    Copy-Item `
        -LiteralPath $coveragePolicySummaryPath `
        -Destination $durableCoverageSummaryPath `
        -Force
    Copy-Item `
        -LiteralPath $coveragePolicyMarkdownPath `
        -Destination $durableCoverageMarkdownPath `
        -Force
    if (Test-Path -LiteralPath $durablePytestOutputPath -PathType Leaf) {
        Copy-Item -LiteralPath $durablePytestOutputPath -Destination $qualityRuntimePytestLogPath -Force
    }
}

function Publish-PytestEvidenceArtifact {
    if (-not (Test-Path -LiteralPath $pytestOutputPath -PathType Leaf)) {
        return
    }
    New-Item -ItemType Directory -Path $qualityRunDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path $qualityRuntimeRunDirectory -Force | Out-Null
    if (-not [string]::Equals(
            $pytestOutputPath,
            $durablePytestOutputPath,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        Copy-Item -LiteralPath $pytestOutputPath -Destination $durablePytestOutputPath -Force
    }
    $script:pytestEvidencePath = Get-RepositoryRelativeArtifactPath `
        -Path $durablePytestOutputPath
    $script:pytestEvidenceSha256 = Get-Sha256Hex -Path $durablePytestOutputPath
    $script:pytestOutputTail = Get-FileTailText `
        -Path $durablePytestOutputPath `
        -MaxBytes 16384
    Copy-Item -LiteralPath $durablePytestOutputPath -Destination $qualityRuntimePytestLogPath -Force
}

function Invoke-PytestWithCapturedOutput {
    $previousPythonDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $arguments = @(
        "-m",
        "pytest",
        "--basetemp",
        $pytestTemp,
        "--cov=ai4binance",
        "--cov-report=",
        "--durations=30",
        "--durations-min=0.5"
    )
    $stepStartedAtUtc = [DateTimeOffset]::UtcNow
    $stepStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $exitCode = $null
    $stepStatus = "ERROR"
    $script:qualityRunCurrentStep = "Pytest"
    $script:qualitySelectedPytestArguments = @("FULL_TEST_SUITE")
    Write-QualityRunMetadata -Status "RUNNING" -CurrentStep $script:qualityRunCurrentStep
    New-Item -ItemType Directory -Path $qualityRunDirectory -Force | Out-Null
    Remove-Item -LiteralPath $pytestOutputPath -Force -ErrorAction SilentlyContinue
    try {
        & $python -B @arguments *> $pytestOutputPath
        $exitCode = $LASTEXITCODE
        $script:pytestExitCode = $exitCode
        $script:qualityStepExitCodes["Pytest"] = $exitCode
        Publish-PytestEvidenceArtifact
        if ($exitCode -ne 0) {
            $stepStatus = "FAIL"
            throw "Pytest failed with exit code $exitCode. Evidence: $script:pytestEvidencePath"
        }
        $stepStatus = "PASS"
    }
    finally {
        Add-QualityStepTelemetry `
            -Name "Pytest" `
            -StartedAtUtc $stepStartedAtUtc `
            -Stopwatch $stepStopwatch `
            -ExitCode $exitCode `
            -Status $stepStatus `
            -OutputPath $durablePytestOutputPath `
            -ArtifactPath $script:pytestEvidencePath
        Write-QualityRunMetadata -Status "RUNNING" -CurrentStep $script:qualityRunCurrentStep
        if ($null -eq $previousPythonDontWriteBytecode) {
            Remove-Item Env:\PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
        }
        else {
            $env:PYTHONDONTWRITEBYTECODE = $previousPythonDontWriteBytecode
        }
    }
}

function Invoke-ScopedPytestWithCapturedOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string[]]$PytestArguments
    )

    $previousPythonDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $arguments = @("-m", "pytest") + $PytestArguments + @(
        "--basetemp",
        $pytestTemp,
        "--durations=20",
        "--durations-min=0.5"
    )
    $script:qualitySelectedPytestArguments = @($PytestArguments)
    $stepStartedAtUtc = [DateTimeOffset]::UtcNow
    $stepStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $exitCode = $null
    $stepStatus = "ERROR"
    $script:qualityRunCurrentStep = $Name
    Write-QualityRunMetadata -Status "RUNNING" -CurrentStep $script:qualityRunCurrentStep
    New-Item -ItemType Directory -Path $qualityRunDirectory -Force | Out-Null
    Remove-Item -LiteralPath $pytestOutputPath -Force -ErrorAction SilentlyContinue
    try {
        & $python -B @arguments *> $pytestOutputPath
        $exitCode = $LASTEXITCODE
        $script:pytestExitCode = $exitCode
        $script:qualityStepExitCodes[$Name] = $exitCode
        Publish-PytestEvidenceArtifact
        if ($exitCode -ne 0) {
            $stepStatus = "FAIL"
            throw "$Name failed with exit code $exitCode. Evidence: $script:pytestEvidencePath"
        }
        $stepStatus = "PASS"
    }
    finally {
        Add-QualityStepTelemetry `
            -Name $Name `
            -StartedAtUtc $stepStartedAtUtc `
            -Stopwatch $stepStopwatch `
            -ExitCode $exitCode `
            -Status $stepStatus `
            -OutputPath $durablePytestOutputPath `
            -ArtifactPath $script:pytestEvidencePath
        Write-QualityRunMetadata -Status "RUNNING" -CurrentStep $script:qualityRunCurrentStep
        if ($null -eq $previousPythonDontWriteBytecode) {
            Remove-Item Env:\PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
        }
        else {
            $env:PYTHONDONTWRITEBYTECODE = $previousPythonDontWriteBytecode
        }
    }
}

function Get-ChangedRepositoryPaths {
    $gitChangedPathsErrorPath = Join-Path $qualityRunDirectory "git-changed-paths-error.txt"
    $gitChangedPathsArtifactPath = (
        "runtime\artifacts\quality\gate\runs\" +
        $qualityRunTimestamp +
        "\git-changed-paths-error.txt"
    )
    Remove-Item `
        -LiteralPath $gitChangedPathsErrorPath `
        -Force `
        -ErrorAction SilentlyContinue
    $previousErrorActionPreference = $ErrorActionPreference
    $changed = @()
    $untracked = @()
    $diffExitCode = -1
    $untrackedExitCode = -1
    try {
        $ErrorActionPreference = "Continue"
        $changed = @(
            & git -C $repoRoot diff --name-only HEAD -- `
                2>> $gitChangedPathsErrorPath
        )
        $diffExitCode = $LASTEXITCODE
        if ($diffExitCode -eq 0) {
            $untracked = @(
                & git -C $repoRoot ls-files --others --exclude-standard `
                    2>> $gitChangedPathsErrorPath
            )
            $untrackedExitCode = $LASTEXITCODE
        }
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($diffExitCode -ne 0) {
        throw (
            "Git changed-path inspection failed with exit code " +
            $diffExitCode +
            ". Evidence: " +
            $gitChangedPathsArtifactPath
        )
    }
    if ($untrackedExitCode -ne 0) {
        throw (
            "Git untracked-path inspection failed with exit code " +
            $untrackedExitCode +
            ". Evidence: " +
            $gitChangedPathsArtifactPath
        )
    }
    $changed += $untracked
    return @(
        $changed |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            Sort-Object -Unique
    )
}

function Test-RepositoryPathMatchesPrefix {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Prefix
    )

    $normalizedPath = $Path.Replace("\", "/")
    $normalizedPrefix = $Prefix.Replace("\", "/")
    return $normalizedPath.StartsWith(
        $normalizedPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Get-FastAffectedPytestArguments {
    $script:qualityRunCurrentStep = "Pytest selection"
    return Invoke-QualityPytestSelector `
        -Profile "fast" `
        -ChangedPaths @(Get-ChangedRepositoryPaths)
}

function Get-StandardRequiredPytestArguments {
    $script:qualityRunCurrentStep = "Pytest selection"
    return Invoke-QualityPytestSelector `
        -Profile "standard" `
        -ChangedPaths @(Get-ChangedRepositoryPaths)
}

function Invoke-QualityPytestSelector {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("fast", "standard")]
        [string]$Profile,
        [string[]]$ChangedPaths = @()
    )

    $script:qualityRunCurrentStep = "Pytest selection"
    if (-not (Test-Path -LiteralPath $qualityGateProfileConfigPath -PathType Leaf)) {
        throw "Quality gate profile policy was not found: $qualityGateProfileConfigPath"
    }
    $selectorOutputPath = Join-Path $pytestTemp ("quality-selector-" + $Profile + ".json")
    $selectorErrorPath = Join-Path $pytestTemp ("quality-selector-" + $Profile + ".err")
    $selectorArguments = @(
        "-m",
        "ai4binance.ops.quality_gate",
        "select-tests",
        "--repository-root",
        $repoRoot,
        "--config",
        $qualityGateProfileConfigPath,
        "--profile",
        $Profile
    )
    foreach ($changedPath in ($ChangedPaths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })) {
        $selectorArguments += @("--changed-path", $changedPath)
    }

    & $python -B @selectorArguments > $selectorOutputPath 2> $selectorErrorPath
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        $selectorError = Get-FileTailText -Path $selectorErrorPath -MaxBytes 8192
        if ([string]::IsNullOrWhiteSpace($selectorError)) {
            $selectorError = Get-FileTailText -Path $selectorOutputPath -MaxBytes 8192
        }
        try {
            $selectorErrorPayload = $selectorError | ConvertFrom-Json
            if (-not [string]::IsNullOrWhiteSpace($selectorErrorPayload.error)) {
                $selectorError = $selectorErrorPayload.error
            }
        }
        catch {
            $selectorError = $selectorError
        }
        throw $selectorError
    }
    $selectorPayload = Get-Content -LiteralPath $selectorOutputPath -Raw |
        ConvertFrom-Json
    $pytestArguments = @($selectorPayload.pytest_arguments)
    if ($pytestArguments.Count -eq 0) {
        throw (
            "Quality gate pytest selector returned no pytest arguments. " +
            "Run scripts\quality.ps1 -Profile standard or -Profile full."
        )
    }
    return $pytestArguments
}

function Remove-PytestTempArtifacts {
    if (-not (Test-Path -LiteralPath $pytestTemp -PathType Container)) {
        return
    }

    try {
        Remove-Item -LiteralPath $pytestTemp -Recurse -Force
    }
    catch {
        $cleanupWarningPath = Join-Path $qualityRunDirectory "cleanup-warning.txt"
        $cleanupWarning = (
            "Unable to remove pytest temp path: " +
            $pytestTemp +
            " :: " +
            $_.Exception.Message
        )
        Set-Content `
            -LiteralPath $cleanupWarningPath `
            -Value $cleanupWarning `
            -Encoding UTF8
    }
}

function Invoke-CoveragePolicyEvaluation {
    Invoke-QualityStep "Coverage policy evaluation" @(
        "-c",
        "from ai4binance.ops.coverage_policy import main; raise SystemExit(main())",
        "--coverage-json",
        $coverageJsonPath,
        "--config",
        $coveragePolicyConfigPath,
        "--output-json",
        $coveragePolicySummaryPath,
        "--output-markdown",
        $coveragePolicyMarkdownPath
    )
}

function Invoke-BanditWithCapturedOutput {
    $stepStartedAtUtc = [DateTimeOffset]::UtcNow
    $stepStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $exitCode = $null
    $stepStatus = "ERROR"
    $script:qualityRunCurrentStep = "Bandit"
    Write-QualityRunMetadata -Status "RUNNING" -CurrentStep $script:qualityRunCurrentStep
    New-Item -ItemType Directory -Path $qualityRunDirectory -Force | Out-Null
    Remove-Item -LiteralPath $banditOutputPath -Force -ErrorAction SilentlyContinue
    Set-Content -LiteralPath $banditOutputPath -Value "" -Encoding ASCII
    try {
        & $python -B -m bandit -q -r src *> $banditOutputPath
        $exitCode = $LASTEXITCODE
        $script:qualityStepExitCodes["Bandit"] = $exitCode
        if ($exitCode -ne 0) {
            $stepStatus = "FAIL"
            throw "Bandit failed with exit code $exitCode"
        }
        $stepStatus = "PASS"
    }
    finally {
        Add-QualityStepTelemetry `
            -Name "Bandit" `
            -StartedAtUtc $stepStartedAtUtc `
            -Stopwatch $stepStopwatch `
            -ExitCode $exitCode `
            -Status $stepStatus `
            -OutputPath $banditOutputPath `
            -ArtifactPath (
                "runtime\artifacts\quality\gate\runs\" +
                $qualityRunTimestamp +
                "\bandit-output.txt"
            )
        Write-QualityRunMetadata -Status "RUNNING" -CurrentStep $script:qualityRunCurrentStep
    }
}

function Invoke-ConditionalMirrorHygiene {
    if (-not (Test-Path -LiteralPath $mirrorManifestPath -PathType Leaf)) {
        $script:qualityRunCurrentStep = "Repository mirror hygiene validator"
        throw "Mirror hygiene manifest is required but was not found."
    }
    Invoke-QualityStep "Repository mirror hygiene validator" @(
        "-m",
        "ai4binance.governance.repository_validator",
        "--repository-root",
        $repoRoot,
        "--check-mirror-manifest",
        $mirrorManifestPath,
        "--output-json",
        $mirrorHygieneReportPath,
        "--output-cleanup-plan",
        $mirrorCleanupPlanPath,
        "--quiet"
    )
    return "VERIFIED"
}

function Invoke-RepositoryGovernanceValidator {
    $previousPythonDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
    $env:PYTHONDONTWRITEBYTECODE = "1"
    try {
        New-Item -ItemType Directory -Path $repositoryValidatorRunDirectory -Force | Out-Null
        if (Restore-RepositoryValidatorCache) {
            Write-RepositoryValidatorRunArtifacts -CacheMode "CACHE_HIT"
            return
        }
        Invoke-QualityStep "Repository governance validator" @(
            "-m",
            "ai4binance.governance.repository_validator",
            "--repository-root",
            $repoRoot,
            "--repository-policy",
            $repositoryValidatorPolicyPath,
            "--output-json",
            $repositoryValidatorReportPath,
            "--output-markdown",
            $repositoryValidatorRunMarkdownPath,
            "--output-migration-map",
            $repositoryValidatorRunMigrationMarkdownPath,
            "--output-findings-json",
            $repositoryValidatorRunFindingsJsonPath,
            "--output-policy-snapshot",
            $repositoryValidatorRunPolicySnapshotPath,
            "--output-mirror-manifest",
            $mirrorManifestPath,
            "--quiet"
        )
        Write-RepositoryValidatorRunArtifacts -CacheMode "CACHE_MISS"
        Save-RepositoryValidatorCache
    }
    finally {
        if ($null -eq $previousPythonDontWriteBytecode) {
            Remove-Item Env:\PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
        }
        else {
            $env:PYTHONDONTWRITEBYTECODE = $previousPythonDontWriteBytecode
        }
    }
}

function Get-RepositoryValidatorCacheSubject {
    $statusOutput = git -C $repoRoot status --porcelain=v1 --untracked-files=all
    if ($LASTEXITCODE -ne 0) {
        $script:repositoryValidatorCacheStatus = "DISABLED"
        $script:repositoryValidatorCacheReason = "git status failed"
        return $null
    }
    $statusEntries = @(
        $statusOutput | Where-Object {
            -not [string]::IsNullOrWhiteSpace([string]$_)
        }
    )
    if ($statusEntries.Count -gt 0) {
        $script:repositoryValidatorCacheStatus = "DISABLED"
        $script:repositoryValidatorCacheReason = "worktree is not clean"
        return $null
    }
    $commit = Get-RepositoryGitCommit
    if ([string]::IsNullOrWhiteSpace($commit) -or $commit -eq "UNKNOWN") {
        $script:repositoryValidatorCacheStatus = "DISABLED"
        $script:repositoryValidatorCacheReason = "git commit is unknown"
        return $null
    }
    if (-not (Test-Path -LiteralPath $repositoryValidatorPolicyPath -PathType Leaf)) {
        $script:repositoryValidatorCacheStatus = "DISABLED"
        $script:repositoryValidatorCacheReason = "repository validator policy is missing"
        return $null
    }
    if (-not (Test-Path -LiteralPath $repositoryValidatorModulePath -PathType Leaf)) {
        $script:repositoryValidatorCacheStatus = "DISABLED"
        $script:repositoryValidatorCacheReason = "repository validator module is missing"
        return $null
    }
    if ([string]::IsNullOrWhiteSpace($qualityGateScriptPath) -or -not (
        Test-Path -LiteralPath $qualityGateScriptPath -PathType Leaf
    )) {
        $script:repositoryValidatorCacheStatus = "DISABLED"
        $script:repositoryValidatorCacheReason = "quality gate script path is missing"
        return $null
    }
    $policyHash = Get-Sha256Hex -Path $repositoryValidatorPolicyPath
    $validatorHash = Get-Sha256Hex -Path $repositoryValidatorModulePath
    $qualityGateScriptHash = Get-Sha256Hex -Path $qualityGateScriptPath
    $payload = [ordered]@{
        schema_version = 1
        git_commit = $commit
        repository_policy_sha256 = $policyHash
        repository_validator_sha256 = $validatorHash
        quality_gate_script_sha256 = $qualityGateScriptHash
        validator_version = "workspace-unreleased"
        cache_scope = "clean_worktree_same_head_policy_and_code"
    }
    $payloadJson = $payload | ConvertTo-Json -Compress
    $script:repositoryValidatorCacheStatus = "ELIGIBLE"
    $script:repositoryValidatorCacheReason = "clean worktree subject is cache eligible"
    return [ordered]@{
        subject_key = Get-Sha256String -Value $payloadJson
        subject = $payload
    }
}

function Restore-RepositoryValidatorCache {
    $subject = Get-RepositoryValidatorCacheSubject
    if ($null -eq $subject) {
        return $false
    }
    if (-not (Test-Path -LiteralPath $repositoryValidatorCacheMetadataPath -PathType Leaf)) {
        $script:repositoryValidatorCacheStatus = "CACHE_MISS"
        $script:repositoryValidatorCacheReason = "cache metadata is missing"
        return $false
    }
    $metadata = Get-Content -LiteralPath $repositoryValidatorCacheMetadataPath -Raw |
        ConvertFrom-Json
    if ($metadata.subject_key -ne $subject.subject_key) {
        $script:repositoryValidatorCacheStatus = "CACHE_MISS"
        $script:repositoryValidatorCacheReason = "cache subject does not match"
        return $false
    }
    if ($metadata.status -ne "PASS") {
        $script:repositoryValidatorCacheStatus = "CACHE_MISS"
        $script:repositoryValidatorCacheReason = "cache metadata status is not PASS"
        return $false
    }
    if (-not (Test-RepositoryValidatorCacheHashes -Metadata $metadata)) {
        $script:repositoryValidatorCacheStatus = "CACHE_MISS"
        $script:repositoryValidatorCacheReason = "cache artifact hash verification failed"
        return $false
    }
    $requiredCacheFiles = @(
        $repositoryValidatorCacheResultPath,
        $repositoryValidatorCacheFindingsPath,
        $repositoryValidatorCachePolicySnapshotPath,
        $repositoryValidatorCacheMirrorManifestPath,
        $repositoryValidatorCacheMarkdownPath,
        $repositoryValidatorCacheMigrationMarkdownPath
    )
    foreach ($path in $requiredCacheFiles) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            $script:repositoryValidatorCacheStatus = "CACHE_MISS"
            $script:repositoryValidatorCacheReason = "cache artifact bundle is incomplete"
            return $false
        }
    }

    $stepStartedAtUtc = [DateTimeOffset]::UtcNow
    $stepStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $script:qualityRunCurrentStep = "Repository governance validator"
    Write-QualityRunMetadata -Status "RUNNING" -CurrentStep $script:qualityRunCurrentStep
    New-Item -ItemType Directory -Path $repositoryValidatorRunDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path (Split-Path -Parent $mirrorManifestPath) -Force | Out-Null
    Copy-Item -LiteralPath $repositoryValidatorCacheResultPath -Destination $repositoryValidatorReportPath -Force
    Copy-Item -LiteralPath $repositoryValidatorCacheFindingsPath -Destination $repositoryValidatorRunFindingsJsonPath -Force
    Copy-Item -LiteralPath $repositoryValidatorCachePolicySnapshotPath -Destination $repositoryValidatorRunPolicySnapshotPath -Force
    Copy-Item -LiteralPath $repositoryValidatorCacheMirrorManifestPath -Destination $mirrorManifestPath -Force
    Copy-Item -LiteralPath $repositoryValidatorCacheMarkdownPath -Destination $repositoryValidatorRunMarkdownPath -Force
    Copy-Item -LiteralPath $repositoryValidatorCacheMigrationMarkdownPath -Destination $repositoryValidatorRunMigrationMarkdownPath -Force
    $script:qualityStepExitCodes["Repository governance validator"] = 0
    Add-QualityStepTelemetry `
        -Name "Repository governance validator" `
        -StartedAtUtc $stepStartedAtUtc `
        -Stopwatch $stepStopwatch `
        -ExitCode 0 `
        -Status "PASS" `
        -OutputPath $repositoryValidatorReportPath `
        -ArtifactPath "runtime\artifacts\quality\gate\repository_validator_latest.json" `
        -CacheMode "CACHE_HIT"
    $script:repositoryValidatorCacheStatus = "CACHE_HIT"
    $script:repositoryValidatorCacheReason = "validated cache artifact bundle restored"
    return $true
}

function Test-RepositoryValidatorCacheHashes {
    param([Parameter(Mandatory = $true)][object]$Metadata)

    $hashChecks = @(
        @($repositoryValidatorCacheResultPath, "result_sha256"),
        @($repositoryValidatorCacheFindingsPath, "findings_sha256"),
        @($repositoryValidatorCachePolicySnapshotPath, "policy_snapshot_sha256"),
        @($repositoryValidatorCacheMirrorManifestPath, "mirror_manifest_sha256")
    )
    foreach ($check in $hashChecks) {
        $path = [string]$check[0]
        $propertyName = [string]$check[1]
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            return $false
        }
        $expectedHash = [string]$Metadata.$propertyName
        if ([string]::IsNullOrWhiteSpace($expectedHash)) {
            return $false
        }
        if ((Get-Sha256Hex -Path $path) -ne $expectedHash) {
            return $false
        }
    }
    return $true
}

function Save-RepositoryValidatorCache {
    $subject = Get-RepositoryValidatorCacheSubject
    if ($null -eq $subject) {
        return
    }
    if (-not (Test-Path -LiteralPath $repositoryValidatorReportPath -PathType Leaf)) {
        $script:repositoryValidatorCacheStatus = "CACHE_MISS"
        $script:repositoryValidatorCacheReason = "repository validator result was not available to cache"
        return
    }
    $report = Get-CachedJsonArtifact `
        -Path $repositoryValidatorReportPath `
        -CacheVariableName "cachedRepositoryValidatorReport"
    if ($null -eq $report -or $report.status -ne "PASS") {
        $script:repositoryValidatorCacheStatus = "CACHE_MISS"
        $script:repositoryValidatorCacheReason = "repository validator result was not PASS"
        return
    }
    $requiredSourceFiles = @(
        $repositoryValidatorRunFindingsJsonPath,
        $repositoryValidatorRunPolicySnapshotPath,
        $mirrorManifestPath,
        $repositoryValidatorRunMarkdownPath,
        $repositoryValidatorRunMigrationMarkdownPath
    )
    foreach ($path in $requiredSourceFiles) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            $script:repositoryValidatorCacheStatus = "CACHE_MISS"
            $script:repositoryValidatorCacheReason = "repository validator source bundle is incomplete"
            return
        }
    }

    New-Item -ItemType Directory -Path $repositoryValidatorCacheDirectory -Force | Out-Null
    Copy-Item -LiteralPath $repositoryValidatorReportPath -Destination $repositoryValidatorCacheResultPath -Force
    Copy-Item -LiteralPath $repositoryValidatorRunFindingsJsonPath -Destination $repositoryValidatorCacheFindingsPath -Force
    Copy-Item -LiteralPath $repositoryValidatorRunPolicySnapshotPath -Destination $repositoryValidatorCachePolicySnapshotPath -Force
    Copy-Item -LiteralPath $mirrorManifestPath -Destination $repositoryValidatorCacheMirrorManifestPath -Force
    Copy-Item -LiteralPath $repositoryValidatorRunMarkdownPath -Destination $repositoryValidatorCacheMarkdownPath -Force
    Copy-Item -LiteralPath $repositoryValidatorRunMigrationMarkdownPath -Destination $repositoryValidatorCacheMigrationMarkdownPath -Force
    [ordered]@{
        schema_version = 1
        status = "PASS"
        subject_key = $subject.subject_key
        subject = $subject.subject
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        result_sha256 = Get-Sha256Hex -Path $repositoryValidatorCacheResultPath
        findings_sha256 = Get-Sha256Hex -Path $repositoryValidatorCacheFindingsPath
        policy_snapshot_sha256 = Get-Sha256Hex -Path $repositoryValidatorCachePolicySnapshotPath
        mirror_manifest_sha256 = Get-Sha256Hex -Path $repositoryValidatorCacheMirrorManifestPath
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } |
        ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath $repositoryValidatorCacheMetadataPath -Encoding UTF8
    $script:repositoryValidatorCacheStatus = "CACHE_SAVED"
    $script:repositoryValidatorCacheReason = "PASS result saved for clean worktree subject"
}

function Get-RepositoryGitCommit {
    try {
        $commit = git -C $repoRoot rev-parse HEAD 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($commit)) {
            return $commit.Trim()
        }
    }
    catch {
    }

    return "UNKNOWN"
}

function Reset-LatestQualityGateArtifacts {
    $latestPaths = @(
        $qualityEvidencePath,
        $repositoryValidatorReportPath,
        $deterministicQualityGateReportPath,
        $approvalRecordPath,
        $humanGovernanceClosureRequestPath,
        $humanGovernanceClosureRequestMarkdownPath,
        $governanceGateReportPath
    )
    foreach ($path in $latestPaths) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force -ErrorAction Stop -Confirm:$false
        }
    }
    $script:cachedRepositoryValidatorReport = $null
    $script:cachedGovernanceGateReport = $null
}

function Get-QualityWorkspaceAttestation {
    $pythonCode = @'
import sys
from pathlib import Path
import json
from ai4binance.governance.constitution_sync import build_quality_gate_workspace_attestation

payload = build_quality_gate_workspace_attestation(Path(sys.argv[1])).to_payload()
print(json.dumps(payload))
'@
    $output = & $python -c $pythonCode $repoRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Quality gate workspace attestation generation failed"
    }
    return $output | ConvertFrom-Json
}

function Get-QualityGateGitWriteLeasePath {
    $gitCommonDirectoryOutput = & git -C $repoRoot rev-parse `
        --path-format=absolute `
        --git-common-dir 2>$null
    $gitExitCode = $LASTEXITCODE
    if ($gitExitCode -ne 0 -or @($gitCommonDirectoryOutput).Count -eq 0) {
        throw "QUALITY_GATE_GIT_COMMON_DIRECTORY_UNAVAILABLE"
    }
    $gitCommonDirectoryText = [string](@($gitCommonDirectoryOutput)[-1])
    if ([string]::IsNullOrWhiteSpace($gitCommonDirectoryText)) {
        throw "QUALITY_GATE_GIT_COMMON_DIRECTORY_UNAVAILABLE"
    }
    $gitCommonDirectory = [IO.Path]::GetFullPath($gitCommonDirectoryText.Trim())
    return Join-Path $gitCommonDirectory "ai4binance-quality-gate-write-lease.json"
}

function Publish-QualityGateGitWriteLease {
    $leasePath = Get-QualityGateGitWriteLeasePath
    $process = Get-Process -Id $PID -ErrorAction Stop
    $temporaryLeasePath = "$leasePath.$PID.tmp"
    $payload = [ordered]@{
        schema_version = 1
        status = "QUALITY_GATE_ACTIVE"
        run_id = $qualityRunTimestamp
        process_id = $PID
        process_started_at_utc = $process.StartTime.ToUniversalTime().ToString("o")
        created_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
        repository_root = [IO.Path]::GetFullPath($repoRoot)
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    try {
        $payload |
            ConvertTo-Json -Depth 4 |
            Set-Content -LiteralPath $temporaryLeasePath -Encoding UTF8
        Move-Item -LiteralPath $temporaryLeasePath -Destination $leasePath -Force
        $script:qualityGateGitWriteLeasePath = $leasePath
    }
    finally {
        if (Test-Path -LiteralPath $temporaryLeasePath) {
            Remove-Item -LiteralPath $temporaryLeasePath -Force -ErrorAction SilentlyContinue
        }
    }
}

function Remove-QualityGateGitWriteLease {
    $leasePath = $script:qualityGateGitWriteLeasePath
    if ([string]::IsNullOrWhiteSpace([string]$leasePath)) {
        return
    }
    if (Test-Path -LiteralPath $leasePath -PathType Leaf) {
        Remove-Item -LiteralPath $leasePath -Force -ErrorAction SilentlyContinue
    }
    $script:qualityGateGitWriteLeasePath = $null
}

function Assert-QualityWorkspaceStable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Stage
    )

    $guardStartedAtUtc = [DateTimeOffset]::UtcNow
    $guardStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $script:qualityRunCurrentStep = "Repository state guard"
    $initial = $script:qualityInitialWorkspaceAttestation
    if ($null -eq $initial) {
        $guardStopwatch.Stop()
        throw "QUALITY_GATE_INITIAL_WORKSPACE_ATTESTATION_MISSING"
    }
    $current = Get-QualityWorkspaceAttestation
    $stable = (
        [string]$initial.repository_root -eq [string]$current.repository_root -and
        [string]$initial.repository_tree_sha256 -eq [string]$current.repository_tree_sha256 -and
        [string]$initial.git_commit -eq [string]$current.git_commit -and
        [string]$initial.change_set_sha256 -eq [string]$current.change_set_sha256
    )
    if ($stable) {
        $guardStopwatch.Stop()
        return
    }

    $relativeEvidencePath = (
        "runtime\quality\" +
        $qualityRunTimestamp +
        "\repository-mutation.json"
    )
    [ordered]@{
        schema_version = 1
        status = "REPOSITORY_MUTATED_DURING_QUALITY_GATE"
        run_id = $qualityRunTimestamp
        detected_at_stage = $Stage
        initial_workspace_attestation = $initial
        current_workspace_attestation = $current
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } |
        ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $repositoryMutationEvidencePath -Encoding UTF8
    $guardStopwatch.Stop()
    $failureMessage = (
        "REPOSITORY_MUTATED_DURING_QUALITY_GATE at $Stage. " +
        "Evidence: $relativeEvidencePath"
    )
    $script:qualityStepExitCodes["Repository state guard"] = 1
    $script:qualityStepTelemetry += [ordered]@{
        step_id = ConvertTo-QualityStepId -Name "Repository state guard"
        name = "Repository state guard"
        started_at_utc = $guardStartedAtUtc.ToString("o")
        ended_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
        wall_time_ms = [int64]$guardStopwatch.ElapsedMilliseconds
        exit_code = 1
        status = "FAIL"
        output_bytes = Get-FileSizeBytes -Path $repositoryMutationEvidencePath
        artifact_path = $relativeEvidencePath
        output_sha256 = Get-Sha256Hex -Path $repositoryMutationEvidencePath
        first_actionable_error = $failureMessage
        cache_mode = "UNMEASURED"
    }
    throw $failureMessage
}

function Write-RepositoryValidatorRunArtifacts {
    param([string]$CacheMode = "CACHE_MISS")

    if (-not (Test-Path -LiteralPath $repositoryValidatorReportPath -PathType Leaf)) {
        throw "Repository validator latest report is missing"
    }

    New-Item -ItemType Directory -Path $repositoryValidatorRunDirectory -Force | Out-Null
    Copy-Item `
        -LiteralPath $repositoryValidatorReportPath `
        -Destination $repositoryValidatorRunResultPath `
        -Force

    $report = Get-CachedJsonArtifact `
        -Path $repositoryValidatorReportPath `
        -CacheVariableName "cachedRepositoryValidatorReport"
    $completedAt = Get-Date
    $cacheSubject = if ($CacheMode -eq "CACHE_HIT") {
        Get-RepositoryValidatorCacheSubject
    }
    else {
        $null
    }
    $metadata = [ordered]@{
        run_id = $repositoryValidatorRunId
        trigger = "quality_gate"
        mode = "guarded"
        scenario = "quality_gate_full"
        cache_mode = $CacheMode
        started_at = $repositoryValidatorRunStartedAt.ToString("o")
        completed_at = $completedAt.ToString("o")
        validator_version = "workspace-unreleased"
        git_commit = Get-RepositoryGitCommit
        result_json_path = (
            "runtime\test\repository-validator\runs\" +
            $repositoryValidatorRunId +
            "\result.json"
        )
        findings_json_path = (
            "runtime\test\repository-validator\runs\" +
            $repositoryValidatorRunId +
            "\findings.json"
        )
        policy_snapshot_path = (
            "runtime\test\repository-validator\runs\" +
            $repositoryValidatorRunId +
            "\policy-snapshot.json"
        )
        report_markdown_path = (
            "runtime\test\repository-validator\runs\" +
            $repositoryValidatorRunId +
            "\report.md"
        )
        migration_json_path = (
            "runtime\test\repository-validator\runs\" +
            $repositoryValidatorRunId +
            "\migration.json"
        )
        migration_markdown_path = (
            "runtime\test\repository-validator\runs\" +
            $repositoryValidatorRunId +
            "\migration.md"
        )
        policy_source_path = "policies\repository-validator\manifest-policy.json"
        latest_result_json_path = "runtime\artifacts\quality\gate\repository_validator_latest.json"
        cache_subject_key = if ($null -ne $cacheSubject) {
            $cacheSubject.subject_key
        }
        else {
            $null
        }
        cache_subject = if ($null -ne $cacheSubject) {
            $cacheSubject.subject
        }
        else {
            $null
        }
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    $metadata |
        ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $repositoryValidatorRunMetadataPath -Encoding UTF8

    [ordered]@{
        run_id = $repositoryValidatorRunId
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        migration_map = @($report.migration_map)
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } |
        ConvertTo-Json -Depth 12 |
        Set-Content -LiteralPath $repositoryValidatorRunMigrationJsonPath -Encoding UTF8
}

function Get-RepositoryValidatorSummary {
    if (-not (Test-Path -LiteralPath $repositoryValidatorReportPath -PathType Leaf)) {
        return $null
    }
    $report = Get-CachedJsonArtifact `
        -Path $repositoryValidatorReportPath `
        -CacheVariableName "cachedRepositoryValidatorReport"
    return [ordered]@{
        status = $report.status
        report_path = "runtime\artifacts\quality\gate\repository_validator_latest.json"
        artifact_count = [int]$report.artifact_count
        repository_health_score = [int]$report.repository_health_score
        blocker_count = [int]($report.blockers | Measure-Object).Count
        finding_count = [int]($report.findings | Measure-Object).Count
        recommended_action_count = [int](
            $report.recommended_actions | Measure-Object
        ).Count
    }
}

function Get-FullSuiteGovernanceEvidence {
    $lineage = Get-ArtifactLineage `
        -Path (Get-PytestEvidenceArtifactPath) `
        -EvidenceSource "FULL_PYTEST_SUITE"
    return [ordered]@{
        docs_hygiene_command = (
            "python -m pytest -q tests/test_docs_hygiene.py " +
            "--basetemp runtime/tmp/process/pytest/full-suite"
        )
        docs_hygiene_tests = @("tests/test_docs_hygiene.py")
        docs_hygiene_passed = "true"
        docs_hygiene_evidence_source = $lineage.evidence_source
        docs_hygiene_evidence_path = $lineage.evidence_path
        docs_hygiene_evidence_sha256 = $lineage.evidence_sha256
        artifact_hygiene_command = (
            "python -m pytest -q tests/test_artifact_hygiene_scripts.py " +
            "--basetemp runtime/tmp/process/pytest/full-suite"
        )
        artifact_hygiene_tests = @("tests/test_artifact_hygiene_scripts.py")
        artifact_hygiene_passed = "true"
        artifact_hygiene_evidence_source = $lineage.evidence_source
        artifact_hygiene_evidence_path = $lineage.evidence_path
        artifact_hygiene_evidence_sha256 = $lineage.evidence_sha256
        constitution_sync_command = (
            "python -m pytest -q tests/test_governance_constitution_sync.py " +
            "--basetemp runtime/tmp/process/pytest/full-suite"
        )
        constitution_sync_tests = @("tests/test_governance_constitution_sync.py")
        constitution_sync_passed = "true"
        constitution_sync_evidence_source = $lineage.evidence_source
        constitution_sync_evidence_path = $lineage.evidence_path
        constitution_sync_evidence_sha256 = $lineage.evidence_sha256
        evidence_source = "FULL_PYTEST_SUITE"
    }
}

function Invoke-DocsHygieneGateTests {
    $lineage = Get-ArtifactLineage `
        -Path (Get-PytestEvidenceArtifactPath) `
        -EvidenceSource "FULL_PYTEST_SUITE"
    return [ordered]@{
        command = (
            "python -m pytest -q tests/test_docs_hygiene.py " +
            "--basetemp runtime/tmp/process/pytest/full-suite"
        )
        selected_tests = @("tests/test_docs_hygiene.py")
        passed = $true
        evidence_source = $lineage.evidence_source
        evidence_path = $lineage.evidence_path
        evidence_sha256 = $lineage.evidence_sha256
    }
}

function Invoke-ArtifactHygieneGateTests {
    $lineage = Get-ArtifactLineage `
        -Path (Get-PytestEvidenceArtifactPath) `
        -EvidenceSource "FULL_PYTEST_SUITE"
    return [ordered]@{
        command = (
            "python -m pytest -q tests/test_artifact_hygiene_scripts.py " +
            "--basetemp runtime/tmp/process/pytest/full-suite"
        )
        selected_tests = @("tests/test_artifact_hygiene_scripts.py")
        passed = $true
        evidence_source = $lineage.evidence_source
        evidence_path = $lineage.evidence_path
        evidence_sha256 = $lineage.evidence_sha256
    }
}

function Invoke-ConstitutionSyncGateTests {
    $lineage = Get-ArtifactLineage `
        -Path (Get-PytestEvidenceArtifactPath) `
        -EvidenceSource "FULL_PYTEST_SUITE"
    return [ordered]@{
        command = (
            "python -m pytest -q tests/test_governance_constitution_sync.py " +
            "--basetemp runtime/tmp/process/pytest/full-suite"
        )
        selected_tests = @("tests/test_governance_constitution_sync.py")
        passed = $true
        evidence_source = $lineage.evidence_source
        evidence_path = $lineage.evidence_path
        evidence_sha256 = $lineage.evidence_sha256
    }
}

function Get-BanditEvidence {
    $lineage = Get-ArtifactLineage `
        -Path $banditOutputPath `
        -EvidenceSource "BANDIT_STDOUT_STDERR_CAPTURE"
    return [ordered]@{
        command = "python -m bandit -q -r src"
        passed = "true"
        evidence_source = $lineage.evidence_source
        evidence_path = $lineage.evidence_path
        evidence_sha256 = $lineage.evidence_sha256
    }
}

function Invoke-DeterministicQualityGate {
    $pytestPassCount = Get-PytestPassCount
    $coveragePercent = Get-CoveragePercent
    $coverageRealismProof = Get-CoverageRealismProof
    if ($null -eq $pytestPassCount) {
        throw "Deterministic quality gate is missing pytest_pass_count"
    }
    if ($null -eq $coveragePercent) {
        throw "Deterministic quality gate is missing coverage_percent"
    }
    if ($null -eq $coverageRealismProof) {
        throw "Deterministic quality gate is missing governed markdown coverage proof"
    }
    $banditEvidence = Get-BanditEvidence
    Invoke-QualityStep "Deterministic quality gate" @(
        "-m",
        "ai4binance.governance.gate",
        "--mode",
        "deterministic-quality",
        "--repository-root",
        $repoRoot,
        "--quality-gate-command",
        (Get-QualityCommandText),
        "--pytest-pass-count",
        $pytestPassCount.ToString(),
        "--coverage-percent",
        ([string]::Format([Globalization.CultureInfo]::InvariantCulture, "{0}", $coveragePercent)),
        "--coverage-source",
        "coverage.py json totals.percent_covered",
        "--coverage-realism-proof-path",
        $coverageRealismProof.markdown_path,
        "--coverage-realism-proof-sha256",
        $coverageRealismProof.markdown_sha256,
        "--bandit-command",
        $banditEvidence.command,
        "--bandit-passed",
        $banditEvidence.passed,
        "--bandit-evidence-source",
        $banditEvidence.evidence_source,
        "--bandit-evidence-path",
        $banditEvidence.evidence_path,
        "--bandit-evidence-sha256",
        $banditEvidence.evidence_sha256,
        "--output-json",
        $deterministicQualityGateReportPath
    )
}

function Invoke-DeterministicGovernanceGateStep {
    param(
        [Parameter(Mandatory = $true)]
        [object]$DocsHygieneEvidence,
        [Parameter(Mandatory = $true)]
        [object]$ArtifactHygieneEvidence,
        [Parameter(Mandatory = $true)]
        [object]$ConstitutionSyncEvidence,
        [string]$ApprovalRecordPathOverride = "",
        [string]$FrozenGovernanceGateReportPath = "",
        [int[]]$AllowedExitCodes = @(0)
    )

    $arguments = @(
        "-m",
        "ai4binance.governance.gate",
        "--mode",
        "governance",
        "--repository-root",
        $repoRoot,
        "--repository-validator-report",
        $repositoryValidatorReportPath,
        "--docs-hygiene-command",
        $DocsHygieneEvidence.command,
        "--docs-hygiene-tests",
        $DocsHygieneEvidence.selected_tests,
        "--docs-hygiene-passed",
        "true",
        "--docs-hygiene-evidence-source",
        $DocsHygieneEvidence.evidence_source,
        "--docs-hygiene-evidence-path",
        $DocsHygieneEvidence.evidence_path,
        "--docs-hygiene-evidence-sha256",
        $DocsHygieneEvidence.evidence_sha256,
        "--artifact-hygiene-command",
        $ArtifactHygieneEvidence.command,
        "--artifact-hygiene-tests",
        $ArtifactHygieneEvidence.selected_tests,
        "--artifact-hygiene-passed",
        "true",
        "--artifact-hygiene-evidence-source",
        $ArtifactHygieneEvidence.evidence_source,
        "--artifact-hygiene-evidence-path",
        $ArtifactHygieneEvidence.evidence_path,
        "--artifact-hygiene-evidence-sha256",
        $ArtifactHygieneEvidence.evidence_sha256,
        "--constitution-sync-command",
        $ConstitutionSyncEvidence.command,
        "--constitution-sync-tests",
        $ConstitutionSyncEvidence.selected_tests,
        "--constitution-sync-passed",
        "true",
        "--constitution-sync-evidence-source",
        $ConstitutionSyncEvidence.evidence_source,
        "--constitution-sync-evidence-path",
        $ConstitutionSyncEvidence.evidence_path,
        "--constitution-sync-evidence-sha256",
        $ConstitutionSyncEvidence.evidence_sha256,
        "--deterministic-quality-gate-report",
        $deterministicQualityGateReportPath,
        "--output-json",
        $governanceGateReportPath
    )
    if (-not [string]::IsNullOrWhiteSpace($ApprovalRecordPathOverride)) {
        $arguments += @("--approval-record-report", $ApprovalRecordPathOverride)
    }
    if (-not [string]::IsNullOrWhiteSpace($FrozenGovernanceGateReportPath)) {
        $arguments += @(
            "--frozen-governance-gate-report",
            $FrozenGovernanceGateReportPath
        )
    }
    return Invoke-QualityStepWithAllowedExitCodes `
        -Name "Deterministic governance gate" `
        -Arguments $arguments `
        -AllowedExitCodes $AllowedExitCodes `
        -StatusByExitCode @{ 2 = "REQUIRES_APPROVAL" }
}

function Test-GovernanceGateApprovalRetryAllowed {
    if (-not (Test-Path -LiteralPath $governanceGateReportPath -PathType Leaf)) {
        throw "Approval retry requires governance gate report"
    }
    $report = Get-CachedJsonArtifact `
        -Path $governanceGateReportPath `
        -CacheVariableName "cachedGovernanceGateReport"
    $requiredApprovalCount = [int]$report.approval_verification.required_approval_count
    if ($requiredApprovalCount -lt 1) {
        return $false
    }
    $nonApprovalBlockers = @(
        @($report.blockers) | Where-Object {
            $_ -ne "APPROVAL_REQUIRED" -and $_ -notlike "APPROVAL_*"
        }
    )
    if (($nonApprovalBlockers | Measure-Object).Count -gt 0) {
        $message = "Approval verification is blocked by unresolved non-approval blockers: " + ($nonApprovalBlockers -join ", ")
        throw $message
    }
    return $true
}

function Resolve-ApprovalReplaySourcePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $candidate = if ([IO.Path]::IsPathRooted($Path)) {
        [IO.Path]::GetFullPath($Path)
    }
    else {
        [IO.Path]::GetFullPath((Join-Path $repoRoot $Path))
    }
    $allowedRoot = [IO.Path]::GetFullPath(
        (Join-Path $qualityGateArtifactDirectory "runs")
    ).TrimEnd("\", "/")
    $allowedPrefix = $allowedRoot + [IO.Path]::DirectorySeparatorChar
    if (-not $candidate.StartsWith(
            $allowedPrefix,
            [StringComparison]::OrdinalIgnoreCase
        )) {
        throw "APPROVAL_REPLAY_SOURCE_OUTSIDE_RUN_DIRECTORY: $Path"
    }
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "APPROVAL_REPLAY_SOURCE_MISSING: $Path"
    }
    return $candidate
}

function Assert-ApprovalReplayArtifactHash {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedSha256,
        [Parameter(Mandatory = $true)]
        [string]$ArtifactName
    )

    $actualSha256 = Get-Sha256Hex -Path $Path
    if ($actualSha256 -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "APPROVAL_REPLAY_ARTIFACT_DRIFT:$ArtifactName"
    }
}

function Get-FullApprovalReplayContext {
    $resolvedApprovalRecordPath = Resolve-ApprovalRecordPathForGovernanceGate
    if ($null -eq $resolvedApprovalRecordPath) {
        throw "APPROVAL_REPLAY_RECORD_REQUIRED"
    }
    $approvalPayload = Get-Content -LiteralPath $resolvedApprovalRecordPath -Raw |
        ConvertFrom-Json
    $approvalRecords = @($approvalPayload.approval_records)
    if ($approvalRecords.Count -lt 1) {
        throw "APPROVAL_REPLAY_RECORDS_MISSING"
    }
    $subjectRefs = @(
        $approvalRecords |
            ForEach-Object { [string]$_.subject_ref } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            Select-Object -Unique
    )
    if ($subjectRefs.Count -ne 1) {
        throw "APPROVAL_REPLAY_SUBJECT_REF_AMBIGUOUS"
    }
    foreach ($record in $approvalRecords) {
        if ([bool]$record.execution_allowed) {
            throw "APPROVAL_REPLAY_EXECUTION_AUTHORITY_FORBIDDEN"
        }
        if ([string]$record.live_eligibility_status -ne "LIVE_ORDER_BLOCKED") {
            throw "APPROVAL_REPLAY_LIVE_BOUNDARY_MISMATCH"
        }
    }

    $sourceGovernancePath = Resolve-ApprovalReplaySourcePath -Path $subjectRefs[0]
    if ((Split-Path -Leaf $sourceGovernancePath) -ne "governance-gate-approval-required.json") {
        throw "APPROVAL_REPLAY_SUBJECT_REF_NOT_FROZEN"
    }
    $sourceDirectory = Split-Path -Parent $sourceGovernancePath
    $sourceGovernance = Get-Content -LiteralPath $sourceGovernancePath -Raw |
        ConvertFrom-Json
    $nonApprovalBlockers = @(
        @($sourceGovernance.blockers) | Where-Object {
            $_ -ne "APPROVAL_REQUIRED" -and $_ -notlike "APPROVAL_*"
        }
    )
    if (
        [string]$sourceGovernance.status -ne "RUNNING_WITH_BLOCKERS" -or
        $nonApprovalBlockers.Count -gt 0 -or
        [int]$sourceGovernance.approval_verification.required_approval_count -lt 1
    ) {
        throw "APPROVAL_REPLAY_SOURCE_NOT_APPROVAL_ONLY"
    }
    if (
        [string]$sourceGovernance.deterministic_quality_gate.status -ne "PASS" -or
        [string]$sourceGovernance.repository_hygiene.status -ne "PASS" -or
        [string]$sourceGovernance.constitution_sync.status -ne "PASS" -or
        [string]$sourceGovernance.repository_conformance.status -ne "PASS" -or
        [string]$sourceGovernance.repository_validator_gate.status -ne "PASS"
    ) {
        throw "APPROVAL_REPLAY_SOURCE_GATE_NOT_PASSING"
    }
    if (
        [bool]$sourceGovernance.execution_allowed -or
        [string]$sourceGovernance.promotion_status -ne "RESEARCH_ONLY" -or
        [string]$sourceGovernance.live_eligibility_status -ne "LIVE_ORDER_BLOCKED"
    ) {
        throw "APPROVAL_REPLAY_SOURCE_SAFETY_BOUNDARY_MISMATCH"
    }

    $currentAttestation = $script:qualityInitialWorkspaceAttestation
    if ($null -eq $currentAttestation) {
        throw "APPROVAL_REPLAY_WORKSPACE_ATTESTATION_MISSING"
    }
    $expectedSubject = $sourceGovernance.subject_digest
    if (
        [string]$currentAttestation.repository_tree_sha256 -ne
            [string]$expectedSubject.repository_tree_sha256 -or
        [string]$currentAttestation.git_commit -ne [string]$expectedSubject.git_commit
    ) {
        throw "APPROVAL_REPLAY_SUBJECT_DRIFT"
    }

    $sourceQualityPath = Resolve-ApprovalReplaySourcePath -Path (
        Join-Path $sourceDirectory "deterministic-quality-gate.json"
    )
    $sourceValidatorPath = Resolve-ApprovalReplaySourcePath -Path (
        Join-Path $sourceDirectory "repository-validator.json"
    )
    $sourceCoverageSummaryPath = Resolve-ApprovalReplaySourcePath -Path (
        Join-Path $sourceDirectory "coverage-summary.json"
    )
    $sourceCoverageMarkdownPath = Resolve-ApprovalReplaySourcePath -Path (
        Join-Path $sourceDirectory "coverage-summary.md"
    )
    $sourceQuality = Get-Content -LiteralPath $sourceQualityPath -Raw |
        ConvertFrom-Json
    $sourceValidator = Get-Content -LiteralPath $sourceValidatorPath -Raw |
        ConvertFrom-Json
    $sourceCoverageSummary = Get-Content -LiteralPath $sourceCoverageSummaryPath -Raw |
        ConvertFrom-Json
    if (
        [string]$sourceQuality.status -ne "PASS" -or
        [string]$sourceQuality.gate_evidence_sha256 -ne
            [string]$sourceGovernance.deterministic_quality_gate.gate_evidence_sha256 -or
        [string]$sourceQuality.subject_digest.subject_id -ne
            [string]$expectedSubject.subject_id -or
        [string]$sourceQuality.subject_digest.change_set_sha256 -ne
            [string]$expectedSubject.change_set_sha256
    ) {
        throw "APPROVAL_REPLAY_DETERMINISTIC_QUALITY_DRIFT"
    }
    if (
        [string]$currentAttestation.change_set_sha256 -ne
            [string]$sourceQuality.quality_evidence_gate.quality_gate.workspace_attestation.change_set_sha256
    ) {
        throw "APPROVAL_REPLAY_WORKSPACE_ATTESTATION_DRIFT"
    }
    if ([string]$sourceValidator.status -ne "PASS") {
        throw "APPROVAL_REPLAY_REPOSITORY_VALIDATOR_NOT_PASSING"
    }

    foreach ($evidence in @(
            $sourceGovernance.docs_hygiene,
            $sourceGovernance.artifact_hygiene,
            $sourceGovernance.constitution_sync_tests
        )) {
        if (-not [bool]$evidence.passed) {
            throw "APPROVAL_REPLAY_HYGIENE_EVIDENCE_NOT_PASSING"
        }
        $evidencePath = Resolve-ApprovalReplaySourcePath -Path (
            [string]$evidence.evidence_path
        )
        if ((Split-Path -Parent $evidencePath) -ne $sourceDirectory) {
            throw "APPROVAL_REPLAY_HYGIENE_EVIDENCE_NOT_RUN_SCOPED"
        }
        Assert-ApprovalReplayArtifactHash `
            -Path $evidencePath `
            -ExpectedSha256 ([string]$evidence.evidence_sha256) `
            -ArtifactName ([string]$evidence.check_id)
    }

    $sourcePytestPath = Resolve-ApprovalReplaySourcePath -Path (
        [string]$sourceGovernance.docs_hygiene.evidence_path
    )
    $sourceBanditPath = Resolve-ApprovalReplaySourcePath -Path (
        [string]$sourceQuality.security_scan.evidence_path
    )
    Assert-ApprovalReplayArtifactHash `
        -Path $sourceBanditPath `
        -ExpectedSha256 ([string]$sourceQuality.security_scan.evidence_sha256) `
        -ArtifactName "BANDIT"
    Assert-ApprovalReplayArtifactHash `
        -Path $sourceCoverageMarkdownPath `
        -ExpectedSha256 (
            [string]$sourceQuality.quality_evidence_gate.quality_gate.coverage_realism_proof_sha256
        ) `
        -ArtifactName "COVERAGE_REALISM_PROOF"
    $expectedCoverage = [double](
        $sourceQuality.quality_evidence_gate.quality_gate.coverage_percent
    )
    if (
        [math]::Abs(
            [double]$sourceCoverageSummary.total_coverage_percent - $expectedCoverage
        ) -gt 0.01
    ) {
        throw "APPROVAL_REPLAY_COVERAGE_SUMMARY_DRIFT"
    }
    $sourceCoveragePath = Resolve-ApprovalReplaySourcePath -Path (
        Join-Path $sourceDirectory "coverage.json"
    )

    return [ordered]@{
        approval_record_path = $resolvedApprovalRecordPath
        governance = $sourceGovernance
        quality = $sourceQuality
        governance_path = $sourceGovernancePath
        quality_path = $sourceQualityPath
        validator_path = $sourceValidatorPath
        pytest_path = $sourcePytestPath
        coverage_path = $sourceCoveragePath
        bandit_path = $sourceBanditPath
        coverage_summary_path = $sourceCoverageSummaryPath
        coverage_markdown_path = $sourceCoverageMarkdownPath
    }
}

function Copy-ApprovalReplayArtifact {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    if (-not [string]::Equals(
            [IO.Path]::GetFullPath($Source),
            [IO.Path]::GetFullPath($Destination),
            [StringComparison]::OrdinalIgnoreCase
        )) {
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    }
}

function Invoke-FullApprovalReplayQualityGate {
    $script:qualityRunCurrentStep = "FULL approval replay validation"
    Write-QualityRunMetadata -Status "RUNNING" -CurrentStep $script:qualityRunCurrentStep
    $context = Get-FullApprovalReplayContext
    Copy-ApprovalReplayArtifact `
        -Source $context.quality_path `
        -Destination $deterministicQualityGateReportPath
    Copy-ApprovalReplayArtifact `
        -Source $context.validator_path `
        -Destination $repositoryValidatorReportPath
    Copy-ApprovalReplayArtifact `
        -Source $context.pytest_path `
        -Destination $durablePytestOutputPath
    Copy-ApprovalReplayArtifact `
        -Source $context.coverage_path `
        -Destination $coverageJsonPath
    Copy-ApprovalReplayArtifact `
        -Source $context.coverage_path `
        -Destination $durableCoverageJsonPath
    Copy-ApprovalReplayArtifact `
        -Source $context.bandit_path `
        -Destination $banditOutputPath
    Copy-ApprovalReplayArtifact `
        -Source $context.coverage_summary_path `
        -Destination $coveragePolicySummaryPath
    Copy-ApprovalReplayArtifact `
        -Source $context.coverage_summary_path `
        -Destination $durableCoverageSummaryPath
    Copy-ApprovalReplayArtifact `
        -Source $context.coverage_markdown_path `
        -Destination $coveragePolicyMarkdownPath
    Copy-ApprovalReplayArtifact `
        -Source $context.coverage_markdown_path `
        -Destination $durableCoverageMarkdownPath
    $script:cachedRepositoryValidatorReport = $null
    $script:cachedGovernanceGateReport = $null
    $script:qualitySelectedPytestArguments = @("FULL_TEST_SUITE")
    $script:qualityReplayPytestPassCount = [int](
        $context.quality.quality_evidence_gate.quality_gate.pytest_pass_count
    )
    $script:qualityReplayCoveragePercent = [double](
        $context.quality.quality_evidence_gate.quality_gate.coverage_percent
    )
    $script:pytestExitCode = 0
    $script:pytestEvidencePath = Get-RepositoryRelativeArtifactPath `
        -Path $durablePytestOutputPath
    $script:pytestEvidenceSha256 = Get-Sha256Hex -Path $durablePytestOutputPath
    $script:pytestOutputTail = Get-FileTailText -Path $durablePytestOutputPath

    $script:qualityRunCurrentStep = "Deterministic governance approval replay"
    Invoke-DeterministicGovernanceGateStep `
        -DocsHygieneEvidence $context.governance.docs_hygiene `
        -ArtifactHygieneEvidence $context.governance.artifact_hygiene `
        -ConstitutionSyncEvidence $context.governance.constitution_sync_tests `
        -ApprovalRecordPathOverride $context.approval_record_path `
        -FrozenGovernanceGateReportPath $context.governance_path | Out-Null
    Invoke-GeneratedArtifactCleanup
    Invoke-ProcessTempRetentionCleanup
    Assert-QualityWorkspaceStable -Stage "BEFORE_APPROVAL_REPLAY_GREEN_EVIDENCE"
    Write-QualityGateGreenEvidence
    Assert-QualityWorkspaceStable -Stage "AFTER_APPROVAL_REPLAY_GREEN_EVIDENCE"
}

function Invoke-DeterministicGovernanceGate {
    $docsHygieneEvidence = Invoke-DocsHygieneGateTests
    $artifactHygieneEvidence = Invoke-ArtifactHygieneGateTests
    $constitutionSyncEvidence = Invoke-ConstitutionSyncGateTests
    Remove-ApprovalRecordArtifact
    $initialGovernanceExitCode = Invoke-DeterministicGovernanceGateStep `
        -DocsHygieneEvidence $docsHygieneEvidence `
        -ArtifactHygieneEvidence $artifactHygieneEvidence `
        -ConstitutionSyncEvidence $constitutionSyncEvidence `
        -AllowedExitCodes @(0, 2)
    if ($initialGovernanceExitCode -eq 0) {
        return
    }
    if (Test-GovernanceGateApprovalRetryAllowed) {
        $resolvedApprovalRecordPath = Resolve-ApprovalRecordPathForGovernanceGate
        if ($null -eq $resolvedApprovalRecordPath) {
            Write-HumanGovernanceClosureRequestArtifact
            throw (
                "Deterministic governance gate requires independently prepared approval records. " +
                "Prepared closure request artifact: $humanGovernanceClosureRequestPath"
            )
        }
        Invoke-DeterministicGovernanceGateStep `
            -DocsHygieneEvidence $docsHygieneEvidence `
            -ArtifactHygieneEvidence $artifactHygieneEvidence `
            -ConstitutionSyncEvidence $constitutionSyncEvidence `
            -ApprovalRecordPathOverride $resolvedApprovalRecordPath
    }
}

function Get-DeterministicQualityGateSummary {
    if (Test-Path -LiteralPath $deterministicQualityGateReportPath -PathType Leaf) {
        $report = Get-Content -LiteralPath $deterministicQualityGateReportPath -Raw |
            ConvertFrom-Json
        return [ordered]@{
            status = $report.status
            gate_id = $report.gate_id
            report_path = "runtime\artifacts\quality\gate\deterministic_quality_gate_latest.json"
            blocker_count = [int]($report.blockers | Measure-Object).Count
            blockers = @($report.blockers)
            quality_evidence_gate_status = $report.quality_evidence_gate.status
            security_scan_passed = [bool]$report.security_scan.passed
            pytest_pass_count = [int]$report.quality_evidence_gate.quality_gate.pytest_pass_count
            coverage_percent = [double]$report.quality_evidence_gate.quality_gate.coverage_percent
            lifecycle_stage = $report.lifecycle_stage
            subject_id = $report.subject_digest.subject_id
            change_set_sha256 = $report.subject_digest.change_set_sha256
            gate_evidence_sha256 = $report.gate_evidence_sha256
        }
    }
    if (-not (Test-Path -LiteralPath $governanceGateReportPath -PathType Leaf)) {
        return $null
    }
    $governanceReport = Get-CachedJsonArtifact `
        -Path $governanceGateReportPath `
        -CacheVariableName "cachedGovernanceGateReport"
    if ($null -ne $governanceReport.deterministic_quality_gate) {
        return [ordered]@{
            status = $governanceReport.deterministic_quality_gate.status
            gate_id = $governanceReport.deterministic_quality_gate.gate_id
            report_path = "runtime\artifacts\quality\gate\deterministic_quality_gate_latest.json"
            blocker_count = [int]$governanceReport.deterministic_quality_gate.blocker_count
            blockers = @($governanceReport.deterministic_quality_gate.blockers)
            quality_evidence_gate_status = $governanceReport.deterministic_quality_gate.quality_evidence_gate_status
            security_scan_passed = [bool]$governanceReport.deterministic_quality_gate.security_scan_passed
            pytest_pass_count = [int]$governanceReport.deterministic_quality_gate.pytest_pass_count
            coverage_percent = [double]$governanceReport.deterministic_quality_gate.coverage_percent
            lifecycle_stage = $governanceReport.deterministic_quality_gate.lifecycle_stage
            subject_id = $governanceReport.deterministic_quality_gate.subject_id
            change_set_sha256 = $governanceReport.deterministic_quality_gate.change_set_sha256
            gate_evidence_sha256 = $governanceReport.deterministic_quality_gate.gate_evidence_sha256
        }
    }
    return [ordered]@{
        status = $governanceReport.status
        gate_id = "deterministic-quality-gate:derived-from-governance"
        report_path = "runtime\artifacts\quality\gate\deterministic_quality_gate_latest.json"
        blocker_count = [int]($governanceReport.blockers | Measure-Object).Count
        blockers = @($governanceReport.blockers)
        quality_evidence_gate_status = "NOT_EMBEDDED"
        security_scan_passed = $false
        pytest_pass_count = $null
        coverage_percent = $null
        lifecycle_stage = $null
        subject_id = $null
        change_set_sha256 = $null
        gate_evidence_sha256 = $null
    }
}

function Get-GovernanceGateSummary {
    if (-not (Test-Path -LiteralPath $governanceGateReportPath -PathType Leaf)) {
        return $null
    }
    $report = Get-CachedJsonArtifact `
        -Path $governanceGateReportPath `
        -CacheVariableName "cachedGovernanceGateReport"
    return [ordered]@{
        status = $report.status
        gate_id = $report.gate_id
        report_path = "runtime\artifacts\quality\gate\governance_gate_latest.json"
        blocker_count = [int]($report.blockers | Measure-Object).Count
        blockers = @($report.blockers)
        deterministic_quality_gate_status = $report.deterministic_quality_gate.status
        repository_hygiene_status = $report.repository_hygiene.status
        constitution_sync_status = $report.constitution_sync.status
        repository_conformance_status = $report.repository_conformance.status
        repository_validator_gate_status = $report.repository_validator_gate.status
        deterministic_gate_resolver_decision = $report.deterministic_gate_resolver.decision
        repository_validator_status = $report.repository_validator.status
        docs_hygiene_passed = [bool]$report.docs_hygiene.passed
        artifact_hygiene_passed = [bool]$report.artifact_hygiene.passed
        constitution_sync_passed = [bool]$report.constitution_sync_tests.passed
        alignment_status = $report.alignment_status
        lifecycle_stage = $report.lifecycle_stage
        subject_id = $report.subject_digest.subject_id
        change_set_sha256 = $report.subject_digest.change_set_sha256
        gate_evidence_sha256 = $report.gate_evidence_sha256
        change_class = $report.change_class
        approval_verification_status = $report.approval_verification.status
        approval_lifecycle_stage = $report.approval_verification.lifecycle_stage
        approval_required = [bool]$report.approval_verification.approval_required
        approval_required_count = [int]$report.approval_verification.required_approval_count
        approval_observed_count = [int]$report.approval_verification.observed_approval_count
        approval_hard_veto = [bool]$report.approval_verification.hard_veto
        approval_evidence_hash = $report.approval_verification.evidence_hash
        approval_authority_family_sha256 = $report.approval_verification.authority_family_sha256
        approval_lifecycle_definition_sha256 = $report.approval_verification.lifecycle_definition_sha256
        traceability_audit_status = $report.traceability_audit.status
        traceability_requirement_count = [int]$report.traceability_audit.requirement_count
        traceability_record_count = [int]$report.traceability_audit.record_count
        traceability_blockers = @($report.traceability_audit.blockers)
        traceability_hard_veto = [bool]$report.traceability_hard_veto
    }
}

function Write-QualityGateGreenEvidence {
    $pytestPassCount = Get-PytestPassCount
    $coveragePercent = Get-CoveragePercent
    $coveragePolicySummary = Get-CoveragePolicySummary
    $coverageRealismProof = Get-CoverageRealismProof
    $repositoryValidatorSummary = Get-RepositoryValidatorSummary
    if ($null -eq $pytestPassCount) {
        throw "Quality gate evidence is missing pytest_pass_count"
    }
    if ($null -eq $coveragePercent) {
        throw "Quality gate evidence is missing coverage_percent"
    }
    if ($null -eq $coveragePolicySummary) {
        throw "Quality gate evidence is missing coverage policy summary"
    }
    if ($null -eq $coverageRealismProof) {
        throw "Quality gate evidence is missing governed markdown coverage proof"
    }
    if ($null -eq $repositoryValidatorSummary) {
        throw "Quality gate evidence is missing repository validator summary"
    }
    $deterministicQualityGateSummary = Get-DeterministicQualityGateSummary
    if ($null -eq $deterministicQualityGateSummary) {
        throw "Quality gate evidence is missing deterministic quality gate summary"
    }
    if ($deterministicQualityGateSummary.status -ne "PASS") {
        throw "Quality gate evidence requires deterministic quality gate PASS"
    }
    $governanceGateSummary = Get-GovernanceGateSummary
    if ($null -eq $governanceGateSummary) {
        throw "Quality gate evidence is missing governance gate summary"
    }
    if ($governanceGateSummary.status -ne "PASS") {
        throw "Quality gate evidence requires governance gate PASS"
    }
    $approvalVerificationStatus = [string]$governanceGateSummary.approval_verification_status
    $approvalHardVeto = [bool]$governanceGateSummary.approval_hard_veto
    $traceabilityAuditStatus = [string]$governanceGateSummary.traceability_audit_status
    $traceabilityHardVeto = [bool]$governanceGateSummary.traceability_hard_veto
    $fullAssuranceBlockers = @()
    if ($approvalHardVeto -and $approvalVerificationStatus -ne "PASS") {
        $fullAssuranceBlockers += "APPROVAL_VERIFICATION_VETO"
    }
    if ($traceabilityHardVeto -and $traceabilityAuditStatus -ne "PASS") {
        $fullAssuranceBlockers += "CANONICAL_TRACE_VERIFICATION_VETO"
    }
    if ($governanceGateSummary.status -ne "PASS") {
        $fullAssuranceBlockers += "DETERMINISTIC_GOVERNANCE_GATE_NOT_PASSING"
    }
    $fullAssuranceStatus = if (($fullAssuranceBlockers | Measure-Object).Count -eq 0) {
        "FULL_ASSURANCE_GREEN"
    }
    else {
        "RUNNING_WITH_BLOCKERS"
    }
    if ([math]::Abs([double]$coveragePolicySummary.total_coverage_percent - [double]$coveragePercent) -gt 0.01) {
        throw "Quality gate coverage_percent does not match governed markdown proof source"
    }
    $evidenceDirectory = Split-Path -Parent $qualityEvidencePath
    New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null
    $workspaceAttestation = Get-QualityWorkspaceAttestation
    $payload = [ordered]@{
        schema_version = 2
        status = "TECHNICAL_QUALITY_PASS"
        legacy_status = "QUALITY_GATE_GREEN"
        profile = $script:qualityGateProfile
        verification_status = "FULL_VERIFIED"
        canonical_quality_authority = $true
        full_assurance_status = $fullAssuranceStatus
        full_assurance_blockers = @($fullAssuranceBlockers)
        command = (Get-QualityCommandText)
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        run_started_at_utc = $script:qualityRunStartedAtUtc.ToString("o")
        run_duration_ms = Get-QualityRunDurationMs
        step_telemetry = @($script:qualityStepTelemetry)
        selected_pytest_arguments = @($script:qualitySelectedPytestArguments)
        selected_test_count = @(
            $script:qualitySelectedPytestArguments |
                Where-Object {
                    Test-PytestSelectionArgument -Argument $_
                }
        ).Count
        pytest_pass_count = $pytestPassCount
        coverage_percent = $coveragePercent
        coverage_source = "coverage.py json totals.percent_covered"
        coverage_policy_summary = $coveragePolicySummary
        coverage_realism_proof = $coverageRealismProof
        repository_validator_summary = $repositoryValidatorSummary
        deterministic_quality_gate_summary = $deterministicQualityGateSummary
        governance_gate_summary = $governanceGateSummary
        approval_verification_hard_veto = $approvalHardVeto
        traceability_hard_veto = $traceabilityHardVeto
        consequential_change_allowed = ($fullAssuranceStatus -eq "FULL_ASSURANCE_GREEN")
        mirror_remote_check = $mirrorRemoteCheck
        mirror_manifest_path = "runtime\artifacts\repository_validation\mirror\latest_inventory.json"
        mirror_hygiene_report_path = "runtime\artifacts\repository_validation\mirror_hygiene_report.json"
        mirror_cleanup_plan_path = "runtime\artifacts\repository_validation\mirror_cleanup_plan.json"
        workspace_attestation = $workspaceAttestation
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    $payload |
        ConvertTo-Json -Depth 12 |
        Set-Content -LiteralPath $qualityEvidencePath -Encoding UTF8
}

function Write-QualityGateFailureEvidence {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FailureStatus,
        [Parameter(Mandatory = $true)]
        [string]$FailureStep,
        [string]$FailureMessage
    )

    $evidenceDirectory = Split-Path -Parent $qualityEvidencePath
    New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null
    $payload = [ordered]@{
        schema_version = 2
        status = $FailureStatus
        profile = $script:qualityGateProfile
        verification_status = Get-QualityProfileVerificationStatus -Status $FailureStatus
        command = (Get-QualityCommandText)
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        run_started_at_utc = $script:qualityRunStartedAtUtc.ToString("o")
        run_duration_ms = Get-QualityRunDurationMs
        current_step = $FailureStep
        error = $FailureMessage
        step_exit_codes = $script:qualityStepExitCodes
        step_telemetry = @($script:qualityStepTelemetry)
        pytest_exit_code = $script:pytestExitCode
        pytest_output_path = $script:pytestEvidencePath
        pytest_output_sha256 = $script:pytestEvidenceSha256
        pytest_output_tail = $script:pytestOutputTail
        selected_pytest_arguments = @($script:qualitySelectedPytestArguments)
        selected_test_count = @(
            $script:qualitySelectedPytestArguments |
                Where-Object {
                    Test-PytestSelectionArgument -Argument $_
                }
        ).Count
        stale_latest_invalidated = $true
        full_verification_status = "NOT_VERIFIED"
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    $payload |
        ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $qualityEvidencePath -Encoding UTF8
}

function Write-QualityProfileEvidence {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Status
    )

    $evidenceDirectory = Split-Path -Parent $qualityEvidencePath
    New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null
    $payload = [ordered]@{
        schema_version = 2
        status = $Status
        profile = $script:qualityGateProfile
        verification_status = Get-QualityProfileVerificationStatus -Status $Status
        canonical_quality_authority = $false
        command = (Get-QualityCommandText)
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        run_started_at_utc = $script:qualityRunStartedAtUtc.ToString("o")
        run_duration_ms = Get-QualityRunDurationMs
        step_exit_codes = $script:qualityStepExitCodes
        step_telemetry = @($script:qualityStepTelemetry)
        selected_pytest_arguments = @($script:qualitySelectedPytestArguments)
        selected_test_count = @(
            $script:qualitySelectedPytestArguments |
            Where-Object {
                Test-PytestSelectionArgument -Argument $_
            }
        ).Count
        stale_latest_invalidated = $true
        full_verification_status = "NOT_VERIFIED"
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    $payload |
        ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $qualityEvidencePath -Encoding UTF8
}

function Write-QualityRunMetadata {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Status,
        [string]$ErrorMessage,
        [string]$CurrentStep = $script:qualityRunCurrentStep
    )

    $metadataDirectory = Split-Path -Parent $qualityRunMetadataPath
    New-Item -ItemType Directory -Path $metadataDirectory -Force | Out-Null
    $payload = [ordered]@{
        status = $Status
        profile = $script:qualityGateProfile
        verification_status = Get-QualityProfileVerificationStatus -Status $Status
        current_step = $CurrentStep
        command = (Get-QualityCommandText)
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        run_started_at_utc = $script:qualityRunStartedAtUtc.ToString("o")
        run_duration_ms = Get-QualityRunDurationMs
        output_markdown_path = "runtime\artifacts\quality\gate\" + (Split-Path -Leaf $qualityRunOutputPath)
        metadata_json_path = "runtime\artifacts\quality\gate\" + (Split-Path -Leaf $qualityRunMetadataPath)
        run_directory = "runtime\artifacts\quality\gate\runs\" + $qualityRunTimestamp
        pytest_output_path = "runtime\artifacts\quality\gate\runs\" + $qualityRunTimestamp + "\pytest-output.txt"
        coverage_json_path = "runtime\artifacts\quality\gate\runs\" + $qualityRunTimestamp + "\coverage.json"
        bandit_output_path = "runtime\artifacts\quality\gate\runs\" + $qualityRunTimestamp + "\bandit-output.txt"
        latest_evidence_path = "runtime\artifacts\quality\gate\latest.json"
        deterministic_quality_gate_report_path = "runtime\artifacts\quality\gate\deterministic_quality_gate_latest.json"
        governance_gate_report_path = "runtime\artifacts\quality\gate\governance_gate_latest.json"
        coverage_summary_json_path = "runtime\artifacts\quality\gate\runs\" + $qualityRunTimestamp + "\coverage-summary.json"
        coverage_summary_markdown_path = "runtime\artifacts\quality\gate\runs\" + $qualityRunTimestamp + "\coverage-summary.md"
        step_exit_codes = $script:qualityStepExitCodes
        step_telemetry = @($script:qualityStepTelemetry)
        pytest_exit_code = $script:pytestExitCode
        pytest_output_available = ($null -ne $script:pytestEvidencePath)
        pytest_evidence_path = $script:pytestEvidencePath
        pytest_output_sha256 = $script:pytestEvidenceSha256
        selected_pytest_arguments = @($script:qualitySelectedPytestArguments)
        selected_test_count = @(
            $script:qualitySelectedPytestArguments |
                Where-Object {
                    Test-PytestSelectionArgument -Argument $_
                }
        ).Count
        error = $ErrorMessage
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    $payload |
        ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $qualityRunMetadataPath -Encoding UTF8
}

function Write-QualityPerformanceArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Status,
        [string]$ErrorMessage,
        [string]$CurrentStep = $script:qualityRunCurrentStep
    )

    $performanceDirectory = Split-Path -Parent $qualityPerformanceLatestPath
    New-Item -ItemType Directory -Path $performanceDirectory -Force | Out-Null
    $steps = @($script:qualityStepTelemetry)
    $slowestSteps = @(
        $steps |
            Sort-Object -Property @{ Expression = { [int64]$_.wall_time_ms }; Descending = $true } |
            Select-Object -First 5
    )
    $outputBytesTotal = [int64]0
    foreach ($step in $steps) {
        if ($null -ne $step.output_bytes) {
            $outputBytesTotal += [int64]$step.output_bytes
        }
    }
    $payload = [ordered]@{
        schema_version = 1
        status = $Status
        profile = $script:qualityGateProfile
        verification_status = Get-QualityProfileVerificationStatus -Status $Status
        current_step = $CurrentStep
        command = (Get-QualityCommandText)
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        run_id = $qualityRunTimestamp
        run_started_at_utc = $script:qualityRunStartedAtUtc.ToString("o")
        run_duration_ms = Get-QualityRunDurationMs
        step_count = $steps.Count
        output_bytes_total = $outputBytesTotal
        selected_pytest_arguments = @($script:qualitySelectedPytestArguments)
        selected_test_count = @(
            $script:qualitySelectedPytestArguments |
                Where-Object {
                    $_.EndsWith(".py", [System.StringComparison]::OrdinalIgnoreCase)
                }
        ).Count
        slowest_steps = @($slowestSteps)
        steps = $steps
        error = $ErrorMessage
        raw_artifacts_available = $true
        full_verification_status = if ($script:qualityGateProfile -eq "full") {
            Get-QualityProfileVerificationStatus -Status $Status
        }
        else {
            "NOT_VERIFIED"
        }
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    $compactPayload = [ordered]@{
        schema_version = 1
        status = $Status
        profile = $script:qualityGateProfile
        verification_status = Get-QualityProfileVerificationStatus -Status $Status
        current_step = $CurrentStep
        command = (Get-QualityCommandText)
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        run_id = $qualityRunTimestamp
        run_started_at_utc = $script:qualityRunStartedAtUtc.ToString("o")
        run_duration_ms = Get-QualityRunDurationMs
        step_count = $steps.Count
        failed_steps = @(
            $steps |
                Where-Object {
                    [string]$_.status -notin @("PASS", "PASSED")
                } |
                Select-Object -First 5 |
                ForEach-Object { ConvertTo-CompactQualityStepSummary -Step $_ }
        )
        slowest_steps = @(
            $slowestSteps |
                ForEach-Object { ConvertTo-CompactQualityStepSummary -Step $_ }
        )
        selected_test_count = @(
            $script:qualitySelectedPytestArguments |
                Where-Object {
                    $_.EndsWith(".py", [System.StringComparison]::OrdinalIgnoreCase)
                }
        ).Count
        runtime_run_directory = "runtime\quality\" + $qualityRunTimestamp
        run_summary_path = "runtime\quality\" + $qualityRunTimestamp + "\summary.json"
        run_timings_path = "runtime\quality\" + $qualityRunTimestamp + "\timings.json"
        pytest_log_path = "runtime\quality\" + $qualityRunTimestamp + "\pytest.log"
        bandit_log_path = "runtime\quality\" + $qualityRunTimestamp + "\bandit.log"
        compatibility_latest_path = "runtime\artifacts\quality\gate\latest.json"
        deterministic_quality_gate_report_path = "runtime\artifacts\quality\gate\deterministic_quality_gate_latest.json"
        governance_gate_report_path = "runtime\artifacts\quality\gate\governance_gate_latest.json"
        raw_artifacts_available = $true
        full_verification_status = if ($script:qualityGateProfile -eq "full") {
            Get-QualityProfileVerificationStatus -Status $Status
        }
        else {
            "NOT_VERIFIED"
        }
        error = $ErrorMessage
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    $payload |
        ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath $qualityPerformanceLatestPath -Encoding UTF8
    $payload |
        ConvertTo-Json -Depth 8 -Compress |
        Add-Content -LiteralPath $qualityPerformanceHistoryPath -Encoding UTF8
    $compactPayload |
        ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath $qualityRuntimeLatestPath -Encoding UTF8
    $compactPayload |
        ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath $qualityRuntimeRunSummaryPath -Encoding UTF8
    [ordered]@{
        schema_version = 1
        run_id = $qualityRunTimestamp
        profile = $script:qualityGateProfile
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        steps = $steps
        slowest_steps = @($slowestSteps)
        output_bytes_total = $outputBytesTotal
    } |
        ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath $qualityRuntimeRunTimingsPath -Encoding UTF8
    $payload |
        ConvertTo-Json -Depth 8 -Compress |
        Add-Content -LiteralPath $qualityRuntimeHistoryPath -Encoding UTF8
    if (Test-Path -LiteralPath $durablePytestOutputPath -PathType Leaf) {
        Copy-Item -LiteralPath $durablePytestOutputPath -Destination $qualityRuntimePytestLogPath -Force
    }
    if (Test-Path -LiteralPath $banditOutputPath -PathType Leaf) {
        Copy-Item -LiteralPath $banditOutputPath -Destination $qualityRuntimeBanditLogPath -Force
    }
    Write-QualityBudgetArtifacts `
        -Status $Status `
        -ErrorMessage $ErrorMessage `
        -CurrentStep $CurrentStep `
        -Steps $steps `
        -SlowestSteps $slowestSteps `
        -OutputBytesTotal $outputBytesTotal
}

function Get-QualityBudgetTokenRisk {
    param(
        [Parameter(Mandatory = $true)]
        [int64]$OutputBytesTotal,
        [Parameter(Mandatory = $true)]
        [int64]$RunDurationMs,
        [Parameter(Mandatory = $true)]
        [int]$SelectedTestCount
    )

    if ($OutputBytesTotal -ge 100000 -or $RunDurationMs -ge 300000 -or $SelectedTestCount -ge 25) {
        return "HIGH"
    }
    if ($OutputBytesTotal -ge 25000 -or $RunDurationMs -ge 120000 -or $SelectedTestCount -ge 5) {
        return "MEDIUM"
    }
    return "LOW"
}

function Write-QualityBudgetArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Status,
        [string]$ErrorMessage,
        [string]$CurrentStep,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$Steps,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$SlowestSteps,
        [Parameter(Mandatory = $true)]
        [int64]$OutputBytesTotal
    )

    $runDurationMs = Get-QualityRunDurationMs
    $selectedTestCount = @(
        $script:qualitySelectedPytestArguments |
            Where-Object {
                Test-PytestSelectionArgument -Argument $_
            }
    ).Count
    $repositoryValidatorStep = @(
        $Steps |
            Where-Object {
                [string]$_.name -eq "Repository governance validator"
            } |
            Select-Object -First 1
    )
    $repositoryValidatorCacheMode = if ($repositoryValidatorStep.Count -gt 0) {
        [string]$repositoryValidatorStep[0].cache_mode
    }
    else {
        "NOT_RECORDED"
    }
    $pytestStep = @(
        $Steps |
            Where-Object {
                [string]$_.step_id -in @("pytest", "pytest_affected", "pytest_required")
            } |
            Select-Object -First 1
    )
    $pytestDurationMs = if ($pytestStep.Count -gt 0) {
        [int64]$pytestStep[0].wall_time_ms
    }
    else {
        [int64]0
    }
    $pytestTestCount = Get-PytestPassCount
    $budgetPayload = [ordered]@{
        schema_version = 1
        status = $Status
        profile = $script:qualityGateProfile
        verification_status = Get-QualityProfileVerificationStatus -Status $Status
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        run_id = $qualityRunTimestamp
        current_step = $CurrentStep
        run_duration_ms = $runDurationMs
        pytest_duration_ms = $pytestDurationMs
        non_pytest_duration_ms = [math]::Max(0, $runDurationMs - $pytestDurationMs)
        step_count = $Steps.Count
        selected_pytest_arguments = @($script:qualitySelectedPytestArguments)
        selected_test_count = $selectedTestCount
        pytest_test_count = $pytestTestCount
        selected_test_family = if ($script:qualityGateProfile -eq "full") {
            "FULL_TEST_SUITE"
        }
        elseif ($selectedTestCount -eq 0) {
            "NO_TEST_FILE_SELECTION"
        }
        else {
            "PROFILE_SCOPED_TESTS"
        }
        output_bytes_total = $OutputBytesTotal
        repository_validator_cache_status = $script:repositoryValidatorCacheStatus
        repository_validator_cache_reason = $script:repositoryValidatorCacheReason
        repository_validator_cache_mode = $repositoryValidatorCacheMode
        token_risk = Get-QualityBudgetTokenRisk `
            -OutputBytesTotal $OutputBytesTotal `
            -RunDurationMs $runDurationMs `
            -SelectedTestCount $selectedTestCount
        slowest_steps = @(
            $SlowestSteps |
                ForEach-Object { ConvertTo-CompactQualityStepSummary -Step $_ }
        )
        error = $ErrorMessage
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    $budgetPayload |
        ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath $qualityBudgetLatestPath -Encoding UTF8
    $budgetPayload |
        ConvertTo-Json -Depth 8 -Compress |
        Add-Content -LiteralPath $qualityBudgetHistoryPath -Encoding UTF8
}

function Write-CompactQualityConsoleOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Status,
        [string]$ErrorMessage,
        [string]$FailureStep
    )

    $evidencePath = (
        "runtime\quality\" +
        $qualityRunTimestamp +
        "\summary.json"
    )
    $selectedTestCount = @(
        $script:qualitySelectedPytestArguments |
            Where-Object {
                Test-PytestSelectionArgument -Argument $_
            }
    ).Count
    if ($Status -eq "QUALITY_GATE_FAILED") {
        $failedTelemetry = @(
            $script:qualityStepTelemetry |
                Where-Object { $_.status -in @("FAIL", "ERROR") } |
                Select-Object -Last 1
        )
        $failedTelemetryItem = if ($failedTelemetry.Count -gt 0) {
            $failedTelemetry[0]
        }
        else {
            $null
        }
        $failedStepId = if ($null -ne $failedTelemetryItem) {
            [string]$failedTelemetryItem.step_id
        }
        elseif (-not [string]::IsNullOrWhiteSpace($FailureStep)) {
            ConvertTo-QualityStepId -Name $FailureStep
        }
        else {
            "quality_gate"
        }
        $failedExitCode = if (
            $null -ne $failedTelemetryItem -and
            $null -ne $failedTelemetryItem.exit_code
        ) {
            [int]$failedTelemetryItem.exit_code
        }
        else {
            1
        }
        $actionableError = if ($null -ne $failedTelemetryItem) {
            [string]$failedTelemetryItem.first_actionable_error
        }
        else {
            ""
        }
        if (-not [string]::IsNullOrWhiteSpace($actionableError)) {
            $actionableError = Get-FirstActionableQualityError -Value $actionableError
        }
        if ([string]::IsNullOrWhiteSpace($actionableError)) {
            $actionableError = Get-FirstActionableQualityError -Value $ErrorMessage
        }
        if ([string]::IsNullOrWhiteSpace($actionableError)) {
            $actionableError = "Quality gate failed; inspect evidence."
        }
        $payload = [ordered]@{
            failed_step = $failedStepId
            exit_code = $failedExitCode
            first_actionable_error = $actionableError
            evidence_path = $evidencePath
        }
    }
    else {
        $tools = @(
            $script:qualityStepTelemetry |
                ForEach-Object { [string]$_.step_id } |
                Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
                Select-Object -Unique
        )
        $payload = [ordered]@{
            profile = $script:qualityGateProfile
            run_id = $qualityRunTimestamp
            status = $Status
            duration = [int64](Get-QualityRunDurationMs)
            tools = $tools
            selected_test_count = $selectedTestCount
            evidence_path = $evidencePath
        }
    }
    Write-Output ($payload | ConvertTo-Json -Depth 4 -Compress)
}

function Invoke-QualityGate {
    Assert-NoInlineApprovalGenerationRequested
    if (-not [string]::IsNullOrWhiteSpace($ApprovalRecordReportPath)) {
        Invoke-FullApprovalReplayQualityGate
        return
    }
    Reset-LatestQualityGateArtifacts
    Invoke-SourceGeneratedArtifactCleanup
    Invoke-QualityStep "Dependency check" @("-m", "pip", "check")
    Invoke-QualityStep "Ruff format" @("-m", "ruff", "format", "--check", ".")
    Invoke-QualityStep "Ruff lint" @("-m", "ruff", "check", ".")
    Invoke-QualityStep "Ruff maintainability ratchet" @(
        "-m",
        "ai4binance.ops.maintainability_ratchet",
        "--repository-root",
        $repoRoot
    )
    Invoke-QualityStep "MyPy" @("-m", "mypy")
    Invoke-QualityStep "Financial leak guard" @(
        "-m",
        "ai4binance.ops.financial_leak_guard",
        "--repository-root",
        $repoRoot
    )
    Invoke-QualityStep "Privacy leak guard" @(
        "-m",
        "ai4binance.ops.privacy_leak_guard",
        "--repository-root",
        $repoRoot
    )
    Assert-QualityWorkspaceStable -Stage "AFTER_FULL_STATIC_CHECKS"
    Invoke-RepositoryGovernanceValidator
    $script:mirrorRemoteCheck = Invoke-ConditionalMirrorHygiene
    Remove-GeneratedCoverageArtifacts
    Assert-QualityWorkspaceStable -Stage "BEFORE_FULL_PYTEST"
    $previousCoverageFile = $env:COVERAGE_FILE
    $env:COVERAGE_FILE = $coverageFile
    try {
        Invoke-PytestWithCapturedOutput
        Invoke-QualityStep "Coverage JSON" @(
            "-m",
            "coverage",
            "json",
            "--quiet",
            "-o",
            $coverageJsonPath
        )
        Invoke-CoveragePolicyEvaluation
        Publish-QualityRunEvidenceArtifacts
    }
    finally {
        if ($null -eq $previousCoverageFile) {
            Remove-Item Env:\COVERAGE_FILE -ErrorAction SilentlyContinue
        }
        else {
            $env:COVERAGE_FILE = $previousCoverageFile
        }
    }
    Invoke-BanditWithCapturedOutput
    Assert-QualityWorkspaceStable -Stage "BEFORE_DETERMINISTIC_QUALITY_GATE"
    Invoke-DeterministicQualityGate
    Invoke-DocsHygieneGateTests | Out-Null
    Invoke-ArtifactHygieneGateTests | Out-Null
    Invoke-ConstitutionSyncGateTests | Out-Null
    Assert-QualityWorkspaceStable -Stage "BEFORE_DETERMINISTIC_GOVERNANCE_GATE"
    Invoke-DeterministicGovernanceGate
    Invoke-GeneratedArtifactCleanup
    Invoke-ProcessTempRetentionCleanup
    Assert-QualityWorkspaceStable -Stage "BEFORE_GREEN_EVIDENCE"
    Write-QualityGateGreenEvidence
    Assert-QualityWorkspaceStable -Stage "AFTER_GREEN_EVIDENCE"
}

function Invoke-FastQualityGate {
    Reset-LatestQualityGateArtifacts
    Invoke-SourceGeneratedArtifactCleanup
    Invoke-QualityStep "Ruff format" @("-m", "ruff", "format", "--check", ".")
    Invoke-QualityStep "Ruff lint" @("-m", "ruff", "check", ".")
    Invoke-QualityStep "Ruff maintainability ratchet" @(
        "-m",
        "ai4binance.ops.maintainability_ratchet",
        "--repository-root",
        $repoRoot
    )
    Reset-DmypyStatusFile
    Invoke-QualityStep "dmypy" @(
        "-m",
        "mypy.dmypy",
        "--status-file",
        $dmypyStatusFile,
        "run",
        "--"
    )
    Assert-QualityWorkspaceStable -Stage "BEFORE_FAST_PYTEST"
    Invoke-ScopedPytestWithCapturedOutput `
        -Name "Pytest affected" `
        -PytestArguments (Get-FastAffectedPytestArguments)
    Invoke-ProcessTempRetentionCleanup
    Assert-QualityWorkspaceStable -Stage "BEFORE_FAST_PROFILE_EVIDENCE"
    Write-QualityProfileEvidence -Status "FAST_PROFILE_PASS"
}

function Invoke-StandardQualityGate {
    Reset-LatestQualityGateArtifacts
    Invoke-SourceGeneratedArtifactCleanup
    Invoke-QualityStep "Ruff format" @("-m", "ruff", "format", "--check", ".")
    Invoke-QualityStep "Ruff lint" @("-m", "ruff", "check", ".")
    Invoke-QualityStep "Ruff maintainability ratchet" @(
        "-m",
        "ai4binance.ops.maintainability_ratchet",
        "--repository-root",
        $repoRoot
    )
    Invoke-QualityStep "MyPy" @("-m", "mypy")
    Assert-QualityWorkspaceStable -Stage "BEFORE_STANDARD_PYTEST"
    Invoke-ScopedPytestWithCapturedOutput `
        -Name "Pytest required" `
        -PytestArguments (Get-StandardRequiredPytestArguments)
    Invoke-ProcessTempRetentionCleanup
    Assert-QualityWorkspaceStable -Stage "BEFORE_STANDARD_PROFILE_EVIDENCE"
    Write-QualityProfileEvidence -Status "STANDARD_PROFILE_PASS"
}

function Invoke-SelectedQualityGate {
    if ($script:qualityGateProfile -eq "fast") {
        Invoke-FastQualityGate
        return
    }
    if ($script:qualityGateProfile -eq "standard") {
        Invoke-StandardQualityGate
        return
    }
    Invoke-QualityGate
}

New-Item -ItemType Directory -Path $qualityGateArtifactDirectory -Force | Out-Null
Start-Transcript -Path $qualityRunOutputPath -Force | Out-Null
Write-QualityRunMetadata -Status $qualityRunStatus -CurrentStep $qualityRunCurrentStep
try {
    $script:qualityRunCurrentStep = "Quality gate Git write guard"
    Publish-QualityGateGitWriteLease
    $script:qualityRunCurrentStep = "Repository state baseline"
    $script:qualityInitialWorkspaceAttestation = Get-QualityWorkspaceAttestation
    Invoke-SelectedQualityGate
    $script:qualityRunCurrentStep = "COMPLETED"
    $qualityRunStatus = if ($script:qualityGateProfile -eq "full") {
        "TECHNICAL_QUALITY_PASS"
    }
    else {
        ($script:qualityGateProfile.ToUpperInvariant() + "_PROFILE_PASS")
    }
}
catch {
    $qualityRunFailedStep = $script:qualityRunCurrentStep
    $script:qualityRunCurrentStep = "FAILED"
    $qualityRunStatus = "QUALITY_GATE_FAILED"
    $qualityRunError = $_.Exception.Message
    $qualityGateExitCode = 1
    Write-QualityGateFailureEvidence `
        -FailureStatus $qualityRunStatus `
        -FailureStep $qualityRunFailedStep `
        -FailureMessage $qualityRunError
}
finally {
    try {
        Stop-Transcript | Out-Null
    }
    catch {
        if ($null -eq $qualityRunError) {
            $qualityRunError = $_.Exception.Message
        }
    }
    if ($null -eq $previousPythonDontWriteBytecode) {
        Remove-Item Env:\PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONDONTWRITEBYTECODE = $previousPythonDontWriteBytecode
    }
    if ($null -eq $previousPythonPath) {
        Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONPATH = $previousPythonPath
    }
    Remove-PytestTempArtifacts
    Invoke-TestTempRetentionCleanup
    Write-QualityPerformanceArtifacts `
        -Status $qualityRunStatus `
        -ErrorMessage $qualityRunError `
        -CurrentStep $script:qualityRunCurrentStep
    Write-QualityRunMetadata -Status $qualityRunStatus -ErrorMessage $qualityRunError
    Write-CompactQualityConsoleOutput `
        -Status $qualityRunStatus `
        -ErrorMessage $qualityRunError `
        -FailureStep $qualityRunFailedStep
    Remove-QualityGateGitWriteLease
    if ($qualityGateMutexAcquired) {
        $qualityGateMutex.ReleaseMutex()
    }
    $qualityGateMutex.Dispose()
}

if ($qualityGateExitCode -ne 0) {
    exit $qualityGateExitCode
}


