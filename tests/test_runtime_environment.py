"""Regression contract for repository-owned process temporary files."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import ai4binance


class RuntimeEnvironmentTests(unittest.TestCase):
    def test_cached_external_temp_is_replaced_and_children_inherit(self) -> None:
        root = Path(ai4binance.__file__).resolve().parents[2]
        code = """
import json, os, pathlib, subprocess, sys, tempfile
tempfile.tempdir = sys.argv[1]
import ai4binance
target = pathlib.Path(tempfile.gettempdir())
with tempfile.NamedTemporaryFile() as stream:
    assert pathlib.Path(stream.name).parent == target
child = subprocess.check_output(
    [sys.executable, '-B', '-c',
     'import tempfile; print(tempfile.gettempdir())'], text=True).strip()
values = [os.environ[k] for k in ('TEMP', 'TMP', 'TMPDIR')]
print(json.dumps([str(target), child, values]))
"""
        environment = dict(
            os.environ,
            PYTHONPATH=str(root / "src"),
            TEMP=str(root),
            TMP=str(root),
            TMPDIR=str(root),
        )
        result = subprocess.run(  # noqa: S603 - fixed local interpreter and code
            [sys.executable, "-B", "-c", code, str(root)],
            cwd=root.parent,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        target = str(root / "runtime" / "tmp" / "process")
        assert json.loads(result.stdout) == [target, target, [target] * 3]

    def test_invalid_contract_and_unavailable_target_fail_without_fallback(
        self,
    ) -> None:
        source = Path(ai4binance.__file__)
        for destination in (
            "../outside",
            "runtime/tmp/../../outside",
            "runtime/tmp/process",
        ):
            with (
                self.subTest(destination=destination),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                package = root / "src" / "ai4binance"
                package.mkdir(parents=True)
                shutil.copyfile(source, package / "__init__.py")
                (root / "pyproject.toml").write_text(
                    '[tool.ai4binance.runtime]\ntemporary_directory = "'
                    + destination
                    + '"\n',
                    encoding="utf-8",
                )
                if destination == "runtime/tmp/process":
                    target = root / destination
                    target.parent.mkdir(parents=True)
                    target.write_text("Blocked by a file.", encoding="utf-8")
                code = """
import os, sys, tempfile
before = {key: os.environ.get(key) for key in ('TEMP', 'TMP', 'TMPDIR')}
cached = tempfile.gettempdir()
try:
    import ai4binance
except (OSError, ValueError):
    assert before == {key: os.environ.get(key) for key in before}
    assert cached == tempfile.gettempdir()
else:
    raise AssertionError('Invalid temporary contract was accepted')
"""
                subprocess.run(  # noqa: S603 - fixed local interpreter and code
                    [sys.executable, "-B", "-c", code],
                    cwd=root,
                    env=dict(os.environ, PYTHONPATH=str(root / "src")),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,
                )
                assert not (root / "outside").exists()

    @unittest.skipUnless(os.name == "nt", "PowerShell launcher requires Windows")
    def test_powershell_bootstrap_uses_owning_repository(self) -> None:
        root = Path(ai4binance.__file__).resolve().parents[2]
        command = (
            ". '" + str(root / "scripts" / "initialize_runtime_environment.ps1") + "'; "
            "[IO.Path]::GetTempPath(); $env:TEMP; $env:TMP; $env:TMPDIR"
        )
        executable = shutil.which("powershell.exe")
        assert executable is not None
        result = subprocess.run(  # noqa: S603 - fixed repository bootstrap script
            [executable, "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=root.parent,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        paths = [
            Path(line.strip()) for line in result.stdout.splitlines() if line.strip()
        ]
        assert paths == [root / "runtime" / "tmp" / "process"] * 4

    def test_pytest_rejects_external_basetemp(self) -> None:
        root = Path(ai4binance.__file__).resolve().parents[2]
        external_base = root / "runtime" / "tmp" / "pytest-outside-process"
        command = [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "tests/test_runtime_environment.py::RuntimeEnvironmentTests::test_cached_external_temp_is_replaced_and_children_inherit",
            "--basetemp",
            str(external_base),
            "-q",
            "-o",
            "addopts=",
        ]
        result = subprocess.run(  # noqa: S603 - fixed local interpreter and test
            command,
            cwd=root,
            env=dict(os.environ, PYTHONPATH=str(root / "src")),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert "PYTEST_BASETEMP_OUTSIDE_RUNTIME_TMP_PROCESS" in (
            result.stdout + result.stderr
        )
        assert not external_base.exists()
