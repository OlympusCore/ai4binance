[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")

$gitleaksVersion = "8.30.1"
$gitleaksArchive = "gitleaks_${gitleaksVersion}_windows_x64.zip"
$gitleaksSha256 = "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e"
$gitleaksUri = (
    "https://github.com/gitleaks/gitleaks/releases/download/" +
    "v${gitleaksVersion}/${gitleaksArchive}"
)

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "SECURITY_TOOLING_VENV_MISSING: $python"
}

Push-Location $repositoryRoot
try {
    & uv sync --frozen --extra security --python $python
    if ($LASTEXITCODE -ne 0) {
        throw "SECURITY_TOOLING_UV_SYNC_FAILED"
    }
}
finally {
    Pop-Location
}

$downloadsRoot = Join-Path $repositoryRoot "tools\downloads"
$gitleaksBase = Join-Path $repositoryRoot "tools\gitleaks"
$gitleaksRoot = Join-Path $gitleaksBase "v${gitleaksVersion}"
$archivePath = Join-Path $downloadsRoot $gitleaksArchive

$resolvedBase = [IO.Path]::GetFullPath($gitleaksBase)
$resolvedTarget = [IO.Path]::GetFullPath($gitleaksRoot)
if (-not $resolvedTarget.StartsWith(
    $resolvedBase + [IO.Path]::DirectorySeparatorChar,
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw "SECURITY_TOOLING_UNSAFE_TARGET: $resolvedTarget"
}

New-Item -ItemType Directory -Path $downloadsRoot -Force | Out-Null
New-Item -ItemType Directory -Path $gitleaksRoot -Force | Out-Null
Invoke-WebRequest -Uri $gitleaksUri -OutFile $archivePath -Headers @{
    "User-Agent" = "AI4BINANCE-Security-Tooling"
}

$actualSha256 = (
    Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($actualSha256 -ne $gitleaksSha256) {
    throw "SECURITY_TOOLING_GITLEAKS_CHECKSUM_MISMATCH: $actualSha256"
}

Expand-Archive -LiteralPath $archivePath -DestinationPath $gitleaksRoot -Force
$gitleaks = Join-Path $gitleaksRoot "gitleaks.exe"
if (-not (Test-Path -LiteralPath $gitleaks -PathType Leaf)) {
    throw "SECURITY_TOOLING_GITLEAKS_EXECUTABLE_MISSING: $gitleaks"
}

$installedVersion = (& $gitleaks version).Trim()
if ($LASTEXITCODE -ne 0 -or $installedVersion -ne $gitleaksVersion) {
    throw "SECURITY_TOOLING_GITLEAKS_VERSION_MISMATCH: $installedVersion"
}

$previousPipApiPythonLocation = $env:PIPAPI_PYTHON_LOCATION
$env:PIPAPI_PYTHON_LOCATION = $python
try {
    & $python -m pip_audit --version
    if ($LASTEXITCODE -ne 0) {
        throw "SECURITY_TOOLING_PIP_AUDIT_VERSION_FAILED"
    }
}
finally {
    if ($null -eq $previousPipApiPythonLocation) {
        Remove-Item Env:\PIPAPI_PYTHON_LOCATION -ErrorAction SilentlyContinue
    }
    else {
        $env:PIPAPI_PYTHON_LOCATION = $previousPipApiPythonLocation
    }
}

Write-Output "SECURITY_TOOLING_INSTALLED"
Write-Output "GITLEAKS_VERSION=$installedVersion"
Write-Output "GITLEAKS_SHA256=$actualSha256"
Write-Output "GITLEAKS_PATH=$gitleaks"
Write-Output "RESEARCH_ONLY"
Write-Output "LIVE_ORDER_BLOCKED"
