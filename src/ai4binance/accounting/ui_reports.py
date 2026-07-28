"""Local, secret-safe HTML summaries for Binance accounting ledgers."""

# ruff: noqa: E501

from __future__ import annotations

import html
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ai4binance.reporting import to_primitive

_TRACKED_FILES = (
    "spot/orders.jsonl",
    "spot/order_events.jsonl",
    "spot/trades.jsonl",
    "spot/capital_flows.jsonl",
    "spot/account_snapshots.jsonl",
    "spot/balance_snapshots.jsonl",
    "futures_usdm/orders.jsonl",
    "futures_usdm/order_events.jsonl",
    "futures_usdm/trades.jsonl",
    "futures_usdm/positions_current.jsonl",
    "futures_usdm/position_events.jsonl",
    "futures_usdm/income_ledger.jsonl",
    "futures_usdm/configuration_snapshots.jsonl",
    "shared/raw_api_events.jsonl",
    "shared/reconciliation_results.jsonl",
    "shared/api_sync_runs.jsonl",
)
_FILE_LABELS = {
    "spot/orders.jsonl": ("Spot REST emir gecmisi", "REST tam snapshot"),
    "spot/order_events.jsonl": ("Spot User Data Stream emir olaylari", "WebSocket"),
    "spot/trades.jsonl": ("Spot REST trade/fill gecmisi", "REST tam snapshot"),
    "spot/capital_flows.jsonl": ("Spot sermaye hareketleri", "REST/WebSocket"),
    "spot/account_snapshots.jsonl": ("Spot hesap snapshot", "Runtime REST"),
    "spot/balance_snapshots.jsonl": ("Spot bakiye snapshot", "Runtime REST"),
    "futures_usdm/orders.jsonl": (
        "USD-M Futures REST emir gecmisi",
        "REST tam snapshot",
    ),
    "futures_usdm/order_events.jsonl": ("USD-M Futures emir olaylari", "WebSocket"),
    "futures_usdm/trades.jsonl": (
        "USD-M Futures trade/fill gecmisi",
        "REST tam snapshot",
    ),
    "futures_usdm/positions_current.jsonl": (
        "USD-M Futures acik pozisyon snapshot",
        "REST tam snapshot",
    ),
    "futures_usdm/position_events.jsonl": (
        "USD-M Futures pozisyon olaylari",
        "WebSocket",
    ),
    "futures_usdm/income_ledger.jsonl": (
        "USD-M Futures gelir/funding kayitlari",
        "REST tam snapshot",
    ),
    "futures_usdm/configuration_snapshots.jsonl": (
        "USD-M Futures konfigurasyon",
        "REST tam snapshot",
    ),
    "shared/raw_api_events.jsonl": ("Ham API olay kimlikleri", "REST/WebSocket ortak"),
    "shared/reconciliation_results.jsonl": (
        "REST/WebSocket mutabakat sonuclari",
        "Mutabakat",
    ),
    "shared/api_sync_runs.jsonl": ("Runtime sync kosulari", "Runtime REST"),
}
_PRODUCTS = ("SPOT", "FUTURES_USDM")
_SOURCES = ("REST", "WEBSOCKET")


@dataclass(frozen=True, slots=True)
class AccountingUiReportBuilder:
    """Build a local HTML dashboard from already-redacted JSONL records."""

    accounting_root: Path
    report_directory: Path
    freshness_seconds: int

    def build(self, observed_at: datetime) -> dict[str, object]:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("report timestamp must be timezone-aware")
        files = tuple(
            self._file_status(relative, observed_at) for relative in _TRACKED_FILES
        )
        reconciliation_events = _read_events(
            self.accounting_root / "shared" / "reconciliation_results.jsonl",
            limit=1_000,
        )
        raw_events = _read_events(
            self.accounting_root / "shared" / "raw_api_events.jsonl",
            limit=5_000,
        )
        reconciliation = _reconciliation_summary(reconciliation_events)
        source_counts = _source_counts(raw_events)
        channels = _channel_summary(
            raw_events,
            observed_at=observed_at,
            freshness_seconds=self.freshness_seconds,
        )
        recent_activity = tuple(_recent_activity(raw_events, reconciliation_events))
        blockers = tuple(
            dict.fromkeys(
                [
                    *(
                        f"ACCOUNTING_FILE_STALE:{item['relative_path']}"
                        for item in files
                        if item["required"] and item["exists"] and item["stale"]
                    ),
                    *(
                        f"ACCOUNTING_FILE_MISSING:{item['relative_path']}"
                        for item in files
                        if item["required"] and not item["exists"]
                    ),
                    *cast(tuple[str, ...], reconciliation["blockers"]),
                ]
            )
        )
        return {
            "title": "AI4BINANCE Accounting UI Report",
            "observed_at": observed_at,
            "accounting_directory": str(self.accounting_root),
            "report_directory": str(self.report_directory),
            "status": "CLEAN" if not blockers else "DEGRADED",
            "files": files,
            "channels": channels,
            "source_counts": source_counts,
            "reconciliation": reconciliation,
            "recent_activity": recent_activity,
            "blockers": blockers,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    def write(self, observed_at: datetime | None = None) -> dict[str, object]:
        report = self.build(observed_at or datetime.now(UTC))
        self.report_directory.mkdir(parents=True, exist_ok=True)
        json_path = self.report_directory / "accounting_report.json"
        html_path = self.report_directory / "index.html"
        json_path.write_text(
            json.dumps(
                to_primitive(
                    {
                        **report,
                        "html_path": str(html_path),
                        "json_path": str(json_path),
                    }
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        html_path.write_text(_render_html(report, json_path), encoding="utf-8")
        return {**report, "html_path": str(html_path), "json_path": str(json_path)}

    def _file_status(self, relative: str, observed_at: datetime) -> dict[str, object]:
        path = self.accounting_root / relative
        exists = path.is_file()
        age_seconds: float | None = None
        line_count = 0
        stale = False
        if exists:
            age_seconds = max(0.0, observed_at.timestamp() - path.stat().st_mtime)
            stale = age_seconds > self.freshness_seconds
            line_count = sum(
                1
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        label, category = _FILE_LABELS[relative]
        return {
            "relative_path": relative,
            "label": label,
            "category": category,
            "path": str(path),
            "exists": exists,
            "required": relative
            in {
                "shared/raw_api_events.jsonl",
                "shared/reconciliation_results.jsonl",
            },
            "line_count": line_count,
            "age_seconds": age_seconds,
            "stale": stale,
        }


def _read_events(path: Path, *, limit: int) -> tuple[dict[str, object], ...]:
    if not path.is_file():
        return ()
    rows: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            rows.append(cast(dict[str, object], event))
    return tuple(rows)


def _payload(event: dict[str, object]) -> dict[str, object]:
    payload = event.get("payload")
    return cast(dict[str, object], payload) if isinstance(payload, dict) else {}


def _reconciliation_summary(events: Iterable[dict[str, object]]) -> dict[str, object]:
    history_counts: dict[str, int] = {}
    latest_by_entity: dict[tuple[str, str, str], dict[str, object]] = {}
    for event in events:
        payload = _payload(event)
        severity = str(payload.get("severity", "")).strip() or "UNKNOWN"
        history_counts[severity] = history_counts.get(severity, 0) + 1
        key = (
            str(payload.get("product_type", "")),
            str(payload.get("entity_type", "")),
            str(payload.get("entity_id", "")),
        )
        if all(key):
            latest_by_entity[key] = payload
    latest_items = tuple(latest_by_entity.values())
    severity_counts: dict[str, int] = {}
    blockers: list[str] = []
    latest: dict[str, object] | None = None
    for payload in latest_items:
        severity = str(payload.get("severity", "")).strip() or "UNKNOWN"
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        latest = payload
        if severity not in {"OK"}:
            entity = str(payload.get("entity_id", "unknown"))
            blockers.append(f"RECONCILIATION_NOT_CLEAN:{severity}:{entity}")
    return {
        "status": "CLEAN" if not blockers else "DEGRADED",
        "latest": latest,
        "severity_counts": severity_counts,
        "history_severity_counts": history_counts,
        "latest_entity_count": len(latest_items),
        "blockers": tuple(dict.fromkeys(blockers)),
    }


def _source_counts(events: Iterable[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        payload = _payload(event)
        envelope = payload.get("envelope")
        source = "UNKNOWN"
        if isinstance(envelope, dict):
            source = str(envelope.get("source_type", "UNKNOWN"))
        counts[source] = counts.get(source, 0) + 1
    return counts


def _channel_summary(
    events: Iterable[dict[str, object]],
    *,
    observed_at: datetime,
    freshness_seconds: int,
) -> tuple[dict[str, object], ...]:
    grouped: dict[tuple[str, str], dict[str, object]] = {
        (product, source): {
            "product_type": product,
            "source_type": source,
            "title": _channel_title(product, source),
            "event_count": 0,
            "latest_received_at": None,
            "age_seconds": None,
            "status": "WAITING",
            "endpoints": {},
            "payload_storage": "HASH_ONLY",
        }
        for product in _PRODUCTS
        for source in _SOURCES
    }
    for event in events:
        payload = _payload(event)
        envelope = payload.get("envelope")
        if not isinstance(envelope, dict):
            continue
        product = str(envelope.get("product_type", ""))
        source = str(envelope.get("source_type", ""))
        key = (product, source)
        if key not in grouped:
            continue
        item = grouped[key]
        event_count = item["event_count"]
        item["event_count"] = (event_count if isinstance(event_count, int) else 0) + 1
        endpoints = cast(dict[str, int], item["endpoints"])
        endpoint = str(envelope.get("endpoint") or payload.get("stream_name") or "")
        if endpoint:
            endpoints[endpoint] = endpoints.get(endpoint, 0) + 1
        received_at = _parse_time(payload.get("received_at") or event.get("timestamp"))
        current_latest = _parse_time(item["latest_received_at"])
        if received_at is not None and (
            current_latest is None or received_at > current_latest
        ):
            item["latest_received_at"] = received_at.isoformat()
    for item in grouped.values():
        latest = _parse_time(item["latest_received_at"])
        if latest is None:
            continue
        age = max(0.0, (observed_at - latest).total_seconds())
        item["age_seconds"] = age
        item["status"] = "ACTIVE" if age <= freshness_seconds else "STALE"
        item["endpoints"] = tuple(
            {"endpoint": endpoint, "count": count}
            for endpoint, count in sorted(
                cast(dict[str, int], item["endpoints"]).items()
            )
        )
    for item in grouped.values():
        if isinstance(item["endpoints"], dict):
            item["endpoints"] = ()
    return tuple(
        grouped[(product, source)] for product in _PRODUCTS for source in _SOURCES
    )


def _channel_title(product: str, source: str) -> str:
    product_label = "Spot" if product == "SPOT" else "USD-M Futures"
    source_label = "REST tam snapshot" if source == "REST" else "User Data Stream"
    return f"{product_label} {source_label}"


def _recent_activity(
    raw_events: Iterable[dict[str, object]],
    reconciliation_events: Iterable[dict[str, object]],
) -> Iterable[dict[str, object]]:
    combined = [*raw_events, *reconciliation_events]
    for event in combined[-20:]:
        payload = _payload(event)
        envelope = payload.get("envelope")
        source_type = (
            envelope.get("source_type") if isinstance(envelope, dict) else None
        )
        yield {
            "timestamp": event.get("timestamp"),
            "event_type": event.get("event_type"),
            "product_type": payload.get("product_type"),
            "source_type": source_type,
            "summary": payload.get("event_type")
            or payload.get("entity_type")
            or payload.get("processing_status"),
            "severity": payload.get("severity"),
        }


def _render_html(report: dict[str, object], json_path: Path) -> str:
    status = str(report["status"])
    status_class = "clean" if status == "CLEAN" else "degraded"
    files = cast(tuple[dict[str, object], ...], report["files"])
    channels = cast(tuple[dict[str, object], ...], report["channels"])
    activities = cast(tuple[dict[str, object], ...], report["recent_activity"])
    blockers = cast(tuple[str, ...], report["blockers"])
    source_counts = cast(dict[str, int], report["source_counts"])
    reconciliation = cast(dict[str, object], report["reconciliation"])
    return f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(str(report["title"]))}</title>
  <style>
    :root {{ color-scheme: light; --ink:#17212b; --muted:#657385; --line:#d8dee8; --ok:#16794c; --bad:#b42318; --panel:#ffffff; --bg:#f4f7fb; --accent:#1f6feb; }}
    body {{ margin:0; font-family: Segoe UI, Arial, sans-serif; background:var(--bg); color:var(--ink); }}
    header {{ padding:24px 32px; background:#0f2437; color:white; }}
    main {{ max-width:1180px; margin:0 auto; padding:24px; }}
    h1 {{ margin:0 0 8px; font-size:26px; letter-spacing:0; }}
    h2 {{ margin:0 0 12px; font-size:18px; letter-spacing:0; }}
    .muted {{ color:var(--muted); }}
    header .muted {{ color:#c8d2df; }}
    .grid {{ display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:12px; margin-bottom:18px; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .metric {{ font-size:28px; font-weight:700; }}
    .badge {{ display:inline-block; padding:4px 10px; border-radius:999px; font-weight:700; }}
    .clean {{ background:#e8f6ef; color:var(--ok); }}
    .degraded {{ background:#fff0ed; color:var(--bad); }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th, td {{ text-align:left; padding:10px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
    th {{ color:#405166; font-weight:700; }}
    code {{ background:#edf2f7; padding:2px 5px; border-radius:4px; }}
    .two {{ display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-bottom:18px; }}
    .blockers {{ margin:0; padding-left:18px; }}
    @media (max-width: 840px) {{ .grid, .two {{ grid-template-columns:1fr; }} main {{ padding:16px; }} header {{ padding:20px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>AI4BINANCE Muhasebe Raporu</h1>
    <div class="muted">Uretim emri yetkisi yok: LIVE_ORDER_BLOCKED. Kaynak JSON: {html.escape(str(json_path))}</div>
  </header>
  <main>
    <section class="grid">
      <div class="panel"><div class="muted">Durum</div><div><span class="badge {status_class}">{html.escape(status)}</span></div></div>
      <div class="panel"><div class="muted">REST kayitlari</div><div class="metric">{source_counts.get("REST", 0)}</div></div>
      <div class="panel"><div class="muted">WebSocket kayitlari</div><div class="metric">{source_counts.get("WEBSOCKET", 0)}</div></div>
      <div class="panel"><div class="muted">Mutabakat</div><div class="metric">{html.escape(str(reconciliation["status"]))}</div></div>
    </section>
    <section class="panel">
      <h2>REST Snapshot ve User Data Stream</h2>
      {_render_channels(channels)}
    </section>
    <section class="two">
      <div class="panel">
        <h2>Blocker Listesi</h2>
        {_render_blockers(blockers)}
      </div>
      <div class="panel">
        <h2>Son Aktiviteler</h2>
        {_render_activity(activities)}
      </div>
    </section>
    <section class="panel">
      <h2>Kayit Dosyalari</h2>
      {_render_files(files)}
    </section>
  </main>
</body>
</html>
"""


def _render_blockers(blockers: tuple[str, ...]) -> str:
    if not blockers:
        return '<p class="muted">Aktif blocker yok.</p>'
    return (
        '<ul class="blockers">'
        + "".join(f"<li><code>{html.escape(item)}</code></li>" for item in blockers)
        + "</ul>"
    )


def _render_activity(items: tuple[dict[str, object], ...]) -> str:
    if not items:
        return '<p class="muted">Henuz aktivite yok.</p>'
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('timestamp') or ''))}</td>"
        f"<td>{html.escape(str(item.get('product_type') or ''))}</td>"
        f"<td>{html.escape(str(item.get('source_type') or ''))}</td>"
        f"<td>{html.escape(str(item.get('summary') or item.get('event_type') or ''))}</td>"
        f"<td>{html.escape(str(item.get('severity') or ''))}</td>"
        "</tr>"
        for item in items
    )
    return f"<table><thead><tr><th>Zaman</th><th>Urun</th><th>Kaynak</th><th>Olay</th><th>Seviye</th></tr></thead><tbody>{rows}</tbody></table>"


def _render_channels(channels: tuple[dict[str, object], ...]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['title']))}</td>"
        f'<td><span class="badge {"clean" if item["status"] == "ACTIVE" else "degraded"}">{html.escape(str(item["status"]))}</span></td>'
        f"<td>{html.escape(str(item['event_count']))}</td>"
        f"<td>{html.escape(str(item.get('latest_received_at') or ''))}</td>"
        f"<td>{html.escape(_age(item.get('age_seconds')))}</td>"
        f"<td>{_render_endpoint_list(cast(tuple[dict[str, object], ...], item['endpoints']))}</td>"
        "</tr>"
        for item in channels
    )
    return f"<table><thead><tr><th>Kanal</th><th>Durum</th><th>Olay</th><th>Son Kayit</th><th>Yas</th><th>Endpointler</th></tr></thead><tbody>{rows}</tbody></table>"


def _render_endpoint_list(items: tuple[dict[str, object], ...]) -> str:
    if not items:
        return '<span class="muted">kayit yok</span>'
    return "<br>".join(
        f"<code>{html.escape(str(item['endpoint']))}</code> {html.escape(str(item['count']))}"
        for item in items[:6]
    )


def _render_files(files: tuple[dict[str, object], ...]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['label']))}</td>"
        f"<td>{html.escape(str(item['category']))}</td>"
        f"<td><code>{html.escape(str(item['relative_path']))}</code></td>"
        f"<td>{'var' if item['exists'] else 'yok'}</td>"
        f"<td>{html.escape(str(item['line_count']))}</td>"
        f"<td>{html.escape(_age(item['age_seconds']))}</td>"
        f"<td>{'evet' if item['stale'] else 'hayir'}</td>"
        "</tr>"
        for item in files
    )
    return f"<table><thead><tr><th>Kayit</th><th>Tip</th><th>Dosya</th><th>Durum</th><th>Satir</th><th>Yas</th><th>Bayat</th></tr></thead><tbody>{rows}</tbody></table>"


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _age(value: object) -> str:
    if not isinstance(value, (float, int)):
        return ""
    if value < 60:
        return f"{value:.0f}s"
    return f"{value / 60:.1f}dk"
