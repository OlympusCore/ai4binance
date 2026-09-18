[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$RepositoryRoot = ""
)

$ErrorActionPreference = "Stop"

function Write-QualityGateGitWriteBlock {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Reason
    )

    [Console]::Error.WriteLine($Reason)
    [Console]::Error.WriteLine("RESEARCH_ONLY")
    [Console]::Error.WriteLine("LIVE_ORDER_BLOCKED")
}

try {
    if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
        $RepositoryRoot = Join-Path $PSScriptRoot ".."
    }
    $resolvedRepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
    $gitCommonDirectoryOutput = & git -C $resolvedRepositoryRoot rev-parse `
        --path-format=absolute `
        --git-common-dir 2>$null
    $gitExitCode = $LASTEXITCODE
    if ($gitExitCode -ne 0 -or @($gitCommonDirectoryOutput).Count -eq 0) {
        throw "GIT_COMMON_DIRECTORY_UNAVAILABLE"
    }
    $gitCommonDirectoryText = [string](@($gitCommonDirectoryOutput)[-1])
    if ([string]::IsNullOrWhiteSpace($gitCommonDirectoryText)) {
        throw "GIT_COMMON_DIRECTORY_UNAVAILABLE"
    }
    $gitCommonDirectory = [IO.Path]::GetFullPath($gitCommonDirectoryText.Trim())
    $leasePath = Join-Path $gitCommonDirectory `
        "ai4binance-quality-gate-write-lease.json"
    if (-not (Test-Path -LiteralPath $leasePath -PathType Leaf)) {
        exit 0
    }

    $lease = Get-Content -LiteralPath $leasePath -Raw | ConvertFrom-Json
    if (
        [string]$lease.status -ne "QUALITY_GATE_ACTIVE" -or
        [string]::IsNullOrWhiteSpace([string]$lease.run_id) -or
        [int64]$lease.process_id -le 0 -or
        [string]::IsNullOrWhiteSpace([string]$lease.process_started_at_utc)
    ) {
        throw "QUALITY_GATE_GIT_WRITE_LEASE_INVALID"
    }

    $leaseProcess = Get-Process -Id ([int]$lease.process_id) `
        -ErrorAction SilentlyContinue
    if ($null -eq $leaseProcess) {
        exit 0
    }
    $recordedStartTime = [DateTimeOffset]::Parse(
        [string]$lease.process_started_at_utc,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind
    ).UtcDateTime
    $actualStartTime = $leaseProcess.StartTime.ToUniversalTime()
    if ($recordedStartTime.Ticks -ne $actualStartTime.Ticks) {
        exit 0
    }

    Write-QualityGateGitWriteBlock -Reason (
        "QUALITY_GATE_GIT_WRITE_BLOCKED: active run " + [string]$lease.run_id
    )
    exit 1
}
catch {
    Write-QualityGateGitWriteBlock -Reason (
        "QUALITY_GATE_GIT_WRITE_GUARD_ERROR: " + $_.Exception.Message
    )
    exit 1
}
