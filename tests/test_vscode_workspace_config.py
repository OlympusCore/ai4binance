"""VS Code workspace configuration guardrails."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
VSCODE = ROOT / ".vscode"


def _load_json(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((VSCODE / name).read_text(encoding="utf-8")))


def test_vscode_json_files_parse() -> None:
    assert _load_json("settings.json")
    assert _load_json("tasks.json")
    assert _load_json("launch.json")
    assert _load_json("extensions.json")


def test_terminal_environment_preserves_safe_local_defaults() -> None:
    settings = _load_json("settings.json")
    env = settings["terminal.integrated.env.windows"]

    assert env["AI4BINANCE_ADVISORY_LLM_MODE"] == "RESEARCH_ONLY"
    assert env["AI4BINANCE_ALLOW_AUTO_LIVE_ORDERS"] == "false"
    assert env["PYTHONPATH"] == "${workspaceFolder}/src"
    assert "TEMP" not in env
    assert "TMP" not in env


def test_interactive_pytest_uses_isolated_os_temp_without_coverage() -> None:
    settings = _load_json("settings.json")
    pytest_args = settings["python.testing.pytestArgs"]

    assert "--basetemp" not in pytest_args
    assert "--no-cov" in pytest_args

    tasks = _load_json("tasks.json")["tasks"]
    pytest_task = next(task for task in tasks if task["label"] == "Test: pytest")
    assert "--basetemp" not in pytest_task["args"]
    assert "--no-cov" in pytest_task["args"]
    assert "TEMP" not in pytest_task["options"]["env"]
    assert "TMP" not in pytest_task["options"]["env"]


def test_workspace_exclusions_preserve_source_packages() -> None:
    settings = _load_json("settings.json")
    source_package_globs = {"**/data", "**/models", "**/tools"}

    for key in ("files.exclude", "files.watcherExclude", "search.exclude"):
        assert source_package_globs.isdisjoint(settings[key])
    assert source_package_globs.isdisjoint(settings["python.analysis.exclude"])

    assert settings["files.exclude"]["runtime"] is True
    assert settings["files.watcherExclude"]["runtime/**"] is True
    assert settings["search.exclude"]["runtime"] is True
    assert settings["terminal.integrated.gpuAcceleration"] == "on"


def test_debug_artifact_paths_and_extensions_match_governed_workspace() -> None:
    launch = _load_json("launch.json")
    mcp_config = next(
        item
        for item in launch["configurations"]
        if item["name"] == "AI4BINANCE: MCP evidence server"
    )
    assert mcp_config["args"] == [
        "--artifact-root",
        "${workspaceFolder}/runtime/artifacts",
    ]
    for configuration in launch["configurations"]:
        assert "TEMP" not in configuration["env"]
        assert "TMP" not in configuration["env"]
        assert configuration["env"]["AI4BINANCE_ALLOW_AUTO_LIVE_ORDERS"] == "false"

    extensions = _load_json("extensions.json")
    assert "redhat.vscode-yaml" in extensions["recommendations"]
    assert "ms-toolsai.jupyter" in extensions["unwantedRecommendations"]


def test_polyglot_extensions_cover_governed_language_owners() -> None:
    recommendations = set(_load_json("extensions.json")["recommendations"])

    assert {
        "dbaeumer.vscode-eslint",
        "golang.go",
        "julialang.language-julia",
        "ms-vscode.cpptools",
        "ms-vscode.powershell",
        "mtxr.sqltools",
        "mtxr.sqltools-driver-sqlite",
        "redhat.vscode-yaml",
        "rust-lang.rust-analyzer",
        "stylelint.vscode-stylelint",
        "tamasfe.even-better-toml",
        "timonwong.shellcheck",
        "vscjava.vscode-java-pack",
    }.issubset(recommendations)


def test_polyglot_language_settings_are_explicit_and_side_effect_bounded() -> None:
    settings = _load_json("settings.json")

    assert settings["files.associations"] == {
        "*.cu": "cuda-cpp",
        "*.cuh": "cuda-cpp",
        "*.jl": "julia",
        "*.schema.json": "json",
        "*.sql": "sql",
    }
    assert settings["[rust]"]["editor.defaultFormatter"] == ("rust-lang.rust-analyzer")
    assert settings["rust-analyzer.check.command"] == "clippy"
    assert settings["[cuda-cpp]"]["editor.defaultFormatter"] == ("ms-vscode.cpptools")
    assert settings["[go]"]["editor.defaultFormatter"] == "golang.go"
    assert settings["go.toolsManagement.autoUpdate"] is False
    assert settings["[julia]"]["editor.defaultFormatter"] == (
        "julialang.language-julia"
    )
    assert settings["[java]"]["editor.defaultFormatter"] == "redhat.java"
    assert settings["java.configuration.updateBuildConfiguration"] == "interactive"


def test_interface_operations_and_contract_formats_have_vscode_hygiene() -> None:
    settings = _load_json("settings.json")

    assert set(settings["eslint.validate"]) == {
        "javascript",
        "javascriptreact",
        "typescript",
        "typescriptreact",
    }
    assert settings["stylelint.validate"] == ["css"]
    assert settings["shellcheck.run"] == "onSave"
    assert settings["[yaml]"]["editor.defaultFormatter"] == "redhat.vscode-yaml"
    assert settings["[toml]"]["editor.defaultFormatter"] == ("tamasfe.even-better-toml")
    assert settings["[json]"]["editor.defaultFormatter"] == (
        "vscode.json-language-features"
    )
    assert settings["json.validate.enable"] is True
    assert settings["yaml.validate"] is True
    assert settings["yaml.schemas"] == {
        "./schemas/governance/technology_language_ownership.schema.json": (
            "config/governance/technology_language_ownership.yaml"
        )
    }
