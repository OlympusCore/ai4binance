"""Canonical domain facade with legacy contract compatibility."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from ai4binance.domain.universe import (
    UniverseFilterPolicy,
    UniverseFilterResult,
    UniverseMarket,
    UniverseSymbol,
)

_LEGACY_DOMAIN_PATH = Path(__file__).resolve().parents[1] / "domain.py"
_LEGACY_DOMAIN_SPEC = spec_from_file_location(
    "ai4binance._legacy_domain_contracts",
    _LEGACY_DOMAIN_PATH,
)
if _LEGACY_DOMAIN_SPEC is None or _LEGACY_DOMAIN_SPEC.loader is None:
    raise ImportError(f"Cannot load legacy domain contracts from {_LEGACY_DOMAIN_PATH}")
_legacy_domain = module_from_spec(_LEGACY_DOMAIN_SPEC)
_LEGACY_DOMAIN_SPEC.loader.exec_module(_legacy_domain)

Action = _legacy_domain.Action
AgentScore = _legacy_domain.AgentScore
CandidateStatus = _legacy_domain.CandidateStatus
Decision = _legacy_domain.Decision
DEFAULT_SIGNAL_TIMESTAMP = _legacy_domain.DEFAULT_SIGNAL_TIMESTAMP
ExecutionStatus = _legacy_domain.ExecutionStatus
FIRST_SETUP_QUALITY_QUESTION = _legacy_domain.FIRST_SETUP_QUALITY_QUESTION
LiveGateInput = _legacy_domain.LiveGateInput
LiveGateResult = _legacy_domain.LiveGateResult
PriceZone = _legacy_domain.PriceZone
SetupScanDisposition = _legacy_domain.SetupScanDisposition
SetupTier = _legacy_domain.SetupTier
Signal = _legacy_domain.Signal
SignalSubScores = _legacy_domain.SignalSubScores
TradeCandidate = _legacy_domain.TradeCandidate
ValidationStatus = _legacy_domain.ValidationStatus
ZERO = _legacy_domain.ZERO
setup_scan_disposition = _legacy_domain.setup_scan_disposition

__all__ = (
    "DEFAULT_SIGNAL_TIMESTAMP",
    "FIRST_SETUP_QUALITY_QUESTION",
    "ZERO",
    "Action",
    "AgentScore",
    "CandidateStatus",
    "Decision",
    "ExecutionStatus",
    "LiveGateInput",
    "LiveGateResult",
    "PriceZone",
    "SetupScanDisposition",
    "SetupTier",
    "Signal",
    "SignalSubScores",
    "TradeCandidate",
    "UniverseFilterPolicy",
    "UniverseFilterResult",
    "UniverseMarket",
    "UniverseSymbol",
    "ValidationStatus",
    "setup_scan_disposition",
)
