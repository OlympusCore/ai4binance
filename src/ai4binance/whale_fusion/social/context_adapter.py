"""Project classified social events into the shared advisory context contract."""

from typing import Literal

from ai4binance.intelligence.event_context import EventObservation
from ai4binance.whale_fusion.social.models import SocialEvent, SocialStance


def to_event_observation(
    event: SocialEvent, *, symbol: str, asset: str,
    market_type: Literal["SPOT", "USD_M_FUTURES"], root_ids: tuple[str, ...],
) -> EventObservation:
    """Keep upstream original-post roots and never equate account confidence to fact verification."""
    if asset not in event.assets:
        raise ValueError("social event does not concern the requested asset")
    first_seen = min(row.observed_at for row in event.provenance)
    available = max(row.observed_at for row in event.provenance)
    polarity = {SocialStance.SUPPORTIVE: 1.0, SocialStance.NEGATIVE: -1.0,
                SocialStance.NEUTRAL: 0.0}.get(event.stance)
    return EventObservation(
        observation_id=event.event_id, symbol=symbol, market_type=market_type,
        source_refs=tuple(sorted({row.source_url for row in event.provenance})),
        root_ids=root_ids, published_at=event.timestamp, first_seen_at=first_seen,
        available_at=available, window_start=event.timestamp, window_end=event.timestamp,
        verification="UNVERIFIED", source_quality=float(event.confidence),
        polarity=polarity, narrative=event.event_type.value,
    )
