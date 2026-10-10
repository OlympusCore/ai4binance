from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from ai4binance.enterprise.resources import ResourcePolicy


@pytest.mark.parametrize(
    ("used", "discretionary", "blocker"),
    [
        (29.9, True, None),
        (30.0, True, "RESOURCE_RAM_SOFT_LIMIT"),
        (30.0, False, None),
        (36.0, False, "RESOURCE_RAM_HARD_LIMIT"),
        (None, True, "RESOURCE_RAM_NOT_VERIFIED"),
        (float("nan"), False, "RESOURCE_RAM_NOT_VERIFIED"),
    ],
)
def test_resource_ram_admission(
    used: float | None, discretionary: bool, blocker: str | None
) -> None:
    assert ResourcePolicy().memory_blocker(used, discretionary=discretionary) == blocker


def test_orchestrator_pool_obeys_resource_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai4binance.agents.orchestrator import EnterpriseOrchestrator
    from tests.test_technical_agents import technical_snapshot

    workers: list[int] = []

    def pool(*, max_workers: int, thread_name_prefix: str) -> ThreadPoolExecutor:
        workers.append(max_workers)
        return ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix=thread_name_prefix
        )

    monkeypatch.setattr("ai4binance.agents.orchestrator.ThreadPoolExecutor", pool)
    EnterpriseOrchestrator(
        max_workers=32, resource_policy=ResourcePolicy(deterministic_cpu_workers=2)
    ).analyze(technical_snapshot())
    assert workers == [2]


def test_resource_lane_contention_times_out_and_releases(tmp_path: Path) -> None:
    from ai4binance.events.file_lock import exclusive_file_lock

    lane = tmp_path / "lane.lock"
    with exclusive_file_lock(lane):
        with ThreadPoolExecutor(max_workers=1) as pool:

            def contend() -> None:
                with exclusive_file_lock(lane, timeout_seconds=0.01):
                    pytest.fail("test-only contender must not enter an occupied lane")

            with pytest.raises(TimeoutError):
                pool.submit(contend).result(timeout=3)
    with exclusive_file_lock(lane, timeout_seconds=0.01):
        pass
    assert lane.read_bytes() == b"0"


def test_resource_wiring_supports_operational_first_import() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "from ai4binance.ops.quality_gate import repository_completion; "
            "from ai4binance.agents.orchestrator import EnterpriseOrchestrator; "
            "from ai4binance.rag import LlamaCppAdvisoryRunner",
        ],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_resource_policy_matches_local_bounded_hardware_defaults() -> None:
    policy = ResourcePolicy()

    assert policy.io_concurrency == 10
    assert policy.deterministic_cpu_workers == 6
    assert policy.cpu_heavy_processes == 2
    assert policy.llm_concurrency == 1
    assert policy.backtest_parallel_jobs == 2
    assert policy.exclusive_llm_lane is True
    assert policy.simultaneous_llm_and_training is False
    assert policy.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(ResourcePolicy(), io_concurrency=11),
        lambda: replace(ResourcePolicy(), deterministic_cpu_workers=7),
        lambda: replace(ResourcePolicy(), cpu_heavy_processes=3),
        lambda: replace(ResourcePolicy(), llm_concurrency=2),
        lambda: replace(ResourcePolicy(), backtest_parallel_jobs=3),
    ],
)
def test_resource_policy_rejects_unbounded_concurrency(
    factory: Callable[[], ResourcePolicy],
) -> None:
    with pytest.raises(ValueError, match="resource budget"):
        factory()


def test_resource_policy_rejects_gpu_contention_and_execution_authority() -> None:
    with pytest.raises(ValueError, match="exclusive"):
        replace(ResourcePolicy(), exclusive_llm_lane=False)
    with pytest.raises(ValueError, match="simultaneous"):
        replace(ResourcePolicy(), simultaneous_llm_and_training=True)
    with pytest.raises(ValueError, match="authorize"):
        replace(ResourcePolicy(), execution_allowed=True)
    with pytest.raises(ValueError, match="RAM policy"):
        replace(ResourcePolicy(), ram_soft_limit_gb=36)
