"""Hardware-aware bounded resource policy for enterprise workflows."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from pathlib import Path


class WorkPriority(StrEnum):
    P0_RISK_VALIDATION_INCIDENT = "P0_RISK_VALIDATION_INCIDENT"
    P1_ACCOUNT_MARKET_MONITORING = "P1_ACCOUNT_MARKET_MONITORING"
    P2_USER_WORK_ORDER = "P2_USER_WORK_ORDER"
    P3_BACKTEST_QUALITY_AUDIT = "P3_BACKTEST_QUALITY_AUDIT"
    P4_TUNING_KNOWLEDGE_REFRESH = "P4_TUNING_KNOWLEDGE_REFRESH"


class ResourceAdmissionError(RuntimeError):
    """Expose a fixed, non-sensitive resource refusal to canonical health stores."""

    def __init__(self, blocker: str) -> None:
        if blocker not in {
            "RESOURCE_RAM_NOT_VERIFIED",
            "RESOURCE_RAM_HARD_LIMIT",
            "RESOURCE_RAM_SOFT_LIMIT",
        }:
            raise ValueError("unsupported resource admission blocker")
        self.blocker = blocker
        super().__init__(blocker)


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

    def memory_blocker(
        self, used_gb: float | None, *, discretionary: bool
    ) -> str | None:
        """Admit work against host physical RAM, leaving the OS reserve intact."""
        if used_gb is None or not isfinite(used_gb) or used_gb < 0:
            return "RESOURCE_RAM_NOT_VERIFIED"
        if used_gb >= self.ram_hard_limit_gb:
            return "RESOURCE_RAM_HARD_LIMIT"
        if discretionary and used_gb >= self.ram_soft_limit_gb:
            return "RESOURCE_RAM_SOFT_LIMIT"
        return None


def physical_ram_used_gb() -> float | None:
    """Read host physical RAM without installing a monitoring dependency."""
    try:
        if os.name == "nt":

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("load", ctypes.c_ulong),
                    ("total", ctypes.c_ulonglong),
                    ("available", ctypes.c_ulonglong),
                    ("page_total", ctypes.c_ulonglong),
                    ("page_available", ctypes.c_ulonglong),
                    ("virtual_total", ctypes.c_ulonglong),
                    ("virtual_available", ctypes.c_ulonglong),
                    ("extended_available", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            probe = ctypes.WinDLL("kernel32", use_last_error=True).GlobalMemoryStatusEx
            probe.argtypes = [ctypes.POINTER(MemoryStatus)]
            probe.restype = ctypes.c_int
            if not probe(ctypes.byref(status)):
                return None
            return float(status.total - status.available) / (1024**3)
        values = {
            key: int(value.split()[0])
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines()
            for key, value in (line.split(":", 1),)
        }
        return (values["MemTotal"] - values["MemAvailable"]) / (1024**2)
    except OSError, ValueError, KeyError, AttributeError:
        return None


def _bounded(name: str, value: int, lower: int, upper: int) -> None:
    if not lower <= value <= upper:
        raise ValueError(f"{name} is outside the approved local resource budget")
