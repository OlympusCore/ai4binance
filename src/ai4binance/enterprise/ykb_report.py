"""YKB-friendly executive brief assembled from governed runtime evidence."""

# ruff: noqa: E501

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from ai4binance.config import Settings
from ai4binance.enterprise.agent_stack import run_agent_stack_audit
from ai4binance.enterprise.vnext_gap_audit import build_vnext_gap_audit
from ai4binance.external_intel.core.models import RetrievedDocument
from ai4binance.external_intel.technology import analyze_technology
from ai4binance.governance import (
    DecisionGovernanceEngine,
    DgeGovernanceContext,
    DgeMarketAction,
    DgeTradeCandidate,
    GovernedDecision,
)
from ai4binance.governance.adapters import (
    DgeEvaluationRecord,
    evaluate_recovery_radar_with_dge,
)
from ai4binance.governance.audit import (
    persist_dge_decision_event,
    persist_dge_evaluation_record,
)
from ai4binance.internal_radar import load_internal_radar_latest
from ai4binance.ops.auto_audit_loop import AutoAuditLoopResult, run_auto_audit_loop
from ai4binance.ops.user_reports import (
    canonical_system_root,
    render_professional_summary,
    user_report_paths,
)
from ai4binance.portfolio.opportunity_recovery import (
    OpportunityRecoveryRadar,
    build_opportunity_recovery_radar,
)
from ai4binance.reporting import to_primitive
from ai4binance.research.virtual_market import (
    AcceptanceStatus,
    MarketAcceptanceResult,
    SystemResearchAcceptance,
    VirtualMarket,
    derive_virtual_runtime_priority_signal,
)
from ai4binance.storage import (
    JsonlAuditStore,
    read_bounded_jsonl_tail,
    write_json_object_verified,
)
from ai4binance.strategies.rules import setup_pattern_type
from ai4binance.validation.summary import ValidationSummaryReader

_ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
_YKB_REPORT_STAMP_RE = re.compile(r"^ykb_report_(\d{8}T\d{6})_tr\.md$")
_SPOT_INVENTORY_REPORTING_THRESHOLD_USDT = Decimal("2")
_OPPORTUNITY_RADAR_SCOPE_RULE = (
    "Stablecoin, wrapped ve kaldiracli tokenlar haric Binance Spot/Futures "
    "koin evreni surekli radar kapsamindadir; Wallet/Value, dust veya "
    "envanter heatmap esigi firsat radarini filtreleyemez."
)


@dataclass(frozen=True, slots=True)
class YkbSpotAssetRow:
    asset: str
    asset_class: str
    free_state: str
    locked_state: str
    value_bucket: str
    liquidity_bucket: str
    value_report_state: str = "VALUE_UNKNOWN_REPORTABLE"
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for value in (
            self.asset,
            self.asset_class,
            self.free_state,
            self.locked_state,
            self.value_bucket,
            self.liquidity_bucket,
            self.value_report_state,
        ):
            if not value.strip():
                raise ValueError("YKB spot asset row identity is required")
        _require_unique_nonblank("YKB spot asset blockers", self.blockers)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("YKB spot asset row cannot authorize execution")


@dataclass(frozen=True, slots=True)
class YkbFuturesPositionRow:
    symbol: str
    position_side: str
    exposure_bucket: str
    margin_state: str
    risk_state: str
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for value in (
            self.symbol,
            self.position_side,
            self.exposure_bucket,
            self.margin_state,
            self.risk_state,
        ):
            if not value.strip():
                raise ValueError("YKB futures position row identity is required")
        _require_unique_nonblank("YKB futures position blockers", self.blockers)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("YKB futures position row cannot authorize execution")


@dataclass(frozen=True, slots=True)
class YkbOpenOrderRow:
    market: str
    symbol: str
    side: str
    order_type: str
    status: str
    locked_liquidity_bucket: str
    stale_state: str
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for value in (
            self.market,
            self.symbol,
            self.side,
            self.order_type,
            self.status,
            self.locked_liquidity_bucket,
            self.stale_state,
        ):
            if not value.strip():
                raise ValueError("YKB open order row identity is required")
        _require_unique_nonblank("YKB open order blockers", self.blockers)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("YKB open order row cannot authorize execution")


@dataclass(frozen=True, slots=True)
class YkbInventoryHeatmapRow:
    inventory_group: str
    concentration_bucket: str
    liquidity_bucket: str
    action_hint: str
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for value in (
            self.inventory_group,
            self.concentration_bucket,
            self.liquidity_bucket,
            self.action_hint,
        ):
            if not value.strip():
                raise ValueError("YKB inventory heatmap row identity is required")
        _require_unique_nonblank("YKB inventory heatmap blockers", self.blockers)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("YKB inventory heatmap row cannot authorize execution")


@dataclass(frozen=True, slots=True)
class YkbFinancialSituation:
    status: str
    spot_asset_count: int
    futures_position_count: int
    reconciliation_status: str
    value_disclosure: str
    known_value_present: bool
    blockers: tuple[str, ...]
    open_order_count: int = 0
    spot_assets: tuple[YkbSpotAssetRow, ...] = ()
    futures_positions: tuple[YkbFuturesPositionRow, ...] = ()
    open_orders: tuple[YkbOpenOrderRow, ...] = ()
    inventory_heatmap: tuple[YkbInventoryHeatmapRow, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.spot_asset_count < 0
            or self.futures_position_count < 0
            or self.open_order_count < 0
        ):
            raise ValueError("YKB financial counts cannot be negative")
        if self.value_disclosure != "REDACTED_SUMMARY_ONLY":
            raise ValueError("YKB financial report must redact raw values")
        _require_unique_nonblank("YKB financial blockers", self.blockers)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("YKB financial situation cannot authorize execution")


@dataclass(frozen=True, slots=True)
class YkbOpportunityBrief:
    opportunity_id: str
    headline: str
    market: str
    symbol: str
    timeframe: str
    setup_name: str
    requested_action: str
    governed_action: str
    trade_side: str
    leverage: str
    dge_status: str
    score: Decimal
    confidence: Decimal
    target_risk_reward: Decimal
    financial_fit: str
    funding_requirement: str
    blockers: tuple[str, ...]
    next_safe_action: str
    evidence_refs: tuple[str, ...]
    required_capital_bucket: str = "UNKNOWN"
    free_quote_sufficiency: str = "UNKNOWN"
    manual_liquidity_preparation: str = "MANUAL_REVIEW_REQUIRED"
    external_capital_policy: str = "NO_EXTERNAL_CAPITAL_ALLOWED"
    conversion_or_transfer_policy: str = "AUTO_MONEY_MOVEMENT_BLOCKED"
    funding_blockers: tuple[str, ...] = ()
    why_now: tuple[str, ...] = ()
    confirmation_requirements: tuple[str, ...] = ()
    promotion_requirements: tuple[str, ...] = ()
    execution_blockers: tuple[str, ...] = ()
    next_evidence_action: str = "KEEP_RESEARCH_RADAR_RUNNING"
    improvement_candidate_hint: str = "HALT_REVIEW_PENDING"
    halt_reset_criteria: tuple[str, ...] = ()
    halt_review_ref: str = "ARTIFACT_REF_NOT_PUBLISHED"
    halt_review_artifact_path: str = "ARTIFACT_PATH_UNRESOLVED"
    halt_root_cause_summary: str = "ROOT_CAUSE_SUMMARY_UNAVAILABLE"
    halt_next_bounded_experiment: str = "NEXT_BOUNDED_EXPERIMENT_UNAVAILABLE"
    entry: str = "PENDING_VALIDATED_LEVEL"
    stop_loss: str = "PENDING_VALIDATED_LEVEL"
    take_profit_1: str = "PENDING_VALIDATED_LEVEL"
    take_profit_2: str = "PENDING_VALIDATED_LEVEL"
    take_profit_3: str = "PENDING_VALIDATED_LEVEL"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    pattern_type: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.opportunity_id,
            self.headline,
            self.market,
            self.symbol,
            self.timeframe,
            self.setup_name,
            self.requested_action,
            self.governed_action,
            self.trade_side,
            self.leverage,
            self.dge_status,
            self.financial_fit,
            self.funding_requirement,
            self.next_safe_action,
            self.required_capital_bucket,
            self.free_quote_sufficiency,
            self.manual_liquidity_preparation,
            self.external_capital_policy,
            self.conversion_or_transfer_policy,
            self.next_evidence_action,
            self.improvement_candidate_hint,
            self.halt_review_ref,
            self.halt_review_artifact_path,
            self.halt_root_cause_summary,
            self.halt_next_bounded_experiment,
        )
        if any(not item.strip() for item in required):
            raise ValueError("YKB opportunity identity is required")
        if not Decimal("0") <= self.score <= Decimal("100"):
            raise ValueError("YKB opportunity score must be 0..100")
        if not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("YKB opportunity confidence must be 0..1")
        if self.target_risk_reward <= Decimal("0"):
            raise ValueError("YKB opportunity risk/reward must be positive")
        _require_unique_nonblank("YKB opportunity blockers", self.blockers)
        _require_unique_nonblank("YKB opportunity evidence refs", self.evidence_refs)
        _require_unique_nonblank(
            "YKB opportunity funding blockers",
            self.funding_blockers,
        )
        for name, values in (
            ("YKB opportunity why-now evidence", self.why_now),
            (
                "YKB opportunity confirmation requirements",
                self.confirmation_requirements,
            ),
            ("YKB opportunity promotion requirements", self.promotion_requirements),
            ("YKB opportunity execution blockers", self.execution_blockers),
            ("YKB opportunity halt reset criteria", self.halt_reset_criteria),
        ):
            _require_unique_nonblank(name, values)
        for value in (
            self.entry,
            self.stop_loss,
            self.take_profit_1,
            self.take_profit_2,
            self.take_profit_3,
        ):
            if not value.strip():
                raise ValueError("YKB opportunity trade plan values are required")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("YKB opportunity brief cannot authorize execution")
        if self.pattern_type is not None and not self.pattern_type.strip():
            raise ValueError("YKB opportunity pattern_type cannot be blank")


@dataclass(frozen=True, slots=True)
class YkbContextItem:
    category: str
    title: str
    impact: str
    recommendation: str
    source: str
    source_url: str
    as_of: str
    symbol: str = "MARKET_WIDE"
    system_benefit: str = "YKB_RESEARCH_VISIBILITY_IMPROVES"
    system_tradeoff: str = "SOURCE_VALIDATION_AND_LOCAL_TEST_REQUIRED"
    ykb_approval_hint: str = "APPROVE_RESEARCH_ONLY_REVIEW_NOT_PRODUCTION"
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for value in (
            self.category,
            self.title,
            self.impact,
            self.recommendation,
            self.source,
            self.source_url,
            self.as_of,
            self.symbol,
            self.system_benefit,
            self.system_tradeoff,
            self.ykb_approval_hint,
        ):
            if not value.strip():
                raise ValueError("YKB context item identity is required")
        _require_unique_nonblank("YKB context blockers", self.blockers)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("YKB context item cannot authorize execution")


@dataclass(frozen=True, slots=True)
class YkbValidationDigest:
    symbol: str
    status: str
    latest_run_id: str
    timeframe: str
    playbook: str
    promotion_status: str
    run_created_at: str
    metrics: tuple[str, ...]
    tuning_parameters: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status_boundary: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for value in (
            self.symbol,
            self.status,
            self.latest_run_id,
            self.timeframe,
            self.playbook,
            self.promotion_status,
            self.run_created_at,
        ):
            if not value.strip():
                raise ValueError("YKB validation digest identity is required")
        for values in (
            self.metrics,
            self.tuning_parameters,
            self.artifact_refs,
            self.blockers,
        ):
            _require_unique_nonblank("YKB validation digest lists", values)
        if (
            self.execution_allowed
            or self.promotion_status_boundary != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("YKB validation digest cannot authorize execution")


@dataclass(frozen=True, slots=True)
class YkbWalletPositionManagement:
    status: str
    recommendation: str
    spot_asset_count: int
    futures_position_count: int
    open_position_policy: str
    blockers: tuple[str, ...]
    spot_open_order_count: int = 0
    futures_open_order_count: int = 0
    funding_recommendation: str = "MANUAL_REVIEW_REQUIRED"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.spot_asset_count < 0
            or self.futures_position_count < 0
            or self.spot_open_order_count < 0
            or self.futures_open_order_count < 0
        ):
            raise ValueError("YKB wallet management counts cannot be negative")
        for value in (
            self.status,
            self.recommendation,
            self.open_position_policy,
            self.funding_recommendation,
        ):
            if not value.strip():
                raise ValueError("YKB wallet management identity is required")
        _require_unique_nonblank("YKB wallet management blockers", self.blockers)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("YKB wallet management cannot authorize execution")


@dataclass(frozen=True, slots=True)
class SemiAutoControlManagement:
    mode: str
    workflow_pattern: str
    blocker_resolution_order_status: str
    risk_oos_live_gate_status: str
    next_management_action: str
    loop_steps: tuple[str, ...]
    human_approval_gates: tuple[str, ...]
    stopping_rule: str
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.mode != "SEMI_AUTO_CONTROL_MANAGEMENT":
            raise ValueError("semi-auto management mode is invalid")
        if self.blocker_resolution_order_status not in {
            "PENDING_YKB_APPROVAL",
            "APPROVED_BY_YKB",
        }:
            raise ValueError("semi-auto blocker order approval status is invalid")
        if self.risk_oos_live_gate_status != ("LOCKED_UNTIL_RISK_AND_OOS_EVIDENCE"):
            raise ValueError("semi-auto risk/OOS live gate is invalid")
        if not self.next_management_action.strip():
            raise ValueError("semi-auto management action is required")
        if not self.loop_steps or not self.human_approval_gates:
            raise ValueError("semi-auto management requires controls")
        for values in (self.loop_steps, self.human_approval_gates, self.blockers):
            _require_unique_nonblank("semi-auto control lists", values)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("semi-auto management cannot authorize execution")


@dataclass(frozen=True, slots=True)
class _FundingRecommendation:
    funding_requirement: str
    required_capital_bucket: str
    free_quote_sufficiency: str
    manual_liquidity_preparation: str
    external_capital_policy: str
    conversion_or_transfer_policy: str
    funding_blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class YkbExecutiveBrief:
    report_id: str
    observed_at: datetime
    status: str
    executive_summary: str
    auto_audit_status: str
    auto_audit_ref: str
    auto_audit_recommendations: tuple[str, ...]
    agent_audit_status: str
    agent_audit_ref: str
    agent_audit_recommendations: tuple[str, ...]
    technology_opportunities: tuple[YkbContextItem, ...]
    important_context: tuple[YkbContextItem, ...]
    latest_validation: YkbValidationDigest
    financial_situation: YkbFinancialSituation
    wallet_position_management: YkbWalletPositionManagement
    opportunities: tuple[YkbOpportunityBrief, ...]
    dge_decisions: tuple[GovernedDecision, ...]
    semi_auto_control: SemiAutoControlManagement
    decision_request: str
    blockers: tuple[str, ...]
    json_path: Path
    markdown_path: Path
    latest_json_path: Path
    latest_markdown_path: Path = Path(".")
    private_financial_json_path: Path = Path(".")
    private_financial_markdown_path: Path = Path(".")
    private_financial_report_policy: str = "LOCAL_PRIVATE_ANNEX_ONLY"
    private_financial_cloud_share_allowed: bool = False
    recovery_radar_status: str = "NOT_REQUESTED"
    recovery_radar_ref: str = ""
    vnext_gap_status: str = "NOT_REQUESTED"
    vnext_gap_ref: str = ""
    vnext_gap_top_gaps: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.report_id.strip() or not self.executive_summary.strip():
            raise ValueError("YKB brief identity is required")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("YKB brief timestamp must be timezone-aware")
        if not self.decision_request.strip():
            raise ValueError("YKB brief decision request is required")
        if self.private_financial_report_policy != "LOCAL_PRIVATE_ANNEX_ONLY":
            raise ValueError("YKB private financial report policy is invalid")
        if self.private_financial_cloud_share_allowed:
            raise ValueError("YKB private financial report cannot be cloud shared")
        _require_unique_nonblank("YKB brief blockers", self.blockers)
        _require_unique_nonblank("YKB vNext top gaps", self.vnext_gap_top_gaps)
        _require_unique_nonblank(
            "YKB auto-audit recommendations",
            self.auto_audit_recommendations,
        )
        _require_unique_nonblank(
            "YKB agent-audit recommendations",
            self.agent_audit_recommendations,
        )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("YKB brief cannot authorize execution")

    def to_payload(self) -> dict[str, object]:
        serialized_opportunities = _serialized_opportunity_payloads(
            self.opportunities,
            validation=self.latest_validation,
        )
        virtual_runtime_evidence = _virtual_runtime_evidence_snapshot(
            self.json_path.parent.parent.parent,
        )
        internal_radar = _internal_radar_payload(self)
        return {
            "command": "ykb-report",
            "report_id": self.report_id,
            "observed_at": self.observed_at.isoformat(),
            "status": self.status,
            "executive_summary": self.executive_summary,
            "auto_audit_status": self.auto_audit_status,
            "auto_audit_ref": self.auto_audit_ref,
            "auto_audit_recommendations": list(self.auto_audit_recommendations),
            "agent_audit_status": self.agent_audit_status,
            "agent_audit_ref": self.agent_audit_ref,
            "agent_audit_recommendations": list(self.agent_audit_recommendations),
            "technology_opportunities": [
                to_primitive(item) for item in self.technology_opportunities
            ],
            "important_context": [
                to_primitive(item) for item in self.important_context
            ],
            "internal_radar": internal_radar,
            "latest_validation": to_primitive(self.latest_validation),
            "virtual_runtime_evidence": virtual_runtime_evidence,
            "virtual_runtime_priority_signal": _virtual_runtime_priority_signal(
                virtual_runtime_evidence
            ),
            "financial_situation": to_primitive(self.financial_situation),
            "wallet_position_management": to_primitive(self.wallet_position_management),
            "opportunities": serialized_opportunities,
            "opportunity_funnel": _opportunity_funnel_payload(
                self.opportunities,
                self.latest_validation,
            ),
            "spot_opportunities": [
                item
                for item in serialized_opportunities
                if str(item["market"]).upper() == "SPOT"
            ],
            "futures_opportunities": [
                item
                for item in serialized_opportunities
                if "FUTURES" in str(item["market"]).upper()
            ],
            "dge_decisions": [to_primitive(item) for item in self.dge_decisions],
            "semi_auto_control": to_primitive(self.semi_auto_control),
            "recovery_radar_status": self.recovery_radar_status,
            "recovery_radar_ref": self.recovery_radar_ref,
            "vnext_gap_status": self.vnext_gap_status,
            "vnext_gap_ref": self.vnext_gap_ref,
            "vnext_gap_top_gaps": list(self.vnext_gap_top_gaps),
            "decision_request": self.decision_request,
            "blockers": list(self.blockers),
            "json_path": str(self.json_path),
            "markdown_path": str(self.markdown_path),
            "latest_json_path": str(self.latest_json_path),
            "latest_markdown_path": str(self.latest_markdown_path),
            "private_financial_report": {
                "json_path": str(self.private_financial_json_path),
                "markdown_path": str(self.private_financial_markdown_path),
                "policy": self.private_financial_report_policy,
                "cloud_share_allowed": self.private_financial_cloud_share_allowed,
                "blockers": [
                    "NO_GITHUB_CLOUD_SHARE",
                    "LOCAL_YKB_ONLY",
                    "BINANCE_FINANCIAL_VALUES_PRIVATE",
                ],
            },
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


PortfolioPayloadBuilder = Callable[[Settings], dict[str, object]]
OpportunitiesPayloadBuilder = Callable[[Settings, str | None], dict[str, object]]
AutoAuditRunner = Callable[..., AutoAuditLoopResult]


def build_ykb_executive_brief(
    settings: Settings,
    *,
    repository_root: Path | None = None,
    symbol: str | None = None,
    use_local_qwen: bool = False,
    max_auto_audit_cycles: int = 1,
    interval_seconds: float = 0.0,
    blocker_resolution_order_approved: bool = False,
    recovery_inventory_units: object | None = None,
    recovery_range_low: object | None = None,
    recovery_range_high: object | None = None,
    recovery_cost_basis: object | None = None,
    observed_at: datetime | None = None,
    portfolio_builder: PortfolioPayloadBuilder | None = None,
    opportunities_builder: OpportunitiesPayloadBuilder | None = None,
    auto_audit_runner: AutoAuditRunner = run_auto_audit_loop,
    dge: DecisionGovernanceEngine | None = None,
) -> YkbExecutiveBrief:
    """Build and persist a YKB decision brief without order authority."""
    root = canonical_system_root(repository_root or Path.cwd()).resolve()
    now = observed_at or datetime.now(_ISTANBUL_TZ)
    from ai4binance.cli.status import opportunities_payload, portfolio_command_payload

    portfolio_payload = (
        portfolio_builder(settings)
        if portfolio_builder is not None
        else portfolio_command_payload(settings)
    )
    target_symbol = symbol.strip().upper() if symbol else "MARKET_WIDE"
    validation_target_symbol = (
        target_symbol if target_symbol != "MARKET_WIDE" else settings.validation_symbol
    )
    opportunities_payload_value = (
        opportunities_builder(settings, target_symbol)
        if opportunities_builder is not None
        else opportunities_payload(settings, target_symbol)
    )
    auto_audit = auto_audit_runner(
        settings,
        repository_root=root,
        max_cycles=max_auto_audit_cycles,
        interval_seconds=interval_seconds,
        use_local_qwen=use_local_qwen,
    )
    primitive_portfolio = _mapping(to_primitive(portfolio_payload))
    primitive_opportunities = _mapping(to_primitive(opportunities_payload_value))
    financial = _financial_situation(primitive_portfolio)
    wallet_management = _wallet_position_management(financial, primitive_portfolio)
    vnext_gap = build_vnext_gap_audit(root)
    agent_audit = run_agent_stack_audit(root, _agent_audit_command_names(), now)
    latest_validation = _latest_validation_digest(settings, validation_target_symbol)
    context_items = _runtime_research_context_items(settings, validation_target_symbol)
    technology_items = tuple(
        item for item in context_items if item.category == "TECHNOLOGY_DEVELOPMENT"
    )
    important_context = tuple(
        item for item in context_items if item.category != "TECHNOLOGY_DEVELOPMENT"
    )
    recovery_radar = _build_optional_recovery_radar(
        settings,
        target_symbol,
        primitive_opportunities,
        recovery_inventory_units=recovery_inventory_units,
        recovery_range_low=recovery_range_low,
        recovery_range_high=recovery_range_high,
        recovery_cost_basis=recovery_cost_basis,
    )
    selected_dge = dge or DecisionGovernanceEngine()
    decisions = _dge_decisions(
        primitive_opportunities,
        primitive_portfolio,
        selected_dge,
        blocker_resolution_order_approved=blocker_resolution_order_approved,
    )
    recovery_records = (
        evaluate_recovery_radar_with_dge(
            recovery_radar,
            dge=selected_dge,
            wallet_verified=financial.status == "READY" and not financial.blockers,
            human_review_recorded=blocker_resolution_order_approved,
        )
        if recovery_radar is not None
        else ()
    )
    recovery_decisions = tuple(record.decision for record in recovery_records)
    all_decisions = (*decisions, *recovery_decisions)
    opportunities = (
        *_opportunity_briefs(primitive_opportunities, decisions, financial, root),
        *_recovery_opportunity_briefs(recovery_records, financial, root),
    )
    optional_opportunity_blockers = (
        ("NO_USER_FRIENDLY_OPPORTUNITY_AVAILABLE",) if not opportunities else ()
    )
    blockers = tuple(
        dict.fromkeys(
            (
                *_text_tuple(auto_audit.to_payload().get("blockers")),
                *financial.blockers,
                *(
                    blocker
                    for decision in all_decisions
                    for blocker in (*decision.hard_blockers, *decision.soft_blockers)
                ),
                *optional_opportunity_blockers,
                *latest_validation.blockers,
                *wallet_management.blockers,
                *(f"VNEXT_GAP:{gap}" for gap in vnext_gap.top_gaps[:5]),
                "LIVE_ORDER_BLOCKED",
            )
        )
    )
    status = "READY" if not blockers else "RUNNING_WITH_BLOCKERS"
    brief = YkbExecutiveBrief(
        report_id=f"ykb-report:{int(now.timestamp())}",
        observed_at=now,
        status=status,
        executive_summary=_executive_summary(
            status,
            opportunities,
            blockers,
            financial,
            wallet_management,
            latest_validation,
            auto_audit.status,
            root,
        ),
        auto_audit_status=auto_audit.status,
        auto_audit_ref=str(auto_audit.markdown_path),
        auto_audit_recommendations=_auto_audit_recommendations(auto_audit),
        agent_audit_status=agent_audit.status.value,
        agent_audit_ref=agent_audit.audit_id,
        agent_audit_recommendations=agent_audit.corrective_actions[:10]
        or ("KEEP_AGENT_STACK_AUDIT_GREEN",),
        technology_opportunities=technology_items,
        important_context=important_context,
        latest_validation=latest_validation,
        financial_situation=financial,
        wallet_position_management=wallet_management,
        opportunities=opportunities,
        dge_decisions=all_decisions,
        semi_auto_control=_semi_auto_control(
            blockers,
            blocker_resolution_order_approved=blocker_resolution_order_approved,
        ),
        decision_request=_decision_request(
            opportunities,
            blockers,
            blocker_resolution_order_approved=blocker_resolution_order_approved,
        ),
        blockers=blockers,
        json_path=Path("."),
        markdown_path=Path("."),
        latest_json_path=Path("."),
        latest_markdown_path=Path("."),
        recovery_radar_status=(
            recovery_radar.status if recovery_radar is not None else "NOT_REQUESTED"
        ),
        recovery_radar_ref=(
            f"recovery-radar:{recovery_radar.symbol}"
            if recovery_radar is not None
            else ""
        ),
        vnext_gap_status=vnext_gap.status,
        vnext_gap_ref="vnext-gap-audit",
        vnext_gap_top_gaps=vnext_gap.top_gaps,
    )
    return _persist_brief(
        root,
        brief,
        now,
        private_financial_source=primitive_portfolio,
        recovery_records=recovery_records,
    )


def _financial_situation(payload: Mapping[str, object]) -> YkbFinancialSituation:
    snapshot = _mapping(payload.get("account_snapshot"))
    spot_assets = _sequence(snapshot.get("spot_assets"))
    futures = _mapping(snapshot.get("futures"))
    spot_rows = tuple(_spot_asset_row(raw_asset) for raw_asset in spot_assets)
    futures_positions = _futures_position_rows(futures)
    open_orders = (
        *_open_order_rows("SPOT", snapshot.get("open_orders")),
        *_open_order_rows("USD_M_FUTURES", futures.get("open_orders")),
    )
    known_value = bool(str(snapshot.get("total_value_usdt", "")).strip())
    blockers = tuple(
        dict.fromkeys(
            (
                *_text_tuple(payload.get("blockers")),
                *_text_tuple(snapshot.get("blockers")),
            )
        )
    )
    reconciliation_status = str(snapshot.get("reconciliation_status", "UNKNOWN"))
    return YkbFinancialSituation(
        status=str(payload.get("status", "BLOCKED")),
        spot_asset_count=len(spot_assets),
        futures_position_count=_safe_int(futures.get("position_count")),
        reconciliation_status=reconciliation_status,
        value_disclosure="REDACTED_SUMMARY_ONLY",
        known_value_present=known_value,
        blockers=blockers,
        open_order_count=len(open_orders),
        spot_assets=spot_rows,
        futures_positions=futures_positions,
        open_orders=open_orders,
        inventory_heatmap=_inventory_heatmap_rows(
            _reportable_spot_assets(spot_rows),
            futures_positions,
            open_orders,
            reconciliation_status,
        ),
    )


def _spot_asset_row(raw_asset: object) -> YkbSpotAssetRow:
    asset = _mapping(raw_asset)
    symbol = str(asset.get("asset", "UNKNOWN")).strip().upper() or "UNKNOWN"
    free_value = _positive_decimal(asset.get("free_market_value_usdt"))
    locked_value = _positive_decimal(asset.get("locked_market_value_usdt"))
    market_value = _positive_decimal(asset.get("market_value_usdt"))
    blockers = _text_tuple(asset.get("blockers"))
    free_state = "FREE_CAPITAL_PRESENT" if free_value is not None else "NO_FREE_CAPITAL"
    locked_state = (
        "LOCKED_CAPITAL_PRESENT" if locked_value is not None else "NO_LOCKED_CAPITAL"
    )
    return YkbSpotAssetRow(
        asset=symbol,
        asset_class=_asset_class(symbol),
        free_state=free_state,
        locked_state=locked_state,
        value_bucket=_value_bucket(market_value),
        liquidity_bucket=_asset_liquidity_bucket(symbol, free_value),
        value_report_state=_spot_asset_value_report_state(
            asset.get("market_value_usdt")
        ),
        blockers=blockers,
    )


def _futures_position_rows(
    futures: Mapping[str, object],
) -> tuple[YkbFuturesPositionRow, ...]:
    rows: list[YkbFuturesPositionRow] = []
    for raw_position in _sequence(futures.get("positions")):
        position = _mapping(raw_position)
        symbol = str(position.get("symbol", "UNKNOWN")).strip().upper() or "UNKNOWN"
        side = _first_text(
            position,
            "position_side",
            "positionSide",
            "side",
            default=_position_side_from_quantity(position.get("quantity")),
        )
        notional = _positive_decimal(position.get("notional"))
        margin_type = _first_text(
            position,
            "margin_type",
            "marginType",
            default="UNKNOWN_MARGIN",
        ).upper()
        liquidation_price = _positive_decimal(
            position.get("liquidation_price") or position.get("liquidationPrice")
        )
        rows.append(
            YkbFuturesPositionRow(
                symbol=symbol,
                position_side=side.upper(),
                exposure_bucket=_value_bucket(notional),
                margin_state=margin_type,
                risk_state=(
                    "LIQUIDATION_PRICE_PRESENT"
                    if liquidation_price is not None
                    else "LIQUIDATION_PRICE_UNKNOWN"
                ),
                blockers=_text_tuple(position.get("blockers")),
            )
        )
    return tuple(rows)


def _open_order_rows(
    default_market: str,
    raw_orders: object,
) -> tuple[YkbOpenOrderRow, ...]:
    rows: list[YkbOpenOrderRow] = []
    for raw_order in _sequence(raw_orders):
        order = _mapping(raw_order)
        remaining_value = _positive_decimal(
            order.get("remaining_value_usdt")
            or order.get("locked_value_usdt")
            or order.get("notional")
        )
        rows.append(
            YkbOpenOrderRow(
                market=str(order.get("market", default_market)).strip().upper()
                or default_market,
                symbol=str(order.get("symbol", "UNKNOWN")).strip().upper() or "UNKNOWN",
                side=str(order.get("side", "UNKNOWN")).strip().upper() or "UNKNOWN",
                order_type=str(order.get("type", order.get("order_type", "UNKNOWN")))
                .strip()
                .upper()
                or "UNKNOWN",
                status=str(order.get("status", "UNKNOWN")).strip().upper() or "UNKNOWN",
                locked_liquidity_bucket=_value_bucket(remaining_value),
                stale_state=str(order.get("stale_state", "STALE_STATE_UNKNOWN"))
                .strip()
                .upper()
                or "STALE_STATE_UNKNOWN",
                blockers=_text_tuple(order.get("blockers")),
            )
        )
    return tuple(rows)


def _inventory_heatmap_rows(
    spot_assets: tuple[YkbSpotAssetRow, ...],
    futures_positions: tuple[YkbFuturesPositionRow, ...],
    open_orders: tuple[YkbOpenOrderRow, ...],
    reconciliation_status: str,
) -> tuple[YkbInventoryHeatmapRow, ...]:
    rows: list[YkbInventoryHeatmapRow] = []
    for asset in spot_assets:
        rows.append(
            YkbInventoryHeatmapRow(
                inventory_group=asset.asset,
                concentration_bucket=asset.value_bucket,
                liquidity_bucket=asset.liquidity_bucket,
                action_hint=_asset_action_hint(asset),
                blockers=asset.blockers,
            )
        )
    if futures_positions:
        rows.append(
            YkbInventoryHeatmapRow(
                inventory_group="FUTURES_EXPOSURE",
                concentration_bucket=_highest_bucket(
                    tuple(item.exposure_bucket for item in futures_positions)
                ),
                liquidity_bucket="MANUAL_REVIEW_REQUIRED",
                action_hint="REVIEW_FUTURES_EXPOSURE_NO_AUTO_REDUCE",
                blockers=("FUTURES_POSITION_REVIEW_REQUIRED",),
            )
        )
    if open_orders:
        rows.append(
            YkbInventoryHeatmapRow(
                inventory_group="OPEN_ORDERS",
                concentration_bucket=_highest_bucket(
                    tuple(item.locked_liquidity_bucket for item in open_orders)
                ),
                liquidity_bucket="LOCKED_LIQUIDITY_REVIEW",
                action_hint="REVIEW_OPEN_ORDERS_NO_AUTO_CANCEL",
                blockers=("OPEN_ORDER_REVIEW_REQUIRED",),
            )
        )
    if reconciliation_status != "CLEAN":
        rows.append(
            YkbInventoryHeatmapRow(
                inventory_group="RECONCILIATION",
                concentration_bucket="UNKNOWN",
                liquidity_bucket="BLOCKED",
                action_hint="FIX_RECONCILIATION_BEFORE_POSITION_OR_FUNDING_ACTION",
                blockers=(f"RECONCILIATION_{reconciliation_status}",),
            )
        )
    return tuple(rows)


def _agent_audit_command_names() -> tuple[str, ...]:
    try:
        from ai4binance.cli.commands import available_command_names
    except ImportError:
        return ()
    return available_command_names()


def _wallet_position_management(
    financial: YkbFinancialSituation,
    payload: Mapping[str, object],
) -> YkbWalletPositionManagement:
    blockers = financial.blockers
    snapshot = _mapping(payload.get("account_snapshot"))
    open_policy = "MANUAL_REVIEW_ONLY_NO_AUTO_ORDER"
    if blockers:
        recommendation = "FIX_WALLET_RECONCILIATION_BEFORE_POSITION_ACTION"
        status = "BLOCKED"
    elif financial.futures_position_count > 0:
        recommendation = "REVIEW_OPEN_FUTURES_HEAT_AND_REDUCE_ONLY_MANUALLY"
        status = "REVIEW_REQUIRED"
    elif financial.spot_asset_count > 0:
        recommendation = "MONITOR_SPOT_CONCENTRATION_AND_REBALANCE_ONLY_AFTER_OOS"
        status = "READY_FOR_REVIEW"
    else:
        recommendation = "WAIT_FOR_WALLET_CONTEXT"
        status = "DEGRADED"
        blockers = tuple(dict.fromkeys((*blockers, "WALLET_POSITION_CONTEXT_EMPTY")))
    snapshot_blockers = _text_tuple(snapshot.get("position_blockers"))
    return YkbWalletPositionManagement(
        status=status,
        recommendation=recommendation,
        spot_asset_count=financial.spot_asset_count,
        futures_position_count=financial.futures_position_count,
        open_position_policy=open_policy,
        blockers=tuple(dict.fromkeys((*blockers, *snapshot_blockers))),
        spot_open_order_count=sum(
            1 for order in financial.open_orders if order.market == "SPOT"
        ),
        futures_open_order_count=sum(
            1 for order in financial.open_orders if "FUTURES" in order.market
        ),
        funding_recommendation=_portfolio_funding_recommendation(financial),
    )


def _auto_audit_recommendations(
    auto_audit: AutoAuditLoopResult,
) -> tuple[str, ...]:
    actions = tuple(
        action
        for cycle in auto_audit.cycles
        for action in cycle.action_refs
        if action.strip()
    )
    if actions:
        return tuple(dict.fromkeys(actions[:10]))
    if auto_audit.blockers:
        return tuple(f"resolve:{blocker}" for blocker in auto_audit.blockers[:10])
    return ("KEEP_AUTO_AUDIT_LOOP_RUNNING",)


def _latest_validation_digest(
    settings: Settings,
    symbol: str,
) -> YkbValidationDigest:
    normalized = symbol.strip().upper()
    summary = ValidationSummaryReader(settings.validation_artifact_directory).summarize(
        normalized
    )
    card = _latest_run_card(settings.validation_artifact_directory, normalized)
    if card is None:
        blockers = tuple(
            dict.fromkeys((*summary.blockers, "BACKTEST_RUN_CARD_UNAVAILABLE"))
        )
        return YkbValidationDigest(
            symbol=normalized,
            status="BACKTEST_RUN_CARD_MISSING",
            latest_run_id="KAYIT_YOK",
            timeframe="MULTI_TF_REVIEW",
            playbook="PLAYBOOK_NOT_PROVEN",
            promotion_status="RESEARCH_ONLY",
            run_created_at="KAYIT_YOK",
            metrics=("METRICS_NOT_PUBLISHED",),
            tuning_parameters=("TUNING_PARAMETERS_NOT_PUBLISHED",),
            artifact_refs=("ARTIFACT_REF_NOT_PUBLISHED",),
            blockers=blockers,
        )
    metrics = _metric_texts(_sequence(card.get("metrics")))
    tuning_parameters = _tuning_parameter_texts(card)
    blockers = tuple(
        dict.fromkeys(
            (
                *_text_tuple(card.get("blockers")),
                *summary.blockers,
                *(
                    ("TUNING_PARAMETERS_UNAVAILABLE",)
                    if tuning_parameters == ("TUNING_PARAMETERS_NOT_PUBLISHED",)
                    else ()
                ),
            )
        )
    )
    return YkbValidationDigest(
        symbol=normalized,
        status="READY_WITH_BLOCKERS" if blockers else "READY",
        latest_run_id=str(card.get("run_id", "KAYIT_YOK")),
        timeframe=str(card.get("timeframe", "MULTI_TF_REVIEW")),
        playbook=_run_card_playbook(card),
        promotion_status=str(card.get("promotion_status", "RESEARCH_ONLY")),
        run_created_at=str(
            card.get(
                "artifact_updated_at",
                card.get(
                    "created_at",
                    card.get("completed_at", card.get("observed_at", "KAYIT_YOK")),
                ),
            )
        ),
        metrics=metrics or ("METRICS_NOT_PUBLISHED",),
        tuning_parameters=tuning_parameters,
        artifact_refs=_artifact_refs(card) or ("ARTIFACT_REF_NOT_PUBLISHED",),
        blockers=blockers or ("LIVE_ORDER_BLOCKED",),
    )


def _latest_run_card(
    root: Path,
    symbol: str,
) -> Mapping[str, object] | None:
    symbol_root = root / symbol
    if not symbol_root.exists():
        return None
    latest: Mapping[str, object] | None = None
    latest_updated = 0.0
    for path in sorted(symbol_root.glob("*/*.run-card.json")):
        payload = _read_json_mapping(path)
        if payload is None:
            continue
        updated = path.stat().st_mtime
        if latest is None or updated > latest_updated:
            latest_payload = dict(payload)
            latest_payload["artifact_path"] = str(path)
            latest_payload["artifact_updated_at"] = datetime.fromtimestamp(
                updated, tz=_ISTANBUL_TZ
            ).isoformat()
            latest = latest_payload
            latest_updated = updated
    return latest


def _runtime_research_context_items(
    settings: Settings,
    symbol: str,
) -> tuple[YkbContextItem, ...]:
    report = _read_json_mapping(settings.runtime_opportunity_report_path)
    if report is None:
        return (
            YkbContextItem(
                category="IMPORTANT_CONTEXT",
                title="Runtime research context unavailable",
                impact="UNKNOWN",
                recommendation="RUN_RUNTIME_RESEARCH_REFRESH_ONCE",
                source="local-runtime_research",
                source_url="artifact://runtime_research/opportunities-latest.json",
                as_of="KAYIT_YOK",
                symbol="MARKET_WIDE",
                blockers=("RUNTIME_RESEARCH_CONTEXT_UNAVAILABLE",),
            ),
        )
    report_items = tuple(
        _context_item(raw_item, report)
        for raw_item in _sequence(report.get("opportunities"))[:10]
    )
    feed_items = _runtime_feed_context_items(settings, symbol)
    open_web_items = _runtime_open_web_article_context_items(settings, symbol)
    items = _dedupe_context_items((*report_items, *feed_items, *open_web_items))[:12]
    if items:
        return items
    return (
        YkbContextItem(
            category="IMPORTANT_CONTEXT",
            title="Runtime research has no important context",
            impact=str(report.get("status", "DEGRADED")),
            recommendation="KEEP_RUNTIME_RESEARCH_REFRESH_RUNNING",
            source="local-runtime_research",
            source_url=str(settings.runtime_opportunity_report_path),
            as_of=str(report.get("generated_at", "KAYIT_YOK")),
            symbol="MARKET_WIDE",
            blockers=("NO_IMPORTANT_RUNTIME_CONTEXT_AVAILABLE",),
        ),
    )


def _runtime_feed_context_items(
    settings: Settings,
    symbol: str,
) -> tuple[YkbContextItem, ...]:
    normalized = symbol.strip().upper()
    items: list[YkbContextItem] = []
    for raw_item in _read_jsonl_mappings(settings.runtime_technology_feed_path):
        item = _mapping(raw_item)
        if not _is_relevant_context_symbol(item, normalized):
            continue
        impact = str(item.get("impact", "INFO")).strip().upper()
        if impact not in {"HIGH", "CRITICAL"}:
            continue
        items.append(
            _feed_context_item(
                item,
                category="TECHNOLOGY_DEVELOPMENT",
                title_prefix="Teknolojik gelisme",
                impact=impact,
                default_recommendation="REVIEW_TECHNOLOGY_CHANGE_FOR_AI4BINANCE",
            )
        )
    for raw_item in _read_jsonl_mappings(settings.runtime_news_feed_path):
        item = _mapping(raw_item)
        if not _is_relevant_context_symbol(item, normalized):
            continue
        impact = str(item.get("impact", "INFO")).strip().upper()
        if impact not in {"HIGH", "CRITICAL"}:
            continue
        items.append(
            _feed_context_item(
                item,
                category="IMPORTANT_NEWS",
                title_prefix="Onemli haber",
                impact=impact,
                default_recommendation="REVIEW_AS_RISK_CONTEXT_NOT_TRADE_SIGNAL",
            )
        )
    for raw_item in (
        *_read_jsonl_mappings(settings.runtime_social_feed_path),
        *_read_jsonl_mappings(settings.runtime_content_feed_path),
    ):
        item = _mapping(raw_item)
        if not _is_relevant_context_symbol(item, normalized):
            continue
        if _score_decimal(item.get("score")) < Decimal("60"):
            continue
        direction = _decimal(item.get("directional_vote"), Decimal("0"))
        impact = "MEDIUM" if abs(direction) < Decimal("0.30") else "HIGH"
        items.append(
            _feed_context_item(
                item,
                category="IMPORTANT_CONTEXT",
                title_prefix="Sosyal/content sinyali",
                impact=impact,
                default_recommendation="USE_AS_SECONDARY_CONTEXT_REQUIRE_VALIDATION",
            )
        )
    return tuple(
        sorted(
            _dedupe_context_items(tuple(items)),
            key=lambda item: (_impact_rank(item.impact), item.as_of, item.title),
            reverse=True,
        )
    )


def _runtime_open_web_article_context_items(
    settings: Settings,
    symbol: str,
) -> tuple[YkbContextItem, ...]:
    normalized = symbol.strip().upper()
    items: list[YkbContextItem] = []
    for raw_event in _read_open_web_ledger_mappings(settings):
        event = _mapping(raw_event)
        if event.get("event_type") != "OPEN_WEB_DOCUMENT_RECORDED":
            continue
        payload = _mapping(event.get("payload"))
        observation = _mapping(payload.get("observation"))
        document_payload = _mapping(payload.get("document"))
        evidence = _mapping(payload.get("evidence"))
        if not _is_web_article_record(observation, evidence):
            continue
        if not _is_relevant_open_web_article(observation, normalized):
            continue
        document = _open_web_retrieved_document(document_payload)
        if document is None:
            continue
        candidate = analyze_technology(
            document,
            evidence_id=str(evidence.get("evidence_id", document.document_id)),
            source_reliability=_unit_float(evidence.get("reliability"), default=0.5),
        )
        if candidate is None:
            continue
        items.append(
            YkbContextItem(
                category="TECHNOLOGY_DEVELOPMENT",
                title=f"Web article: {candidate.title}",
                impact=_open_web_article_impact(candidate.confidence),
                recommendation=(
                    "YKB_ONAYI_ILE_RESEARCH_SPIKE_UYGULANABILIR_PRODUCTION_DEGIL"
                ),
                source=_open_web_article_source(observation, evidence),
                source_url=document.canonical_uri,
                as_of=(
                    document.published_at.isoformat()
                    if document.published_at is not None
                    else document.retrieved_at.isoformat()
                ),
                symbol="MARKET_WIDE",
                system_benefit=_open_web_article_benefit(candidate),
                system_tradeoff=_open_web_article_tradeoff(candidate),
                ykb_approval_hint=(
                    "YKB_APPROVAL_REQUIRED_FOR_VALIDATION_ONLY_LIVE_ORDER_BLOCKED"
                ),
                blockers=tuple(
                    dict.fromkeys(
                        (
                            "WEB_ARTICLE_UNVERIFIED",
                            *candidate.blockers,
                            "YKB_APPROVAL_REQUIRED",
                            "LIVE_ORDER_BLOCKED",
                        )
                    )
                ),
            )
        )
    return tuple(
        sorted(
            _dedupe_context_items(tuple(items)),
            key=lambda item: (_impact_rank(item.impact), item.as_of, item.title),
            reverse=True,
        )[:5]
    )


def _read_open_web_ledger_mappings(
    settings: Settings,
) -> tuple[Mapping[str, object], ...]:
    path = settings.open_web_evidence_ledger_path
    try:
        if (
            path.exists()
            and path.stat().st_size > settings.runtime_context_max_file_bytes
        ):
            return ()
    except OSError:
        return ()
    return _read_jsonl_mappings(path)


def _is_web_article_record(
    observation: Mapping[str, object],
    evidence: Mapping[str, object],
) -> bool:
    source_types = {
        str(observation.get("source_type", "")).strip().upper(),
        str(evidence.get("source_type", "")).strip().upper(),
    }
    return "WEB_ARTICLE" in source_types


def _is_relevant_open_web_article(
    observation: Mapping[str, object],
    symbol: str,
) -> bool:
    symbols = tuple(item.upper() for item in _text_tuple(observation.get("symbols")))
    if not symbols:
        return True
    return bool({"ALL", "MARKET_WIDE", "AI4BINANCE", symbol}.intersection(symbols))


def _open_web_retrieved_document(
    value: Mapping[str, object],
) -> RetrievedDocument | None:
    retrieved_at = _aware_datetime(value.get("retrieved_at"))
    if retrieved_at is None:
        return None
    try:
        return RetrievedDocument(
            document_id=str(value.get("document_id", "open-web-document")),
            observation_id=str(value.get("observation_id", "open-web-observation")),
            canonical_uri=str(value.get("canonical_uri", "")),
            content_sha256=str(value.get("content_sha256", "")),
            title=str(value.get("title", "Open web article")),
            retrieved_at=retrieved_at,
            content_type=str(value.get("content_type", "text/html")),
            byte_count=max(1, _safe_int(value.get("byte_count"))),
            text_excerpt=str(value.get("text_excerpt", "")),
            author_or_origin=str(value.get("author_or_origin", "open-web")),
            published_at=_aware_datetime(value.get("published_at")),
            language=str(value.get("language", "UNKNOWN")),
            headings=_text_tuple(value.get("headings")),
            references=_text_tuple(value.get("references")),
            full_text_persisted=False,
        )
    except ValueError:
        return None


def _aware_datetime(value: object) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _unit_float(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, parsed))


def _open_web_article_source(
    observation: Mapping[str, object],
    evidence: Mapping[str, object],
) -> str:
    return _first_text(
        observation,
        "author_or_origin",
        "provider_id",
        default=str(evidence.get("author_or_origin", "open-web-article")),
    )


def _open_web_article_impact(confidence: float) -> str:
    if confidence >= 0.70:
        return "HIGH"
    if confidence >= 0.50:
        return "MEDIUM"
    return "LOW"


def _open_web_article_benefit(candidate: object) -> str:
    technology_area = str(getattr(candidate, "technology_area", "technology"))
    components = (
        ", ".join(getattr(candidate, "affected_components", ())) or "AI4BINANCE"
    )
    return f"WEB_ARTICLE_ARTI: {technology_area} fikri {components} icin YKB gorunurlugu ve local validation adayi uretir."


def _open_web_article_tradeoff(candidate: object) -> str:
    validation = ", ".join(getattr(candidate, "required_validation", ()))
    suffix = f" Required validation: {validation}." if validation else ""
    return (
        "WEB_ARTICLE_EKSI: Tek makale promosyonel, eski veya yanlis olabilir; "
        "bagimsiz kaynak, guvenlik incelemesi, benchmark ve rollback kaniti gerekir."
        f"{suffix}"
    )


def _feed_context_item(
    item: Mapping[str, object],
    *,
    category: str,
    title_prefix: str,
    impact: str,
    default_recommendation: str,
) -> YkbContextItem:
    title = _first_text(
        item,
        "title",
        "headline",
        "development_id",
        "event_id",
        default=title_prefix,
    )
    if title == title_prefix:
        title = f"{title_prefix}: {item.get('source', 'runtime-feed')}"
    return YkbContextItem(
        category=category,
        title=title,
        impact=impact,
        recommendation=_first_text(
            item,
            "opportunity_hint",
            "recommendation",
            default=default_recommendation,
        ),
        source=str(item.get("source", "runtime-feed")),
        source_url=str(item.get("source_url", "artifact://runtime_research/feed")),
        as_of=str(item.get("as_of", item.get("scheduled_at", "KAYIT_YOK"))),
        symbol=str(item.get("symbol", "MARKET_WIDE")).upper(),
        system_benefit=_context_benefit(item, category=category),
        system_tradeoff=_context_tradeoff(item, category=category),
        ykb_approval_hint=_context_approval_hint(item, category=category),
        blockers=_text_tuple(item.get("blockers")),
    )


def _context_benefit(item: Mapping[str, object], *, category: str) -> str:
    return _first_text(
        item,
        "system_benefit",
        "ai4binance_benefit",
        "benefit",
        "pros",
        "artisi",
        default=_default_context_benefit(category),
    )


def _context_tradeoff(item: Mapping[str, object], *, category: str) -> str:
    return _first_text(
        item,
        "system_tradeoff",
        "ai4binance_tradeoff",
        "tradeoff",
        "risk",
        "cons",
        "eksisi",
        default=_default_context_tradeoff(category),
    )


def _context_approval_hint(item: Mapping[str, object], *, category: str) -> str:
    return _first_text(
        item,
        "ykb_approval_hint",
        "approval_hint",
        "approval_note",
        "onay_notu",
        default=_default_context_approval_hint(category),
    )


def _default_context_benefit(category: str) -> str:
    if category == "TECHNOLOGY_DEVELOPMENT":
        return "AI4BINANCE_OBSERVABILITY_VALIDATION_OR_LATENCY_CAPABILITY_CAN_IMPROVE"
    return "AI4BINANCE_CONTEXT_QUALITY_CAN_IMPROVE"


def _default_context_tradeoff(category: str) -> str:
    if category == "TECHNOLOGY_DEVELOPMENT":
        return "ENGINEERING_SECURITY_COMPATIBILITY_AND_LOCAL_TEST_COST_REQUIRED"
    return "SOURCE_RELIABILITY_AND_TRADING_RELEVANCE_MUST_BE_VALIDATED"


def _default_context_approval_hint(category: str) -> str:
    if category == "TECHNOLOGY_DEVELOPMENT":
        return "APPROVE_RESEARCH_SPIKE_WITH_DGE_PRIVACY_AND_ROLLBACK_EVIDENCE"
    return "APPROVE_CONTEXT_MONITORING_ONLY_NOT_TRADE_SIGNAL"


def _read_jsonl_mappings(path: Path) -> tuple[Mapping[str, object], ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    items: list[Mapping[str, object]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        mapping = _mapping(payload)
        if mapping:
            items.append(mapping)
    return tuple(items)


def _is_relevant_context_symbol(
    item: Mapping[str, object],
    symbol: str,
) -> bool:
    raw_symbol = str(item.get("symbol", "ALL")).strip().upper()
    return raw_symbol in {"ALL", "MARKET_WIDE", symbol}


def _dedupe_context_items(
    items: tuple[YkbContextItem, ...],
) -> tuple[YkbContextItem, ...]:
    deduped: dict[tuple[str, str, str], YkbContextItem] = {}
    for item in items:
        key = (item.category, item.title, item.source_url)
        if key not in deduped:
            deduped[key] = item
    return tuple(deduped.values())


def _impact_rank(value: str) -> int:
    return {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
    }.get(value.strip().upper(), 0)


def _context_item(
    raw_item: object,
    report: Mapping[str, object],
) -> YkbContextItem:
    item = _mapping(raw_item)
    category = str(item.get("category", "IMPORTANT_CONTEXT")).strip().upper()
    title = _first_text(
        item,
        "title",
        "headline",
        "opportunity_hint",
        default=str(item.get("opportunity_id", "runtime-context")),
    )
    recommendation = _first_text(
        item,
        "opportunity_hint",
        "next_safe_action",
        "recommendation",
        default="REVIEW_CONTEXT_AS_ADVISORY_EVIDENCE",
    )
    source_url = _first_text(
        item,
        "primary_source_url",
        "source_url",
        default=_first_sequence_text(item.get("trace_urls"))
        or "artifact://runtime_research/opportunities-latest.json",
    )
    return YkbContextItem(
        category=category,
        title=title,
        impact=str(item.get("impact", item.get("status", "INFO"))),
        recommendation=recommendation,
        source=str(item.get("source", item.get("category", "runtime_research"))),
        source_url=source_url,
        as_of=str(
            item.get(
                "as_of",
                item.get("latest_as_of", report.get("generated_at", "KAYIT_YOK")),
            )
        ),
        symbol=str(item.get("symbol", item.get("coin", "MARKET_WIDE"))).upper(),
        system_benefit=_context_benefit(item, category=category),
        system_tradeoff=_context_tradeoff(item, category=category),
        ykb_approval_hint=_context_approval_hint(item, category=category),
        blockers=_text_tuple(item.get("blockers")),
    )


def _build_optional_recovery_radar(
    settings: Settings,
    target_symbol: str,
    primitive_opportunities: Mapping[str, object],
    *,
    recovery_inventory_units: object | None,
    recovery_range_low: object | None,
    recovery_range_high: object | None,
    recovery_cost_basis: object | None,
) -> OpportunityRecoveryRadar | None:
    if recovery_inventory_units is None or str(recovery_inventory_units).strip() == "":
        return None
    return build_opportunity_recovery_radar(
        settings,
        symbol=target_symbol,
        inventory_units=recovery_inventory_units,
        range_low=recovery_range_low,
        range_high=recovery_range_high,
        cost_basis=recovery_cost_basis,
        opportunities_builder=lambda settings, symbol: dict(primitive_opportunities),
    )


def _dge_decisions(
    opportunities_payload: Mapping[str, object],
    portfolio_payload: Mapping[str, object],
    dge: DecisionGovernanceEngine,
    *,
    blocker_resolution_order_approved: bool = False,
) -> tuple[GovernedDecision, ...]:
    inbox = _mapping(opportunities_payload.get("inbox"))
    items = _eligible_opportunity_items(inbox)
    portfolio_blockers = _text_tuple(portfolio_payload.get("blockers"))
    wallet_verified = not any(
        token in blocker
        for blocker in portfolio_blockers
        for token in ("UNAVAILABLE", "RECONCILIATION_REQUIRED", "MISMATCH")
    )
    decisions: list[GovernedDecision] = []
    for index, item in enumerate(items[:5], start=1):
        symbol = str(item.get("symbol", inbox.get("symbol", "UNKNOWN"))).upper()
        blockers = _opportunity_governance_blockers(item)
        context = DgeGovernanceContext(
            context_id=f"ykb:{symbol}:context:{index}",
            data_snapshot_id=str(inbox.get("symbol", symbol)),
            semantic_graph_id=f"ykb-semantic:{symbol}:{index}",
            position_context_ref=str(portfolio_payload.get("status", "portfolio")),
            wallet_verified=wallet_verified,
            oos_approved=not any("OOS" in blocker for blocker in blockers)
            and str(item.get("promotion_status", "")) == "STAGED_CANDIDATE",
            risk_approved=not any("RISK" in blocker for blocker in blockers),
            execution_feasible=False,
            human_approval_recorded=blocker_resolution_order_approved,
            position_dependency_bias_detected=any(
                "COIN_ATTACHMENT" in blocker for blocker in blockers
            ),
            no_new_capital_required=True,
            blockers=tuple(dict.fromkeys((*blockers, *portfolio_blockers))),
            evidence_refs=("opportunities", "portfolio", "auto-audit"),
            config_hash="ykb_report_v1",
        )
        candidate = DgeTradeCandidate(
            candidate_id=f"ykb-opportunity:{symbol}:{index}",
            symbol=symbol,
            market=str(item.get("market", "SPOT")),
            requested_action=_requested_action(item),
            setup_name=str(item.get("setup_name", "UNKNOWN_SETUP")),
            score=_score_decimal(item.get("score")),
            confidence=_confidence_decimal(item.get("confidence")),
            risk_reward=_positive_decimal(item.get("target_risk_reward"))
            or Decimal("2"),
            capital_source="CURRENT_CAPITAL_REVIEW",
            evidence_refs=("opportunities",),
        )
        decisions.append(dge.evaluate(candidate, context))
    return tuple(decisions)


def _default_halt_review_artifact_path(root: Path) -> str:
    paths = user_report_paths(
        root,
        "virtual_loss_streak_halt_review",
        "LATEST",
        file_stem="virtual_loss_streak_halt_review",
    )
    return _relative_report_path(root, paths.latest_json_path)


def _relative_report_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _find_halt_review_artifact_for_ref(root: Path, review_ref: str) -> str:
    normalized_ref = review_ref.strip()
    if not normalized_ref or normalized_ref == "ARTIFACT_REF_NOT_PUBLISHED":
        return "ARTIFACT_PATH_UNRESOLVED"
    artifact_dir = (
        root
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "virtual_loss_streak_halt_review"
    )
    if not artifact_dir.exists():
        return "ARTIFACT_PATH_UNRESOLVED"
    registry_history_path = artifact_dir / "review_registry.jsonl"
    if registry_history_path.exists():
        try:
            history_lines = registry_history_path.read_text(
                encoding="utf-8"
            ).splitlines()
        except OSError:
            history_lines = []
        for line in reversed(history_lines):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(payload.get("review_ref", "")).strip() != normalized_ref:
                continue
            artifact_path = str(payload.get("artifact_path", "")).strip()
            if artifact_path:
                resolved = root / artifact_path
                if resolved.exists():
                    return artifact_path.replace("\\", "/")
    registry_path = artifact_dir / "review_registry_latest.json"
    if registry_path.exists():
        try:
            registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            registry_payload = {}
        if str(registry_payload.get("review_ref", "")).strip() == normalized_ref:
            artifact_path = str(registry_payload.get("artifact_path", "")).strip()
            if artifact_path:
                resolved = root / artifact_path
                if resolved.exists():
                    return artifact_path.replace("\\", "/")
    candidates = sorted(
        path
        for path in artifact_dir.glob("virtual_loss_streak_halt_review_*.json")
        if path.is_file()
    )
    for path in reversed(candidates):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("review_id", "")).strip() == normalized_ref:
            return _relative_report_path(root, path)
    latest_path = artifact_dir / "latest.json"
    if latest_path.exists():
        try:
            payload = json.loads(latest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "ARTIFACT_PATH_UNRESOLVED"
        if str(payload.get("review_id", "")).strip() == normalized_ref:
            return _relative_report_path(root, latest_path)
    return "ARTIFACT_PATH_UNRESOLVED"


def _resolve_halt_review_artifact_path(
    root: Path,
    review_ref: str,
    configured_path: str,
) -> str:
    configured = configured_path.strip()
    if configured and configured != "ARTIFACT_PATH_UNRESOLVED":
        candidate = Path(configured)
        resolved = candidate if candidate.is_absolute() else root / candidate
        if resolved.exists():
            return (
                configured.replace("\\", "/")
                if not candidate.is_absolute()
                else str(resolved)
            )
    exact_match = _find_halt_review_artifact_for_ref(root, review_ref)
    if exact_match != "ARTIFACT_PATH_UNRESOLVED":
        return exact_match
    default_path = user_report_paths(
        root,
        "virtual_loss_streak_halt_review",
        "LATEST",
        file_stem="virtual_loss_streak_halt_review",
    ).latest_json_path
    if default_path.exists():
        return _relative_report_path(root, default_path)
    return "ARTIFACT_PATH_UNRESOLVED"


def _read_halt_review_artifact(
    root: Path,
    artifact_path: str,
) -> Mapping[str, object]:
    configured = artifact_path.strip()
    if not configured or configured == "ARTIFACT_PATH_UNRESOLVED":
        return {}
    candidate = Path(configured)
    resolved = candidate if candidate.is_absolute() else root / candidate
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _halt_review_root_cause_summary(
    artifact_payload: Mapping[str, object],
) -> str:
    summary = str(
        artifact_payload.get("root_cause_summary", "ROOT_CAUSE_SUMMARY_UNAVAILABLE")
    ).strip()
    return summary or "ROOT_CAUSE_SUMMARY_UNAVAILABLE"


def _halt_review_next_bounded_experiment(
    artifact_payload: Mapping[str, object],
) -> str:
    experiment = str(
        artifact_payload.get(
            "next_bounded_experiment",
            "NEXT_BOUNDED_EXPERIMENT_UNAVAILABLE",
        )
    ).strip()
    return experiment or "NEXT_BOUNDED_EXPERIMENT_UNAVAILABLE"


def _has_loss_streak_halt_marker(blockers: tuple[str, ...]) -> bool:
    return "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED" in blockers


def _recovery_opportunity_briefs(
    records: tuple[DgeEvaluationRecord, ...],
    financial: YkbFinancialSituation,
    root: Path,
) -> tuple[YkbOpportunityBrief, ...]:
    briefs: list[YkbOpportunityBrief] = []
    for record in records:
        decision = record.decision
        candidate = record.candidate
        blockers = tuple(
            dict.fromkeys((*decision.hard_blockers, *decision.soft_blockers))
        )
        funding = _funding_recommendation({}, financial, blockers)
        briefs.append(
            YkbOpportunityBrief(
                opportunity_id=decision.candidate_id,
                headline=_headline(
                    decision.symbol,
                    candidate.setup_name,
                    decision.governance_status.value,
                    blockers,
                ),
                market=candidate.market,
                symbol=decision.symbol,
                timeframe=_timeframe_value({"timeframe": candidate.primary_timeframe}),
                setup_name=candidate.setup_name,
                pattern_type=setup_pattern_type(candidate.setup_name),
                requested_action=decision.requested_action.value,
                governed_action=decision.governed_action.value,
                trade_side=_trade_side(
                    {},
                    candidate.market,
                    decision.requested_action.value,
                ),
                leverage=_trade_leverage({}, candidate.market),
                dge_status=decision.governance_status.value,
                score=candidate.score,
                confidence=candidate.confidence,
                target_risk_reward=candidate.risk_reward or Decimal("1"),
                financial_fit=_financial_fit(decision),
                funding_requirement=funding.funding_requirement,
                blockers=blockers,
                next_safe_action=_next_action(blockers),
                evidence_refs=decision.evidence_refs,
                halt_review_artifact_path=(
                    _resolve_halt_review_artifact_path(
                        root,
                        "ARTIFACT_REF_NOT_PUBLISHED",
                        _default_halt_review_artifact_path(root),
                    )
                    if _has_loss_streak_halt_marker(blockers)
                    else "ARTIFACT_PATH_UNRESOLVED"
                ),
                required_capital_bucket=funding.required_capital_bucket,
                free_quote_sufficiency=funding.free_quote_sufficiency,
                manual_liquidity_preparation=funding.manual_liquidity_preparation,
                external_capital_policy=funding.external_capital_policy,
                conversion_or_transfer_policy=funding.conversion_or_transfer_policy,
                funding_blockers=funding.funding_blockers,
                entry=_trade_plan_value({}, "entry"),
                stop_loss=_trade_plan_value({}, "stop_loss", "stop", "sl"),
                take_profit_1=_trade_plan_value({}, "tp1", "take_profit_1"),
                take_profit_2=_trade_plan_value({}, "tp2", "take_profit_2"),
                take_profit_3=_trade_plan_value({}, "tp3", "take_profit_3"),
            )
        )
    return tuple(briefs)


def _opportunity_briefs(
    opportunities_payload: Mapping[str, object],
    decisions: tuple[GovernedDecision, ...],
    financial: YkbFinancialSituation,
    root: Path,
) -> tuple[YkbOpportunityBrief, ...]:
    inbox = _mapping(opportunities_payload.get("inbox"))
    items = _eligible_opportunity_items(inbox)
    briefs: list[YkbOpportunityBrief] = []
    for index, item in enumerate(items[: len(decisions)]):
        decision = decisions[index]
        source_blockers = _text_tuple(item.get("blockers"))
        blockers = tuple(
            dict.fromkeys(
                (*source_blockers, *decision.hard_blockers, *decision.soft_blockers)
            )
        )
        score = _score_decimal(item.get("score"))
        confidence = _confidence_decimal(item.get("confidence"))
        symbol = str(item.get("symbol", decision.symbol)).upper()
        market = str(item.get("market", "SPOT"))
        setup = str(item.get("setup_name", "UNKNOWN_SETUP"))
        dge_status = decision.governance_status.value
        funding = _funding_recommendation(item, financial, blockers)
        halt_review_ref = (
            str(item.get("halt_review_ref", "ARTIFACT_REF_NOT_PUBLISHED"))
            if _has_loss_streak_halt_marker(blockers)
            else "ARTIFACT_REF_NOT_PUBLISHED"
        )
        halt_review_artifact_path = (
            _resolve_halt_review_artifact_path(
                root,
                halt_review_ref,
                str(
                    item.get(
                        "halt_review_artifact_path",
                        "ARTIFACT_PATH_UNRESOLVED",
                    )
                ),
            )
            if _has_loss_streak_halt_marker(blockers)
            else "ARTIFACT_PATH_UNRESOLVED"
        )
        halt_review_artifact = _read_halt_review_artifact(
            root,
            halt_review_artifact_path,
        )
        briefs.append(
            YkbOpportunityBrief(
                opportunity_id=decision.candidate_id,
                headline=_headline(symbol, setup, dge_status, blockers),
                market=market,
                symbol=symbol,
                timeframe=_timeframe_value(item),
                setup_name=setup,
                pattern_type=_pattern_type_value(
                    item.get("pattern_type"),
                    fallback_setup_name=setup,
                ),
                requested_action=decision.requested_action.value,
                governed_action=decision.governed_action.value,
                trade_side=_trade_side(item, market, decision.requested_action.value),
                leverage=_trade_leverage(item, market),
                dge_status=dge_status,
                score=score,
                confidence=confidence,
                target_risk_reward=_positive_decimal(item.get("target_risk_reward"))
                or Decimal("2"),
                financial_fit=_financial_fit(decision),
                funding_requirement=funding.funding_requirement,
                blockers=blockers,
                next_safe_action=_next_action(blockers),
                evidence_refs=decision.evidence_refs,
                why_now=_text_tuple(item.get("why_now")),
                confirmation_requirements=_text_tuple(
                    item.get("confirmation_requirements")
                ),
                promotion_requirements=_text_tuple(item.get("promotion_requirements")),
                execution_blockers=tuple(
                    dict.fromkeys(
                        (
                            *_text_tuple(item.get("execution_blockers")),
                            *decision.hard_blockers,
                            *decision.soft_blockers,
                        )
                    )
                ),
                next_evidence_action=str(
                    item.get("next_evidence_action", _next_action(blockers))
                ),
                improvement_candidate_hint=str(
                    item.get("improvement_candidate_hint", "HALT_REVIEW_PENDING")
                ),
                halt_reset_criteria=_text_tuple(item.get("halt_reset_criteria")),
                halt_review_ref=halt_review_ref,
                halt_review_artifact_path=halt_review_artifact_path,
                halt_root_cause_summary=_halt_review_root_cause_summary(
                    halt_review_artifact
                ),
                halt_next_bounded_experiment=_halt_review_next_bounded_experiment(
                    halt_review_artifact
                ),
                required_capital_bucket=funding.required_capital_bucket,
                free_quote_sufficiency=funding.free_quote_sufficiency,
                manual_liquidity_preparation=funding.manual_liquidity_preparation,
                external_capital_policy=funding.external_capital_policy,
                conversion_or_transfer_policy=funding.conversion_or_transfer_policy,
                funding_blockers=funding.funding_blockers,
                entry=_trade_plan_value(item, "entry", "entry_price"),
                stop_loss=_trade_plan_value(item, "stop_loss", "stop", "sl"),
                take_profit_1=_trade_plan_value(
                    item,
                    "tp1",
                    "take_profit_1",
                    "take_profit",
                ),
                take_profit_2=_trade_plan_value(item, "tp2", "take_profit_2"),
                take_profit_3=_trade_plan_value(item, "tp3", "take_profit_3"),
            )
        )
    return tuple(briefs)


def _semi_auto_control(
    blockers: tuple[str, ...],
    *,
    blocker_resolution_order_approved: bool,
) -> SemiAutoControlManagement:
    approval_status = (
        "APPROVED_BY_YKB"
        if blocker_resolution_order_approved
        else "PENDING_YKB_APPROVAL"
    )
    next_action = (
        "EXECUTE_APPROVED_BLOCKER_RESOLUTION_ORDER"
        if blocker_resolution_order_approved
        else "REQUEST_YKB_BLOCKER_ORDER_APPROVAL"
    )
    review_blockers = (
        () if blocker_resolution_order_approved else ("HUMAN_REVIEW_REQUIRED",)
    )
    return SemiAutoControlManagement(
        mode="SEMI_AUTO_CONTROL_MANAGEMENT",
        workflow_pattern="HUMAN_IN_THE_LOOP_EVALUATOR_OPTIMIZER",
        blocker_resolution_order_status=approval_status,
        risk_oos_live_gate_status="LOCKED_UNTIL_RISK_AND_OOS_EVIDENCE",
        next_management_action=next_action,
        loop_steps=(
            "AUTO_AUDIT_LOOP",
            "FINANCIAL_CONTEXT_REVIEW",
            "OPPORTUNITY_RADAR_REVIEW",
            "DGE_DECISION_REVIEW",
            "YKB_DECISION_PACKET",
        ),
        human_approval_gates=(
            "TRADING_SCOPE",
            "MONEY_MOVEMENT_SCOPE",
            "RISK_OR_POLICY_ESCALATION",
            "LIVE_ORDER_GATE",
        ),
        stopping_rule="STOP_AT_BLOCKER_OR_YKB_DECISION",
        blockers=tuple(dict.fromkeys((*blockers, *review_blockers))),
    )


def _persist_brief(
    root: Path,
    brief: YkbExecutiveBrief,
    observed_at: datetime,
    *,
    private_financial_source: Mapping[str, object],
    recovery_records: tuple[DgeEvaluationRecord, ...] = (),
) -> YkbExecutiveBrief:
    stamp = observed_at.astimezone(_ISTANBUL_TZ).strftime("%Y%m%dT%H%M%S_tr")
    report_paths = user_report_paths(
        root,
        "ykb",
        stamp,
        file_stem="ykb_report",
        latest_stem="latest",
    )
    artifact_dir = root / "runtime" / "artifacts" / "ykb"
    private_financial_dir = root / "runtime" / "state" / "private" / "ykb"
    artifact_json_path = artifact_dir / f"ykb_report_{stamp}.json"
    artifact_latest_json_path = artifact_dir / "ykb_report_latest.json"
    json_path = report_paths.json_path
    latest_json_path = report_paths.latest_json_path
    markdown_path = report_paths.markdown_path
    private_financial_json_path = (
        private_financial_dir / f"ykb_financial_values_{stamp}.json"
    )
    private_financial_markdown_path = (
        private_financial_dir / f"ykb_financial_values_{stamp}.md"
    )
    persisted = YkbExecutiveBrief(
        report_id=brief.report_id,
        observed_at=brief.observed_at,
        status=brief.status,
        executive_summary=brief.executive_summary,
        auto_audit_status=brief.auto_audit_status,
        auto_audit_ref=brief.auto_audit_ref,
        auto_audit_recommendations=brief.auto_audit_recommendations,
        agent_audit_status=brief.agent_audit_status,
        agent_audit_ref=brief.agent_audit_ref,
        agent_audit_recommendations=brief.agent_audit_recommendations,
        technology_opportunities=brief.technology_opportunities,
        important_context=brief.important_context,
        latest_validation=brief.latest_validation,
        financial_situation=brief.financial_situation,
        wallet_position_management=brief.wallet_position_management,
        opportunities=brief.opportunities,
        dge_decisions=brief.dge_decisions,
        semi_auto_control=brief.semi_auto_control,
        decision_request=brief.decision_request,
        blockers=brief.blockers,
        json_path=json_path,
        markdown_path=markdown_path,
        latest_json_path=latest_json_path,
        latest_markdown_path=report_paths.latest_markdown_path,
        private_financial_json_path=private_financial_json_path,
        private_financial_markdown_path=private_financial_markdown_path,
        recovery_radar_status=brief.recovery_radar_status,
        recovery_radar_ref=brief.recovery_radar_ref,
        vnext_gap_status=brief.vnext_gap_status,
        vnext_gap_ref=brief.vnext_gap_ref,
        vnext_gap_top_gaps=brief.vnext_gap_top_gaps,
    )
    payload = persisted.to_payload()
    write_json_object_verified(
        json_path,
        payload,
        blocker="ykb_report_DESTINATION_VERIFY_FAILED",
        subject_id=persisted.report_id,
        indent=2,
    )
    write_json_object_verified(
        latest_json_path,
        payload,
        blocker="ykb_report_DESTINATION_VERIFY_FAILED",
        subject_id=persisted.report_id,
        indent=2,
    )
    write_json_object_verified(
        artifact_json_path,
        payload,
        blocker="ykb_report_DESTINATION_VERIFY_FAILED",
        subject_id=persisted.report_id,
        indent=2,
    )
    write_json_object_verified(
        artifact_latest_json_path,
        payload,
        blocker="ykb_report_DESTINATION_VERIFY_FAILED",
        subject_id=persisted.report_id,
        indent=2,
    )
    report_paths.report_dir.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_render_markdown(persisted), encoding="utf-8")
    report_paths.latest_markdown_path.write_text(
        _render_latest_markdown(persisted),
        encoding="utf-8",
    )
    private_financial_payload = _private_financial_report_payload(
        persisted,
        private_financial_source,
    )
    write_json_object_verified(
        private_financial_json_path,
        private_financial_payload,
        blocker="YKB_PRIVATE_FINANCIAL_REPORT_DESTINATION_VERIFY_FAILED",
        subject_id=persisted.report_id,
        indent=2,
    )
    private_financial_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    private_financial_markdown_path.write_text(
        _render_private_financial_markdown(private_financial_payload),
        encoding="utf-8",
    )
    for decision in persisted.dge_decisions:
        persist_dge_decision_event(root, decision, source="ykb_report")
    for record in recovery_records:
        persist_dge_evaluation_record(root, record)
    return persisted


def _private_financial_report_payload(
    brief: YkbExecutiveBrief,
    source: Mapping[str, object],
) -> dict[str, object]:
    snapshot = _mapping(source.get("account_snapshot"))
    futures = _mapping(snapshot.get("futures"))
    private_snapshot: dict[str, object] = {
        "snapshot_id": _value_text(snapshot.get("snapshot_id")),
        "reconciliation_status": _value_text(
            snapshot.get("reconciliation_status"),
            default="UNKNOWN",
        ),
        "total_value_usdt": _value_text(snapshot.get("total_value_usdt")),
        "spot_assets": [
            _private_spot_asset_payload(raw_asset)
            for raw_asset in _sequence(snapshot.get("spot_assets"))
        ],
        "spot_open_orders": [
            _private_open_order_payload("SPOT", raw_order)
            for raw_order in _sequence(snapshot.get("open_orders"))
        ],
        "futures": {
            "position_count": _safe_int(futures.get("position_count")),
            "total_wallet_balance": _value_text(futures.get("total_wallet_balance")),
            "available_balance": _value_text(futures.get("available_balance")),
            "positions": [
                _private_futures_position_payload(raw_position)
                for raw_position in _sequence(futures.get("positions"))
            ],
            "open_orders": [
                _private_open_order_payload("USD_M_FUTURES", raw_order)
                for raw_order in _sequence(futures.get("open_orders"))
            ],
        },
    }
    return {
        "command": "ykb-private-financial-values",
        "report_id": brief.report_id,
        "observed_at": brief.observed_at.isoformat(),
        "policy": {
            "storage": "runtime/state/private/ykb",
            "scope": "LOCAL_YKB_ONLY",
            "cloud_share_allowed": False,
            "github_share_allowed": False,
            "blockers": [
                "NO_GITHUB_CLOUD_SHARE",
                "LOCAL_YKB_ONLY",
                "BINANCE_FINANCIAL_VALUES_PRIVATE",
            ],
        },
        "account_snapshot": private_snapshot,
        "management_recommendations": list(
            _private_financial_management_recommendations(
                brief.financial_situation,
                snapshot,
                futures,
            )
        ),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _private_spot_asset_payload(raw_asset: object) -> dict[str, object]:
    asset = _mapping(raw_asset)
    return {
        "asset": _value_text(asset.get("asset"), default="UNKNOWN").upper(),
        "free_qty": _value_text(asset.get("free_qty")),
        "locked_qty": _value_text(asset.get("locked_qty")),
        "market_value_usdt": _value_text(asset.get("market_value_usdt")),
        "free_market_value_usdt": _value_text(asset.get("free_market_value_usdt")),
        "locked_market_value_usdt": _value_text(asset.get("locked_market_value_usdt")),
        "management_hint": _private_asset_management_hint(asset),
        "blockers": list(_text_tuple(asset.get("blockers"))),
    }


def _private_futures_position_payload(raw_position: object) -> dict[str, object]:
    position = _mapping(raw_position)
    return {
        "symbol": _value_text(position.get("symbol"), default="UNKNOWN").upper(),
        "position_side": _first_text(
            position,
            "position_side",
            "positionSide",
            "side",
            default=_position_side_from_quantity(position.get("quantity")),
        ).upper(),
        "quantity": _value_text(position.get("quantity")),
        "notional": _value_text(position.get("notional")),
        "entry_price": _value_text(
            position.get("entry_price") or position.get("entryPrice")
        ),
        "mark_price": _value_text(
            position.get("mark_price") or position.get("markPrice")
        ),
        "unrealized_profit": _value_text(
            position.get("unrealized_profit") or position.get("unrealizedProfit")
        ),
        "liquidation_price": _value_text(
            position.get("liquidation_price") or position.get("liquidationPrice")
        ),
        "margin_type": _first_text(
            position,
            "margin_type",
            "marginType",
            default="UNKNOWN_MARGIN",
        ).upper(),
        "management_hint": "REVIEW_FUTURES_EXPOSURE_NO_AUTO_REDUCE",
        "blockers": list(_text_tuple(position.get("blockers"))),
    }


def _private_open_order_payload(
    default_market: str,
    raw_order: object,
) -> dict[str, object]:
    order = _mapping(raw_order)
    return {
        "market": _value_text(order.get("market"), default=default_market).upper(),
        "symbol": _value_text(order.get("symbol"), default="UNKNOWN").upper(),
        "side": _value_text(order.get("side"), default="UNKNOWN").upper(),
        "order_type": _value_text(
            order.get("type") or order.get("order_type"),
            default="UNKNOWN",
        ).upper(),
        "status": _value_text(order.get("status"), default="UNKNOWN").upper(),
        "price": _value_text(order.get("price")),
        "quantity": _value_text(order.get("quantity") or order.get("orig_qty")),
        "remaining_value_usdt": _value_text(order.get("remaining_value_usdt")),
        "locked_value_usdt": _value_text(order.get("locked_value_usdt")),
        "notional": _value_text(order.get("notional")),
        "management_hint": "REVIEW_OPEN_ORDER_NO_AUTO_CANCEL",
        "blockers": list(_text_tuple(order.get("blockers"))),
    }


def _private_asset_management_hint(asset: Mapping[str, object]) -> str:
    symbol = _value_text(asset.get("asset"), default="UNKNOWN").upper()
    if symbol == "HOT":
        return "DO_NOT_SELL_OR_TRANSFER_WITHOUT_EXPLICIT_YKB_APPROVAL"
    if symbol in {"USDT", "USDC"}:
        return "REVIEW_QUOTE_CASH_FOR_MANUAL_LIQUIDITY_ONLY"
    if _positive_decimal(asset.get("locked_market_value_usdt")) is not None:
        return "REVIEW_LOCKED_VALUE_NO_AUTO_CANCEL"
    return "MONITOR_POSITION_NO_AUTO_ACTION"


def _private_financial_management_recommendations(
    financial: YkbFinancialSituation,
    snapshot: Mapping[str, object],
    futures: Mapping[str, object],
) -> tuple[str, ...]:
    recommendations: list[str] = [
        "NO_GITHUB_CLOUD_SHARE",
        "NO_EXTERNAL_CAPITAL_ALLOWED",
        "AUTO_MONEY_MOVEMENT_BLOCKED",
        "LIVE_ORDER_BLOCKED",
    ]
    if financial.reconciliation_status != "CLEAN" or financial.blockers:
        recommendations.append("FIX_RECONCILIATION_BEFORE_ANY_CAPITAL_DECISION")
    if _sequence(snapshot.get("open_orders")):
        recommendations.append("REVIEW_SPOT_OPEN_ORDERS_NO_AUTO_CANCEL")
    if _sequence(futures.get("open_orders")):
        recommendations.append("REVIEW_FUTURES_OPEN_ORDERS_NO_AUTO_CANCEL")
    if _sequence(futures.get("positions")):
        recommendations.append("REVIEW_FUTURES_EXPOSURE_NO_AUTO_REDUCE")
    if any(
        _value_text(_mapping(asset).get("asset")).upper() == "HOT"
        for asset in _sequence(snapshot.get("spot_assets"))
    ):
        recommendations.append("PROTECTED_HOT_POSITION_NO_AUTO_SELL_OR_TRANSFER")
    if _quote_liquidity_bucket(financial) in {"READY", "LIMITED"}:
        recommendations.append("QUOTE_LIQUIDITY_AVAILABLE_FOR_MANUAL_REVIEW_ONLY")
    else:
        recommendations.append("MANUAL_LIQUIDITY_PREPARATION_REQUIRED")
    return tuple(dict.fromkeys(recommendations))


def _render_private_financial_markdown(payload: Mapping[str, object]) -> str:
    snapshot = _mapping(payload.get("account_snapshot"))
    futures = _mapping(snapshot.get("futures"))
    lines = [
        f"# Local-Only YKB Binance Finansal Deger Eki - {payload.get('report_id')}",
        "",
        "## Paylasim Politikasi",
        "",
        "- scope: `LOCAL_YKB_ONLY`",
        "- github_share_allowed: `false`",
        "- cloud_share_allowed: `false`",
        "- blocker: `NO_GITHUB_CLOUD_SHARE`",
        "- execution_allowed: `false`",
        "- live_eligibility_status: `LIVE_ORDER_BLOCKED`",
        "",
        "## Binance Finansal Degerler",
        "",
        f"- snapshot_id: `{snapshot.get('snapshot_id') or 'UNAVAILABLE'}`",
        f"- reconciliation_status: `{snapshot.get('reconciliation_status')}`",
        f"- total_value_usdt: `{snapshot.get('total_value_usdt') or 'UNAVAILABLE'}`",
        "",
        "### Spot Assets",
        "",
    ]
    spot_asset_rows: list[tuple[object, ...]] = []
    for raw_asset in _sequence(snapshot.get("spot_assets")):
        asset = _mapping(raw_asset)
        spot_asset_rows.append(
            (
                asset.get("asset"),
                asset.get("free_qty") or "-",
                asset.get("locked_qty") or "-",
                asset.get("market_value_usdt") or "-",
                asset.get("free_market_value_usdt") or "-",
                asset.get("locked_market_value_usdt") or "-",
                asset.get("management_hint"),
            )
        )
    lines.extend(
        _markdown_table(
            (
                "Asset",
                "free_qty",
                "locked_qty",
                "market_value_usdt",
                "free_market_value_usdt",
                "locked_market_value_usdt",
                "Management",
            ),
            spot_asset_rows,
            alignments=("left", "right", "right", "right", "right", "right", "left"),
        )
    )
    lines.extend(
        [
            "",
            "### Open Orders",
            "",
        ]
    )
    open_orders = (
        *_sequence(snapshot.get("spot_open_orders")),
        *_sequence(futures.get("open_orders")),
    )
    open_order_rows: list[tuple[object, ...]] = []
    if not open_orders:
        open_order_rows.append(
            ("-", "-", "-", "-", "NONE", "-", "-", "-", "-", "-", "WAIT")
        )
    for raw_order in open_orders:
        order = _mapping(raw_order)
        open_order_rows.append(
            (
                order.get("market"),
                order.get("symbol"),
                order.get("side"),
                order.get("order_type"),
                order.get("status"),
                order.get("price") or "-",
                order.get("quantity") or "-",
                order.get("remaining_value_usdt") or "-",
                order.get("locked_value_usdt") or "-",
                order.get("notional") or "-",
                order.get("management_hint"),
            )
        )
    lines.extend(
        _markdown_table(
            (
                "Market",
                "Symbol",
                "Side",
                "Type",
                "Status",
                "price",
                "quantity",
                "remaining_value_usdt",
                "locked_value_usdt",
                "notional",
                "Management",
            ),
            open_order_rows,
            alignments=(
                "left",
                "left",
                "left",
                "left",
                "left",
                "right",
                "right",
                "right",
                "right",
                "right",
                "left",
            ),
        )
    )
    lines.extend(
        [
            "",
            "### Futures Positions",
            "",
        ]
    )
    positions = _sequence(futures.get("positions"))
    position_rows: list[tuple[object, ...]] = []
    if not positions:
        position_rows.append(
            ("-", "NONE", "-", "-", "-", "-", "-", "-", "NO_OPEN_FUTURES_POSITION")
        )
    for raw_position in positions:
        position = _mapping(raw_position)
        position_rows.append(
            (
                position.get("symbol"),
                position.get("position_side"),
                position.get("quantity") or "-",
                position.get("notional") or "-",
                position.get("entry_price") or "-",
                position.get("mark_price") or "-",
                position.get("unrealized_profit") or "-",
                position.get("liquidation_price") or "-",
                position.get("management_hint"),
            )
        )
    lines.extend(
        _markdown_table(
            (
                "Symbol",
                "Side",
                "quantity",
                "notional",
                "entry_price",
                "mark_price",
                "unrealized_profit",
                "liquidation_price",
                "Management",
            ),
            position_rows,
            alignments=(
                "left",
                "left",
                "right",
                "right",
                "right",
                "right",
                "right",
                "right",
                "left",
            ),
        )
    )
    lines.extend(
        [
            "",
            "## YKB Finansal Deger Yonetim Onerileri",
            "",
        ]
    )
    for recommendation in _sequence(payload.get("management_recommendations")):
        lines.append(f"- `{recommendation}`")
    lines.append("")
    return "\n".join(lines)


def _render_latest_markdown(brief: YkbExecutiveBrief) -> str:
    internal_radar = _internal_radar_payload(brief)
    opportunity_lines = [
        (
            f"- `{item.symbol}` `{item.market}` `{item.timeframe}` "
            f"{item.trade_side} leverage `{item.leverage}`; "
            f"E `{item.entry}`, SL `{item.stop_loss}`, "
            f"TP1 `{item.take_profit_1}`, TP2 `{item.take_profit_2}`, "
            f"TP3 `{item.take_profit_3}`; DGE `{item.dge_status}`; "
            f"next action `{item.next_safe_action}`."
        )
        for item in brief.opportunities[:10]
    ]
    technology_lines = [
        (
            f"- `{item.impact}` {item.title} ({item.source}, {item.source_url}); recommendation: `{item.recommendation}`."
        )
        for item in brief.technology_opportunities[:10]
    ]
    context_lines = [
        (
            f"- `{item.category}` `{item.impact}` {item.title} "
            f"({item.source}, {item.source_url}); recommendation: "
            f"`{item.recommendation}`."
        )
        for item in brief.important_context[:10]
    ]
    financial_lines = [
        f"- Financial status: `{brief.financial_situation.status}`.",
        f"- Spot asset count: `{brief.financial_situation.spot_asset_count}`.",
        (
            f"- Futures position count: `{brief.financial_situation.futures_position_count}`."
        ),
        f"- Reconciliation: `{brief.financial_situation.reconciliation_status}`.",
        (
            f"- Wallet recommendation: `{brief.wallet_position_management.recommendation}`."
        ),
        "- Public report value disclosure: `REDACTED_SUMMARY_ONLY`.",
    ]
    validation_lines = [
        f"- Validation status: `{brief.latest_validation.status}`.",
        f"- Latest run id: `{brief.latest_validation.latest_run_id}`.",
        f"- Validation symbol: `{brief.latest_validation.symbol}`.",
        f"- Tuning parameters: `{_latest_validation_tuning_text(brief)}`.",
    ]
    return render_professional_summary(
        title="AI4Binance YKB Report",
        observed_at=_istanbul_time_text(brief.observed_at),
        status=brief.status,
        summary=brief.executive_summary,
        blockers=brief.blockers,
        sections=(
            ("Opportunity Watchlist", opportunity_lines),
            ("Technology Developments", technology_lines),
            ("News and Content Context", context_lines),
            ("Internal Image Radar", _internal_radar_summary_lines(internal_radar)),
            ("Financial Situation", financial_lines),
            ("Validation and Audit", validation_lines),
        ),
    )


def _latest_validation_tuning_text(brief: YkbExecutiveBrief) -> str:
    return ", ".join(brief.latest_validation.tuning_parameters) or "UNAVAILABLE"


def _internal_radar_payload(brief: YkbExecutiveBrief) -> dict[str, object]:
    """Return only the redacted local-radar digest suitable for YKB output."""
    parents = brief.json_path.parents
    root = parents[4] if len(parents) > 4 else Path.cwd()
    return load_internal_radar_latest(root)


def _internal_radar_summary_lines(payload: Mapping[str, object]) -> list[str]:
    blockers = _text_tuple(payload.get("blockers"))
    vision_summary = payload.get("vision_summary")
    vision = vision_summary if isinstance(vision_summary, Mapping) else {}
    return [
        f"- Status: `{_value_text(payload.get('status'), default='UNAVAILABLE')}`.",
        f"- New review candidates: `{_safe_int(payload.get('new_candidate_count'))}`.",
        f"- Pending review candidates: `{_safe_int(payload.get('review_candidate_count'))}`.",
        f"- Validated visual observations: `{_safe_int(vision.get('observed_count'))}`.",
        f"- System benefit categories: `{_radar_category_counts(vision.get('benefit_categories'))}`.",
        f"- System trade-off categories: `{_radar_category_counts(vision.get('tradeoff_categories'))}`.",
        "- Source images, names, full paths, and EXIF: `NOT_INCLUDED_IN_YKB`.",
        f"- Blockers: `{', '.join(blockers) or '-'}`.",
        "- Authority: `RESEARCH_ONLY`; `LIVE_ORDER_BLOCKED`.",
    ]


def _radar_category_counts(value: object) -> str:
    if not isinstance(value, Mapping):
        return "-"
    items = [
        (str(key), count)
        for key, count in value.items()
        if isinstance(key, str) and isinstance(count, int) and count > 0
    ]
    return ", ".join(f"{key}={count}" for key, count in sorted(items)) or "-"


def _render_markdown(brief: YkbExecutiveBrief) -> str:
    financial = brief.financial_situation
    internal_radar = _internal_radar_payload(brief)
    lines = [
        f"# AI4BINANCE YKB Executive Brief - {brief.report_id}",
        "",
        "## ELI10",
        "",
        (
            "Bu rapor sistem sagligi, mevcut finansal durum ozeti, firsat radari "
            "ve DGE kararini YKB icin tek sayfada toplar. Rapor karar destegidir; "
            "emir vermez, risk artirmaz ve canli modu acmaz."
        ),
        "",
        "## Zaman Standardi",
        "",
        "- timezone: `Europe/Istanbul`",
        f"- report_observed_at: `{_istanbul_time_text(brief.observed_at)}`",
        (
            "- note: `Binance/OHLCV ham zamanlari kanonik kaynakta UTC kalir; "
            "YKB ve yonetim raporu zamanlari Istanbul olarak gosterilir.`"
        ),
        "",
        *_recent_ykb_report_history_lines(brief.markdown_path),
        "",
        "## Yonetici Ozeti",
        "",
        brief.executive_summary,
        "",
        "### Firsat ve Oneri Ozeti",
        "",
        *_executive_opportunity_lines(brief.opportunities),
        "",
        "## Mevcut Finansal Durum",
        "",
        (
            "Public YKB raporunda ham Binance finansal degerleri bilerek "
            "saklanir; karar icin gerekli sayim, sinif, mutabakat, nakit/quote "
            "hazirligi ve yonetim onerisi gorunur tutulur. Detayli parasal "
            "degerler yalniz local-private ekte incelenir ve GitHub/cloud "
            "paylasimina kapatilir."
        ),
        "",
        f"- status: `{financial.status}`",
        f"- spot_asset_count: `{financial.spot_asset_count}`",
        f"- spot_inventory_reportable_count_ge_2_usdt: `{len(_reportable_spot_assets(financial.spot_assets))}`",
        f"- spot_inventory_dust_omitted_count_lt_2_usdt: `{_spot_inventory_dust_omitted_count(financial.spot_assets)}`",
        f"- futures_position_count: `{financial.futures_position_count}`",
        f"- reconciliation_status: `{financial.reconciliation_status}`",
        f"- value_disclosure: `{financial.value_disclosure}`",
        f"- known_value_present: `{financial.known_value_present}`",
        f"- wallet_position_recommendation: `{brief.wallet_position_management.recommendation}`",
        f"- open_position_policy: `{brief.wallet_position_management.open_position_policy}`",
        "",
        "## Wallet / Position / Funding Recommendation",
        "",
        (
            f"- spot_open_order_count: `{brief.wallet_position_management.spot_open_order_count}`"
        ),
        (
            f"- futures_open_order_count: `{brief.wallet_position_management.futures_open_order_count}`"
        ),
        (
            f"- funding_recommendation: `{brief.wallet_position_management.funding_recommendation}`"
        ),
        "- value_disclosure_policy: `REDACTED_SUMMARY_ONLY`",
        "",
        "## Local-Only Binance Finansal Deger Eki",
        "",
        (f"- private_financial_json_path: `{brief.private_financial_json_path}`"),
        (
            f"- private_financial_markdown_path: `{brief.private_financial_markdown_path}`"
        ),
        f"- policy: `{brief.private_financial_report_policy}`",
        "- cloud_share_allowed: `false`",
        (
            "- github_cloud_blocker: `NO_GITHUB_CLOUD_SHARE; BINANCE_FINANCIAL_VALUES_PRIVATE`"
        ),
        (
            "- yonetim_notu: `Ham Binance finansal degerleri yalniz bu "
            "local-private ekte incelenir; GitHub/cloud/public rapor "
            "yuzeylerine kopyalanmaz.`"
        ),
        "",
        "## Spot Inventory Heatmap",
        "",
        (
            "- reporting_rule: `2 USDT altindaki dust varliklar "
            "public heatmap'te raporlanmaz; 2 USDT ve uzeri veya degeri kanitlanamayan "
            "varliklar yonetim/firsat izleme icin gorunur kalir. Bu kural "
            "yalniz Wallet/Value heatmap filtresidir; Spot/Futures teknik "
            "firsat tablolarini susturmaz.`"
        ),
        f"- opportunity_radar_scope: `{_OPPORTUNITY_RADAR_SCOPE_RULE}`",
    ]
    spot_inventory_rows: list[tuple[object, ...]] = []
    reportable_spot_assets = _reportable_spot_assets(financial.spot_assets)
    if not reportable_spot_assets:
        spot_inventory_rows.append(
            (
                "-",
                "UNKNOWN",
                "UNKNOWN",
                "UNKNOWN",
                "UNKNOWN",
                "NOT_PROVEN",
                "WAIT",
                "NO_REPORTABLE_ASSET_GE_2_USDT",
            )
        )
    for asset in reportable_spot_assets:
        spot_inventory_rows.append(
            (
                asset.asset,
                asset.asset_class,
                asset.free_state,
                asset.locked_state,
                asset.value_bucket,
                asset.liquidity_bucket,
                _asset_action_hint(asset),
                _asset_opportunity_review_hint(asset),
            )
        )
    lines.extend(
        _markdown_table(
            (
                "Asset",
                "Class",
                "Free",
                "Locked",
                "Value",
                "Liquidity",
                "Action",
                "Spot/Futures Firsat Yonetimi",
            ),
            spot_inventory_rows,
        )
    )
    lines.extend(
        [
            "",
            "## Internal Image Radar",
            "",
            (
                "This local-only radar stores no source image, file name, full path, "
                "or EXIF data in YKB. It presents only bounded fingerprints and review "
                "status; it cannot create trading or production authority."
            ),
            "",
            *_internal_radar_summary_lines(internal_radar),
        ]
    )
    lines.extend(
        [
            "",
            "## Open Orders",
            "",
        ]
    )
    open_order_rows: list[tuple[object, ...]] = []
    if not financial.open_orders:
        open_order_rows.append(("-", "-", "-", "-", "NONE", "UNKNOWN", "UNKNOWN"))
    for order in financial.open_orders:
        open_order_rows.append(
            (
                order.market,
                order.symbol,
                order.side,
                order.order_type,
                order.status,
                order.locked_liquidity_bucket,
                order.stale_state,
            )
        )
    lines.extend(
        _markdown_table(
            ("Market", "Symbol", "Side", "Type", "Status", "Locked Liquidity", "Stale"),
            open_order_rows,
        )
    )
    lines.extend(
        [
            "",
            "## Futures Exposure Review",
            "",
        ]
    )
    futures_position_rows: list[tuple[object, ...]] = []
    if not financial.futures_positions:
        futures_position_rows.append(
            ("-", "NONE", "ZERO", "UNKNOWN", "NO_OPEN_FUTURES_POSITION")
        )
    for position in financial.futures_positions:
        futures_position_rows.append(
            (
                position.symbol,
                position.position_side,
                position.exposure_bucket,
                position.margin_state,
                position.risk_state,
            )
        )
    lines.extend(
        _markdown_table(
            ("Symbol", "Side", "Exposure", "Margin", "Risk"),
            futures_position_rows,
        )
    )
    lines.extend(
        [
            "",
            "## Inventory Heatmap Actions",
            "",
        ]
    )
    for row in financial.inventory_heatmap:
        lines.append(
            "- "
            f"{row.inventory_group}: concentration=`{row.concentration_bucket}`, "
            f"liquidity=`{row.liquidity_bucket}`, action=`{row.action_hint}`"
        )
    lines.extend(
        [
            "",
            "## Auto-Audit ve Semi-Auto Control",
            "",
            (
                "Auto-Audit ve DGE bu raporda YKB icin denetim/duzeltme "
                "radaridir: sistem sagligi, blocker tekrarlari, privacy/financial "
                "leak kapilari ve vNext gap'leri karar talebine tasir. Bu bolum "
                "otomatik emir veya otomatik para hareketi yetkisi vermez."
            ),
            "",
            f"- auto_audit_status: `{brief.auto_audit_status}`",
            f"- auto_audit_ref: `{brief.auto_audit_ref}`",
            f"- auto_audit_recommendations: `{', '.join(brief.auto_audit_recommendations)}`",
            f"- agent_audit_status: `{brief.agent_audit_status}`",
            f"- agent_audit_ref: `{brief.agent_audit_ref}`",
            f"- agent_audit_recommendations: `{', '.join(brief.agent_audit_recommendations)}`",
            f"- recovery_radar_status: `{brief.recovery_radar_status}`",
            f"- recovery_radar_ref: `{brief.recovery_radar_ref or '-'}`",
            f"- vnext_gap_status: `{brief.vnext_gap_status}`",
            f"- vnext_gap_ref: `{brief.vnext_gap_ref or '-'}`",
            f"- vnext_gap_top_gaps: `{', '.join(brief.vnext_gap_top_gaps) or '-'}`",
            f"- management_mode: `{brief.semi_auto_control.mode}`",
            f"- workflow_pattern: `{brief.semi_auto_control.workflow_pattern}`",
            f"- blocker_resolution_order_status: `{brief.semi_auto_control.blocker_resolution_order_status}`",
            f"- risk_oos_live_gate_status: `{brief.semi_auto_control.risk_oos_live_gate_status}`",
            (
                f"- next_management_action: `{brief.semi_auto_control.next_management_action}`"
            ),
            f"- stopping_rule: `{brief.semi_auto_control.stopping_rule}`",
            "",
            "## Teknolojik Gelisme Firsatlari ve Oneriler",
            "",
            (
                "Bu bolum yalniz AI4BINANCE sistemine somut katki ihtimali olan "
                "teknoloji sinyallerini YKB'ye tasir. Kaynak GitHub, X, "
                "LinkedIn, Telegram veya baska bir provider olabilir; her satir "
                "dogrulama linki ve uygulanabilir oneri ipucu olmadan karar "
                "adayi sayilmaz."
            ),
            "",
        ]
    )
    technology_rows: list[tuple[object, ...]] = []
    if not brief.technology_opportunities:
        technology_rows.append(
            (
                "Teknolojik gelisme adayi yok",
                "runtime_research",
                "artifact://runtime_research/opportunities-latest.json",
                "KAYIT_YOK",
                "INFO",
                "Izleme surdurulur",
                "EK_ARTI_YOK",
                "EK_EKSI_YOK",
                "ONAY_GEREKMEZ",
            )
        )
    for context_item in brief.technology_opportunities:
        technology_rows.append(
            (
                context_item.title,
                context_item.source,
                context_item.source_url,
                _istanbul_time_text(context_item.as_of),
                context_item.impact,
                context_item.recommendation,
                context_item.system_benefit,
                context_item.system_tradeoff,
                context_item.ykb_approval_hint,
            )
        )
    lines.extend(
        _markdown_table(
            (
                "Ne olmus?",
                "Kim soyledi?",
                "Nereden dogrulanir?",
                "Ne zaman oldu?",
                "Etki",
                "AI4BINANCE icin ne yapilabilir?",
                "Sisteme Artisi",
                "Sisteme Eksisi",
                "YKB Onay Notu",
            ),
            technology_rows,
        )
    )
    lines.extend(
        [
            "",
            "## Onemli Haber / Sosyal Medya / Content Bilgisi",
            "",
        ]
    )
    if not brief.important_context:
        lines.append("- Kritik haber/sosyal/content bilgisi yok.")
    for context_item in brief.important_context:
        lines.extend(
            [
                (
                    f"- `{context_item.source}` kaynagi `{context_item.symbol}` "
                    f"icin `{_istanbul_time_text(context_item.as_of)}` zamanli "
                    f"`{context_item.category}` bilgisi verdi: "
                    f"{context_item.title}. Etki: "
                    f"`{context_item.impact}`."
                ),
                f"  - dogrulama_linki: `{context_item.source_url}`",
                f"  - YKB_notu: `{context_item.recommendation}`",
            ]
        )
    validation = brief.latest_validation
    lines.extend(
        [
            "",
            "## Son Backtest / Fine-Tuning Parametre Ozeti",
            "",
            f"- symbol: `{validation.symbol}`",
            f"- status: `{validation.status}`",
            f"- latest_run_id: `{validation.latest_run_id}`",
            (
                f"- backtest_run_created_at: `{_istanbul_time_text(validation.run_created_at)}`"
            ),
            f"- timeframe/playbook: `{validation.timeframe}` / `{validation.playbook}`",
            f"- promotion_status: `{validation.promotion_status}`",
            f"- metrics: `{', '.join(validation.metrics)}`",
            f"- fine_tuning_parameters: `{', '.join(validation.tuning_parameters)}`",
            f"- blockers: `{', '.join(validation.blockers) or '-'}`",
            "",
            "## Opportunity Funnel",
            "",
            *_opportunity_funnel_lines(brief.opportunities),
            "",
            "## Loss-Streak Halted Scopes",
            "",
            *_loss_streak_halted_scope_lines(
                brief.opportunities,
                validation=brief.latest_validation,
            ),
            "",
            "## Immediate Actions",
            "",
            *_loss_streak_immediate_action_lines(
                brief.opportunities,
                validation=brief.latest_validation,
            ),
            "",
            "## Spot Tarafi Firsat Plani",
            "",
        ]
    )
    spot_items = tuple(
        item
        for item in brief.opportunities
        if item.market.upper() == "SPOT" and _is_executive_trade_plan_row(item)
    )
    lines.extend(_trade_plan_table(spot_items))
    if not spot_items:
        lines.append(_empty_trade_plan_message("SPOT", brief.opportunities))
    lines.extend(
        [
            "",
            "## Futures Tarafi Firsat Plani",
            "",
        ]
    )
    futures_items = tuple(
        item
        for item in brief.opportunities
        if "FUTURES" in item.market.upper() and _is_executive_trade_plan_row(item)
    )
    lines.extend(_trade_plan_table(futures_items))
    if not futures_items:
        lines.append(_empty_trade_plan_message("USD_M_FUTURES", brief.opportunities))
    lines.extend(
        [
            "",
            "## Tum Firsatlar ve DGE Degerlendirmesi",
            "",
        ]
    )
    if not brief.opportunities:
        lines.append("- Kullanici dostu firsat yok; radar arastirma modunda kalir.")
    else:
        lines.extend(_dge_opportunity_summary_lines(brief.opportunities))
    repeat_offender_patterns = {
        pattern
        for pattern, count in Counter(
            _loss_streak_pattern_key(item)
            for item in brief.opportunities
            if "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED" in item.blockers
        ).items()
        if count > 1
    }
    for opportunity in brief.opportunities:
        lines.extend(
            [
                f"### {opportunity.symbol} - {opportunity.setup_name}",
                "",
                (
                    f"{opportunity.symbol} icin `{opportunity.timeframe}` "
                    f"timeframe'de `{opportunity.market}` tarafinda "
                    f"`{opportunity.trade_side}` yonlu arastirma firsati var. "
                    f"Kaldirac bilgisi `{opportunity.leverage}`; DGE sonucu "
                    f"`{opportunity.dge_status}` ve nihai aksiyon "
                    f"`{opportunity.governed_action}`."
                ),
                "",
                f"- headline: {opportunity.headline}",
                f"- timeframe: `{opportunity.timeframe}`",
                (
                    "- market/side/leverage: "
                    f"`{opportunity.market}` / `{opportunity.trade_side}` / "
                    f"`{opportunity.leverage}`"
                ),
                f"- requested_action: `{opportunity.requested_action}`",
                f"- governed_action: `{opportunity.governed_action}`",
                f"- dge_status: `{opportunity.dge_status}`",
                (
                    f"- score/confidence: `{opportunity.score}` / `{opportunity.confidence}`"
                ),
                f"- target_RR: `{opportunity.target_risk_reward}`",
                f"- financial_fit: `{opportunity.financial_fit}`",
                f"- funding_requirement: `{opportunity.funding_requirement}`",
                f"- required_capital_bucket: `{opportunity.required_capital_bucket}`",
                f"- free_quote_sufficiency: `{opportunity.free_quote_sufficiency}`",
                (
                    f"- manual_liquidity_preparation: `{opportunity.manual_liquidity_preparation}`"
                ),
                f"- external_capital_policy: `{opportunity.external_capital_policy}`",
                (
                    f"- conversion_or_transfer_policy: `{opportunity.conversion_or_transfer_policy}`"
                ),
                f"- next_safe_action: `{opportunity.next_safe_action}`",
                (f"- next_evidence_action: `{opportunity.next_evidence_action}`"),
                (
                    "- loss_streak_review_priority: "
                    f"`{_loss_streak_review_priority(opportunity, repeat_offender_patterns=repeat_offender_patterns)}`"
                ),
                (
                    "- loss_streak_review_rationale: "
                    f"`{_loss_streak_review_rationale(opportunity, repeat_offender_patterns=repeat_offender_patterns)}`"
                ),
                (
                    "- loss_streak_escalation_state: "
                    f"`{
                        _loss_streak_scope_escalation_state(
                            opportunity,
                            validation=brief.latest_validation,
                            repeat_offender_patterns=repeat_offender_patterns,
                        )
                    }`"
                ),
                (
                    "- loss_streak_first_action: "
                    f"`{
                        _loss_streak_scope_first_action(
                            opportunity,
                            validation=brief.latest_validation,
                            repeat_offender_patterns=repeat_offender_patterns,
                        )
                    }`"
                ),
                f"- why_now: {', '.join(opportunity.why_now[:5]) or '-'}",
                (
                    f"- confirmation_requirements: {', '.join(opportunity.confirmation_requirements[:8]) or '-'}"
                ),
                (
                    f"- promotion_requirements: {', '.join(opportunity.promotion_requirements[:8]) or '-'}"
                ),
                (
                    f"- execution_blockers: {', '.join(opportunity.execution_blockers[:8]) or '-'}"
                ),
                (
                    f"- funding_blockers: {', '.join(opportunity.funding_blockers[:8]) or '-'}"
                ),
                f"- blockers: {', '.join(opportunity.blockers[:8]) or '-'}",
                "",
            ]
        )
    lines.extend(
        [
            "## YKB Karar Talebi",
            "",
            brief.decision_request,
            "",
            "## Guvenlik",
            "",
            (
                "- Cybersecurity and leakage control: public report surfaces must "
                "be checked with `Privacy leak guard` and `Financial leak guard`; "
                "KVKK data, email addresses, wallet identifiers, raw balances, "
                "and credential-like data are blockers for GitHub/cloud sharing."
            ),
            "- `NO_GITHUB_CLOUD_SHARE` is preserved for financial/private attachments.",
            "- `RESEARCH_ONLY` is preserved.",
            "- `LIVE_ORDER_BLOCKED` is preserved.",
            (
                "- Raw credentials, secrets, or unnecessary balance details are not written to the report."
            ),
            (
                "- Human approval is mandatory for finance, trading, or money-movement actions."
            ),
            (
                "- Recommendation: this report must not be moved to the YKB "
                "publication folder until it passes privacy/financial guard, "
                "repository secret scan, artifact provenance/hash, and DGE "
                "blocker checks in the quality gate."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _executive_summary(
    status: str,
    opportunities: tuple[YkbOpportunityBrief, ...],
    blockers: tuple[str, ...],
    financial: YkbFinancialSituation,
    wallet_management: YkbWalletPositionManagement,
    validation: YkbValidationDigest,
    auto_audit_status: str,
    root: Path,
) -> str:
    if opportunities:
        focus = "; ".join(
            (
                f"{item.symbol} {item.timeframe} {item.market} {item.trade_side} RR={item.target_risk_reward}"
            )
            for item in opportunities[:3]
        )
        opportunity_sentence = (
            f"YKB radarinda {len(opportunities)} adet arastirma firsati var: "
            f"{focus}. Bunlar emir talimati degil; DGE sonucu ve blocker listesi "
            "tamamlanmadan sadece izleme/validasyon konusudur."
        )
    else:
        opportunity_sentence = (
            "YKB radar has no user-friendly Spot/Futures research candidate ready "
            "for presentation today; the system keeps discovery in research mode."
        )
    funnel: Any = _opportunity_funnel_payload(opportunities, validation)
    halted_count = int(funnel["loss_streak_halted_visible_research"])
    runtime_snapshot = _virtual_runtime_evidence_snapshot(root)
    return "\n\n".join(
        (
            (
                f"AI4BINANCE genel durum: {status}. Auto-Audit durumu "
                f"{auto_audit_status}; YKB onayina tasinan toplam blocker sayisi "
                f"{len(blockers)}. Stablecoin, wrapped ve kaldiracli token bazlari "
                "firsat kapsamindan haric tutulur."
            ),
            opportunity_sentence,
            (
                "VIRTUAL_MARKET loss-streak durdurma gorunumu: "
                f"{halted_count} gorunur aday ard arda zarar siniri nedeniyle "
                "beklemeye alinmis durumda."
            ),
            (
                "Loss-streak cluster odagi: "
                f"`{funnel['loss_streak_halted_primary_setup']}` ana tekrar eden "
                "setup olarak izleniyor."
            ),
            (
                "Pattern cluster odagi: "
                f"`{funnel['loss_streak_halted_primary_pattern']}` en baskin "
                "market/setup/side tekrar desenidir; repeat offender sayisi "
                f"{funnel['loss_streak_repeat_offender_visible_research']}."
            ),
            (
                "Oncelikli bounded halt review kuyrugu: "
                f"{_loss_streak_priority_queue_summary(opportunities)} "
                f"Wallet stress baglami: "
                f"{_loss_streak_wallet_stress_context(financial, wallet_management)}"
            ),
            (f"Wallet KPI ozeti: {_latest_validation_wallet_kpi_context(validation)}"),
            (
                f"Virtual runtime evidence ozeti: {_virtual_runtime_evidence_context(root)}"
            ),
            (
                "Virtual runtime market acceptance ozeti: "
                f"{_virtual_runtime_market_acceptance_context(root)}"
            ),
            (
                "Virtual runtime DGE effectiveness ozeti: "
                f"{_virtual_runtime_dge_effectiveness_context(root)}"
            ),
            (
                "Historical/forward Virtual Market ve wallet epoch ozeti: "
                f"{_historical_replay_evidence_context(root)} / "
                f"{_historical_replay_wallet_epoch_context(root)}"
            ),
            (
                f"Virtual runtime counterfactual note: {_virtual_runtime_counterfactual_note(runtime_snapshot)}"
            ),
            (
                f"Virtual runtime priority signal: {_virtual_runtime_priority_signal(runtime_snapshot)}"
            ),
            (
                f"Escalated risk note: {_loss_streak_escalated_risk_note(opportunities, validation)}"
            ),
            (
                "Finansal gorunum ham degerleri public raporda saklar: "
                f"spot varlik sayisi {financial.spot_asset_count}, futures acik "
                f"pozisyon sayisi {financial.futures_position_count}, mutabakat "
                f"durumu {financial.reconciliation_status}. Finansman karari icin "
                f"onerilen yol: {wallet_management.funding_recommendation}."
            ),
            (
                "Son backtest/fine-tuning kaydi "
                f"{_istanbul_time_text(validation.run_created_at)}; "
                f"durum {validation.status}, promotion {validation.promotion_status}. "
                "Canli emir, transfer, satis veya risk artisi yetkisi verilmez."
            ),
        )
    )


def _virtual_runtime_counterfactual_note(snapshot: Mapping[str, object]) -> str:
    if not bool(snapshot.get("available", False)):
        return "UNAVAILABLE (virtual runtime evidence mevcut degil)."
    pnl = snapshot.get("no_trade_counterfactual_pnl_usdt")
    risk_multiple = snapshot.get("no_trade_counterfactual_r")
    if pnl is None and risk_multiple is None:
        return "UNAVAILABLE (no-trade counterfactual KPI yayinlanmamis)."
    parts: list[str] = []
    if pnl is not None:
        parts.append(f"counterfactual_pnl_usdt=`{pnl}`")
    if risk_multiple is not None:
        parts.append(f"counterfactual_r=`{risk_multiple}`")
    return " / ".join(parts)


def _virtual_runtime_priority_signal(snapshot: Mapping[str, object]) -> str:
    if not bool(snapshot.get("available", False)):
        return "UNAVAILABLE"
    return derive_virtual_runtime_priority_signal(
        surface_kind=str(snapshot.get("surface_kind", "UNKNOWN")).strip() or "UNKNOWN",
        status=str(snapshot.get("status", "UNKNOWN")).strip() or "UNKNOWN",
        blockers=_virtual_runtime_priority_blockers(snapshot),
        has_counterfactual_pnl=snapshot.get("no_trade_counterfactual_pnl_usdt")
        is not None,
        has_counterfactual_r=snapshot.get("no_trade_counterfactual_r") is not None,
        has_net_return=snapshot.get("net_return") is not None,
        has_max_drawdown=snapshot.get("max_drawdown") is not None,
        has_oos_expectancy=snapshot.get("oos_expectancy_usdt") is not None,
    )


def _virtual_runtime_priority_blockers(
    snapshot: Mapping[str, object],
) -> tuple[str, ...]:
    combined: list[str] = []
    for key in (
        "blockers",
        "spot_acceptance_blockers",
        "futures_acceptance_blockers",
        "system_acceptance_blockers",
    ):
        for item in _sequence(snapshot.get(key)):
            blocker = str(item).strip()
            if blocker:
                combined.append(blocker)
    return tuple(dict.fromkeys(combined))


def _decision_request(
    opportunities: tuple[YkbOpportunityBrief, ...],
    blockers: tuple[str, ...],
    *,
    blocker_resolution_order_approved: bool,
) -> str:
    blocker_lines = "\n".join(
        f"{index}. `{blocker}` icin sahip atanip kanitli kapatma paketi istensin."
        for index, blocker in enumerate(blockers[:5], start=1)
    )
    if not blocker_lines:
        blocker_lines = "1. Acik blocker yoksa izleme modu ve kanit tazeleme sursun."
    if blocker_resolution_order_approved:
        return (
            "YKB karari kayitli: blocker cozum sirasi onaylandi ve ayni onay "
            "talebi bu bolumde tekrar listelenmez. Sistem onayli sirayi "
            "uygulama/izleme modunda optimize eder; risk ve OOS kaniti "
            "tamamlanana kadar live emir yetkisi verilmez. Yeni veya kapsam "
            "disi karar talebi olusursa YKB'ye ayri madde olarak tasinir."
        )
    if opportunities:
        return (
            "YKB'den beklenen karar: blocker cozum sirasini onayla, risk/OOS "
            "kaniti tamamlanana kadar live emir yetkisi verme. Firsatlar karar "
            "adayi degil; DGE tarafindan izleme/validasyon paketidir.\n\n"
            "DGE/Auto-Audit oncelikli karar listesi:\n"
            f"{blocker_lines}"
        )
    return (
        "YKB'den beklenen karar: auto-audit loop'u izleme modunda surdur ve "
        f"ilk {min(5, len(blockers))} blocker icin sorumlu aksiyon ata.\n\n"
        "DGE/Auto-Audit oncelikli karar listesi:\n"
        f"{blocker_lines}"
    )


def _requested_action(item: Mapping[str, object]) -> DgeMarketAction:
    text = " ".join(
        str(item.get(key, "")) for key in ("direction", "setup_name", "status")
    ).upper()
    if "SELL" in text or "BEAR" in text or "SHORT" in text:
        return DgeMarketAction.SELL
    if "BUY" in text or "BULL" in text or "LONG" in text:
        return DgeMarketAction.BUY
    return DgeMarketAction.HOLD


_QUOTE_SUFFIXES: tuple[str, ...] = (
    "USDT",
    "FDUSD",
    "USDC",
    "BUSD",
    "BTC",
    "ETH",
    "BNB",
    "TRY",
)
_STABLECOIN_BASES: frozenset[str] = frozenset(
    {"USDT", "USDC", "FDUSD", "BUSD", "DAI", "TUSD", "USDP", "EUR", "EURI"}
)
_WRAPPED_BASES: frozenset[str] = frozenset({"WBTC", "WETH", "WBETH", "WBNB", "WSTETH"})
_LEVERAGED_BASE_SUFFIXES: tuple[str, ...] = (
    "UP",
    "DOWN",
    "BULL",
    "BEAR",
    "3L",
    "3S",
    "5L",
    "5S",
)


def _eligible_opportunity_items(
    inbox: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    selected: dict[tuple[str, str, str, str, str], Mapping[str, object]] = {}
    order: list[tuple[str, str, str, str, str]] = []
    fallback_symbol = str(inbox.get("symbol", "UNKNOWN")).upper()
    for raw_item in _sequence(inbox.get("items")):
        item = _mapping(raw_item)
        symbol = str(item.get("symbol", fallback_symbol)).upper()
        if _is_opportunity_radar_scope_symbol(symbol):
            key = _opportunity_item_semantic_key(item, fallback_symbol)
            current = selected.get(key)
            if current is None:
                selected[key] = item
                order.append(key)
            elif _opportunity_item_rank(item) > _opportunity_item_rank(current):
                selected[key] = item
    return tuple(selected[key] for key in order)


def _opportunity_item_semantic_key(
    item: Mapping[str, object],
    fallback_symbol: str,
) -> tuple[str, str, str, str, str]:
    return (
        str(item.get("market", "SPOT")).strip().upper(),
        str(item.get("symbol", fallback_symbol)).strip().upper(),
        _timeframe_value(item).strip().upper(),
        str(item.get("setup_name", "UNKNOWN_SETUP")).strip().lower(),
        str(item.get("direction", item.get("side", "UNKNOWN"))).strip().upper(),
    )


def _opportunity_item_rank(item: Mapping[str, object]) -> tuple[Decimal, Decimal, int]:
    has_levels = int(
        all(
            _trade_plan_value(item, *keys).strip().upper() != "PENDING_VALIDATED_LEVEL"
            for keys in (
                ("stop_loss", "stop", "sl"),
                ("entry", "entry_price"),
                ("tp1", "take_profit_1", "take_profit"),
                ("tp2", "take_profit_2"),
                ("tp3", "take_profit_3"),
            )
        )
    )
    return (
        _score_decimal(item.get("score")),
        _confidence_decimal(item.get("confidence")),
        has_levels,
    )


def _opportunity_governance_blockers(
    item: Mapping[str, object],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *_text_tuple(item.get("blockers")),
                *_text_tuple(item.get("confirmation_requirements")),
                *_text_tuple(item.get("promotion_requirements")),
                *_text_tuple(item.get("execution_blockers")),
            )
        )
    )


def _is_opportunity_radar_scope_symbol(symbol: str) -> bool:
    """Return True when symbol belongs to the YKB Opportunity Radar universe.

    Wallet value, dust size, inventory heatmap visibility, funding fit, or
    portfolio availability are deliberately not checked here. Those concerns are
    reported and governed later, but they must not silence technical Spot/Futures
    opportunities for Binance coins in scope.
    """
    return not _is_ykb_excluded_symbol(symbol)


def _is_ykb_excluded_symbol(symbol: str) -> bool:
    base = _base_asset(symbol)
    if base in _STABLECOIN_BASES or base in _WRAPPED_BASES:
        return True
    return any(base.endswith(suffix) for suffix in _LEVERAGED_BASE_SUFFIXES)


def _base_asset(symbol: str) -> str:
    normalized = symbol.strip().upper()
    for quote in sorted(_QUOTE_SUFFIXES, key=len, reverse=True):
        if normalized.endswith(quote) and len(normalized) > len(quote):
            return normalized[: -len(quote)]
    return normalized


def _trade_side(
    item: Mapping[str, object],
    market: str,
    requested_action: str,
) -> str:
    text = " ".join(
        str(item.get(key, ""))
        for key in ("side", "direction", "position_side", "requested_action")
    ).upper()
    action = requested_action.upper()
    futures = "FUTURES" in market.upper()
    if futures:
        if "SHORT" in text or "BEAR" in text or action == "SELL":
            return "SHORT"
        if "LONG" in text or "BULL" in text or action == "BUY":
            return "LONG"
        return "NO_DIRECTION"
    if "SELL" in text or "BEAR" in text or action == "SELL":
        return "SELL"
    if "BUY" in text or "BULL" in text or action == "BUY":
        return "BUY"
    return "HOLD"


def _trade_leverage(item: Mapping[str, object], market: str) -> str:
    if "FUTURES" not in market.upper():
        return "1x"
    for key in ("leverage", "max_leverage", "suggested_leverage"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "NOT_APPROVED"


def _executive_opportunity_lines(
    opportunities: tuple[YkbOpportunityBrief, ...],
) -> list[str]:
    trade_ready_items = tuple(
        item for item in opportunities if _is_executive_trade_plan_row(item)
    )
    watchlist_items = tuple(
        item
        for item in opportunities
        if _is_directional_executive_candidate(item)
        and not _is_executive_trade_plan_row(item)
    )
    lines = [
        "#### Seviyeleri Hazir Trade Plan Adaylari (Live Bloklu)",
        "",
    ]
    if trade_ready_items:
        lines.extend(
            _markdown_table(
                (
                    "Koin",
                    "Timeframe",
                    "Market",
                    "Setup",
                    "Side",
                    "Leverage",
                    "RR",
                    "DGE",
                    "YKB Notu",
                ),
                tuple(
                    (
                        item.symbol,
                        item.timeframe,
                        item.market,
                        item.setup_name,
                        item.trade_side,
                        item.leverage,
                        item.target_risk_reward,
                        item.dge_status,
                        item.next_safe_action,
                    )
                    for item in trade_ready_items[:5]
                ),
                alignments=(
                    "left",
                    "left",
                    "left",
                    "left",
                    "left",
                    "left",
                    "right",
                    "left",
                    "left",
                ),
            )
        )
    else:
        lines.append(
            "Bugun YKB icin SL/E/TP seviyeleri tamamlanmis Spot/Futures trade "
            "plan adayi yok. Live emir, transfer, satis veya risk artisi "
            "yetkisi verilmez."
        )
    lines.extend(
        [
            "",
            "#### Kacirma Riski Yuksek Izleme / Validasyon Adaylari",
            "",
        ]
    )
    if not watchlist_items:
        lines.append(
            "Izleme/validasyon adayi yok; radar arastirma modunda kanit tazeler."
        )
        return lines
    lines.extend(
        _markdown_table(
            (
                "Koin",
                "Timeframe",
                "Market",
                "Setup",
                "Side",
                "Leverage",
                "Score",
                "Confidence",
                "DGE",
                "Eksik Kanit",
                "Sonraki Aksiyon",
            ),
            tuple(
                (
                    item.symbol,
                    item.timeframe,
                    item.market,
                    item.setup_name,
                    item.trade_side,
                    item.leverage,
                    item.score,
                    item.confidence,
                    item.dge_status,
                    _watchlist_gap_summary(item),
                    item.next_evidence_action,
                )
                for item in watchlist_items[:5]
            ),
            alignments=(
                "left",
                "left",
                "left",
                "left",
                "left",
                "left",
                "right",
                "right",
                "left",
                "left",
                "left",
            ),
        )
    )
    return lines


def _watchlist_gap_summary(item: YkbOpportunityBrief) -> str:
    if item.confirmation_requirements:
        return ", ".join(item.confirmation_requirements[:3])
    if item.promotion_requirements:
        return ", ".join(item.promotion_requirements[:3])
    if not _has_validated_trade_levels(item):
        return "SL/E/TP_VALIDATION_MISSING"
    if any("OOS" in blocker or "BACKTEST" in blocker for blocker in item.blockers):
        return "BACKTEST_WALK_FORWARD_OOS_MISSING"
    if any("RISK" in blocker for blocker in item.blockers):
        return "RISK_REVIEW_MISSING"
    if any(
        "RECONCILIATION" in blocker or "WALLET" in blocker for blocker in item.blockers
    ):
        return "WALLET_RECONCILIATION_MISSING"
    return "DGE_BLOCKERS_PRESENT"


def _has_validated_trade_levels(item: YkbOpportunityBrief) -> bool:
    required_levels = (
        item.stop_loss,
        item.entry,
        item.take_profit_1,
        item.take_profit_2,
        item.take_profit_3,
    )
    return all(
        value.strip().upper() != "PENDING_VALIDATED_LEVEL" for value in required_levels
    )


def _is_directional_executive_candidate(item: YkbOpportunityBrief) -> bool:
    side = item.trade_side.strip().upper()
    market = item.market.strip().upper()
    if market == "SPOT":
        return side in {"BUY", "SELL"}
    if "FUTURES" in market:
        return side in {"LONG", "SHORT"}
    return False


def _dge_opportunity_summary_lines(
    opportunities: tuple[YkbOpportunityBrief, ...],
) -> list[str]:
    lines = _markdown_table(
        (
            "Koin",
            "Timeframe",
            "Market",
            "Setup",
            "Side",
            "Leverage",
            "DGE",
            "Finansman",
            "Sonraki Guvenli Aksiyon",
        ),
        tuple(
            (
                item.symbol,
                item.timeframe,
                item.market,
                item.setup_name,
                item.trade_side,
                item.leverage,
                item.dge_status,
                item.funding_requirement,
                item.next_safe_action,
            )
            for item in opportunities
        ),
    )
    lines.append("")
    return lines


def _opportunity_funnel_lines(
    opportunities: tuple[YkbOpportunityBrief, ...],
) -> list[str]:
    payload: Any = _opportunity_funnel_payload(opportunities)
    visible = payload["visible_research_opportunities"]
    pending = payload["watchlist_or_validation_pending"]
    return [
        f"- visible_research_opportunities: `{visible}`",
        f"- spot_visible_research: `{payload['spot_visible_research']}`",
        f"- futures_visible_research: `{payload['futures_visible_research']}`",
        f"- watchlist_or_validation_pending: `{pending}`",
        (
            f"- virtual_market_ready_trade_plans: `{payload['virtual_market_ready_trade_plans']}`"
        ),
        f"- blocked_visible_research: `{payload['blocked_visible_research']}`",
        (
            f"- loss_streak_halted_visible_research: `{payload['loss_streak_halted_visible_research']}`"
        ),
        (
            f"- loss_streak_halted_spot_visible_research: `{payload['loss_streak_halted_spot_visible_research']}`"
        ),
        (
            f"- loss_streak_halted_futures_visible_research: `{payload['loss_streak_halted_futures_visible_research']}`"
        ),
        (
            f"- loss_streak_halt_review_refs: `{', '.join(payload['loss_streak_halt_review_refs']) or '-'}`"
        ),
        (
            "- loss_streak_halt_review_artifact_paths: "
            f"`{', '.join(payload['loss_streak_halt_review_artifact_paths']) or '-'}`"
        ),
        (
            "- loss_streak_halt_reviews_with_resolved_artifacts: "
            f"`{payload['loss_streak_halt_reviews_with_resolved_artifacts']}`"
        ),
        (
            "- loss_streak_halt_reviews_pending_artifact_resolution: "
            f"`{payload['loss_streak_halt_reviews_pending_artifact_resolution']}`"
        ),
        (
            f"- loss_streak_halted_primary_setup: `{payload['loss_streak_halted_primary_setup']}`"
        ),
        (
            f"- loss_streak_halted_setup_clusters: `{', '.join(payload['loss_streak_halted_setup_clusters']) or '-'}`"
        ),
        (
            f"- loss_streak_halted_primary_pattern: `{payload['loss_streak_halted_primary_pattern']}`"
        ),
        (
            "- loss_streak_halted_pattern_clusters: "
            f"`{', '.join(payload['loss_streak_halted_pattern_clusters']) or '-'}`"
        ),
        (
            "- loss_streak_repeat_offender_visible_research: "
            f"`{payload['loss_streak_repeat_offender_visible_research']}`"
        ),
        (
            f"- loss_streak_repeat_offender_scopes: `{', '.join(payload['loss_streak_repeat_offender_scopes']) or '-'}`"
        ),
        (
            f"- loss_streak_priority_queue_summary: `{payload['loss_streak_priority_queue_summary']}`"
        ),
        (
            "- loss_streak_high_escalation_visible_research: "
            f"`{payload['loss_streak_high_escalation_visible_research']}`"
        ),
        (
            f"- loss_streak_high_escalation_scopes: `{', '.join(payload['loss_streak_high_escalation_scopes']) or '-'}`"
        ),
        (
            f"- loss_streak_fragile_edge_visible_research: `{payload['loss_streak_fragile_edge_visible_research']}`"
        ),
        (
            f"- loss_streak_fragile_edge_scopes: `{', '.join(payload['loss_streak_fragile_edge_scopes']) or '-'}`"
        ),
        f"- live_eligible: `{payload['live_eligible']}`",
        f"- live_eligibility_status: `{payload['live_eligibility_status']}`",
    ]


def _loss_streak_halted_scope_lines(
    opportunities: tuple[YkbOpportunityBrief, ...],
    *,
    validation: YkbValidationDigest | None = None,
) -> list[str]:
    halted_items = tuple(
        item
        for item in opportunities
        if "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED" in item.blockers
    )
    repeat_offender_patterns = {
        pattern
        for pattern, count in Counter(
            _loss_streak_pattern_key(item) for item in halted_items
        ).items()
        if count > 1
    }
    if not halted_items:
        return [
            "Loss-streak nedeniyle durdurulan gorunur scope yok; bounded autonomy bu raporda blocker bazli izleniyor."
        ]
    return _markdown_table(
        (
            "Koin",
            "Timeframe",
            "Market",
            "Setup",
            "Side",
            "DGE",
            "Pattern",
            "Repeat Offender",
            "Review Priority",
            "Escalation State",
            "First Action",
            "Review Rationale",
            "Root Cause Summary",
            "Next Bounded Experiment",
            "Improvement Candidate",
            "Reset Criteria",
            "Halt Review Ref",
            "Artifact Path",
            "Halt Nedeni",
            "Sonraki Kanit Aksiyonu",
        ),
        tuple(
            (
                item.symbol,
                item.timeframe,
                item.market,
                item.setup_name,
                item.trade_side,
                item.dge_status,
                _loss_streak_pattern_key(item),
                _loss_streak_repeat_offender_state(
                    item,
                    repeat_offender_patterns=repeat_offender_patterns,
                ),
                _loss_streak_review_priority(
                    item,
                    repeat_offender_patterns=repeat_offender_patterns,
                ),
                _loss_streak_scope_escalation_state(
                    item,
                    validation=validation,
                    repeat_offender_patterns=repeat_offender_patterns,
                ),
                _loss_streak_scope_first_action(
                    item,
                    validation=validation,
                    repeat_offender_patterns=repeat_offender_patterns,
                ),
                _loss_streak_review_rationale(
                    item,
                    repeat_offender_patterns=repeat_offender_patterns,
                ),
                item.halt_root_cause_summary,
                item.halt_next_bounded_experiment,
                _halted_scope_improvement_candidate(item),
                _halted_scope_reset_summary(item),
                _halted_scope_review_ref(item),
                _halted_scope_artifact_path(item),
                "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",
                item.next_evidence_action,
            )
            for item in halted_items[:5]
        ),
        alignments=(
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
        ),
    )


def _loss_streak_immediate_action_lines(
    opportunities: tuple[YkbOpportunityBrief, ...],
    *,
    validation: YkbValidationDigest | None = None,
) -> list[str]:
    halted_items = tuple(
        item
        for item in opportunities
        if "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED" in item.blockers
    )
    if not halted_items:
        return [
            "Immediate escalation aksiyonu yok; bounded halt review kuyrugu normal sirada izleniyor."
        ]
    repeat_offender_patterns = {
        pattern
        for pattern, count in Counter(
            _loss_streak_pattern_key(item) for item in halted_items
        ).items()
        if count > 1
    }
    rows: list[tuple[int, str, str, str]] = []
    seen_patterns: set[str] = set()
    for item in halted_items:
        pattern = _loss_streak_pattern_key(item)
        if pattern in seen_patterns:
            continue
        seen_patterns.add(pattern)
        escalation_state = _loss_streak_scope_escalation_state(
            item,
            validation=validation,
            repeat_offender_patterns=repeat_offender_patterns,
        )
        if escalation_state not in {"HIGH_ESCALATION", "FRAGILE_EDGE_ESCALATION"}:
            continue
        first_action = _loss_streak_scope_first_action(
            item,
            validation=validation,
            repeat_offender_patterns=repeat_offender_patterns,
        )
        rows.append(
            (
                _loss_streak_escalation_rank(escalation_state),
                pattern,
                escalation_state,
                first_action,
            )
        )
    if rows:
        return [
            f"- `{pattern}` -> `{escalation_state}` / `{first_action}`"
            for _, pattern, escalation_state, first_action in sorted(
                rows,
                key=lambda item: (item[0], item[1], item[2], item[3]),
            )
        ]
    return [
        "Immediate escalation aksiyonu yok; bounded halt review kuyrugu normal sirada izleniyor."
    ]


def _serialized_opportunity_payloads(
    opportunities: tuple[YkbOpportunityBrief, ...],
    *,
    validation: YkbValidationDigest | None,
) -> list[dict[str, object]]:
    repeat_offender_patterns = {
        pattern
        for pattern, count in Counter(
            _loss_streak_pattern_key(item)
            for item in opportunities
            if "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED" in item.blockers
        ).items()
        if count > 1
    }
    serialized: list[dict[str, object]] = []
    for item in opportunities:
        payload: Any = to_primitive(item)
        payload["loss_streak_review_priority"] = _loss_streak_review_priority(
            item,
            repeat_offender_patterns=repeat_offender_patterns,
        )
        payload["loss_streak_review_rationale"] = _loss_streak_review_rationale(
            item,
            repeat_offender_patterns=repeat_offender_patterns,
        )
        payload["loss_streak_escalation_state"] = _loss_streak_scope_escalation_state(
            item,
            validation=validation,
            repeat_offender_patterns=repeat_offender_patterns,
        )
        payload["loss_streak_first_action"] = _loss_streak_scope_first_action(
            item,
            validation=validation,
            repeat_offender_patterns=repeat_offender_patterns,
        )
        serialized.append(payload)
    return serialized


def _loss_streak_pattern_key(item: YkbOpportunityBrief) -> str:
    return f"{item.market}:{item.setup_name}:{item.trade_side}"


def _loss_streak_repeat_offender_state(
    item: YkbOpportunityBrief,
    *,
    repeat_offender_patterns: set[str],
) -> str:
    if _loss_streak_pattern_key(item) in repeat_offender_patterns:
        return "REPEAT_OFFENDER"
    return "ISOLATED"


def _loss_streak_review_priority(
    item: YkbOpportunityBrief,
    *,
    repeat_offender_patterns: set[str],
) -> str:
    artifact_resolved = _halted_scope_artifact_path(item) != "ARTIFACT_PATH_UNRESOLVED"
    if _loss_streak_pattern_key(item) in repeat_offender_patterns:
        return "P1_REPEAT_PATTERN_REVALIDATION"
    if not artifact_resolved:
        return "P2_ARTIFACT_RESOLUTION_REQUIRED"
    if item.financial_fit != "VIRTUAL_MARKET_AUTONOMOUS_FIT":
        return "P3_FINANCIAL_FIT_RECHECK"
    if item.score < Decimal("65") or item.confidence < Decimal("0.60"):
        return "P4_SIGNAL_QUALITY_REVIEW"
    return "P5_STANDARD_REVIEW_QUEUE"


def _loss_streak_review_rationale(
    item: YkbOpportunityBrief,
    *,
    repeat_offender_patterns: set[str],
) -> str:
    artifact_resolved = _halted_scope_artifact_path(item) != "ARTIFACT_PATH_UNRESOLVED"
    if _loss_streak_pattern_key(item) in repeat_offender_patterns:
        return (
            "Repeated halted market/setup/side pattern requires bounded revalidation."
        )
    if not artifact_resolved:
        return (
            "Halt review artifact is unresolved and must be recovered before analysis."
        )
    if item.financial_fit != "VIRTUAL_MARKET_AUTONOMOUS_FIT":
        return (
            "Financial fit is below autonomous threshold and needs manual reassessment."
        )
    if item.score < Decimal("65") or item.confidence < Decimal("0.60"):
        return "Signal quality is weak for autonomous replay and should be reviewed."
    return (
        "Standard bounded halt review queue with resolved artifact and acceptable fit."
    )


def _loss_streak_scope_escalation_state(
    item: YkbOpportunityBrief,
    *,
    validation: YkbValidationDigest | None,
    repeat_offender_patterns: set[str],
) -> str:
    if _loss_streak_pattern_key(item) not in repeat_offender_patterns:
        return "NO_ESCALATION"
    if validation is None:
        return "ESCALATION_CONTEXT_UNAVAILABLE"
    note = _loss_streak_escalated_risk_note((item, item), validation)
    if note.startswith("HIGH_ESCALATION"):
        return "HIGH_ESCALATION"
    if note.startswith("FRAGILE_EDGE_ESCALATION"):
        return "FRAGILE_EDGE_ESCALATION"
    if note.startswith("MODERATE_ESCALATION"):
        return "MODERATE_ESCALATION"
    if note.startswith("ELEVATED_REPEAT_PATTERN"):
        return "ELEVATED_REPEAT_PATTERN"
    return "NO_ESCALATION"


def _loss_streak_scope_first_action(
    item: YkbOpportunityBrief,
    *,
    validation: YkbValidationDigest | None,
    repeat_offender_patterns: set[str],
) -> str:
    state = _loss_streak_scope_escalation_state(
        item,
        validation=validation,
        repeat_offender_patterns=repeat_offender_patterns,
    )
    if state == "HIGH_ESCALATION":
        return "FREEZE_PATTERN_AND_RUN_ROOT_CAUSE_REVALIDATION"
    if state == "FRAGILE_EDGE_ESCALATION":
        return "KEEP_EDGE_GUARDED_AND_RUN_PROTECTIVE_REVALIDATION"
    if state == "MODERATE_ESCALATION":
        return "REVALIDATE_PATTERN_BEFORE_NEXT_AUTONOMOUS_CYCLE"
    if state == "ELEVATED_REPEAT_PATTERN":
        return "RESTORE_DRAWDOWN_CONTEXT_AND_RECHECK_PATTERN"
    if state == "ESCALATION_CONTEXT_UNAVAILABLE":
        return "RESTORE_VALIDATION_CONTEXT_BEFORE_ESCALATION_TRIAGE"
    return "STANDARD_BOUNDED_REVIEW"


def _loss_streak_escalation_rank(state: str) -> int:
    if state == "HIGH_ESCALATION":
        return 1
    if state == "FRAGILE_EDGE_ESCALATION":
        return 2
    if state == "MODERATE_ESCALATION":
        return 3
    if state == "ELEVATED_REPEAT_PATTERN":
        return 4
    if state == "ESCALATION_CONTEXT_UNAVAILABLE":
        return 5
    return 99


def _loss_streak_priority_rank(priority: str) -> int:
    if priority.startswith("P1_"):
        return 1
    if priority.startswith("P2_"):
        return 2
    if priority.startswith("P3_"):
        return 3
    if priority.startswith("P4_"):
        return 4
    if priority.startswith("P5_"):
        return 5
    return 99


def _loss_streak_priority_queue_summary(
    opportunities: tuple[YkbOpportunityBrief, ...],
) -> str:
    halted_items = tuple(
        item
        for item in opportunities
        if "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED" in item.blockers
    )
    if not halted_items:
        return "aktif review adayi yok."
    repeat_offender_patterns = {
        pattern
        for pattern, count in Counter(
            _loss_streak_pattern_key(item) for item in halted_items
        ).items()
        if count > 1
    }
    candidates: list[tuple[int, str, str]] = []
    seen_patterns: set[str] = set()
    for item in halted_items:
        pattern = _loss_streak_pattern_key(item)
        if pattern in seen_patterns:
            continue
        seen_patterns.add(pattern)
        priority = _loss_streak_review_priority(
            item,
            repeat_offender_patterns=repeat_offender_patterns,
        )
        candidates.append(
            (
                _loss_streak_priority_rank(priority),
                pattern,
                priority,
            )
        )
    top_candidates = sorted(
        candidates,
        key=lambda item: (item[0], item[1], item[2]),
    )[:3]
    return "; ".join(
        f"`{pattern}` -> `{priority}`" for _, pattern, priority in top_candidates
    )


def _loss_streak_wallet_stress_context(
    financial: YkbFinancialSituation,
    wallet_management: YkbWalletPositionManagement,
) -> str:
    total_open_orders = (
        financial.open_order_count
        + wallet_management.spot_open_order_count
        + wallet_management.futures_open_order_count
    )
    if (
        financial.reconciliation_status != "CLEAN"
        or not financial.known_value_present
        or "BLOCKED" in wallet_management.funding_recommendation
    ):
        return (
            "HIGH_WALLET_STRESS (`reconciliation_status`/value visibility/funding "
            "readiness bounded review hizini kisitliyor)."
        )
    if total_open_orders >= 2 or financial.futures_position_count > 0:
        return "MODERATE_WALLET_STRESS (acik emir veya futures pozisyon yogunlugu inceleme siralamasini etkileyebilir)."
    return "LOW_WALLET_STRESS (wallet mutabakati temiz; bounded halt review kuyrugu daha dogrudan islenebilir)."


def _latest_validation_metric_value(
    validation: YkbValidationDigest,
    metric_name: str,
) -> str | None:
    target = metric_name.strip().lower()
    for metric in validation.metrics:
        left, separator, right = metric.partition("=")
        if separator != "=":
            continue
        if left.strip().lower() != target:
            continue
        value = right.strip()
        if value:
            return value
    return None


def _latest_validation_wallet_kpi_context(validation: YkbValidationDigest) -> str:
    net_return = _latest_validation_metric_value(validation, "net_return")
    trade_count = _latest_validation_metric_value(validation, "trade_count")
    max_drawdown = _latest_validation_metric_value(validation, "max_drawdown")
    if net_return is None and trade_count is None and max_drawdown is None:
        return "UNAVAILABLE (`latest_validation.metrics` icinde wallet-performans ozeti yayinlanmamis)."
    parts: list[str] = []
    if net_return is not None:
        parts.append(f"net_return=`{net_return}`")
    if max_drawdown is not None:
        parts.append(f"max_drawdown=`{max_drawdown}`")
    if trade_count is not None:
        parts.append(f"trade_count=`{trade_count}`")
    return " / ".join(parts)


def _virtual_runtime_evidence_context(root: Path) -> str:
    snapshot = _virtual_runtime_evidence_snapshot(root)
    if not snapshot["available"]:
        return str(snapshot["summary"])
    if snapshot["market_acceptance_available"]:
        return (
            f"surface=`{snapshot['surface_kind']}` / status=`{snapshot['status']}` / "
            f"gate_eligible=`{snapshot['telemetry_gate_eligible']}` / "
            f"spot_acceptance_status=`{snapshot['spot_acceptance_status']}` / "
            f"spot_acceptance_blockers=`{snapshot['spot_acceptance_blockers_summary']}` / "
            f"futures_acceptance_status=`{snapshot['futures_acceptance_status']}` / "
            f"futures_acceptance_blockers=`{snapshot['futures_acceptance_blockers_summary']}` / "
            f"system_acceptance_status=`{snapshot['system_acceptance_status']}` / "
            f"system_acceptance_blockers=`{snapshot['system_acceptance_blockers_summary']}` / "
            f"system_blocked_markets=`{snapshot['system_acceptance_blocked_markets_summary']}` / "
            f"improvement_candidates=`{snapshot['improvement_candidate_count']}` / "
            f"{snapshot['metrics_summary']}"
        )
    return (
        f"surface=`{snapshot['surface_kind']}` / status=`{snapshot['status']}` / "
        f"gate_eligible=`{snapshot['telemetry_gate_eligible']}` / "
        f"acceptance_count=`{snapshot['acceptance_count']}` / "
        f"improvement_candidates=`{snapshot['improvement_candidate_count']}` / "
        f"{snapshot['metrics_summary']}"
    )


def _virtual_runtime_market_acceptance_context(root: Path) -> str:
    artifact_dir = root / "runtime" / "artifacts" / "user_reports" / "virtual_evidence"
    snapshot = _virtual_runtime_market_acceptance_snapshot(artifact_dir)
    if not snapshot["market_acceptance_available"]:
        return (
            "UNAVAILABLE (spot/futures market-specific evidence payloads bulunamadi)."
        )
    return (
        f"spot_acceptance_status=`{snapshot['spot_acceptance_status']}` / "
        f"spot_acceptance_blockers=`{snapshot['spot_acceptance_blockers_summary']}` / "
        f"futures_acceptance_status=`{snapshot['futures_acceptance_status']}` / "
        f"futures_acceptance_blockers=`{snapshot['futures_acceptance_blockers_summary']}` / "
        f"system_acceptance_status=`{snapshot['system_acceptance_status']}` / "
        f"system_acceptance_blockers=`{snapshot['system_acceptance_blockers_summary']}` / "
        f"system_blocked_markets=`{snapshot['system_acceptance_blocked_markets_summary']}`"
    )


def _virtual_runtime_dge_effectiveness_context(root: Path) -> str:
    """Render separate Spot/Futures DGE evidence from canonical market payloads."""

    artifact_dir = root / "runtime" / "artifacts" / "user_reports" / "virtual_evidence"
    market_paths = (
        (
            "SPOT",
            artifact_dir / "virtual_research_spot_evidence_latest.json",
        ),
        (
            "USD_M_FUTURES",
            artifact_dir / "virtual_research_usd_m_futures_evidence_latest.json",
        ),
    )
    summaries: list[str] = []
    for market, path in market_paths:
        payload = _read_json_mapping(path)
        dge = _mapping(payload.get("dge_effectiveness")) if payload else {}
        if not dge:
            summaries.append(f"{market}=`UNAVAILABLE`")
            continue
        status = str(dge.get("status", "NOT_EVALUABLE")).strip()
        rules = tuple(_mapping(item) for item in _sequence(dge.get("rule_metrics")))
        useful_rules = (
            ",".join(
                str(rule.get("rule_id", "")).strip()
                for rule in rules
                if rule.get("status") == "EFFECTIVE"
                and str(rule.get("rule_id", "")).strip()
            )
            or "-"
        )
        review_rules = (
            ",".join(
                str(rule.get("rule_id", "")).strip()
                for rule in rules
                if rule.get("status") in {"INEFFECTIVE", "MIXED"}
                and str(rule.get("rule_id", "")).strip()
            )
            or "-"
        )
        summaries.append(
            f"{market}:status=`{status}` / "
            f"net_protection_value_usdt=`{dge.get('net_protection_value_usdt', '-')}` / "
            f"block_precision=`{dge.get('block_precision', '-')}` / "
            f"false_block_rate=`{dge.get('false_block_rate', '-')}` / "
            f"counterfactual_coverage=`{dge.get('counterfactual_coverage', '-')}` / "
            f"replay_match_rate=`{dge.get('replay_match_rate', '-')}` / "
            f"top_useful_rules=`{useful_rules}` / "
            f"top_harmful_or_review_rules=`{review_rules}`"
        )
    if all(summary.endswith("`UNAVAILABLE`") for summary in summaries):
        return "UNAVAILABLE (market-specific DGE effectiveness evidence bulunamadi)."
    return " || ".join(summaries)


def _historical_replay_evidence_context(root: Path) -> str:
    """Render market-isolated replay KPIs and keep forward evidence explicit."""

    payload = _read_json_mapping(
        root
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "historical_replay"
        / "historical_replay_system_evaluation_latest.json"
    )
    if (
        not payload
        or payload.get("schema_version") != "HistoricalReplaySystemEvaluation/v1"
        or payload.get("evidence_class") != "HISTORICAL_REPLAY"
    ):
        return "HISTORICAL_REPLAY=`UNAVAILABLE` / FORWARD_VIRTUAL=`UNAVAILABLE`"
    market_payloads = {
        str(item.get("market", "")).strip().upper(): item
        for item in (_mapping(value) for value in _sequence(payload.get("markets")))
    }
    expected = ("SPOT", "USD_M_FUTURES")
    if set(market_payloads) != set(expected):
        return (
            "HISTORICAL_REPLAY=`BLOCKED:MARKET_EVIDENCE_INCOMPLETE` / "
            "FORWARD_VIRTUAL=`UNAVAILABLE`"
        )
    summaries: list[str] = []
    for market in expected:
        item = market_payloads[market]
        performance = _mapping(item.get("performance"))
        portfolio = _mapping(performance.get("portfolio_performance"))
        common = _historical_replay_metric_values(performance.get("common_kpis"))
        specific = _historical_replay_metric_values(
            performance.get("market_specific_kpis")
        )
        acceptance = _mapping(item.get("acceptance"))
        dge = _mapping(item.get("dge_effectiveness"))
        direction_metric = (
            f"buy_count=`{specific.get('buy_count', '-')}` / "
            f"sell_count=`{specific.get('sell_count', '-')}`"
            if market == "SPOT"
            else (
                f"long_count=`{specific.get('long_count', '-')}` / "
                f"short_count=`{specific.get('short_count', '-')}` / "
                f"funding_pnl=`{specific.get('funding_pnl', '-')}` / "
                f"liquidation_count=`{specific.get('liquidation_count', '-')}`"
            )
        )
        summaries.append(
            f"{market}:initial=`{portfolio.get('starting_equity_usdt', '-')}` / "
            f"equity=`{portfolio.get('ending_equity_usdt', '-')}` / "
            f"net_return=`{portfolio.get('net_return', '-')}` / "
            f"max_drawdown=`{portfolio.get('max_drawdown', '-')}` / "
            f"expectancy=`{common.get('expectancy_usdt', '-')}` / "
            f"trade_count=`{common.get('trade_count', '-')}` / "
            f"acceptance=`{acceptance.get('status', 'UNAVAILABLE')}` / "
            f"dge=`{dge.get('status', 'NOT_EVALUABLE')}` / {direction_metric}"
        )
    forward_status = _forward_virtual_evidence_status(root)
    return (
        f"HISTORICAL_REPLAY=`AVAILABLE` run_id=`{payload.get('run_id', '-')}` / "
        + " || ".join(summaries)
        + f" / FORWARD_VIRTUAL=`{forward_status}`"
    )


def _historical_replay_metric_values(value: object) -> dict[str, object]:
    metrics: dict[str, object] = {}
    for item in (_mapping(raw) for raw in _sequence(value)):
        metric_id = str(item.get("metric_id", "")).strip()
        if metric_id:
            metrics[metric_id] = (
                item.get("value")
                if item.get("status") == "AVAILABLE"
                else "INSUFFICIENT_DATA"
            )
    return metrics


def _forward_virtual_evidence_status(root: Path) -> str:
    artifact_dir = root / "runtime" / "artifacts" / "user_reports" / "virtual_evidence"
    payloads = tuple(
        _read_json_mapping(path)
        for path in (
            artifact_dir / "virtual_research_spot_evidence_latest.json",
            artifact_dir / "virtual_research_usd_m_futures_evidence_latest.json",
        )
    )
    return (
        "AVAILABLE"
        if len(payloads) == 2
        and all(
            payload is not None and payload.get("evidence_class") == "FORWARD_VIRTUAL"
            for payload in payloads
        )
        else "UNAVAILABLE"
    )


def _historical_replay_wallet_epoch_context(root: Path) -> str:
    """Render current, previous, and lifetime epoch evidence without masking."""

    evaluation = _read_json_mapping(
        root
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "historical_replay"
        / "historical_replay_system_evaluation_latest.json"
    )
    if not evaluation:
        return "CURRENT_WALLET_EPOCH=`UNAVAILABLE`"
    run_id = str(evaluation.get("run_id", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id):
        return "CURRENT_WALLET_EPOCH=`BLOCKED:INVALID_RUN_ID`"
    evaluation_epochs = {
        str(item.get("market", "")).strip().upper(): _mapping(item.get("wallet_epoch"))
        for item in (_mapping(raw) for raw in _sequence(evaluation.get("markets")))
    }
    history_path = (
        root
        / "runtime"
        / "artifacts"
        / "research"
        / "historical_replay"
        / "wallet_epochs"
        / "reset_history"
        / f"{run_id}.jsonl"
    )
    if not history_path.exists():
        current = " || ".join(
            _wallet_epoch_identity(market, evaluation_epochs.get(market, {}))
            for market in ("SPOT", "USD_M_FUTURES")
        )
        return (
            f"CURRENT_WALLET_EPOCH={current} / "
            "PREVIOUS_EPOCH_SUMMARY=`UNAVAILABLE:NO_RESET` / "
            "LIFETIME_VIRTUAL_HISTORY=`1 epoch per market`"
        )
    try:
        JsonlAuditStore(
            history_path,
            durable=True,
            tamper_evident=True,
        ).verify_chain()
        lines = read_bounded_jsonl_tail(
            history_path,
            max_lines=100_000,
            max_bytes=64 * 1024 * 1024,
        )
        records = tuple(_mapping(json.loads(line.decode("utf-8"))) for line in lines)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return "CURRENT_WALLET_EPOCH=`BLOCKED:RESET_HISTORY_INVALID`"
    reset_payloads = tuple(
        _mapping(record.get("payload"))
        for record in records
        if record.get("event_type") == "HISTORICAL_REPLAY_WALLET_RESET"
    )
    if not reset_payloads:
        return "CURRENT_WALLET_EPOCH=`BLOCKED:RESET_EVENT_UNAVAILABLE`"
    latest = reset_payloads[-1]
    current_epochs = {
        str(item.get("market", "")).strip().upper(): item
        for item in (_mapping(raw) for raw in _sequence(latest.get("new_epochs")))
    }
    previous = {
        str(item.get("market", "")).strip().upper(): item
        for item in (
            _mapping(raw) for raw in _sequence(latest.get("previous_epoch_summaries"))
        )
    }
    current_text = " || ".join(
        _wallet_epoch_identity(market, current_epochs.get(market, {}))
        for market in ("SPOT", "USD_M_FUTURES")
    )
    previous_text = " || ".join(
        f"{market}:ending_equity=`{previous.get(market, {}).get('ending_equity_usdt', '-')}`"
        for market in ("SPOT", "USD_M_FUTURES")
    )
    return (
        f"CURRENT_WALLET_EPOCH={current_text} / "
        f"PREVIOUS_EPOCH_SUMMARY={previous_text} / "
        f"LIFETIME_VIRTUAL_HISTORY=`{len(reset_payloads) + 1} epochs per market`"
    )


def _wallet_epoch_identity(market: str, epoch: Mapping[str, object]) -> str:
    return (
        f"{market}:epoch_id=`{epoch.get('epoch_id', 'UNAVAILABLE')}` / "
        f"initial_capital=`{epoch.get('initial_capital_usdt', '-')}` / "
        f"segment=`{epoch.get('system_segment_sha256', '-')}` / "
        f"evidence_class=`{epoch.get('evidence_class', '-')}`"
    )


def _virtual_runtime_evidence_snapshot(root: Path) -> dict[str, object]:
    artifact_dir = root / "runtime" / "artifacts" / "user_reports" / "virtual_evidence"
    if not artifact_dir.exists():
        return {
            "available": False,
            "summary": "UNAVAILABLE (`runtime/artifacts/user_reports/virtual_evidence` bulunamadi).",
            "surface_kind": "UNAVAILABLE",
            "status": "UNAVAILABLE",
            "telemetry_gate_eligible": False,
            "acceptance_count": 0,
            "improvement_candidate_count": 0,
            "blockers": [],
            "blockers_summary": "-",
            "metrics_summary": "metrics=`UNAVAILABLE`",
            "metrics": {},
            "net_return": None,
            "max_drawdown": None,
            "oos_expectancy_usdt": None,
            "no_trade_counterfactual_pnl_usdt": None,
            "no_trade_counterfactual_r": None,
            **_virtual_runtime_market_acceptance_snapshot(artifact_dir),
        }
    candidates = (
        artifact_dir / "virtual_research_evidence_latest.json",
        artifact_dir / "virtual_no_trade_evidence_latest.json",
    )
    for path in candidates:
        payload = _read_json_mapping(path)
        if payload is None:
            continue
        surface_kind = str(payload.get("surface_kind", "UNKNOWN")).strip() or "UNKNOWN"
        status = str(payload.get("status", "UNKNOWN")).strip() or "UNKNOWN"
        gate = bool(payload.get("telemetry_gate_eligible", False))
        acceptance_results = _sequence(payload.get("acceptance_results"))
        improvement_candidate_ids = _sequence(payload.get("improvement_candidate_ids"))
        blockers = tuple(
            str(item).strip()
            for item in _sequence(payload.get("blockers"))
            if str(item).strip()
        )
        metric_summary = _mapping(payload.get("telemetry_metric_summary"))
        normalized_metrics = _normalized_virtual_runtime_metrics(metric_summary)
        metric_parts: list[str] = []
        net_return = _telemetry_metric_summary_value(
            metric_summary,
            "virtual.net_return",
        )
        max_drawdown = _telemetry_metric_summary_value(
            metric_summary,
            "virtual.max_drawdown",
        )
        oos_expectancy = _telemetry_metric_summary_value(
            metric_summary,
            "virtual.oos_expectancy_usdt",
        )
        no_trade_counterfactual_pnl_usdt = _telemetry_metric_summary_value(
            metric_summary,
            "virtual.no_trade_counterfactual_pnl_usdt",
        )
        no_trade_counterfactual_r = _telemetry_metric_summary_value(
            metric_summary,
            "virtual.no_trade_counterfactual_r",
        )
        completed_trades = _telemetry_metric_summary_value(
            metric_summary,
            "virtual.completed_trades",
        )
        daily_sharpe = _telemetry_metric_summary_value(
            metric_summary,
            "virtual.daily_sharpe",
        )
        profit_factor = _telemetry_metric_summary_value(
            metric_summary,
            "virtual.profit_factor",
        )
        win_rate = _telemetry_metric_summary_value(
            metric_summary,
            "virtual.win_rate",
        )
        average_r = _telemetry_metric_summary_value(
            metric_summary,
            "virtual.average_r",
        )
        if net_return is not None:
            metric_parts.append(f"net_return=`{net_return}`")
        if max_drawdown is not None:
            metric_parts.append(f"max_drawdown=`{max_drawdown}`")
        if oos_expectancy is not None:
            metric_parts.append(f"oos_expectancy_usdt=`{oos_expectancy}`")
        if completed_trades is not None:
            metric_parts.append(f"completed_trades=`{completed_trades}`")
        if daily_sharpe is not None:
            metric_parts.append(f"daily_sharpe=`{daily_sharpe}`")
        if profit_factor is not None:
            metric_parts.append(f"profit_factor=`{profit_factor}`")
        if win_rate is not None:
            metric_parts.append(f"win_rate=`{win_rate}`")
        if average_r is not None:
            metric_parts.append(f"average_r=`{average_r}`")
        if no_trade_counterfactual_pnl_usdt is not None:
            metric_parts.append(
                f"no_trade_counterfactual_pnl_usdt=`{no_trade_counterfactual_pnl_usdt}`"
            )
        if no_trade_counterfactual_r is not None:
            metric_parts.append(
                f"no_trade_counterfactual_r=`{no_trade_counterfactual_r}`"
            )
        metrics_text = " / ".join(metric_parts) or "metrics=`UNAVAILABLE`"
        market_snapshot = _virtual_runtime_market_acceptance_snapshot(artifact_dir)
        return {
            "available": True,
            "summary": (
                f"surface=`{surface_kind}` / status=`{status}` / "
                f"gate_eligible=`{gate}` / acceptance_count=`{len(acceptance_results)}` / "
                f"improvement_candidates=`{len(improvement_candidate_ids)}` / "
                f"{metrics_text}"
            ),
            "surface_kind": surface_kind,
            "status": status,
            "telemetry_gate_eligible": gate,
            "acceptance_count": len(acceptance_results),
            "improvement_candidate_count": len(improvement_candidate_ids),
            "blockers": list(blockers),
            "blockers_summary": ", ".join(blockers) or "-",
            "metrics_summary": metrics_text,
            "metrics": normalized_metrics,
            "net_return": net_return,
            "max_drawdown": max_drawdown,
            "oos_expectancy_usdt": oos_expectancy,
            "completed_trades": completed_trades,
            "daily_sharpe": daily_sharpe,
            "profit_factor": profit_factor,
            "win_rate": win_rate,
            "average_r": average_r,
            "no_trade_counterfactual_pnl_usdt": no_trade_counterfactual_pnl_usdt,
            "no_trade_counterfactual_r": no_trade_counterfactual_r,
            **market_snapshot,
        }
    return {
        "available": False,
        "summary": "UNAVAILABLE (virtual evidence latest payload okunamadi).",
        "surface_kind": "UNAVAILABLE",
        "status": "UNAVAILABLE",
        "telemetry_gate_eligible": False,
        "acceptance_count": 0,
        "improvement_candidate_count": 0,
        "blockers": [],
        "blockers_summary": "-",
        "metrics_summary": "metrics=`UNAVAILABLE`",
        "metrics": {},
        "net_return": None,
        "max_drawdown": None,
        "oos_expectancy_usdt": None,
        "completed_trades": None,
        "daily_sharpe": None,
        "profit_factor": None,
        "win_rate": None,
        "average_r": None,
        "no_trade_counterfactual_pnl_usdt": None,
        "no_trade_counterfactual_r": None,
        **_virtual_runtime_market_acceptance_snapshot(artifact_dir),
    }


def _virtual_runtime_market_acceptance_snapshot(report_dir: Path) -> dict[str, object]:
    """Read market-specific research evidence and derive the system acceptance view."""

    market_paths = (
        (
            VirtualMarket.SPOT,
            report_dir / "virtual_research_spot_evidence_latest.json",
        ),
        (
            VirtualMarket.USD_M_FUTURES,
            report_dir / "virtual_research_usd_m_futures_evidence_latest.json",
        ),
    )
    market_results: dict[VirtualMarket, MarketAcceptanceResult] = {}
    for market, path in market_paths:
        payload = _read_json_mapping(path)
        if payload is None:
            continue
        result = _virtual_runtime_market_acceptance_result(payload, market, path)
        if result is not None:
            market_results[market] = result
    if len(market_results) != 2:
        return {
            "market_acceptance_available": False,
            "spot_acceptance_status": "UNAVAILABLE",
            "spot_acceptance_blockers": [],
            "spot_acceptance_blockers_summary": "UNAVAILABLE",
            "futures_acceptance_status": "UNAVAILABLE",
            "futures_acceptance_blockers": [],
            "futures_acceptance_blockers_summary": "UNAVAILABLE",
            "system_acceptance_status": "UNAVAILABLE",
            "system_acceptance_blockers": [],
            "system_acceptance_blockers_summary": "UNAVAILABLE",
            "system_acceptance_blocked_markets": [],
            "system_acceptance_blocked_markets_summary": "UNAVAILABLE",
        }
    spot_result = market_results[VirtualMarket.SPOT]
    futures_result = market_results[VirtualMarket.USD_M_FUTURES]
    system = SystemResearchAcceptance.derive(spot_result, futures_result)
    blocked_markets = tuple(
        market.value
        for market, result in (
            (VirtualMarket.SPOT, spot_result),
            (VirtualMarket.USD_M_FUTURES, futures_result),
        )
        if result.status is not AcceptanceStatus.PASS
    )
    return {
        "market_acceptance_available": True,
        "spot_acceptance_status": spot_result.status.value,
        "spot_acceptance_blockers": list(spot_result.blockers),
        "spot_acceptance_blockers_summary": ", ".join(spot_result.blockers) or "-",
        "futures_acceptance_status": futures_result.status.value,
        "futures_acceptance_blockers": list(futures_result.blockers),
        "futures_acceptance_blockers_summary": ", ".join(futures_result.blockers)
        or "-",
        "system_acceptance_status": system.status.value,
        "system_acceptance_blockers": list(system.blockers),
        "system_acceptance_blockers_summary": ", ".join(system.blockers) or "-",
        "system_acceptance_blocked_markets": list(blocked_markets),
        "system_acceptance_blocked_markets_summary": ", ".join(blocked_markets) or "-",
    }


def _virtual_runtime_market_acceptance_result(
    payload: Mapping[str, object],
    market: VirtualMarket,
    path: Path,
) -> MarketAcceptanceResult | None:
    acceptance_results = _sequence(payload.get("acceptance_results"))
    explicit_result = _mapping(payload.get("market_acceptance_result"))
    primary_result = (
        explicit_result
        if explicit_result
        else _mapping(acceptance_results[0])
        if acceptance_results
        else {}
    )
    status_text = str(
        primary_result.get("status", payload.get("status", "UNKNOWN"))
    ).strip()
    if not status_text:
        status_text = "UNKNOWN"
    try:
        status = AcceptanceStatus(status_text)
    except ValueError:
        return None
    blockers = tuple(
        str(blocker).strip()
        for blocker in _sequence(primary_result.get("blockers"))
        if str(blocker).strip()
    )
    if status is AcceptanceStatus.PASS and blockers:
        return None
    if status is not AcceptanceStatus.PASS and not blockers:
        return None
    evidence_refs = tuple(
        ref
        for ref in dict.fromkeys(
            (
                str(payload.get("snapshot_id", "")).strip(),
                str(payload.get("telemetry_id", "")).strip(),
                str(primary_result.get("result_id", "")).strip(),
                path.stem,
            )
        )
        if ref
    )
    if not evidence_refs:
        return None
    policy_id = (
        str(
            payload.get("acceptance_policy_id", "virtual-market-research-acceptance-v1")
        ).strip()
        or "virtual-market-research-acceptance-v1"
    )
    try:
        return MarketAcceptanceResult(
            market=market,
            status=status,
            blockers=blockers,
            evidence_refs=evidence_refs,
            policy_id=policy_id,
        )
    except ValueError:
        return None


def _normalized_virtual_runtime_metrics(
    metric_summary: Mapping[str, object],
) -> dict[str, dict[str, str]]:
    normalized: dict[str, dict[str, str]] = {}
    for metric_id in sorted(metric_summary):
        raw_metric = metric_summary[metric_id]
        metric = _mapping(raw_metric)
        key = str(metric_id).strip()
        if not key:
            continue
        short_name = key.split(".")[-1].strip()
        if not short_name:
            continue
        value = str(metric.get("value", "")).strip()
        unit = str(metric.get("unit", "")).strip()
        normalized[short_name] = {
            "metric_id": key,
            "value": value,
            "unit": unit,
        }
    return normalized


def _telemetry_metric_summary_value(
    metric_summary: Mapping[str, object],
    metric_id: str,
) -> str | None:
    metric = _mapping(metric_summary.get(metric_id))
    value = str(metric.get("value", "")).strip()
    if value:
        return value
    return None


def _loss_streak_escalated_risk_note(
    opportunities: tuple[YkbOpportunityBrief, ...],
    validation: YkbValidationDigest,
) -> str:
    funnel: Any = _opportunity_funnel_payload(opportunities)
    repeat_offender_count = int(funnel["loss_streak_repeat_offender_visible_research"])
    max_drawdown_text = _latest_validation_metric_value(validation, "max_drawdown")
    net_return_text = _latest_validation_metric_value(validation, "net_return")
    if repeat_offender_count < 1:
        if max_drawdown_text is None:
            return "UNAVAILABLE (repeat offender yok; max_drawdown metric'i yayinlanmamis)."
        return f"LOW_ESCALATION (repeat offender yok; max_drawdown=`{max_drawdown_text}` izleme amacli tutuluyor)."
    if max_drawdown_text is None:
        return "ELEVATED_REPEAT_PATTERN (repeat offender var; max_drawdown metric'i olmadan bounded risk notu kisitli)."
    try:
        max_drawdown = Decimal(max_drawdown_text)
    except InvalidOperation:
        return "ELEVATED_REPEAT_PATTERN (repeat offender var; max_drawdown metric'i gecersiz formatta)."
    net_return: Decimal | None = None
    if net_return_text is not None:
        try:
            net_return = Decimal(net_return_text)
        except InvalidOperation:
            net_return = None
    if max_drawdown >= Decimal("0.10"):
        if net_return is not None and net_return < Decimal("0"):
            return (
                "HIGH_ESCALATION (repeat offender + "
                f"max_drawdown=`{max_drawdown_text}` + net_return=`{net_return_text}` "
                "negatif; bounded revalidation ve root-cause incelemesi hizlandirilmali)."
            )
        if net_return is not None and net_return > Decimal("0"):
            return (
                "FRAGILE_EDGE_ESCALATION (repeat offender + "
                f"max_drawdown=`{max_drawdown_text}` yuksek ama net_return=`{net_return_text}` "
                "pozitif; edge kirilgan olabilir ve koruyucu yeniden validasyon gerekli)."
            )
        return (
            f"HIGH_ESCALATION (repeat offender + max_drawdown=`{max_drawdown_text}` "
            "birlikte goruluyor; bounded revalidation sirasi hizlandirilmali)."
        )
    if net_return is not None and net_return < Decimal("0"):
        return (
            "MODERATE_ESCALATION (repeat offender var; "
            f"net_return=`{net_return_text}` negatif ve max_drawdown=`{max_drawdown_text}` "
            "kritik esik alti olsa da pattern yeniden validasyona alinmali)."
        )
    return (
        f"MODERATE_ESCALATION (repeat offender var; max_drawdown=`{max_drawdown_text}` "
        "esigi kritik degil ama pattern yeniden validasyona alinmali)."
    )


def _halted_scope_improvement_candidate(item: YkbOpportunityBrief) -> str:
    hint = item.improvement_candidate_hint.strip()
    if hint and hint != "HALT_REVIEW_PENDING":
        return hint
    return f"improvement:loss-streak:{item.setup_name}:{item.market.lower()}:{item.timeframe.lower()}"


def _halted_scope_reset_summary(item: YkbOpportunityBrief) -> str:
    if item.halt_reset_criteria:
        return ", ".join(item.halt_reset_criteria[:2])
    if item.confirmation_requirements:
        return ", ".join(item.confirmation_requirements[:2])
    if item.promotion_requirements:
        return ", ".join(item.promotion_requirements[:2])
    return "bounded reset pending fresh validation evidence"


def _halted_scope_review_ref(item: YkbOpportunityBrief) -> str:
    review_ref = item.halt_review_ref.strip()
    if review_ref and review_ref != "ARTIFACT_REF_NOT_PUBLISHED":
        return review_ref
    return f"virtual-loss-streak-halt:{item.symbol.lower()}:{item.market.lower()}:{item.timeframe.lower()}"


def _halted_scope_artifact_path(item: YkbOpportunityBrief) -> str:
    artifact_path = item.halt_review_artifact_path.strip()
    if artifact_path and artifact_path != "ARTIFACT_PATH_UNRESOLVED":
        return artifact_path
    return "ARTIFACT_PATH_UNRESOLVED"


def _opportunity_funnel_payload(
    opportunities: tuple[YkbOpportunityBrief, ...],
    validation: YkbValidationDigest | None = None,
) -> dict[str, object]:
    halted_items = tuple(
        item
        for item in opportunities
        if "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED" in item.blockers
    )
    visible = len(opportunities)
    paper_ready = sum(1 for item in opportunities if _is_executive_trade_plan_row(item))
    watchlist = sum(
        1
        for item in opportunities
        if _is_directional_executive_candidate(item)
        and not _is_executive_trade_plan_row(item)
    )
    blocked_visible = sum(1 for item in opportunities if item.blockers)
    halted_visible = len(halted_items)
    halted_spot_visible = sum(
        1 for item in halted_items if item.market.strip().upper() == "SPOT"
    )
    halted_futures_visible = sum(
        1 for item in halted_items if "FUTURES" in item.market.strip().upper()
    )
    halted_artifact_resolved = sum(
        1
        for item in halted_items
        if _halted_scope_artifact_path(item) != "ARTIFACT_PATH_UNRESOLVED"
    )
    halted_setup_counts = Counter(item.setup_name for item in halted_items)
    halted_setup_clusters = [
        f"{setup_name}:{count}"
        for setup_name, count in sorted(
            halted_setup_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    halted_pattern_counts = Counter(
        f"{item.market}:{item.setup_name}:{item.trade_side}" for item in halted_items
    )
    halted_pattern_clusters = [
        f"{pattern}:{count}"
        for pattern, count in sorted(
            halted_pattern_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    repeat_offender_scopes = [
        pattern
        for pattern, count in sorted(
            halted_pattern_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
        if count > 1
    ]
    high_escalation_scopes: list[str] = []
    fragile_edge_scopes: list[str] = []
    escalated_risk_note = (
        _loss_streak_escalated_risk_note(opportunities, validation)
        if validation is not None
        else "UNAVAILABLE (validation context not supplied)."
    )
    if halted_items and validation is not None:
        if escalated_risk_note.startswith("HIGH_ESCALATION"):
            high_escalation_scopes = sorted(
                {
                    _loss_streak_pattern_key(item)
                    for item in halted_items
                    if _loss_streak_pattern_key(item) in repeat_offender_scopes
                }
            )
        elif escalated_risk_note.startswith("FRAGILE_EDGE_ESCALATION"):
            fragile_edge_scopes = sorted(
                {
                    _loss_streak_pattern_key(item)
                    for item in halted_items
                    if _loss_streak_pattern_key(item) in repeat_offender_scopes
                }
            )
    spot_visible = sum(1 for item in opportunities if item.market.upper() == "SPOT")
    futures_visible = sum(
        1 for item in opportunities if "FUTURES" in item.market.upper()
    )
    return {
        "visible_research_opportunities": visible,
        "spot_visible_research": spot_visible,
        "futures_visible_research": futures_visible,
        "watchlist_or_validation_pending": watchlist,
        "virtual_market_ready_trade_plans": paper_ready,
        "blocked_visible_research": blocked_visible,
        "loss_streak_halted_visible_research": halted_visible,
        "loss_streak_halted_spot_visible_research": halted_spot_visible,
        "loss_streak_halted_futures_visible_research": halted_futures_visible,
        "loss_streak_halted_scopes": [
            f"{item.market}:{item.symbol}:{item.setup_name}:{item.timeframe}"
            for item in halted_items
        ],
        "loss_streak_halt_review_refs": [
            _halted_scope_review_ref(item) for item in halted_items
        ],
        "loss_streak_halt_review_artifact_paths": [
            _halted_scope_artifact_path(item) for item in halted_items
        ],
        "loss_streak_halt_review_artifacts": [
            {
                "scope": f"{item.market}:{item.symbol}:{item.setup_name}:{item.timeframe}",
                "review_ref": _halted_scope_review_ref(item),
                "artifact_path": _halted_scope_artifact_path(item),
            }
            for item in halted_items
        ],
        "loss_streak_halt_reviews_with_resolved_artifacts": halted_artifact_resolved,
        "loss_streak_halt_reviews_pending_artifact_resolution": (
            halted_visible - halted_artifact_resolved
        ),
        "loss_streak_halted_primary_setup": (
            halted_setup_clusters[0] if halted_setup_clusters else "NONE"
        ),
        "loss_streak_halted_setup_clusters": halted_setup_clusters,
        "loss_streak_halted_primary_pattern": (
            halted_pattern_clusters[0] if halted_pattern_clusters else "NONE"
        ),
        "loss_streak_halted_pattern_clusters": halted_pattern_clusters,
        "loss_streak_repeat_offender_visible_research": len(repeat_offender_scopes),
        "loss_streak_repeat_offender_scopes": repeat_offender_scopes,
        "loss_streak_priority_queue_summary": _loss_streak_priority_queue_summary(
            opportunities
        ),
        "loss_streak_high_escalation_visible_research": (
            1 if escalated_risk_note.startswith("HIGH_ESCALATION") else 0
        ),
        "loss_streak_high_escalation_scopes": high_escalation_scopes,
        "loss_streak_fragile_edge_visible_research": (
            1 if escalated_risk_note.startswith("FRAGILE_EDGE_ESCALATION") else 0
        ),
        "loss_streak_fragile_edge_scopes": fragile_edge_scopes,
        "live_eligible": 0,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _empty_trade_plan_message(
    market: str,
    opportunities: tuple[YkbOpportunityBrief, ...],
) -> str:
    normalized = market.strip().upper()
    if normalized == "SPOT":
        visible_count = sum(
            1 for item in opportunities if item.market.strip().upper() == "SPOT"
        )
    else:
        visible_count = sum(
            1 for item in opportunities if "FUTURES" in item.market.strip().upper()
        )
    if visible_count:
        return (
            f"No virtual-market-ready {normalized} trade plan rows. "
            f"{visible_count} visible research candidate(s) remain in watchlist, "
            "confirmation, validation, or blocker review. Execution stays NO_TRADE."
        )
    return (
        f"No visible {normalized} research candidate and no virtual-market-ready "
        "trade plan row. Discovery remains active; execution stays NO_TRADE."
    )


def _headline(
    symbol: str,
    setup: str,
    dge_status: str,
    blockers: tuple[str, ...],
) -> str:
    if blockers:
        return f"{symbol} {setup}: izlenebilir firsat, DGE {dge_status} ve blocker var."
    return f"{symbol} {setup}: otonom virtual-market simulasyonuna yakin; live yine bloklu."


def _financial_fit(decision: GovernedDecision) -> str:
    if decision.hard_blockers:
        return "NOT_FINANCIALLY_ELIGIBLE_YET"
    if decision.soft_blockers:
        return "MANUAL_REVIEW_REQUIRED"
    return "VIRTUAL_MARKET_AUTONOMOUS_FIT"


def _funding_recommendation(
    item: Mapping[str, object],
    financial: YkbFinancialSituation,
    blockers: tuple[str, ...],
) -> _FundingRecommendation:
    required = (
        _positive_decimal(item.get("required_capital_usdt"))
        or _positive_decimal(item.get("size_usdt"))
        or _positive_decimal(item.get("position_size_usdt"))
    )
    required_bucket = _value_bucket(required)
    quote_bucket = _quote_liquidity_bucket(financial)
    funding_blockers = tuple(
        dict.fromkeys(
            (
                *(
                    ("RECONCILIATION_BLOCKS_CAPITAL_FIT",)
                    if financial.reconciliation_status != "CLEAN" or financial.blockers
                    else ()
                ),
                *(("REQUIRED_CAPITAL_UNKNOWN",) if required is None else ()),
                *blockers,
            )
        )
    )
    if funding_blockers:
        sufficiency = (
            "UNKNOWN_RECONCILIATION_BLOCKED"
            if "RECONCILIATION_BLOCKS_CAPITAL_FIT" in funding_blockers
            else "UNKNOWN"
        )
        requirement = "MANUAL_LIQUIDITY_REVIEW_REQUIRED"
    elif quote_bucket in {"READY", "LIMITED"}:
        sufficiency = "FREE_QUOTE_POTENTIALLY_SUFFICIENT"
        requirement = "CURRENT_QUOTE_CAPITAL_REVIEW"
    else:
        sufficiency = "FREE_QUOTE_NOT_PROVEN"
        requirement = "MANUAL_LIQUIDITY_PREPARATION_REQUIRED"
    return _FundingRecommendation(
        funding_requirement=requirement,
        required_capital_bucket=required_bucket,
        free_quote_sufficiency=sufficiency,
        manual_liquidity_preparation="MANUAL_REVIEW_REQUIRED",
        external_capital_policy="NO_EXTERNAL_CAPITAL_ALLOWED",
        conversion_or_transfer_policy="AUTO_MONEY_MOVEMENT_BLOCKED",
        funding_blockers=funding_blockers,
    )


def _portfolio_funding_recommendation(financial: YkbFinancialSituation) -> str:
    if financial.reconciliation_status != "CLEAN" or financial.blockers:
        return "FIX_RECONCILIATION_BEFORE_FUNDING_DECISION"
    if _quote_liquidity_bucket(financial) in {"READY", "LIMITED"}:
        return "QUOTE_LIQUIDITY_AVAILABLE_FOR_MANUAL_REVIEW"
    return "MANUAL_LIQUIDITY_PREPARATION_REQUIRED"


def _quote_liquidity_bucket(financial: YkbFinancialSituation) -> str:
    quote_assets = tuple(
        asset for asset in financial.spot_assets if asset.asset_class == "QUOTE_CASH"
    )
    if any(asset.liquidity_bucket == "READY" for asset in quote_assets):
        return "READY"
    if quote_assets:
        return "LIMITED"
    return "NOT_PROVEN"


def _asset_class(asset: str) -> str:
    if asset in {"USDT", "USDC"}:
        return "QUOTE_CASH"
    if asset == "BNB":
        return "FEE_RESERVE"
    if asset == "HOT":
        return "PROTECTED_POSITION"
    return "SPOT_POSITION"


def _asset_liquidity_bucket(asset: str, free_value: Decimal | None) -> str:
    if _asset_class(asset) == "QUOTE_CASH" and free_value is not None:
        return "READY"
    if free_value is not None:
        return "MANUAL_REVIEW"
    return "NOT_PROVEN"


def _asset_action_hint(asset: YkbSpotAssetRow) -> str:
    if asset.asset_class == "QUOTE_CASH":
        return "REVIEW_FREE_QUOTE_FOR_MANUAL_LIQUIDITY"
    if asset.asset_class == "PROTECTED_POSITION":
        return "DO_NOT_SELL_WITHOUT_EXPLICIT_OVERRIDE"
    if asset.locked_state == "LOCKED_CAPITAL_PRESENT":
        return "REVIEW_LOCKED_ORDERS_NO_AUTO_CANCEL"
    return "MONITOR_POSITION_NO_AUTO_ACTION"


def _reportable_spot_assets(
    assets: tuple[YkbSpotAssetRow, ...],
) -> tuple[YkbSpotAssetRow, ...]:
    return tuple(
        asset
        for asset in assets
        if asset.value_report_state != "DUST_LT_2_USDT_OMITTED_FROM_PUBLIC_HEATMAP"
    )


def _spot_inventory_dust_omitted_count(assets: tuple[YkbSpotAssetRow, ...]) -> int:
    return sum(
        1
        for asset in assets
        if asset.value_report_state == "DUST_LT_2_USDT_OMITTED_FROM_PUBLIC_HEATMAP"
    )


def _spot_asset_value_report_state(value: object) -> str:
    if value is None or not str(value).strip():
        return "VALUE_UNKNOWN_REPORTABLE"
    parsed = _decimal(value, Decimal("-1"))
    if parsed < Decimal("0"):
        return "VALUE_UNKNOWN_REPORTABLE"
    if parsed < _SPOT_INVENTORY_REPORTING_THRESHOLD_USDT:
        return "DUST_LT_2_USDT_OMITTED_FROM_PUBLIC_HEATMAP"
    return "REPORTABLE_GE_2_USDT"


def _asset_opportunity_review_hint(asset: YkbSpotAssetRow) -> str:
    if asset.value_report_state == "VALUE_UNKNOWN_REPORTABLE":
        return "VALUE_UNKNOWN_FIX_RECONCILIATION_BEFORE_OPPORTUNITY_REVIEW"
    if asset.asset_class == "QUOTE_CASH":
        return "MANUAL_LIQUIDITY_FOR_APPROVED_SPOT_FUTURES_CANDIDATES"
    if asset.asset_class == "PROTECTED_POSITION":
        return "SPOT_FUTURES_VALIDATION_PACKAGE_REQUIRED_NO_AUTO_SELL"
    if asset.locked_state == "LOCKED_CAPITAL_PRESENT":
        return "REVIEW_OPEN_ORDER_THEN_SCAN_SPOT_REBUY_OR_FUTURES_HEDGE"
    return "SCAN_SPOT_SELL_REBUY_OR_FUTURES_HEDGE_RESEARCH_ONLY"


def _position_side_from_quantity(value: object) -> str:
    quantity = _decimal(value, Decimal("0"))
    if quantity > 0:
        return "LONG"
    if quantity < 0:
        return "SHORT"
    return "UNKNOWN_SIDE"


def _value_bucket(value: Decimal | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value <= Decimal("0"):
        return "ZERO"
    if value < Decimal("25"):
        return "LOW"
    if value < Decimal("250"):
        return "MEDIUM"
    return "HIGH"


def _highest_bucket(buckets: tuple[str, ...]) -> str:
    order = {"HIGH": 4, "MEDIUM": 3, "LOW": 2, "ZERO": 1, "UNKNOWN": 0}
    if not buckets:
        return "UNKNOWN"
    return max(buckets, key=lambda item: order.get(item, 0))


def _next_action(blockers: tuple[str, ...]) -> str:
    if not blockers:
        return "PREPARE_VIRTUAL_MARKET_AUTONOMOUS_REVIEW"
    if any("OOS" in blocker or "BACKTEST" in blocker for blocker in blockers):
        return "COMPLETE_BACKTEST_WALK_FORWARD_OOS"
    if any("RISK" in blocker for blocker in blockers):
        return "PREPARE_RISK_REVIEW"
    if any("WALLET" in blocker or "RECONCILIATION" in blocker for blocker in blockers):
        return "FIX_WALLET_RECONCILIATION"
    return "REVIEW_TOP_BLOCKER"


def _trade_plan_value(item: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "PENDING_VALIDATED_LEVEL"


def _timeframe_value(item: Mapping[str, object]) -> str:
    value = str(item.get("timeframe", "")).strip()
    if value and value.upper() not in {"UNKNOWN", "UNAVAILABLE"}:
        return value
    return "MULTI_TF_REVIEW"


def _pattern_type_value(
    value: object,
    *,
    fallback_setup_name: str,
) -> str | None:
    if value is not None:
        text = str(value).strip()
        if text:
            return text
    return setup_pattern_type(fallback_setup_name)


def _trade_plan_row(item: YkbOpportunityBrief) -> str:
    return _markdown_table_row(_trade_plan_cells(item))


def _trade_plan_table(items: Sequence[YkbOpportunityBrief]) -> list[str]:
    return _markdown_table(
        (
            "Koin",
            "Timeframe",
            "Market",
            "Setup",
            "Side",
            "Leverage",
            "SL",
            "E",
            "TP1",
            "TP2",
            "TP3",
            "RR",
            "DGE",
            "Aksiyon",
        ),
        tuple(_trade_plan_cells(item) for item in items),
        alignments=(
            "left",
            "left",
            "left",
            "left",
            "left",
            "left",
            "right",
            "right",
            "right",
            "right",
            "right",
            "right",
            "left",
            "left",
        ),
    )


def _trade_plan_cells(item: YkbOpportunityBrief) -> tuple[object, ...]:
    return (
        item.symbol,
        item.timeframe,
        item.market,
        item.setup_name,
        item.trade_side,
        item.leverage,
        item.stop_loss,
        item.entry,
        item.take_profit_1,
        item.take_profit_2,
        item.take_profit_3,
        item.target_risk_reward,
        item.dge_status,
        item.governed_action,
    )


def _markdown_table(
    headers: Sequence[object],
    rows: Sequence[Sequence[object]],
    *,
    alignments: Sequence[str] | None = None,
) -> list[str]:
    """Return a Markdown table whose raw source columns are human-aligned."""
    header_cells = tuple(_markdown_cell(value) for value in headers)
    row_cells = tuple(tuple(_markdown_cell(value) for value in row) for row in rows)
    widths = [
        max(
            len(header_cells[index]),
            *(len(row[index]) for row in row_cells),
            3,
        )
        for index in range(len(header_cells))
    ]
    normalized_alignments = tuple(alignments or ())
    lines = [
        _markdown_table_row(header_cells, widths=widths),
        _markdown_separator_row(widths, normalized_alignments),
    ]
    lines.extend(_markdown_table_row(row, widths=widths) for row in row_cells)
    return lines


def _markdown_table_row(
    cells: Sequence[object],
    *,
    widths: Sequence[int] | None = None,
) -> str:
    rendered_cells = tuple(_markdown_cell(value) for value in cells)
    effective_widths = tuple(widths or (len(cell) for cell in rendered_cells))
    padded_cells = tuple(
        cell.ljust(effective_widths[index]) for index, cell in enumerate(rendered_cells)
    )
    return f"| {' | '.join(padded_cells)} |"


def _markdown_separator_row(
    widths: Sequence[int],
    alignments: Sequence[str],
) -> str:
    separators: list[str] = []
    for index, width in enumerate(widths):
        alignment = alignments[index].lower() if index < len(alignments) else "left"
        marker_width = max(width, 3)
        if alignment == "right":
            separators.append(f"{'-' * (marker_width - 1)}:")
        elif alignment == "center":
            separators.append(f":{'-' * max(marker_width - 2, 1)}:")
        else:
            separators.append("-" * marker_width)
    return f"| {' | '.join(separators)} |"


def _markdown_cell(value: object) -> str:
    text = "-" if value is None else str(value).strip()
    if not text:
        return "-"
    return text.replace("\n", " ").replace("|", "\\|")


def _is_executive_trade_plan_row(item: YkbOpportunityBrief) -> bool:
    side = item.trade_side.strip().upper()
    market = item.market.strip().upper()
    if not _has_validated_trade_levels(item):
        return False
    if market == "SPOT":
        return side in {"BUY", "SELL"}
    if "FUTURES" in market:
        return side in {"LONG", "SHORT"}
    return False


def _istanbul_time_text(value: object) -> str:
    if isinstance(value, datetime):
        moment = value
    else:
        text = str(value).strip()
        if not text or text in {"KAYIT_YOK", "ARTIFACT_REF_NOT_PUBLISHED"}:
            return text or "KAYIT_YOK"
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.isoformat()
    return moment.astimezone(_ISTANBUL_TZ).isoformat()


def _recent_ykb_report_history_lines(
    current_markdown_path: Path,
    *,
    limit: int = 3,
) -> list[str]:
    entries: dict[str, str] = {}
    report_dir = current_markdown_path.parent
    if report_dir.exists():
        for path in report_dir.glob("ykb_report_*_tr.md"):
            stamp = _ykb_report_stamp_from_name(path.name)
            if stamp is None:
                continue
            entries[stamp] = path.name
    current_stamp = _ykb_report_stamp_from_name(current_markdown_path.name)
    if current_stamp is not None:
        entries[current_stamp] = current_markdown_path.name
    lines = ["## Son 3 YKB Rapor Tarihcesi", ""]
    if not entries:
        lines.append("- Rapor gecmisi bulunamadi.")
        return lines
    for stamp, name in sorted(entries.items(), reverse=True)[:limit]:
        lines.append(f"- `{_ykb_report_stamp_to_istanbul_text(stamp)}` - `{name}`")
    return lines


def _ykb_report_stamp_from_name(file_name: str) -> str | None:
    match = _YKB_REPORT_STAMP_RE.match(file_name)
    if match is None:
        return None
    return match.group(1)


def _ykb_report_stamp_to_istanbul_text(stamp: str) -> str:
    try:
        parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%S").replace(tzinfo=_ISTANBUL_TZ)
    except ValueError:
        return stamp
    return parsed.isoformat()


def _metric_texts(values: tuple[object, ...]) -> tuple[str, ...]:
    metrics: list[str] = []
    for value in values:
        if isinstance(value, list | tuple) and len(value) >= 2:
            metrics.append(f"{value[0]}={value[1]}")
    return tuple(dict.fromkeys(metrics))


def _tuning_parameter_texts(card: Mapping[str, object]) -> tuple[str, ...]:
    candidates = (
        card.get("selected_parameters"),
        _mapping(card.get("strategy")).get("selected_parameters"),
        _mapping(card.get("tuning")).get("selected_parameters"),
        card.get("parameters"),
    )
    for candidate in candidates:
        mapping = _mapping(candidate)
        if mapping:
            return tuple(
                f"{key}={mapping[key]}" for key in sorted(mapping) if str(key).strip()
            )
    return ("TUNING_PARAMETERS_NOT_PUBLISHED",)


def _artifact_refs(card: Mapping[str, object]) -> tuple[str, ...]:
    refs: list[str] = []
    for value in _sequence(card.get("artifact_sha256")):
        if isinstance(value, list | tuple) and value:
            refs.append(str(value[0]))
    return tuple(dict.fromkeys(refs))


def _run_card_playbook(card: Mapping[str, object]) -> str:
    hypothesis = str(card.get("hypothesis_id", "")).strip()
    parts = hypothesis.split(":")
    if len(parts) >= 3 and parts[1]:
        return parts[1]
    return str(card.get("playbook", "UNKNOWN_PLAYBOOK"))


def _read_json_mapping(path: Path) -> Mapping[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _mapping(payload)


def _first_text(
    item: Mapping[str, object],
    *keys: str,
    default: str,
) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _first_sequence_text(value: object) -> str:
    sequence = _sequence(value)
    if not sequence:
        return ""
    first = str(sequence[0]).strip()
    return first


def _value_text(value: object, *, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return ()


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, list | tuple):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(str(value)))
    except (TypeError, ValueError):
        return 0


def _score_decimal(value: object) -> Decimal:
    parsed = _decimal(value, Decimal("0"))
    if Decimal("0") <= parsed <= Decimal("1"):
        return parsed * Decimal("100")
    return min(Decimal("100"), max(Decimal("0"), parsed))


def _confidence_decimal(value: object) -> Decimal:
    return min(Decimal("1"), max(Decimal("0"), _decimal(value, Decimal("0"))))


def _positive_decimal(value: object) -> Decimal | None:
    parsed = _decimal(value, Decimal("0"))
    return parsed if parsed > Decimal("0") else None


def _decimal(value: object, default: Decimal) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default
    return parsed if parsed.is_finite() else default


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
