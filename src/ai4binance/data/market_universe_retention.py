"""Bounded retention for the canonical research market universe."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from ai4binance.integrations.binance import BinanceEligibleMarketSnapshot

_SYMBOL = re.compile(r"^[A-Z0-9]{4,24}$")


@dataclass(frozen=True, slots=True)
class MarketUniverseRetention:
    """Remove only symbol-scoped generated data outside the selected universe."""

    archive_root: Path
    source_cache_root: Path
    opportunity_monitor_root: Path
    futures_replay_root: Path | None = None
    futures_artifact_roots: tuple[Path, ...] = ()

    def prune(self, universe: BinanceEligibleMarketSnapshot) -> dict[str, object]:
        if universe.blockers:
            return {
                "status": "BLOCKED",
                "removed_directory_count": 0,
                "removed_bytes": 0,
                "blockers": ["UNIVERSE_RETENTION_SELECTION_UNAVAILABLE"],
            }
        spot = frozenset(universe.spot_symbols)
        futures = frozenset(universe.futures_symbols)
        candidates: list[Path] = []
        for name, allowed in (
            ("spot", spot),
            ("usd_m_futures", futures),
            ("usd_m_futures_mark", futures),
            ("usd_m_futures_index", futures),
        ):
            candidates.extend(
                self._out_of_scope_children(self.archive_root / name, allowed)
            )
        for name in (
            "coin_m_futures",
            "coin_m_futures_mark",
            "coin_m_futures_index",
        ):
            root = self.archive_root / name
            if root.is_dir() and not root.is_symlink():
                candidates.append(root)
        candidates.extend(
            self._out_of_scope_children(self.opportunity_monitor_root / "SPOT", spot)
        )
        candidates.extend(
            self._out_of_scope_children(
                self.opportunity_monitor_root / "USD_M_FUTURES", futures
            )
        )
        candidates.extend(self._source_candidates("spot", spot))
        candidates.extend(self._source_candidates("futures/um", futures))
        if self.futures_replay_root is not None:
            candidates.extend(
                self._out_of_scope_flat_files(self.futures_replay_root, futures)
            )
        for root in self.futures_artifact_roots:
            candidates.extend(self._out_of_scope_children(root, futures))
        coin_m = self.source_cache_root / "data" / "futures" / "cm"
        if coin_m.is_dir() and not coin_m.is_symlink():
            candidates.append(coin_m)

        unique = tuple(sorted(set(candidates), key=lambda path: str(path).casefold()))
        removed_bytes = sum(self._directory_bytes(path) for path in unique)
        for path in unique:
            self._remove_verified_directory(path)
        return {
            "status": "PRUNED",
            "removed_directory_count": len(unique),
            "removed_bytes": removed_bytes,
            "blockers": [],
        }

    def _source_candidates(self, segment: str, allowed: frozenset[str]) -> list[Path]:
        root = self.source_cache_root / "data" / Path(segment)
        if not root.is_dir() or root.is_symlink():
            return []
        candidates: list[Path] = []
        for cadence in ("daily", "monthly"):
            cadence_root = root / cadence
            if not cadence_root.is_dir() or cadence_root.is_symlink():
                continue
            for kind_root in cadence_root.iterdir():
                if not kind_root.is_dir() or kind_root.is_symlink():
                    continue
                candidates.extend(self._out_of_scope_children(kind_root, allowed))
        return candidates

    @staticmethod
    def _out_of_scope_children(root: Path, allowed: frozenset[str]) -> list[Path]:
        if not root.is_dir() or root.is_symlink():
            return []
        return [
            child
            for child in root.iterdir()
            if child.is_dir()
            and not child.is_symlink()
            and _SYMBOL.fullmatch(child.name)
            and child.name not in allowed
        ]

    @staticmethod
    def _directory_bytes(path: Path) -> int:
        if path.is_file():
            return path.stat().st_size
        total = 0
        for child in path.rglob("*"):
            if child.is_file() and not child.is_symlink():
                total += child.stat().st_size
        return total

    def _remove_verified_directory(self, path: Path) -> None:
        resolved = path.resolve()
        allowed_roots = tuple(
            root.resolve()
            for root in (
                self.archive_root,
                self.source_cache_root,
                self.opportunity_monitor_root,
                *((self.futures_replay_root,) if self.futures_replay_root else ()),
                *self.futures_artifact_roots,
            )
        )
        if path.is_symlink() or not any(
            root in resolved.parents for root in allowed_roots
        ):
            raise ValueError("universe retention target is outside the allowed roots")
        if resolved.is_dir():
            shutil.rmtree(resolved)
        else:
            resolved.unlink()

    @staticmethod
    def _out_of_scope_flat_files(root: Path, allowed: frozenset[str]) -> list[Path]:
        if not root.is_dir() or root.is_symlink():
            return []
        candidates: list[Path] = []
        for child in root.iterdir():
            if not child.is_file() or child.is_symlink():
                continue
            symbol = child.name.split("-", maxsplit=1)[0]
            if _SYMBOL.fullmatch(symbol) and symbol not in allowed:
                candidates.append(child)
        return candidates


__all__ = ("MarketUniverseRetention",)
