"""Argument parsing and small command-normalization helpers."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Protocol

from ai4binance.cli.commands import available_command_names, canonical_command
from ai4binance.config import Settings
from ai4binance.external_intel.core.enums import MissionName
from ai4binance.schemas import MarketSnapshot

_INTERNAL_COMMAND_NAMES = ("virtual-market-daemon",)


class SnapshotAcquirer(Protocol):
    """Injectable public snapshot source used by CLI integration tests."""

    def acquire(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
    ) -> MarketSnapshot: ...


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "AI4Binance safe CLI. Use 'commands --format text' for a grouped "
            "command guide."
        )
    )
    parser.add_argument(
        "command",
        choices=(*available_command_names(), *_INTERNAL_COMMAND_NAMES),
    )
    parser.add_argument(
        "subject",
        nargs="?",
        help="Optional slash-command subject, for example '/scan spot'.",
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Set only the CLI confirmation gate; this command never submits orders.",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=("json", "text"),
        default="json",
        help="Render supported payload commands as JSON or a concise text summary.",
    )
    parser.add_argument(
        "--side", default=None, help="Spot order side for live preview."
    )
    parser.add_argument(
        "--order-type",
        default=None,
        help="Spot order type for live preview, for example LIMIT or MARKET.",
    )
    parser.add_argument(
        "--quantity",
        default=None,
        help="Base-asset quantity for explicit Spot live preview.",
    )
    parser.add_argument(
        "--price",
        default=None,
        help="Limit price for explicit Spot live preview.",
    )
    parser.add_argument(
        "--time-in-force",
        default=None,
        help="Limit time-in-force for explicit Spot live preview.",
    )
    parser.add_argument(
        "--client-order-id",
        default=None,
        help="Client order ID for explicit Spot live preview.",
    )
    parser.add_argument(
        "--authorization-id",
        default=None,
        help="Exact approved authorization envelope ID for Spot placement.",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Bound runtime-daemon cycles for diagnostics; omit for resident mode.",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help=(
            "Override the research validation symbol; validate-research defaults "
            "to BTCUSDT."
        ),
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Second-brain retrieval query.",
    )
    parser.add_argument(
        "--seed-url",
        action="append",
        default=[],
        help="Allowlisted HTTPS article URL for the Open Web Radar.",
    )
    parser.add_argument(
        "--mission",
        choices=tuple(item.value for item in MissionName),
        default="TECHNOLOGY_DEVELOPMENT",
        help="Open Web EIEF mission enum value.",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="Exclusive YYYY-MM-DD date for Binance Vision validation sync.",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Render the second-brain result as a local HTML UI document.",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Ask the loopback llama.cpp advisory runner after RAG retrieval.",
    )
    parser.add_argument(
        "--task",
        default=None,
        help="Task name to map to a governed agentic workflow pattern.",
    )
    parser.add_argument(
        "--risk-domain",
        default="general",
        help="Risk domain for agentic workflow selection.",
    )
    parser.add_argument(
        "--independent-checks",
        type=int,
        default=0,
        help="Number of independent checks available for parallel workflows.",
    )
    parser.add_argument(
        "--stages",
        type=int,
        default=0,
        help="Number of ordered stages available for prompt chaining.",
    )
    parser.add_argument(
        "--requires-human-review",
        action="store_true",
        help="Force a human-review workflow gate.",
    )
    parser.add_argument(
        "--needs-routing",
        action="store_true",
        help="Prefer routing when inputs need different paths.",
    )
    parser.add_argument(
        "--quality-sensitive",
        action="store_true",
        help="Prefer evaluator-optimizer when a rubric is required.",
    )
    parser.add_argument(
        "--bounded-actions",
        action="store_true",
        help="Mark the task as having bounded actions.",
    )
    parser.add_argument(
        "--downside-controlled",
        action="store_true",
        help="Mark the downside as controlled for autonomous workflow review.",
    )
    parser.add_argument(
        "--opposing-views",
        action="store_true",
        help="Prefer multi-agent debate for pressure testing.",
    )
    parser.add_argument(
        "--skills-root",
        default=None,
        help="Skill directory or directory containing skill folders.",
    )
    parser.add_argument(
        "--source-file",
        default=None,
        help="Offline JSON candidate file for skill-discovery commands.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=10,
        help="Maximum external skill discovery candidates per cycle.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.85,
        help="Minimum deterministic score for quarantined skill drafts.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=None,
        help="Skill discovery daemon interval; defaults to Settings.",
    )
    parser.add_argument(
        "--prompt-file",
        default=None,
        help="UTF-8 file containing raw prompt text for enterprise-intake.",
    )
    parser.add_argument(
        "--change-file",
        default=None,
        help="UTF-8 JSON OEK change manifest for oek-gap-analysis.",
    )
    parser.add_argument(
        "--security-evidence-file",
        default=None,
        help=(
            "UTF-8 JSON evidence bundle for security-weekly-deep-audit. "
            "Never include raw secrets."
        ),
    )
    parser.add_argument(
        "--approve-blocker-order",
        action="store_true",
        help=(
            "Record YKB approval for blocker-resolution ordering only; this does "
            "not approve risk, OOS, paper/live execution, or money movement."
        ),
    )
    parser.add_argument(
        "--inventory-units",
        default=None,
        help="Explicit base-asset units for recovery radar planning.",
    )
    parser.add_argument(
        "--range-low",
        default=None,
        help=(
            "Optional low price override for recovery radar. If omitted, the "
            "radar derives a technical support/resistance range when available."
        ),
    )
    parser.add_argument(
        "--range-high",
        default=None,
        help=(
            "Optional high price override for recovery radar. If omitted, the "
            "radar derives a technical support/resistance range when available."
        ),
    )
    parser.add_argument(
        "--cost-basis",
        default=None,
        help="Optional average cost basis for recovery radar review.",
    )
    return parser


def parse_arguments(arguments: Sequence[str] | None) -> argparse.Namespace:
    return build_parser().parse_args(arguments)


def normalize_slash_command(command: str, subject: str | None) -> str:
    return canonical_command(command, subject)


def normalize_cli_symbol(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized or not normalized.isalnum():
        raise ValueError("symbol override must be alphanumeric")
    return normalized


def parse_as_of(value: str | None) -> date:
    if value is None:
        return datetime.now(UTC).date()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("--as-of must be YYYY-MM-DD") from None


def safe_validation_symbol(value: str | None, settings: Settings) -> str:
    try:
        return normalize_cli_symbol(value) or settings.validation_symbol
    except ValueError:
        return settings.validation_symbol


__all__ = (
    "SnapshotAcquirer",
    "build_parser",
    "normalize_cli_symbol",
    "normalize_slash_command",
    "parse_arguments",
    "parse_as_of",
    "safe_validation_symbol",
)
