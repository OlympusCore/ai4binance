[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$WorktreePaths,
    [switch]$InstallDependencies
)

$ErrorActionPreference = "Stop"
if (-not $InstallDependencies) {
    throw "Dependency installation requires the explicit -InstallDependencies switch."
}

foreach ($worktreePath in $WorktreePaths) {
    Push-Location -LiteralPath $worktreePath
    try {
        & {
            $ErrorActionPreference = "Stop"
            $root = git rev-parse --show-toplevel
            if ($LASTEXITCODE -ne 0) {
                throw "Repository root unavailable."
            }
            $root = (Resolve-Path -LiteralPath $root).Path
            if ($root -ne (Get-Location).Path) {
                throw "Run setup from the specified worktree root."
            }

            $listing = git worktree list --porcelain
            if ($LASTEXITCODE -ne 0) {
                throw "Unable to discover the main worktree."
            }
            $mainEntry = $listing |
                Where-Object { $_.StartsWith("worktree ") } |
                Select-Object -First 1
            if (-not $mainEntry) {
                throw "Main worktree unavailable."
            }

            $seedPython = Join-Path $mainEntry.Substring(9) ".venv\Scripts\python.exe"
            $environmentPath = Join-Path $root "runtime\tmp\codex-worktree-venv"
            $linkPath = Join-Path $root ".venv"
            $hookPath = Join-Path $root "scripts\codex_governance_hook.py"
            foreach ($requiredFile in @($seedPython, $hookPath, (Join-Path $root "uv.lock"))) {
                if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
                    throw "Required file unavailable: $requiredFile"
                }
            }
            if ((Get-Content -Raw -LiteralPath (Join-Path $root ".python-version")).Trim() -ne "3.14.7") {
                throw "Worktree Python version differs from the reviewed 3.14.7 baseline."
            }

            $existingLink = Get-Item -LiteralPath $linkPath -Force -ErrorAction SilentlyContinue
            if ($null -ne $existingLink) {
                if ($existingLink.LinkType -ne "Junction") {
                    throw "Existing .venv will not be modified."
                }
                $existingTarget = [IO.Path]::GetFullPath([string](@($existingLink.Target)[0]))
                if ($existingTarget -ne $environmentPath) {
                    throw "Existing .venv points to a different environment."
                }
            }

            $uvCommand = Get-Command uv -CommandType Application -ErrorAction Stop |
                Select-Object -First 1
            $variableNames = @(
                "TEMP", "TMP", "TMPDIR", "PYTHONPATH",
                "UV_PROJECT_ENVIRONMENT", "UV_CACHE_DIR"
            )
            $savedVariables = @{}
            foreach ($name in $variableNames) {
                $savedVariables[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
            }
            try {
                $probe = @'
import sys
import sysconfig
assert sys.version_info[:3] == (3, 14, 7)
assert sys._is_gil_enabled()
assert sysconfig.get_config_var("SOABI") == "cp314-win_amd64"
assert not sys._jit.is_enabled()
sys.path.insert(0, sys.argv[1])
import ai4binance
import tempfile
print(tempfile.gettempdir())
'@
                $temporaryOutput = @(
                    $probe | & $seedPython -I -B - (Join-Path $root "src")
                )
                if ($LASTEXITCODE -ne 0 -or $temporaryOutput.Count -ne 1) {
                    throw "Canonical runtime or temporary-directory verification failed."
                }
                $temporaryDirectory = [IO.Path]::GetFullPath([string]$temporaryOutput[0])
                $runtimePrefix = (Join-Path $root "runtime") + [IO.Path]::DirectorySeparatorChar
                if (-not $temporaryDirectory.StartsWith(
                    $runtimePrefix, [StringComparison]::OrdinalIgnoreCase
                )) {
                    throw "Temporary directory is outside the worktree runtime."
                }
                if (-not (Test-Path -LiteralPath $temporaryDirectory -PathType Container)) {
                    throw "Repository temporary directory is unavailable."
                }

                $env:TEMP = $temporaryDirectory
                $env:TMP = $temporaryDirectory
                $env:TMPDIR = $temporaryDirectory
                $env:UV_CACHE_DIR = Join-Path $root "runtime\tmp\uv-cache"
                $env:UV_PROJECT_ENVIRONMENT = $environmentPath

                & $uvCommand.Source sync --frozen --all-extras --no-install-project `
                    --python $seedPython --no-python-downloads --system-certs --no-progress
                if ($LASTEXITCODE -ne 0) {
                    throw "Worktree dependency synchronization failed."
                }

                $environmentPython = Join-Path $environmentPath "Scripts\python.exe"
                & $uvCommand.Source pip check --python $environmentPython
                if ($LASTEXITCODE -ne 0) {
                    throw "Worktree dependency verification failed."
                }
                if ($null -eq $existingLink) {
                    New-Item -ItemType Junction -Path $linkPath -Target $environmentPath |
                        Out-Null
                }

                $env:PYTHONPATH = Join-Path $root "src"
                $startupOutput = @(
                    & (Join-Path $linkPath "Scripts\python.exe") -B $hookPath --startup
                )
                if ($LASTEXITCODE -ne 0) {
                    $startupOutput | Write-Output
                    throw "Worktree governance startup verification failed."
                }
                $startupOutput | Set-Content -Encoding utf8 -LiteralPath (
                    Join-Path $temporaryDirectory "codex-worktree-startup.txt"
                )
                Write-Output "CODEX_WORKTREE_STARTUP_READY: $root"
            }
            finally {
                foreach ($name in $variableNames) {
                    [Environment]::SetEnvironmentVariable(
                        $name, $savedVariables[$name], "Process"
                    )
                }
            }
        }
    }
    finally {
        Pop-Location
    }
}
