# Resolve the temporary-directory contract through the owning Python package.
# Dot-source before native processes or Add-Type; never alter machine/user TEMP.
& {
    $runtimeRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
    $runtimePython = Join-Path $runtimeRoot ".venv\Scripts\python.exe"
    $runtimeSource = Join-Path $runtimeRoot "src"
    $runtimeCode = 'import sys; sys.path.insert(0, sys.argv[1]); import ai4binance; import tempfile; print(tempfile.gettempdir())'
    $runtimeOutput = @(& $runtimePython -I -B -c $runtimeCode $runtimeSource)
    if ($LASTEXITCODE -ne 0 -or $runtimeOutput.Count -ne 1) {
        throw "Repository temporary environment initialization failed."
    }
    $runtimeTemporary = [string]$runtimeOutput[0]
    if (-not (Test-Path -LiteralPath $runtimeTemporary -PathType Container)) {
        throw "Repository temporary directory is unavailable."
    }
    $env:TEMP = $runtimeTemporary
    $env:TMP = $runtimeTemporary
    $env:TMPDIR = $runtimeTemporary
}
