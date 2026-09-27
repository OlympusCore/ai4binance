"""Compatibility exports for virtual-market contracts and acceptance workflow."""

from ai4binance.application.virtual_market import (
    default_acceptance_policy_path as default_acceptance_policy_path,
)
from ai4binance.application.virtual_market import (
    default_blocker_registry_path as default_blocker_registry_path,
)
from ai4binance.application.virtual_market import (
    evaluate_market_acceptance as evaluate_market_acceptance,
)
from ai4binance.application.virtual_market import (
    evaluate_research_candidate as evaluate_research_candidate,
)
from ai4binance.application.virtual_market import (
    evaluate_two_stage_profitability_evidence as _evaluate_two_stage,
)
from ai4binance.application.virtual_market import (
    load_acceptance_blocker_definitions as load_acceptance_blocker_definitions,
)
from ai4binance.application.virtual_market import (
    load_acceptance_policy as load_acceptance_policy,
)
from ai4binance.application.virtual_market import (
    render_system_acceptance_markdown as render_system_acceptance_markdown,
)
from ai4binance.domain.research.virtual_market import (
    ACCEPTANCE_BLOCKER_CANONICAL_CODES as ACCEPTANCE_BLOCKER_CANONICAL_CODES,
)
from ai4binance.domain.research.virtual_market import (
    DEFAULT_HARD_FAIL_GATES as DEFAULT_HARD_FAIL_GATES,
)
from ai4binance.domain.research.virtual_market import (
    DEFAULT_INITIAL_EQUITY_USDT as DEFAULT_INITIAL_EQUITY_USDT,
)
from ai4binance.domain.research.virtual_market import (
    DEFAULT_REQUIRED_COST_STRESS_SCENARIOS as DEFAULT_REQUIRED_COST_STRESS_SCENARIOS,
)
from ai4binance.domain.research.virtual_market import (
    DEFAULT_SYSTEM_ACCEPTANCE_OPERATOR as DEFAULT_SYSTEM_ACCEPTANCE_OPERATOR,
)
from ai4binance.domain.research.virtual_market import (
    EXISTING_FINAL_ACCEPTANCE_STAGE as EXISTING_FINAL_ACCEPTANCE_STAGE,
)
from ai4binance.domain.research.virtual_market import (
    MARKET_STATUS_BLOCKER_PRECEDENCE as MARKET_STATUS_BLOCKER_PRECEDENCE,
)
from ai4binance.domain.research.virtual_market import (
    MAX_ACCEPTANCE_POLICY_BYTES as MAX_ACCEPTANCE_POLICY_BYTES,
)
from ai4binance.domain.research.virtual_market import (
    ONE as ONE,
)
from ai4binance.domain.research.virtual_market import (
    RESEARCH_CANDIDATE_STAGE as RESEARCH_CANDIDATE_STAGE,
)
from ai4binance.domain.research.virtual_market import (
    STATUS_BLOCKER_CLASSES as STATUS_BLOCKER_CLASSES,
)
from ai4binance.domain.research.virtual_market import (
    SYSTEM_STATUS_BLOCKERS as SYSTEM_STATUS_BLOCKERS,
)
from ai4binance.domain.research.virtual_market import (
    SYSTEM_STATUS_PRECEDENCE as SYSTEM_STATUS_PRECEDENCE,
)
from ai4binance.domain.research.virtual_market import (
    ZERO as ZERO,
)
from ai4binance.domain.research.virtual_market import (
    AcceptancePolicy as AcceptancePolicy,
)
from ai4binance.domain.research.virtual_market import (
    AcceptanceStatus as AcceptanceStatus,
)
from ai4binance.domain.research.virtual_market import (
    CostStressScenarioEvidence as CostStressScenarioEvidence,
)
from ai4binance.domain.research.virtual_market import (
    DailyEquityPoint as DailyEquityPoint,
)
from ai4binance.domain.research.virtual_market import (
    MarketAcceptanceResult as MarketAcceptanceResult,
)
from ai4binance.domain.research.virtual_market import (
    MarketPerformanceEvidence as MarketPerformanceEvidence,
)
from ai4binance.domain.research.virtual_market import (
    RegimeAttribution as RegimeAttribution,
)
from ai4binance.domain.research.virtual_market import (
    ResearchCandidatePolicy as ResearchCandidatePolicy,
)
from ai4binance.domain.research.virtual_market import (
    ResearchCandidateResult as ResearchCandidateResult,
)
from ai4binance.domain.research.virtual_market import (
    SystemResearchAcceptance as SystemResearchAcceptance,
)
from ai4binance.domain.research.virtual_market import (
    TwoStageProfitabilityEvidence as TwoStageProfitabilityEvidence,
)
from ai4binance.domain.research.virtual_market import (
    VirtualMarket as VirtualMarket,
)
from ai4binance.domain.research.virtual_market import (
    _append_drawdown_blocker as _append_drawdown_blocker,
)
from ai4binance.domain.research.virtual_market import (
    _append_futures_blockers as _append_futures_blockers,
)
from ai4binance.domain.research.virtual_market import (
    _coerce_virtual_market as _coerce_virtual_market,
)
from ai4binance.domain.research.virtual_market import (
    _derive_system_status as _derive_system_status,
)
from ai4binance.domain.research.virtual_market import (
    _mapping as _mapping,
)
from ai4binance.domain.research.virtual_market import (
    _market_status_from_blockers as _market_status_from_blockers,
)
from ai4binance.domain.research.virtual_market import (
    _optional_bool_with_default as _optional_bool_with_default,
)
from ai4binance.domain.research.virtual_market import (
    _optional_decimal_with_default as _optional_decimal_with_default,
)
from ai4binance.domain.research.virtual_market import (
    _optional_mapping as _optional_mapping,
)
from ai4binance.domain.research.virtual_market import (
    _optional_string_tuple_with_default as _optional_string_tuple_with_default,
)
from ai4binance.domain.research.virtual_market import (
    _require_decimal_ratio as _require_decimal_ratio,
)
from ai4binance.domain.research.virtual_market import (
    _require_finite_decimal as _require_finite_decimal,
)
from ai4binance.domain.research.virtual_market import (
    _require_nonnegative_int as _require_nonnegative_int,
)
from ai4binance.domain.research.virtual_market import (
    _require_optional_nonnegative as _require_optional_nonnegative,
)
from ai4binance.domain.research.virtual_market import (
    _require_system_status_blockers as _require_system_status_blockers,
)
from ai4binance.domain.research.virtual_market import (
    _require_unique_nonblank as _require_unique_nonblank,
)
from ai4binance.domain.research.virtual_market import (
    _require_virtual_market_policy_authority as _require_policy_authority,
)
from ai4binance.domain.research.virtual_market import (
    _require_virtual_market_research_only_authority as _require_research_authority,
)
from ai4binance.domain.research.virtual_market import (
    _required_bool as _required_bool,
)
from ai4binance.domain.research.virtual_market import (
    _required_decimal as _required_decimal,
)
from ai4binance.domain.research.virtual_market import (
    _required_int as _required_int,
)
from ai4binance.domain.research.virtual_market import (
    _required_string as _required_string,
)
from ai4binance.domain.research.virtual_market import (
    _required_string_tuple as _required_string_tuple,
)
from ai4binance.domain.research.virtual_market import (
    calculate_daily_returns as calculate_daily_returns,
)
from ai4binance.domain.research.virtual_market import (
    calculate_daily_sharpe as calculate_daily_sharpe,
)
from ai4binance.domain.research.virtual_market import (
    canonical_acceptance_blocker_codes as canonical_acceptance_blocker_codes,
)
from ai4binance.domain.research.virtual_market import (
    derive_virtual_runtime_priority_signal as derive_virtual_runtime_priority_signal,
)
from ai4binance.domain.research.virtual_market import (
    required_acceptance_blocker_mappings as required_acceptance_blocker_mappings,
)
from ai4binance.domain.research.virtual_market import (
    required_system_status_blockers as required_system_status_blockers,
)

evaluate_two_stage_profitability_evidence = _evaluate_two_stage
_require_virtual_market_policy_authority = _require_policy_authority
_require_virtual_market_research_only_authority = _require_research_authority
