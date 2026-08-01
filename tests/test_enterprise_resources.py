from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from ai4binance.enterprise.resources import ResourcePolicy


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
