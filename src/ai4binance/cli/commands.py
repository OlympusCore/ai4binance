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
        "system-report",
        "core",
        "Build a secret-safe whole-system operator report.",
        examples=("system-report --format text",),
    ),
    CliCommandSpec(
        "auto-audit-once",
        "core",
        "Run one report-only auto-audit cycle with optional local Qwen review.",
        aliases=("auto-audit",),
        examples=("auto-audit-once --llm --format text",),
    ),
    CliCommandSpec(
        "auto-audit-daemon",
        "core",
        "Run bounded report-only auto-audit cycles while the session is active.",
        examples=("auto-audit-daemon --max-cycles 3 --interval-seconds 300",),
    ),
    CliCommandSpec(
        "security-weekly-deep-audit",
        "core",
        (
            "Run the report-only EAACIE weekly deep security audit with SBOM, "
            "CVE evidence, MFA, restore, WORM and scheduler checks."
        ),
        aliases=("security-deep-audit",),
        examples=(
            "security-weekly-deep-audit --security-evidence-file "
            "runtime/artifacts/assurance/security/security-evidence.json --format text",
        ),
    ),
    CliCommandSpec(
        "ykb-report",
        "core",
        (
            "Build a YKB-friendly executive brief from auto-audit, DGE, "
            "opportunities and financial context."
        ),
        aliases=("ykb-brief",),
        examples=("ykb-report --llm --format text",),
    ),
    CliCommandSpec(
        "vnext-gap-audit",
        "core",
        "Map the EnterpriseAI vNext v1.1 target architecture to local evidence.",
        aliases=("vnext-audit", "gap-audit"),
        examples=("vnext-gap-audit --format text",),
    ),
    CliCommandSpec(
        "opportunity-recovery-radar",
        "portfolio",
        (
            "Build a recovery-mode candidate ladder from inventory, range and "
            "opportunity evidence."
        ),
        aliases=("recovery-radar", "candidate-ladder"),
        examples=(
            "opportunity-recovery-radar --symbol HOTUSDT --inventory-units "
            "18400000 --format text",
            "opportunity-recovery-radar --symbol HOTUSDT --inventory-units "
            "18400000 --range-low 0.000312 --range-high 0.000390 --format text",
        ),
    ),
    CliCommandSpec(
        "dge-rules",
        "governance",
        "List centralized DGE rule metadata without changing policy.",
        examples=("dge-rules --format text",),
    ),
    CliCommandSpec(
        "dge-replay",
        "governance",
        "Replay a persisted DGE decision record by decision id.",
        examples=("dge-replay dge:abc123 --format text",),
    ),
    CliCommandSpec(
        "dge-shadow-rules",
        "governance",
        "Show DGE shadow-rule mode and live-safe promotion blockers.",
        examples=("dge-shadow-rules --format text",),
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
        "skills-audit",
        "governance",
        "Audit repo-local Agent Skills without installing or executing them.",
        examples=(
            "skills-audit --format text",
            "skills-audit --skills-root .agents/skills",
        ),
    ),
    CliCommandSpec(
        "skill-discovery-once",
        "governance",
        "Run one quarantine-first external Agent Skill discovery cycle.",
        examples=(
            "skill-discovery-once --max-candidates 3 --format text",
            "skill-discovery-once --source-file candidates.json",
        ),
    ),
    CliCommandSpec(
        "skill-discovery-daemon",
        "governance",
        "Run continuous skill discovery while the computer session is active.",
        examples=("skill-discovery-daemon --max-cycles 1",),
    ),
    CliCommandSpec(
        "skill-discovery-status",
        "governance",
        "Read the last continuous skill discovery state.",
        examples=("skill-discovery-status --format text",),
    ),
    CliCommandSpec(
        "privacy-boundary",
        "governance",
        (
            "Scan for local profile details copied outside "
            "docs/archive/reference_local_computer_profile.md."
        ),
        examples=("privacy-boundary --format text",),
    ),
    CliCommandSpec(
        "enterprise-intake",
        "governance",
        "Convert a raw prompt file into a General Manager summary-only directive.",
        examples=("enterprise-intake --prompt-file prompt.txt",),
    ),
    CliCommandSpec(
        "quality-system-audit",
        "governance",
        "Run the QAQC enterprise system audit.",
        aliases=("qaqc-audit",),
        examples=("qaqc-audit --format text", "quality-system-audit --format text"),
    ),
    CliCommandSpec(
        "agent-stack-audit",
        "governance",
        "Audit the governed modern AI agent stack.",
        examples=("agent-stack-audit --format text",),
    ),
    CliCommandSpec(
        "oek-gap-analysis",
        "governance",
        "Check an agent, skill, workflow, or config change against the OEK.",
        aliases=("oek-audit",),
        examples=(
            "oek-gap-analysis --change-file artifacts/oek-change.json",
            "oek-audit --change-file artifacts/oek-change.json --format text",
        ),
    ),
    CliCommandSpec(
        "repository-cleanup-audit",
        "governance",
        "Run the report-only repository cleanup and stability audit.",
        aliases=("cleanup-audit",),
        examples=(
            "repository-cleanup-audit --format text",
            "cleanup-audit --format json",
        ),
    ),
    CliCommandSpec(
        "virtual-market-paper-soak",
        "validation",
        "Build a fail-closed virtual-market paper-soak readiness artifact.",
        aliases=("paper-soak-readiness",),
        examples=("virtual-market-paper-soak --format text",),
    ),
    CliCommandSpec(
        "virtual-market-retrieval-eval",
        "validation",
        "Evaluate virtual-market retrieval evidence quality.",
        examples=("virtual-market-retrieval-eval --query BTCUSDT --format text",),
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
        "external-intel",
        "market-research",
        (
            "Run the report-only External Intelligence & Evidence Fabric MVP "
            "with fail-closed radar outputs."
        ),
        aliases=("eief",),
        examples=(
            "external-intel --symbol HOTUSDT --format text",
            "eief --format json",
        ),
    ),
    CliCommandSpec(
        "external-intel-universe",
        "market-research",
        "Show the EIEF opportunity universe classification smoke snapshot.",
        aliases=("eief-universe",),
        examples=("external-intel-universe --format json",),
    ),
    CliCommandSpec(
        "external-intel-open-web",
        "market-research",
        (
            "Retrieve allowlisted public web evidence without credentialed "
            "search or cloud LLM tokens."
        ),
        aliases=("open-web-radar",),
        examples=(
            "external-intel-open-web --format json",
            "open-web-radar --seed-url https://github.blog/example/",
        ),
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
        "backtest-runtime-economics",
        "validation",
        "Review local backtest runtime economics and CUDA readiness.",
        examples=("backtest-runtime-economics --format text",),
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
        "runtime-research-refresh-once",
        "runtime",
        (
            "Refresh internet research feeds, run runtime-once, and publish a "
            "trace-validation report."
        ),
        aliases=("runtime-refresh",),
    ),
    CliCommandSpec(
        "runtime-daemon",
        "runtime",
        "Run the read-only runtime daemon.",
    ),
    CliCommandSpec(
        "virtual-market-once",
        "runtime",
        "Run one bounded virtual-market simulation probe.",
        aliases=("virtual-runtime-once", "virtual-runtime"),
        examples=("virtual-market-once --format text",),
    ),
    CliCommandSpec(
        "virtual-market-soak",
        "runtime",
        "Write a bounded virtual-market boundary-soak artifact.",
        aliases=("virtual-runtime-soak",),
        examples=("virtual-market-soak --format text",),
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
