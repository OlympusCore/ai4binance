"""Fail-closed coverage for the local Futures OOS publication CLI."""

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai4binance.cli import futures_oos


def resolver_root(tmp_path: Path) -> futures_oos.LocalGitFuturesOosRevisionResolver:
    (tmp_path / ".git").mkdir()
    return futures_oos.LocalGitFuturesOosRevisionResolver(tmp_path)


def test_futures_oos_git_resolver_rejects_unsafe_configuration_and_missing_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="timeout"):
        futures_oos.LocalGitFuturesOosRevisionResolver(tmp_path, timeout_seconds=0.0)
    with pytest.raises(ValueError, match="output bound"):
        futures_oos.LocalGitFuturesOosRevisionResolver(tmp_path, max_output_bytes=1)
    with pytest.raises(ValueError, match="ROOT_INVALID"):
        futures_oos.LocalGitFuturesOosRevisionResolver(tmp_path / "missing")

    resolver = resolver_root(tmp_path)
    monkeypatch.setattr(futures_oos.shutil, "which", lambda _name: None)  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="GIT_UNAVAILABLE"):
        resolver()


def test_futures_oos_git_runner_rejects_command_output_and_decoding_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolver = resolver_root(tmp_path)
    monkeypatch.setattr(
        futures_oos.subprocess,  # type: ignore[attr-defined]
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("missing")),
    )
    with pytest.raises(ValueError, match="GIT_COMMAND_FAILED"):
        resolver._run_git("git", "status")

    monkeypatch.setattr(
        futures_oos.subprocess,  # type: ignore[attr-defined]
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout=b"x" * 1025, stderr=b"", returncode=0
        ),
    )
    resolver = futures_oos.LocalGitFuturesOosRevisionResolver(
        tmp_path, max_output_bytes=1024
    )
    with pytest.raises(ValueError, match="GIT_OUTPUT_TOO_LARGE"):
        resolver._run_git("git", "status")

    monkeypatch.setattr(
        futures_oos.subprocess,  # type: ignore[attr-defined]
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=b"", stderr=b"", returncode=1),
    )
    with pytest.raises(ValueError, match="GIT_COMMAND_FAILED"):
        resolver._run_git("git", "status")

    monkeypatch.setattr(
        futures_oos.subprocess,  # type: ignore[attr-defined]
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout=b"\xff", stderr=b"", returncode=0
        ),
    )
    with pytest.raises(ValueError, match="GIT_OUTPUT_INVALID"):
        resolver._run_git("git", "status")


def test_futures_oos_cli_helpers_keep_window_and_blocker_bounds() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="between two"):
        futures_oos._positive_integer("1")
    assert futures_oos._positive_integer("2") == 2
    assert (
        futures_oos._bounded_blocker(ValueError(" "))
        == "FUTURES_OOS_PUBLICATION_FAILED"
    )
    assert futures_oos._bounded_blocker(ValueError("x" * 257)) == (
        "FUTURES_OOS_PUBLICATION_FAILED"
    )
    bounded = futures_oos._bounded_blocker(ValueError("REPLAY_TAMPERED"))
    assert bounded == "REPLAY_TAMPERED"


def test_futures_oos_cli_reports_local_io_failure_without_execution_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Loader:
        def __init__(self, _root: Path) -> None:
            pass

        def load(self, _replay_file: str) -> object:
            raise OSError("unreadable")

    monkeypatch.setattr(futures_oos, "RuntimeFuturesReplayLoader", Loader)

    exit_code = futures_oos.main(
        (
            "--repository-root",
            str(tmp_path),
            "--replay-file",
            "fixture.json",
            "--setup",
            "DELEVERAGING",
            "--train-size",
            "4",
            "--test-size",
            "2",
            "--step-size",
            "2",
        )
    )

    assert exit_code == 2
    assert "FUTURES_OOS_LOCAL_IO_FAILED" in capsys.readouterr().out
