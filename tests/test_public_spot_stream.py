"""Official Binance Spot public stream contract and ingest tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.events import DiskEventJournal
from ai4binance.exchange import (
    BinanceSpotKlineParser,
    BinanceSpotStreamPolicy,
    PublicKlineIngestor,
    PublicStreamRecovery,
    SpotKlineUpdate,
    SpotStreamServerShutdown,
    StreamRecoveryPolicy,
    StreamState,
)
from ai4binance.exchange.errors import ExchangePayloadError

OPEN_TIME = datetime(2026, 7, 13, 9, 0, tzinfo=UTC)
EVENT_TIME = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)


def kline_payload(
    *,
    closed: bool = False,
    first_trade_id: int = 100,
    last_trade_id: int = 101,
    trade_count: int = 2,
    symbol: str = "HOTUSDT",
    interval: str = "1h",
    event_time: datetime = EVENT_TIME,
    open_time: datetime = OPEN_TIME,
) -> dict[str, object]:
    close_time = open_time + timedelta(hours=1) - timedelta(milliseconds=1)
    return {
        "e": "kline",
        "E": int(event_time.timestamp() * 1_000),
        "s": symbol,
        "k": {
            "t": int(open_time.timestamp() * 1_000),
            "T": int(close_time.timestamp() * 1_000),
            "s": symbol,
            "i": interval,
            "f": first_trade_id,
            "L": last_trade_id,
            "o": "0.0010",
            "c": "0.0012",
            "h": "0.0013",
            "l": "0.0009",
            "v": "1000",
            "n": trade_count,
            "x": closed,
        },
    }


def encoded(payload: object) -> str:
    return json.dumps(payload, separators=(",", ":"))


def live_ingestor(
    policy: StreamRecoveryPolicy | None = None,
) -> PublicKlineIngestor:
    ingestor = PublicKlineIngestor(
        "HOTUSDT",
        "1h",
        recovery=PublicStreamRecovery(policy or StreamRecoveryPolicy()),
    )
    transition = ingestor.bootstrap(snapshot_sequence=99, connected_at=OPEN_TIME)
    assert transition.state is StreamState.LIVE
    return ingestor


def test_parser_accepts_raw_and_combined_official_kline_shapes() -> None:
    parser = BinanceSpotKlineParser()
    raw = parser.parse(encoded(kline_payload(closed=True)))
    assert isinstance(raw, SpotKlineUpdate)
    assert raw.symbol == "HOTUSDT"
    assert raw.sequence_bounds == (100, 101)
    assert raw.as_candle().timestamp == OPEN_TIME

    combined = parser.parse(
        encoded(
            {
                "stream": "hotusdt@kline_1h",
                "data": kline_payload(closed=True),
            }
        )
    )
    assert combined == raw


def test_ingestor_rejects_open_and_duplicate_candles_without_execution() -> None:
    ingestor = live_ingestor()
    open_result = ingestor.ingest(encoded(kline_payload()))
    assert open_result.transition.accepted is True
    assert open_result.blockers == ("OPEN_KLINE_NOT_DECISION_ELIGIBLE",)
    assert open_result.decision_eligible is False

    closed = ingestor.ingest(encoded(kline_payload(closed=True)))
    assert closed.candle is not None
    assert closed.decision_eligible is True
    assert closed.execution_allowed is False
    assert closed.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    duplicate = ingestor.ingest(encoded(kline_payload(closed=True)))
    assert duplicate.candle is None
    assert duplicate.blockers == ("DUPLICATE_OR_OLD_CLOSED_KLINE",)


def test_closed_kline_creates_replayable_journal_event(tmp_path: Path) -> None:
    result = live_ingestor().ingest(encoded(kline_payload(closed=True)))
    assert result.update is not None
    event = result.update.to_domain_event(sequence=1)
    journal = DiskEventJournal(tmp_path / "market-events.jsonl", durable=False)
    journal.append(event)

    loaded = journal.load()
    assert loaded == (event,)
    assert loaded[0].event_type == "SPOT_KLINE_CLOSED"
    assert loaded[0].payload_dict()["symbol"] == "HOTUSDT"


def test_gap_backpressure_and_unsequenced_updates_fail_closed() -> None:
    gap = live_ingestor().ingest(
        encoded(kline_payload(first_trade_id=103, last_trade_id=104))
    )
    assert gap.transition.state is StreamState.GAP_DETECTED
    assert gap.blockers == ("STREAM_SEQUENCE_GAP",)

    limited = live_ingestor(StreamRecoveryPolicy(maximum_queue_depth=1)).ingest(
        encoded(kline_payload()), queue_depth=2
    )
    assert limited.transition.state is StreamState.DEGRADED
    assert limited.blockers == ("STREAM_BACKPRESSURE_LIMIT_EXCEEDED",)

    empty = live_ingestor().ingest(
        encoded(
            kline_payload(
                closed=True,
                first_trade_id=-1,
                last_trade_id=-1,
                trade_count=0,
            )
        )
    )
    assert empty.blockers == ("KLINE_TRADE_SEQUENCE_UNAVAILABLE",)
    assert empty.candle is None


def test_shutdown_and_connection_rollover_require_planned_reconnect() -> None:
    ingestor = live_ingestor()
    shutdown = ingestor.ingest(
        encoded(
            {
                "e": "serverShutdown",
                "E": int(EVENT_TIME.timestamp() * 1_000),
            }
        )
    )
    assert shutdown.transition.state is StreamState.DISCONNECTED
    assert shutdown.blockers == ("STREAM_SERVER_SHUTDOWN",)
    assert shutdown.update is None

    rollover = live_ingestor().recovery.check_connection_rollover(
        OPEN_TIME + timedelta(hours=23, minutes=55)
    )
    assert rollover.state is StreamState.DISCONNECTED
    assert rollover.blockers == ("STREAM_CONNECTION_ROLLOVER_REQUIRED",)

    healthy = live_ingestor().recovery.check_connection_rollover(
        OPEN_TIME + timedelta(hours=1)
    )
    assert healthy.accepted is True


def test_stream_policy_enforces_official_bounds() -> None:
    policy = BinanceSpotStreamPolicy(maximum_streams_per_connection=2)
    policy.validate_subscriptions(("hotusdt@kline_1h", "hotusdt@kline_4h"))
    with pytest.raises(ValueError, match="subscriptions"):
        policy.validate_subscriptions(())
    with pytest.raises(ValueError, match="subscriptions"):
        policy.validate_subscriptions(("HOTUSDT@kline_1h",))
    with pytest.raises(ValueError, match="subscriptions"):
        policy.validate_subscriptions(
            ("hotusdt@kline_1h", "hotusdt@kline_4h", "hotusdt@kline_1d")
        )
    with pytest.raises(ValueError, match="policy"):
        BinanceSpotStreamPolicy(maximum_control_messages_per_second=0)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"e": "trade", "E": int(EVENT_TIME.timestamp() * 1_000)},
        kline_payload(symbol="hotusdt"),
        kline_payload(interval="7m"),
        kline_payload(first_trade_id=102, last_trade_id=101),
        kline_payload(trade_count=-1),
    ],
)
def test_parser_rejects_unsupported_or_invalid_payloads(payload: object) -> None:
    with pytest.raises(ExchangePayloadError):
        BinanceSpotKlineParser().parse(encoded(payload))


def test_parser_rejects_bad_json_size_identity_and_field_types() -> None:
    parser = BinanceSpotKlineParser(BinanceSpotStreamPolicy(maximum_message_bytes=16))
    with pytest.raises(ExchangePayloadError, match="size"):
        parser.parse("x" * 17)
    with pytest.raises(ExchangePayloadError, match="JSON"):
        BinanceSpotKlineParser().parse(b"\xff")
    with pytest.raises(ExchangePayloadError, match="identity"):
        BinanceSpotKlineParser().parse(
            encoded(
                {
                    "stream": "btcusdt@kline_1h",
                    "data": kline_payload(),
                }
            )
        )
    mismatched_symbol = kline_payload()
    nested = mismatched_symbol["k"]
    assert isinstance(nested, dict)
    nested["s"] = "BTCUSDT"
    with pytest.raises(ExchangePayloadError, match="symbol identity"):
        BinanceSpotKlineParser().parse(encoded(mismatched_symbol))
    wrong_closed = kline_payload()
    kline = wrong_closed["k"]
    assert isinstance(kline, dict)
    kline["x"] = "false"
    with pytest.raises(ExchangePayloadError, match="boolean"):
        BinanceSpotKlineParser().parse(encoded(wrong_closed))


def test_contracts_reject_invalid_direct_use_and_identity() -> None:
    ingestor = live_ingestor()
    with pytest.raises(ExchangePayloadError, match="identity"):
        ingestor.ingest(encoded(kline_payload(symbol="BTCUSDT")))
    with pytest.raises(ValueError, match="identity"):
        PublicKlineIngestor("bad-symbol", "1h")

    update = BinanceSpotKlineParser().parse(encoded(kline_payload()))
    assert isinstance(update, SpotKlineUpdate)
    with pytest.raises(ValueError, match="decision candle"):
        update.as_candle()
    with pytest.raises(ValueError, match="journaled"):
        update.to_domain_event(sequence=1)
    with pytest.raises(ValueError, match="timezone-aware"):
        SpotStreamServerShutdown(EVENT_TIME.replace(tzinfo=None))

    recovery = PublicStreamRecovery()
    recovery.start()
    recovery.connected()
    recovery.apply_snapshot(1, OPEN_TIME)
    with pytest.raises(ValueError, match="age is unavailable"):
        recovery.check_connection_rollover(EVENT_TIME)
