"""Cross-platform exclusive file locking for local event persistence."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, cast


@contextmanager
def exclusive_file_lock(path: Path) -> Iterator[None]:
    """Hold one exclusive byte-range lock for the supplied lock file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        _acquire_file_lock(stream)
        try:
            yield
        finally:
            _release_file_lock(stream)


def _acquire_file_lock(stream: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        return

    import fcntl

    flock = cast(Any, getattr(fcntl, "flock", None))
    lock_ex = cast(Any, getattr(fcntl, "LOCK_EX", None))
    if flock is None or lock_ex is None:
        raise RuntimeError("POSIX file locking is unavailable on this platform.")
    flock(stream.fileno(), lock_ex)


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
