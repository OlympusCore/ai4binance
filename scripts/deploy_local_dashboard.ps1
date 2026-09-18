param(
    [switch]$Apply,
    [string]$ReceiptPath
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$sourceRoot = Join-Path $repositoryRoot "src\ai4binance\local_dashboard"
$deploymentRoot = Join-Path $repositoryRoot "runtime\dashboard"
$processRoot = Join-Path $repositoryRoot "runtime\tmp\process\dashboard-deploy"
$runId = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
$stageRoot = Join-Path $processRoot $runId

function Get-RelativePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($repositoryRoot + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "DASHBOARD_DEPLOY_PATH_OUTSIDE_REPOSITORY"
    }
    return $full.Substring($repositoryRoot.Length + 1).Replace("\", "/")
}

function Get-FileRecord {
    param([Parameter(Mandatory = $true)][string]$Path)
    $item = Get-Item -LiteralPath $Path
    return [ordered]@{
        path = Get-RelativePath -Path $item.FullName
        bytes = [int64]$item.Length
        sha256 = Get-Sha256 -Path $item.FullName
    }
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $algorithm = [System.Security.Cryptography.SHA256]::Create()
        try {
            return ([System.BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
        }
        finally {
            $algorithm.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

$sourceFiles = @(
    "build.py.in",
    "design_source.html",
    "install.ps1.in",
    "launch.ps1.in",
    "local_views.js",
    "lucide.js.gz",
    "market_views.py.in",
    "README.md",
    "refresh_learning.py.in",
    "server.py.in"
)
$deploymentFiles = @(
    "app.css",
    "app.js",
    "build.py",
    "index.html",
    "install.ps1",
    "launch.ps1",
    "local_views.js",
    "lucide.js",
    "market_views.py",
    "README.md",
    "refresh_learning.py",
    "server.py"
)

foreach ($name in $sourceFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot $name) -PathType Leaf)) {
        throw "DASHBOARD_CANONICAL_SOURCE_MISSING:$name"
    }
}

New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
try {
    foreach ($name in $sourceFiles) {
        Copy-Item -LiteralPath (Join-Path $sourceRoot $name) -Destination $stageRoot -Force
    }
    foreach ($template in @(
        "build.py",
        "install.ps1",
        "launch.ps1",
        "market_views.py",
        "refresh_learning.py",
        "server.py"
    )) {
        Copy-Item `
            -LiteralPath (Join-Path $stageRoot ($template + ".in")) `
            -Destination (Join-Path $stageRoot $template) `
            -Force
    }
    $compressedAsset = Join-Path $stageRoot "lucide.js.gz"
    $expandedAsset = Join-Path $stageRoot "lucide.js"
    $compressedStream = [System.IO.File]::OpenRead($compressedAsset)
    try {
        $gzipStream = [System.IO.Compression.GZipStream]::new(
            $compressedStream,
            [System.IO.Compression.CompressionMode]::Decompress
        )
        try {
            $expandedStream = [System.IO.File]::Create($expandedAsset)
            try {
                $gzipStream.CopyTo($expandedStream)
            }
            finally {
                $expandedStream.Dispose()
            }
        }
        finally {
            $gzipStream.Dispose()
        }
    }
    finally {
        $compressedStream.Dispose()
    }
    & python (Join-Path $stageRoot "build.py") (Join-Path $stageRoot "design_source.html") | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "DASHBOARD_BUILD_FAILED:$LASTEXITCODE"
    }

    $changes = @()
    foreach ($name in $deploymentFiles) {
        $staged = Join-Path $stageRoot $name
        $deployed = Join-Path $deploymentRoot $name
        $stagedHash = Get-Sha256 -Path $staged
        $deployedHash = if (Test-Path -LiteralPath $deployed -PathType Leaf) {
            Get-Sha256 -Path $deployed
        }
        else {
            $null
        }
        if ($stagedHash -ne $deployedHash) {
            $changes += $name
        }
    }

    if ($Apply) {
        New-Item -ItemType Directory -Path $deploymentRoot -Force | Out-Null
        foreach ($name in $deploymentFiles) {
            Copy-Item -LiteralPath (Join-Path $stageRoot $name) -Destination (Join-Path $deploymentRoot $name) -Force
        }
    }

    $restartSensitiveFiles = @(
        "app.css",
        "app.js",
        "index.html",
        "launch.ps1",
        "local_views.js",
        "lucide.js",
        "market_views.py",
        "refresh_learning.py",
        "server.py"
    )
    $restartRequired = [bool](
        $Apply -and
        @($changes | Where-Object { $_ -in $restartSensitiveFiles }).Count -gt 0
    )

    $receipt = [ordered]@{
        schema_version = "1.0"
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        applied = [bool]$Apply
        canonical_source = "src/ai4binance/local_dashboard"
        deployment_root = "runtime/dashboard"
        changed_files = @($changes)
        restart_required = $restartRequired
        preserved_paths = @(
            "runtime/dashboard/config.json",
            "runtime/dashboard/browser-profile",
            "runtime/dashboard/health.json",
            "runtime/dashboard/guardian.log"
        )
        source_files = @($sourceFiles | ForEach-Object { Get-FileRecord -Path (Join-Path $sourceRoot $_) })
        deployment_files = @($deploymentFiles | ForEach-Object { Get-FileRecord -Path (Join-Path $stageRoot $_) })
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }

    if ([string]::IsNullOrWhiteSpace($ReceiptPath)) {
        $ReceiptPath = if ($Apply) {
            Join-Path $deploymentRoot "source-manifest.json"
        }
        else {
            Join-Path $repositoryRoot "runtime\artifacts\repository_validation\runtime_hygiene\dashboard-deploy-dry-run.json"
        }
    }
    $receiptFullPath = [System.IO.Path]::GetFullPath($ReceiptPath)
    if (-not $receiptFullPath.StartsWith($repositoryRoot + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "DASHBOARD_RECEIPT_PATH_OUTSIDE_REPOSITORY"
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $receiptFullPath) -Force | Out-Null
    $receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $receiptFullPath -Encoding UTF8
    $receipt | ConvertTo-Json -Depth 6
}
finally {
    if (Test-Path -LiteralPath $stageRoot -PathType Container) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force -Confirm:$false
    }
}
