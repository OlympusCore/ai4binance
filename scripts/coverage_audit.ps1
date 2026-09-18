param(
    [string]$CoverageJsonPath = "",
    [double]$Threshold = 93.0,
    [double]$TargetCoverage = 95.0,
    [string]$OutputDirectory = "",
    [ValidateSet("Coverage", "Risk", "BranchPressure", "Remediation")]
    [string]$SortBy = "Coverage",
    [string]$Priority = "",
    [string]$Tier = "",
    [string]$Authority = "",
    [switch]$TargetOnly,
    [ValidateSet("Table", "Json")]
    [string]$Format = "Table"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$policyDocumentPath = "docs/policies/quality/coverage_improvement_strategy_policy.md"
$coverageConfigPath = "config/quality/coverage-targets.json"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = "python"
}

function Get-RepositoryRelativePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )
    return $Path.Replace("\", "/").TrimStart("/")
}

function Resolve-CoverageJsonPath {
    if ($CoverageJsonPath.Trim()) {
        return (Resolve-Path -LiteralPath $CoverageJsonPath).Path
    }

    $coverageSearchRoots = @(
        (Join-Path $repoRoot "runtime\artifacts\quality\gate\runs"),
        (Join-Path $repoRoot "runtime\quality"),
        (Join-Path $repoRoot "runtime\tmp\process\pytest")
    )
    foreach ($searchRoot in $coverageSearchRoots) {
        if (-not (Test-Path -LiteralPath $searchRoot -PathType Container)) {
            continue
        }
        $latestCoverage = Get-ChildItem `
            -LiteralPath $searchRoot `
            -Recurse `
            -File `
            -Filter "coverage.json" `
            -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        if ($null -ne $latestCoverage) {
            return $latestCoverage.FullName
        }
    }

    throw (
        "Coverage JSON path was not provided and no coverage.json artifact " +
        "was found under durable quality runs or runtime\tmp\process\pytest."
    )
}

if (-not $OutputDirectory.Trim()) {
    $OutputDirectory = Join-Path $repoRoot "runtime\artifacts\quality\gate"
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$resolvedCoverageJsonPath = Resolve-CoverageJsonPath
$repoRootPrefix = $repoRoot.TrimEnd("\") + "\"
$coverageJsonDisplayPath = Get-RepositoryRelativePath -Path $resolvedCoverageJsonPath
if ($resolvedCoverageJsonPath.StartsWith(
        $repoRootPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    $coverageJsonDisplayPath = Get-RepositoryRelativePath -Path (
        $resolvedCoverageJsonPath.Substring($repoRootPrefix.Length)
    )
}

$arguments = @(
    "-m",
    "ai4binance.ops.coverage_audit",
    "--coverage-json",
    $resolvedCoverageJsonPath,
    "--output-directory",
    $OutputDirectory,
    "--threshold",
    ([string]$Threshold),
    "--target-coverage",
    ([string]$TargetCoverage),
    "--policy-document",
    $policyDocumentPath,
    "--config",
    $coverageConfigPath,
    "--coverage-json-display",
    $coverageJsonDisplayPath,
    "--sort-by",
    $SortBy
)
if ($Priority.Trim()) {
    $arguments += @("--priority", $Priority)
}
if ($Tier.Trim()) {
    $arguments += @("--tier", $Tier)
}
if ($Authority.Trim()) {
    $arguments += @("--authority", $Authority)
}
if ($TargetOnly) {
    $arguments += "--target-only"
}

 $previousPythonPath = $env:PYTHONPATH
if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
}
else {
    $env:PYTHONPATH = (Join-Path $repoRoot "src") + ";" + $previousPythonPath
}
try {
    $payloadJson = & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Coverage audit generation failed with exit code $LASTEXITCODE"
    }
}
finally {
    if ($null -eq $previousPythonPath) {
        Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONPATH = $previousPythonPath
    }
}
$payload = $payloadJson | ConvertFrom-Json
$orderedRows = @($payload.files)
$jsonOutputPath = Join-Path $OutputDirectory "coverage_audit_below_93.json"
$markdownOutputPath = Join-Path $OutputDirectory "coverage_audit_below_93.md"

if ($Format -eq "Json") {
    $payloadJson
}
else {
    Write-Output "Coverage audit: files below $("{0:N2}" -f $Threshold)%"
    Write-Output "Manual remediation target: $("{0:N2}" -f $TargetCoverage)%"
    Write-Output "Sort: $SortBy"
    Write-Output "JSON output: $jsonOutputPath"
    Write-Output "Markdown output: $markdownOutputPath"
    if ($orderedRows.Count -eq 0) {
        Write-Output "No files below threshold."
    }
    else {
        $orderedRows |
            Format-Table -Property `
                risk_rank,
                coverage_rank,
                remediation_rank,
                path,
                priority,
                tier,
                coverage_percent,
                target_coverage,
                coverage_gap_to_target,
                branch_coverage_percent,
                missing_lines `
                -AutoSize |
            Out-String -Stream -Width 4096
    }
}
