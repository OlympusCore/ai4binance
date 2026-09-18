"""AI4BINANCE Trust, Assurance & Governance Plane.

The plane is local, deterministic, and report-only. It maps Graph RAG,
XAI Evidence Graph, AI Ethics, AI risk, and security controls into a bounded
control catalog without installing external services or widening trading
authority.
"""

# ruff: noqa: E501,RUF001

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256


class TrustPlanePriority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class TrustPlaneControlStatus(StrEnum):
    ACTIVE_LOCAL = "ACTIVE_LOCAL"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    STAGED_RESEARCH_ONLY = "STAGED_RESEARCH_ONLY"


class TrustPlaneLayerCreationStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    STAGED_RESEARCH_ONLY = "STAGED_RESEARCH_ONLY"


class TrustPlaneStandard(StrEnum):
    ISO_IEC_42001 = "ISO/IEC 42001"
    ISO_IEC_23894 = "ISO/IEC 23894"
    NIST_AI_RMF = "NIST AI RMF"


class TrustPlaneCapability(StrEnum):
    GRAPH_RAG = "GRAPH_RAG"
    XAI_EVIDENCE_GRAPH = "XAI_EVIDENCE_GRAPH"
    AI_ETHICS = "AI_ETHICS"
    POLICY_AS_CODE = "POLICY_AS_CODE"
    UNCERTAINTY_ABSTENTION = "UNCERTAINTY_ABSTENTION"
    LINEAGE = "LINEAGE"
    VALIDATION_PROMOTION = "VALIDATION_PROMOTION"
    OBSERVABILITY = "OBSERVABILITY"
    SOURCE_TRUST = "SOURCE_TRUST"
    REPLAY = "REPLAY"
    DRIFT = "DRIFT"
    ADVERSARIAL_TESTING = "ADVERSARIAL_TESTING"
    SUPPLY_CHAIN = "SUPPLY_CHAIN"
    DLP = "DLP"


class TrustPlaneControlId(StrEnum):
    DECISION_PROVENANCE_LEDGER = "decision_provenance_ledger"
    POLICY_AS_CODE_ENGINE = "policy_as_code_engine"
    UNCERTAINTY_ABSTENTION_ENGINE = "uncertainty_abstention_engine"
    DATA_FEATURE_DECISION_LINEAGE = "data_feature_decision_lineage"
    SEMANTIC_CONTRACT_REGISTRY = "semantic_contract_registry"
    VALIDATION_PROMOTION_REGISTRY = "validation_promotion_registry"
    AI_OBSERVABILITY_OPENTELEMETRY = "ai_observability_opentelemetry"
    SOURCE_TRUST_CLAIM_VERIFICATION = "source_trust_claim_verification"
    TEMPORAL_CAUSAL_EVIDENCE_GRAPH = "temporal_causal_evidence_graph"
    COUNTERFACTUAL_XAI = "counterfactual_xai"
    RAG_EVALUATION_ENGINE = "rag_evaluation_engine"
    DIGITAL_TWIN_DETERMINISTIC_REPLAY = "digital_twin_deterministic_replay"
    CHAMPION_CHALLENGER_FRAMEWORK = "champion_challenger_framework"
    DRIFT_INTELLIGENCE = "drift_intelligence"
    ADVERSARIAL_RED_TEAM_ENGINE = "adversarial_red_team_engine"
    ASSURANCE_CASE_ENGINE = "assurance_case_engine"
    AI_FMEA_BOW_TIE_STPA = "ai_fmea_bow_tie_stpa"
    MEMORY_GOVERNANCE = "memory_governance"
    AI_SOFTWARE_SUPPLY_CHAIN_GUARD = "ai_software_supply_chain_guard"
    DATA_EGRESS_DLP_GUARD = "data_egress_dlp_guard"


_ALL_STANDARDS = (
    TrustPlaneStandard.ISO_IEC_42001,
    TrustPlaneStandard.ISO_IEC_23894,
    TrustPlaneStandard.NIST_AI_RMF,
)


@dataclass(frozen=True, slots=True)
class TrustPlaneControl:
    control_id: TrustPlaneControlId
    title: str
    contribution: str
    priority: TrustPlanePriority
    status: TrustPlaneControlStatus
    capabilities: tuple[TrustPlaneCapability, ...]
    standards: tuple[TrustPlaneStandard, ...]
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    action_refs: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.contribution.strip():
            raise ValueError("trust control title and contribution are required")
        if not self.capabilities:
            raise ValueError("trust control requires capabilities")
        _require_unique(
            "trust control capabilities",
            tuple(capability.value for capability in self.capabilities),
        )
        if not self.standards:
            raise ValueError("trust control requires standards")
        _require_unique(
            "trust control standards",
            tuple(standard.value for standard in self.standards),
        )
        if not self.evidence_refs:
            raise ValueError("trust control requires evidence")
        _require_unique("trust control evidence refs", self.evidence_refs)
        _require_unique("trust control blockers", self.blockers)
        _require_unique("trust control action refs", self.action_refs)
        if self.status is TrustPlaneControlStatus.ACTIVE_LOCAL and self.blockers:
            raise ValueError("active local trust control cannot carry blockers")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("trust controls cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "control_id": self.control_id.value,
            "title": self.title,
            "contribution": self.contribution,
            "priority": self.priority.value,
            "status": self.status.value,
            "capabilities": [capability.value for capability in self.capabilities],
            "standards": [standard.value for standard in self.standards],
            "evidence_refs": list(self.evidence_refs),
            "blockers": list(self.blockers),
            "action_refs": list(self.action_refs),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class TrustPlaneConditionalLayer:
    control_id: TrustPlaneControlId
    title: str
    priority: TrustPlanePriority
    requested: bool
    created: bool
    creation_status: TrustPlaneLayerCreationStatus
    required_evidence_refs: tuple[str, ...]
    provided_evidence_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    action_refs: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.priority is TrustPlanePriority.P0:
            raise ValueError("conditional trust layers are only for P1/P2 controls")
        if not self.title.strip():
            raise ValueError("conditional trust layer title is required")
        if not self.required_evidence_refs:
            raise ValueError("conditional trust layer requires evidence contract")
        _require_unique(
            "conditional trust layer required evidence refs",
            self.required_evidence_refs,
        )
        _require_unique(
            "conditional trust layer provided evidence refs",
            self.provided_evidence_refs,
        )
        _require_unique("conditional trust layer blockers", self.blockers)
        _require_unique("conditional trust layer action refs", self.action_refs)
        if self.created and self.creation_status is not (
            TrustPlaneLayerCreationStatus.STAGED_RESEARCH_ONLY
        ):
            raise ValueError("created conditional trust layers must be staged")
        if not self.requested and self.created:
            raise ValueError("unrequested conditional trust layers cannot be created")
        if (
            self.creation_status is TrustPlaneLayerCreationStatus.EVIDENCE_REQUIRED
            and not self.blockers
        ):
            raise ValueError("evidence-required trust layers must carry blockers")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("conditional trust layers cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "control_id": self.control_id.value,
            "title": self.title,
            "priority": self.priority.value,
            "requested": self.requested,
            "created": self.created,
            "creation_status": self.creation_status.value,
            "required_evidence_refs": list(self.required_evidence_refs),
            "provided_evidence_refs": list(self.provided_evidence_refs),
            "blockers": list(self.blockers),
            "action_refs": list(self.action_refs),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class TrustPlaneAssessment:
    plane_id: str
    controls: tuple[TrustPlaneControl, ...]
    conditional_layers: tuple[TrustPlaneConditionalLayer, ...] = ()
    external_services_enabled: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.plane_id.strip():
            raise ValueError("trust plane id is required")
        if not self.controls:
            raise ValueError("trust plane requires controls")
        _require_unique(
            "trust plane controls",
            tuple(control.control_id.value for control in self.controls),
        )
        _require_unique(
            "trust plane conditional layers",
            tuple(layer.control_id.value for layer in self.conditional_layers),
        )
        control_ids = {control.control_id for control in self.controls}
        for layer in self.conditional_layers:
            if layer.created and layer.control_id not in control_ids:
                raise ValueError("created conditional layer requires a control")
            if not layer.created and layer.control_id in control_ids:
                raise ValueError("uncreated conditional layer cannot have a control")
        if (
            self.external_services_enabled
            or self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "trust plane cannot authorize trading or external services"
            )

    @property
    def priority_counts(self) -> dict[str, int]:
        return {
            priority.value: sum(
                1 for control in self.controls if control.priority is priority
            )
            for priority in TrustPlanePriority
        }

    @property
    def status_counts(self) -> dict[str, int]:
        return {
            status.value: sum(
                1 for control in self.controls if control.status is status
            )
            for status in TrustPlaneControlStatus
        }

    @property
    def standard_coverage(self) -> dict[str, list[str]]:
        return {
            standard.value: [
                control.control_id.value
                for control in self.controls
                if standard in control.standards
            ]
            for standard in TrustPlaneStandard
        }

    @property
    def p0_control_ids(self) -> tuple[str, ...]:
        return tuple(
            control.control_id.value
            for control in self.controls
            if control.priority is TrustPlanePriority.P0
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        blocker_sources: tuple[
            TrustPlaneControl | TrustPlaneConditionalLayer,
            ...,
        ] = (*self.controls, *self.conditional_layers)
        return tuple(
            dict.fromkeys(
                blocker for item in blocker_sources for blocker in item.blockers
            )
        )

    @property
    def conditional_layer_counts(self) -> dict[str, int]:
        return {
            status.value: sum(
                1
                for layer in self.conditional_layers
                if layer.creation_status is status
            )
            for status in TrustPlaneLayerCreationStatus
        }

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "plane_id": self.plane_id,
            "framework": "AI4BINANCE_TRUST_ASSURANCE_GOVERNANCE_PLANE",
            "standards": [standard.value for standard in TrustPlaneStandard],
            "capabilities": [capability.value for capability in TrustPlaneCapability],
            "priority_counts": self.priority_counts,
            "status_counts": self.status_counts,
            "standard_coverage": self.standard_coverage,
            "p0_control_ids": list(self.p0_control_ids),
            "conditional_layer_counts": self.conditional_layer_counts,
            "blockers": list(self.blockers),
            "controls": [control.to_payload() for control in self.controls],
            "conditional_layers": [
                layer.to_payload() for layer in self.conditional_layers
            ],
            "external_services_enabled": False,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }
        payload["plane_hash"] = _stable_digest(payload)
        return payload


def build_default_trust_plane_assessment(
    *,
    evidence_refs: tuple[str, ...] = ("trust-plane-catalog",),
) -> TrustPlaneAssessment:
    """Return the full local control catalog requested for AI4BINANCE."""

    if not evidence_refs:
        raise ValueError("trust plane assessment requires evidence")
    _require_unique("trust plane assessment evidence refs", evidence_refs)
    return TrustPlaneAssessment(
        plane_id="trust-plane:ai4binance:v1",
        controls=_default_controls(evidence_refs),
    )


def build_conditional_trust_plane_assessment(
    *,
    evidence_refs: tuple[str, ...] = ("trust-plane-catalog",),
    requested_layers: tuple[TrustPlaneControlId, ...] = (),
    layer_evidence_refs: dict[TrustPlaneControlId, tuple[str, ...]] | None = None,
) -> TrustPlaneAssessment:
    """Build P0 always-on controls and P1/P2 only when request/evidence exists."""

    if not evidence_refs:
        raise ValueError("conditional trust plane assessment requires evidence")
    _require_unique("conditional trust plane evidence refs", evidence_refs)
    _require_unique(
        "conditional trust plane requested layers",
        tuple(layer.value for layer in requested_layers),
    )
    available = {
        control.control_id: control for control in _default_controls(evidence_refs)
    }
    _validate_requested_layers(requested_layers, available)
    layer_evidence = layer_evidence_refs or {}
    controls: list[TrustPlaneControl] = [
        control
        for control in available.values()
        if control.priority is TrustPlanePriority.P0
    ]
    conditional_layers: list[TrustPlaneConditionalLayer] = []
    for control in available.values():
        if control.priority is TrustPlanePriority.P0:
            continue
        provided = layer_evidence.get(control.control_id, ())
        if provided:
            _require_unique(
                f"conditional trust layer evidence {control.control_id.value}",
                provided,
            )
        requested = control.control_id in requested_layers
        created = requested and bool(provided)
        status = TrustPlaneLayerCreationStatus.NOT_REQUESTED
        blockers: tuple[str, ...] = ()
        action_refs: tuple[str, ...] = (f"request:{control.control_id.value}",)
        if requested and not provided:
            status = TrustPlaneLayerCreationStatus.EVIDENCE_REQUIRED
            blockers = (
                "ADVANCED_TRUST_LAYER_EVIDENCE_REQUIRED",
                *control.blockers,
            )
            action_refs = (
                *action_refs,
                *control.action_refs,
            )
        elif created:
            status = TrustPlaneLayerCreationStatus.STAGED_RESEARCH_ONLY
            blockers = (
                "ADVANCED_TRUST_LAYER_RESEARCH_ONLY",
                *(
                    blocker
                    for blocker in control.blockers
                    if blocker.endswith("_RESEARCH_ONLY")
                ),
            )
            action_refs = (
                "create:conditional-trust-layer",
                *control.action_refs,
            )
            controls.append(
                _control(
                    control.control_id,
                    control.title,
                    control.contribution,
                    control.priority,
                    TrustPlaneControlStatus.STAGED_RESEARCH_ONLY,
                    control.capabilities,
                    (*evidence_refs, *provided),
                    blockers=blockers,
                    action_refs=action_refs,
                )
            )
        conditional_layers.append(
            TrustPlaneConditionalLayer(
                control_id=control.control_id,
                title=control.title,
                priority=control.priority,
                requested=requested,
                created=created,
                creation_status=status,
                required_evidence_refs=_required_evidence_refs_for(control.control_id),
                provided_evidence_refs=provided,
                blockers=blockers,
                action_refs=action_refs,
            )
        )
    return TrustPlaneAssessment(
        plane_id="trust-plane:ai4binance:v1:conditional",
        controls=tuple(controls),
        conditional_layers=tuple(conditional_layers),
    )


def _default_controls(
    evidence_refs: tuple[str, ...],
) -> tuple[TrustPlaneControl, ...]:
    local = TrustPlaneControlStatus.ACTIVE_LOCAL
    staged = TrustPlaneControlStatus.STAGED_RESEARCH_ONLY
    evidence_required = TrustPlaneControlStatus.EVIDENCE_REQUIRED
    return (
        _control(
            TrustPlaneControlId.DECISION_PROVENANCE_LEDGER,
            "Decision Provenance Ledger",
            "Maintains the full decision lineage and hashable evidence package.",
            TrustPlanePriority.P0,
            local,
            (TrustPlaneCapability.XAI_EVIDENCE_GRAPH,),
            evidence_refs,
            action_refs=("emit:decision-provenance-record",),
        ),
        _control(
            TrustPlaneControlId.POLICY_AS_CODE_ENGINE,
            "Policy-as-Code Engine",
            "Applies risk and governance rules as deterministic policy evaluation.",
            TrustPlanePriority.P0,
            local,
            (TrustPlaneCapability.POLICY_AS_CODE,),
            evidence_refs,
            action_refs=("emit:policy-evaluation-record",),
        ),
        _control(
            TrustPlaneControlId.UNCERTAINTY_ABSTENTION_ENGINE,
            "Uncertainty & Abstention Engine",
            "Preserves the WAIT/NO_TRADE boundary and abstention record under uncertainty.",
            TrustPlanePriority.P0,
            local,
            (
                TrustPlaneCapability.UNCERTAINTY_ABSTENTION,
                TrustPlaneCapability.AI_ETHICS,
            ),
            evidence_refs,
            action_refs=("emit:uncertainty-assessment-record",),
        ),
        _control(
            TrustPlaneControlId.DATA_FEATURE_DECISION_LINEAGE,
            "data/Feature/Decision Lineage",
            "Tracks the point-in-time chain between data, features, snapshots, and decisions.",
            TrustPlanePriority.P0,
            local,
            (TrustPlaneCapability.LINEAGE,),
            evidence_refs,
            action_refs=("check:validation-integrity",),
        ),
        _control(
            TrustPlaneControlId.SEMANTIC_CONTRACT_REGISTRY,
            "Semantic Contract Registry",
            "Requires the field contract for required and forbidden agent/audit outputs.",
            TrustPlanePriority.P0,
            local,
            (TrustPlaneCapability.XAI_EVIDENCE_GRAPH, TrustPlaneCapability.AI_ETHICS),
            evidence_refs,
            action_refs=("emit:semantic-contract-record",),
        ),
        _control(
            TrustPlaneControlId.VALIDATION_PROMOTION_REGISTRY,
            "Validation & Promotion Registry",
            "Manages the strategy, model, and parameter lifecycle through the paper-only promotion board.",
            TrustPlanePriority.P0,
            local,
            (TrustPlaneCapability.VALIDATION_PROMOTION,),
            evidence_refs,
            action_refs=("check:promotion-board",),
        ),
        _control(
            TrustPlaneControlId.AI_OBSERVABILITY_OPENTELEMETRY,
            "AI Observability / OpenTelemetry",
            "Tracks agent and workflow behavior with a local trace/span contract; external collectors are disabled.",
            TrustPlanePriority.P0,
            local,
            (TrustPlaneCapability.OBSERVABILITY,),
            evidence_refs,
            action_refs=("emit:local-observability-event",),
        ),
        _control(
            TrustPlaneControlId.SOURCE_TRUST_CLAIM_VERIFICATION,
            "Source Trust & Claim Verification",
            "Constrains news, RAG, and LLM evidence with citations, freshness, and source-trust records.",
            TrustPlanePriority.P0,
            local,
            (TrustPlaneCapability.GRAPH_RAG, TrustPlaneCapability.SOURCE_TRUST),
            evidence_refs,
            action_refs=("check:rag-source-citations",),
        ),
        _control(
            TrustPlaneControlId.DATA_EGRESS_DLP_GUARD,
            "Data Egress / DLP Guard",
            "Constrains GitHub, cloud, log, and output data leakage through privacy and DLP guards.",
            TrustPlanePriority.P0,
            local,
            (TrustPlaneCapability.DLP, TrustPlaneCapability.AI_ETHICS),
            evidence_refs,
            action_refs=("check:privacy-leak-guard", "check:security-core-dlp"),
        ),
        _control(
            TrustPlaneControlId.TEMPORAL_CAUSAL_EVIDENCE_GRAPH,
            "Temporal/Causal Evidence Graph",
            "Stages temporal and causal links as separate graph relationships.",
            TrustPlanePriority.P1,
            staged,
            (TrustPlaneCapability.XAI_EVIDENCE_GRAPH, TrustPlaneCapability.LINEAGE),
            evidence_refs,
            blockers=("TEMPORAL_CAUSAL_GRAPH_RESEARCH_ONLY",),
            action_refs=("stage:temporal-causal-evidence-graph",),
        ),
        _control(
            TrustPlaneControlId.COUNTERFACTUAL_XAI,
            "Counterfactual XAI",
            "Stages research-only analysis of which changes would alter the decision.",
            TrustPlanePriority.P1,
            staged,
            (TrustPlaneCapability.XAI_EVIDENCE_GRAPH,),
            evidence_refs,
            blockers=("COUNTERFACTUAL_XAI_RESEARCH_ONLY",),
            action_refs=("stage:counterfactual-xai",),
        ),
        _control(
            TrustPlaneControlId.RAG_EVALUATION_ENGINE,
            "RAG Evaluation Engine",
            "Stages Graph RAG precision, freshness, contradiction, and faithfulness measurement.",
            TrustPlanePriority.P1,
            staged,
            (TrustPlaneCapability.GRAPH_RAG, TrustPlaneCapability.SOURCE_TRUST),
            evidence_refs,
            blockers=("RAG_EVALUATION_FIXTURE_REQUIRED",),
            action_refs=("stage:rag-evaluation-engine",),
        ),
        _control(
            TrustPlaneControlId.DIGITAL_TWIN_DETERMINISTIC_REPLAY,
            "Digital Twin / Deterministic Replay",
            "Replays historical decisions exactly through the event journal and deterministic replay.",
            TrustPlanePriority.P1,
            evidence_required,
            (TrustPlaneCapability.REPLAY,),
            evidence_refs,
            blockers=("APPLICATION_REPLAY_WIRING_REQUIRED",),
            action_refs=("check:event-journal-replay",),
        ),
        _control(
            TrustPlaneControlId.CHAMPION_CHALLENGER_FRAMEWORK,
            "Champion–Challenger Framework",
            "Compares new algorithms silently, paper-only, and without promotion authority.",
            TrustPlanePriority.P1,
            staged,
            (TrustPlaneCapability.VALIDATION_PROMOTION,),
            evidence_refs,
            blockers=("CHAMPION_CHALLENGER_RESEARCH_ONLY",),
            action_refs=("stage:champion-challenger",),
        ),
        _control(
            TrustPlaneControlId.DRIFT_INTELLIGENCE,
            "Drift Intelligence",
            "Links data, regime, model, and strategy drift signals to audit triggers.",
            TrustPlanePriority.P1,
            evidence_required,
            (TrustPlaneCapability.DRIFT,),
            evidence_refs,
            blockers=("DRIFT_BASELINE_EVIDENCE_REQUIRED",),
            action_refs=("check:performance-drift-audit",),
        ),
        _control(
            TrustPlaneControlId.ADVERSARIAL_RED_TEAM_ENGINE,
            "Adversarial / Red-Team Engine",
            "Tests poisoning, prompt injection, and agent abuse scenarios fail-closed.",
            TrustPlanePriority.P1,
            staged,
            (TrustPlaneCapability.ADVERSARIAL_TESTING, TrustPlaneCapability.AI_ETHICS),
            evidence_refs,
            blockers=("RED_TEAM_SCENARIOS_REQUIRED",),
            action_refs=("stage:adversarial-red-team",),
        ),
        _control(
            TrustPlaneControlId.ASSURANCE_CASE_ENGINE,
            "Assurance Case Engine",
            "Explains why a change is safe through an evidence tree.",
            TrustPlanePriority.P1,
            staged,
            (TrustPlaneCapability.XAI_EVIDENCE_GRAPH, TrustPlaneCapability.AI_ETHICS),
            evidence_refs,
            blockers=("ASSURANCE_CASE_TEMPLATE_REQUIRED",),
            action_refs=("stage:assurance-case-engine",),
        ),
        _control(
            TrustPlaneControlId.AI_FMEA_BOW_TIE_STPA,
            "AI-FMEA / Bow-Tie / STPA",
            "Stages systematic failure, hazard, and loss-of-control analysis.",
            TrustPlanePriority.P1,
            staged,
            (TrustPlaneCapability.AI_ETHICS, TrustPlaneCapability.ADVERSARIAL_TESTING),
            evidence_refs,
            blockers=("SYSTEM_THEORETIC_HAZARD_ANALYSIS_REQUIRED",),
            action_refs=("stage:ai-fmea-bow-tie-stpa",),
        ),
        _control(
            TrustPlaneControlId.MEMORY_GOVERNANCE,
            "Memory Governance",
            "Constrains agent and RAG memory contamination and authority leakage.",
            TrustPlanePriority.P2,
            evidence_required,
            (TrustPlaneCapability.GRAPH_RAG, TrustPlaneCapability.AI_ETHICS),
            evidence_refs,
            blockers=("MEMORY_CORPUS_POLICY_EVIDENCE_REQUIRED",),
            action_refs=("check:rag-memory-governance",),
        ),
        _control(
            TrustPlaneControlId.AI_SOFTWARE_SUPPLY_CHAIN_GUARD,
            "AI/Software Supply Chain Guard",
            "Dependency, model, dataset ve skill supply-chain risklerini denetler.",
            TrustPlanePriority.P2,
            evidence_required,
            (TrustPlaneCapability.SUPPLY_CHAIN,),
            evidence_refs,
            blockers=("SUPPLY_CHAIN_ATTESTATION_REQUIRED",),
            action_refs=("check:supply-chain-guard",),
        ),
    )


def _validate_requested_layers(
    requested_layers: tuple[TrustPlaneControlId, ...],
    available: dict[TrustPlaneControlId, TrustPlaneControl],
) -> None:
    for control_id in requested_layers:
        control = available.get(control_id)
        if control is None:
            raise ValueError("requested trust layer is unknown")
        if control.priority is TrustPlanePriority.P0:
            raise ValueError("P0 trust controls are always-on and cannot be requested")


def _required_evidence_refs_for(control_id: TrustPlaneControlId) -> tuple[str, ...]:
    mapping = {
        TrustPlaneControlId.TEMPORAL_CAUSAL_EVIDENCE_GRAPH: (
            "temporal-graph-design",
            "causal-relation-contract",
        ),
        TrustPlaneControlId.COUNTERFACTUAL_XAI: (
            "counterfactual-fixture",
            "decision-sensitivity-report",
        ),
        TrustPlaneControlId.RAG_EVALUATION_ENGINE: (
            "rag-eval-fixture",
            "citation-faithfulness-report",
        ),
        TrustPlaneControlId.DIGITAL_TWIN_DETERMINISTIC_REPLAY: (
            "event-journal-replay-report",
            "decision-replay-fixture",
        ),
        TrustPlaneControlId.CHAMPION_CHALLENGER_FRAMEWORK: (
            "champion-baseline",
            "challenger-shadow-report",
        ),
        TrustPlaneControlId.DRIFT_INTELLIGENCE: (
            "drift-baseline",
            "regime-drift-thresholds",
        ),
        TrustPlaneControlId.ADVERSARIAL_RED_TEAM_ENGINE: (
            "red-team-scenarios",
            "abuse-case-report",
        ),
        TrustPlaneControlId.ASSURANCE_CASE_ENGINE: (
            "assurance-case-template",
            "safety-claim-evidence",
        ),
        TrustPlaneControlId.AI_FMEA_BOW_TIE_STPA: (
            "hazard-analysis-template",
            "loss-control-map",
        ),
        TrustPlaneControlId.MEMORY_GOVERNANCE: (
            "memory-corpus-policy",
            "memory-contamination-check",
        ),
        TrustPlaneControlId.AI_SOFTWARE_SUPPLY_CHAIN_GUARD: (
            "dependency-attestation",
            "model-dataset-provenance",
        ),
    }
    return mapping[control_id]


def _control(
    control_id: TrustPlaneControlId,
    title: str,
    contribution: str,
    priority: TrustPlanePriority,
    status: TrustPlaneControlStatus,
    capabilities: tuple[TrustPlaneCapability, ...],
    evidence_refs: tuple[str, ...],
    *,
    blockers: tuple[str, ...] = (),
    action_refs: tuple[str, ...] = (),
) -> TrustPlaneControl:
    return TrustPlaneControl(
        control_id=control_id,
        title=title,
        contribution=contribution,
        priority=priority,
        status=status,
        capabilities=capabilities,
        standards=_ALL_STANDARDS,
        evidence_refs=evidence_refs,
        blockers=blockers,
        action_refs=action_refs,
    )


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


def _stable_digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()
