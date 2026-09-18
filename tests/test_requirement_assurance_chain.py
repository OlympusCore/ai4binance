"""Regression coverage for deterministic requirement assurance chains."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ai4binance.governance.enforcement.inventory import (
    RequirementAssuranceDecision,
    load_enforcement_inventory,
)

ROOT = Path(__file__).parent.parent


def test_requirement_assurance_chain_validates_full_linkage_without_authority() -> None:
    inventory = load_enforcement_inventory()
    traceability = inventory.requirement_traceability
    assert traceability is not None

    chains = traceability.assurance_chains(ROOT)

    assert len(chains) == 20
    assert (
        sum(
            item.assurance_decision is RequirementAssuranceDecision.ASSURED
            for item in chains
        )
        == 17
    )
    assured = next(item for item in chains if item.requirement_id == "RQ-002")
    assert assured.snapshot_bound is True
    assert len(assured.snapshot_evidence_sha256) == 64
    assert assured.authority_inherited is False
    assert assured.execution_allowed is False
    assert assured.promotion_status == "RESEARCH_ONLY"
    assert assured.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_requirement_assurance_keeps_external_evidence_gaps_blocked() -> None:
    inventory = load_enforcement_inventory()
    traceability = inventory.requirement_traceability
    assert traceability is not None

    chains = {item.requirement_id: item for item in traceability.assurance_chains(ROOT)}

    assert chains["RQ-001"].assurance_decision is RequirementAssuranceDecision.ASSURED
    assert chains["RQ-003"].enforcement_points == ("market_snapshot_wire_validation",)
    assert chains["RQ-009"].enforcement_points == ("governed_memory_candidate_intake",)
    assert chains["RQ-013"].assurance_decision is RequirementAssuranceDecision.BLOCKED
    assert chains["RQ-015"].assurance_decision is RequirementAssuranceDecision.BLOCKED
    assert chains["RQ-016"].assurance_decision is RequirementAssuranceDecision.BLOCKED


def test_requirement_assurance_chain_rejects_authority_or_execution_expansion() -> None:
    inventory = load_enforcement_inventory()
    traceability = inventory.requirement_traceability
    assert traceability is not None
    assured = next(
        item
        for item in traceability.assurance_chains(ROOT)
        if item.requirement_id == "RQ-002"
    )

    with pytest.raises(ValueError, match="cannot inherit authority"):
        replace(assured, authority_inherited=True)
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(assured, execution_allowed=True)
