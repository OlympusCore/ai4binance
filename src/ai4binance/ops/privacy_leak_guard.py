"""Fail-closed KVKK/privacy guard for public GitHub/cloud surfaces."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ai4binance.reporting import to_primitive

PUBLIC_SCAN_ROOTS: tuple[str, ...] = (
    "runtime/reports/ykb",
    "runtime/artifacts/validation",
)

PRIVATE_ALLOWED_ROOTS: tuple[str, ...] = (
    "runtime/state/private",
    "runtime/state/binance-accounting-local",
    "secrets",
)
RUNTIME_STATE_ROOTS: tuple[str, ...] = ("runtime/state",)
RUNTIME_STATE_PRIVATE_ROOTS: tuple[str, ...] = ("runtime/state/private",)

_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_EVM_ADDRESS_PATTERN = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
_BTC_ADDRESS_PATTERN = re.compile(r"\b(?:bc1|[13])[a-zA-HJ-NP-Z0-9]{25,62}\b")
_KVKK_PERSONAL_MARKERS: tuple[str, ...] = (
    "mailadresim",
    "mail adresim",
    "emailim",
    "e-posta adresim",
    "eposta adresim",
    "tc kimlik",
    "tckn",
    "kimlik no",
)
_BINANCE_WALLET_MARKERS: tuple[str, ...] = (
    "binanwallet",
    "binan wallet",
    "binan_wallet",
    "binancewallet",
    "binance wallet",
    "binance_wallet",
    "binance account",
    "binance uid",
)
_WALLET_CONTEXT_MARKERS: tuple[str, ...] = (
    "wallet",
    "address",
    "deposit",
    "withdraw",
    "binance",
)


@dataclass(frozen=True, slots=True)
class PrivacyLeakFinding:
    relative_path: str
    category: str


@dataclass(frozen=True, slots=True)
class PrivacyLeakScanResult:
    status: str
    scanned_roots: tuple[str, ...]
    findings: tuple[PrivacyLeakFinding, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.status not in {"CLEAR", "BLOCKED"}:
            raise ValueError("privacy leak scan status is invalid")
        if self.status == "CLEAR" and (self.findings or self.blockers):
            raise ValueError("clear privacy leak scan cannot contain blockers")
        if self.status == "BLOCKED" and not self.findings:
            raise ValueError("blocked privacy leak scan requires findings")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("privacy leak scan cannot authorize execution")

    def to_payload(self) -> dict[str, object]:
        return cast(dict[str, object], to_primitive(self))


def scan_public_privacy_leaks(
    repository_root: Path,
    *,
    public_roots: tuple[str, ...] = PUBLIC_SCAN_ROOTS,
) -> PrivacyLeakScanResult:
    """Scan public/shareable surfaces without returning raw personal values."""
    root = repository_root.resolve()
    findings: list[PrivacyLeakFinding] = []
    for relative_root in public_roots:
        scan_root = (root / relative_root).resolve()
        if not _is_relative_to(scan_root, root) or not scan_root.exists():
            continue
        candidates = (
            [scan_root]
            if scan_root.is_file()
            else [path for path in scan_root.rglob("*") if path.is_file()]
        )
        for path in candidates:
            if _is_private_allowed_path(root, path):
                continue
            text = _read_bounded_text(path)
            if text is None:
                continue
            for category in _privacy_categories(text):
                findings.append(
                    PrivacyLeakFinding(
                        relative_path=_relative_posix(root, path),
                        category=category,
                    )
                )
    blockers = (
        (
            "KVKK_PUBLIC_PRIVACY_LEAK",
            "NO_GITHUB_CLOUD_SHARE",
            "PUBLIC_ARTIFACT_REDACTION_REQUIRED",
        )
        if findings
        else ()
    )
    return PrivacyLeakScanResult(
        status="BLOCKED" if findings else "CLEAR",
        scanned_roots=public_roots,
        findings=tuple(dict.fromkeys(findings)),
        blockers=blockers,
    )


def scan_runtime_state_private_boundary(
    repository_root: Path,
    *,
    state_roots: tuple[str, ...] = RUNTIME_STATE_ROOTS,
    private_roots: tuple[str, ...] = RUNTIME_STATE_PRIVATE_ROOTS,
) -> PrivacyLeakScanResult:
    """Require wallet and personal state to stay under runtime/state/private."""
    root = repository_root.resolve()
    findings: list[PrivacyLeakFinding] = []
    for relative_root in state_roots:
        state_root = (root / relative_root).resolve()
        if not _is_relative_to(state_root, root) or not state_root.exists():
            continue
        candidates = (
            [state_root]
            if state_root.is_file()
            else [path for path in state_root.rglob("*") if path.is_file()]
        )
        for path in candidates:
            if _is_runtime_private_state_path(root, path, private_roots):
                continue
            text = _read_bounded_text(path)
            if text is None:
                continue
            for category in _privacy_categories(text):
                findings.append(
                    PrivacyLeakFinding(
                        relative_path=_relative_posix(root, path),
                        category=f"RUNTIME_STATE_{category}",
                    )
                )
    blockers = (
        (
            "RUNTIME_STATE_PRIVATE_BOUNDARY_VIOLATION",
            "PRIVATE_STATE_RELOCATION_REQUIRED",
            "PUBLIC_ARTIFACT_REDACTION_REQUIRED",
        )
        if findings
        else ()
    )
    return PrivacyLeakScanResult(
        status="BLOCKED" if findings else "CLEAR",
        scanned_roots=state_roots,
        findings=tuple(dict.fromkeys(findings)),
        blockers=blockers,
    )


def assert_runtime_state_private_boundary(repository_root: Path) -> None:
    """Raise when private runtime state is stored outside runtime/state/private."""
    result = scan_runtime_state_private_boundary(repository_root)
    if result.blockers:
        first = result.findings[0]
        raise ValueError(
            "RUNTIME_STATE_PRIVATE_BOUNDARY_VIOLATION: "
            f"{first.relative_path} contains {first.category}"
        )


def assert_public_privacy_data_do_not_leak(repository_root: Path) -> None:
    """Raise when public/shareable surfaces contain KVKK/privacy data."""
    result = scan_public_privacy_leaks(repository_root)
    if result.blockers:
        first = result.findings[0]
        raise ValueError(
            f"KVKK_PUBLIC_PRIVACY_LEAK: {first.relative_path} contains {first.category}"
        )


def _privacy_categories(text: str) -> tuple[str, ...]:
    lowered = text.casefold()
    categories: list[str] = []
    if _EMAIL_PATTERN.search(text):
        categories.append("EMAIL_ADDRESS_PUBLIC_LEAK")
    if any(marker in lowered for marker in _KVKK_PERSONAL_MARKERS):
        categories.append("KVKK_PERSONAL_DATA_PUBLIC_LEAK")
    if (
        any(marker in lowered for marker in _BINANCE_WALLET_MARKERS)
        or _EVM_ADDRESS_PATTERN.search(text)
        or _btc_address_with_wallet_context(text)
    ):
        categories.append("BINANCE_WALLET_IDENTIFIER_PUBLIC_LEAK")
    return tuple(dict.fromkeys(categories))


def _btc_address_with_wallet_context(text: str) -> bool:
    for match in _BTC_ADDRESS_PATTERN.finditer(text):
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 80)
        context = text[start:end].casefold()
        if any(marker in context for marker in _WALLET_CONTEXT_MARKERS):
            return True
    return False


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


def _is_runtime_private_state_path(
    root: Path,
    path: Path,
    private_roots: tuple[str, ...],
) -> bool:
    resolved = path.resolve()
    return any(
        _is_relative_to(resolved, (root / relative).resolve())
        for relative in private_roots
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
        description="Block KVKK/privacy leaks in public YKB artifacts."
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to scan.",
    )
    args = parser.parse_args(argv)
    result = scan_public_privacy_leaks(args.repository_root)
    if result.blockers:
        first = result.findings[0]
        print(
            f"KVKK_PUBLIC_PRIVACY_LEAK {first.relative_path} category={first.category}"
        )
        return 1
    print("PRIVACY_LEAK_GUARD_CLEAR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
