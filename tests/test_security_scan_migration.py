"""Regression tests for the canonical security-scanner migration."""

from pathlib import Path
from typing import cast

from ai4binance.infrastructure.security import (
    SecurityFinding,
    SecurityScanArtifact,
    SecurityScanner,
    SecurityScanRequest,
    SecurityScanService,
    SecurityScanStatus,
    SecuritySeverity,
)
from ai4binance.ops.kaizen_quality import build_architecture_baseline
from ai4binance.security_scan import (
    SecurityFinding as LegacySecurityFinding,
)
from ai4binance.security_scan import (
    SecurityScanArtifact as LegacySecurityScanArtifact,
)
from ai4binance.security_scan import (
    SecurityScanner as LegacySecurityScanner,
)
from ai4binance.security_scan import (
    SecurityScanRequest as LegacySecurityScanRequest,
)
from ai4binance.security_scan import (
    SecurityScanService as LegacySecurityScanService,
)
from ai4binance.security_scan import (
    SecurityScanStatus as LegacySecurityScanStatus,
)
from ai4binance.security_scan import (
    SecuritySeverity as LegacySecuritySeverity,
)

ROOT = Path(__file__).resolve().parents[1]


def test_security_scan_facade_preserves_public_identity() -> None:
    assert LegacySecurityFinding is SecurityFinding
    assert LegacySecurityScanArtifact is SecurityScanArtifact
    assert LegacySecurityScanner is SecurityScanner
    assert LegacySecurityScanRequest is SecurityScanRequest
    assert LegacySecurityScanService is SecurityScanService
    assert LegacySecurityScanStatus is SecurityScanStatus
    assert LegacySecuritySeverity is SecuritySeverity


def test_security_scan_migration_is_recorded_as_canonical_and_facade() -> None:
    payload = build_architecture_baseline(ROOT).to_payload()
    ledger = cast(list[dict[str, object]], payload["migration_ledger"])
    by_path = {cast(str, item["source_path"]): item for item in ledger}

    canonical_path = "src/ai4binance/infrastructure/security/scanner.py"
    canonical = by_path[canonical_path]
    assert canonical["classification"] == "KEEP"
    assert canonical["current_role"] == "SECURITY_ADAPTER"
    assert canonical["canonical_domain"] == "16_SECURITY"
    assert canonical["logical_plane"] == "CONTROL & ASSURANCE PLANE"
    assert canonical["runtime_class"] == "GOVERNED_CONTROL"
    assert canonical["hot_path"] is False
    assert canonical["confidence"] == "HIGH"
    assert canonical["blockers"] == []

    facade = by_path["src/ai4binance/security_scan.py"]
    assert facade["classification"] == "FACADE"
    assert facade["target_paths"] == [canonical_path]
    assert facade["execution_allowed"] is False
    assert facade["promotion_status"] == "RESEARCH_ONLY"
    assert facade["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
