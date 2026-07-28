"""Fast deterministic synthesis of existing analysis into a market outlook."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from ai4binance.domain import Action, PriceZone, SetupTier
from ai4binance.outlook.models import (
    BiasDirection,
    HighImpactEvent,
    KeyLevel,
    KeyLevelKind,
    MarketOutlook,
    OutlookStatus,
    SetupRadarItem,
    TimeframeBias,
    TpoCompositeContext,
)
from ai4binance.schemas import AgentResult, AnalysisState, DataQuality

BIAS_TIMEFRAMES = ("1d", "4h", "1h", "15m")
MAX_RADAR_SETUPS = 5
ZONE_ATR_FRACTION = Decimal("0.25")
ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class MarketOutlookEngine:
    """Reuse agent evidence; never recalculate indicators or create signals."""

    def build(self, analysis: AnalysisState) -> MarketOutlook:
        """Build one snapshot-consistent, research-only outlook."""
        snapshot = analysis.market_snapshot
        blockers: list[str] = list(analysis.blockers)
        warnings: list[str] = list(analysis.warnings)

        biases, bias_blockers = self._biases(analysis.agent_results)
        blockers.extend(bias_blockers)
        regime = self._regime(analysis.agent_results)
        if regime == "UNKNOWN":
            blockers.append("MARKET_REGIME_UNAVAILABLE")

        events, event_warnings = self._high_impact_events(snapshot.news_snapshot)
        warnings.extend(event_warnings)
        if not events:
            blockers.append("HIGH_IMPACT_DATA_UNAVAILABLE")

        levels = self._key_levels(analysis.agent_results)
        if not levels:
            blockers.append("KEY_LEVELS_UNAVAILABLE")

        tpo = self._tpo_context(analysis)
        blockers.extend(tpo.blockers)
        macro_cycle = self._macro_cycle(analysis.agent_results)
        if macro_cycle == "UNKNOWN":
            blockers.append("MACRO_CYCLE_EVIDENCE_UNAVAILABLE")

        unique_blockers = tuple(dict.fromkeys(blockers))
        unique_warnings = tuple(dict.fromkeys(warnings))
        status = self._status(snapshot.data_quality, unique_blockers)
        pro_trend = self._pro_trend_direction(biases)
        conflict = self._has_conflict(biases)
        decision = analysis.final_decision
        rationale = (
            decision.reason_summary
            if decision is not None
            else "No validated final decision is available; prefer NO_TRADE."
        )
        return MarketOutlook(
            snapshot_id=snapshot.snapshot_id,
            symbol=snapshot.symbol,
            timestamp=snapshot.created_at,
            status=status,
            timeframe_biases=biases,
            market_regime=regime,
            pro_trend_direction=pro_trend,
            timeframe_conflict=conflict,
            macro_cycle_view=macro_cycle,
            volatility_state=self._volatility_state(analysis.agent_results),
            setups_on_radar=self._setups(analysis),
            high_impact_data=events,
            key_levels=levels,
            tpo_composites=tpo,
            no_trade_rationale=rationale,
            blockers=unique_blockers,
            warnings=unique_warnings,
        )

    @staticmethod
    def _biases(
        results: Mapping[str, AgentResult],
    ) -> tuple[tuple[TimeframeBias, ...], tuple[str, ...]]:
        trend = results.get("trend")
        metrics = MarketOutlookEngine._nested_mapping(
            trend.calculation_metadata if trend is not None else {}, "timeframes"
        )
        biases: list[TimeframeBias] = []
        blockers: list[str] = []
        for timeframe in BIAS_TIMEFRAMES:
            timeframe_metrics = metrics.get(timeframe)
            vote = (
                MarketOutlookEngine._float(timeframe_metrics.get("vote"))
                if isinstance(timeframe_metrics, Mapping)
                else None
            )
            if vote is None:
                biases.append(
                    TimeframeBias(
                        timeframe,
                        BiasDirection.UNKNOWN,
                        0.0,
                        0.0,
                        ("TIMEFRAME_TREND_EVIDENCE_UNAVAILABLE",),
                    )
                )
                blockers.append(f"BIAS_DATA_UNAVAILABLE:{timeframe}")
                continue
            bounded = max(-1.0, min(1.0, vote))
            biases.append(
                TimeframeBias(
                    timeframe=timeframe,
                    direction=MarketOutlookEngine._direction(bounded),
                    score=round(abs(bounded) * 100.0, 6),
                    confidence=round(abs(bounded), 6),
                    reason_codes=("TREND_AGENT_TIMEFRAME_VOTE",),
                )
            )
        return tuple(biases), tuple(blockers)

    @staticmethod
    def _setups(analysis: AnalysisState) -> tuple[SetupRadarItem, ...]:
        if analysis.candidate_setups:
            ranked = sorted(
                analysis.candidate_setups,
                key=lambda item: (-item.score, item.candidate_id),
            )
            return tuple(
                SetupRadarItem(
                    setup_name=item.setup_name,
                    timeframe=item.timeframe,
                    direction=(
                        BiasDirection.BULLISH
                        if item.action is Action.BUY
                        else BiasDirection.BEARISH
                    ),
                    setup_tier=MarketOutlookEngine._tier(item.score),
                    score=item.score,
                    confidence=item.confidence,
                    status=item.status.value,
                    promotion_status=item.promotion_status.value,
                    blockers=item.blockers,
                )
                for item in ranked[:MAX_RADAR_SETUPS]
            )

        radar: list[SetupRadarItem] = []
        seen: set[tuple[str, str]] = set()
        for name in sorted(analysis.agent_results):
            result = analysis.agent_results[name]
            for raw_setup in result.detected_setups:
                setup_name, separator, timeframe = raw_setup.partition(":")
                timeframe = timeframe if separator else "UNKNOWN"
                key = (setup_name, timeframe)
                if key in seen:
                    continue
                seen.add(key)
                blockers = result.blockers or ("SETUP_NOT_OOS_VALIDATED",)
                radar.append(
                    SetupRadarItem(
                        setup_name=setup_name,
                        timeframe=timeframe,
                        direction=MarketOutlookEngine._direction(
                            result.directional_vote
                        ),
                        setup_tier=MarketOutlookEngine._tier(result.score),
                        score=result.score,
                        confidence=result.confidence,
                        status=result.status.value,
                        promotion_status=result.promotion_status.value,
                        blockers=blockers,
                    )
                )
        radar.sort(key=lambda item: (-item.score, item.setup_name, item.timeframe))
        return tuple(radar[:MAX_RADAR_SETUPS])

    @staticmethod
    def _high_impact_events(
        news_snapshot: Mapping[str, object],
    ) -> tuple[tuple[HighImpactEvent, ...], tuple[str, ...]]:
        raw_events = news_snapshot.get("high_impact_events")
        provider_blockers = news_snapshot.get("provider_blockers", ())
        provider_warnings = (
            tuple(f"MARKET_CONTEXT:{item}" for item in provider_blockers)
            if isinstance(provider_blockers, tuple)
            and all(isinstance(item, str) for item in provider_blockers)
            else ()
        )
        if not isinstance(raw_events, Sequence) or isinstance(raw_events, (str, bytes)):
            return (), provider_warnings
        events: list[HighImpactEvent] = []
        warnings: list[str] = []
        for index, raw_event in enumerate(raw_events):
            if not isinstance(raw_event, Mapping):
                warnings.append(f"HIGH_IMPACT_EVENT_INVALID:{index}")
                continue
            title = raw_event.get("title")
            source = raw_event.get("source")
            impact = str(raw_event.get("impact", "")).upper()
            scheduled_at = MarketOutlookEngine._datetime(raw_event.get("scheduled_at"))
            if (
                not isinstance(title, str)
                or not title.strip()
                or not isinstance(source, str)
                or not source.strip()
                or impact not in {"HIGH", "CRITICAL"}
                or scheduled_at is None
            ):
                warnings.append(f"HIGH_IMPACT_EVENT_INVALID:{index}")
                continue
            raw_id = raw_event.get("event_id")
            event_id = (
                raw_id.strip()
                if isinstance(raw_id, str) and raw_id.strip()
                else f"{source.strip()}:{scheduled_at.isoformat()}:{title.strip()}"
            )
            events.append(
                HighImpactEvent(
                    event_id=event_id,
                    title=title.strip(),
                    scheduled_at=scheduled_at,
                    impact=impact,
                    source=source.strip(),
                )
            )
        events.sort(key=lambda item: (item.scheduled_at, item.event_id))
        return tuple(events), (*provider_warnings, *warnings)

    @staticmethod
    def _key_levels(results: Mapping[str, AgentResult]) -> tuple[KeyLevel, ...]:
        structural = results.get("support_resistance")
        volatility = results.get("volatility")
        structural_metrics = MarketOutlookEngine._nested_mapping(
            structural.calculation_metadata if structural is not None else {},
            "timeframes",
        )
        volatility_metrics = MarketOutlookEngine._nested_mapping(
            volatility.calculation_metadata if volatility is not None else {},
            "timeframes",
        )
        levels: list[KeyLevel] = []
        for timeframe in BIAS_TIMEFRAMES:
            raw = structural_metrics.get(timeframe)
            if not isinstance(raw, Mapping):
                continue
            atr_raw = volatility_metrics.get(timeframe)
            atr_value = (
                MarketOutlookEngine._decimal(atr_raw.get("atr_14"))
                if isinstance(atr_raw, Mapping)
                else None
            )
            half_width = (atr_value or ZERO) * ZONE_ATR_FRACTION
            for field_name, kind in (
                ("support", KeyLevelKind.SUPPORT),
                ("resistance", KeyLevelKind.RESISTANCE),
            ):
                value = MarketOutlookEngine._decimal(raw.get(field_name))
                if value is None or value < ZERO:
                    continue
                levels.append(
                    KeyLevel(
                        timeframe=timeframe,
                        kind=kind,
                        zone=PriceZone(
                            lower=max(ZERO, value - half_width),
                            upper=value + half_width,
                        ),
                    )
                )
        return tuple(levels)

    @staticmethod
    def _tpo_context(analysis: AnalysisState) -> TpoCompositeContext:
        result = analysis.agent_results.get("volume_profile")
        poc = (
            MarketOutlookEngine._decimal(result.calculation_metadata.get("poc"))
            if result is not None
            else None
        )
        source_timeframe = next(
            (
                timeframe
                for timeframe in BIAS_TIMEFRAMES
                if len(analysis.market_snapshot.ohlcv_by_timeframe.get(timeframe, ()))
                >= 55
            ),
            None,
        )
        blockers = [
            "TPO_AUCTION_PROFILE_NOT_IMPLEMENTED",
            "COMPOSITE_BALANCE_AREAS_NOT_IMPLEMENTED",
        ]
        if poc is None:
            blockers.append("VOLUME_PROFILE_PROXY_UNAVAILABLE")
        return TpoCompositeContext(
            status="PROXY_ONLY" if poc is not None else "UNAVAILABLE",
            source_timeframe=source_timeframe if poc is not None else None,
            point_of_control_proxy=poc,
            evidence=result.evidence if result is not None and poc is not None else (),
            blockers=tuple(blockers),
        )

    @staticmethod
    def _macro_cycle(results: Mapping[str, AgentResult]) -> str:
        wyckoff = results.get("wyckoff")
        setups = set(wyckoff.detected_setups) if wyckoff is not None else set()
        if "SPRING_PROXY" in setups:
            return "ACCUMULATION_CANDIDATE"
        if "UPTHRUST_PROXY" in setups:
            return "DISTRIBUTION_CANDIDATE"
        return "UNKNOWN"

    @staticmethod
    def _regime(results: Mapping[str, AgentResult]) -> str:
        result = results.get("market_regime")
        value = (
            result.calculation_metadata.get("regime") if result is not None else None
        )
        return value if isinstance(value, str) and value.strip() else "UNKNOWN"

    @staticmethod
    def _volatility_state(results: Mapping[str, AgentResult]) -> str:
        result = results.get("volatility")
        if result is None or not result.applicable:
            return "UNKNOWN"
        if any(item.startswith("ABNORMAL_VOLATILITY:") for item in result.warnings):
            return "ABNORMAL"
        return "NORMAL"

    @staticmethod
    def _status(data_quality: DataQuality, blockers: tuple[str, ...]) -> OutlookStatus:
        if (
            data_quality is DataQuality.DATA_INVALID
            or "EARLY_EXIT_NO_TRADE" in blockers
        ):
            return OutlookStatus.BLOCKED
        return OutlookStatus.PARTIAL if blockers else OutlookStatus.READY

    @staticmethod
    def _pro_trend_direction(biases: tuple[TimeframeBias, ...]) -> BiasDirection:
        for timeframe in ("1d", "4h", "1h"):
            bias = next(item for item in biases if item.timeframe == timeframe)
            if bias.direction in {BiasDirection.BULLISH, BiasDirection.BEARISH}:
                return bias.direction
        return BiasDirection.UNKNOWN

    @staticmethod
    def _has_conflict(biases: tuple[TimeframeBias, ...]) -> bool:
        directions = {
            item.direction
            for item in biases
            if item.direction in {BiasDirection.BULLISH, BiasDirection.BEARISH}
        }
        return len(directions) > 1

    @staticmethod
    def _direction(vote: float) -> BiasDirection:
        if vote > 0.15:
            return BiasDirection.BULLISH
        if vote < -0.15:
            return BiasDirection.BEARISH
        return BiasDirection.NEUTRAL

    @staticmethod
    def _tier(score: float) -> SetupTier:
        if score >= 85.0:
            return SetupTier.A_STAR
        if score >= 78.0:
            return SetupTier.A
        if score >= 70.0:
            return SetupTier.B
        if score >= 60.0:
            return SetupTier.C
        return SetupTier.NO_TRADE

    @staticmethod
    def _nested_mapping(
        mapping: Mapping[str, object], key: str
    ) -> Mapping[str, object]:
        value = mapping.get(key)
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _float(value: object) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float, Decimal)):
            converted = float(value)
            return converted if converted == converted else None
        return None

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            converted = Decimal(str(value))
        except InvalidOperation:
            return None
        return converted if converted.is_finite() else None

    @staticmethod
    def _datetime(value: object) -> datetime | None:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed
