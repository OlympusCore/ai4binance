"""Deterministic operating-system boundary contracts for migration measurements."""

import ctypes
import os
import platform
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from ai4binance.ops import python_migration_benchmark as benchmark


def test_system_cpu_probe_reads_ticks_and_rejects_failed_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def read_times(idle: object, kernel: object, user: object) -> bool:
        for pointer, value in ((idle, 2), (kernel, 7), (user, 3)):
            cast(Any, pointer)._obj.low = value
            cast(Any, pointer)._obj.high = 1
        return True

    api = SimpleNamespace(GetSystemTimes=Mock(side_effect=read_times))
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: api)
    assert benchmark._windows_system_cpu_times() == tuple(
        (1 << 32) + value for value in (2, 7, 3)
    )
    api.GetSystemTimes.side_effect = None
    api.GetSystemTimes.return_value = False
    with pytest.raises(OSError, match="HOST_LOAD_PROBE_FAILED"):
        benchmark._windows_system_cpu_times()
    monkeypatch.setattr(ctypes, "WinDLL", None)
    with pytest.raises(OSError, match="HOST_LOAD_PROBE_UNAVAILABLE"):
        benchmark._windows_system_cpu_times()


def test_host_load_uses_two_samples_and_requested_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    probe = Mock(side_effect=[(20, 40, 10), (25, 50, 20)])
    sleep = Mock()
    monkeypatch.setattr(benchmark, "_windows_system_cpu_times", probe)
    monkeypatch.setattr(time, "sleep", sleep)
    assert benchmark._host_cpu_load_percent(probe_seconds=0.25) == 75.0
    sleep.assert_called_once_with(0.25)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    with pytest.raises(OSError, match="UNSUPPORTED_PLATFORM"):
        benchmark._host_cpu_load_percent(probe_seconds=0.25)


@pytest.mark.parametrize("after", [(0, 0, 0), (30, 10, 10)])
def test_cpu_load_rejects_nonadvancing_or_inconsistent_ticks(
    after: tuple[int, int, int],
) -> None:
    with pytest.raises(ValueError, match="HOST_LOAD_SAMPLE_INVALID"):
        benchmark._cpu_load_percent_between((0, 0, 0), after)


@pytest.mark.parametrize(
    ("handle", "wait", "blocker"),
    [
        (0, 0, "QUALITY_GATE_MUTEX_UNAVAILABLE"),
        (42, 258, "QUALITY_GATE_ALREADY_RUNNING"),
        (42, 99, "QUALITY_GATE_MUTEX_UNAVAILABLE"),
        (42, 0, None),
        (42, 128, None),
    ],
)
def test_quality_mutex_classifies_and_closes_handles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    handle: int,
    wait: int,
    blocker: str,
) -> None:
    api = SimpleNamespace(
        CreateMutexW=Mock(return_value=handle),
        WaitForSingleObject=Mock(return_value=wait),
        CloseHandle=Mock(),
        ReleaseMutex=Mock(),
    )
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: api)
    assert benchmark._try_acquire_quality_gate_mutex(tmp_path) == (
        handle if blocker is None else None,
        blocker,
    )
    if blocker is None:
        api.CloseHandle.assert_not_called()
        benchmark._release_quality_gate_mutex(handle)
        api.ReleaseMutex.assert_called_once_with(handle)
    if handle:
        api.CloseHandle.assert_called_once_with(handle)
    else:
        api.CloseHandle.assert_not_called()


@pytest.mark.parametrize(
    ("query", "mask", "setting", "error"),
    [
        (False, 3, True, "QUERY_FAILED"),
        (True, 1, True, "CPU_NOT_ALLOWED"),
        (True, 3, False, "SET_FAILED"),
        (True, 3, True, None),
    ],
)
def test_process_affinity_never_changes_real_host(
    monkeypatch: pytest.MonkeyPatch, query: bool, mask: int, setting: bool, error: str
) -> None:
    def get_masks(process: int, process_mask: object, system_mask: object) -> bool:
        assert process == 10
        cast(Any, process_mask)._obj.value = mask
        cast(Any, system_mask)._obj.value = 3
        return query

    api = SimpleNamespace(
        GetCurrentProcess=Mock(return_value=10),
        GetProcessAffinityMask=Mock(side_effect=get_masks),
        SetProcessAffinityMask=Mock(return_value=setting),
    )
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: api)
    if error:
        with pytest.raises((OSError, ValueError), match=error):
            benchmark._set_process_affinity(1)
    else:
        assert benchmark._set_process_affinity(1) == {"cpu_index": 1, "mask": 2}
        api.SetProcessAffinityMask.assert_called_once_with(10, 2)


def test_unavailable_host_services_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert benchmark._try_acquire_quality_gate_mutex(tmp_path) == (
        None,
        "QUALITY_GATE_MUTEX_UNAVAILABLE",
    )
    benchmark._release_quality_gate_mutex(42)
    with pytest.raises(OSError, match="UNSUPPORTED_PLATFORM"):
        benchmark._set_process_affinity(0)
    monkeypatch.setattr(os, "cpu_count", lambda: None)
    with pytest.raises(OSError, match="HOST_LOGICAL_PROCESSOR_COUNT_UNAVAILABLE"):
        benchmark._measurement_host_load_limits()


@pytest.mark.parametrize(
    ("value", "blocker"),
    [(-1, "HOST_LOAD_SAMPLE_INVALID"), (101, "HOST_LOAD_SAMPLE_INVALID")],
)
def test_quiescence_rejects_invalid_samples(value: float, blocker: str) -> None:
    assert benchmark._await_host_quiescence(sampler=lambda: value) == (
        False,
        (),
        blocker,
    )


def test_quiescence_probe_errors_and_sustained_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(benchmark, "_host_cpu_load_percent", Mock(side_effect=OSError))
    assert benchmark._await_host_quiescence() == (False, (), "HOST_LOAD_UNAVAILABLE")
    monkeypatch.setattr(benchmark, "_QUIESCENCE_ATTEMPTS", 2)
    assert benchmark._await_host_quiescence(
        sampler=lambda: 100, sleeper=lambda _: None
    ) == (False, (100.0, 100.0), "HOST_NOT_QUIESCENT")
