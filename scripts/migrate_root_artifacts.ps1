param()

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$rootArtifacts = Join-Path $repoRoot "artifacts"

function Assert-InRepoPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if (
        $fullPath -ne $repoRoot -and
        -not $fullPath.StartsWith($repoRoot + "\", [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "Refusing path outside repository: $fullPath"
    }
    return $fullPath
}

function Get-LegacyCollisionPath {
    param([Parameter(Mandatory = $true)][string]$DestinationPath)
    $directory = Split-Path -Parent $DestinationPath
    $leaf = Split-Path -Leaf $DestinationPath
    $base = [System.IO.Path]::GetFileNameWithoutExtension($leaf)
    $extension = [System.IO.Path]::GetExtension($leaf)
    $candidate = Join-Path $directory ($base + ".legacy-from-root-artifacts" + $extension)
    $index = 2
    while (Test-Path -LiteralPath $candidate) {
        $candidate = Join-Path $directory (
            $base + ".legacy-from-root-artifacts-" + $index + $extension
        )
        $index += 1
    }
    return $candidate
}

function Merge-MovePath {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$DestinationPath
    )

    $source = Assert-InRepoPath -Path $SourcePath
    $destination = Assert-InRepoPath -Path $DestinationPath
    if (-not (Test-Path -LiteralPath $source)) {
        return
    }

    if (Test-Path -LiteralPath $source -PathType Leaf) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force |
            Out-Null
        if (-not (Test-Path -LiteralPath $destination)) {
            Move-Item -LiteralPath $source -Destination $destination -Force
            return
        }
        $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
        $destinationHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
        if ($sourceHash -eq $destinationHash) {
            Remove-Item -LiteralPath $source -Force
            return
        }
        $legacyPath = Get-LegacyCollisionPath -DestinationPath $destination
        Move-Item -LiteralPath $source -Destination $legacyPath -Force
        return
    }

    if (-not (Test-Path -LiteralPath $destination)) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force |
            Out-Null
        Move-Item -LiteralPath $source -Destination $destination
        return
    }

    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Get-ChildItem -LiteralPath $source -Force -Name | ForEach-Object {
        $childSource = Join-Path $source $_
        $childDestination = Join-Path $destination $_
        if ((Test-Path -LiteralPath $childSource -PathType Container) -and -not (Test-Path -LiteralPath $childDestination)) {
            Move-Item -LiteralPath $childSource -Destination $childDestination
            return
        }
        Merge-MovePath `
            -SourcePath $childSource `
            -DestinationPath $childDestination
    }
    Remove-Item -LiteralPath $source -Force -Recurse
}

if (-not (Test-Path -LiteralPath $rootArtifacts -PathType Container)) {
    [pscustomobject]@{
        status = "NO_ROOT_ARTIFACTS"
        root_artifacts = "artifacts"
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Depth 4
    exit 0
}

$mappings = [ordered]@{
    "artifacts\accounting-ui" = "runtime\artifacts\accounting_ui"
    "artifacts\auto_audit" = "runtime\artifacts\assurance\auto_audit"
    "artifacts\latency" = "runtime\artifacts\benchmarks\latency"
    "artifacts\maintenance-archive" = "runtime\artifacts\maintenance_archive"
    "artifacts\market-outlook" = "runtime\artifacts\decisions\market_outlook"
    "artifacts\quality_gate" = "runtime\artifacts\quality\gate"
    "artifacts\scanner" = "runtime\artifacts\decisions\scanner"
    "artifacts\second-brain" = "runtime\artifacts\context\second_brain"
    "artifacts\security_tooling" = "runtime\artifacts\assurance\security_tooling"
    "artifacts\system_audit" = "runtime\artifacts\assurance\system_audit"
    "artifacts\test_temp" = "runtime\tmp\test_temp"
    "artifacts\user-reports" = "runtime\artifacts\user_reports"
    "artifacts\validation" = "runtime\artifacts\validation"
    "artifacts\virtual-market" = "runtime\artifacts\research\virtual_market"
    "artifacts\ykb" = "runtime\artifacts\user_reports\ykb"
    "artifacts\file-interaction-report.md" = "runtime\reports\file-interaction-report.md"
}

$moved = [System.Collections.Generic.List[object]]::new()
foreach ($entry in $mappings.GetEnumerator()) {
    $source = Join-Path $repoRoot $entry.Key
    $destination = Join-Path $repoRoot $entry.Value
    if (-not (Test-Path -LiteralPath $source)) {
        continue
    }
    Merge-MovePath -SourcePath $source -DestinationPath $destination
    $moved.Add(
        [pscustomobject]@{
            source = $entry.Key.Replace("\", "/")
            destination = $entry.Value.Replace("\", "/")
        }
    )
}

if (Test-Path -LiteralPath $rootArtifacts) {
    $remaining = Get-ChildItem -LiteralPath $rootArtifacts -Force -ErrorAction SilentlyContinue
    if (@($remaining).Count -eq 0) {
        Remove-Item -LiteralPath $rootArtifacts -Force
    }
}

[pscustomobject]@{
    status = if (Test-Path -LiteralPath $rootArtifacts) {
        "ROOT_ARTIFACTS_REMAIN"
    }
    else {
        "ROOT_ARTIFACTS_REMOVED"
    }
    root_artifacts = "artifacts"
    moved = @($moved)
    execution_allowed = $false
    promotion_status = "RESEARCH_ONLY"
    live_eligibility_status = "LIVE_ORDER_BLOCKED"
} | ConvertTo-Json -Depth 6

if (Test-Path -LiteralPath $rootArtifacts) {
    exit 1
}
