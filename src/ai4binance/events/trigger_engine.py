"""Deterministic enterprise trigger decisions for research/event intake."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

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
_MARKET_RESEARCH_DOMAINS: frozenset[str] = frozenset(
    {"MARKET", "NEWS", "SOCIAL", "CONTENT", "WHALE", "TOKENOMICS", "EXCHANGE"}
)
_VALID_ACTIONS: frozenset[str] = frozenset(
    {"IGNORE", "WATCH", "RESEARCH", "ALERT", "BLOCK", "NO_ACTION"}
)
_RISK_BLOCKING_TYPES: tuple[str, ...] = (
    "HACK",
    "EXPLOIT",
    "BREACH",
    "DELIST",
    "SUSPEND",
    "CVE",
    "DEPRECATION",
    "OUTAGE",
    "INVESTIGATION",
    "LAWSUIT",
    "BANKRUPTCY",
    "INSOLVENCY",
)


@dataclass(frozen=True, slots=True)
class TriggerEvent:
    """Provider-neutral event that asks whether research should start.

    The trigger event is deliberately not a signal, order, release installer, or
    scheduler. It is a deterministic intake contract for deciding whether a
    change deserves research, watch, alert, or blocking attention.
    """

    event_id: str
    event_type: str
    domain: str
    entity: str | None
    detected_at: datetime
    source: str
    severity: Decimal
    confidence: Decimal
    relevance: Decimal
    freshness: Decimal
    evidence_count: int
    dedup_key: str
    payload: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for value in (
            self.event_id,
            self.event_type,
            self.domain,
            self.source,
            self.dedup_key,
        ):
            if not value.strip():
                raise ValueError("trigger event identity is required")
        if self.detected_at.tzinfo is None or self.detected_at.utcoffset() is None:
            raise ValueError("trigger event timestamp must be timezone-aware")
        for metric in (self.severity, self.confidence, self.relevance, self.freshness):
            if metric < Decimal("0") or metric > Decimal("1"):
                raise ValueError("trigger event metrics must be within zero and one")
        if self.evidence_count < 0:
            raise ValueError("trigger event evidence count cannot be negative")
        keys = tuple(key for key, _value in self.payload)
        if any(not key.strip() for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("trigger event payload keys must be non-empty and unique")
        if tuple(sorted(self.payload)) != self.payload:
            raise ValueError("trigger event payload must be sorted")

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        event_type: str,
        domain: str,
        entity: str | None,
        detected_at: datetime,
        source: str,
        severity: object,
        confidence: object,
        relevance: object,
        freshness: object,
        evidence_count: int,
        dedup_key: str,
        payload: Mapping[str, object] | None = None,
    ) -> TriggerEvent:
        return cls(
            event_id=event_id,
            event_type=event_type.strip().upper(),
            domain=domain.strip().upper(),
            entity=entity.strip().upper() if entity and entity.strip() else None,
            detected_at=detected_at,
            source=source.strip(),
            severity=_bounded_decimal(severity),
            confidence=_bounded_decimal(confidence),
            relevance=_bounded_decimal(relevance),
            freshness=_bounded_decimal(freshness),
            evidence_count=evidence_count,
            dedup_key=dedup_key.strip(),
            payload=_payload_tuple(payload or {}),
        )

    def payload_dict(self) -> dict[str, str]:
        return dict(self.payload)


@dataclass(frozen=True, slots=True)
class TriggerDecision:
    event_id: str
    event_type: str
    domain: str
    entity: str | None
    impact_score: Decimal
    action: str
    research_required: bool
    blockers: tuple[str, ...]
    dedup_key: str
    source: str
    detected_at: datetime
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for value in (self.event_id, self.event_type, self.domain, self.action):
            if not value.strip():
                raise ValueError("trigger decision identity is required")
        if self.impact_score < Decimal("0") or self.impact_score > Decimal("100"):
            raise ValueError(
                "trigger decision score must be within zero and one hundred"
            )
        if self.action not in _VALID_ACTIONS:
            raise ValueError("trigger decision action is invalid")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("trigger decision cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class EnterpriseEventTriggerEngine:
    """Hybrid trigger engine for technology and market intelligence research."""

    watch_threshold: Decimal = Decimal("30")
    research_threshold: Decimal = Decimal("50")
    alert_threshold: Decimal = Decimal("70")
    critical_threshold: Decimal = Decimal("85")

    def __post_init__(self) -> None:
        thresholds = (
            self.watch_threshold,
            self.research_threshold,
            self.alert_threshold,
            self.critical_threshold,
        )
        if thresholds != tuple(sorted(thresholds)):
            raise ValueError("trigger thresholds must be ordered")
        if self.watch_threshold < 0 or self.critical_threshold > 100:
            raise ValueError("trigger thresholds must be within zero and one hundred")

    def evaluate(self, event: TriggerEvent) -> TriggerDecision:
        blockers: tuple[str, ...] = ()
        if _is_market_research_event(event) and event.entity is not None:
            if not is_binance_coin_research_symbol(event.entity):
                return _decision(
                    event,
                    impact_score=Decimal("0"),
                    action="IGNORE",
                    blockers=("EXCLUDED_STABLE_WRAPPED_OR_LEVERAGED_TOKEN",),
                )
        score = _impact_score(event)
        action = self._action(event, score)
        if action == "BLOCK":
            blockers = ("RISK_RESEARCH_BLOCKER",)
        return _decision(event, impact_score=score, action=action, blockers=blockers)

    def evaluate_many(
        self,
        events: Sequence[TriggerEvent],
    ) -> tuple[TriggerDecision, ...]:
        by_key: dict[str, TriggerDecision] = {}
        for event in events:
            decision = self.evaluate(event)
            current = by_key.get(decision.dedup_key)
            if current is None or _decision_sort_key(decision) > _decision_sort_key(
                current
            ):
                by_key[decision.dedup_key] = decision
        return tuple(
            sorted(
                by_key.values(),
                key=lambda item: (
                    item.impact_score,
                    item.detected_at,
                    item.event_id,
                ),
                reverse=True,
            )
        )

    def _action(self, event: TriggerEvent, score: Decimal) -> str:
        if score < self.watch_threshold:
            return "IGNORE"
        if score < self.research_threshold:
            return "WATCH"
        if score < self.alert_threshold:
            return "RESEARCH"
        if _is_risk_blocking_event(event) and score >= self.alert_threshold:
            return "BLOCK"
        return "ALERT"


def is_binance_coin_research_symbol(symbol: str) -> bool:
    """Return True for Binance Spot/Futures coin radar symbols in scope.

    This is the market-intelligence counterpart of the YKB opportunity radar
    rule: stablecoins, wrapped tokens, and leveraged tokens are excluded, but
    wallet value, inventory size, and public heatmap visibility are not filters.
    """
    base = _base_asset(symbol)
    if not base:
        return False
    if base in _STABLECOIN_BASES or base in _WRAPPED_BASES:
        return False
    return not any(base.endswith(suffix) for suffix in _LEVERAGED_BASE_SUFFIXES)


def _decision(
    event: TriggerEvent,
    *,
    impact_score: Decimal,
    action: str,
    blockers: tuple[str, ...],
) -> TriggerDecision:
    return TriggerDecision(
        event_id=event.event_id,
        event_type=event.event_type,
        domain=event.domain,
        entity=event.entity,
        impact_score=impact_score,
        action=action,
        research_required=action in {"RESEARCH", "ALERT", "BLOCK"},
        blockers=blockers,
        dedup_key=event.dedup_key,
        source=event.source,
        detected_at=event.detected_at,
    )


def _impact_score(event: TriggerEvent) -> Decimal:
    payload = event.payload_dict()
    source_credibility = _source_credibility(event)
    mention_velocity = _payload_decimal(payload, "mention_velocity")
    market_confirmation = _payload_decimal(payload, "market_confirmation")
    cross_source_confirmation = _payload_decimal(payload, "cross_source_confirmation")
    score = (
        source_credibility * Decimal("0.20")
        + event.relevance * Decimal("0.20")
        + event.severity * Decimal("0.20")
        + mention_velocity * Decimal("0.10")
        + market_confirmation * Decimal("0.15")
        + cross_source_confirmation * Decimal("0.10")
        + event.freshness * Decimal("0.05")
    ) * Decimal("100")
    if event.evidence_count == 0:
        score -= Decimal("15")
    elif event.evidence_count >= 3:
        score += Decimal("5")
    return min(Decimal("100"), max(Decimal("0"), score.quantize(Decimal("0.01"))))


def _source_credibility(event: TriggerEvent) -> Decimal:
    payload = event.payload_dict()
    explicit = payload.get("source_credibility")
    if explicit is not None:
        return _bounded_decimal(explicit)
    tier = payload.get("source_tier", "").strip().lower()
    return {
        "official": Decimal("1.00"),
        "tier1_media": Decimal("0.90"),
        "tier2_media": Decimal("0.75"),
        "verified_social": Decimal("0.60"),
        "community": Decimal("0.35"),
        "anonymous": Decimal("0.10"),
    }.get(tier, event.confidence)


def _is_market_research_event(event: TriggerEvent) -> bool:
    return event.domain in _MARKET_RESEARCH_DOMAINS


def _is_risk_blocking_event(event: TriggerEvent) -> bool:
    payload = event.payload_dict()
    if payload.get("risk_blocker", "").strip().lower() in {"1", "true", "yes"}:
        return True
    text = f"{event.domain} {event.event_type} {payload.get('category', '')}".upper()
    return any(token in text for token in _RISK_BLOCKING_TYPES)


def _decision_sort_key(decision: TriggerDecision) -> tuple[Decimal, datetime, str]:
    return (decision.impact_score, decision.detected_at, decision.event_id)


def _base_asset(symbol: str) -> str:
    normalized = symbol.strip().upper()
    for quote in sorted(_QUOTE_SUFFIXES, key=len, reverse=True):
        if normalized.endswith(quote) and len(normalized) > len(quote):
            return normalized[: -len(quote)]
    return normalized


def _payload_tuple(payload: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(key), str(value)) for key, value in payload.items()))


def _payload_decimal(payload: Mapping[str, str], key: str) -> Decimal:
    return _bounded_decimal(payload.get(key, "0"))


def _bounded_decimal(value: object) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("trigger metric must be decimal-compatible") from error
    if parsed < Decimal("0"):
        return Decimal("0")
    if parsed > Decimal("1"):
        return Decimal("1")
    return parsed
