param(
    [int]$IntervalSeconds = 300,
    [switch]$RunOnce
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
$env:PYTHONDONTWRITEBYTECODE = "1"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$artifactDirectory = Join-Path $root "runtime\artifacts\repository_validation\governance"
$reportDirectory = Join-Path $root "runtime\reports\audit"
$stateDirectory = Join-Path $root "runtime\state"
$healthPath = Join-Path $stateDirectory "repository-governance-health.json"
$stdoutPath = Join-Path $root "runtime\logs\services\repository-governance.stdout.log"
$stderrPath = Join-Path $root "runtime\logs\services\repository-governance.stderr.log"

function Write-MonitorHealth {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [int]$ExitCode = 0,
        [string]$JsonPath = "",
        [string]$MarkdownPath = ""
    )
    $payload = [ordered]@{
        service = "repository-governance"
        status = $Status
        updated_at = [DateTimeOffset]::UtcNow.ToString("o")
        pid = $PID
        exit_code = $ExitCode
        latest_json_path = $JsonPath
        latest_markdown_path = $MarkdownPath
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    $temporary = "$healthPath.tmp"
    $payload | ConvertTo-Json -Depth 4 -Compress |
        Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $healthPath -Force
}

function Invoke-RepositoryGovernanceValidation {
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $jsonPath = Join-Path $artifactDirectory "repository-governance-$stamp.json"
    $markdownPath = Join-Path $reportDirectory "REPOSITORY_GOVERNANCE_$stamp.md"
    $latestJsonPath = Join-Path $artifactDirectory "repository-governance-latest.json"
    $latestMarkdownPath = Join-Path $reportDirectory "REPOSITORY_GOVERNANCE_LATEST.md"

    # The validator writes durable JSON/Markdown reports; quiet mode prevents
    # the always-on monitor from appending the full artifact inventory every cycle.
    & $python -B -m ai4binance.governance.repository_validator `
        --repository-root $root `
        --output-json $jsonPath `
        --output-markdown $markdownPath `
        --quiet `
        2>> $stderrPath
    $exitCode = [int]$LASTEXITCODE

    if (Test-Path -LiteralPath $jsonPath -PathType Leaf) {
        Copy-Item -LiteralPath $jsonPath -Destination $latestJsonPath -Force
    }
    if (Test-Path -LiteralPath $markdownPath -PathType Leaf) {
        Copy-Item -LiteralPath $markdownPath -Destination $latestMarkdownPath -Force
    }

    $status = if ($exitCode -eq 0) { "PASS" } else { "RUNNING_WITH_BLOCKERS" }
    Write-MonitorHealth `
        -Status $status `
        -ExitCode $exitCode `
        -JsonPath $latestJsonPath `
        -MarkdownPath $latestMarkdownPath
}

if ($IntervalSeconds -lt 30) {
    throw "IntervalSeconds must be at least 30 for background governance monitoring."
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Repository Python runtime not found: $python"
}

New-Item -ItemType Directory `
    -Path $artifactDirectory, $reportDirectory, $stateDirectory, (Split-Path -Parent $stdoutPath) `
    -Force | Out-Null

Write-MonitorHealth -Status "RUNNING"
while ($true) {
    Invoke-RepositoryGovernanceValidation
    if ($RunOnce) {
        break
    }
    Start-Sleep -Seconds $IntervalSeconds
}

