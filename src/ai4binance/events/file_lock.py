"""Cross-platform exclusive file locking for local event persistence."""

from __future__ import annotations

import errno
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, cast

_WINDOWS_LOCK_RETRY_SECONDS = 0.05
_WINDOWS_LOCK_TIMEOUT_SECONDS = 30.0
_WINDOWS_RETRYABLE_LOCK_ERRORS = frozenset({errno.EACCES, errno.EAGAIN, errno.EDEADLK})


@contextmanager
def exclusive_file_lock(
    path: Path, *, timeout_seconds: float | None = None
) -> Iterator[None]:
    """Hold one exclusive byte-range lock for the supplied lock file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if timeout_seconds is not None and not 0 < timeout_seconds <= 300:
            raise ValueError("file lock timeout must be between zero and 300 seconds")
        if timeout_seconds is None:
            _acquire_file_lock(stream)
        else:
            _acquire_file_lock(stream, timeout_seconds=timeout_seconds)
        try:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            yield
        finally:
            _release_file_lock(stream)


def _acquire_file_lock(
    stream: BinaryIO, *, timeout_seconds: float | None = None
) -> None:
    if os.name == "nt":
        _acquire_windows_file_lock(stream, timeout_seconds=timeout_seconds)
    else:
        _acquire_posix_file_lock(stream, timeout_seconds=timeout_seconds)


def _acquire_windows_file_lock(
    stream: BinaryIO, *, timeout_seconds: float | None
) -> None:
    import msvcrt

    deadline = time.monotonic() + (
        timeout_seconds
        if timeout_seconds is not None
        else _WINDOWS_LOCK_TIMEOUT_SECONDS
    )
    while True:
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError as error:
            if error.errno not in _WINDOWS_RETRYABLE_LOCK_ERRORS:
                raise
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "exclusive file lock acquisition timed out"
                ) from error
            time.sleep(_WINDOWS_LOCK_RETRY_SECONDS)


def _acquire_posix_file_lock(
    stream: BinaryIO, *, timeout_seconds: float | None
) -> None:
    import fcntl

    flock = cast(Any, getattr(fcntl, "flock", None))
    lock_ex = cast(Any, getattr(fcntl, "LOCK_EX", None))
    if flock is None or lock_ex is None:
        raise RuntimeError("POSIX file locking is unavailable on this platform.")
    if timeout_seconds is None:
        flock(stream.fileno(), lock_ex)
        return
    lock_nb = cast(Any, getattr(fcntl, "LOCK_NB", None))
    if lock_nb is None:
        raise RuntimeError("nonblocking POSIX file locking is unavailable")
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            flock(stream.fileno(), lock_ex | lock_nb)
            return
        except OSError as error:
            if error.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "exclusive file lock acquisition timed out"
                ) from error
            time.sleep(_WINDOWS_LOCK_RETRY_SECONDS)


def _release_file_lock(stream: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    flock = cast(Any, getattr(fcntl, "flock", None))
    lock_un = cast(Any, getattr(fcntl, "LOCK_UN", None))
    if flock is None or lock_un is None:
        raise RuntimeError("POSIX file locking is unavailable on this platform.")
    flock(stream.fileno(), lock_un)
