"""User-facing CLI command catalog and alias resolution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CliCommandSpec:
    canonical: str
    group: str
    summary: str
    aliases: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


COMMAND_SPECS: tuple[CliCommandSpec, ...] = (
    CliCommandSpec(
        "status",
        "core",
        "Print the fail-closed default trading status.",
        aliases=("summary",),
        examples=("status", "summary --format text"),
    ),
    CliCommandSpec(
        "commands",
        "core",
        "List command groups, aliases, and examples.",
        aliases=("help",),
        examples=("commands", "help validation"),
    ),
    CliCommandSpec(
        "agents",
        "governance",
        "List governed advisory agents and live-authority counts.",
    ),
    CliCommandSpec(
        "agentic-skills",
        "governance",
        "Recommend a governed workflow pattern for a bounded task.",
    ),
    CliCommandSpec(
        "lean-governance",
        "governance",
        "Review operational excellence guardrails.",
    ),
    CliCommandSpec(
        "qaqc-agent",
        "governance",
        "Show the QAQC-Agent governance review.",
    ),
    CliCommandSpec(
        "analyze-public",
        "market-research",
        "Acquire public Spot data and produce a deterministic NO_TRADE analysis.",
    ),
    CliCommandSpec(
        "research-public",
        "market-research",
        "Run the safe public research workflow.",
        aliases=("research",),
    ),
    CliCommandSpec(
        "archive-public",
        "market-research",
        "Archive public market candles without wallet contamination.",
    ),
    CliCommandSpec(
        "whale-fusion-research",
        "market-research",
        "Run whale-fusion research with provider blockers surfaced.",
    ),
    CliCommandSpec(
        "second-brain",
        "market-research",
        "Search the local second-brain evidence index.",
    ),
    CliCommandSpec(
        "sync-validation-data",
        "validation",
        "Sync Binance Vision validation data for the validation symbol.",
    ),
    CliCommandSpec(
        "validate-research",
        "validation",
        "Run validation research gates.",
        aliases=("validate",),
    ),
    CliCommandSpec(
        "validation-summary",
        "validation",
        "Summarize persisted validation run cards.",
        aliases=("backtests",),
        examples=("validation-summary --symbol HOTUSDT", "backtests --format text"),
    ),
    CliCommandSpec(
        "backtest-results",
        "validation",
        "Compatibility alias for validation-summary output.",
    ),
    CliCommandSpec(
        "crew-plan",
        "validation",
        "Show the governed validation crew plan.",
    ),
    CliCommandSpec(
        "portfolio",
        "portfolio",
        "Show read-only portfolio/account snapshot status.",
        aliases=("/portfolio",),
    ),
    CliCommandSpec(
        "opportunities",
        "portfolio",
        "Show visible research opportunities and execution blockers.",
        aliases=("/opportunities", "ops"),
        examples=("opportunities --symbol HOTUSDT", "ops --format text"),
    ),
    CliCommandSpec(
        "manual-actions",
        "portfolio",
        "Show pending manual actions.",
        aliases=("/manual-actions",),
    ),
    CliCommandSpec(
        "approvals",
        "portfolio",
        "Show recorded manual approvals.",
        aliases=("/approvals",),
    ),
    CliCommandSpec(
        "scan-spot",
        "portfolio",
        "Scan configured Spot watch symbols with explicit blockers.",
        aliases=("scan",),
        examples=("scan spot", "/scan spot", "scan-spot"),
    ),
    CliCommandSpec(
        "scan-futures",
        "portfolio",
        "Scan configured USD-M Futures watch symbols as research-only evidence.",
        examples=("scan futures", "/scan futures", "scan-futures"),
    ),
    CliCommandSpec(
        "scan-all",
        "portfolio",
        "Scan configured Spot and USD-M Futures watch symbols.",
        examples=("scan all", "/scan all", "scan-all"),
    ),
    CliCommandSpec(
        "runtime-once",
        "runtime",
        "Run one read-only runtime cycle.",
    ),
    CliCommandSpec(
        "runtime-daemon",
        "runtime",
        "Run the read-only runtime daemon.",
    ),
    CliCommandSpec(
        "voice-once",
        "runtime",
        "Run one voice assistant cycle.",
    ),
    CliCommandSpec(
        "voice-daemon",
        "runtime",
        "Run the voice assistant daemon.",
    ),
    CliCommandSpec(
        "accounting-collect-once",
        "accounting",
        "Collect one read-only accounting REST snapshot.",
    ),
    CliCommandSpec(
        "accounting-collect-daemon",
        "accounting",
        "Run the read-only accounting REST daemon.",
    ),
    CliCommandSpec(
        "accounting-ws-once",
        "accounting",
        "Collect one read-only accounting WebSocket snapshot.",
    ),
    CliCommandSpec(
        "accounting-ws-daemon",
        "accounting",
        "Run the read-only accounting WebSocket daemon.",
    ),
    CliCommandSpec(
        "accounting-reconcile-once",
        "accounting",
        "Run one accounting reconciliation pass.",
    ),
    CliCommandSpec(
        "accounting-ui-report",
        "accounting",
        "Build the local accounting UI report.",
    ),
    CliCommandSpec(
        "accounting-status",
        "accounting",
        "Show accounting file freshness and reconciliation status.",
    ),
    CliCommandSpec(
        "live-preview-spot",
        "live-spot",
        "Create a Spot order preview hash without authority.",
        aliases=("live-preview",),
    ),
    CliCommandSpec(
        "live-place-spot",
        "live-spot",
        "Place an exact approved Spot preview only after all live gates pass.",
        aliases=("live-place",),
    ),
)


def command_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for spec in COMMAND_SPECS:
        aliases[spec.canonical] = spec.canonical
        for alias in spec.aliases:
            aliases[alias] = spec.canonical
    aliases["/scan"] = "scan"
    return aliases


def available_command_names() -> tuple[str, ...]:
    return tuple(dict.fromkeys(command_aliases()))


def canonical_command(command: str, subject: str | None = None) -> str:
    if command in {"scan", "/scan"}:
        return _canonical_scan_subject(subject)
    return command_aliases().get(command, command)


def _canonical_scan_subject(subject: str | None) -> str:
    normalized_subject = (subject or "spot").strip().casefold()
    if normalized_subject == "spot":
        return "scan-spot"
    if normalized_subject == "futures":
        return "scan-futures"
    if normalized_subject == "all":
        return "scan-all"
    return "scan-unknown"


def command_catalog_payload(topic: str | None = None) -> dict[str, object]:
    selected = _select_specs(topic)
    groups: dict[str, list[dict[str, object]]] = {}
    for spec in selected:
        groups.setdefault(spec.group, []).append(
            {
                "command": spec.canonical,
                "summary": spec.summary,
                "aliases": spec.aliases,
                "examples": spec.examples,
            }
        )
    return {
        "command": "commands",
        "topic": topic,
        "groups": groups,
        "command_count": len(selected),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "blockers": (),
    }


def _select_specs(topic: str | None) -> tuple[CliCommandSpec, ...]:
    if topic is None or not topic.strip():
        return COMMAND_SPECS
    normalized = topic.strip().casefold()
    canonical = command_aliases().get(normalized, normalized)
    return tuple(
        spec
        for spec in COMMAND_SPECS
        if spec.group == normalized or spec.canonical == canonical
    )
