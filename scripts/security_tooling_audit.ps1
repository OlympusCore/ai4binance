[CmdletBinding()]
param(
    [ValidateSet("pypi", "osv", "esms")]
    [string]$VulnerabilityService = "pypi",
    [ValidateRange(1, 300)]
    [int]$PipAuditTimeoutSeconds = 15
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")

$gitleaksVersion = "8.30.1"
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$gitleaks = Join-Path (
    $repositoryRoot
) "tools\gitleaks\v${gitleaksVersion}\gitleaks.exe"
$artifactRoot = Join-Path $repositoryRoot "runtime\artifacts\assurance\security_tooling"
$stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$pipAuditReport = Join-Path $artifactRoot (
    "pip-audit-${VulnerabilityService}-${stamp}.json"
)
$pipAuditLog = Join-Path $artifactRoot (
    "pip-audit-${VulnerabilityService}-${stamp}.log"
)
$gitleaksReport = Join-Path $artifactRoot "gitleaks-${stamp}.json"
$gitleaksLog = Join-Path $artifactRoot "gitleaks-${stamp}.log"
$summaryReport = Join-Path $artifactRoot "security_tooling-${stamp}.json"

New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null

$blockers = [Collections.Generic.List[string]]::new()
$pipAuditExitCode = $null
$gitleaksExitCode = $null
$pipAuditFindingCount = $null
$gitleaksFindingCount = $null
$previousPipApiPythonLocation = $env:PIPAPI_PYTHON_LOCATION

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $blockers.Add("SECURITY_TOOLING_VENV_MISSING")
}
else {
    $env:PIPAPI_PYTHON_LOCATION = $python
    $pipAuditBootstrap = (
        "import truststore; truststore.inject_into_ssl(); " +
        "from pip_audit._cli import audit; audit()"
    )
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $python -c $pipAuditBootstrap --local --skip-editable --format json `
            --vulnerability-service $VulnerabilityService --progress-spinner off `
            --timeout $PipAuditTimeoutSeconds --output $pipAuditReport 2> $pipAuditLog
        $pipAuditExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if (Test-Path -LiteralPath $pipAuditReport -PathType Leaf) {
        try {
            $pipAuditPayload = Get-Content -LiteralPath $pipAuditReport -Raw |
                ConvertFrom-Json
            $pipAuditFindingCount = 0
            foreach ($dependency in @($pipAuditPayload.dependencies)) {
                if ($null -ne $dependency.vulns) {
                    $pipAuditFindingCount += @($dependency.vulns).Count
                }
            }
        }
        catch {
            $blockers.Add("DEPENDENCY_AUDIT_REPORT_INVALID")
        }
    }
    if ($pipAuditExitCode -ne 0) {
        if ($pipAuditFindingCount -gt 0) {
            $blockers.Add("DEPENDENCY_VULNERABILITIES_REQUIRE_REVIEW")
        }
        elseif (-not $blockers.Contains("DEPENDENCY_AUDIT_REPORT_INVALID")) {
            $blockers.Add("DEPENDENCY_AUDIT_FAILED")
        }
    }
}

if (-not (Test-Path -LiteralPath $gitleaks -PathType Leaf)) {
    $blockers.Add("GITLEAKS_NOT_INSTALLED")
}
else {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $gitleaks git --redact=100 --report-format json `
            --report-path $gitleaksReport --no-banner --no-color --timeout 300 `
            $repositoryRoot 2> $gitleaksLog
        $gitleaksExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if (Test-Path -LiteralPath $gitleaksReport -PathType Leaf) {
        try {
            $gitleaksPayload = Get-Content -LiteralPath $gitleaksReport -Raw |
                ConvertFrom-Json
            $gitleaksFindingCount = @($gitleaksPayload).Count
        }
        catch {
            $blockers.Add("SECRET_SCAN_REPORT_INVALID")
        }
    }
    if ($gitleaksExitCode -ne 0) {
        if ($gitleaksFindingCount -gt 0) {
            $blockers.Add("SECRET_FINDINGS_REQUIRE_REVIEW")
        }
        elseif (-not $blockers.Contains("SECRET_SCAN_REPORT_INVALID")) {
            $blockers.Add("SECRET_SCAN_FAILED")
        }
    }
}

if ($null -eq $previousPipApiPythonLocation) {
    Remove-Item Env:\PIPAPI_PYTHON_LOCATION -ErrorAction SilentlyContinue
}
else {
    $env:PIPAPI_PYTHON_LOCATION = $previousPipApiPythonLocation
}

$status = if ($blockers.Count -eq 0) { "PASSED" } else { "REVIEW_REQUIRED" }
$summary = [ordered]@{
    schema_version = "AI4BINANCE-SECURITY-TOOLING-1.0"
    created_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    status = $status
    scanners = [ordered]@{
        pip_audit = [ordered]@{
            vulnerability_service = $VulnerabilityService
            timeout_seconds = $PipAuditTimeoutSeconds
            exit_code = $pipAuditExitCode
            finding_count = $pipAuditFindingCount
            report_path = $pipAuditReport
            log_path = $pipAuditLog
        }
        gitleaks = [ordered]@{
            version = $gitleaksVersion
            exit_code = $gitleaksExitCode
            finding_count = $gitleaksFindingCount
            report_path = $gitleaksReport
            log_path = $gitleaksLog
            redaction_percent = 100
        }
    }
    blockers = @($blockers)
    auto_fix_allowed = $false
    execution_allowed = $false
    promotion_status = "RESEARCH_ONLY"
    live_eligibility_status = "LIVE_ORDER_BLOCKED"
}
$summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $summaryReport `
    -Encoding utf8

Write-Output "SECURITY_TOOLING_STATUS=$status"
Write-Output "SUMMARY_PATH=$summaryReport"
Write-Output "RESEARCH_ONLY"
Write-Output "LIVE_ORDER_BLOCKED"

if ($blockers.Count -ne 0) {
    exit 1
}

