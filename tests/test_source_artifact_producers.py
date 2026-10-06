"""Exercise source-artifact producers only in disposable runtime fixtures."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_unflagged_discovery_bootstrap_protects_application_and_child(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    package = source / "ai4binance"
    package.mkdir(parents=True)
    shutil.copyfile(ROOT / "src/ai4binance/__init__.py", package / "__init__.py")
    (source / "artifact_probe.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ai4binance.runtime]\ntemporary_directory = "runtime/tmp/process"\n',
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    shutil.copyfile(ROOT / "tests/conftest.py", tests / "conftest.py")
    (tests / "test_discovery_probe.py").write_text(
        "import os, subprocess, sys\n"
        "from pathlib import Path\n"
        "import ai4binance, artifact_probe\n"
        "assert sys.dont_write_bytecode\n"
        "assert os.environ['PYTHONDONTWRITEBYTECODE'] == '1'\n"
        "expected = Path(__file__).parents[1] / 'src/ai4binance/__init__.py'\n"
        "assert Path(ai4binance.__file__).resolve() == expected.resolve()\n"
        "child = subprocess.run([sys.executable, '-c', "
        '"import ai4binance, artifact_probe, os, sys; '
        "assert sys.dont_write_bytecode; "
        "assert os.environ['PYTHONDONTWRITEBYTECODE'] == '1'; "
        'assert artifact_probe.VALUE == 1; print(ai4binance.__file__)"], '
        "check=True, capture_output=True, text=True, timeout=30)\n"
        "assert Path(child.stdout.strip()).resolve() == expected.resolve()\n"
        "def test_probe():\n    assert artifact_probe.VALUE == 1\n",
        encoding="utf-8",
    )
    environment = dict(os.environ, PYTHONPATH=str(source))
    for name in (
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONPYCACHEPREFIX",
        "PYTEST_ADDOPTS",
        "HYPOTHESIS_STORAGE_DIRECTORY",
    ):
        environment.pop(name, None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, sys; assert not sys.dont_write_bytecode; "
            "assert 'PYTHONDONTWRITEBYTECODE' not in os.environ; "
            "import pytest; raise SystemExit(pytest.main(["
            "'--collect-only', 'tests', '--no-cov', '--rootdir=.', "
            "'-o', 'addopts=-q --strict-markers -p no:cacheprovider']))",
        ],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 test collected" in result.stdout
    assert not list(source.rglob("*.pyc"))
    assert not list(source.rglob("__pycache__"))


def test_editor_terminal_children_do_not_write_source_bytecode(tmp_path: Path) -> None:
    settings = json.loads((ROOT / ".vscode/settings.json").read_text(encoding="utf-8"))
    environment = dict(os.environ, PYTHONPATH=str(tmp_path))
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    environment.pop("PYTHONPYCACHEPREFIX", None)
    terminal = settings["terminal.integrated.env.windows"]
    if "PYTHONDONTWRITEBYTECODE" in terminal:
        environment["PYTHONDONTWRITEBYTECODE"] = terminal["PYTHONDONTWRITEBYTECODE"]
    (tmp_path / "artifact_probe.py").write_text("VALUE = 1\n", encoding="utf-8")
    code = (
        "import artifact_probe, subprocess, sys; "
        "subprocess.run([sys.executable, '-c', 'import artifact_probe'], check=True)"
    )
    subprocess.run(  # noqa: S603 - fixed interpreter and isolated test-only module
        [sys.executable, "-c", code],
        env=environment,
        cwd=tmp_path,
        check=True,
        timeout=30,
    )
    assert not list(tmp_path.rglob("*.pyc"))


@pytest.mark.parametrize(
    "operation", ["requirements", "metadata", "editable", "wheel", "sdist"]
)
def test_setuptools_outputs_preserve_source_boundary(
    tmp_path: Path, operation: str
) -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    source = tmp_path / "src"
    package = source / "artifact_fixture"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    lines = [
        "[build-system]",
        'requires = ["setuptools>=75", "wheel"]',
        'build-backend = "setuptools.build_meta"',
        "[project]",
        'name = "artifact-fixture"',
        'version = "0.1.0"',
        "[project.scripts]",
        'artifact-fixture = "artifact_fixture:main"',
        "[tool.setuptools.packages.find]",
        'where = ["src"]',
    ]
    commands = config["tool"]["setuptools"].get("cmdclass", {})
    if "egg_info" in commands:
        lines.extend(
            ["[tool.setuptools.cmdclass]", f'egg_info = "{commands["egg_info"]}"']
        )
        module = source / "ai4binance/ops/build_metadata.py"
        module.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "src/ai4binance/ops/build_metadata.py", module)
    (tmp_path / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    output = tmp_path / "runtime/build/output"
    output.mkdir(parents=True)
    calls = {
        "requirements": "b.get_requires_for_build_editable()",
        "metadata": "b.prepare_metadata_for_build_editable('runtime/build/output')",
        "editable": "b.build_editable('runtime/build/output')",
        "wheel": "b.build_wheel('runtime/build/output')",
        "sdist": "b.build_sdist('runtime/build/output')",
    }
    result = subprocess.run(  # noqa: S603 - installed backend and test-only project
        [
            sys.executable,
            "-B",
            "-c",
            "import setuptools.build_meta as b; " + calls[operation],
        ],
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not list(source.rglob("*.egg-info")), result.stdout
    assert not list(source.rglob("*.pyc"))
    if operation in {"requirements", "wheel", "sdist"}:
        metadata = tmp_path / "runtime/cache/build/metadata/artifact_fixture.egg-info"
        assert (metadata / "PKG-INFO").is_file()
    elif operation == "metadata":
        assert (output / "artifact_fixture.egg-info/PKG-INFO").is_file()
    if operation != "requirements":
        assert list(output.iterdir()), result.stdout
    if operation in {"editable", "wheel"}:
        with zipfile.ZipFile(next(output.glob("*.whl"))) as archive:
            entries = archive.read("artifact_fixture-0.1.0.dist-info/entry_points.txt")
            assert b"artifact-fixture = artifact_fixture:main" in entries
