param(
    [switch]$Apply,
    [int]$MinimumSizeMB = 100,
    [string]$ArchiveRoot = "H:\AI4BINANCE-Archive\backtest-validation"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$sourceRoot = Join-Path $repoRoot "backtest\validation"
$stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$manifestDirectory = Join-Path $repoRoot "runtime\artifacts\maintenance_archive\$stamp"
$manifestPath = Join-Path $manifestDirectory "backtest-validation-archive.json"

function Get-RepoRelativePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if (-not $fullPath.StartsWith($repoRoot + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside repository: $fullPath"
    }
    return $fullPath.Substring($repoRoot.Length + 1)
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

if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
    [pscustomobject]@{
        command = "archive-backtest-validation"
        applied = [bool]$Apply
        status = "NO_SOURCE_DIRECTORY"
        source_root = "backtest\validation"
        archive_root = $ArchiveRoot
        candidate_count = 0
        archived_count = 0
        skipped_count = 0
        files = @()
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Depth 5
    exit 0
}

$minimumBytes = [int64]$MinimumSizeMB * 1MB
$archiveRootFull = [System.IO.Path]::GetFullPath($ArchiveRoot)
$candidates = Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -Filter "*.jsonl" |
    Where-Object { $_.Length -ge $minimumBytes } |
    Sort-Object Length -Descending

$rows = foreach ($item in $candidates) {
    $relative = Get-RepoRelativePath -Path $item.FullName
    $relativeUnderValidation = $item.FullName.Substring($sourceRoot.Length + 1)
    $archivePath = Join-Path $archiveRootFull $stamp
    $archivePath = Join-Path $archivePath ($relativeUnderValidation + ".zip")
    [pscustomobject]@{
        path = $relative
        size_mb = [math]::Round($item.Length / 1MB, 2)
        archive_path = $archivePath
        archived = $false
        skipped_reason = $null
    }
}

if ($Apply -and @($rows).Count -gt 0) {
    foreach ($row in $rows) {
        $source = Join-Path $repoRoot $row.path
        if (-not (Test-ExclusiveRead -Path $source)) {
            $row.skipped_reason = "FILE_IN_USE"
            continue
        }
        New-Item -ItemType Directory -Path (Split-Path -Parent $row.archive_path) -Force | Out-Null
        Compress-Archive -LiteralPath $source -DestinationPath $row.archive_path -Force
        if (-not (Test-Path -LiteralPath $row.archive_path -PathType Leaf)) {
            $row.skipped_reason = "ARCHIVE_WRITE_FAILED"
            continue
        }
        if ((Get-Item -LiteralPath $row.archive_path).Length -lt 1) {
            $row.skipped_reason = "ARCHIVE_EMPTY"
            continue
        }
        Remove-Item -LiteralPath $source -Force
        $row.archived = $true
    }
}

New-Item -ItemType Directory -Path $manifestDirectory -Force | Out-Null
$result = [pscustomobject]@{
    command = "archive-backtest-validation"
    applied = [bool]$Apply
    status = "COMPLETE"
    source_root = "backtest\validation"
    archive_root = $archiveRootFull
    generated_at = [DateTimeOffset]::UtcNow.ToString("o")
    minimum_size_mb = $MinimumSizeMB
    candidate_count = @($rows).Count
    archived_count = @($rows | Where-Object { $_.archived }).Count
    skipped_count = @($rows | Where-Object { $_.skipped_reason }).Count
    files = @($rows)
    manifest_path = Get-RepoRelativePath -Path $manifestPath
    execution_allowed = $false
    live_eligibility_status = "LIVE_ORDER_BLOCKED"
}
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
$result | ConvertTo-Json -Depth 6
