from __future__ import annotations

import json
import platform
import shutil
import site
import subprocess
import sys
import sysconfig
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast

import pytest
import yaml

from ai4binance.schema_validation import OfflineSchemaRegistry, SchemaValidationError

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_REGISTRY_PATH = ROOT / "docs/registries/registry_python_runtime.yaml"
RUNTIME_SCHEMA_ID = "urn:ai4binance:schema:registries:python-runtime-registry:1.0.0"
SETUP_UV_ACTION = "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0"


class _JitRuntime(Protocol):
    def is_enabled(self) -> bool: ...


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise AssertionError(f"{field} must be a mapping")
    return cast(Mapping[str, object], value)


def _required_string(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{field} must be a non-empty string")
    return value


def _runtime_registry() -> Mapping[str, object]:
    payload: object = yaml.safe_load(RUNTIME_REGISTRY_PATH.read_text(encoding="utf-8"))
    return _mapping(payload, field="python runtime registry")


def _runtime_contract() -> Mapping[str, object]:
    return _mapping(_runtime_registry().get("runtime"), field="runtime")


def test_python_runtime_registry_is_schema_valid_and_authoritative() -> None:
    payload = _runtime_registry()
    schema_registry = OfflineSchemaRegistry.from_directory(ROOT / "schemas")

    schema_registry.validate(RUNTIME_SCHEMA_ID, payload)

    runtime = _runtime_contract()
    version = _required_string(runtime, "version")
    assert version.rsplit(".", maxsplit=1)[0] == runtime["major_minor"]
    assert payload["source_of_truth"] is True
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_python_runtime_registry_rejects_execution_authority() -> None:
    payload = dict(_runtime_registry())
    payload["execution_allowed"] = True
    schema_registry = OfflineSchemaRegistry.from_directory(ROOT / "schemas")

    with pytest.raises(SchemaValidationError):
        schema_registry.validate(RUNTIME_SCHEMA_ID, payload)


def test_canonical_python_policy_is_consistent() -> None:
    runtime = _runtime_contract()
    canonical_python = _required_string(runtime, "version")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == (
        canonical_python
    )
    major_minor = _required_string(runtime, "major_minor")
    major, minor = major_minor.split(".", maxsplit=1)
    next_minor = int(minor) + 1
    assert project["project"]["requires-python"] == (
        f">={major_minor},<{major}.{next_minor}"
    )
    assert project["tool"]["ruff"]["target-version"] == "py314"
    assert project["tool"]["mypy"]["python_version"] == major_minor


def test_canonical_runtime_is_standard_gil_without_jit() -> None:
    runtime = _runtime_contract()

    assert platform.python_implementation() == runtime["implementation"]
    assert platform.python_version() == runtime["version"]
    assert platform.machine().casefold() in {"amd64", "x86_64"}
    assert runtime["architecture"] == "x86_64"
    assert sys._is_gil_enabled() is runtime["gil_enabled"]
    assert sysconfig.get_config_var("Py_GIL_DISABLED") == int(
        cast(bool, runtime["free_threaded"])
    )
    assert sysconfig.get_config_var("SOABI") == runtime["abi"]
    jit = cast(_JitRuntime | None, getattr(sys, "_jit", None))
    assert jit is not None
    assert jit.is_enabled() is runtime["jit_enabled"]


def test_canonical_venv_and_vscode_interpreter_are_consistent() -> None:
    runtime = _runtime_contract()
    settings = json.loads((ROOT / ".vscode/settings.json").read_text(encoding="utf-8"))
    terminal_environment = settings["terminal.integrated.env.windows"]
    venv_root = (ROOT / cast(str, runtime["project_environment"])).resolve()
    pyvenv_config = (venv_root / "pyvenv.cfg").read_text(encoding="utf-8")

    assert Path(sys.prefix).resolve() == venv_root
    assert Path(sys.base_prefix).resolve() != Path(sys.prefix).resolve()
    assert site.ENABLE_USER_SITE is False
    assert all(
        Path(path).resolve().is_relative_to(venv_root)
        for path in site.getsitepackages()
    )
    assert "include-system-site-packages = false" in pyvenv_config
    assert settings["python.defaultInterpreterPath"] == (
        "${workspaceFolder}/" + cast(str, runtime["executable"])
    )
    assert terminal_environment["VIRTUAL_ENV"] == "${workspaceFolder}\\.venv"
    assert terminal_environment["PATH"].startswith(
        "${workspaceFolder}\\.venv\\Scripts;"
    )


def test_ci_uses_uv_with_the_canonical_python() -> None:
    canonical_python = _required_string(_runtime_contract(), "version")
    workflows = (
        ROOT / ".github/workflows/quality_profiles.yml",
        ROOT / ".github/workflows/security_tooling.yml",
        ROOT / ".github/workflows/nightly_quality_triage.yml",
    )

    for workflow in workflows:
        content = workflow.read_text(encoding="utf-8")
        assert SETUP_UV_ACTION in content
        assert 'version: "0.12.10"' in content
        assert f"uv python install {canonical_python}" in content
        assert "actions/setup-python" not in content
        assert "pip install" not in content


def test_activation_requires_the_canonical_patch_runtime() -> None:
    canonical_python = _required_string(_runtime_contract(), "version")
    script = (ROOT / "scripts/activate_dev.ps1").read_text(encoding="utf-8")

    assert f'$expectedVersion = "{canonical_python}"' in script


def test_validation_bootstrap_is_repo_local_and_fail_closed() -> None:
    canonical_python = _required_string(_runtime_contract(), "version")
    script = (ROOT / "scripts/bootstrap_python314_validation.ps1").read_text(
        encoding="utf-8"
    )

    assert f'$canonicalPython = "{canonical_python}"' in script
    assert "3c979abda4530fe9bf3d92e9bcf5c5575e3b3126" in script
    assert "crates/uv-python/download-metadata.json" in script
    assert 'Join-Path $repositoryRoot "runtime\\tmp"' in script
    assert "PYTHON_VALIDATION_ENVIRONMENT_OUTSIDE_RUNTIME_TMP" in script
    assert "--no-bin" in script
    assert "--no-registry" in script
    assert "--managed-python" in script
    assert "--no-install-project" in script
    assert "PROJECT_INSTALLATION=SOURCE_TREE_NOT_INSTALLED" in script
    assert "$env:UV_PROJECT_ENVIRONMENT = $validationRoot" in script
    assert '"gil_enabled": sys._is_gil_enabled()' in script
    assert '"jit_enabled": bool(jit is not None and jit.is_enabled())' in script
    assert "LIVE_ORDER_BLOCKED" in script
    assert "--clear" not in script


def test_validation_bootstrap_rejects_the_canonical_venv_as_a_target() -> None:
    powershell = shutil.which("pwsh")
    assert powershell is not None
    result = subprocess.run(  # noqa: S603
        [
            powershell,
            "-NoProfile",
            "-File",
            str(ROOT / "scripts/bootstrap_python314_validation.ps1"),
            "-ValidationEnvironment",
            ".venv",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "PYTHON_VALIDATION_ENVIRONMENT_OUTSIDE_RUNTIME_TMP" in (
        result.stdout + result.stderr
    )
