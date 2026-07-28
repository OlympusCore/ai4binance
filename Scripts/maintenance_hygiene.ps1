param(
    [switch]$Apply,
    [switch]$IncludeBacktest,
    [int]$MinimumSizeMB = 100
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$archiveRoot = Join-Path $root "Artifacts\maintenance-archive"
$stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runRoot = Join-Path $archiveRoot $stamp
$manifestPath = Join-Path $runRoot "manifest.json"

function Resolve-InRepoPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not $resolved.StartsWith($root + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside repository: $resolved"
    }
    return $resolved
}

function Get-RepoRelativePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if (-not $fullPath.StartsWith($root + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside repository: $fullPath"
    }
    return $fullPath.Substring($root.Length + 1)
}

function Test-ExclusiveRead {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        $stream = [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::None
        )
        $stream.Dispose()
        return $true
    }
    catch {
        return $false
    }
}

$candidateRoots = @("Logs")
if ($IncludeBacktest) {
    $candidateRoots += "Backtest\validation"
}
$minimumBytes = [int64]$MinimumSizeMB * 1MB
$candidates = foreach ($relativeRoot in $candidateRoots) {
    $candidateRoot = Join-Path $root $relativeRoot
    if (-not (Test-Path -LiteralPath $candidateRoot -PathType Container)) {
        continue
    }
    Get-ChildItem -LiteralPath $candidateRoot -File -Recurse |
        Where-Object {
            $_.Length -ge $minimumBytes -and
            ($_.Extension -in @(".jsonl", ".log"))
        } |
        Sort-Object Length -Descending
}

$rows = foreach ($item in $candidates) {
    $resolved = Resolve-InRepoPath -Path $item.FullName
    $relative = Get-RepoRelativePath -Path $resolved
    $archivePath = Join-Path $runRoot ($relative + ".zip")
    [pscustomobject]@{
        path = $relative
        size_mb = [math]::Round($item.Length / 1MB, 2)
        updated_at = $item.LastWriteTimeUtc.ToString("o")
        archive_path = Get-RepoRelativePath -Path $archivePath
        archived = $false
        skipped_reason = $null
    }
}

if ($Apply -and @($rows).Count -gt 0) {
    New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
    foreach ($row in $rows) {
        $source = Join-Path $root $row.path
        $source = Resolve-InRepoPath -Path $source
        if (-not (Test-ExclusiveRead -Path $source)) {
            $row.skipped_reason = "FILE_IN_USE"
            continue
        }
        $archivePath = Join-Path $root $row.archive_path
        New-Item -ItemType Directory -Path (Split-Path -Parent $archivePath) -Force |
            Out-Null
        Compress-Archive -LiteralPath $source -DestinationPath $archivePath -Force
        Remove-Item -LiteralPath $source -Force
        $row.archived = $true
    }
    [pscustomobject]@{
        command = "maintenance-hygiene"
        applied = $true
        include_backtest = [bool]$IncludeBacktest
        minimum_size_mb = $MinimumSizeMB
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        files = @($rows)
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
}

[pscustomobject]@{
    command = "maintenance-hygiene"
    applied = [bool]$Apply
    include_backtest = [bool]$IncludeBacktest
    minimum_size_mb = $MinimumSizeMB
    archive_directory = if ($Apply) {
        Get-RepoRelativePath -Path $runRoot
    }
    else {
        $null
    }
    candidate_count = @($rows).Count
    archived_count = @($rows | Where-Object { $_.archived }).Count
    skipped_count = @($rows | Where-Object { $_.skipped_reason }).Count
    files = @($rows)
    execution_allowed = $false
    live_eligibility_status = "LIVE_ORDER_BLOCKED"
} | ConvertTo-Json -Depth 5
