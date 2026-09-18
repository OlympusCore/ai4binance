"""Contract coverage for the non-authoritative logical-architecture registry."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ai4binance.governance.architecture import (
    LogicalArchitectureGraph,
    LogicalComponentKind,
    LogicalRelationType,
    load_logical_architecture_registry,
    validate_runtime_architecture_conformance,
)
from ai4binance.governance.framework import (
    RelationshipRuleId,
    build_core_architecture,
    build_relationship_rule_catalog,
)

ROOT = Path(__file__).parents[3]
REGISTRY_PATH = ROOT / "docs/registries/registry_logical_architecture.yaml"


def test_registry_is_schema_valid_sorted_and_live_blocked() -> None:
    registry = load_logical_architecture_registry(REGISTRY_PATH)

    assert registry.registry_id == "AI4B-LOGICAL-ARCHITECTURE-REGISTRY-001"
    assert registry.version == "1.12.0"
    assert registry.source_of_truth is False
    assert registry.execution_allowed is False
    assert registry.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert [component.component_id for component in registry.components] == sorted(
        component.component_id for component in registry.components
    )
    assert all(component.side_effects is False for component in registry.components)
    assert all(
        component.decision_authority is False for component in registry.components
    )
    assert all(component.risk_override is False for component in registry.components)
    assert all(
        component.validation_override is False for component in registry.components
    )
    canonical_planes = {
        domain.domain_id.value: domain.plane.value
        for domain in build_core_architecture().domains
    }
    assert all(
        component.logical_plane == canonical_planes[component.canonical_domain]
        for component in registry.components
    )


def test_registry_maps_opportunity_intelligence_without_authority_expansion() -> None:
    registry = load_logical_architecture_registry(REGISTRY_PATH)
    component_index = {
        component.component_id: component for component in registry.components
    }

    assert component_index["opportunity-intelligence"].source_paths == (
        "src/ai4binance/opportunity_intelligence.py",
    )
    assert component_index["opportunity-lifecycle-ledger"].source_paths == (
        "src/ai4binance/historical_replay_state.py",
        "src/ai4binance/opportunity_ledger.py",
    )
    assert component_index["opportunity-outcome-evaluation"].source_paths == (
        "src/ai4binance/opportunity_outcomes.py",
        "src/ai4binance/research/backtesting/futures_engine.py",
    )
    for component_id in (
        "opportunity-intelligence",
        "opportunity-lifecycle-ledger",
        "opportunity-outcome-evaluation",
    ):
        component = component_index[component_id]
        assert component.deterministic is True
        assert component.llm_dependency is False
        assert component.authority_effect == "EVIDENCE_ONLY"
        assert component.execution_allowed is False
        assert component.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_registry_maps_coverage_assurance_domains_without_authority_expansion() -> None:
    registry = load_logical_architecture_registry(REGISTRY_PATH)
    component_index = {
        component.component_id: component for component in registry.components
    }
    expected_sources = {
        "data-quality": ("src/ai4binance/data/binance_vision.py",),
        "event-replay": ("src/ai4binance/governance/replay.py",),
        "portfolio-accounting": ("src/ai4binance/portfolio/cost_basis.py",),
        "security-controls": ("src/ai4binance/governance/mcp_gateway.py",),
    }

    assert {
        component_id: component_index[component_id].source_paths
        for component_id in expected_sources
    } == expected_sources
    assert all(
        component_index[component_id].authority_effect == "EVIDENCE_ONLY"
        and component_index[component_id].deterministic is True
        and component_index[component_id].llm_dependency is False
        and component_index[component_id].side_effects is False
        and component_index[component_id].decision_authority is False
        and component_index[component_id].risk_override is False
        and component_index[component_id].validation_override is False
        and component_index[component_id].execution_allowed is False
        and component_index[component_id].live_eligibility_status
        == "LIVE_ORDER_BLOCKED"
        for component_id in expected_sources
    )


def test_loader_rejects_canonical_domain_plane_drift(tmp_path: Path) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    components = payload["components"]
    assert isinstance(components, list)
    component = next(
        item for item in components if item["component_id"] == "decision-candidate"
    )
    component["logical_plane"] = "CONTROL & ASSURANCE PLANE"
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            r"canonical domain-plane drift: decision-candidate\.logical_plane "
            "must be DECISION & EXECUTION PLANE"
        ),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_registry_preserves_canonical_decision_chain_semantics() -> None:
    registry = load_logical_architecture_registry(REGISTRY_PATH)
    component_index = {
        component.component_id: component for component in registry.components
    }
    relation_index = {relation.relation_id: relation for relation in registry.relations}
    canonical_component_names = {
        "closure-review": "ClosureReview",
        "decision-candidate": "DecisionCandidate",
        "decision-governance": "DecisionGovernance",
        "deterministic-core": "DeterministicCore",
        "execution-gate-result": "ExecutionGateResult",
        "execution-record": "ExecutionRecord",
        "learning-candidate": "LearningCandidate",
        "lesson": "Lesson",
        "policy": "Policy",
        "position-lifecycle": "PositionLifecycle",
        "risk-assessment": "RiskAssessment",
        "setup": "Setup",
        "trade-decision": "TradeDecision",
        "trade-plan": "TradePlan",
        "validation": "Validation",
    }
    decision_rule_ids = {
        RelationshipRuleId.RR_007_DECISION,
        RelationshipRuleId.RR_008_RISK,
        RelationshipRuleId.RR_012_GOVERNANCE,
        RelationshipRuleId.RR_013_EXECUTION,
        RelationshipRuleId.RR_015_POSITION_LIFECYCLE,
        RelationshipRuleId.RR_016_REVIEW,
        RelationshipRuleId.RR_017_LESSON,
        RelationshipRuleId.RR_018_LEARNING,
        RelationshipRuleId.RR_021_VALIDATION,
        RelationshipRuleId.RR_022_DECISION_GOVERNANCE,
    }
    canonical_required_triples = {
        (triple.source, triple.relationship.value, triple.target)
        for rule in build_relationship_rule_catalog().rules
        if rule.rule_id in decision_rule_ids
        for triple in rule.required
    }

    assert {
        "closure-review",
        "decision-candidate",
        "decision-governance",
        "deterministic-core",
        "execution-gate-result",
        "execution-record",
        "learning-candidate",
        "lesson",
        "policy",
        "position-lifecycle",
        "risk-assessment",
        "setup",
        "trade-decision",
        "trade-plan",
        "validation",
    } <= component_index.keys()
    assert component_index["closure-review"].authority_effect == "EVIDENCE_ONLY"
    assert component_index["decision-candidate"].authority_effect == "EVIDENCE_ONLY"
    assert component_index["decision-governance"].authority_effect == "IMPLEMENTATION"
    assert component_index["deterministic-core"].authority_effect == "IMPLEMENTATION"
    assert component_index["execution-gate-result"].authority_effect == "VETO"
    assert component_index["execution-record"].authority_effect == "EVIDENCE_ONLY"
    assert component_index["learning-candidate"].authority_effect == "EVIDENCE_ONLY"
    assert component_index["lesson"].authority_effect == "EVIDENCE_ONLY"
    assert component_index["policy"].authority_effect == "VETO"
    assert component_index["position-lifecycle"].authority_effect == "EVIDENCE_ONLY"
    assert component_index["risk-assessment"].authority_effect == "VETO"
    assert component_index["setup"].authority_effect == "EVIDENCE_ONLY"
    assert component_index["trade-plan"].authority_effect == "EVIDENCE_ONLY"
    assert component_index["validation"].authority_effect == "VETO"
    assert all(
        component_index[component_id].hot_path
        and component_index[component_id].deterministic
        and not component_index[component_id].llm_dependency
        for component_id in canonical_component_names
    )
    assert {
        relation_id: (
            relation_index[relation_id].from_component_id,
            relation_index[relation_id].relation_type,
            relation_index[relation_id].to_component_id,
        )
        for relation_id in (
            "candidate-constrained-by-risk-assessment",
            "candidate-validated-by-validation",
            "closure-review-produces-lesson",
            "decision-governance-produces-trade-decision",
            "deterministic-core-produces-decision-candidate",
            "execution-record-creates-position-lifecycle",
            "lesson-proposes-learning-candidate",
            "position-lifecycle-evaluated-by-closure-review",
            "setup-evaluated-by-deterministic-core",
            "trade-decision-governed-by-policy",
            "trade-plan-subject-to-execution-gate-result",
        )
    } == {
        "candidate-constrained-by-risk-assessment": (
            "decision-candidate",
            LogicalRelationType.CONSTRAINED_BY,
            "risk-assessment",
        ),
        "candidate-validated-by-validation": (
            "decision-candidate",
            LogicalRelationType.VALIDATED_BY,
            "validation",
        ),
        "closure-review-produces-lesson": (
            "closure-review",
            LogicalRelationType.PRODUCES_LESSON,
            "lesson",
        ),
        "decision-governance-produces-trade-decision": (
            "decision-governance",
            LogicalRelationType.PRODUCES,
            "trade-decision",
        ),
        "deterministic-core-produces-decision-candidate": (
            "deterministic-core",
            LogicalRelationType.PRODUCES,
            "decision-candidate",
        ),
        "execution-record-creates-position-lifecycle": (
            "execution-record",
            LogicalRelationType.CREATES,
            "position-lifecycle",
        ),
        "lesson-proposes-learning-candidate": (
            "lesson",
            LogicalRelationType.PROPOSES,
            "learning-candidate",
        ),
        "position-lifecycle-evaluated-by-closure-review": (
            "position-lifecycle",
            LogicalRelationType.EVALUATED_BY,
            "closure-review",
        ),
        "setup-evaluated-by-deterministic-core": (
            "setup",
            LogicalRelationType.EVALUATED_BY,
            "deterministic-core",
        ),
        "trade-decision-governed-by-policy": (
            "trade-decision",
            LogicalRelationType.GOVERNED_BY,
            "policy",
        ),
        "trade-plan-subject-to-execution-gate-result": (
            "trade-plan",
            LogicalRelationType.SUBJECT_TO,
            "execution-gate-result",
        ),
    }
    assert {
        (
            canonical_component_names[relation.from_component_id],
            relation.relation_type.value,
            canonical_component_names[relation.to_component_id],
        )
        for relation in relation_index.values()
        if relation.relation_id
        in {
            "candidate-constrained-by-risk-assessment",
            "candidate-validated-by-validation",
            "closure-review-produces-lesson",
            "decision-governance-produces-trade-decision",
            "deterministic-core-produces-decision-candidate",
            "execution-record-creates-position-lifecycle",
            "lesson-proposes-learning-candidate",
            "position-lifecycle-evaluated-by-closure-review",
            "setup-evaluated-by-deterministic-core",
            "trade-decision-governed-by-policy",
            "trade-plan-subject-to-execution-gate-result",
        }
    } == canonical_required_triples


def test_loader_rejects_missing_setup_evaluation_relation(tmp_path: Path) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    relations = payload["relations"]
    assert isinstance(relations, list)
    payload["relations"] = [
        relation
        for relation in relations
        if relation["relation_id"] != "setup-evaluated-by-deterministic-core"
    ]
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "canonical decision chain drift: missing relation "
            "setup-evaluated-by-deterministic-core"
        ),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_missing_trade_decision_governance_relation(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    relations = payload["relations"]
    assert isinstance(relations, list)
    payload["relations"] = [
        relation
        for relation in relations
        if relation["relation_id"] != "trade-decision-governed-by-policy"
    ]
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "canonical decision chain drift: missing relation "
            "trade-decision-governed-by-policy"
        ),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_missing_trade_plan_execution_gate_relation(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    relations = payload["relations"]
    assert isinstance(relations, list)
    payload["relations"] = [
        relation
        for relation in relations
        if relation["relation_id"] != "trade-plan-subject-to-execution-gate-result"
    ]
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "canonical decision chain drift: missing relation "
            "trade-plan-subject-to-execution-gate-result"
        ),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_missing_execution_position_lifecycle_relation(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    relations = payload["relations"]
    assert isinstance(relations, list)
    payload["relations"] = [
        relation
        for relation in relations
        if relation["relation_id"] != "execution-record-creates-position-lifecycle"
    ]
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "canonical decision chain drift: missing relation "
            "execution-record-creates-position-lifecycle"
        ),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_missing_position_lifecycle_closure_review_relation(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    relations = payload["relations"]
    assert isinstance(relations, list)
    payload["relations"] = [
        relation
        for relation in relations
        if relation["relation_id"] != "position-lifecycle-evaluated-by-closure-review"
    ]
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "canonical decision chain drift: missing relation "
            "position-lifecycle-evaluated-by-closure-review"
        ),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_missing_closure_review_lesson_relation(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    relations = payload["relations"]
    assert isinstance(relations, list)
    payload["relations"] = [
        relation
        for relation in relations
        if relation["relation_id"] != "closure-review-produces-lesson"
    ]
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "canonical decision chain drift: missing relation "
            "closure-review-produces-lesson"
        ),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_missing_lesson_learning_candidate_relation(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    relations = payload["relations"]
    assert isinstance(relations, list)
    payload["relations"] = [
        relation
        for relation in relations
        if relation["relation_id"] != "lesson-proposes-learning-candidate"
    ]
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "canonical decision chain drift: missing relation "
            "lesson-proposes-learning-candidate"
        ),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_execution_gate_authority_effect_drift(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    components = payload["components"]
    assert isinstance(components, list)
    component = next(
        item for item in components if item["component_id"] == "execution-gate-result"
    )
    component["authority_effect"] = "EVIDENCE_ONLY"
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"execution-gate-result\.authority_effect must be VETO",
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_missing_canonical_decision_component(tmp_path: Path) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    components = payload["components"]
    relations = payload["relations"]
    assert isinstance(components, list)
    assert isinstance(relations, list)
    payload["components"] = [
        component
        for component in components
        if component["component_id"] != "validation"
    ]
    payload["relations"] = [
        relation
        for relation in relations
        if relation["relation_id"] != "candidate-validated-by-validation"
    ]
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="canonical decision chain drift: missing component validation",
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_missing_canonical_decision_relation(tmp_path: Path) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    relations = payload["relations"]
    assert isinstance(relations, list)
    payload["relations"] = [
        relation
        for relation in relations
        if relation["relation_id"] != "candidate-constrained-by-risk-assessment"
    ]
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "canonical decision chain drift: missing relation "
            "candidate-constrained-by-risk-assessment"
        ),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_noncanonical_decision_relation_semantics(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    relations = payload["relations"]
    assert isinstance(relations, list)
    relation = next(
        item
        for item in relations
        if item["relation_id"] == "candidate-validated-by-validation"
    )
    relation["relation_type"] = "PRODUCES"
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "canonical decision chain drift: "
            "candidate-validated-by-validation has non-canonical semantics"
        ),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_decision_chain_authority_effect_drift(tmp_path: Path) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    components = payload["components"]
    assert isinstance(components, list)
    component = next(
        item for item in components if item["component_id"] == "risk-assessment"
    )
    component["authority_effect"] = "EVIDENCE_ONLY"
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"risk-assessment\.authority_effect must be VETO",
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


@pytest.mark.parametrize("component_id", ["decision-governance", "deterministic-core"])
def test_loader_rejects_decision_implementation_effect_drift(
    tmp_path: Path,
    component_id: str,
) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    components = payload["components"]
    assert isinstance(components, list)
    component = next(
        item for item in components if item["component_id"] == component_id
    )
    component["authority_effect"] = "EVIDENCE_ONLY"
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=rf"{component_id}\.authority_effect must be IMPLEMENTATION",
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "expected_message"),
    [
        ("hot_path", False, "deterministic-core.hot_path must be true"),
        ("deterministic", False, "deterministic-core.deterministic must be true"),
        ("llm_dependency", True, "deterministic-core.llm_dependency must be false"),
    ],
)
def test_loader_rejects_decision_chain_runtime_characteristic_drift(
    tmp_path: Path,
    field_name: str,
    invalid_value: bool,
    expected_message: str,
) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    components = payload["components"]
    assert isinstance(components, list)
    component = next(
        item for item in components if item["component_id"] == "deterministic-core"
    )
    component[field_name] = invalid_value
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_message):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_advisory_agent_trade_decision_shortcut(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    components = payload["components"]
    relations = payload["relations"]
    assert isinstance(components, list)
    assert isinstance(relations, list)
    advisory_agent = dict(
        next(
            component
            for component in components
            if component["component_id"] == "decision-candidate"
        )
    )
    advisory_agent.update(
        component_id="advisory-agent",
        component_kind="ADVISORY_AGENT",
        owner="Advisory Analysis",
        runtime_class="ADVISORY_ONLY",
    )
    components.append(advisory_agent)
    payload["components"] = sorted(components, key=lambda item: item["component_id"])
    relations.append(
        {
            "relation_id": "advisory-agent-produces-trade-decision",
            "from_component_id": "advisory-agent",
            "to_component_id": "trade-decision",
            "relation_type": "PRODUCES",
        }
    )
    payload["relations"] = sorted(relations, key=lambda item: item["relation_id"])
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "unauthorized trade-decision producer: "
            "advisory-agent-produces-trade-decision"
        ),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_canonical_agent_execution_shortcut(tmp_path: Path) -> None:
    prohibited = next(
        rule
        for rule in build_relationship_rule_catalog().rules
        if rule.rule_id is RelationshipRuleId.RR_014_NO_SHORTCUT
    ).prohibited
    assert tuple(
        (triple.source, triple.relationship.value, triple.target)
        for triple in prohibited
    ) == (("Agent", "EXECUTES", "Order"),)

    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    components = payload["components"]
    relations = payload["relations"]
    assert isinstance(components, list)
    assert isinstance(relations, list)
    advisory_agent = dict(
        next(
            component
            for component in components
            if component["component_id"] == "decision-candidate"
        )
    )
    advisory_agent.update(
        component_id="advisory-agent",
        component_kind="ADVISORY_AGENT",
        owner="Advisory Analysis",
        runtime_class="ADVISORY_ONLY",
    )
    order = dict(
        next(
            component
            for component in components
            if component["component_id"] == "trade-plan"
        )
    )
    order.update(component_id="order", runtime_class="IMMUTABLE_CONTRACT")
    components.extend((advisory_agent, order))
    payload["components"] = sorted(components, key=lambda item: item["component_id"])
    relations.append(
        {
            "relation_id": "advisory-agent-executes-order",
            "from_component_id": "advisory-agent",
            "to_component_id": "order",
            "relation_type": "EXECUTES",
        }
    )
    payload["relations"] = sorted(relations, key=lambda item: item["relation_id"])
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=("unauthorized agent execution shortcut: advisory-agent-executes-order"),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_canonical_learning_self_promotion_shortcut(
    tmp_path: Path,
) -> None:
    prohibited = next(
        rule
        for rule in build_relationship_rule_catalog().rules
        if rule.rule_id is RelationshipRuleId.RR_019_NO_SELF_PROMOTION
    ).prohibited
    assert tuple(
        (triple.source, triple.relationship.value, triple.target)
        for triple in prohibited
    ) == (("LearningCandidate", "PROMOTES", "ProductionComponent"),)

    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    components = payload["components"]
    relations = payload["relations"]
    assert isinstance(components, list)
    assert isinstance(relations, list)
    production_component = dict(
        next(
            component
            for component in components
            if component["component_id"] == "learning-candidate"
        )
    )
    production_component.update(
        component_id="production-component",
        owner="Production Governance",
    )
    components.append(production_component)
    payload["components"] = sorted(components, key=lambda item: item["component_id"])
    relations.append(
        {
            "relation_id": "learning-candidate-promotes-production-component",
            "from_component_id": "learning-candidate",
            "to_component_id": "production-component",
            "relation_type": "PROMOTES",
        }
    )
    payload["relations"] = sorted(relations, key=lambda item: item["relation_id"])
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "unauthorized learning self-promotion shortcut: "
            "learning-candidate-promotes-production-component"
        ),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_non_governance_trade_decision_producer(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    relations = payload["relations"]
    assert isinstance(relations, list)
    relations.append(
        {
            "relation_id": "deterministic-core-produces-trade-decision",
            "from_component_id": "deterministic-core",
            "to_component_id": "trade-decision",
            "relation_type": "PRODUCES",
        }
    )
    payload["relations"] = sorted(relations, key=lambda item: item["relation_id"])
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "unauthorized trade-decision producer: "
            "deterministic-core-produces-trade-decision"
        ),
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_component_kind_taxonomy_is_closed_and_schema_aligned(tmp_path: Path) -> None:
    expected_kinds = {
        "ADAPTER",
        "ADVISORY_AGENT",
        "CAPABILITY",
        "CONTROL",
        "DOMAIN",
        "ENGINE",
        "FACADE",
        "GATE",
        "ORCHESTRATOR",
        "REGISTRY",
        "RUNTIME_ACTOR",
        "SERVICE",
    }
    assert {kind.value for kind in LogicalComponentKind} == expected_kinds

    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    components = payload["components"]
    assert isinstance(components, list)
    first_component = components[0]
    assert isinstance(first_component, dict)

    for component_kind in expected_kinds:
        first_component["component_kind"] = component_kind
        candidate_path = tmp_path / f"{component_kind}.yaml"
        candidate_path.write_text(
            yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
        )
        registry = load_logical_architecture_registry(
            candidate_path, schema_root=ROOT / "schemas"
        )
        assert registry.components[0].component_kind.value == component_kind

    first_component["component_kind"] = "UNCLASSIFIED"
    invalid_path = tmp_path / "invalid-kind.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="schema validation failed"):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_registry_graph_resolves_dependencies_without_cycles() -> None:
    graph = LogicalArchitectureGraph(load_logical_architecture_registry(REGISTRY_PATH))

    assert graph.dependencies_of("kaizen-quality-snapshot") == (
        "logical-architecture-registry",
    )
    assert graph.dependents_of("logical-architecture-registry") == (
        "kaizen-quality-snapshot",
    )
    assert graph.dependency_cycles() == ()
    graph.assert_acyclic_dependencies()


def test_loader_rejects_authority_grant_in_component(tmp_path: Path) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    components = payload["components"]
    assert isinstance(components, list)
    first_component = components[0]
    assert isinstance(first_component, dict)
    first_component["decision_authority"] = True
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="schema validation failed"):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_relation_to_unknown_component(tmp_path: Path) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    relations = payload["relations"]
    assert isinstance(relations, list)
    first_relation = relations[0]
    assert isinstance(first_relation, dict)
    first_relation["to_component_id"] = "missing-component"
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown components"):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_duplicate_relation_semantics(tmp_path: Path) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    relations = payload["relations"]
    assert isinstance(relations, list)
    duplicate = dict(
        next(
            relation
            for relation in relations
            if relation["relation_id"] == "candidate-constrained-by-risk-assessment"
        )
    )
    duplicate["relation_id"] = "duplicate-candidate-risk-constraint"
    relations.append(duplicate)
    payload["relations"] = sorted(relations, key=lambda item: item["relation_id"])
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="logical architecture relation semantics must be unique",
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_unavailable_repository_reference(tmp_path: Path) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    components = payload["components"]
    assert isinstance(components, list)
    first_component = components[0]
    assert isinstance(first_component, dict)
    first_component["source_paths"] = ["src/ai4binance/missing.py"]
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="logical architecture repository references are unavailable",
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_loader_rejects_dependency_cycle(tmp_path: Path) -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    relations = payload["relations"]
    assert isinstance(relations, list)
    relations.append(
        {
            "relation_id": "core-architecture-depends-on-kaizen",
            "from_component_id": "core-architecture-framework",
            "to_component_id": "kaizen-quality-snapshot",
            "relation_type": "DEPENDS_ON",
        }
    )
    payload["relations"] = sorted(relations, key=lambda item: item["relation_id"])
    invalid_path = tmp_path / "registry.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="logical architecture dependency cycle detected",
    ):
        load_logical_architecture_registry(invalid_path, schema_root=ROOT / "schemas")


def test_runtime_conformance_proves_one_canonical_trade_decision_route() -> None:
    registry = load_logical_architecture_registry(REGISTRY_PATH)

    evidence = validate_runtime_architecture_conformance(registry, ROOT)

    assert evidence.trade_decision_contract_path == (
        "src/ai4binance/governance/dge_models.py"
    )
    assert evidence.trade_decision_producer_path == (
        "src/ai4binance/governance/dge_engine.py"
    )
    assert evidence.mandatory_dge_handoffs == (
        "risk_approved",
        "validation_approved",
    )


def test_runtime_conformance_rejects_alternative_trade_decision_producer(
    tmp_path: Path,
) -> None:
    registry = load_logical_architecture_registry(REGISTRY_PATH)
    _write_runtime_decision_sources(tmp_path)
    rogue_path = tmp_path / "src" / "ai4binance" / "agents" / "rogue_decision_agent.py"
    rogue_path.parent.mkdir(parents=True)
    rogue_path.write_text(
        "from ai4binance.governance.dge_models import TradeDecision as FinalDecision\n"
        "\n"
        "def decide():\n"
        "    return FinalDecision()\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=(
            r"unauthorized TradeDecision producer: "
            r"src/ai4binance/agents/rogue_decision_agent\.py"
        ),
    ):
        validate_runtime_architecture_conformance(registry, tmp_path)


@pytest.mark.parametrize("missing_handoff", ["risk_approved", "validation_approved"])
def test_runtime_conformance_rejects_missing_mandatory_dge_handoff(
    tmp_path: Path,
    missing_handoff: str,
) -> None:
    registry = load_logical_architecture_registry(REGISTRY_PATH)
    _write_runtime_decision_sources(tmp_path, missing_handoff=missing_handoff)

    with pytest.raises(
        ValueError,
        match=f"missing mandatory handoffs: {missing_handoff}",
    ):
        validate_runtime_architecture_conformance(registry, tmp_path)


def test_runtime_conformance_rejects_alias_as_parallel_contract(
    tmp_path: Path,
) -> None:
    registry = load_logical_architecture_registry(REGISTRY_PATH)
    _write_runtime_decision_sources(tmp_path)
    rogue_path = tmp_path / "src" / "ai4binance" / "agents" / "governed_alias.py"
    rogue_path.parent.mkdir(parents=True)
    rogue_path.write_text("class GovernedDecision:\n    pass\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="GovernedDecision compatibility alias cannot define a parallel contract",
    ):
        validate_runtime_architecture_conformance(registry, tmp_path)


def _write_runtime_decision_sources(
    repository_root: Path,
    *,
    missing_handoff: str | None = None,
) -> None:
    governance_root = repository_root / "src" / "ai4binance" / "governance"
    governance_root.mkdir(parents=True)
    (governance_root / "dge_models.py").write_text(
        "class TradeDecision:\n    pass\n\nGovernedDecision = TradeDecision\n",
        encoding="utf-8",
    )
    handoffs = ["risk_approved", "validation_approved"]
    handoffs.remove(missing_handoff) if missing_handoff is not None else None
    handoff_lines = "".join(f"    context.{name}\n" for name in handoffs)
    (governance_root / "dge_engine.py").write_text(
        "from ai4binance.governance.dge_models import GovernedDecision\n"
        "\n"
        "def decide(context):\n"
        f"{handoff_lines}"
        "    return GovernedDecision()\n",
        encoding="utf-8",
    )
