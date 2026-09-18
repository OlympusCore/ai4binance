"""Standalone Radar CLI and bounded transport tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai4binance.github_radar import __main__ as radar_cli
from ai4binance.github_radar.engine import GitHubRadarEngine
from ai4binance.github_radar.github_client import (
    MAX_RESPONSE_BYTES,
    HttpsGitHubTransport,
)
from ai4binance.github_radar.reporting import write_json_atomic


def test_cli_baseline_writes_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "baseline.json"

    exit_code = radar_cli.main(
        [
            "--repository-root",
            str(Path.cwd()),
            "baseline",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["capability_count"] == 76
    assert printed == payload


def test_cli_evaluate_writes_research_only_catalog(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "evaluation.json"

    exit_code = radar_cli.main(
        [
            "--repository-root",
            str(Path.cwd()),
            "evaluate",
            "--input",
            "tests/fixtures/github_radar/repository_evidence.json",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["catalog_entry"]["status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert json.loads(capsys.readouterr().out) == payload


def test_cli_discover_is_bounded_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "discovery.json"

    def fake_discover(
        self: GitHubRadarEngine,
        client: object,
        **options: object,
    ) -> tuple[()]:
        assert client is not None
        assert options["capability_ids"] == ("R26-C01",)
        return ()

    monkeypatch.setattr(GitHubRadarEngine, "discover", fake_discover)

    exit_code = radar_cli.main(
        [
            "--repository-root",
            str(Path.cwd()),
            "discover",
            "--capability",
            "R26-C01",
            "--maximum-queries",
            "1",
            "--repositories-per-query",
            "1",
            "--documents-per-repository",
            "2",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["candidate_count"] == 0
    assert payload["execution_allowed"] is False
    assert json.loads(capsys.readouterr().out) == payload


def test_cli_input_helpers_and_atomic_writer_fail_closed(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.json"
    oversized.write_text("x" * 512_001, encoding="utf-8")
    with pytest.raises(ValueError, match="bounded size"):
        radar_cli._load_repository_evidence(oversized)
    with pytest.raises(ValueError, match="must be a mapping"):
        radar_cli._mapping([], "input")
    with pytest.raises(ValueError, match="must be a sequence"):
        radar_cli._sequence("not-a-sequence", "input")

    output = tmp_path / "nested" / "payload.json"
    write_json_atomic(output, {"status": "RESEARCH_ONLY"})
    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "RESEARCH_ONLY"}
    assert not output.with_suffix(".json.tmp").exists()


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self, maximum: int) -> bytes:
        assert maximum == MAX_RESPONSE_BYTES + 1
        return self._body


class FakeConnection:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.request_args: tuple[object, ...] | None = None
        self.closed = False

    def request(self, *args: object, **kwargs: object) -> None:
        self.request_args = (*args, kwargs)

    def getresponse(self) -> FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


def test_https_transport_is_get_only_bounded_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(FakeResponse(200, b'{"rate": 60}'))
    monkeypatch.setattr(
        "ai4binance.github_radar.github_client.http.client.HTTPSConnection",
        lambda host, timeout: connection,
    )
    transport = HttpsGitHubTransport("session-token", timeout_seconds=2.0)

    payload = transport.get_json("/rate_limit", {"scope": "core"})

    assert payload == {"rate": 60}
    assert connection.request_args is not None
    assert connection.request_args[0] == "GET"
    assert connection.closed is True


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (FakeResponse(403, b"denied"), "status 403"),
        (FakeResponse(200, b"x" * (MAX_RESPONSE_BYTES + 1)), "bounded size"),
    ],
)
def test_https_transport_rejects_failure_and_unbounded_response(
    monkeypatch: pytest.MonkeyPatch,
    response: FakeResponse,
    message: str,
) -> None:
    connection = FakeConnection(response)
    monkeypatch.setattr(
        "ai4binance.github_radar.github_client.http.client.HTTPSConnection",
        lambda host, timeout: connection,
    )

    with pytest.raises((RuntimeError, ValueError), match=message):
        HttpsGitHubTransport().get_json("/rate_limit")
    assert connection.closed is True


def test_https_transport_rejects_invalid_configuration_and_path() -> None:
    with pytest.raises(ValueError, match="blank"):
        HttpsGitHubTransport(" ")
    with pytest.raises(ValueError, match="timeout"):
        HttpsGitHubTransport(timeout_seconds=0.5)
    with pytest.raises(ValueError, match="path"):
        HttpsGitHubTransport().get_json("https://api.github.com/rate_limit")
