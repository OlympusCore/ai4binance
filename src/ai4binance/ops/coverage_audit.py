"""Risk-ranked coverage remediation audit."""

from __future__ import annotations

import argparse
import fnmatch
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import yaml

from ai4binance.governance.architecture import (
    LogicalArchitectureRegistry,
    load_logical_architecture_registry,
)
from ai4binance.ops.coverage_architecture import (
    ArchitectureCoverageRow,
    CoverageArchitectureConfig,
    CriticalBehaviorCoverageRow,
    evaluate_coverage_architecture,
    load_coverage_architecture_config,
)
from ai4binance.reporting import to_primitive


class CoverageAuditSort(StrEnum):
    COVERAGE = "Coverage"
    RISK = "Risk"
    BRANCH_PRESSURE = "BranchPressure"
    REMEDIATION = "Remediation"


_IMPACT_SCORES = {
    "NONE": 0,
    "LOW": 25,
    "MEDIUM": 55,
    "HIGH": 85,
}
_AUTHORITY_SCORES = {
    "GOVERNANCE": 100,
    "DECISION_GOVERNANCE": 98,
    "RISK_EXECUTION": 96,
    "VALIDATION": 88,
    "PORTFOLIO_ACCOUNTING": 82,
    "ADAPTER": 72,
    "RESEARCH": 64,
    "SUPPORT": 42,
    "SOURCE": 40,
}
_EFFORT_POINTS = {"S": 1, "M": 2, "L": 3, "XL": 5}


@dataclass(frozen=True, slots=True)
class CoverageAuditRule:
    """Risk classification rule for one source path group."""

    rule_id: str
    description: str
    priority: str
    tier: str
    authority_class: str
    economic_impact: str
    execution_impact: str
    blast_radius: str
    target_coverage: float
    criticality_score: int
    include: tuple[str, ...]
    test_gap_types: tuple[str, ...]
    recommended_test_types: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_identifier("coverage audit rule", self.rule_id)
        _require_text("coverage audit rule description", self.description)
        _require_choice("priority", self.priority, {"P0", "P1", "P2", "P3"})
        _require_choice("tier", self.tier, {"T0", "T1", "T2", "T3", "T4"})
        _require_text("authority_class", self.authority_class)
        _require_impact("economic_impact", self.economic_impact)
        _require_impact("execution_impact", self.execution_impact)
        _require_impact("blast_radius", self.blast_radius)
        _require_percent("target_coverage", self.target_coverage)
        if not 0 <= self.criticality_score <= 100:
            raise ValueError("criticality_score must be between 0 and 100")
        _require_patterns("coverage audit include patterns", self.include)
        _require_non_empty_strings("test_gap_types", self.test_gap_types)
        _require_non_empty_strings(
            "recommended_test_types", self.recommended_test_types
        )


@dataclass(frozen=True, slots=True)
class CoverageAuditConfig:
    """Configuration for manual remediation audit output."""

    default_threshold: float
    default_target_coverage: float
    output_basename: str
    classification_rules: tuple[CoverageAuditRule, ...]
    architecture_assurance: CoverageArchitectureConfig | None = None

    def __post_init__(self) -> None:
        _require_percent("default_threshold", self.default_threshold)
        _require_percent("default_target_coverage", self.default_target_coverage)
        _require_identifier("output_basename", self.output_basename.replace("-", "_"))
        if self.default_threshold > self.default_target_coverage:
            raise ValueError("default_threshold cannot exceed default_target_coverage")
        if not self.classification_rules:
            raise ValueError("coverage audit requires classification rules")


@dataclass(frozen=True, slots=True)
class CoverageAuditFile:
    """Coverage.py file summary with optional missing line details."""

    path: str
    coverage_percent: float
    statements: int
    covered_lines: int
    missing_lines: int
    branches: int
    covered_branches: int
    missing_branches: int
    missing_line_numbers: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CoverageAuditRow:
    """Decision-ready remediation row for one source file."""

    path: str
    file_name: str
    coverage_rank: int
    risk_rank: int
    remediation_rank: int
    priority: str
    tier: str
    coverage_percent: float
    line_coverage_percent: float
    branch_coverage_percent: float | None
    target_coverage: float
    coverage_gap_to_target: float
    missing_lines: int
    missing_branches: int
    missing_total: int
    statements: int
    branches: int
    branch_pressure: float
    complexity: str
    criticality_score: int
    authority_class: str
    economic_impact: str
    execution_impact: str
    blast_radius: str
    test_gap_types: tuple[str, ...]
    recommended_test_types: tuple[str, ...]
    estimated_effort: str
    effort_points: int
    remediation_value: float
    priority_score: float
    remediation_efficiency: float
    manual_instruction: str
    classification_rule: str


@dataclass(frozen=True, slots=True)
class CoverageAuditReport:
    """Complete coverage audit report."""

    report_id: str
    generated_at_utc: datetime
    policy_document: str
    coverage_config: str
    coverage_json: str
    threshold_percent: float
    target_coverage_percent: float
    below_threshold_count: int
    target_gap_count: int
    sort_by: str
    filters: dict[str, object]
    files: tuple[CoverageAuditRow, ...]
    coverage_view: tuple[CoverageAuditRow, ...]
    risk_view: tuple[CoverageAuditRow, ...]
    remediation_view: tuple[CoverageAuditRow, ...]
    architecture_view: tuple[ArchitectureCoverageRow, ...]
    critical_behavior_view: tuple[CriticalBehaviorCoverageRow, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("coverage audit cannot authorize execution")

    def to_payload(self) -> dict[str, object]:
        return cast(dict[str, object], to_primitive(self))


def load_coverage_audit_config(path: Path) -> CoverageAuditConfig:
    """Load coverage audit configuration from the governed target file."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = _mapping(payload, "coverage target config")
    policy = _mapping(root.get("audit_policy"), "audit_policy")
    rules_payload = _mapping(
        policy.get("classification_rules"),
        "audit_policy.classification_rules",
    )
    rules = tuple(
        CoverageAuditRule(
            rule_id=str(rule_id),
            description=str(
                _mapping(raw, f"classification_rules.{rule_id}").get("description", "")
            ),
            priority=str(
                _mapping(raw, f"classification_rules.{rule_id}").get("priority", "")
            ),
            tier=str(_mapping(raw, f"classification_rules.{rule_id}").get("tier", "")),
            authority_class=str(
                _mapping(raw, f"classification_rules.{rule_id}").get(
                    "authority_class", ""
                )
            ),
            economic_impact=str(
                _mapping(raw, f"classification_rules.{rule_id}").get(
                    "economic_impact", ""
                )
            ),
            execution_impact=str(
                _mapping(raw, f"classification_rules.{rule_id}").get(
                    "execution_impact", ""
                )
            ),
            blast_radius=str(
                _mapping(raw, f"classification_rules.{rule_id}").get("blast_radius", "")
            ),
            target_coverage=float(
                _mapping(raw, f"classification_rules.{rule_id}").get(
                    "target_coverage", -1.0
                )
            ),
            criticality_score=int(
                _mapping(raw, f"classification_rules.{rule_id}").get(
                    "criticality_score", -1
                )
            ),
            include=_strings(
                _mapping(raw, f"classification_rules.{rule_id}").get("include"),
                f"classification_rules.{rule_id}.include",
            ),
            test_gap_types=_strings(
                _mapping(raw, f"classification_rules.{rule_id}").get("test_gap_types"),
                f"classification_rules.{rule_id}.test_gap_types",
            ),
            recommended_test_types=_strings(
                _mapping(raw, f"classification_rules.{rule_id}").get(
                    "recommended_test_types"
                ),
                f"classification_rules.{rule_id}.recommended_test_types",
            ),
        )
        for rule_id, raw in rules_payload.items()
    )
    return CoverageAuditConfig(
        default_threshold=float(policy.get("default_threshold", -1.0)),
        default_target_coverage=float(policy.get("default_target_coverage", -1.0)),
        output_basename=str(policy.get("output_basename", "")),
        classification_rules=rules,
        architecture_assurance=load_coverage_architecture_config(
            root.get("architecture_assurance")
        ),
    )


def load_coverage_audit_files(path: Path) -> tuple[CoverageAuditFile, ...]:
    """Load file summaries from coverage.py JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    files = _mapping(payload.get("files"), "coverage.files")
    rows: list[CoverageAuditFile] = []
    for raw_path, raw_file in files.items():
        file_payload = _mapping(raw_file, f"coverage.files.{raw_path}")
        summary = _mapping(
            file_payload.get("summary"), f"coverage.files.{raw_path}.summary"
        )
        path_text = _normalize_path(str(raw_path)).lstrip("/")
        statements = int(summary.get("num_statements", 0))
        missing_lines = int(summary.get("missing_lines", 0))
        branches = int(summary.get("num_branches", 0))
        missing_branches = int(summary.get("missing_branches", 0))
        rows.append(
            CoverageAuditFile(
                path=path_text,
                coverage_percent=round(float(summary.get("percent_covered", 0.0)), 2),
                statements=statements,
                covered_lines=max(0, statements - missing_lines),
                missing_lines=missing_lines,
                branches=branches,
                covered_branches=max(0, branches - missing_branches),
                missing_branches=missing_branches,
                missing_line_numbers=_int_tuple(file_payload.get("missing_lines")),
            )
        )
    return tuple(rows)


def build_coverage_audit_report(
    files: tuple[CoverageAuditFile, ...],
    config: CoverageAuditConfig,
    *,
    policy_document: str,
    coverage_config: str,
    coverage_json: str,
    threshold: float | None = None,
    target_coverage: float | None = None,
    sort_by: CoverageAuditSort = CoverageAuditSort.COVERAGE,
    priority: str | None = None,
    tier: str | None = None,
    authority: str | None = None,
    target_only: bool = False,
    source_root: Path | None = None,
    architecture_registry: LogicalArchitectureRegistry | None = None,
    coverage_generated_at: datetime | None = None,
    generated_at: datetime | None = None,
) -> CoverageAuditReport:
    """Build a risk-ranked coverage remediation report."""
    threshold_value = config.default_threshold if threshold is None else threshold
    target_value = (
        config.default_target_coverage if target_coverage is None else target_coverage
    )
    _require_percent("threshold", threshold_value)
    _require_percent("target_coverage", target_value)
    all_rows = tuple(
        _row_for_file(file, config, target_value, source_root=source_root)
        for file in files
    )
    rows = tuple(
        row
        for row in all_rows
        if row.coverage_percent < threshold_value
        or (target_only and row.coverage_gap_to_target > 0)
    )
    rows = _assign_ranks(rows)
    filtered = tuple(
        row
        for row in rows
        if _matches_filter(row.priority, priority)
        and _matches_filter(row.tier, tier)
        and _matches_filter(row.authority_class, authority)
        and (not target_only or row.coverage_gap_to_target > 0)
    )
    architecture_view: tuple[ArchitectureCoverageRow, ...] = ()
    critical_behavior_view: tuple[CriticalBehaviorCoverageRow, ...] = ()
    if config.architecture_assurance is not None and architecture_registry is not None:
        if source_root is None:
            raise ValueError(
                "source_root is required for architecture assurance evaluation"
            )
        architecture_report = evaluate_coverage_architecture(
            config.architecture_assurance,
            architecture_registry,
            files,
            repository_root=source_root,
            coverage_generated_at=coverage_generated_at,
            generated_at=generated_at,
        )
        architecture_view = architecture_report.architecture_view
        critical_behavior_view = architecture_report.critical_behavior_view
    return CoverageAuditReport(
        report_id="AI4B-COVERAGE-AUDIT-DECISION-READY",
        generated_at_utc=generated_at or datetime.now(UTC),
        policy_document=policy_document,
        coverage_config=coverage_config,
        coverage_json=coverage_json,
        threshold_percent=round(threshold_value, 2),
        target_coverage_percent=round(target_value, 2),
        below_threshold_count=sum(
            1 for row in rows if row.coverage_percent < threshold_value
        ),
        target_gap_count=sum(1 for row in rows if row.coverage_gap_to_target > 0),
        sort_by=sort_by.value,
        filters={
            "priority": priority,
            "tier": tier,
            "authority": authority,
            "target_only": target_only,
        },
        files=_sort_rows(filtered, sort_by),
        coverage_view=_sort_rows(filtered, CoverageAuditSort.COVERAGE),
        risk_view=_sort_rows(filtered, CoverageAuditSort.RISK),
        remediation_view=_sort_rows(filtered, CoverageAuditSort.REMEDIATION),
        architecture_view=architecture_view,
        critical_behavior_view=critical_behavior_view,
    )


def write_coverage_audit_outputs(
    report: CoverageAuditReport,
    *,
    output_directory: Path,
    output_basename: str,
) -> tuple[Path, Path]:
    """Write JSON and Markdown coverage audit artifacts."""
    output_directory.mkdir(parents=True, exist_ok=True)
    json_output = output_directory / f"{output_basename}.json"
    markdown_output = output_directory / f"{output_basename}.md"
    json_output.write_text(
        json.dumps(report.to_payload(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
    return json_output, markdown_output


def render_markdown(report: CoverageAuditReport) -> str:
    """Render a reader-friendly coverage remediation report."""
    lines = [
        "# AI4BINANCE Coverage Audit Decision Report",
        "",
        "## ELI10",
        "",
        "This report ranks uncovered behavior by coverage debt, risk, and "
        "remediation value.",
        "",
        "## Summary",
        "",
        f"- Threshold: {report.threshold_percent:.2f}%",
        f"- Manual remediation target: {report.target_coverage_percent:.2f}%",
        f"- Files below threshold: {report.below_threshold_count}",
        f"- Files below target: {report.target_gap_count}",
        f"- Sort: {report.sort_by}",
        "- Execution allowed: false",
        "- Live eligibility: LIVE_ORDER_BLOCKED",
        "",
        "## Coverage View",
        "",
        _table(report.coverage_view),
        "",
        "## Risk View",
        "",
        _table(report.risk_view),
        "",
        "## Remediation View",
        "",
        _table(report.remediation_view),
        "",
        "## Architecture View",
        "",
        _architecture_table(report.architecture_view),
        "",
        "## Critical Behavior View",
        "",
        _critical_behavior_table(report.critical_behavior_view),
        "",
        "## Safety",
        "",
        "Coverage is quality evidence only. It does not authorize live orders, "
        "risk-limit changes, strategy promotion, or execution authority.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for the PowerShell coverage audit wrapper."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-json", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--policy-document", required=True)
    parser.add_argument("--coverage-json-display", required=True)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--target-coverage", type=float)
    parser.add_argument(
        "--sort-by",
        choices=tuple(item.value for item in CoverageAuditSort),
        default="Coverage",
    )
    parser.add_argument("--priority")
    parser.add_argument("--tier")
    parser.add_argument("--authority")
    parser.add_argument("--target-only", action="store_true")
    args = parser.parse_args(argv)

    config = load_coverage_audit_config(args.config)
    files = load_coverage_audit_files(args.coverage_json)
    architecture_registry = None
    if config.architecture_assurance is not None:
        architecture_registry = load_logical_architecture_registry(
            Path.cwd() / config.architecture_assurance.registry_path,
            schema_root=Path.cwd() / "schemas",
        )
    report = build_coverage_audit_report(
        files,
        config,
        policy_document=args.policy_document,
        coverage_config=_normalize_path(str(args.config)),
        coverage_json=args.coverage_json_display,
        threshold=args.threshold,
        target_coverage=args.target_coverage,
        sort_by=CoverageAuditSort(args.sort_by),
        priority=args.priority,
        tier=args.tier,
        authority=args.authority,
        target_only=bool(args.target_only),
        source_root=Path.cwd(),
        architecture_registry=architecture_registry,
        coverage_generated_at=datetime.fromtimestamp(
            args.coverage_json.stat().st_mtime,
            UTC,
        ),
    )
    write_coverage_audit_outputs(
        report,
        output_directory=args.output_directory,
        output_basename=config.output_basename,
    )
    print(json.dumps(report.to_payload(), sort_keys=True))
    return 0


def _row_for_file(
    file: CoverageAuditFile,
    config: CoverageAuditConfig,
    default_target: float,
    *,
    source_root: Path | None,
) -> CoverageAuditRow:
    rule = _classify(file.path, config)
    target = max(default_target, rule.target_coverage)
    coverage_gap = round(max(0.0, target - file.coverage_percent), 2)
    branch_coverage = (
        None
        if file.branches == 0
        else round(file.covered_branches / file.branches * 100, 2)
    )
    missing_total = file.missing_lines + file.missing_branches
    branch_pressure = round(file.missing_branches / max(1, file.missing_lines), 2)
    complexity = _complexity(file.statements, file.branches)
    effort = _estimated_effort(missing_total, complexity)
    categories = _test_gap_types(file, rule, source_root)
    recommended = tuple(
        dict.fromkeys((*rule.recommended_test_types, *_recommended_tests(categories)))
    )
    priority_score = _priority_score(rule, coverage_gap, branch_pressure)
    remediation_value = round(rule.criticality_score * coverage_gap, 2)
    remediation_efficiency = round(priority_score / _EFFORT_POINTS[effort], 2)
    return CoverageAuditRow(
        path=file.path,
        file_name=Path(file.path).name,
        coverage_rank=0,
        risk_rank=0,
        remediation_rank=0,
        priority=rule.priority,
        tier=rule.tier,
        coverage_percent=file.coverage_percent,
        line_coverage_percent=file.coverage_percent,
        branch_coverage_percent=branch_coverage,
        target_coverage=target,
        coverage_gap_to_target=coverage_gap,
        missing_lines=file.missing_lines,
        missing_branches=file.missing_branches,
        missing_total=missing_total,
        statements=file.statements,
        branches=file.branches,
        branch_pressure=branch_pressure,
        complexity=complexity,
        criticality_score=rule.criticality_score,
        authority_class=rule.authority_class,
        economic_impact=rule.economic_impact,
        execution_impact=rule.execution_impact,
        blast_radius=rule.blast_radius,
        test_gap_types=categories,
        recommended_test_types=recommended,
        estimated_effort=effort,
        effort_points=_EFFORT_POINTS[effort],
        remediation_value=remediation_value,
        priority_score=priority_score,
        remediation_efficiency=remediation_efficiency,
        manual_instruction=(
            f"Raise {file.path} coverage to at least {target:.2f}% with "
            f"{', '.join(recommended)} tests for {', '.join(categories)}."
        ),
        classification_rule=rule.rule_id,
    )


def _assign_ranks(rows: tuple[CoverageAuditRow, ...]) -> tuple[CoverageAuditRow, ...]:
    coverage_order = {
        id(row): index
        for index, row in enumerate(_sort_rows(rows, CoverageAuditSort.COVERAGE), 1)
    }
    risk_order = {
        id(row): index
        for index, row in enumerate(_sort_rows(rows, CoverageAuditSort.RISK), 1)
    }
    remediation_order = {
        id(row): index
        for index, row in enumerate(_sort_rows(rows, CoverageAuditSort.REMEDIATION), 1)
    }
    return tuple(
        replace(
            row,
            coverage_rank=coverage_order[id(row)],
            risk_rank=risk_order[id(row)],
            remediation_rank=remediation_order[id(row)],
        )
        for row in rows
    )


def _sort_rows(
    rows: tuple[CoverageAuditRow, ...],
    sort_by: CoverageAuditSort,
) -> tuple[CoverageAuditRow, ...]:
    if sort_by is CoverageAuditSort.RISK:
        return tuple(sorted(rows, key=_risk_sort_key))
    elif sort_by is CoverageAuditSort.BRANCH_PRESSURE:
        return tuple(sorted(rows, key=_branch_pressure_sort_key))
    elif sort_by is CoverageAuditSort.REMEDIATION:
        return tuple(sorted(rows, key=_remediation_sort_key))
    return tuple(sorted(rows, key=_coverage_sort_key))


def _risk_sort_key(row: CoverageAuditRow) -> tuple[float, float, str]:
    return (-row.priority_score, -float(row.criticality_score), row.path)


def _branch_pressure_sort_key(row: CoverageAuditRow) -> tuple[float, float, str]:
    return (-row.branch_pressure, -float(row.missing_branches), row.path)


def _remediation_sort_key(row: CoverageAuditRow) -> tuple[float, float, str]:
    return (-row.remediation_efficiency, -row.remediation_value, row.path)


def _coverage_sort_key(row: CoverageAuditRow) -> tuple[float, float, float, str]:
    return (
        row.coverage_percent,
        -float(row.missing_branches),
        -float(row.missing_lines),
        row.path,
    )


def _classify(path: str, config: CoverageAuditConfig) -> CoverageAuditRule:
    for rule in config.classification_rules:
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in rule.include):
            return rule
    return CoverageAuditRule(
        rule_id="default_source",
        description="Default source coverage target.",
        priority="P3",
        tier="T4",
        authority_class="SOURCE",
        economic_impact="LOW",
        execution_impact="LOW",
        blast_radius="LOW",
        target_coverage=config.default_target_coverage,
        criticality_score=40,
        include=("*",),
        test_gap_types=("BRANCH_PATHS",),
        recommended_test_types=("unit", "boundary"),
    )


def _priority_score(
    rule: CoverageAuditRule, coverage_gap: float, branch_pressure: float
) -> float:
    authority_score = _AUTHORITY_SCORES.get(rule.authority_class, 40)
    economic_execution_score = max(
        _IMPACT_SCORES[rule.economic_impact],
        _IMPACT_SCORES[rule.execution_impact],
    )
    branch_risk_score = min(100.0, branch_pressure * 100.0)
    blast_radius_score = _IMPACT_SCORES[rule.blast_radius]
    coverage_gap_score = min(100.0, coverage_gap * 5.0)
    return round(
        0.30 * authority_score
        + 0.25 * economic_execution_score
        + 0.20 * branch_risk_score
        + 0.15 * blast_radius_score
        + 0.10 * coverage_gap_score,
        2,
    )


def _test_gap_types(
    file: CoverageAuditFile,
    rule: CoverageAuditRule,
    source_root: Path | None,
) -> tuple[str, ...]:
    categories: list[str] = list(rule.test_gap_types)
    if file.missing_branches > 0:
        categories.append("BRANCH_PATHS")
    source_text = _missing_source_text(file, source_root)
    lowered_path = file.path.lower()
    if "except " in source_text or "raise " in source_text:
        categories.append("ERROR_PATHS")
    if "return " in source_text:
        categories.append("RETURN_PATHS")
    if "json" in source_text or "to_payload" in source_text:
        categories.append("SERIALIZATION_PATH")
    if any(
        token in lowered_path
        for token in ("blocker", "governance", "dge", "risk", "validation")
    ):
        categories.append("FAIL_CLOSED_PATH")
    if (
        "live" in lowered_path
        or "execution" in lowered_path
        or "exchange" in lowered_path
    ):
        categories.append("LIVE_ORDER_BLOCK_PATH")
    if "replay" in lowered_path:
        categories.append("REPLAY_PATH")
    if "recovery" in lowered_path:
        categories.append("RECOVERY_PATH")
    return tuple(dict.fromkeys(categories))


def _recommended_tests(categories: tuple[str, ...]) -> tuple[str, ...]:
    tests: list[str] = []
    if "BRANCH_PATHS" in categories:
        tests.append("branch")
    if "ERROR_PATHS" in categories:
        tests.append("failure_path")
    if "FAIL_CLOSED_PATH" in categories or "LIVE_ORDER_BLOCK_PATH" in categories:
        tests.append("fail_closed")
    if "SERIALIZATION_PATH" in categories:
        tests.append("serialization")
    if "REPLAY_PATH" in categories:
        tests.append("replay")
    if "RECOVERY_PATH" in categories:
        tests.append("recovery")
    return tuple(tests)


def _missing_source_text(file: CoverageAuditFile, source_root: Path | None) -> str:
    if source_root is None or not file.missing_line_numbers:
        return ""
    source_path = source_root / file.path
    if not source_path.is_file():
        return ""
    lines = source_path.read_text(encoding="utf-8").splitlines()
    snippets = [
        lines[number - 1]
        for number in file.missing_line_numbers
        if 0 < number <= len(lines)
    ]
    return "\n".join(snippets)


def _complexity(statements: int, branches: int) -> str:
    score = statements + branches * 2
    if score >= 260:
        return "HIGH"
    if score >= 90:
        return "MEDIUM"
    return "LOW"


def _estimated_effort(missing_total: int, complexity: str) -> str:
    if missing_total >= 90 or complexity == "HIGH":
        return "XL"
    if missing_total >= 45:
        return "L"
    if missing_total >= 15 or complexity == "MEDIUM":
        return "M"
    return "S"


def _table(rows: tuple[CoverageAuditRow, ...]) -> str:
    if not rows:
        return "No files matched this view."
    lines = [
        "| Risk rank | Coverage rank | Remediation rank | Priority | Tier | "
        "Coverage | Target | Gap | Branch coverage | Missing lines | "
        "Missing branches | Criticality | Authority | Effort | Path |",
        "| ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in rows[:50]:
        branch = (
            "N/A"
            if row.branch_coverage_percent is None
            else f"{row.branch_coverage_percent:.2f}%"
        )
        lines.append(
            f"| {row.risk_rank} | {row.coverage_rank} | {row.remediation_rank} | "
            f"{row.priority} | {row.tier} | {row.coverage_percent:.2f}% | "
            f"{row.target_coverage:.2f}% | {row.coverage_gap_to_target:.2f} | "
            f"{branch} | {row.missing_lines} | {row.missing_branches} | "
            f"{row.criticality_score} | {row.authority_class} | "
            f"{row.estimated_effort} | "
            f"`{row.path}` |"
        )
    return "\n".join(lines)


def _architecture_table(rows: tuple[ArchitectureCoverageRow, ...]) -> str:
    if not rows:
        return "Architecture assurance was not evaluated."
    lines = [
        "| Target | Tier | Component | Domain | Statement | Branch | Relations | "
        "Runtime evidence | State |",
        "| --- | --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for row in rows:
        statement = (
            "NOT_MEASURED"
            if row.statement_coverage is None
            else f"{row.statement_coverage:.2f}%"
        )
        branch = "N/A" if row.branch_coverage is None else f"{row.branch_coverage:.2f}%"
        lines.append(
            f"| {row.target} | {row.tier} | {row.component_id or 'NOT_DECLARED'} | "
            f"{row.canonical_domain} | {statement} | {branch} | "
            f"{row.relation_status} | {row.runtime_evidence} | {row.state} |"
        )
    return "\n".join(lines)


def _critical_behavior_table(
    rows: tuple[CriticalBehaviorCoverageRow, ...],
) -> str:
    if not rows:
        return "Critical behavior assurance was not evaluated."
    lines = [
        "| Obligation | Category | Component | Expected outcome | Covered | "
        "Asserted | Runtime proven | State |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row.obligation_id} | {row.category} | {row.component_id} | "
            f"{row.expected_outcome} | {row.covered} | {row.asserted} | "
            f"{row.runtime_proven} | {row.state} |"
        )
    return "\n".join(lines)


def _matches_filter(value: str, requested: str | None) -> bool:
    return not requested or value.upper() == requested.upper()


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return cast(dict[str, Any], value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    return tuple(str(item) for item in value)


def _int_tuple(value: object) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(int(item) for item in value if isinstance(item, int))


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def _require_identifier(label: str, value: str) -> None:
    _require_text(label, value)
    if not value.replace("_", "").isalnum():
        raise ValueError(f"{label} must be a simple identifier")


def _require_text(label: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} is required")


def _require_choice(label: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        raise ValueError(f"{label} is invalid")


def _require_impact(label: str, value: str) -> None:
    _require_choice(label, value, set(_IMPACT_SCORES))


def _require_percent(label: str, value: float) -> None:
    if value < 0.0 or value > 100.0:
        raise ValueError(f"{label} must be between 0 and 100")


def _require_patterns(label: str, values: tuple[str, ...]) -> None:
    _require_non_empty_strings(label, values)
    normalized = tuple(_normalize_path(value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} must be unique")


def _require_non_empty_strings(label: str, values: tuple[str, ...]) -> None:
    if not values or any(not value.strip() for value in values):
        raise ValueError(f"{label} cannot be empty")


if __name__ == "__main__":
    raise SystemExit(main())
