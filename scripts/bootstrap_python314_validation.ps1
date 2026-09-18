[CmdletBinding()]
param(
    [string]$ValidationEnvironment = "runtime\tmp\python3147-validation-venv"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")

$canonicalPython = "3.14.7"
$managedRuntimeName = "cpython-3.14.7-windows-x86_64-none"
$uvMetadataUrl = (
    "https://raw.githubusercontent.com/astral-sh/uv/" +
    "3c979abda4530fe9bf3d92e9bcf5c5575e3b3126/" +
    "crates/uv-python/download-metadata.json"
)
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$runtimeTmpRoot = [IO.Path]::GetFullPath(
    (Join-Path $repositoryRoot "runtime\tmp")
).TrimEnd(
    [IO.Path]::DirectorySeparatorChar,
    [IO.Path]::AltDirectorySeparatorChar
)
$validationRoot = if ([IO.Path]::IsPathRooted($ValidationEnvironment)) {
    [IO.Path]::GetFullPath($ValidationEnvironment)
}
else {
    [IO.Path]::GetFullPath((Join-Path $repositoryRoot $ValidationEnvironment))
}
$runtimeTmpPrefix = $runtimeTmpRoot + [IO.Path]::DirectorySeparatorChar
if (-not $validationRoot.StartsWith(
    $runtimeTmpPrefix,
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw "PYTHON_VALIDATION_ENVIRONMENT_OUTSIDE_RUNTIME_TMP: $validationRoot"
}

$uvCommand = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue
if ($null -eq $uvCommand) {
    throw "UV_COMMAND_NOT_FOUND"
}

$managedInstallRoot = Join-Path $runtimeTmpRoot "uv-python-downloads-py3147"
$managedPython = Join-Path (
    Join-Path $managedInstallRoot $managedRuntimeName
) "python.exe"
$validationPython = Join-Path $validationRoot "Scripts\python.exe"
$previousProjectEnvironment = $env:UV_PROJECT_ENVIRONMENT

Push-Location $repositoryRoot
try {
    & $uvCommand.Source python install $canonicalPython `
        --python-downloads-json-url $uvMetadataUrl `
        --install-dir $managedInstallRoot `
        --no-bin `
        --no-registry `
        --managed-python `
        --system-certs
    if ($LASTEXITCODE -ne 0) {
        throw "PYTHON_3_14_7_MANAGED_INSTALL_FAILED"
    }
    if (-not (Test-Path -LiteralPath $managedPython -PathType Leaf)) {
        throw "PYTHON_3_14_7_MANAGED_RUNTIME_MISSING: $managedPython"
    }

    if (-not (Test-Path -LiteralPath $validationPython -PathType Leaf)) {
        & $uvCommand.Source venv `
            --python $managedPython `
            $validationRoot
        if ($LASTEXITCODE -ne 0) {
            throw "PYTHON_3_14_7_VALIDATION_VENV_FAILED"
        }
    }

    $env:UV_PROJECT_ENVIRONMENT = $validationRoot
    & $uvCommand.Source sync `
        --frozen `
        --all-extras `
        --no-install-project `
        --python $managedPython `
        --system-certs `
        --no-progress
    if ($LASTEXITCODE -ne 0) {
        throw "PYTHON_3_14_7_UV_SYNC_FAILED"
    }

    & $uvCommand.Source pip check --python $validationPython
    if ($LASTEXITCODE -ne 0) {
        throw "PYTHON_3_14_7_DEPENDENCY_CHECK_FAILED"
    }

    $probe = @'
import json
import platform
import sys
import sysconfig

jit = getattr(sys, "_jit", None)
print(json.dumps({
    "implementation": platform.python_implementation(),
    "version": platform.python_version(),
    "machine": platform.machine().casefold(),
    "gil_enabled": sys._is_gil_enabled(),
    "py_gil_disabled": sysconfig.get_config_var("Py_GIL_DISABLED"),
    "soabi": sysconfig.get_config_var("SOABI"),
    "jit_available": jit is not None,
    "jit_enabled": bool(jit is not None and jit.is_enabled()),
}, sort_keys=True))
'@
    $runtime = (& $validationPython -B -c $probe) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) {
        throw "PYTHON_3_14_7_RUNTIME_PROBE_FAILED"
    }
    if (
        $runtime.implementation -ne "CPython" -or
        $runtime.version -ne $canonicalPython -or
        $runtime.machine -notin @("amd64", "x86_64") -or
        $runtime.gil_enabled -ne $true -or
        [int]$runtime.py_gil_disabled -ne 0 -or
        $runtime.soabi -ne "cp314-win_amd64" -or
        $runtime.jit_available -ne $true -or
        $runtime.jit_enabled -ne $false
    ) {
        throw (
            "PYTHON_3_14_7_RUNTIME_POLICY_MISMATCH: " +
            ($runtime | ConvertTo-Json -Compress)
        )
    }
}
finally {
    if ($null -eq $previousProjectEnvironment) {
        Remove-Item Env:\UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue
    }
    else {
        $env:UV_PROJECT_ENVIRONMENT = $previousProjectEnvironment
    }
    Pop-Location
}

Write-Output "PYTHON_3_14_7_VALIDATION_READY"
Write-Output "PYTHON_VERSION=$($runtime.version)"
Write-Output "PYTHON_SOABI=$($runtime.soabi)"
Write-Output "STANDARD_GIL=$($runtime.gil_enabled)"
Write-Output "EXPERIMENTAL_JIT=$($runtime.jit_enabled)"
Write-Output "VALIDATION_ENVIRONMENT=$validationRoot"
Write-Output "PROJECT_INSTALLATION=SOURCE_TREE_NOT_INSTALLED"
Write-Output "RESEARCH_ONLY"
Write-Output "LIVE_ORDER_BLOCKED"
