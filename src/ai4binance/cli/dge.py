"""Report-only DGE CLI helpers."""

from __future__ import annotations

from pathlib import Path

from ai4binance.governance.replay import replay_dge_decision
from ai4binance.governance.rules import default_governance_rule_catalog
from ai4binance.reporting import to_primitive


def dge_rules_payload() -> dict[str, object]:
    rules = default_governance_rule_catalog()
    return {
        "command": "dge-rules",
        "status": "READY",
        "rule_count": len(rules),
        "rules": [to_primitive(rule) for rule in rules],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "blockers": (),
    }


def dge_shadow_rules_payload() -> dict[str, object]:
    return {
        "command": "dge-shadow-rules",
        "status": "READY",
        "shadow_mode": "AVAILABLE_FOR_COUNTERFACTUAL_MEASUREMENT",
        "active_policy_mutation_allowed": False,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "blockers": ("HUMAN_REVIEW_REQUIRED_FOR_RULE_PROMOTION",),
    }


def dge_replay_payload(
    *,
    decision_id: str | None,
    repository_root: Path | None = None,
) -> dict[str, object]:
    normalized = (decision_id or "").strip()
    if not normalized:
        return {
            "command": "dge-replay",
            "status": "NON_REPRODUCIBLE",
            "blockers": ("DGE_DECISION_ID_REQUIRED",),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    result = replay_dge_decision(repository_root or Path.cwd(), normalized)
    payload = to_primitive(result)
    if not isinstance(payload, dict):
        raise TypeError("DGE replay payload must be a mapping")
    payload.update(
        {
            "command": "dge-replay",
            "blockers": (result.blocker,) if result.blocker else (),
        }
    )
    return payload
