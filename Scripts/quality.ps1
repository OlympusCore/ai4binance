$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$pytestTempRoot = Join-Path $PSScriptRoot "..\Artifacts\TestTemp"
New-Item -ItemType Directory -Path $pytestTempRoot -Force | Out-Null
$pytestTemp = Join-Path (
    $pytestTempRoot
) ("ai4binance-pytest-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $pytestTemp -Force | Out-Null
$coverageFile = Join-Path $pytestTemp ".coverage"
$qualityEvidencePath = Join-Path $repoRoot "Artifacts\quality-gate\latest.json"

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

function Invoke-GeneratedArtifactCleanup {
    $cleanupScript = Join-Path $PSScriptRoot "cleanup_generated_artifacts.ps1"
    & $cleanupScript -Apply -Mode @("Caches", "Coverage") | Out-Null
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Generated artifact cleanup failed with exit code $exitCode"
    }
}

function Invoke-QualityStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $python @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode"
    }
}

function Write-QualityGateGreenEvidence {
    $evidenceDirectory = Split-Path -Parent $qualityEvidencePath
    New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null
    $payload = [ordered]@{
        status = "QUALITY_GATE_GREEN"
        command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Scripts\quality.ps1"
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    $payload |
        ConvertTo-Json -Depth 3 |
        Set-Content -LiteralPath $qualityEvidencePath -Encoding UTF8
}

Invoke-QualityStep "Dependency check" @("-m", "pip", "check")
Invoke-QualityStep "Ruff format" @("-m", "ruff", "format", "--check", ".")
Invoke-QualityStep "Ruff lint" @("-m", "ruff", "check", ".")
Invoke-QualityStep "MyPy" @("-m", "mypy")
Remove-GeneratedCoverageArtifacts
$previousCoverageFile = $env:COVERAGE_FILE
$env:COVERAGE_FILE = $coverageFile
try {
    Invoke-QualityStep "Pytest" @("-m", "pytest", "--basetemp", $pytestTemp)
}
finally {
    if ($null -eq $previousCoverageFile) {
        Remove-Item Env:\COVERAGE_FILE -ErrorAction SilentlyContinue
    }
    else {
        $env:COVERAGE_FILE = $previousCoverageFile
    }
}
Invoke-QualityStep "Bandit" @("-m", "bandit", "-q", "-r", "src")
Invoke-GeneratedArtifactCleanup
Write-QualityGateGreenEvidence
