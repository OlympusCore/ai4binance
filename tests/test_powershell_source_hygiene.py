"""PowerShell parser and bounded static-analysis gate for tracked scripts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]

VALIDATOR = r"""
$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath($env:AI4B_REPOSITORY_ROOT)
$tracked = @(git -C $root ls-files -- '*.ps1')
$failures = [System.Collections.Generic.List[object]]::new()
foreach ($relative in $tracked) {
    $path = Join-Path $root $relative
    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $path,
        [ref]$tokens,
        [ref]$parseErrors
    )
    foreach ($parseError in $parseErrors) {
        $failures.Add([pscustomobject]@{
            path = $relative
            code = 'POWERSHELL_PARSE_ERROR'
            detail = $parseError.Message
        })
    }
    $commands = $ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.CommandAst]
    }, $true)
    foreach ($command in $commands) {
        $name = $command.GetCommandName()
        if ($name -in @('Invoke-Expression', 'iex', 'Set-ExecutionPolicy')) {
            $failures.Add([pscustomobject]@{
                path = $relative
                code = 'POWERSHELL_DYNAMIC_OR_POLICY_EXECUTION'
                detail = $name
            })
        }
        $isDynamicType = (
            $name -eq 'Add-Type' -and
            $command.Extent.Text -notmatch '(?i)-AssemblyName\b'
        )
        if ($isDynamicType) {
            $failures.Add([pscustomobject]@{
                path = $relative
                code = 'POWERSHELL_DYNAMIC_TYPE_DEFINITION'
                detail = 'Add-Type is restricted to named framework assemblies.'
            })
        }
    }
}
[pscustomobject]@{
    tracked_script_count = $tracked.Count
    failures = @($failures)
} | ConvertTo-Json -Depth 5 -Compress
if ($failures.Count -gt 0) { exit 1 }
"""


def test_tracked_powershell_sources_pass_parser_and_static_guards() -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    assert shell is not None, "PowerShell is required for the Windows source gate"

    completed = subprocess.run(  # noqa: S603
        (
            shell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            VALIDATOR,
        ),
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
        env={**os.environ, "AI4B_REPOSITORY_ROOT": str(ROOT)},
    )

    assert completed.stdout.strip(), completed.stderr
    payload = json.loads(completed.stdout)
    assert completed.returncode == 0, payload["failures"]
    assert payload["tracked_script_count"] > 0
    assert payload["failures"] == []
