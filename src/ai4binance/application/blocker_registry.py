"""Load the governed blocker configuration for application evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml

from ai4binance.domain.blockers import BlockerRegistry, blocker_registry_from_payload


def load_blocker_registry(path: Path) -> BlockerRegistry:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("blocker registry must be a mapping")
    return blocker_registry_from_payload(cast(Mapping[str, Any], payload))
