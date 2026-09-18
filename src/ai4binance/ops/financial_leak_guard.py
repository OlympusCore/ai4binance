"""Fail-closed guard against publishing raw Binance financial values."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ai4binance.reporting import to_primitive

RAW_BINANCE_FINANCIAL_TOKENS: tuple[str, ...] = (
    "total_value_usdt",
    "market_value_usdt",
    "free_market_value_usdt",
    "locked_market_value_usdt",
    "walletBalance",
    "availableBalance",
    "crossWalletBalance",
    "crossUnPnl",
    "unrealizedProfit",
    "positionInitialMargin",
    "openOrderInitialMargin",
)

PUBLIC_SCAN_ROOTS: tuple[str, ...] = (
    "runtime/reports/ykb",
    "runtime/artifacts/validation",
)

PRIVATE_ALLOWED_ROOTS: tuple[str, ...] = (
    "runtime/state/private",
    "runtime/state/binance-accounting-local",
    "secrets",
)


@dataclass(frozen=True, slots=True)
class FinancialLeakFinding:
    relative_path: str
    token: str


@dataclass(frozen=True, slots=True)
class FinancialLeakScanResult:
    status: str
    scanned_roots: tuple[str, ...]
    findings: tuple[FinancialLeakFinding, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.status not in {"CLEAR", "BLOCKED"}:
            raise ValueError("financial leak scan status is invalid")
        if self.status == "CLEAR" and (self.findings or self.blockers):
            raise ValueError("clear financial leak scan cannot contain blockers")
        if self.status == "BLOCKED" and not self.findings:
            raise ValueError("blocked financial leak scan requires findings")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("financial leak scan cannot authorize execution")

    def to_payload(self) -> dict[str, object]:
        return cast(dict[str, object], to_primitive(self))


def scan_public_financial_value_leaks(
    repository_root: Path,
    *,
    public_roots: tuple[str, ...] = PUBLIC_SCAN_ROOTS,
) -> FinancialLeakScanResult:
    """Scan shareable YKB/report surfaces for raw Binance financial fields."""
    root = repository_root.resolve()
    findings: list[FinancialLeakFinding] = []
    for relative_root in public_roots:
        scan_root = (root / relative_root).resolve()
        if not _is_relative_to(scan_root, root) or not scan_root.exists():
            continue
        if scan_root.is_file():
            candidates = [scan_root]
        else:
            candidates = [path for path in scan_root.rglob("*") if path.is_file()]
        for path in candidates:
            if _is_private_allowed_path(root, path):
                continue
            text = _read_bounded_text(path)
            if text is None:
                continue
            for token in RAW_BINANCE_FINANCIAL_TOKENS:
                if token in text:
                    findings.append(
                        FinancialLeakFinding(
                            relative_path=_relative_posix(root, path),
                            token=token,
                        )
                    )
                    break
    blockers = ("BINANCE_FINANCIAL_VALUE_PUBLIC_LEAK",) if findings else ()
    return FinancialLeakScanResult(
        status="BLOCKED" if findings else "CLEAR",
        scanned_roots=public_roots,
        findings=tuple(findings),
        blockers=blockers,
    )


def assert_public_financial_values_do_not_leak(repository_root: Path) -> None:
    """Raise when public/shareable surfaces contain raw Binance values."""
    result = scan_public_financial_value_leaks(repository_root)
    if result.blockers:
        first = result.findings[0]
        raise ValueError(
            "BINANCE_FINANCIAL_VALUE_PUBLIC_LEAK: "
            f"{first.relative_path} contains {first.token}"
        )


def _read_bounded_text(path: Path, *, max_bytes: int = 2_000_000) -> str | None:
    try:
        if path.stat().st_size > max_bytes:
            return None
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _is_private_allowed_path(root: Path, path: Path) -> bool:
    resolved = path.resolve()
    return any(
        _is_relative_to(resolved, (root / relative).resolve())
        for relative in PRIVATE_ALLOWED_ROOTS
    )


def _relative_posix(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Block raw Binance financial values in public YKB artifacts."
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to scan.",
    )
    args = parser.parse_args(argv)
    result = scan_public_financial_value_leaks(args.repository_root)
    if result.blockers:
        first = result.findings[0]
        print(
            "BINANCE_FINANCIAL_VALUE_PUBLIC_LEAK "
            f"{first.relative_path} token={first.token}"
        )
        return 1
    print("BINANCE_FINANCIAL_VALUE_PUBLIC_LEAK_GUARD_CLEAR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
