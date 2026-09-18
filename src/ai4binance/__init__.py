"""AI4Binance validation-first decision platform."""

import os
import tempfile
import tomllib
from pathlib import Path


def configure_runtime_environment() -> Path:
    """Bind process and child temporary files to the owning checkout, fail closed.

    Apply before application imports, including when tempfile cached an inherited
    Windows or another project's temporary directory. No user/machine settings
    are modified. Explicit caller-supplied file destinations remain explicit.
    """
    root = Path(__file__).resolve().parents[2]
    with (root / "pyproject.toml").open("rb") as stream:
        contract = tomllib.load(stream)["tool"]["ai4binance"]["runtime"]
    relative = Path(contract["temporary_directory"])
    if relative.is_absolute() or relative.parts[:2] != ("runtime", "tmp"):
        raise ValueError("Temporary directory must be inside repository runtime/tmp")
    if ".." in relative.parts:
        raise ValueError("Temporary directory must not contain parent traversal")
    target = (root / relative).resolve()
    if not target.is_relative_to(root / "runtime" / "tmp"):
        raise ValueError("Temporary directory resolves outside repository runtime/tmp")
    target.mkdir(parents=True, exist_ok=True)
    # Explicit dir prevents tempfile from silently trying OS fallback locations.
    with tempfile.TemporaryFile(dir=target):
        pass
    for name in ("TEMP", "TMP", "TMPDIR"):
        os.environ[name] = str(target)
    tempfile.tempdir = str(target)
    return target


configure_runtime_environment()

__version__ = "0.1.0"
