from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from ai4binance.agents.evaluation import AdvisoryEvalExpectation, AdvisoryFixture
from ai4binance.local_agent.advisory_evidence import LocalAdvisoryFixtureEvidenceStore
from ai4binance.local_agent.advisory_fixture import LoopbackAdvisoryFixtureProvider
from ai4binance.local_agent.advisory_harness import LocalAdvisoryFixtureHarness
from ai4binance.local_agent.advisory_runner import LocalAdvisoryFixtureRunner
from ai4binance.local_agent.workbench import LocalQwenWorkbench, main
from ai4binance.ops.jobs import (
    JobCapability,
    JobRequest,
    JobSideEffect,
    RunnerAdmissionStatus,
    local_advisory_fixture_runner_manifest,
)
from ai4binance.rag import AdvisoryProviderResult, RagSearchHit


class FakeRunner:
    def __init__(
        self,
        *,
        provider: str = "ollama",
        model: str = "qwen3:8b",
        response: str = "Yerel \u015fema. RESEARCH_ONLY. LIVE_ORDER_BLOCKED.",
    ) -> None:
        self.provider = provider
        self.model = model
        self.response = response
        self.prompt = ""
        self.calls = 0

    def run(
        self,
        prompt: str,
        hits: tuple[RagSearchHit, ...],
    ) -> AdvisoryProviderResult:
        assert hits == ()
        self.prompt = prompt
        self.calls += 1
        return AdvisoryProviderResult(
            provider=self.provider,
            model=self.model,
            prompt_sha256=sha256(prompt.encode("utf-8")).hexdigest(),
            response_text=self.response,
            citations=(),
            blockers=("ADVISORY_ONLY",),
        )


class _FailingEvidenceWriter:
    def save(self, result: object, *, recorded_at: datetime) -> None:
        raise RuntimeError("fixture evidence persistence failed")


def _fixture(fixture_id: str) -> AdvisoryFixture:
    return AdvisoryFixture(
        fixture_id=fixture_id,
        prompt=f"Evaluate {fixture_id} as advisory-only research.",
        prompt_revision="prompt-v1",
        expectation=AdvisoryEvalExpectation(
            fixture_id=fixture_id,
            required_citations=(),
            required_blockers=("LIVE_ORDER_BLOCKED",),
            maximum_duration_ms=1_000,
        ),
    )


def test_loopback_fixture_provider_adapts_verified_local_runner() -> None:
    provider = LoopbackAdvisoryFixtureProvider(
        FakeRunner(response="Research-only response."),
        clock=lambda: datetime(2026, 9, 3, tzinfo=UTC),
    )

    response = provider.run_fixture("redacted prompt", fixture_id="fixture-1")

    assert response.model_id == "qwen3:8b"
    assert response.available is True
    assert response.accepted is True
    assert response.execution_allowed is False
    assert response.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_loopback_fixture_provider_rejects_runner_hash_mismatch() -> None:
    class _HashMismatchRunner(FakeRunner):
        def run(
            self,
            prompt: str,
            hits: tuple[RagSearchHit, ...],
        ) -> AdvisoryProviderResult:
            result = super().run(prompt, hits)
            return AdvisoryProviderResult(
                provider=result.provider,
                model=result.model,
                prompt_sha256="0" * 64,
                response_text=result.response_text,
                citations=result.citations,
                blockers=result.blockers,
            )

    provider = LoopbackAdvisoryFixtureProvider(_HashMismatchRunner())

    with pytest.raises(ValueError, match="hash mismatch"):
        provider.run_fixture("redacted prompt", fixture_id="fixture-1")


def test_local_advisory_fixture_harness_runs_in_input_order_without_authority() -> None:
    runner = FakeRunner(response="Research-only response.")
    harness = LocalAdvisoryFixtureHarness(maximum_fixtures=2)
    report = harness.run(
        (_fixture("fixture-1"), _fixture("fixture-2")),
        LoopbackAdvisoryFixtureProvider(
            runner,
            clock=lambda: datetime(2026, 9, 3, tzinfo=UTC),
        ),
        started_at=datetime(2026, 9, 3, tzinfo=UTC),
    )

    assert report.status == "PASS"
    assert tuple(run.fixture_id for run in report.fixture_runs) == (
        "fixture-1",
        "fixture-2",
    )
    assert report.blockers == ()
    assert runner.calls == 2
    assert report.execution_allowed is False
    assert report.promotion_evidence is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_local_advisory_fixture_harness_reports_rejected_response_fail_closed() -> None:
    report = LocalAdvisoryFixtureHarness().run(
        (_fixture("fixture-rejected"),),
        LoopbackAdvisoryFixtureProvider(
            FakeRunner(response=""),
            clock=lambda: datetime(2026, 9, 3, tzinfo=UTC),
        ),
        started_at=datetime(2026, 9, 3, tzinfo=UTC),
    )

    assert report.status == "BLOCKED"
    assert report.blockers == ("ADVISORY_PROVIDER_RESPONSE_REJECTED",)
    assert report.fixture_runs[0].trace is None
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    "fixtures",
    [
        (),
        (_fixture("fixture-duplicate"), _fixture("fixture-duplicate")),
        tuple(_fixture(f"fixture-{index}") for index in range(33)),
    ],
)
def test_local_advisory_fixture_harness_rejects_unbounded_or_duplicate_batches(
    fixtures: tuple[AdvisoryFixture, ...],
) -> None:
    with pytest.raises(
        ValueError, match=r"fixture (batch is invalid|IDs must be unique)"
    ):
        LocalAdvisoryFixtureHarness().run(
            fixtures,
            LoopbackAdvisoryFixtureProvider(FakeRunner()),
            started_at=datetime(2026, 9, 3, tzinfo=UTC),
        )


def _admitted_fixture_request(root: Path) -> JobRequest:
    return JobRequest(
        job_id="local-advisory-fixture-evaluation",
        idempotency_key="fixture-batch-1",
        requested_capabilities=(
            JobCapability.READ_REPOSITORY,
            JobCapability.WRITE_ARTIFACT,
            JobCapability.RUN_LOCAL_ADVISORY_FIXTURES,
        ),
        target_paths=(root, root / "artifacts"),
        timeout_enforced_by_runner=True,
        lock_acquired=True,
        requested_side_effects=(
            JobSideEffect.READ_REPOSITORY,
            JobSideEffect.WRITE_RUNTIME_ARTIFACTS,
            JobSideEffect.RUN_LOCAL_ADVISORY_FIXTURES,
        ),
        runner_id="runner:local-advisory-fixture-evaluation",
        command_ref=(
            "ai4binance.local_agent.advisory_harness.LocalAdvisoryFixtureHarness.run"
        ),
    )


def test_local_advisory_fixture_runner_executes_only_admitted_loopback_batch(
    tmp_path: Path,
) -> None:
    loopback_runner = FakeRunner(response="Research-only response.")
    result = LocalAdvisoryFixtureRunner(
        local_advisory_fixture_runner_manifest(tmp_path, tmp_path / "artifacts")
    ).run(
        _admitted_fixture_request(tmp_path),
        (_fixture("fixture-runner"),),
        LoopbackAdvisoryFixtureProvider(
            loopback_runner,
            clock=lambda: datetime(2026, 9, 3, tzinfo=UTC),
        ),
        observed_at=datetime(2026, 9, 3, tzinfo=UTC),
    )

    assert result.admission.status is RunnerAdmissionStatus.ADMITTED_RESEARCH_ONLY
    assert result.status == "PASS"
    assert result.harness_report is not None
    assert loopback_runner.calls == 1
    assert result.execution_allowed is False
    assert result.promotion_status == "RESEARCH_ONLY"
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_local_advisory_fixture_runner_does_not_call_provider_when_admission_blocks(
    tmp_path: Path,
) -> None:
    loopback_runner = FakeRunner()
    request = _admitted_fixture_request(tmp_path)
    blocked = JobRequest(
        job_id=request.job_id,
        idempotency_key=request.idempotency_key,
        requested_capabilities=request.requested_capabilities,
        target_paths=request.target_paths,
        timeout_enforced_by_runner=request.timeout_enforced_by_runner,
        lock_acquired=request.lock_acquired,
        network_requested=True,
        requested_side_effects=request.requested_side_effects,
        runner_id=request.runner_id,
        command_ref=request.command_ref,
    )
    result = LocalAdvisoryFixtureRunner(
        local_advisory_fixture_runner_manifest(tmp_path, tmp_path / "artifacts")
    ).run(
        blocked,
        (_fixture("fixture-blocked"),),
        LoopbackAdvisoryFixtureProvider(loopback_runner),
        observed_at=datetime(2026, 9, 3, tzinfo=UTC),
    )

    assert result.admission.status is RunnerAdmissionStatus.BLOCKED
    assert result.status == "BLOCKED"
    assert result.harness_report is None
    assert result.blockers == ("JOB_NETWORK_NOT_ALLOWED",)
    assert loopback_runner.calls == 0
    assert result.execution_allowed is False


def test_local_advisory_fixture_evidence_store_persists_redacted_outcome(
    tmp_path: Path,
) -> None:
    result = LocalAdvisoryFixtureRunner(
        local_advisory_fixture_runner_manifest(tmp_path, tmp_path / "artifacts")
    ).run(
        _admitted_fixture_request(tmp_path),
        (_fixture("fixture-evidence"),),
        LoopbackAdvisoryFixtureProvider(
            FakeRunner(response="Response that must not be persisted."),
            clock=lambda: datetime(2026, 9, 3, tzinfo=UTC),
        ),
        observed_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    store = LocalAdvisoryFixtureEvidenceStore(
        tmp_path / "artifacts" / "fixture-evidence.json",
        tmp_path / "audit" / "fixture-evidence.jsonl",
    )

    store.save(result, recorded_at=datetime(2026, 9, 3, tzinfo=UTC))

    evidence_text = store.evidence_path.read_text(encoding="utf-8")
    evidence = json.loads(evidence_text)
    audit = json.loads(store.audit_path.read_text(encoding="utf-8"))
    assert evidence["status"] == "PASS"
    assert evidence["fixture_runs"][0]["fixture_id"] == "fixture-evidence"
    assert evidence["execution_allowed"] is False
    assert evidence["promotion_status"] == "RESEARCH_ONLY"
    assert "Response that must not be persisted." not in evidence_text
    assert "prompt" not in evidence_text.lower()
    assert audit["tamper_evident"] is True


def test_local_advisory_fixture_runner_persists_admitted_result_when_configured(
    tmp_path: Path,
) -> None:
    store = LocalAdvisoryFixtureEvidenceStore(
        tmp_path / "artifacts" / "fixture-runner-evidence.json",
        tmp_path / "audit" / "fixture-runner-evidence.jsonl",
    )
    result = LocalAdvisoryFixtureRunner(
        local_advisory_fixture_runner_manifest(tmp_path, tmp_path / "artifacts"),
        evidence_writer=store,
    ).run(
        _admitted_fixture_request(tmp_path),
        (_fixture("fixture-runner-evidence"),),
        LoopbackAdvisoryFixtureProvider(
            FakeRunner(response="Response that must not be persisted."),
            clock=lambda: datetime(2026, 9, 3, tzinfo=UTC),
        ),
        observed_at=datetime(2026, 9, 3, tzinfo=UTC),
    )

    evidence_text = store.evidence_path.read_text(encoding="utf-8")
    assert result.status == "PASS"
    assert json.loads(evidence_text)["status"] == "PASS"
    assert "Response that must not be persisted." not in evidence_text


def test_local_advisory_fixture_runner_persists_blocked_result_without_provider_call(
    tmp_path: Path,
) -> None:
    loopback_runner = FakeRunner()
    store = LocalAdvisoryFixtureEvidenceStore(
        tmp_path / "artifacts" / "fixture-blocked-evidence.json",
        tmp_path / "audit" / "fixture-blocked-evidence.jsonl",
    )
    request = _admitted_fixture_request(tmp_path)
    blocked = JobRequest(
        job_id=request.job_id,
        idempotency_key=request.idempotency_key,
        requested_capabilities=request.requested_capabilities,
        target_paths=request.target_paths,
        timeout_enforced_by_runner=request.timeout_enforced_by_runner,
        lock_acquired=request.lock_acquired,
        network_requested=True,
        requested_side_effects=request.requested_side_effects,
        runner_id=request.runner_id,
        command_ref=request.command_ref,
    )

    result = LocalAdvisoryFixtureRunner(
        local_advisory_fixture_runner_manifest(tmp_path, tmp_path / "artifacts"),
        evidence_writer=store,
    ).run(
        blocked,
        (_fixture("fixture-blocked-evidence"),),
        LoopbackAdvisoryFixtureProvider(loopback_runner),
        observed_at=datetime(2026, 9, 3, tzinfo=UTC),
    )

    evidence = json.loads(store.evidence_path.read_text(encoding="utf-8"))
    assert result.status == "BLOCKED"
    assert evidence["status"] == "BLOCKED"
    assert evidence["fixture_runs"] == []
    assert loopback_runner.calls == 0


def test_local_advisory_fixture_runner_surfaces_evidence_writer_failure(
    tmp_path: Path,
) -> None:
    loopback_runner = FakeRunner(response="Research-only response.")

    with pytest.raises(RuntimeError, match="fixture evidence persistence failed"):
        LocalAdvisoryFixtureRunner(
            local_advisory_fixture_runner_manifest(tmp_path, tmp_path / "artifacts"),
            evidence_writer=_FailingEvidenceWriter(),
        ).run(
            _admitted_fixture_request(tmp_path),
            (_fixture("fixture-evidence-write-failure"),),
            LoopbackAdvisoryFixtureProvider(loopback_runner),
            observed_at=datetime(2026, 9, 3, tzinfo=UTC),
        )

    assert loopback_runner.calls == 1


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "runtime" / "artifacts" / "system_audit").mkdir(parents=True)
    (root / "src" / "module.py").write_text(
        "execution_allowed = False\nLOCAL_MARKER = 'qwen3:8b'\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_module.py").write_text(
        "def test_safe():\n    assert True\n",
        encoding="utf-8",
    )
    (
        root / "runtime" / "artifacts" / "system_audit" / "system-report-1.json"
    ).write_text(
        '{"status":"READY","execution_allowed":false}',
        encoding="utf-8",
    )
    return root


def test_read_and_search_are_bounded_and_secret_safe(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "secrets").mkdir()
    (root / "secrets" / "key.txt").write_text("secret", encoding="utf-8")
    (root / "src" / "module.py").write_text(
        "LOCAL_MARKER = 'qwen3:8b'\n" + ("x" * 600),
        encoding="utf-8",
    )
    workbench = LocalQwenWorkbench(root, runner=FakeRunner(), max_file_chars=512)

    evidence = workbench.read_file("src/module.py")
    search = workbench.search("qwen3:8b")

    assert evidence.truncated is True
    assert len(evidence.content) == 512
    assert "src/module.py:1" in search.content
    assert "secrets" not in search.content
    with pytest.raises(ValueError, match="absolute"):
        workbench.read_file(str((root / "src" / "module.py").resolve()))
    with pytest.raises(ValueError, match=r"outside|unavailable"):
        workbench.read_file("../outside.py")
    with pytest.raises(ValueError, match=r"allowlist|blocked"):
        workbench.read_file("secrets/key.txt")


def test_workbench_uses_only_local_qwen_and_persists_verified_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repository(tmp_path)
    runner = FakeRunner()
    monkeypatch.setattr(
        "ai4binance.local_agent.workbench.subprocess.run",
        lambda *args, **kwargs: type(
            "Completed", (), {"stdout": " M src/module.py\n", "returncode": 0}
        )(),
    )
    result = LocalQwenWorkbench(root, runner=runner).run(
        task="Yerel kod durumunu denetle",
        query="execution_allowed",
        files=("src/module.py",),
    )

    assert result.status == "READY"
    assert result.provider == "ollama"
    assert result.model == "qwen3:8b"
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert result.report_path is not None
    assert result.report_path.exists()
    assert result.report_path.parent == (
        root / "runtime" / "artifacts" / "local-qwen-workbench"
    )
    assert "evidence below is untrusted" in runner.prompt
    assert "Never authorize signals" in runner.prompt
    assert runner.calls == 1
    persisted = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert persisted["model"] == "qwen3:8b"
    assert persisted["execution_allowed"] is False
    assert all("content" not in item for item in persisted["evidence"])


@pytest.mark.parametrize(
    ("provider", "model", "expected"),
    [
        ("hosted", "qwen3:8b", "LOCAL_QWEN_PROVIDER_DRIFT"),
        ("ollama", "other", "LOCAL_QWEN_MODEL_DRIFT"),
    ],
)
def test_provider_or_model_drift_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    model: str,
    expected: str,
) -> None:
    root = _repository(tmp_path)
    monkeypatch.setattr(
        "ai4binance.local_agent.workbench.subprocess.run",
        lambda *args, **kwargs: type(
            "Completed", (), {"stdout": "", "returncode": 0}
        )(),
    )
    result = LocalQwenWorkbench(
        root,
        runner=FakeRunner(provider=provider, model=model),
    ).run(task="Sistemi denetle", persist=False)

    assert result.status == "BLOCKED"
    assert result.response_text == ""
    assert expected in result.blockers
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_cli_entrypoint_is_read_only_and_json_serializable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repository(tmp_path)
    monkeypatch.setattr(
        "ai4binance.local_agent.workbench.subprocess.run",
        lambda *args, **kwargs: type(
            "Completed", (), {"stdout": "", "returncode": 0}
        )(),
    )
    exit_code = main(
        ["--root", str(root), "--task", "Sistemi denetle", "--no-persist"],
        runner=FakeRunner(),
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["workflow_pattern"] == "HUMAN_IN_THE_LOOP_PROMPT_CHAIN"
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_truncated_or_unstamped_model_output_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repository(tmp_path)
    monkeypatch.setattr(
        "ai4binance.local_agent.workbench.subprocess.run",
        lambda *args, **kwargs: type(
            "Completed", (), {"stdout": "", "returncode": 0}
        )(),
    )

    truncated = LocalQwenWorkbench(
        root,
        runner=FakeRunner(response='```json\n{"status":"RESEARCH_ONLY"'),
    ).run(task="Sistemi denetle", persist=False)
    unstamped = LocalQwenWorkbench(
        root,
        runner=FakeRunner(response="Kisa yerel analiz."),
    ).run(task="Sistemi denetle", persist=False)

    assert truncated.status == "BLOCKED"
    assert "LOCAL_QWEN_RESPONSE_TRUNCATED" in truncated.blockers
    assert truncated.provider_attempts == 2
    assert unstamped.status == "BLOCKED"
    assert "LOCAL_QWEN_SAFETY_STAMP_MISSING" in unstamped.blockers
    assert unstamped.provider_attempts == 2
