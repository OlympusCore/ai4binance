"""Deterministic Market Outlook to X draft transformation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ai4binance.content.models import ContentClaim, ContentDraft, ContentSource
from ai4binance.content.policy import ContentCompliancePolicy
from ai4binance.mcp.evidence import EvidenceEnvelope, FreshnessStatus


class DraftBlockedError(ValueError):
    """Raised when evidence or generated content fails a mandatory gate."""

    def __init__(self, blockers: tuple[str, ...]) -> None:
        self.blockers = blockers
        super().__init__(", ".join(blockers))


@dataclass(frozen=True, slots=True)
class ContentDraftEngine:
    """Build one bounded draft from fresh read-only Evidence MCP output."""

    policy: ContentCompliancePolicy = field(default_factory=ContentCompliancePolicy)
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    template_version: str = "market-outlook-v1"

    def create_market_outlook_draft(self, evidence: EvidenceEnvelope) -> ContentDraft:
        """Create a compliant draft or fail with explicit blockers."""
        self._validate_envelope(evidence)
        data = evidence.data
        timestamp = self._timestamp(data.get("timestamp"))
        if timestamp is None:
            raise DraftBlockedError(("CONTENT_SOURCE_TIMESTAMP_INVALID",))

        symbol = self._field(data, "symbol", 20)
        regime = self._field(data, "market_regime", 32)
        volatility = self._field(data, "volatility_state", 24)
        rationale = self._field(data, "no_trade_rationale", 60)
        biases = self._biases(data.get("timeframe_biases"))
        radar = self._radar(data.get("setups_on_radar"))

        content = (
            f"{symbol} | Görünüm\n"
            f"1D:{biases['1d']} 4H:{biases['4h']} 1H:{biases['1h']}\n"
            f"Rejim: {regime} | Vol: {volatility}\n"
            f"Radar: {radar}\n"
            f"NO_TRADE: {rationale}\n"
            f"{self.policy.required_disclaimer}"
        )
        policy_result = self.policy.evaluate(content)
        if policy_result.blockers:
            raise DraftBlockedError(policy_result.blockers)

        claims = (
            ContentClaim(
                text=f"1D:{biases['1d']} 4H:{biases['4h']} 1H:{biases['1h']}",
                source_field="timeframe_biases",
            ),
            ContentClaim(text=f"Rejim: {regime}", source_field="market_regime"),
            ContentClaim(text=f"Vol: {volatility}", source_field="volatility_state"),
            ContentClaim(text=f"Radar: {radar}", source_field="setups_on_radar"),
            ContentClaim(
                text=f"NO_TRADE: {rationale}", source_field="no_trade_rationale"
            ),
        )
        source = ContentSource(
            artifact_type=evidence.artifact_type,
            source_artifact=evidence.source_artifact,
            source_sha256=evidence.source_sha256,
            evidence_timestamp=timestamp,
            freshness_status=evidence.freshness_status.value,
        )
        created_at = self._now()
        draft_id = self._draft_id(evidence.source_sha256, content)
        return ContentDraft(
            draft_id=draft_id,
            created_at=created_at,
            content=content,
            source=source,
            claims=claims,
            compliance_status=policy_result.status,
            template_version=self.template_version,
        )

    def _validate_envelope(self, evidence: EvidenceEnvelope) -> None:
        blockers: list[str] = []
        if evidence.artifact_type != "market_outlook":
            blockers.append("CONTENT_SOURCE_TYPE_UNSUPPORTED")
        if evidence.freshness_status is not FreshnessStatus.FRESH:
            blockers.append("CONTENT_SOURCE_NOT_FRESH")
        if evidence.execution_allowed or evidence.live_eligibility_status != (
            "LIVE_ORDER_BLOCKED"
        ):
            blockers.append("CONTENT_SOURCE_AUTHORITY_VIOLATION")
        if not evidence.data:
            blockers.append("CONTENT_SOURCE_DATA_MISSING")
        if blockers:
            raise DraftBlockedError(tuple(blockers))

    def _draft_id(self, source_sha256: str, content: str) -> str:
        encoded = json.dumps(
            {
                "content": content,
                "source_sha256": source_sha256,
                "template_version": self.template_version,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("content engine clock must be timezone-aware")
        return value

    @staticmethod
    def _timestamp(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed

    @staticmethod
    def _field(data: Mapping[str, object], name: str, limit: int) -> str:
        value = data.get(name)
        if not isinstance(value, str) or not value.strip():
            raise DraftBlockedError((f"CONTENT_SOURCE_{name.upper()}_INVALID",))
        compact = " ".join(value.split())
        return compact[:limit].rstrip()

    @staticmethod
    def _biases(value: object) -> dict[str, str]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise DraftBlockedError(("CONTENT_SOURCE_BIASES_INVALID",))
        result: dict[str, str] = {}
        for item in value:
            if not isinstance(item, Mapping):
                continue
            timeframe = item.get("timeframe")
            direction = item.get("direction")
            if (
                isinstance(timeframe, str)
                and timeframe.casefold() in {"1d", "4h", "1h"}
                and isinstance(direction, str)
                and direction in {"BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN"}
            ):
                result[timeframe.casefold()] = direction
        if set(result) != {"1d", "4h", "1h"}:
            raise DraftBlockedError(("CONTENT_SOURCE_BIASES_INCOMPLETE",))
        return result

    @staticmethod
    def _radar(value: object) -> str:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise DraftBlockedError(("CONTENT_SOURCE_RADAR_INVALID",))
        if not value:
            return "SETUP_YOK"
        item = value[0]
        if not isinstance(item, Mapping):
            raise DraftBlockedError(("CONTENT_SOURCE_RADAR_INVALID",))
        name = item.get("setup_name")
        tier = item.get("setup_tier")
        if not isinstance(name, str) or not name.strip() or not isinstance(tier, str):
            raise DraftBlockedError(("CONTENT_SOURCE_RADAR_INVALID",))
        compact_name = " ".join(name.split())[:24].rstrip()
        if tier not in {"A*", "A", "B", "C", "NO_TRADE"}:
            raise DraftBlockedError(("CONTENT_SOURCE_RADAR_INVALID",))
        return f"{compact_name} ({tier})"
