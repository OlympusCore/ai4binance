"""Governed coverage policy evaluation for quality-gate evidence."""

from __future__ import annotations

import argparse
import fnmatch
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml

from ai4binance.governance.architecture import (
    LogicalArchitectureRegistry,
    load_logical_architecture_registry,
)
from ai4binance.ops.coverage_architecture import (
    CoverageArchitectureConfig,
    CoverageArchitectureReport,
    evaluate_coverage_architecture,
    load_coverage_architecture_config,
)
from ai4binance.reporting import to_primitive

_VALID_ENFORCEMENT_MODES = frozenset({"baseline_migration", "enforced"})
_POLICY_STATES = frozenset(
    {
        "BELOW_POLICY",
        "IMPROVEMENT_REQUIRED",
        "PASS",
        "NOT_MEASURED",
        "COVERAGE_SCOPE_CONFLICT",
    }
)


@dataclass(frozen=True, slots=True)
class CoverageFamilyConfig:
    """Path ownership definition for one governed coverage family."""

    name: str
    description: str
    include: tuple[str, ...]
    exclude: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier("coverage family", self.name)
        _require_text("coverage family description", self.description)
        _require_patterns("coverage include patterns", self.include, allow_empty=False)
        _require_patterns("coverage exclude patterns", self.exclude, allow_empty=True)


@dataclass(frozen=True, slots=True)
class CoveragePolicyConfig:
    """Machine-readable coverage policy configuration."""

    policy_id: str
    governed_minimum: float
    remediation_trigger: float
    enforcement_mode: str
    branch_minimum: float
    families: tuple[CoverageFamilyConfig, ...]
    architecture_assurance: CoverageArchitectureConfig | None = None

    def __post_init__(self) -> None:
        _require_text("coverage policy id", self.policy_id)
        _require_percent("governed_minimum", self.governed_minimum)
        _require_percent("remediation_trigger", self.remediation_trigger)
        _require_percent("branch_minimum", self.branch_minimum)
        if self.remediation_trigger > self.governed_minimum:
            raise ValueError("remediation_trigger cannot exceed governed_minimum")
        if self.enforcement_mode not in _VALID_ENFORCEMENT_MODES:
            raise ValueError("coverage enforcement_mode is invalid")
        if not self.families:
            raise ValueError("coverage policy requires at least one family")
        family_names = tuple(family.name for family in self.families)
        if len(set(family_names)) != len(family_names):
            raise ValueError("coverage families must be unique")


@dataclass(frozen=True, slots=True)
class FileCoverage:
    """Coverage.py file summary normalized for policy evaluation."""

    path: str
    statements: int
    covered_lines: int
    missing_lines: int
    branches: int
    covered_branches: int
    missing_branches: int
    percent_covered: float

    def __post_init__(self) -> None:
        _require_text("coverage file path", self.path)
        for label, value in (
            ("statements", self.statements),
            ("covered_lines", self.covered_lines),
            ("missing_lines", self.missing_lines),
            ("branches", self.branches),
            ("covered_branches", self.covered_branches),
            ("missing_branches", self.missing_branches),
        ):
            if value < 0:
                raise ValueError(f"{label} cannot be negative")
        _require_percent("percent_covered", self.percent_covered)


@dataclass(frozen=True, slots=True)
class CoverageFamilyResult:
    """Policy outcome for one governed coverage family."""

    target: str
    coverage_family: str
    source_paths: tuple[str, ...]
    statement_coverage: float | None
    branch_coverage: float | None
    covered_lines: int
    missing_lines: int
    covered_branches: int
    missing_branches: int
    policy_threshold: float
    coverage_gap: float
    policy_state: str

    def __post_init__(self) -> None:
        _require_identifier("coverage target", self.target)
        _require_identifier("coverage family", self.coverage_family)
        if self.policy_state not in _POLICY_STATES:
            raise ValueError("coverage policy_state is invalid")
        if self.statement_coverage is not None:
            _require_percent("statement_coverage", self.statement_coverage)
        if self.branch_coverage is not None:
            _require_percent("branch_coverage", self.branch_coverage)
        _require_percent("policy_threshold", self.policy_threshold)


@dataclass(frozen=True, slots=True)
class CoveragePolicySummary:
    """Complete governed coverage policy summary."""

    policy_id: str
    generated_at_utc: datetime
    total_coverage_percent: float | None
    coverage_source: str
    enforcement_mode: str
    governed_minimum: float
    remediation_trigger: float
    branch_minimum: float
    target_results: tuple[CoverageFamilyResult, ...]
    policy_failures: tuple[str, ...]
    not_measured: tuple[str, ...]
    coverage_scope_conflicts: tuple[str, ...]
    policy_result: str
    architecture_assurance: CoverageArchitectureReport | None = None
    architecture_failures: tuple[str, ...] = ()
    critical_behavior_failures: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("coverage policy id", self.policy_id)
        _require_text("coverage source", self.coverage_source)
        if self.total_coverage_percent is not None:
            _require_percent("total_coverage_percent", self.total_coverage_percent)
        _require_percent("branch_minimum", self.branch_minimum)
        if self.enforcement_mode not in _VALID_ENFORCEMENT_MODES:
            raise ValueError("coverage enforcement_mode is invalid")
        if self.policy_result not in {
            "PASS",
            "BASELINE_DEBT",
            "FAIL",
            "COVERAGE_SCOPE_CONFLICT",
        }:
            raise ValueError("coverage policy_result is invalid")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("coverage policy summary cannot authorize execution")

    def to_payload(self) -> dict[str, object]:
        return cast(dict[str, object], to_primitive(self))


def load_coverage_policy_config(path: Path) -> CoveragePolicyConfig:
    """Load and validate the governed coverage target configuration."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("coverage target config must be a mapping")
    policy = _mapping(payload.get("coverage_policy"), "coverage_policy")
    families_payload = _mapping(payload.get("families"), "families")
    families = tuple(
        CoverageFamilyConfig(
            name=str(name),
            description=str(_mapping(value, f"families.{name}").get("description", "")),
            include=_strings(
                _mapping(value, f"families.{name}").get("include"),
                f"families.{name}.include",
            ),
            exclude=_strings(
                _mapping(value, f"families.{name}").get("exclude", ()),
                f"families.{name}.exclude",
            ),
        )
        for name, value in families_payload.items()
    )
    return CoveragePolicyConfig(
        policy_id=str(policy.get("policy_id", "")),
        governed_minimum=float(policy.get("governed_minimum", -1.0)),
        remediation_trigger=float(policy.get("remediation_trigger", -1.0)),
        enforcement_mode=str(policy.get("enforcement_mode", "")),
        branch_minimum=float(policy.get("branch_minimum", -1.0)),
        families=families,
        architecture_assurance=load_coverage_architecture_config(
            payload.get("architecture_assurance")
        ),
    )


def load_file_coverage(path: Path) -> tuple[FileCoverage, ...]:
    """Load file-level coverage summaries from a coverage.py JSON artifact."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    files = _mapping(payload.get("files"), "coverage.files")
    rows: list[FileCoverage] = []
    for raw_path, raw_file in files.items():
        if not raw_path:
            continue
        file_payload = _mapping(raw_file, f"coverage.files.{raw_path}")
        summary = _mapping(
            file_payload.get("summary"), f"coverage.files.{raw_path}.summary"
        )
        statements = int(summary.get("num_statements", 0))
        missing_lines = int(summary.get("missing_lines", 0))
        branches = int(summary.get("num_branches", 0))
        missing_branches = int(summary.get("missing_branches", 0))
        rows.append(
            FileCoverage(
                path=_normalize_path(str(raw_path)),
                statements=statements,
                covered_lines=max(0, statements - missing_lines),
                missing_lines=missing_lines,
                branches=branches,
                covered_branches=max(0, branches - missing_branches),
                missing_branches=missing_branches,
                percent_covered=round(float(summary.get("percent_covered", 0.0)), 2),
            )
        )
    return tuple(rows)


def load_total_coverage_percent(path: Path) -> float:
    """Load total statement coverage from a coverage.py JSON artifact."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    totals = _mapping(payload.get("totals"), "coverage.totals")
    return round(float(totals.get("percent_covered", -1.0)), 2)


def evaluate_coverage_policy(
    config: CoveragePolicyConfig,
    file_coverage: tuple[FileCoverage, ...],
    *,
    total_coverage_percent: float | None = None,
    coverage_source: str = "coverage.py json totals.percent_covered",
    architecture_registry: LogicalArchitectureRegistry | None = None,
    repository_root: Path | None = None,
    coverage_generated_at: datetime | None = None,
    generated_at: datetime | None = None,
) -> CoveragePolicySummary:
    """Evaluate governed coverage families from current coverage evidence."""
    ownership: dict[str, list[str]] = {}
    results: list[CoverageFamilyResult] = []
    for family in config.families:
        matched = tuple(
            row for row in file_coverage if _matches_family(row.path, family)
        )
        for row in matched:
            ownership.setdefault(row.path, []).append(family.name)
        results.append(_family_result(config, family, matched))

    conflicts = tuple(
        f"{path}:{','.join(sorted(families))}"
        for path, families in sorted(ownership.items())
        if len(set(families)) > 1
    )
    if conflicts:
        results = [
            CoverageFamilyResult(
                target=result.target,
                coverage_family=result.coverage_family,
                source_paths=result.source_paths,
                statement_coverage=result.statement_coverage,
                branch_coverage=result.branch_coverage,
                covered_lines=result.covered_lines,
                missing_lines=result.missing_lines,
                covered_branches=result.covered_branches,
                missing_branches=result.missing_branches,
                policy_threshold=result.policy_threshold,
                coverage_gap=result.coverage_gap,
                policy_state="COVERAGE_SCOPE_CONFLICT",
            )
            for result in results
        ]

    ordered = tuple(
        sorted(
            results,
            key=lambda result: (
                101.0
                if result.statement_coverage is None
                else result.statement_coverage,
                -result.missing_branches,
                -result.missing_lines,
                result.target,
            ),
        )
    )
    policy_failures = tuple(
        result.target
        for result in ordered
        if result.policy_state in {"BELOW_POLICY", "IMPROVEMENT_REQUIRED"}
    )
    not_measured = tuple(
        result.target for result in ordered if result.policy_state == "NOT_MEASURED"
    )
    architecture_assurance = None
    if config.architecture_assurance is not None and architecture_registry is not None:
        if repository_root is None:
            raise ValueError(
                "repository_root is required for architecture assurance evaluation"
            )
        architecture_assurance = evaluate_coverage_architecture(
            config.architecture_assurance,
            architecture_registry,
            file_coverage,
            repository_root=repository_root,
            coverage_generated_at=coverage_generated_at,
            generated_at=generated_at,
        )
    architecture_failures = (
        architecture_assurance.architecture_failures
        if architecture_assurance is not None
        else ()
    )
    critical_behavior_failures = (
        architecture_assurance.critical_behavior_failures
        if architecture_assurance is not None
        else ()
    )
    policy_result = _policy_result(
        config,
        policy_failures,
        not_measured,
        conflicts,
        architecture_failures,
        critical_behavior_failures,
    )
    return CoveragePolicySummary(
        policy_id=config.policy_id,
        generated_at_utc=generated_at or datetime.now(UTC),
        total_coverage_percent=total_coverage_percent,
        coverage_source=coverage_source,
        enforcement_mode=config.enforcement_mode,
        governed_minimum=config.governed_minimum,
        remediation_trigger=config.remediation_trigger,
        branch_minimum=config.branch_minimum,
        target_results=ordered,
        policy_failures=policy_failures,
        not_measured=not_measured,
        coverage_scope_conflicts=conflicts,
        policy_result=policy_result,
        architecture_assurance=architecture_assurance,
        architecture_failures=architecture_failures,
        critical_behavior_failures=critical_behavior_failures,
    )


def write_coverage_policy_outputs(
    summary: CoveragePolicySummary,
    *,
    json_path: Path,
    markdown_path: Path,
) -> None:
    """Persist machine-readable and reader-readable coverage policy evidence."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(summary.to_payload(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(summary), encoding="utf-8")


def render_markdown(summary: CoveragePolicySummary) -> str:
    """Render a concise coverage policy report."""
    total_coverage = (
        "UNAVAILABLE"
        if summary.total_coverage_percent is None
        else f"{summary.total_coverage_percent:.2f}%"
    )
    lines = [
        "---",
        "document_id: AI4B-QUALITY-EVID-COVERAGE-REALISM-001",
        "title: AI4BINANCE Coverage Realism Evidence Paper",
        "document_type: EVIDENCE",
        "version: 1.0.0",
        "status: GENERATED",
        "owner: Quality Governance",
        "authority_level: EVIDENCE",
        "content_role: QUALITY_EVIDENCE",
        "source_of_truth: false",
        "machine_enforceable: true",
        "audit_required: true",
        "classification: INTERNAL",
        "generated_by: ai4binance.ops.coverage_policy",
        "policy_ref: docs/policies/quality/coverage_improvement_strategy_policy.md",
        "---",
        "",
        "# AI4BINANCE Coverage Policy Summary",
        "",
        "## ELI10",
        "",
        "This report ranks governed coverage families from weakest to strongest.",
        "Coverage debt stays visible and cannot grant trading authority.",
        "",
        "## Summary",
        "",
        f"- Policy id: `{summary.policy_id}`",
        f"- Generated at UTC: `{summary.generated_at_utc.isoformat()}`",
        f"- Total coverage: `{total_coverage}`",
        f"- Coverage source: `{summary.coverage_source}`",
        f"- Enforcement mode: `{summary.enforcement_mode}`",
        f"- Governed minimum: `{summary.governed_minimum:.2f}%`",
        f"- Branch minimum: `{summary.branch_minimum:.2f}%`",
        f"- Remediation trigger: `{summary.remediation_trigger:.2f}%`",
        f"- Policy result: `{summary.policy_result}`",
        f"- Architecture gaps: `{len(summary.architecture_failures)}`",
        f"- Critical behavior gaps: `{len(summary.critical_behavior_failures)}`",
        f"- Execution allowed: `{summary.execution_allowed}`",
        f"- Live eligibility: `{summary.live_eligibility_status}`",
        "",
        "## Priority",
        "",
        "| Rank | Family | Statement coverage | Branch coverage | Gap to policy | "
        "Missing lines | Missing branches | State |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for rank, result in enumerate(summary.target_results, start=1):
        coverage = (
            "NOT_MEASURED"
            if result.statement_coverage is None
            else f"{result.statement_coverage:.2f}%"
        )
        branch_coverage = (
            "NOT_MEASURED"
            if result.branch_coverage is None
            else f"{result.branch_coverage:.2f}%"
        )
        lines.append(
            "| "
            f"{rank} | {result.coverage_family} | {coverage} | "
            f"{branch_coverage} | {result.coverage_gap:.2f} | "
            f"{result.missing_lines} | "
            f"{result.missing_branches} | {result.policy_state} |"
        )
    lines.extend(
        [
            "",
            "## Realism Proof",
            "",
            "- Coverage percentage is read from the current coverage.py JSON "
            "`totals.percent_covered` field.",
            "- Governed family rows are calculated from current coverage.py JSON "
            "file summaries.",
            "- `NOT_MEASURED` remains unavailable evidence and is not converted "
            "into a fake zero.",
            "- Focused pytest output, cached terminal text, and stale markdown are "
            "not valid coverage-percentage sources.",
            "",
            "## Safety",
            "",
            "Coverage is quality evidence only. It does not authorize live orders, "
            "risk-limit changes, strategy promotion, or execution authority.",
            "",
        ]
    )
    if summary.architecture_assurance is not None:
        lines.extend(
            [
                "## Architecture Assurance",
                "",
                "| Target | Tier | Component | Statement | Branch | "
                "Relations | Runtime evidence | State |",
                "| --- | --- | --- | ---: | ---: | --- | --- | --- |",
            ]
        )
        for row in summary.architecture_assurance.architecture_view:
            statement = (
                "NOT_MEASURED"
                if row.statement_coverage is None
                else f"{row.statement_coverage:.2f}%"
            )
            branch = (
                "N/A" if row.branch_coverage is None else f"{row.branch_coverage:.2f}%"
            )
            lines.append(
                f"| {row.target} | {row.tier} | {row.component_id or 'NOT_DECLARED'} "
                f"| {statement} | {branch} | {row.relation_status} | "
                f"{row.runtime_evidence} | {row.state} |"
            )
        lines.extend(
            [
                "",
                "## Critical Behavior Assurance",
                "",
                "| Obligation | Category | Component | Covered | Asserted | "
                "Runtime proven | State |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for behavior_row in summary.architecture_assurance.critical_behavior_view:
            lines.append(
                f"| {behavior_row.obligation_id} | {behavior_row.category} | "
                f"{behavior_row.component_id} | {behavior_row.covered} | "
                f"{behavior_row.asserted} | {behavior_row.runtime_proven} | "
                f"{behavior_row.state} |"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint used by the local quality gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-json", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-markdown", required=True, type=Path)
    args = parser.parse_args(argv)

    config = load_coverage_policy_config(args.config)
    coverage_generated_at = datetime.fromtimestamp(
        args.coverage_json.stat().st_mtime,
        UTC,
    )
    architecture_registry = None
    repository_root = Path.cwd()
    if config.architecture_assurance is not None:
        architecture_registry = load_logical_architecture_registry(
            repository_root / config.architecture_assurance.registry_path,
            schema_root=repository_root / "schemas",
        )
    summary = evaluate_coverage_policy(
        config,
        load_file_coverage(args.coverage_json),
        total_coverage_percent=load_total_coverage_percent(args.coverage_json),
        architecture_registry=architecture_registry,
        repository_root=repository_root,
        coverage_generated_at=coverage_generated_at,
    )
    write_coverage_policy_outputs(
        summary,
        json_path=args.output_json,
        markdown_path=args.output_markdown,
    )
    print(f"Coverage policy result: {summary.policy_result}")
    if summary.policy_result in {"COVERAGE_SCOPE_CONFLICT", "FAIL"}:
        return 1
    return 0


def _family_result(
    config: CoveragePolicyConfig,
    family: CoverageFamilyConfig,
    files: tuple[FileCoverage, ...],
) -> CoverageFamilyResult:
    if not files:
        return CoverageFamilyResult(
            target=family.name,
            coverage_family=family.name,
            source_paths=(),
            statement_coverage=None,
            branch_coverage=None,
            covered_lines=0,
            missing_lines=0,
            covered_branches=0,
            missing_branches=0,
            policy_threshold=config.governed_minimum,
            coverage_gap=config.governed_minimum,
            policy_state="NOT_MEASURED",
        )
    statements = sum(row.statements for row in files)
    covered_lines = sum(row.covered_lines for row in files)
    missing_lines = sum(row.missing_lines for row in files)
    branches = sum(row.branches for row in files)
    covered_branches = sum(row.covered_branches for row in files)
    missing_branches = sum(row.missing_branches for row in files)
    statement_coverage = (
        round(covered_lines / statements * 100, 2) if statements else 100.0
    )
    branch_coverage = round(covered_branches / branches * 100, 2) if branches else None
    statement_gap = max(0.0, config.governed_minimum - statement_coverage)
    branch_gap = (
        0.0
        if branch_coverage is None
        else max(0.0, config.branch_minimum - branch_coverage)
    )
    gap = round(max(statement_gap, branch_gap), 2)
    branch_below_trigger = (
        branch_coverage is not None and branch_coverage < config.remediation_trigger
    )
    branch_below_minimum = (
        branch_coverage is not None and branch_coverage < config.branch_minimum
    )
    if statement_coverage < config.remediation_trigger or branch_below_trigger:
        state = "BELOW_POLICY"
    elif statement_coverage < config.governed_minimum or branch_below_minimum:
        state = "IMPROVEMENT_REQUIRED"
    else:
        state = "PASS"
    return CoverageFamilyResult(
        target=family.name,
        coverage_family=family.name,
        source_paths=tuple(row.path for row in files),
        statement_coverage=statement_coverage,
        branch_coverage=branch_coverage,
        covered_lines=covered_lines,
        missing_lines=missing_lines,
        covered_branches=covered_branches,
        missing_branches=missing_branches,
        policy_threshold=config.governed_minimum,
        coverage_gap=gap,
        policy_state=state,
    )


def _policy_result(
    config: CoveragePolicyConfig,
    policy_failures: tuple[str, ...],
    not_measured: tuple[str, ...],
    conflicts: tuple[str, ...],
    architecture_failures: tuple[str, ...] = (),
    critical_behavior_failures: tuple[str, ...] = (),
) -> str:
    if conflicts:
        return "COVERAGE_SCOPE_CONFLICT"
    if (
        not policy_failures
        and not not_measured
        and not architecture_failures
        and not critical_behavior_failures
    ):
        return "PASS"
    if config.enforcement_mode == "enforced":
        return "FAIL"
    return "BASELINE_DEBT"


def _matches_family(path: str, family: CoverageFamilyConfig) -> bool:
    included = any(fnmatch.fnmatchcase(path, pattern) for pattern in family.include)
    excluded = any(fnmatch.fnmatchcase(path, pattern) for pattern in family.exclude)
    return included and not excluded


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return cast(dict[str, Any], value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        strings = tuple(str(item) for item in value)
        _require_patterns(label, strings, allow_empty=True)
        return strings
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    strings = tuple(str(item) for item in value)
    _require_patterns(label, strings, allow_empty=True)
    return strings


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def _require_identifier(label: str, value: str) -> None:
    _require_text(label, value)
    if not value.replace("_", "").isalnum():
        raise ValueError(f"{label} must be a simple identifier")


def _require_text(label: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} is required")


def _require_percent(label: str, value: float) -> None:
    if value < 0.0 or value > 100.0:
        raise ValueError(f"{label} must be between 0 and 100")


def _require_patterns(
    label: str,
    values: tuple[str, ...],
    *,
    allow_empty: bool,
) -> None:
    if not values and not allow_empty:
        raise ValueError(f"{label} cannot be empty")
    normalized = tuple(_normalize_path(value) for value in values)
    if any(not value for value in normalized):
        raise ValueError(f"{label} cannot contain blank values")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} must be unique")


if __name__ == "__main__":
    raise SystemExit(main())
