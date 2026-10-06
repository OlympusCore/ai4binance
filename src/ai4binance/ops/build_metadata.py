"""Keep setuptools' reproducible package metadata outside authored source."""

from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Local type boundary for the installed, untyped setuptools command.
    class _EggInfoBase:
        egg_base: str | None

        def finalize_options(self) -> None:
            return None

else:
    _EggInfoBase = import_module("setuptools.command.egg_info").egg_info


class RuntimeEggInfo(_EggInfoBase):
    """Use the repository runtime for default metadata; honor explicit outputs."""

    def finalize_options(self) -> None:
        if self.egg_base is None:
            root = Path(__file__).resolve().parents[3]
            target = root / "runtime/cache/build/metadata"
            target.mkdir(parents=True, exist_ok=True)
            self.egg_base = str(target)
        super().finalize_options()
