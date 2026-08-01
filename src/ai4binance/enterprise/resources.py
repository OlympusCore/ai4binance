"""Hardware-aware bounded resource policy for enterprise workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkPriority(StrEnum):
    P0_RISK_VALIDATION_INCIDENT = "P0_RISK_VALIDATION_INCIDENT"
    P1_ACCOUNT_MARKET_MONITORING = "P1_ACCOUNT_MARKET_MONITORING"
    P2_USER_WORK_ORDER = "P2_USER_WORK_ORDER"
    P3_BACKTEST_QUALITY_AUDIT = "P3_BACKTEST_QUALITY_AUDIT"
    P4_TUNING_KNOWLEDGE_REFRESH = "P4_TUNING_KNOWLEDGE_REFRESH"


@dataclass(frozen=True, slots=True)
class ResourcePolicy:
    io_concurrency: int = 10
    deterministic_cpu_workers: int = 6
    cpu_heavy_processes: int = 2
    llm_concurrency: int = 1
    gpu_training_concurrency: int = 1
    backtest_parallel_jobs: int = 2
    ram_soft_limit_gb: int = 30
    ram_hard_limit_gb: int = 36
    exclusive_llm_lane: bool = True
    simultaneous_llm_and_training: bool = False
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _bounded("io_concurrency", self.io_concurrency, 1, 10)
        _bounded("deterministic_cpu_workers", self.deterministic_cpu_workers, 1, 6)
        _bounded("cpu_heavy_processes", self.cpu_heavy_processes, 1, 2)
        _bounded("llm_concurrency", self.llm_concurrency, 1, 1)
        _bounded("gpu_training_concurrency", self.gpu_training_concurrency, 0, 1)
        _bounded("backtest_parallel_jobs", self.backtest_parallel_jobs, 1, 2)
        if not 1 <= self.ram_soft_limit_gb < self.ram_hard_limit_gb <= 36:
            raise ValueError("RAM policy must stay within the approved local budget")
        if not self.exclusive_llm_lane:
            raise ValueError("local LLM lane must remain exclusive")
        if self.simultaneous_llm_and_training:
            raise ValueError("simultaneous LLM and training is not allowed")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("resource policy cannot authorize execution")


def _bounded(name: str, value: int, lower: int, upper: int) -> None:
    if not lower <= value <= upper:
        raise ValueError(f"{name} is outside the approved local resource budget")
