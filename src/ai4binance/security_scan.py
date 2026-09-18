"""Compatibility facade for the canonical security-scanner adapter."""

from ai4binance.infrastructure.security.scanner import (
    SecurityFinding,
    SecurityScanArtifact,
    SecurityScanner,
    SecurityScanRequest,
    SecurityScanService,
    SecurityScanStatus,
    SecuritySeverity,
)

__all__ = (
    "SecurityFinding",
    "SecurityScanArtifact",
    "SecurityScanRequest",
    "SecurityScanService",
    "SecurityScanStatus",
    "SecurityScanner",
    "SecuritySeverity",
)
