"""Local fixtures for multi-market depth bridging, durable replay, and recovery."""

import json
import shutil
import time
import zlib
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from ai4binance.data.market_depth import (
    DepthJournal,
    MarketDepthCollector,
    _checkpoint,
    apply_depth_event,
    apply_depth_snapshot,
    read_local_depth,
)
from ai4binance.exchange.client import JsonTransport
from ai4binance.exchange.order_book import BookLevel, ReadOnlyOrderBook

NOW = datetime(2026, 9, 11, tzinfo=UTC)


def _json_transport(value: object | None = None) -> JsonTransport:
    return cast(JsonTransport, object() if value is None else value)


def snapshot() -> dict[str, object]:
    return {"lastUpdateId": 100, "bids": [["99", "2"]], "asks": [["101", "3"]]}


def event(
    symbol: str, first: int = 100, last: int = 101, previous: int = 99
) -> dict[str, object]:
    return {
        "e": "depthUpdate",
        "s": symbol,
        "E": int(NOW.timestamp() * 1000),
        "U": first,
        "u": last,
        "pu": previous,
        "b": [["98", "5"]],
        "a": [["102", "4"]],
    }


@pytest.mark.parametrize(
    ("market", "symbol"),
    [
        ("spot", "BTCUSDT"),
        ("usd_m_futures", "BTCUSDT"),
        ("coin_m_futures", "BTCUSD_PERP"),
    ],
)
def test_snapshot_bridge_checkpoint_and_replay(
    tmp_path: Path, market: str, symbol: str
) -> None:
    path = tmp_path / "depth.sqlite3"
    journal = DepthJournal(path)
    book = ReadOnlyOrderBook(symbol, futures_sequence=market != "spot")
    apply_depth_snapshot(book, snapshot())
    first = event(symbol)
    assert apply_depth_event(book, first, market)
    later = event(symbol, 102, 103, 101)
    later["b"] = [["98", "0"]]
    assert apply_depth_event(book, later, market)
    journal.append(
        [
            (market, symbol, "snapshot", snapshot(), NOW.timestamp()),
            (market, symbol, "delta", first, NOW.timestamp()),
            (market, symbol, "delta", later, NOW.timestamp()),
        ]
    )
    result = read_local_depth(path, market, symbol, now=NOW)
    assert result["lastUpdateId"] == 103
    bids = result["bids"]
    assert isinstance(bids, list)
    assert ["98", "5"] not in bids
    assert result["execution_allowed"] is False
    journal.append([(market, symbol, "checkpoint", _checkpoint(book), NOW.timestamp())])
    following = event(symbol, 104, 105, 103)
    journal.append([(market, symbol, "delta", following, NOW.timestamp())])
    assert read_local_depth(path, market, symbol, now=NOW)["lastUpdateId"] == 105
    journal.close()


@pytest.mark.parametrize("market", ["spot", "usd_m_futures", "coin_m_futures"])
def test_gap_and_unsynchronized_are_never_readable(tmp_path: Path, market: str) -> None:
    journal = DepthJournal(tmp_path / "depth.db")
    journal.append([(market, "BTCUSDT", "snapshot", snapshot(), NOW.timestamp())])
    with pytest.raises(ValueError, match="unsynchronized"):
        read_local_depth(journal.path, market, "BTCUSDT", now=NOW)
    journal.append([(market, "BTCUSDT", "gap", {"reason": "offline"}, NOW.timestamp())])
    with pytest.raises(ValueError, match="unsynchronized"):
        read_local_depth(journal.path, market, "BTCUSDT", now=NOW)
    journal.close()


def test_futures_previous_id_is_mandatory_and_gap_blocks() -> None:
    book = ReadOnlyOrderBook("BTCUSD_PERP", futures_sequence=True)
    apply_depth_snapshot(book, snapshot())
    assert apply_depth_event(book, event(book.symbol, 99, 100, 95), "coin_m_futures")
    wrong = event(book.symbol, 101, 102, 99)
    with pytest.raises(ValueError, match="gap"):
        apply_depth_event(book, wrong, "coin_m_futures")
    with pytest.raises(ValueError, match="gap"):
        apply_depth_event(book, event(book.symbol, 101, 102, 100), "coin_m_futures")


@pytest.mark.parametrize(
    "mutation", ["identity", "type", "missing_pu", "crossed", "nan", "duplicate"]
)
def test_untrusted_depth_rejected(mutation: str) -> None:
    book = ReadOnlyOrderBook("BTCUSD_PERP", futures_sequence=True)
    apply_depth_snapshot(book, snapshot())
    raw = event(book.symbol)
    if mutation == "identity":
        raw["s"] = "ETHUSD_PERP"
    elif mutation == "type":
        raw["st"] = 1
    elif mutation == "missing_pu":
        raw.pop("pu")
    elif mutation == "crossed":
        raw["b"] = [["102", "4"]]
    elif mutation == "nan":
        raw["b"] = [["NaN", "4"]]
    else:
        raw["b"] = [["98", "4"], ["98", "5"]]
    with pytest.raises((ValueError, ArithmeticError)):
        apply_depth_event(book, raw, "coin_m_futures")


def test_stale_future_and_corrupt_local_journal_rejected(tmp_path: Path) -> None:
    journal = DepthJournal(tmp_path / "depth.db")
    journal.append(
        [
            ("spot", "BTCUSDT", "snapshot", snapshot(), NOW.timestamp()),
            ("spot", "BTCUSDT", "delta", event("BTCUSDT"), NOW.timestamp()),
        ]
    )
    for now in (NOW + timedelta(seconds=31), NOW - timedelta(seconds=1)):
        with pytest.raises(ValueError, match="stale"):
            read_local_depth(journal.path, "spot", "BTCUSDT", now=now)
    journal.connection.execute(
        "UPDATE depth_events SET payload=? WHERE kind='delta'", (b"invalid",)
    )
    journal.connection.commit()
    with pytest.raises(zlib.error):
        read_local_depth(journal.path, "spot", "BTCUSDT", now=NOW)
    journal.close()


@pytest.mark.parametrize("symbol", ["BTCUSD_PERP", "BTCUSD_260925", "币安人生USDT"])
def test_valid_contract_and_unicode_book_identities(symbol: str) -> None:
    assert ReadOnlyOrderBook(symbol).symbol == symbol


@pytest.mark.parametrize(
    "symbol", ["../BTCUSD_PERP", "BTC_USD_BAD", "BTCUSD_PERP/../", "BTCUSD_.."]
)
def test_depth_path_identities_reject_traversal(symbol: str) -> None:
    with pytest.raises(ValueError, match="symbol"):
        ReadOnlyOrderBook(symbol)


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_book_levels_rejected(number: str) -> None:
    with pytest.raises(ValueError, match="price"):
        BookLevel(Decimal(number), Decimal("1"))


def test_journal_batch_rollback(tmp_path: Path) -> None:
    journal = DepthJournal(tmp_path / "depth.db")
    with pytest.raises(ValueError, match="journal record"):
        journal.append(
            [
                ("spot", "BTCUSDT", "snapshot", snapshot(), NOW.timestamp()),
                ("spot", "BTCUSDT", "invalid", {}, NOW.timestamp()),
            ]
        )
    assert (
        journal.connection.execute("SELECT COUNT(*) FROM depth_events").fetchone()[0]
        == 0
    )
    journal.close()


@pytest.mark.parametrize("symbol_gap", [False, True])
def test_group_stream_bootstrap_records_diff_not_partial_depth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symbol_gap: bool,
) -> None:
    class Transport:
        def get_json(self, path: str, params: object = None) -> object:
            assert path == "/api/v3/depth"
            assert params in (
                {"symbol": "BTCUSDT", "limit": 5000},
                {"symbol": "ETHUSDT", "limit": 5000},
            )
            return snapshot()

    class ImmediatePool:
        def __init__(self, **kwargs: object) -> None:
            pass

        def submit(self, fn: object, *args: object) -> Future[object]:
            future: Future[object] = Future()
            future.set_result(fn(*args))  # type: ignore[operator]
            return future

        def shutdown(self, **kwargs: object) -> None:
            pass

    class Connection:
        calls = 0
        closed = False

        def __init__(self) -> None:
            self.subscribed: list[str] = []

        def send(self, raw: str) -> None:
            self.subscribed.extend(json.loads(raw)["params"])

        def recv(self, **kwargs: object) -> str | None:
            self.calls += 1
            script = (
                [
                    ("BTCUSDT", 100, 101),
                    ("BTCUSDT", 102, 103),
                    ("ETHUSDT", 100, 101),
                    ("BTCUSDT", 105, 106),
                    ("BTCUSDT", 100, 101),
                    ("ETHUSDT", 102, 103),
                    ("BTCUSDT", 102, 103),
                ]
                if symbol_gap
                else [("BTCUSDT", 100, 101), ("BTCUSDT", 102, 103)]
            )
            if self.calls > len(script):
                collector.stop_event.set()
                return None
            raw = event(*script[self.calls - 1])
            raw["E"] = int(time.time() * 1000)
            return json.dumps({"stream": "btcusdt@depth", "data": raw})

        def close(self) -> None:
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(
        "ai4binance.data.market_depth.ThreadPoolExecutor", ImmediatePool
    )
    collector = MarketDepthCollector(
        tmp_path,
        {"spot": Transport()},
        connection_factory=lambda *args, **kwargs: connection,
    )
    collector.groups["test"] = {}
    collector.journal = DepthJournal(tmp_path / "depth.sqlite3")
    names = ("BTCUSDT", "ETHUSDT") if symbol_gap else ("BTCUSDT",)
    collector._connection("spot", names, "test")
    assert connection.subscribed == (
        ["btcusdt@depth", "ethusdt@depth", "btcusdt@depth"]
        if symbol_gap
        else ["btcusdt@depth"]
    )
    assert connection.closed
    assert (
        read_local_depth(
            collector.journal.path, "spot", "BTCUSDT", now=datetime.now(UTC)
        )["lastUpdateId"]
        == 103
    )
    if symbol_gap:
        assert (
            read_local_depth(
                collector.journal.path, "spot", "ETHUSDT", now=datetime.now(UTC)
            )["lastUpdateId"]
            == 103
        )
        assert (
            collector.journal.connection.execute(
                "SELECT COUNT(*) FROM depth_events "
                "WHERE symbol='ETHUSDT' AND kind='gap'"
            ).fetchone()[0]
            == 0
        )
    collector.symbols = {"spot": names}
    collector.close()
    with pytest.raises(ValueError, match="unsynchronized"):
        read_local_depth(
            tmp_path / "depth.sqlite3", "spot", "BTCUSDT", now=datetime.now(UTC)
        )


def test_depth_levels_snapshot_and_old_delta_validation() -> None:
    from ai4binance.data import market_depth

    with pytest.raises(ValueError, match="invalid depth levels"):
        market_depth._levels("invalid")
    with pytest.raises(ValueError, match="invalid depth level shape"):
        market_depth._levels([["100"]])

    rejected = SimpleNamespace(
        symbol="BTCUSDT",
        apply_snapshot=lambda _snapshot: SimpleNamespace(accepted=False),
    )
    with pytest.raises(ValueError, match="snapshot failed validation"):
        apply_depth_snapshot(rejected, snapshot())  # type: ignore[arg-type]

    book = ReadOnlyOrderBook("BTCUSDT")
    apply_depth_snapshot(book, snapshot())
    assert apply_depth_event(book, event("BTCUSDT", 100, 101, 99), "spot")
    assert not apply_depth_event(book, event("BTCUSDT", 99, 100, 98), "spot")


def test_depth_journal_empty_append_and_local_query_validation(tmp_path: Path) -> None:
    journal = DepthJournal(tmp_path / "depth.db")
    journal.append([])
    with pytest.raises(ValueError, match="invalid local depth query"):
        read_local_depth(journal.path, "invalid", "BTCUSDT", now=NOW)
    with pytest.raises(ValueError, match="invalid local depth query"):
        read_local_depth(
            journal.path,
            "spot",
            "BTCUSDT",
            now=datetime(2026, 9, 11),
        )
    with pytest.raises(ValueError, match="invalid local depth query"):
        read_local_depth(
            journal.path,
            "spot",
            "BTCUSDT",
            now=NOW,
            maximum_age_seconds=61,
        )
    journal.close()


def test_local_depth_rejects_missing_checkpoint_and_gap_row(tmp_path: Path) -> None:
    journal = DepthJournal(tmp_path / "depth.db")
    journal.append(
        [
            ("spot", "BTCUSDT", "snapshot", snapshot(), NOW.timestamp()),
            ("spot", "BTCUSDT", "delta", event("BTCUSDT"), NOW.timestamp()),
        ]
    )
    journal.connection.execute("DELETE FROM depth_events WHERE kind='snapshot'")
    journal.connection.commit()
    with pytest.raises(ValueError, match="checkpoint unavailable"):
        read_local_depth(journal.path, "spot", "BTCUSDT", now=NOW)

    journal.connection.execute("DELETE FROM depth_events")
    journal.connection.execute("DELETE FROM depth_heads")
    journal.connection.commit()
    journal.append(
        [
            ("spot", "BTCUSDT", "snapshot", snapshot(), NOW.timestamp()),
            ("spot", "BTCUSDT", "gap", {"reason": "test"}, NOW.timestamp()),
        ]
    )
    journal.connection.execute(
        "UPDATE depth_heads SET status='LIVE', checkpoint_seq=latest_seq - 1"
    )
    journal.connection.commit()
    with pytest.raises(ValueError, match="contains a gap"):
        read_local_depth(journal.path, "spot", "BTCUSDT", now=NOW)
    journal.close()


def test_local_depth_rejects_truncated_compressed_record(tmp_path: Path) -> None:
    journal = DepthJournal(tmp_path / "depth.db")
    journal.append(
        [
            ("spot", "BTCUSDT", "snapshot", snapshot(), NOW.timestamp()),
            ("spot", "BTCUSDT", "delta", event("BTCUSDT"), NOW.timestamp()),
        ]
    )
    truncated = zlib.compress(json.dumps(event("BTCUSDT")).encode())[:-2]
    journal.connection.execute(
        "UPDATE depth_events SET payload=? WHERE kind='delta'", (truncated,)
    )
    journal.connection.commit()

    with pytest.raises(ValueError, match="too large or corrupt"):
        read_local_depth(journal.path, "spot", "BTCUSDT", now=NOW)
    journal.close()


def test_depth_collector_start_validates_groups_and_restarts_changed_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai4binance.data import market_depth

    with pytest.raises(ValueError, match="group bound"):
        MarketDepthCollector(
            tmp_path, {"spot": _json_transport()}, symbols_per_connection=0
        )

    class FakeThread:
        def __init__(self, **_kwargs: object) -> None:
            self.started = False

        def start(self) -> None:
            self.started = True

        def join(self, *, timeout: int) -> None:
            assert timeout == 3

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(market_depth, "Thread", FakeThread)
    collector = MarketDepthCollector(tmp_path / "valid", {"spot": _json_transport()})
    collector.start({"spot": ("BTCUSDT",)})
    first_thread = collector.threads[0]
    collector.start({"spot": ("BTCUSDT",)})
    assert collector.threads[0] is first_thread
    collector.start({"spot": ("ETHUSDT",)})
    assert collector.symbols == {"spot": ("ETHUSDT",)}
    collector.close()

    missing = MarketDepthCollector(tmp_path / "missing", {"spot": _json_transport()})
    with pytest.raises(ValueError, match="transport is missing"):
        missing.start({"usd_m_futures": ("BTCUSDT",)})
    assert missing.journal is not None
    missing.journal.close()

    bounded = MarketDepthCollector(
        tmp_path / "bounded", {"spot": _json_transport()}, symbols_per_connection=1
    )
    with pytest.raises(ValueError, match="bounded socket capacity"):
        bounded.start({"spot": tuple(f"S{index}USDT" for index in range(65))})
    assert bounded.journal is not None
    bounded.journal.close()


def test_depth_collector_status_write_and_shutdown_guards(
    tmp_path: Path,
) -> None:
    collector = MarketDepthCollector(tmp_path, {"spot": _json_transport()})
    collector.groups["spot-0"] = {"status": "STARTING"}
    collector._status("spot-0", status="COLLECTING")
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["groups"]["spot-0"]["status"] == "COLLECTING"
    with pytest.raises(ValueError, match="journal is not open"):
        collector._write([])

    class AliveThread:
        def join(self, *, timeout: int) -> None:
            assert timeout == 3

        def is_alive(self) -> bool:
            return True

    collector.threads = [AliveThread()]  # type: ignore[list-item]
    with pytest.raises(RuntimeError, match="shutdown incomplete"):
        collector.close()


def test_depth_collector_records_explicit_empty_target_state(tmp_path: Path) -> None:
    collector = MarketDepthCollector(tmp_path, {"spot": _json_transport()})

    collector.start({"spot": ()})

    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "NO_ELIGIBLE_DEPTH_TARGETS"
    assert status["blockers"] == ["NO_ELIGIBLE_DEPTH_TARGETS"]
    assert status["groups"] == {}
    collector.close()


@pytest.mark.parametrize("connection_fails", [False, True])
def test_depth_supervisor_records_disconnect_and_reconnect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    connection_fails: bool,
) -> None:
    collector = MarketDepthCollector(tmp_path, {"spot": _json_transport()})
    collector.groups["spot-0"] = {}
    writes: list[list[object]] = []
    statuses: list[dict[str, object]] = []

    def write(records: list[object]) -> None:
        writes.append(list(records))
        records.clear()

    monkeypatch.setattr(collector, "_write", write)
    monkeypatch.setattr(
        collector,
        "_status",
        lambda _group, **payload: statuses.append(payload),
    )
    if connection_fails:
        monkeypatch.setattr(
            collector,
            "_connection",
            lambda *_args: (_ for _ in ()).throw(ValueError("stream failed")),
        )
    else:
        monkeypatch.setattr(collector, "_connection", lambda *_args: None)
    monkeypatch.setattr(collector.stop_event, "wait", lambda _seconds: True)

    collector._supervise("spot", ("BTCUSDT",), "spot-0")

    assert len(writes) == 2
    assert statuses[-1]["status"] == (
        "RECONNECTING" if connection_fails else "DISCONNECTED"
    )


def test_depth_supervisor_blocks_when_gap_persistence_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = MarketDepthCollector(tmp_path, {"spot": _json_transport()})
    collector.groups["spot-0"] = {}
    writes = 0
    statuses: list[dict[str, object]] = []

    def write(_records: list[object]) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("disk unavailable")

    monkeypatch.setattr(collector, "_write", write)
    monkeypatch.setattr(
        collector,
        "_connection",
        lambda *_args: (_ for _ in ()).throw(ValueError("stream failed")),
    )
    monkeypatch.setattr(
        collector,
        "_status",
        lambda _group, **payload: statuses.append(payload),
    )

    collector._supervise("spot", ("BTCUSDT",), "spot-0")

    assert statuses[-1] == {
        "status": "BLOCKED",
        "reason": "DEPTH_STORAGE_UNAVAILABLE",
    }


@pytest.mark.parametrize(
    ("message", "error"),
    [
        (json.dumps([]), "invalid depth stream response"),
        (json.dumps({"code": 400}), "invalid depth stream response"),
        (json.dumps({"data": []}), "invalid depth stream envelope"),
        (
            json.dumps(
                {
                    "data": {
                        **event("BTCUSDT"),
                        "E": int((time.time() - 120) * 1000),
                    }
                }
            ),
            "stale or future depth event",
        ),
        (
            json.dumps({"data": {**event("ETHUSDT"), "E": int(time.time() * 1000)}}),
            "unsubscribed depth identity",
        ),
    ],
)
def test_depth_connection_rejects_invalid_stream_messages(
    tmp_path: Path,
    message: str,
    error: str,
) -> None:
    if error == "unsubscribed depth identity":
        envelope = json.loads(message)
        envelope["data"]["E"] = int(time.time() * 1000)
        message = json.dumps(envelope)

    class Connection:
        def send(self, _message: str) -> None:
            pass

        def recv(self, **_kwargs: object) -> str:
            return message

        def close(self) -> None:
            pass

    collector = MarketDepthCollector(
        tmp_path,
        {
            "spot": _json_transport(
                SimpleNamespace(get_json=lambda *_args, **_kwargs: snapshot())
            )
        },
        connection_factory=lambda *_args, **_kwargs: Connection(),
    )
    collector.journal = DepthJournal(tmp_path / "depth.db")
    collector.groups["spot-0"] = {}

    with pytest.raises(ValueError, match=error):
        collector._connection("spot", ("BTCUSDT",), "spot-0")
    collector.journal.close()


def test_depth_connection_honors_stop_during_connect_throttle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = MarketDepthCollector(
        tmp_path,
        {"spot": _json_transport()},
        connection_factory=lambda *_args, **_kwargs: pytest.fail("must not connect"),
    )
    monkeypatch.setattr(collector.stop_event, "wait", lambda _seconds: True)

    collector._connection("spot", ("BTCUSDT",), "spot-0")


def test_depth_connection_handles_timeout_and_pending_symbol_message(
    tmp_path: Path,
) -> None:
    class TimeoutConnection:
        def send(self, _message: str) -> None:
            pass

        def recv(self, **_kwargs: object) -> None:
            collector.stop_event.set()
            raise TimeoutError

        def close(self) -> None:
            pass

    collector = MarketDepthCollector(
        tmp_path / "timeout",
        {"spot": _json_transport()},
        connection_factory=lambda *_args, **_kwargs: TimeoutConnection(),
    )
    collector.journal = DepthJournal(tmp_path / "timeout.db")
    collector._connection("spot", ("BTCUSDT",), "spot-0")
    collector.journal.close()

    class PendingConnection:
        calls = 0

        def send(self, _message: str) -> None:
            pass

        def recv(self, **_kwargs: object) -> str | None:
            self.calls += 1
            if self.calls == 1:
                raw = event("ETHUSDT")
                raw["E"] = int(time.time() * 1000)
                return json.dumps({"data": raw})
            pending_collector.stop_event.set()
            return None

        def close(self) -> None:
            pass

    pending_collector = MarketDepthCollector(
        tmp_path / "pending",
        {"spot": _json_transport()},
        connection_factory=lambda *_args, **_kwargs: PendingConnection(),
    )
    pending_collector.journal = DepthJournal(tmp_path / "pending.db")
    pending_collector._connection("spot", ("BTCUSDT", "ETHUSDT"), "spot-0")
    pending_collector.journal.close()


def test_depth_connection_rejects_invalid_snapshot_and_low_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai4binance.data import market_depth

    class ImmediatePool:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def submit(self, function: object, *args: object) -> Future[object]:
            future: Future[object] = Future()
            future.set_result(function(*args))  # type: ignore[operator]
            return future

        def shutdown(self, **_kwargs: object) -> None:
            pass

    class Connection:
        calls = 0

        def send(self, _message: str) -> None:
            pass

        def recv(self, **_kwargs: object) -> str | None:
            self.calls += 1
            raw = event("BTCUSDT")
            raw["E"] = int(time.time() * 1000)
            return json.dumps({"data": raw})

        def close(self) -> None:
            pass

    monkeypatch.setattr(market_depth, "ThreadPoolExecutor", ImmediatePool)
    collector = MarketDepthCollector(
        tmp_path / "invalid-snapshot",
        {
            "spot": _json_transport(
                SimpleNamespace(get_json=lambda *_args, **_kwargs: [])
            )
        },
        connection_factory=lambda *_args, **_kwargs: Connection(),
    )
    collector.journal = DepthJournal(tmp_path / "invalid-snapshot.db")
    with pytest.raises(ValueError, match="invalid depth snapshot response"):
        collector._connection("spot", ("BTCUSDT",), "spot-0")
    collector.journal.close()

    monotonic_call = 0

    def monotonic() -> float:
        nonlocal monotonic_call
        monotonic_call += 1
        return float(monotonic_call)

    monkeypatch.setattr(time, "monotonic", monotonic)
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=0),
    )

    class QuietConnection(Connection):
        def recv(self, **_kwargs: object) -> None:
            return None

    low_disk = MarketDepthCollector(
        tmp_path / "low-disk",
        {"spot": _json_transport()},
        connection_factory=lambda *_args, **_kwargs: QuietConnection(),
    )
    low_disk.journal = DepthJournal(tmp_path / "low-disk.db")
    Connection.calls = 0
    with pytest.raises(OSError, match="free-space reserve"):
        low_disk._connection("spot", ("BTCUSDT",), "spot-0")
    low_disk.journal.close()
