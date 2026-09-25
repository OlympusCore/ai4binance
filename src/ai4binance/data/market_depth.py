"""Shared public L2 diff-depth recording, recovery, and local-only replay.

This reuses the canonical sequence-aware book. REST snapshots bound initial
coverage; neither missing offline events nor unseen outer levels are invented.
"""

from __future__ import annotations

import importlib
import json
import shutil
import sqlite3
import time
import zlib
from collections import deque
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

from ai4binance.data.market_history_continuous import _SAFE_STATE, _prefix, _save
from ai4binance.exchange.client import JsonTransport
from ai4binance.exchange.order_book import (
    BookLevel,
    OrderBookDelta,
    OrderBookSnapshot,
    ReadOnlyOrderBook,
)

_URLS = {
    "spot": "wss://stream.binance.com:9443/stream",
    "usd_m_futures": "wss://fstream.binance.com/public/stream",
    "coin_m_futures": "wss://dstream.binance.com/stream",
}
_DEPTH_COMPACTION_BATCH_SIZE = 50_000
DepthRecord = tuple[str, str, str, dict[str, object], float]


def _levels(raw: object) -> tuple[BookLevel, ...]:
    from decimal import Decimal

    if not isinstance(raw, list) or len(raw) > 100_000:
        raise ValueError("invalid depth levels")
    result = []
    for item in raw:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("invalid depth level shape")
        result.append(BookLevel(Decimal(str(item[0])), Decimal(str(item[1]))))
    return tuple(result)


def apply_depth_snapshot(book: ReadOnlyOrderBook, raw: Mapping[str, object]) -> None:
    observed = datetime.fromtimestamp(float(str(raw.get("event_at", 0))), UTC)
    result = book.apply_snapshot(
        OrderBookSnapshot(
            book.symbol,
            int(str(raw["lastUpdateId"])),
            observed,
            _levels(raw["bids"]),
            _levels(raw["asks"]),
            bool(raw.get("bridged", False)),
        )
    )
    if not result.accepted:
        raise ValueError("depth snapshot failed validation")


def apply_depth_event(
    book: ReadOnlyOrderBook, raw: Mapping[str, object], market: str
) -> bool:
    if raw.get("e") != "depthUpdate" or raw.get("s") != book.symbol:
        raise ValueError("depth event identity mismatch")
    expected_type = 2 if market == "coin_m_futures" else 1
    if market != "spot" and "st" in raw and raw["st"] != expected_type:
        raise ValueError("depth market type mismatch")
    result = book.apply_delta(
        OrderBookDelta(
            int(str(raw["U"])),
            int(str(raw["u"])),
            datetime.fromtimestamp(int(str(raw["E"])) / 1000, UTC),
            _levels(raw["b"]),
            _levels(raw["a"]),
            int(str(raw["pu"])) if "pu" in raw else None,
        )
    )
    if result.blockers == ("ORDER_BOOK_OLD_DELTA",):
        return False
    if not result.accepted:
        raise ValueError("depth sequence or integrity gap")
    return True


def _checkpoint(book: ReadOnlyOrderBook) -> dict[str, object]:
    bids, asks = book.levels()
    return {
        "lastUpdateId": book.last_update_id,
        "event_at": book.last_event_at.timestamp() if book.last_event_at else 0,
        "bids": [[str(row.price), str(row.quantity)] for row in bids],
        "asks": [[str(row.price), str(row.quantity)] for row in asks],
        "bridged": True,
        "coverage": "SNAPSHOT_LIMITED_PLUS_OBSERVED_UPDATES",
        **_SAFE_STATE,
    }


class DepthJournal:
    """Single WAL journal; atomic batches and read-only deterministic consumers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        self.connection = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS depth_events (
                seq INTEGER PRIMARY KEY, market TEXT NOT NULL, symbol TEXT NOT NULL,
                kind TEXT NOT NULL, payload BLOB NOT NULL, received_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS depth_stream ON depth_events(market,symbol,seq);
            CREATE TABLE IF NOT EXISTS depth_heads (
                market TEXT, symbol TEXT, checkpoint_seq INTEGER, latest_seq INTEGER,
                status TEXT, received_at REAL, PRIMARY KEY(market,symbol));
        """)

    def append(self, records: list[DepthRecord]) -> None:
        if not records:
            return
        with self.lock, self.connection:
            for market, symbol, kind, payload, received in records:
                if market not in _URLS or kind not in {
                    "snapshot",
                    "checkpoint",
                    "delta",
                    "gap",
                }:
                    raise ValueError("invalid depth journal record")
                data = zlib.compress(
                    json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
                )
                seq = self.connection.execute(
                    "INSERT INTO depth_events(market,symbol,kind,payload,received_at) "
                    "VALUES(?,?,?,?,?)",
                    (market, symbol, kind, data, received),
                ).lastrowid
                checkpoint = seq if kind in {"snapshot", "checkpoint"} else None
                status = (
                    "LIVE"
                    if kind in {"delta", "checkpoint"}
                    else "SYNCING"
                    if kind == "snapshot"
                    else "GAP"
                )
                self.connection.execute(
                    """
                    INSERT INTO depth_heads VALUES(?,?,?,?,?,?)
                    ON CONFLICT(market,symbol) DO UPDATE SET
                    checkpoint_seq=COALESCE(excluded.checkpoint_seq,depth_heads.checkpoint_seq),
                    latest_seq=excluded.latest_seq,status=excluded.status,received_at=excluded.received_at
                """,
                    (market, symbol, checkpoint, seq, status, received),
                )
                if checkpoint is not None:
                    self.connection.execute(
                        "DELETE FROM depth_events WHERE seq IN ("
                        "SELECT seq FROM depth_events WHERE market=? AND symbol=? "
                        "AND seq<? ORDER BY seq LIMIT ?)",
                        (
                            market,
                            symbol,
                            checkpoint,
                            _DEPTH_COMPACTION_BATCH_SIZE,
                        ),
                    )

    def close(self) -> None:
        with self.lock:
            self.connection.close()


def read_local_depth(
    path: Path,
    market: str,
    symbol: str,
    *,
    now: datetime,
    maximum_age_seconds: float = 30,
) -> dict[str, object]:
    """Never fetch from Binance or return a stale, unbridged, or gapped book."""
    if (
        market not in _URLS
        or now.utcoffset() is None
        or not 0 < maximum_age_seconds <= 60
    ):
        raise ValueError("invalid local depth query")
    book = ReadOnlyOrderBook(
        symbol, maximum_levels=100_000, futures_sequence=market != "spot"
    )
    with closing(
        sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    ) as connection:
        connection.execute("BEGIN")
        head = connection.execute(
            "SELECT checkpoint_seq,latest_seq,status,received_at FROM depth_heads "
            "WHERE market=? AND symbol=?",
            (market, book.symbol),
        ).fetchone()
        if (
            head is None
            or head[2] != "LIVE"
            or not 0 <= now.timestamp() - head[3] <= maximum_age_seconds
        ):
            raise ValueError("local depth unavailable, stale, or unsynchronized")
        rows = connection.execute(
            "SELECT kind,payload FROM depth_events WHERE market=? AND symbol=? "
            "AND seq>=? AND seq<=? ORDER BY seq LIMIT 100001",
            (market, book.symbol, head[0], head[1]),
        ).fetchall()
        if (
            not rows
            or len(rows) > 100000
            or rows[0][0] not in {"snapshot", "checkpoint"}
        ):
            raise ValueError("local depth checkpoint unavailable")
        for kind, blob in rows:
            inflater = zlib.decompressobj()
            data = inflater.decompress(blob, 16_000_001)
            if len(data) > 16_000_000 or not inflater.eof:
                raise ValueError("local depth record too large or corrupt")
            payload = json.loads(data)
            if kind in {"snapshot", "checkpoint"}:
                apply_depth_snapshot(book, payload)
            elif kind == "delta":
                apply_depth_event(book, payload, market)
            else:
                raise ValueError("local depth contains a gap")
    return {
        "market": market,
        "symbol": book.symbol,
        "received_at": head[3],
        **_checkpoint(book),
    }


class MarketDepthCollector:
    """Bounded grouped sockets; one owner integrated with the history lease.

    Symbols join gradually as their REST snapshots become available. Existing
    subscriptions continue while the next symbol bootstraps. No partial-depth
    stream, private endpoint, or API credential is used.
    """

    def __init__(
        self,
        root: Path,
        transports: Mapping[str, JsonTransport],
        *,
        connection_factory: Callable[..., Any] | None = None,
        symbols_per_connection: int = 64,
    ) -> None:
        if not 1 <= symbols_per_connection <= 128:
            raise ValueError("depth socket group bound is invalid")
        self.root, self.transports = root, transports
        self.factory = connection_factory
        self.group_size = symbols_per_connection
        self.stop_event = Event()
        self.threads: list[Thread] = []
        self.symbols: dict[str, tuple[str, ...]] = {}
        self.journal: DepthJournal | None = None
        self.groups: dict[str, dict[str, object]] = {}
        self.guard = Lock()
        self.connect_guard = Lock()
        self.last_connect = 0.0

    def start(self, symbols: Mapping[str, tuple[str, ...]]) -> None:
        if self.threads:
            if self.symbols == dict(symbols):
                return
            self.close()
            self.threads, self.groups = [], {}
            self.stop_event = Event()
        self.symbols = dict(symbols)
        self.journal = DepthJournal(self.root / "depth.sqlite3")
        for market, names in self.symbols.items():
            if market not in self.transports:
                raise ValueError("depth market transport is missing")
            for index in range(0, len(names), self.group_size):
                group = f"{market}-{index // self.group_size}"
                self.groups[group] = {
                    "status": "STARTING",
                    "symbol_count": len(names[index : index + self.group_size]),
                    "live_symbols": 0,
                }
                thread = Thread(
                    target=self._supervise,
                    args=(market, names[index : index + self.group_size], group),
                    daemon=True,
                )
                self.threads.append(thread)
        if len(self.threads) > 64:
            raise ValueError("depth universe exceeds bounded socket capacity")
        now = datetime.now(UTC).isoformat()
        _save(
            self.root / "status.json",
            {
                "status": ("STARTING" if self.threads else "NO_ELIGIBLE_DEPTH_TARGETS"),
                "observed_at": now,
                "groups": self.groups,
                "coverage": "PUBLIC_L2_SNAPSHOT_LIMITED_PLUS_DIFFS",
                "offline_depth_backfill": "UNAVAILABLE",
                "blockers": ([] if self.threads else ["NO_ELIGIBLE_DEPTH_TARGETS"]),
                **_SAFE_STATE,
            },
        )
        for thread in self.threads:
            thread.start()

    def _status(self, group: str, **payload: object) -> None:
        with self.guard:
            self.groups[group].update(payload)
            self.groups[group]["observed_at"] = datetime.now(UTC).isoformat()
            _save(
                self.root / "status.json",
                {
                    "status": "COLLECTING",
                    "observed_at": datetime.now(UTC).isoformat(),
                    "groups": self.groups,
                    "coverage": "PUBLIC_L2_SNAPSHOT_LIMITED_PLUS_DIFFS",
                    "offline_depth_backfill": "UNAVAILABLE",
                    **_SAFE_STATE,
                },
            )

    def _write(self, records: list[DepthRecord]) -> None:
        if self.journal is None:
            raise ValueError("depth journal is not open")
        self.journal.append(records)
        records.clear()

    def _supervise(self, market: str, symbols: tuple[str, ...], group: str) -> None:
        attempt = 0
        while not self.stop_event.is_set():
            try:
                self._write(
                    [
                        (
                            market,
                            symbol,
                            "gap",
                            {"reason": "START_OR_RECONNECT", **_SAFE_STATE},
                            time.time(),
                        )
                        for symbol in symbols
                    ]
                )
                self._connection(market, symbols, group)
            except (
                Exception
            ) as error:  # A failed public shard never retains LIVE authority.
                self._status(group, status="RECONNECTING", reason=type(error).__name__)
                try:
                    self._write(
                        [
                            (
                                market,
                                symbol,
                                "gap",
                                {"reason": type(error).__name__, **_SAFE_STATE},
                                time.time(),
                            )
                            for symbol in symbols
                        ]
                    )
                except (OSError, sqlite3.Error):
                    self._status(
                        group, status="BLOCKED", reason="DEPTH_STORAGE_UNAVAILABLE"
                    )
                    return
            else:
                self._write(
                    [
                        (
                            market,
                            symbol,
                            "gap",
                            {"reason": "CONNECTION_CLOSED", **_SAFE_STATE},
                            time.time(),
                        )
                        for symbol in symbols
                    ]
                )
                self._status(group, status="DISCONNECTED")
            attempt = min(attempt + 1, 6)
            if self.stop_event.wait(min(60, 2**attempt)):
                return

    def _connection(self, market: str, symbols: tuple[str, ...], group: str) -> None:
        factory = (
            self.factory or importlib.import_module("websockets.sync.client").connect
        )
        with self.connect_guard:
            if self.stop_event.wait(
                max(0, self.last_connect + 0.25 - time.monotonic())
            ):
                return
            self.last_connect = time.monotonic()
        connection = factory(
            _URLS[market],
            open_timeout=10,
            close_timeout=2,
            ping_interval=20,
            ping_timeout=20,
            max_size=2_000_000,
            max_queue=64,
        )
        books: dict[str, ReadOnlyOrderBook] = {}
        records: list[DepthRecord] = []
        buffers: deque[dict[str, object]] = deque()
        future: Future[object] | None = None
        pending: str | None = None
        remaining = deque(symbols)
        live: set[str] = set()
        last_checkpoint: dict[str, float] = {}
        last_flush, started = time.monotonic(), time.monotonic()
        executor = ThreadPoolExecutor(max_workers=1)
        received_bytes = 0

        def resync(symbol: str) -> None:
            """Invalidate only the broken book and queue its bounded resnapshot."""
            live.discard(symbol)
            books.pop(symbol, None)
            remaining.append(symbol)
            records.append(
                (
                    market,
                    symbol,
                    "gap",
                    {"reason": "SYMBOL_SEQUENCE_GAP", **_SAFE_STATE},
                    time.time(),
                )
            )
            self._write(records)

        try:
            while (
                not self.stop_event.is_set() and time.monotonic() - started < 23 * 3600
            ):
                if pending is None:
                    pending = remaining.popleft() if remaining else None
                    if pending:
                        suffix = "@depth" if market == "spot" else "@depth@500ms"
                        connection.send(
                            json.dumps(
                                {
                                    "method": "SUBSCRIBE",
                                    "params": [pending.lower() + suffix],
                                    "id": len(books) + 1,
                                }
                            )
                        )
                        books[pending] = ReadOnlyOrderBook(
                            pending,
                            maximum_levels=100_000,
                            futures_sequence=market != "spot",
                        )
                        future = executor.submit(
                            self.transports[market].get_json,
                            _prefix(market) + "depth",
                            {
                                "symbol": pending,
                                "limit": 5000 if market == "spot" else 1000,
                            },
                        )
                if future is not None and future.done():
                    raw = future.result()
                    if pending is None or not isinstance(raw, dict):
                        raise ValueError("invalid depth snapshot response")
                    book = books[pending]
                    try:
                        apply_depth_snapshot(book, raw)
                        records.append((market, pending, "snapshot", raw, time.time()))
                        for event in buffers:
                            if apply_depth_event(book, event, market):
                                records.append(
                                    (market, pending, "delta", event, time.time())
                                )
                                live.add(pending)
                    except ValueError:
                        resync(pending)
                    buffers.clear()
                    pending, future = None, None
                try:
                    message = connection.recv(timeout=0.5)
                except TimeoutError:
                    message = None
                if message is not None:
                    received_bytes += len(
                        message.encode() if isinstance(message, str) else message
                    )
                    raw = json.loads(message)
                    if not isinstance(raw, dict) or "code" in raw:
                        raise ValueError("invalid depth stream response")
                    event = raw.get("data", raw)
                    if not isinstance(event, dict):
                        raise ValueError("invalid depth stream envelope")
                    if event.get("e") == "depthUpdate":
                        event_age = time.time() - int(str(event.get("E"))) / 1000
                        if not -5 <= event_age <= 60:
                            raise ValueError("stale or future depth event")
                        symbol = str(event.get("s"))
                        if symbol not in books:
                            if symbol in remaining:
                                continue
                            raise ValueError("unsubscribed depth identity")
                        if symbol == pending:
                            if len(buffers) >= 4096:
                                raise ValueError("depth bootstrap buffer overflow")
                            buffers.append(event)
                            if future is None:
                                future = executor.submit(
                                    self.transports[market].get_json,
                                    _prefix(market) + "depth",
                                    {
                                        "symbol": symbol,
                                        "limit": 5000 if market == "spot" else 1000,
                                    },
                                )
                        else:
                            try:
                                applied = apply_depth_event(
                                    books[symbol], event, market
                                )
                            except ValueError:
                                resync(symbol)
                                continue
                            if not applied:
                                continue
                            records.append(
                                (market, symbol, "delta", event, time.time())
                            )
                            live.add(symbol)
                            if time.monotonic() - last_checkpoint.get(symbol, 0) >= 60:
                                records.append(
                                    (
                                        market,
                                        symbol,
                                        "checkpoint",
                                        _checkpoint(books[symbol]),
                                        time.time(),
                                    )
                                )
                                last_checkpoint[symbol] = time.monotonic()
                if len(records) >= 500 or time.monotonic() - last_flush >= 1:
                    if shutil.disk_usage(self.root).free < 1_000_000_000:
                        raise OSError("depth recording free-space reserve reached")
                    self._write(records)
                    self._status(
                        group,
                        status="COLLECTING",
                        live_symbols=len(live),
                        decoded_message_bytes=received_bytes,
                    )
                    last_flush = time.monotonic()
        finally:
            connection.close()
            executor.shutdown(wait=False, cancel_futures=True)
            self._write(records)

    def close(self) -> None:
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=3)
        if any(thread.is_alive() for thread in self.threads):
            raise RuntimeError("depth collector shutdown incomplete")
        if self.journal is not None:
            self._write(
                [
                    (
                        market,
                        symbol,
                        "gap",
                        {"reason": "COLLECTOR_STOPPED", **_SAFE_STATE},
                        time.time(),
                    )
                    for market, symbols in self.symbols.items()
                    for symbol in symbols
                ]
            )
            self.journal.close()
