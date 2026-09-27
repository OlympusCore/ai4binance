"""Policy loading and report projection for virtual-market acceptance."""

from __future__ import annotations

from pathlib import Path

import yaml

from ai4binance.application.blocker_registry import load_blocker_registry
from ai4binance.core.report_rendering import render_professional_summary
from ai4binance.domain.blockers import BLOCKER_REGISTRY_PATH, BlockerDefinition
from ai4binance.domain.research.virtual_market import (
    MAX_ACCEPTANCE_POLICY_BYTES,
    AcceptancePolicy,
    MarketAcceptanceResult,
    MarketPerformanceEvidence,
    ResearchCandidateResult,
    SystemResearchAcceptance,
    TwoStageProfitabilityEvidence,
    acceptance_policy_from_payload,
    canonical_acceptance_blocker_codes,
)
from ai4binance.domain.research.virtual_market import (
    evaluate_market_acceptance as _evaluate_market_acceptance,
)
from ai4binance.domain.research.virtual_market import (
    evaluate_research_candidate as _evaluate_research_candidate,
)
from ai4binance.domain.research.virtual_market import (
    evaluate_two_stage_profitability_evidence as _evaluate_two_stage,
)


def render_system_acceptance_markdown(acceptance: SystemResearchAcceptance) -> str:
    """Render a report that keeps Spot and Futures acceptance visible separately."""

    spot = acceptance.spot
    futures = acceptance.futures
    spot_blockers = ", ".join(spot.blockers) if spot.blockers else "NONE"
    spot_evidence_refs = ", ".join(spot.evidence_refs)
    futures_blockers = ", ".join(futures.blockers) if futures.blockers else "NONE"
    futures_evidence_refs = ", ".join(futures.evidence_refs)
    system_blockers = ", ".join(acceptance.blockers) if acceptance.blockers else "NONE"
    canonical_blockers = (
        ", ".join(acceptance.canonical_blocker_codes)
        if acceptance.canonical_blocker_codes
        else "NONE"
    )
    return render_professional_summary(
        title="Virtual System Acceptance RESEARCH",
        observed_at=" / ".join(acceptance.evidence_refs[:2]) or "system-acceptance",
        status=acceptance.status.value,
        summary=(
            "This report keeps Spot and USD_M Futures acceptance separate. "
            "The system gate passes only when both markets pass; any failing "
            "market blocks the system result."
        ),
        sections=(
            (
                "Overview",
                (
                    "- Surface kind: `SYSTEM_ACCEPTANCE`",
                    f"- System status: `{acceptance.status.value}`",
                    "- Execution: `NO_TRADE`",
                    f"- Promotion: `{acceptance.promotion_status}`",
                    f"- Live eligibility: `{acceptance.live_eligibility_status}`",
                ),
            ),
            (
                "Spot Acceptance",
                (
                    f"- Market: `{spot.market.value}`",
                    f"- Status: `{spot.status.value}`",
                    f"- Blockers: `{spot_blockers}`",
                    f"- Evidence refs: `{spot_evidence_refs}`",
                ),
            ),
            (
                "USD_M Futures Acceptance",
                (
                    f"- Market: `{futures.market.value}`",
                    f"- Status: `{futures.status.value}`",
                    f"- Blockers: `{futures_blockers}`",
                    f"- Evidence refs: `{futures_evidence_refs}`",
                ),
            ),
            (
                "System Blockers",
                (
                    f"- Blockers: `{system_blockers}`",
                    f"- Canonical blockers: `{canonical_blockers}`",
                ),
            ),
        ),
        blockers=acceptance.blockers,
    )


def evaluate_market_acceptance(
    evidence: MarketPerformanceEvidence,
    policy: AcceptancePolicy | None = None,
) -> MarketAcceptanceResult:
    """Resolve the governed policy and delegate deterministic acceptance evaluation."""

    return _evaluate_market_acceptance(evidence, policy or load_acceptance_policy())


def evaluate_research_candidate(
    evidence: MarketPerformanceEvidence,
    policy: AcceptancePolicy | None = None,
) -> ResearchCandidateResult:
    """Resolve the governed policy and delegate deterministic acceptance evaluation."""

    return _evaluate_research_candidate(evidence, policy or load_acceptance_policy())


def evaluate_two_stage_profitability_evidence(
    evidence: MarketPerformanceEvidence,
    policy: AcceptancePolicy | None = None,
) -> TwoStageProfitabilityEvidence:
    """Resolve the governed policy and delegate deterministic acceptance evaluation."""

    return _evaluate_two_stage(evidence, policy or load_acceptance_policy())


def default_acceptance_policy_path(repository_root: Path | None = None) -> Path:
    """Return the repository-local virtual-market acceptance policy path."""

    root = (repository_root or Path.cwd()).resolve()
    return root / "config" / "research" / "virtual_market_acceptance.yaml"


def default_blocker_registry_path(repository_root: Path | None = None) -> Path:
    """Return the repository-local canonical blocker registry path."""

    root = (repository_root or Path.cwd()).resolve()
    return root / BLOCKER_REGISTRY_PATH


def load_acceptance_blocker_definitions(
    blockers: tuple[str, ...],
    registry_path: Path | None = None,
) -> tuple[BlockerDefinition, ...]:
    """Resolve virtual-market acceptance blockers through the canonical registry."""

    registry = load_blocker_registry(
        (registry_path or default_blocker_registry_path()).resolve()
    )
    return tuple(
        registry.require_canonical_code(blocker_code)
        for blocker_code in canonical_acceptance_blocker_codes(blockers)
    )


def load_acceptance_policy(path: Path | None = None) -> AcceptancePolicy:
    """Load the research-only acceptance policy from the governed YAML contract."""

    resolved = (path or default_acceptance_policy_path()).resolve()
    if resolved.stat().st_size > MAX_ACCEPTANCE_POLICY_BYTES:
        raise ValueError("virtual-market acceptance policy exceeds the bounded size")
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    return acceptance_policy_from_payload(raw)
