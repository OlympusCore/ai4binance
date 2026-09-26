"""Core contracts and deterministic domain boundaries."""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

_TAIL_READ_CHUNK_BYTES = 64 * 1024
_DEFAULT_MAX_TAIL_BYTES = 16 * 1024 * 1024


def read_bounded_jsonl_tail(
    path: Path,
    *,
    max_lines: int = 200,
    max_bytes: int = _DEFAULT_MAX_TAIL_BYTES,
) -> tuple[bytes, ...]:
    """Read recent complete non-empty JSONL records without whole-file loading."""
    if max_lines < 1 or max_bytes < 1:
        raise ValueError("JSONL tail limits must be positive")
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        end = _trim_trailing_whitespace(stream, stream.tell())
        cursor = end
        buffer = b""
        while cursor > 0:
            start = max(0, cursor - _TAIL_READ_CHUNK_BYTES)
            starts_at_record_boundary = start == 0
            if start > 0:
                stream.seek(start - 1)
                previous = stream.read(1)
                stream.seek(start)
                current = stream.read(1)
                starts_at_record_boundary = previous in b"\r\n" or current in b"\r\n"
            stream.seek(start)
            buffer = stream.read(cursor - start) + buffer
            if len(buffer) > max_bytes:
                raise OSError("JSONL tail exceeds bounded read limit")
            lines = tuple(line for line in buffer.splitlines() if line.strip())
            if lines and not starts_at_record_boundary:
                lines = lines[1:]
            if len(lines) >= max_lines or start == 0:
                return lines[-max_lines:]
            cursor = start
    return ()


def _trim_trailing_whitespace(stream: BinaryIO, end: int) -> int:
    while end > 0:
        start = max(0, end - _TAIL_READ_CHUNK_BYTES)
        stream.seek(start)
        block = stream.read(end - start)
        stripped = block.rstrip(b" \t\r\n")
        if stripped:
            return start + len(stripped)
        end = start
    return 0
