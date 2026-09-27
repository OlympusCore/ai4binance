"""Loopback-only, test-only dashboard acceptance host; never reads live data."""

from __future__ import annotations

import http.client
import json
import runpy
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "runtime/tmp/process/dashboard-acceptance"


def prepare() -> None:
    STAGE.mkdir(parents=True, exist_ok=True)
    (STAGE / "disconnected").write_text("false", encoding="utf-8")
    source = ROOT / "src/ai4binance/local_dashboard"
    for name in ("build.py.in", "design_source.html", "local_views.js"):
        shutil.copyfile(source / name, STAGE / name)
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-B",
            str(STAGE / "build.py.in"),
            str(STAGE / "design_source.html"),
            str(ROOT / "frontend/src"),
        ],
        check=True,
        timeout=30,
    )
    fixture = runpy.run_path(str(ROOT / "tests/test_dashboard_decisions.py"))
    record = fixture["SERVER"]["decision_record"](
        fixture["receipt"](),
        "TEST_ONLY.jsonl",
        fixture["NOW"],
    )
    record["status"] = "STALE"
    payload = {
        "schema_version": "DashboardSnapshot/v1",
        "generated_at": fixture["NOW"].isoformat(),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "sources": {
            "virtual": {"status": "STALE"},
            "market_history": {"status": "CURRENT"},
            "learning": {"status": "CURRENT"},
        },
        "virtual": {},
        "services": [],
        "health_findings": [
            {
                "finding_id": "TEST_ONLY_RISK_VETO",
                "severity": "P0",
                "status": "BLOCKED",
                "evidence": "TEST_ONLY.jsonl",
            }
        ],
        "operational_readiness": {
            "status": "DEGRADED",
            "high_priority_finding_count": 1,
        },
        "decision_history": {
            "status": "PARTIALLY_VERIFIED",
            "records": [record],
            "findings": [],
        },
    }
    for index in range(60):
        payload["sources"][f"TEST_ONLY_SOURCE_{index:02}"] = {"status": "CURRENT"}
    (STAGE / "fixture.json").write_text(json.dumps(payload), encoding="utf-8")
    # Instrument only this disposable test build, never the shipped interface.
    script_path = STAGE / "app.js"
    script = script_path.read_text(encoding="utf-8")
    script = script.replace(
        "function render(){", "function render(){const testStart=performance.now();"
    )
    script = script.replace(
        "enhanceCommandShell(commandFocus);",
        """
enhanceCommandShell(commandFocus);
root.dataset.testRenderCount=String(Number(root.dataset.testRenderCount||0)+1);
root.dataset.testRenderMs=String(performance.now()-testStart);
root.dataset.testDomNodes=String(root.querySelectorAll('*').length);
root.dataset.testRequestCount=String(performance.getEntriesByType('resource').length);
if(localData&&!root.dataset.testUsableMs)root.dataset.testUsableMs=String(performance.now());
if(performance.memory)root.dataset.testHeapBytes=String(performance.memory.usedJSHeapSize);
""",
    )
    script += """
// TEST ONLY: browser metrics contain no account data and are never shipped.
for (const type of ['largest-contentful-paint','layout-shift','event']) {
  if (!PerformanceObserver.supportedEntryTypes.includes(type)) continue;
  new PerformanceObserver(list => {
    const root = document.querySelector('#a4-workspace');
    for (const entry of list.getEntries()) {
      if(type==='largest-contentful-paint')root.dataset.testLcpMs=String(entry.startTime);
      if(type==='layout-shift'&&!entry.hadRecentInput)
        root.dataset.testCls=String(Number(root.dataset.testCls||0)+entry.value);
      if(type==='event')root.dataset.testInteractionMs=String(Math.max(
        Number(root.dataset.testInteractionMs||0),entry.duration));
    }
  }).observe({type,buffered:true,durationThreshold:16});
}
"""
    script_path.write_text(script, encoding="utf-8")
    document = STAGE / "index.html"
    document.write_text(
        document.read_text(encoding="utf-8").replace(
            "<body>",
            '<body><p role="status">TEST ONLY — deterministic acceptance fixtures; '
            "no live data</p>",
        ),
        encoding="utf-8",
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        self.send_error(405, "TEST_ONLY_ACTIONS_DISABLED")

    def do_GET(self) -> None:
        path = urlsplit(self.path)
        if path.path == "/api/state":
            mode = (STAGE / "disconnected").read_text(encoding="utf-8")
            if mode == "unauthorized":
                self.send_error(403, "TEST_ONLY_UNAUTHORIZED")
                return
            if mode == "true":
                self.send_error(503, "TEST_ONLY_DISCONNECTED")
                return
            body = (
                b"not-json"
                if mode == "invalid"
                else (STAGE / "fixture.json").read_bytes()
            )
            kind = "application/json"
        elif path.path == "/api/markets":
            query = parse_qs(path.query)
            market = query.get("market", ["SPOT"])[0]
            symbol = query.get(
                "symbol", ["TEST_SPOT" if market == "SPOT" else "TEST_FUTURES"]
            )[0]
            body = json.dumps(
                {
                    "market": market,
                    "symbol": symbol,
                    "symbols": [symbol],
                    "timeframes": ["15m", "1h"],
                    "stale": False,
                    "execution_allowed": False,
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                }
            ).encode()
            kind = "application/json"
        elif path.path in ("/", "/app.js", "/app.css"):
            filename = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css"}[
                path.path
            ]
            kind = {
                "/": "text/html",
                "/app.js": "text/javascript",
                "/app.css": "text/css",
            }[path.path]
            body = (STAGE / filename).read_bytes()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_fixture_serves_only_test_data_and_rejects_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(Handler.do_GET.__globals__, "STAGE", tmp_path)
    (tmp_path / "fixture.json").write_text('{"test_only":true}', encoding="utf-8")
    (tmp_path / "disconnected").write_text("false", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for method, path, status in (
            ("GET", "/api/state", 200),
            ("POST", "/api/markets/refresh", 405),
            ("POST", "/api/wallet/refresh", 405),
            ("GET", "/config.json", 404),
        ):
            connection = http.client.HTTPConnection(
                "127.0.0.1",
                server.server_port,
                timeout=5,
            )
            connection.request(method, path)
            response = connection.getresponse()
            assert response.status == status
            body = response.read()
            if status == 200:
                assert json.loads(body) == {"test_only": True}
            connection.close()
        (tmp_path / "disconnected").write_text("true", encoding="utf-8")
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            server.server_port,
            timeout=5,
        )
        connection.request("GET", "/api/state")
        response = connection.getresponse()
        assert response.status == 503
        response.read()
        connection.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


if __name__ == "__main__":
    prepare()
    print("TEST_ONLY_DASHBOARD http://127.0.0.1:8766/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8766), Handler).serve_forever()
