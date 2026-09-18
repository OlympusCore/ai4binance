"""Durable at-least-once event delivery and checkpoint safety tests."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Lock

import pytest

from ai4binance.events import (
    DiskConsumerCheckpointStore,
    DiskEventJournal,
    DomainEvent,
    DurableEventCheckpointCorruptionError,
    DurableEventDelivery,
    DurableEventDeliveryError,
    JournaledEventRuntime,
    durable_event_idempotency_key,
)

NOW = datetime(2026, 9, 9, tzinfo=UTC)


def build_events() -> tuple[DomainEvent, ...]:
    first = DomainEvent.create(
        event_id="delivery-event-1",
        aggregate_id="paper-order-delivery",
        event_type="ORDER_SUBMITTED",
        sequence=1,
        occurred_at=NOW,
    )
    second = DomainEvent.create(
        event_id="delivery-event-2",
        aggregate_id="paper-order-delivery",
        event_type="ORDER_ACCEPTED",
        sequence=2,
        occurred_at=NOW + timedelta(seconds=1),
        previous_hash=first.event_hash,
    )
    return first, second


def checkpoint_file(runtime: JournaledEventRuntime) -> Path:
    store = runtime.checkpoint_store
    assert store is not None
    return next(store.root.glob("*.checkpoint.json"))


def test_durable_consumer_recovers_crash_window_and_does_not_redeliver(
    tmp_path: Path,
) -> None:
    journal = DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    event = build_events()[0]
    journal.append(event)

    first_delivery: list[DurableEventDelivery] = []
    restarted = JournaledEventRuntime.open(
        DiskEventJournal(journal.path, durable=False)
    )
    restarted.subscribe_durable("paper_projection", first_delivery.append)

    assert tuple(delivery.event for delivery in first_delivery) == (event,)
    assert first_delivery[0].execution_allowed is False
    assert first_delivery[0].live_eligibility_status == "LIVE_ORDER_BLOCKED"

    second_delivery: list[DurableEventDelivery] = []
    restarted_again = JournaledEventRuntime.open(
        DiskEventJournal(journal.path, durable=False)
    )
    restarted_again.subscribe_durable("paper_projection", second_delivery.append)

    assert second_delivery == []
    store = restarted_again.checkpoint_store
    assert store is not None
    checkpoint = store.load_verified("paper_projection", restarted_again.snapshot())
    assert checkpoint is not None
    assert checkpoint.sequence == 1
    assert checkpoint.event_id == event.event_id
    assert checkpoint.event_hash == event.event_hash


def test_handler_failure_preserves_offset_and_stable_idempotency_key(
    tmp_path: Path,
) -> None:
    journal = DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    for event in build_events():
        journal.append(event)
    runtime = JournaledEventRuntime.open(journal)
    attempted_keys: list[str] = []

    def fail_second(delivery: DurableEventDelivery) -> None:
        attempted_keys.append(delivery.idempotency_key)
        if delivery.event.sequence == 2:
            raise RuntimeError("simulated side-effect failure")

    with pytest.raises(DurableEventDeliveryError, match="sequence 2"):
        runtime.subscribe_durable("paper_projection", fail_second)

    store = runtime.checkpoint_store
    assert store is not None
    checkpoint = store.load_verified("paper_projection", runtime.snapshot())
    assert checkpoint is not None
    assert checkpoint.sequence == 1

    retried: list[DurableEventDelivery] = []
    restarted = JournaledEventRuntime.open(
        DiskEventJournal(journal.path, durable=False)
    )
    restarted.subscribe_durable("paper_projection", retried.append)

    assert tuple(delivery.event.sequence for delivery in retried) == (2,)
    assert retried[0].idempotency_key == attempted_keys[-1]


def test_checkpoint_write_failure_is_propagated_without_false_advancement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    event = build_events()[0]
    journal.append(event)
    runtime = JournaledEventRuntime.open(journal)
    observed: list[DurableEventDelivery] = []

    def fail_write(
        _store: DiskConsumerCheckpointStore,
        _consumer_id: str,
        _event: DomainEvent,
    ) -> None:
        raise OSError("simulated checkpoint failure")

    monkeypatch.setattr(DiskConsumerCheckpointStore, "_write_unlocked", fail_write)

    with pytest.raises(DurableEventDeliveryError, match="sequence 1") as raised:
        runtime.subscribe_durable("paper_projection", observed.append)

    assert isinstance(raised.value.__cause__, OSError)
    assert tuple(delivery.event for delivery in observed) == (event,)
    store = runtime.checkpoint_store
    assert store is not None
    assert tuple(store.root.glob("*.checkpoint.json")) == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("consumer_id", "other_consumer"),
        ("sequence", 2),
        ("event_id", "other-event"),
        ("event_hash", "f" * 64),
        ("schema_version", "2.0"),
        ("sequence", True),
        ("consumer_id", 7),
        ("event_id", 7),
        ("event_hash", 7),
        ("schema_version", 7),
        ("updated_at", 7),
    ],
)
def test_checkpoint_identity_and_schema_mismatch_fail_closed(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    journal = DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    journal.append(build_events()[0])
    runtime = JournaledEventRuntime.open(journal)
    runtime.subscribe_durable("paper_projection", lambda _delivery: None)
    target = checkpoint_file(runtime)
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload[field] = value
    target.write_text(json.dumps(payload), encoding="utf-8")
    observed: list[DurableEventDelivery] = []

    restarted = JournaledEventRuntime.open(
        DiskEventJournal(journal.path, durable=False)
    )
    with pytest.raises(DurableEventCheckpointCorruptionError):
        restarted.subscribe_durable("paper_projection", observed.append)

    assert observed == []


@pytest.mark.parametrize(
    "payload",
    [b"not-json", b"x" * 65_537],
    ids=["malformed", "oversized"],
)
def test_malformed_and_oversized_checkpoints_fail_closed(
    tmp_path: Path,
    payload: bytes,
) -> None:
    journal = DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    journal.append(build_events()[0])
    runtime = JournaledEventRuntime.open(journal)
    runtime.subscribe_durable("paper_projection", lambda _delivery: None)
    checkpoint_file(runtime).write_bytes(payload)

    restarted = JournaledEventRuntime.open(
        DiskEventJournal(journal.path, durable=False)
    )
    with pytest.raises(DurableEventCheckpointCorruptionError):
        restarted.subscribe_durable("paper_projection", lambda _delivery: None)


@pytest.mark.parametrize(
    "consumer_id",
    ["", "../escape", "..\\escape", "/absolute", "nested/consumer", " consumer", "ç"],
)
def test_consumer_identifiers_cannot_control_checkpoint_paths(
    tmp_path: Path,
    consumer_id: str,
) -> None:
    root = tmp_path / "consumer-state"
    store = DiskConsumerCheckpointStore(root, durable=False)

    with pytest.raises(ValueError, match="consumer identity"):
        store.load_verified(consumer_id, ())

    assert not root.exists()


def test_consumers_have_independent_offsets_and_deterministic_dispatch_order(
    tmp_path: Path,
) -> None:
    runtime = JournaledEventRuntime.open(
        DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    )
    observed: list[tuple[str, int]] = []
    runtime.subscribe_durable(
        "zeta_projection",
        lambda delivery: observed.append(
            (delivery.consumer_id, delivery.event.sequence)
        ),
    )
    runtime.subscribe_durable(
        "alpha_projection",
        lambda delivery: observed.append(
            (delivery.consumer_id, delivery.event.sequence)
        ),
    )

    runtime.publish(build_events()[0])

    assert observed == [
        ("alpha_projection", 1),
        ("zeta_projection", 1),
    ]
    store = runtime.checkpoint_store
    assert store is not None
    assert store.load_verified("alpha_projection", runtime.snapshot()) is not None
    assert store.load_verified("zeta_projection", runtime.snapshot()) is not None
    assert len(tuple(store.root.glob("*.checkpoint.json"))) == 2


def test_ephemeral_failure_cannot_suppress_persisted_durable_delivery(
    tmp_path: Path,
) -> None:
    runtime = JournaledEventRuntime.open(
        DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    )
    durable: list[DomainEvent] = []
    runtime.subscribe_durable(
        "paper_projection",
        lambda delivery: durable.append(delivery.event),
    )

    def fail_ephemeral(_event: DomainEvent) -> None:
        raise RuntimeError("simulated ephemeral failure")

    runtime.subscribe(fail_ephemeral)
    event = build_events()[0]

    with pytest.raises(RuntimeError, match="simulated ephemeral failure"):
        runtime.publish(event)

    assert durable == [event]
    assert runtime.journal.load() == (event,)


def test_multiple_dispatch_failures_are_preserved(
    tmp_path: Path,
) -> None:
    runtime = JournaledEventRuntime.open(
        DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    )

    def fail_durable(_delivery: DurableEventDelivery) -> None:
        raise RuntimeError("durable failure")

    def fail_ephemeral(_event: DomainEvent) -> None:
        raise RuntimeError("ephemeral failure")

    runtime.subscribe_durable("paper_projection", fail_durable)
    runtime.subscribe(fail_ephemeral)

    with pytest.raises(ExceptionGroup) as raised:
        runtime.publish(build_events()[0])

    assert len(raised.value.exceptions) == 2
    assert isinstance(raised.value.exceptions[0], RuntimeError)
    assert isinstance(raised.value.exceptions[1], DurableEventDeliveryError)


def test_bus_rejection_and_journal_read_failure_are_aggregated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = JournaledEventRuntime.open(
        DiskEventJournal(tmp_path / "events.jsonl", durable=False),
        capacity=1,
    )
    observed: list[DomainEvent] = []
    runtime.subscribe_durable(
        "paper_projection",
        lambda delivery: observed.append(delivery.event),
    )
    first, second = build_events()
    runtime.publish(first)

    def fail_load(_journal: object) -> tuple[DomainEvent, ...]:
        raise OSError("simulated journal read failure")

    monkeypatch.setattr(type(runtime.journal), "load", fail_load)

    with pytest.raises(ExceptionGroup) as raised:
        runtime.publish(second)

    assert len(raised.value.exceptions) == 2
    assert isinstance(raised.value.exceptions[0], OverflowError)
    assert isinstance(raised.value.exceptions[1], OSError)
    assert observed == [first]
    assert len(runtime.journal.path.read_bytes().splitlines()) == 2


def test_lag_catchup_journal_read_failure_remains_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = JournaledEventRuntime.open(
        DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    )
    runtime.subscribe_durable("paper_projection", lambda _delivery: None)
    first, second = build_events()
    runtime.publish(first)
    checkpoint_file(runtime).unlink()

    def fail_load(_journal: object) -> tuple[DomainEvent, ...]:
        raise OSError("simulated lag catch-up read failure")

    monkeypatch.setattr(type(runtime.journal), "load", fail_load)

    with pytest.raises(OSError, match="lag catch-up read failure"):
        runtime.publish(second)

    assert len(runtime.journal.path.read_bytes().splitlines()) == 2


def test_lag_catchup_handler_failure_does_not_advance_checkpoint(
    tmp_path: Path,
) -> None:
    runtime = JournaledEventRuntime.open(
        DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    )
    fail_delivery = False
    observed: list[DurableEventDelivery] = []

    def consume(delivery: DurableEventDelivery) -> None:
        observed.append(delivery)
        if fail_delivery:
            raise RuntimeError("simulated lag catch-up handler failure")

    runtime.subscribe_durable("paper_projection", consume)
    first, second = build_events()
    runtime.publish(first)
    original_key = observed[0].idempotency_key
    checkpoint_file(runtime).unlink()
    fail_delivery = True

    with pytest.raises(DurableEventDeliveryError, match="sequence 1") as raised:
        runtime.publish(second)

    assert isinstance(raised.value.__cause__, RuntimeError)
    assert observed[-1].event == first
    assert observed[-1].idempotency_key == original_key
    store = runtime.checkpoint_store
    assert store is not None
    assert tuple(store.root.glob("*.checkpoint.json")) == ()


def test_existing_subscribe_remains_ephemeral_after_restart(tmp_path: Path) -> None:
    journal = DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    journal.append(build_events()[0])
    runtime = JournaledEventRuntime.open(journal)
    observed: list[DomainEvent] = []

    runtime.subscribe(observed.append)

    assert observed == []


def test_duplicate_checkpoint_keys_fail_closed_before_handler(
    tmp_path: Path,
) -> None:
    journal = DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    journal.append(build_events()[0])
    runtime = JournaledEventRuntime.open(journal)
    runtime.subscribe_durable("paper_projection", lambda _delivery: None)
    target = checkpoint_file(runtime)
    encoded = target.read_text(encoding="utf-8")
    target.write_text(
        encoded.replace(
            '"consumer_id":',
            '"consumer_id":"paper_projection","consumer_id":',
            1,
        ),
        encoding="utf-8",
    )
    observed: list[DurableEventDelivery] = []

    restarted = JournaledEventRuntime.open(
        DiskEventJournal(journal.path, durable=False)
    )
    with pytest.raises(DurableEventCheckpointCorruptionError):
        restarted.subscribe_durable("paper_projection", observed.append)

    assert observed == []


def test_delivery_envelope_cannot_grant_execution_or_live_eligibility() -> None:
    event = build_events()[0]
    key = durable_event_idempotency_key("paper_projection", event)

    with pytest.raises(ValueError, match="execution authority"):
        DurableEventDelivery(
            consumer_id="paper_projection",
            event=event,
            idempotency_key=key,
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="live eligibility"):
        DurableEventDelivery(
            consumer_id="paper_projection",
            event=event,
            idempotency_key=key,
            live_eligibility_status="LIVE_ELIGIBLE",
        )


def test_publish_without_durable_consumers_does_not_copy_complete_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = JournaledEventRuntime.open(
        DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    )

    def fail_snapshot(_bus: object) -> tuple[DomainEvent, ...]:
        raise AssertionError("publish copied complete in-memory history")

    monkeypatch.setattr(type(runtime.bus), "snapshot", fail_snapshot)

    runtime.publish(build_events()[0])


def test_contiguous_durable_publish_does_not_require_complete_history_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = JournaledEventRuntime.open(
        DiskEventJournal(tmp_path / "events.jsonl", durable=False)
    )
    observed: list[DomainEvent] = []
    runtime.subscribe_durable(
        "paper_projection",
        lambda delivery: observed.append(delivery.event),
    )

    def fail_load(_journal: object) -> tuple[DomainEvent, ...]:
        raise AssertionError("contiguous delivery replayed complete history")

    monkeypatch.setattr(type(runtime.journal), "load", fail_load)
    event = build_events()[0]

    runtime.publish(event)

    assert observed == [event]


def test_distinct_store_instances_serialize_one_consumer_checkpoint(
    tmp_path: Path,
) -> None:
    events = (build_events()[0],)
    root = tmp_path / "consumer-state"
    stores = (
        DiskConsumerCheckpointStore(root, durable=False),
        DiskConsumerCheckpointStore(root, durable=False),
    )
    start = Barrier(2)
    observation_lock = Lock()
    observed: list[str] = []

    def deliver(store: DiskConsumerCheckpointStore) -> None:
        start.wait()

        def consume(delivery: DurableEventDelivery) -> None:
            with observation_lock:
                observed.append(delivery.idempotency_key)

        store.deliver_pending("paper_projection", consume, events)

    with ThreadPoolExecutor(max_workers=2) as executor:
        tuple(executor.map(deliver, stores))

    assert len(observed) == 1
