"""Bounded adapters for decision-time news and sentiment evidence, not signals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Literal, Protocol

from pydantic import ConfigDict, Field, TypeAdapter, ValidationError
from pydantic.dataclasses import dataclass as validated_dataclass

Identity = Annotated[
    str, Field(strict=True, min_length=1, max_length=500, pattern=r"\S")
]
Unit = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
Metric = Annotated[float, Field(strict=True, allow_inf_nan=False)]
CHANNELS = ("news", "sentiment")


class EventSnapshot(Protocol):
    """Read-only decision context without a dependency on the aggregate schema."""

    @property
    def snapshot_id(self) -> str: ...

    @property
    def symbol(self) -> str: ...

    @property
    def market_type(self) -> str: ...

    @property
    def created_at(self) -> datetime: ...

    @property
    def news_snapshot(self) -> Mapping[str, object]: ...

    @property
    def sentiment_snapshot(self) -> Mapping[str, object]: ...


@validated_dataclass(
    frozen=True, config=ConfigDict(extra="forbid", revalidate_instances="always")
)
class EventObservation:
    """A revision available at a known time; unknown measurements remain absent."""

    observation_id: Identity
    symbol: Identity
    market_type: Literal["SPOT", "USD_M_FUTURES"]
    source_refs: tuple[Identity, ...]
    root_ids: tuple[Identity, ...]
    published_at: datetime
    first_seen_at: datetime
    available_at: datetime
    window_start: datetime
    window_end: datetime
    verification: Literal["VERIFIED", "UNVERIFIED", "CONFLICTING"]
    source_quality: Unit
    revision_at: datetime | None = None
    polarity: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)] | None = None
    volume: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    velocity: Metric | None = None
    delta: Metric | None = None
    event_severity: Literal["UNKNOWN", "LOW", "ELEVATED", "HIGH", "CRITICAL"] = (
        "UNKNOWN"
    )
    narrative: Identity = "NOT_MEASURED"
    crowding: Identity = "NOT_MEASURED"
    risk_review_required: Annotated[bool, Field(strict=True)] = False

    def __post_init__(self) -> None:
        stamps = (
            self.published_at,
            self.first_seen_at,
            self.available_at,
            self.window_start,
            self.window_end,
        )
        if any(stamp.utcoffset() is None for stamp in stamps):
            raise ValueError("event timestamps must be timezone-aware")
        if not (
            self.published_at <= self.first_seen_at <= self.available_at
            and self.window_start <= self.window_end <= self.available_at
        ):
            raise ValueError("event chronology is invalid")
        if self.revision_at is not None and (
            self.revision_at.utcoffset() is None
            or not self.published_at <= self.revision_at <= self.available_at
        ):
            raise ValueError(
                "revision cannot predate publication or arrive after availability"
            )
        if any(
            not values or len(values) > 100 or len(set(values)) != len(values)
            for values in (self.source_refs, self.root_ids)
        ):
            raise ValueError("event provenance must be unique, nonempty and bounded")


EVENT_ADAPTER = TypeAdapter(EventObservation)


@dataclass(frozen=True, slots=True)
class EventContextEvidence:
    snapshot_id: str
    channel: str
    status: str
    observations: tuple[EventObservation, ...] = ()
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or self.channel not in CHANNELS:
            raise ValueError("event context identity is invalid")
        if self.status not in {"AVAILABLE", "DATA_UNAVAILABLE", "DATA_INVALID"}:
            raise ValueError("event context status is invalid")
        if (self.status == "AVAILABLE") != bool(self.observations):
            raise ValueError("available context requires observations")

    @property
    def root_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted({root for row in self.observations for root in row.root_ids})
        )

    @property
    def measurement_status(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (
                name,
                "MEASURED"
                if any(getattr(row, name) is not None for row in self.observations)
                else "NOT_MEASURED",
            )
            for name in ("polarity", "volume", "velocity", "delta")
        )


def bind_event_context(
    snapshot: EventSnapshot,
    channel: str,
    *,
    required: bool = False,
    maximum_age: timedelta = timedelta(hours=24),
) -> EventContextEvidence:
    """Legacy scores are not upgraded to verified point-in-time observations."""
    if channel not in CHANNELS or maximum_age <= timedelta(0):
        raise ValueError("invalid event context policy")
    raw = snapshot.news_snapshot if channel == "news" else snapshot.sentiment_snapshot
    values = raw.get("observations")
    missing = f"{channel.upper()}_CONTEXT_UNAVAILABLE"
    if values is None or values == () or values == []:
        return EventContextEvidence(
            snapshot.snapshot_id,
            channel,
            "DATA_UNAVAILABLE",
            warnings=(missing,),
            blockers=(missing,) if required else (),
        )
    try:
        if not isinstance(values, (tuple, list)):
            raise ValueError("event observations must be a bounded sequence")
        if len(values) > 256:
            raise ValueError("event observations exceed the bounded limit")
        rows = tuple(
            EVENT_ADAPTER.validate_python(
                dict(value) if isinstance(value, Mapping) else value
            )
            for value in values
        )
        _validate_snapshot_rows(snapshot, rows, maximum_age)
    except ValidationError, ValueError, TypeError:
        reason = f"{channel.upper()}_CONTEXT_INVALID_OR_UNAVAILABLE_AT_DECISION"
        # Explicit malformed supplied data cannot suppress a valid risk row in
        # the same batch by making an optional channel look merely absent.
        return EventContextEvidence(
            snapshot.snapshot_id,
            channel,
            "DATA_INVALID",
            warnings=(reason,),
            blockers=(reason,),
        )
    warnings = tuple(
        sorted(
            {
                f"{channel.upper()}_{row.verification}"
                for row in rows
                if row.verification != "VERIFIED"
            }
        )
    )
    # The deterministic adapter owns the veto. Provider text is never a blocker code.
    blockers = tuple(
        sorted(
            {
                f"{channel.upper()}_CRITICAL_EVENT_REVIEW_REQUIRED"
                for row in rows
                if row.event_severity == "CRITICAL"
            }
        )
    )
    if required and any(row.verification != "VERIFIED" for row in rows):
        blockers += (f"{channel.upper()}_VERIFICATION_REQUIRED",)
    if any(row.risk_review_required for row in rows):
        blockers += (f"{channel.upper()}_EVENT_RISK_REVIEW_REQUIRED",)
    return EventContextEvidence(
        snapshot.snapshot_id, channel, "AVAILABLE", rows, warnings, blockers
    )


def _validate_snapshot_rows(
    snapshot: EventSnapshot, rows: tuple[EventObservation, ...], maximum_age: timedelta
) -> None:
    ids = [row.observation_id for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(
            "duplicate observation IDs require explicit upstream revision selection"
        )
    for row in rows:
        if (row.symbol, row.market_type) != (snapshot.symbol, snapshot.market_type):
            raise ValueError("event identity does not match the snapshot")
        if (
            row.available_at > snapshot.created_at
            or snapshot.created_at - row.window_end > maximum_age
        ):
            raise ValueError("event is stale or unavailable at decision time")


def context_payload(
    rows: tuple[EventObservation, ...],
) -> dict[str, tuple[dict[str, object], ...]]:
    """Canonical snapshot input shape for existing source adapters."""
    if len(rows) > 256:
        raise ValueError("event observation payload exceeds the bounded limit")
    return {
        "observations": tuple(
            EVENT_ADAPTER.dump_python(row, mode="json") for row in rows
        )
    }
