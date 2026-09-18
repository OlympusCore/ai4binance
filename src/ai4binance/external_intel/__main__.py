"""Standalone report-only EIEF CLI."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from ai4binance.external_intel.cli.commands import (
    external_intel_payload,
    external_intel_universe_payload,
    open_web_payload,
)
from ai4binance.external_intel.core.enums import MissionName


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI4BINANCE EIEF report-only CLI.")
    parser.add_argument(
        "command",
        choices=(
            "scan",
            "radar-status",
            "risk",
            "daily",
            "universe",
            "opportunity",
            "technology",
            "open-web",
        ),
    )
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--topic", default=None)
    parser.add_argument(
        "--mission",
        choices=tuple(item.value for item in MissionName),
        default=MissionName.TECHNOLOGY_DEVELOPMENT.value,
    )
    parser.add_argument("--seed-url", action="append", default=[])
    parsed = parser.parse_args(arguments)
    if parsed.command == "universe":
        payload = external_intel_universe_payload()
    elif parsed.command == "open-web":
        payload = open_web_payload(
            mission=MissionName(parsed.mission),
            seed_urls=tuple(parsed.seed_url),
        )
    else:
        payload = external_intel_payload(
            command=f"external-intel-{parsed.command}",
            symbol=parsed.symbol,
            topic=parsed.topic,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
