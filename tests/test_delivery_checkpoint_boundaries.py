"""Durable event delivery refuses gaps, corrupt checkpoints, and authority drift."""

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.events.delivery import (
    DiskConsumerCheckpointStore,
    DurableConsumerCheckpoint,
    DurableEventCheckpointCorruptionError,
    DurableEventDelivery,
    DurableEventDeliveryError,
    durable_event_idempotency_key,
)
from tests.test_event_delivery import NOW, build_events


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sequence", 0, "sequence"),
        ("event_id", " ", "identity"),
        ("event_hash", "g" * 64, "hash"),
        ("updated_at", datetime(2026, 1, 1), "timezone-aware"),
        ("schema_version", "2", "unsupported"),
    ],
)
def test_checkpoint_rejects_invalid_progress_contract(
    field: str, value: object, message: str
) -> None:
    event = build_events()[0]
    checkpoint = DurableConsumerCheckpoint(
        "consumer", 1, event.event_id, event.event_hash, NOW
    )
    with pytest.raises(ValueError, match=message):
        replace(checkpoint, **{field: cast(Any, value)})


def test_delivery_contract_cannot_enable_execution() -> None:
    event = build_events()[0]
    delivery = DurableEventDelivery(
        "consumer", event, durable_event_idempotency_key("consumer", event)
    )
    with pytest.raises(ValueError, match="execution authority"):
        replace(delivery, execution_allowed=True)
    with pytest.raises(ValueError, match="live eligibility"):
        replace(delivery, live_eligibility_status="LIVE")


def test_incremental_delivery_requires_contiguous_verified_progress(
    tmp_path: Path,
) -> None:
    first, second = build_events()
    store = DiskConsumerCheckpointStore(tmp_path, durable=False)
    delivered: list[DurableEventDelivery] = []
    assert not store.deliver_next("consumer", delivered.append, second, first)
    assert delivered == []
    assert store.deliver_next("consumer", delivered.append, first, None)
    assert store.deliver_next("consumer", delivered.append, first, None)
    assert len(delivered) == 1
    assert not store.deliver_next("consumer", delivered.append, second, None)
    assert len(delivered) == 1
    assert store.deliver_next("consumer", delivered.append, second, first)
    assert [item.event.sequence for item in delivered] == [1, 2]
    path = next(tmp_path.glob("*.checkpoint.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["event_id"] = "different-event"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(
        DurableEventCheckpointCorruptionError, match="does not match delivered"
    ):
        store.deliver_next("consumer", delivered.append, second, first)
    assert len(delivered) == 2


def test_checkpoint_byte_capacity_preserves_uncommitted_progress(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="size limit"):
        DiskConsumerCheckpointStore(tmp_path, maximum_checkpoint_bytes=255)
    store = DiskConsumerCheckpointStore(tmp_path, maximum_checkpoint_bytes=256)
    delivered: list[DurableEventDelivery] = []
    with pytest.raises(DurableEventDeliveryError) as error:
        store.deliver_pending("consumer" + "x" * 100, delivered.append, build_events())
    assert isinstance(error.value.__cause__, OverflowError)
    assert len(delivered) == 1
    assert not list(tmp_path.glob("*.checkpoint.json"))


@pytest.mark.parametrize("mutation", ["oversized", "duplicate", "invalid_chain"])
def test_corrupt_checkpoint_or_event_chain_blocks_further_delivery(
    tmp_path: Path, mutation: str
) -> None:
    store = DiskConsumerCheckpointStore(tmp_path, durable=False)
    events = build_events()
    store.deliver_pending("consumer", lambda delivery: None, events)
    path = next(tmp_path.glob("*.checkpoint.json"))
    if mutation == "oversized":
        path.write_text(" " * 65_537, encoding="utf-8")
    elif mutation == "duplicate":
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("{", '{"sequence":2,', 1), encoding="utf-8")
    else:
        events = tuple(reversed(events))
    delivered: list[DurableEventDelivery] = []
    with pytest.raises(
        (DurableEventCheckpointCorruptionError, DurableEventDeliveryError)
    ):
        store.deliver_pending("consumer", delivered.append, events)
    assert delivered == []
