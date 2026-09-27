"""Stable JSON-compatible serialization for immutable audit contracts."""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import cast


def to_primitive(value: object) -> object:
    """Convert domain objects to deterministic JSON-compatible primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: to_primitive(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {
            str(key): to_primitive(item)
            for key, item in sorted(mapping.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset)):
        return [to_primitive(item) for item in sorted(value, key=repr)]
    if isinstance(value, (list, tuple)):
        return [to_primitive(item) for item in value]
    raise TypeError(f"unsupported audit value type: {type(value).__name__}")
