"""Report-only repository cleanup and stability audit."""

from __future__ import annotations

import ast
import subprocess  # nosec B404
import time
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


class CleanupAuditStatus(StrEnum):
    PASSED = "PASSED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class RefactorPriority(StrEnum):
    P1_STABILITY = "P1_STABILITY"
    P2_PERFORMANCE = "P2_PERFORMANCE"
    P3_CLEAN_CODE = "P3_CLEAN_CODE"
    P4_ARTIFACT_HYGIENE = "P4_ARTIFACT_HYGIENE"
    P3_REFACTOR_PACKAGE = "P3_REFACTOR_PACKAGE"


@dataclass(frozen=True, slots=True)
class RootVerification:
    canonical_root: str
    workspace_junction: str | None
    workspace_junction_target: str | None


@dataclass(frozen=True, slots=True)
class RepositoryInventory:
    source_files: int
    test_files: int
    docs_files: int
    script_files: int
    agent_skill_files: int
    python_modules: int
    generated_cleanup_candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FolderClassification:
    path: str
    owner_area: str
    folder_type: str
    decision: str
    retention: str
    cleanup_mode: str | None
    notes: str


@dataclass(frozen=True, slots=True)
class RootHygieneClassification:
    path: str
    present: bool
    observed_children: tuple[str, ...]
    owner_area: str
    folder_type: str
    decision: str
    canonical_target: str
    notes: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EntryPointMap:
    project_scripts: dict[str, str]
    main_modules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuditFinding:
    finding_id: str
    subject_ref: str
    severity: str
    evidence_refs: tuple[str, ...]
    recommended_action: str


@dataclass(frozen=True, slots=True)
class PythonSurfaceAudit:
    exact_import_cycle_count: int
    dynamic_usage_files: tuple[str, ...]
    static_unimported_files: tuple[str, ...]
    largest_modules: tuple[str, ...]
    broad_exception_sites: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FileClassification:
    path: str
    decision: str
    evidence_refs: tuple[str, ...]
    rationale: str


@dataclass(frozen=True, slots=True)
class BroadExceptionReview:
    site: str
    status: str
    catch_boundary: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    next_action: str


@dataclass(frozen=True, slots=True)
class RefactorWorkPackage:
    package_id: str
    priority: RefactorPriority
    problem: str
    evidence_refs: tuple[str, ...]
    proposed_change: str
    files_affected: tuple[str, ...]
    risk: str
    tests: tuple[str, ...]
    rollback: str
    expected_benefit: str
    approval_required: bool = True


@dataclass(frozen=True, slots=True)
class PerformanceBaseline:
    python_startup_ms: float
    cli_commands_text_ms: float
    cleanup_dry_run_ms: float
    measurement_notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RepositoryCleanupAuditReport:
    command: str
    observed_at: datetime
    root: RootVerification
    inventory: RepositoryInventory
    folder_classifications: tuple[FolderClassification, ...]
    root_hygiene_classifications: tuple[RootHygieneClassification, ...]
    entry_points: EntryPointMap
    exact_import_cycle_count: int
    dynamic_usage_files: tuple[str, ...]
    static_unimported_files: tuple[str, ...]
    static_unimported_classifications: tuple[FileClassification, ...]
    largest_modules: tuple[str, ...]
    broad_exception_sites: tuple[str, ...]
    broad_exception_reviews: tuple[BroadExceptionReview, ...]
    findings: tuple[AuditFinding, ...]
    performance_baseline: PerformanceBaseline
    work_packages: tuple[RefactorWorkPackage, ...]
    status: CleanupAuditStatus
    files_deleted: int = 0
    files_moved: int = 0
    files_changed_by_audit: int = 0
    packages_installed: int = 0
    live_actions: int = 0
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"


_EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "artifacts",
    "logs",
    "state",
    "secrets",
    "models",
    "data",
    "backtest",
    "Wallet",
    "Orders",
    "Opportunities",
}


def run_repository_cleanup_audit(workspace_root: Path) -> RepositoryCleanupAuditReport:
    requested_root = workspace_root
    root = workspace_root.resolve()
    inventory = _inventory(root)
    entry_points = _entry_points(root)
    graph = _analyze_python_surface(root)
    baseline = _performance_baseline(root)
    findings = _findings(inventory, graph)
    packages = _work_packages(inventory, graph, baseline)
    return RepositoryCleanupAuditReport(
        command="repository-cleanup-audit",
        observed_at=datetime.now(UTC),
        root=_verify_root(requested_root, root),
        inventory=inventory,
        folder_classifications=_folder_classifications(),
        root_hygiene_classifications=_root_hygiene_classifications(root),
        entry_points=entry_points,
        exact_import_cycle_count=graph.exact_import_cycle_count,
        dynamic_usage_files=graph.dynamic_usage_files,
        static_unimported_files=graph.static_unimported_files,
        static_unimported_classifications=_classify_static_unimported(
            graph.static_unimported_files
        ),
        largest_modules=graph.largest_modules,
        broad_exception_sites=graph.broad_exception_sites,
        broad_exception_reviews=_broad_exception_reviews(graph.broad_exception_sites),
        findings=findings,
        performance_baseline=baseline,
        work_packages=packages,
        status=(
            CleanupAuditStatus.REVIEW_REQUIRED
            if findings
            else CleanupAuditStatus.PASSED
        ),
    )


def _verify_root(requested_root: Path, root: Path) -> RootVerification:
    junction_target: str | None = None
    workspace_alias: Path | None = None
    observed_root = requested_root
    if not observed_root.is_absolute():
        observed_root = Path.cwd() / observed_root
    try:
        if observed_root.exists() and observed_root.resolve() == root:
            workspace_alias = observed_root
            junction_target = str(root)
    except OSError:
        workspace_alias = None
    return RootVerification(
        canonical_root=str(root),
        workspace_junction=(
            str(workspace_alias) if workspace_alias is not None else None
        ),
        workspace_junction_target=junction_target,
    )


def _inventory(root: Path) -> RepositoryInventory:
    def count_files(relative: str, suffix: str | None = None) -> int:
        base = root / relative
        if not base.exists():
            return 0
        return sum(
            1
            for path in base.rglob("*")
            if path.is_file()
            and not _is_excluded(path)
            and (suffix is None or path.suffix == suffix)
        )

    return RepositoryInventory(
        source_files=count_files("src"),
        test_files=count_files("tests", ".py"),
        docs_files=count_files("docs", ".md"),
        script_files=count_files("scripts", ".ps1"),
        agent_skill_files=count_files(".agents"),
        python_modules=count_files("src/ai4binance", ".py"),
        generated_cleanup_candidates=_cleanup_candidates(root),
    )


def _entry_points(root: Path) -> EntryPointMap:
    pyproject = root / "pyproject.toml"
    project_scripts: dict[str, str] = {}
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        scripts = data.get("project", {}).get("scripts", {})
        if isinstance(scripts, dict):
            project_scripts = {
                str(name): str(target) for name, target in sorted(scripts.items())
            }
    main_modules = tuple(
        _relative(path, root)
        for path in sorted((root / "src").rglob("*.py"))
        if not _is_excluded(path)
        and 'if __name__ == "__main__"' in path.read_text(encoding="utf-8")
    )
    return EntryPointMap(project_scripts=project_scripts, main_modules=main_modules)


def _analyze_python_surface(root: Path) -> PythonSurfaceAudit:
    modules: dict[str, str] = {}
    exact_imports: dict[str, set[str]] = {}
    referenced_modules: dict[str, set[str]] = {}
    dynamic_usage: set[str] = set()
    broad_exceptions: list[str] = []
    largest: list[tuple[int, str]] = []
    source_root = root / "src"
    for path in sorted((source_root / "ai4binance").rglob("*.py")):
        if _is_excluded(path):
            continue
        relative = _relative(path, root)
        module = ".".join(path.relative_to(source_root).with_suffix("").parts)
        if module.endswith(".__init__"):
            module = module.removesuffix(".__init__")
        modules[module] = relative
        text = path.read_text(encoding="utf-8")
        largest.append((len(text.splitlines()), relative))
        tree = ast.parse(text, filename=relative)
        exact_imports[module] = set()
        referenced_modules[module] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("ai4binance"):
                        exact_imports[module].add(alias.name)
                        referenced_modules[module].add(alias.name)
                    if alias.name == "importlib":
                        dynamic_usage.add(relative)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    dynamic_usage.add(relative)
                resolved = _resolve_import_from_module(module, node)
                if resolved is not None and resolved.startswith("ai4binance"):
                    referenced_modules[module].add(resolved)
                    if not node.level:
                        exact_imports[module].add(resolved)
            elif isinstance(node, ast.Call):
                name = getattr(node.func, "id", "")
                attr = getattr(node.func, "attr", "")
                if name in {"getattr", "__import__"} or attr == "import_module":
                    dynamic_usage.add(relative)
            elif isinstance(node, ast.ExceptHandler) and _is_broad_exception(node):
                broad_exceptions.append(f"{relative}:{node.lineno}")

    reverse: dict[str, set[str]] = {name: set() for name in modules}
    exact_edges: dict[str, set[str]] = {name: set() for name in modules}
    for module, dependencies in referenced_modules.items():
        for dependency in dependencies:
            if dependency in modules:
                reverse[dependency].add(module)
            else:
                for candidate in sorted(modules, key=len, reverse=True):
                    if dependency.startswith(candidate + "."):
                        reverse[candidate].add(module)
                        break
    for module, dependencies in exact_imports.items():
        for dependency in dependencies:
            if dependency in modules:
                exact_edges[module].add(dependency)

    static_unimported = tuple(
        modules[module]
        for module in sorted(modules)
        if (
            not reverse[module]
            and not modules[module].endswith("__init__.py")
            and not _is_reserved_placeholder_module(root / modules[module])
        )
    )
    return PythonSurfaceAudit(
        exact_import_cycle_count=_count_cycles(exact_edges),
        dynamic_usage_files=tuple(sorted(dynamic_usage)),
        static_unimported_files=static_unimported,
        broad_exception_sites=tuple(broad_exceptions),
        largest_modules=tuple(
            f"{relative}:{line_count}"
            for line_count, relative in sorted(largest, reverse=True)[:10]
        ),
    )


def _performance_baseline(root: Path) -> PerformanceBaseline:
    return PerformanceBaseline(
        python_startup_ms=_timed(
            root,
            (".venv/Scripts/python.exe", "-c", "print('ok')"),
        ),
        cli_commands_text_ms=_timed(
            root,
            (
                ".venv/Scripts/python.exe",
                "-m",
                "ai4binance.cli",
                "commands",
                "--format",
                "text",
            ),
        ),
        cleanup_dry_run_ms=_timed(
            root,
            (
                "powershell",
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                "scripts/cleanup_generated_artifacts.ps1",
                "-Mode",
                "All",
            ),
        ),
        measurement_notes=(
            "single local warm measurement",
            "report-only; not a performance guarantee",
        ),
    )


def _findings(
    inventory: RepositoryInventory,
    graph: PythonSurfaceAudit,
) -> tuple[AuditFinding, ...]:
    findings: list[AuditFinding] = []
    broad = graph.broad_exception_sites
    if broad:
        findings.append(
            AuditFinding(
                finding_id="RF001_BROAD_EXCEPTION_SITES",
                subject_ref="src/ai4binance",
                severity="MEDIUM",
                evidence_refs=broad[:10],
                recommended_action=(
                    "Review fail-closed broad exceptions and narrow adapter "
                    "boundaries where tests prove equivalent behavior."
                ),
            )
        )
    dynamic = graph.dynamic_usage_files
    static_unimported = graph.static_unimported_files
    if static_unimported:
        findings.append(
            AuditFinding(
                finding_id="RF005_STATIC_UNIMPORTED_REQUIRES_DYNAMIC_REVIEW",
                subject_ref="src/ai4binance",
                severity="LOW",
                evidence_refs=static_unimported[:10],
                recommended_action=(
                    "Classify static-unimported files through CLI, registry, "
                    "config and test evidence before archive decisions."
                ),
            )
        )
    if dynamic:
        findings.append(
            AuditFinding(
                finding_id="DYNAMIC_USAGE_GUARD_ACTIVE",
                subject_ref="src/ai4binance",
                severity="INFO",
                evidence_refs=dynamic[:10],
                recommended_action="Keep dynamic-use files out of delete candidates.",
            )
        )
    if inventory.generated_cleanup_candidates:
        findings.append(
            AuditFinding(
                finding_id="RF004_GENERATED_CACHE_CANDIDATES",
                subject_ref="generated-artifacts",
                severity="LOW",
                evidence_refs=inventory.generated_cleanup_candidates,
                recommended_action=(
                    "Use cleanup_generated_artifacts.ps1 -Mode Caches -Apply."
                ),
            )
        )
    return tuple(findings)


def _work_packages(
    inventory: RepositoryInventory,
    graph: PythonSurfaceAudit,
    baseline: PerformanceBaseline,
) -> tuple[RefactorWorkPackage, ...]:
    largest = graph.largest_modules
    broad = graph.broad_exception_sites
    static_unimported = graph.static_unimported_files
    return (
        RefactorWorkPackage(
            package_id="RF-001",
            priority=RefactorPriority.P1_STABILITY,
            problem="Broad exception handlers hide precise failure boundaries.",
            evidence_refs=broad[:10],
            proposed_change="Narrow each site only after equivalent fail-closed tests.",
            files_affected=tuple(sorted({site.split(":", 1)[0] for site in broad})),
            risk="Medium",
            tests=("pytest focused adapter tests --no-cov", "scripts/quality.ps1"),
            rollback="Revert the scoped exception narrowing diff.",
            expected_benefit=(
                "Clearer blockers without changing safe fallback behavior."
            ),
        ),
        RefactorWorkPackage(
            package_id="RF-002",
            priority=RefactorPriority.P2_PERFORMANCE,
            problem="Performance decisions need a durable local baseline first.",
            evidence_refs=(
                f"python_startup_ms:{baseline.python_startup_ms:.2f}",
                f"cli_commands_text_ms:{baseline.cli_commands_text_ms:.2f}",
                f"cleanup_dry_run_ms:{baseline.cleanup_dry_run_ms:.2f}",
            ),
            proposed_change="Keep baseline metrics in report-only audit output.",
            files_affected=("src/ai4binance/ops/repository_cleanup_audit.py",),
            risk="Low",
            tests=("pytest tests/test_repository_cleanup_audit.py --no-cov",),
            rollback="Remove the report-only baseline collector.",
            expected_benefit="Prevents unmeasured performance refactors.",
        ),
        RefactorWorkPackage(
            package_id="RF-003",
            priority=RefactorPriority.P3_CLEAN_CODE,
            problem="Accounting and governance surfaces include large modules.",
            evidence_refs=largest[:10],
            proposed_change=(
                "Plan behavior-preserving extractions before touching accounting "
                "runtime code."
            ),
            files_affected=tuple(item.split(":", 1)[0] for item in largest[:5]),
            risk="Medium",
            tests=("accounting focused tests", "scripts/quality.ps1"),
            rollback="Revert one extraction package at a time.",
            expected_benefit="Smaller reviewable modules with unchanged persistence.",
        ),
        RefactorWorkPackage(
            package_id="RF-004",
            priority=RefactorPriority.P4_ARTIFACT_HYGIENE,
            problem="Generated cache folders are reproducible local noise.",
            evidence_refs=inventory.generated_cleanup_candidates,
            proposed_change=(
                "Run cache cleanup mode when no source artifacts are involved."
            ),
            files_affected=inventory.generated_cleanup_candidates,
            risk="Low",
            tests=("scripts/cleanup_generated_artifacts.ps1 -Mode All",),
            rollback="Caches are regenerated by Ruff and MyPy.",
            expected_benefit="Lower repo noise and faster human review.",
        ),
        RefactorWorkPackage(
            package_id="RF-005",
            priority=RefactorPriority.P3_CLEAN_CODE,
            problem="Static-unimported files can be misclassified in registry systems.",
            evidence_refs=static_unimported[:10],
            proposed_change="Report static-unimported files as review candidates.",
            files_affected=("src/ai4binance/ops/repository_cleanup_audit.py",),
            risk="Low",
            tests=("pytest tests/test_repository_cleanup_audit.py --no-cov",),
            rollback="Remove the report-only classifier.",
            expected_benefit="Prevents unsafe dead-code deletion.",
        ),
        RefactorWorkPackage(
            package_id="RF-006",
            priority=RefactorPriority.P3_REFACTOR_PACKAGE,
            problem=(
                "accounting/records.py mixes record models, serialization, "
                "ledger append paths and helper validation in one large file."
            ),
            evidence_refs=("src/ai4binance/accounting/records.py:2253",),
            proposed_change=(
                "Prepare a behavior-preserving split into records/models.py, "
                "records/serialization.py and records/helpers.py while keeping "
                "the public accounting.records import surface stable."
            ),
            files_affected=(
                "src/ai4binance/accounting/records.py",
                "src/ai4binance/accounting/records/models.py",
                "src/ai4binance/accounting/records/serialization.py",
                "src/ai4binance/accounting/records/helpers.py",
            ),
            risk="Medium",
            tests=(
                "pytest tests/test_accounting_records.py --no-cov",
                "pytest tests/test_accounting_collectors.py --no-cov",
                "scripts/quality.ps1",
            ),
            rollback=(
                "Revert the extraction package and keep the monolithic records.py "
                "implementation."
            ),
            expected_benefit=(
                "Smaller reviewable accounting modules without changing append-only "
                "record persistence, hashes or public imports."
            ),
        ),
    )


def _cleanup_candidates(root: Path) -> tuple[str, ...]:
    candidates = []
    for relative in (".mypy_cache", ".ruff_cache", ".pytest_cache", ".test-tmp"):
        if (root / relative).is_dir():
            candidates.append(relative)
    return tuple(candidates)


def _resolve_import_from_module(module: str, node: ast.ImportFrom) -> str | None:
    if node.module and node.module.startswith("ai4binance"):
        return node.module
    if not node.level:
        return node.module
    container_parts = module.split(".")
    if not container_parts:
        return None
    anchor = container_parts[: -node.level]
    if node.module:
        anchor.extend(node.module.split("."))
    if not anchor:
        return None
    return ".".join(anchor)


def _is_reserved_placeholder_module(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return False
    body = list(tree.body)
    if not body:
        return True
    if len(body) != 1:
        return False
    statement = body[0]
    if isinstance(statement, ast.Expr):
        value = statement.value
        return isinstance(value, ast.Constant) and isinstance(value.value, str)
    return False


def _folder_classifications() -> tuple[FolderClassification, ...]:
    return (
        FolderClassification(
            ".pytest_cache",
            "Quality",
            "Generated cache",
            "GENERATED",
            "on demand",
            "Caches",
            "Recreated by Pytest; safe generated cache cleanup without ACL forcing.",
        ),
        FolderClassification(
            ".mypy_cache",
            "Quality",
            "Generated cache",
            "GENERATED",
            "on demand",
            "Caches",
            "Recreated by MyPy.",
        ),
        FolderClassification(
            ".ruff_cache",
            "Quality",
            "Generated cache",
            "GENERATED",
            "on demand",
            "Caches",
            "Recreated by Ruff.",
        ),
        FolderClassification(
            "runtime/tmp/test_temp",
            "Quality",
            "Generated temp",
            "ACL_FORCED_GENERATED",
            "2 days",
            "TestTempRetention",
            (
                "ACL forcing is allowed only for stale direct children after "
                "written approval."
            ),
        ),
        FolderClassification(
            "secrets",
            "Security",
            "Protected local state",
            "PROTECTED",
            "never broad-delete",
            None,
            "Only placeholder files are commit-eligible; secret contents are not read.",
        ),
        FolderClassification(
            "runtime/state/private",
            "Runtime state",
            "Protected local state",
            "PROTECTED",
            "never broad-delete",
            None,
            "Private local-only state stays outside generated cleanup.",
        ),
        FolderClassification(
            "Orders",
            "Execution/audit",
            "Domain evidence",
            "KEEP_DOMAIN_ROOT",
            "manual",
            None,
            "Preserve rejected order and blocker evidence.",
        ),
        FolderClassification(
            "Opportunities",
            "Advisory radar",
            "Domain evidence",
            "KEEP_DOMAIN_ROOT",
            "manual",
            None,
            "Keep blocked opportunity context auditable.",
        ),
        FolderClassification(
            "Alerts",
            "Notifications",
            "Project folder",
            "DELETE_EMPTY",
            "manual",
            None,
            "Remove only if empty and unreferenced.",
        ),
        FolderClassification(
            "Analysis",
            "Research/reporting",
            "Project folder",
            "ARCHIVE_LOCAL",
            "manual",
            None,
            "Review useful reports before pruning.",
        ),
    )


def _root_hygiene_classifications(root: Path) -> tuple[RootHygieneClassification, ...]:
    return (
        _classify_legacy_root(
            root,
            relative="artifacts",
            owner_area="Runtime evidence",
            folder_type="Legacy runtime alias",
            present_decision="MOVE",
            absent_decision="GENERATED_RUNTIME",
            canonical_target="runtime/artifacts",
            notes=(
                "Historical machine-readable evidence root; new writes stay under "
                "runtime/artifacts and any remaining root usage needs explicit "
                "migration evidence."
            ),
        ),
        _classify_legacy_root(
            root,
            relative="data",
            owner_area="Runtime data",
            folder_type="Legacy compatibility root",
            present_decision="REGISTER",
            absent_decision="GENERATED_RUNTIME",
            canonical_target="runtime/data",
            notes=(
                "Legacy data root remains read-visible until a bounded migration "
                "record classifies each subtree; do not broad-move or delete."
            ),
        ),
    )


def _classify_legacy_root(
    root: Path,
    *,
    relative: str,
    owner_area: str,
    folder_type: str,
    present_decision: str,
    absent_decision: str,
    canonical_target: str,
    notes: str,
) -> RootHygieneClassification:
    path = root / relative
    present = path.exists()
    observed_children: tuple[str, ...] = ()
    if path.is_dir():
        observed_children = tuple(
            _relative(child, root)
            for child in sorted(path.iterdir(), key=lambda item: item.name.lower())[:8]
        )
    decision = present_decision if present else absent_decision
    return RootHygieneClassification(
        path=relative,
        present=present,
        observed_children=observed_children,
        owner_area=owner_area,
        folder_type=folder_type,
        decision=decision,
        canonical_target=canonical_target,
        notes=notes,
        evidence_refs=(
            "src/ai4binance/governance/repository_validator.py:_LEGACY_RUNTIME_ROOT_TARGETS",
            "docs/standards/standard_repository_structure_governance.md",
            "docs/adr/adr_canonical_repository_tree.md",
        ),
    )


def _classify_static_unimported(
    static_unimported: tuple[str, ...],
) -> tuple[FileClassification, ...]:
    registry: dict[str, FileClassification] = {
        "src/ai4binance/agents/advisory.py": FileClassification(
            "src/ai4binance/agents/advisory.py",
            "KEEP",
            (
                "tests/test_advisory_v2.py",
                "docs/compliance/registry_compliance_matrix.md",
            ),
            "Advisory v2 contract is test-backed and intentionally non-executing.",
        ),
        "src/ai4binance/agents/evaluation.py": FileClassification(
            "src/ai4binance/agents/evaluation.py",
            "KEEP",
            (
                "tests/test_agent_runtime_governance.py",
                "docs/compliance/registry_compliance_matrix.md",
            ),
            "Deterministic advisory trace evaluator is a governed contract surface.",
        ),
        "src/ai4binance/application/context/memory.py": FileClassification(
            "src/ai4binance/application/context/memory.py",
            "KEEP",
            ("tests/test_governed_memory_fabric.py",),
            "Governed Memory Fabric context compiler is read-only and tested.",
        ),
        "src/ai4binance/application/virtual_runtime.py": FileClassification(
            "src/ai4binance/application/virtual_runtime.py",
            "KEEP",
            (
                "tests/test_virtual_runtime_bridge.py",
                "tests/test_kaizen_quality.py",
            ),
            "Identity-preserving virtual-runtime compatibility facade is tested.",
        ),
        "src/ai4binance/application/whale_fusion.py": FileClassification(
            "src/ai4binance/application/whale_fusion.py",
            "KEEP",
            (
                "tests/test_application_whale_fusion_migration.py",
                "tests/test_whale_fusion_application.py",
            ),
            "Identity-preserving WHALE-FUSION compatibility facade is tested.",
        ),
        "src/ai4binance/cli/parser.py": FileClassification(
            "src/ai4binance/cli/parser.py",
            "KEEP",
            (
                "tests/test_cli_parser_migration.py",
                "tests/test_coverage_recovery.py",
            ),
            "Identity-preserving CLI parser compatibility facade is directly tested.",
        ),
        "src/ai4binance/cli/shared.py": FileClassification(
            "src/ai4binance/cli/shared.py",
            "KEEP",
            (
                "tests/test_cli_shared_migration.py",
                "tests/test_cli.py",
            ),
            "Identity-preserving shared CLI compatibility facade is directly tested.",
        ),
        "src/ai4binance/cli/skill_discovery.py": FileClassification(
            "src/ai4binance/cli/skill_discovery.py",
            "KEEP",
            (
                "tests/test_cli_skill_discovery_migration.py",
                "tests/test_skill_discovery_runtime.py",
            ),
            "Identity-preserving Agent Skill discovery CLI facade is directly tested.",
        ),
        "src/ai4binance/cli/output.py": FileClassification(
            "src/ai4binance/cli/output.py",
            "KEEP",
            (
                "tests/test_cli_output_migration.py",
                "tests/test_cli.py",
                "tests/test_repository_cleanup_audit.py",
            ),
            "Identity-preserving CLI presentation facade is directly tested.",
        ),
        "src/ai4binance/domain/memory.py": FileClassification(
            "src/ai4binance/domain/memory.py",
            "KEEP",
            ("tests/test_governed_memory_fabric.py",),
            "Governed Memory Fabric domain service is deterministic and fail-closed.",
        ),
        "src/ai4binance/historical_replay_evaluation.py": FileClassification(
            "src/ai4binance/historical_replay_evaluation.py",
            "KEEP",
            (
                "tests/test_historical_replay_evaluation.py",
                "tests/test_historical_replay_state.py",
                "src/ai4binance/enterprise/ykb_report.py",
            ),
            (
                "Full-system historical replay evidence orchestration is test-backed, "
                "research-only, and retained pending its registered architecture split."
            ),
        ),
        ("src/ai4binance/historical_replay_application.py"): FileClassification(
            "src/ai4binance/historical_replay_application.py",
            "KEEP",
            ("tests/test_historical_replay_materialization.py",),
            (
                "Transition-safe historical replay orchestration is integration-tested "
                "and cannot authorize live execution."
            ),
        ),
        "src/ai4binance/core/exchange_errors.py": FileClassification(
            "src/ai4binance/core/exchange_errors.py",
            "KEEP",
            (
                "tests/test_binance_market_universe_provider.py",
                "tests/test_kaizen_quality.py",
            ),
            "Identity-preserving compatibility facade is directly tested.",
        ),
        "src/ai4binance/exchange/errors.py": FileClassification(
            "src/ai4binance/exchange/errors.py",
            "KEEP",
            (
                "tests/test_binance_market_universe_provider.py",
                "tests/test_kaizen_quality.py",
            ),
            "Identity-preserving legacy exchange facade is directly tested.",
        ),
        (
            "src/ai4binance/infrastructure/opportunity_artifact_loader.py"
        ): FileClassification(
            "src/ai4binance/infrastructure/opportunity_artifact_loader.py",
            "KEEP",
            (
                "tests/test_opportunity_artifact_loader.py",
                "tests/test_kaizen_quality.py",
            ),
            "Identity-preserving filesystem compatibility facade is directly tested.",
        ),
        "src/ai4binance/infrastructure/persistence/memory.py": FileClassification(
            "src/ai4binance/infrastructure/persistence/memory.py",
            "KEEP",
            ("tests/test_governed_memory_fabric.py",),
            "Governed Memory Fabric JSONL adapter is bounded and advisory-only.",
        ),
        "src/ai4binance/ops/python_migration_benchmark.py": FileClassification(
            "src/ai4binance/ops/python_migration_benchmark.py",
            "KEEP",
            (
                "tests/test_python_migration_benchmark.py",
                "src/ai4binance/ops/performance.py",
            ),
            "Host-bound migration benchmark is deterministic and fail-closed.",
        ),
        "src/ai4binance/ops/python_runtime_removal_gate.py": FileClassification(
            "src/ai4binance/ops/python_runtime_removal_gate.py",
            "KEEP",
            (
                "tests/test_python_runtime_removal_gate.py",
                "docs/registries/registry_python_runtime.yaml",
            ),
            "Canonical Python runtime removal gate is fail-closed and report-only.",
        ),
        "src/ai4binance/research/backtesting/path_monte_carlo.py": FileClassification(
            "src/ai4binance/research/backtesting/path_monte_carlo.py",
            "KEEP",
            ("tests/test_path_monte_carlo.py",),
            "Path Monte Carlo diagnostics are directly tested validation evidence.",
        ),
        "src/ai4binance/cli.py": FileClassification(
            "src/ai4binance/cli.py",
            "ENTRY_POINT",
            ("pyproject.toml:ai4binance", "src/ai4binance/cli.py:__main__"),
            "Public CLI dispatcher and console script target.",
        ),
        "src/ai4binance/cli/futures_oos.py": FileClassification(
            "src/ai4binance/cli/futures_oos.py",
            "ENTRY_POINT",
            (
                "src/ai4binance/cli/futures_oos.py:__main__",
                "tests/test_futures_replay.py",
            ),
            "Local research-only Futures OOS publication entry point.",
        ),
        "src/ai4binance/cli/market_data.py": FileClassification(
            "src/ai4binance/cli/market_data.py",
            "ENTRY_POINT",
            (
                "src/ai4binance/cli/market_data.py:__main__",
                "scripts/install_startup_task.ps1:RunMarketHistory",
                "tests/test_market_history_sync.py",
            ),
            "Local research-only public market-history synchronization entry point.",
        ),
        "src/ai4binance/exchange/resilience.py": FileClassification(
            "src/ai4binance/exchange/resilience.py",
            "KEEP",
            (
                "tests/test_exchange_portfolio_resilience.py",
                "docs/compliance/registry_compliance_matrix.md",
            ),
            "Exchange rate-limit and server-time resilience gate.",
        ),
        "src/ai4binance/governance/constitution_sync.py": FileClassification(
            "src/ai4binance/governance/constitution_sync.py",
            "KEEP",
            (
                "src/ai4binance/governance/constitution_sync.py",
                "tests/test_governance_constitution_sync.py",
                "docs/compliance/registry_compliance_matrix.md",
                "docs/governance/framework_core_vnext_governance.md",
            ),
            (
                "Governance alignment audit binds code, written rules and "
                "quality evidence."
            ),
        ),
        "src/ai4binance/governance/repository_validator.py": FileClassification(
            "src/ai4binance/governance/repository_validator.py",
            "ENTRY_POINT",
            (
                "src/ai4binance/governance/repository_validator.py:__main__",
                "tests/test_repository_validator.py",
                "docs/standards/standard_repository_file_governance.md",
                "docs/standards/standard_documentation_knowledge_governance.md",
                "docs/compliance/registry_compliance_matrix.md",
                "scripts/quality.ps1",
            ),
            (
                "RepositoryPolicy, RepositoryArtifact schema, "
                "GovernedKnowledgeObject metadata and deterministic "
                "repository_validator are enforced by the quality gate."
            ),
        ),
        "src/ai4binance/governance/gate.py": FileClassification(
            "src/ai4binance/governance/gate.py",
            "ENTRY_POINT",
            (
                "src/ai4binance/governance/gate.py:__main__",
                "tests/test_governance_gate.py",
                "tests/test_artifact_hygiene_scripts.py",
                "scripts/quality.ps1",
                "docs/standards/standard_repository_validator_governance.md",
            ),
            (
                "Deterministic governance gate is a quality-gate entry point "
                "that combines validator enforcement, docs hygiene, "
                "artifact hygiene, constitution sync and evidence checks."
            ),
        ),
        "src/ai4binance/exchange/order_book.py": FileClassification(
            "src/ai4binance/exchange/order_book.py",
            "KEEP",
            (
                "tests/test_order_book_recorder.py",
                "tests/test_public_spot_stream.py",
            ),
            "Order-book state handling is a governed exchange data capability.",
        ),
        "src/ai4binance/local_agent/__main__.py": FileClassification(
            "src/ai4binance/local_agent/__main__.py",
            "ENTRY_POINT",
            (
                "src/ai4binance/local_agent/__main__.py",
                "tests/test_local_qwen_workbench.py",
            ),
            "Read-only local Ollama qwen3:8b workbench module entry point.",
        ),
        "src/ai4binance/markets.py": FileClassification(
            "src/ai4binance/markets.py",
            "KEEP",
            (
                "tests/test_markets_migration.py",
                "tests/test_kaizen_quality.py",
            ),
            "Identity-preserving market-identifier compatibility facade is tested.",
        ),
        "src/ai4binance/observability/local.py": FileClassification(
            "src/ai4binance/observability/local.py",
            "KEEP",
            (
                "tests/test_observability_migration.py",
                "tests/test_kaizen_quality.py",
            ),
            "Identity-preserving local-observability compatibility facade is tested.",
        ),
        "src/ai4binance/github_radar/__main__.py": FileClassification(
            "src/ai4binance/github_radar/__main__.py",
            "ENTRY_POINT",
            (
                "src/ai4binance/github_radar/__main__.py",
                "tests/test_github_radar_cli.py",
            ),
            "Standalone capability-first, research-only GitHub Radar entry point.",
        ),
        "src/ai4binance/external_intel/__main__.py": FileClassification(
            "src/ai4binance/external_intel/__main__.py",
            "ENTRY_POINT",
            (
                "src/ai4binance/external_intel/__main__.py",
                "tests/test_external_intel_cli.py",
            ),
            "Standalone report-only EIEF CLI entry point.",
        ),
        "src/ai4binance/external_intel/evidence/verification.py": FileClassification(
            "src/ai4binance/external_intel/evidence/verification.py",
            "KEEP",
            ("tests/test_external_intel_evidence.py",),
            "Claim verification reducer is an EIEF evidence contract surface.",
        ),
        (
            "src/ai4binance/external_intel/normalization/deduplication.py"
        ): FileClassification(
            "src/ai4binance/external_intel/normalization/deduplication.py",
            "KEEP",
            ("tests/test_external_intel_evidence.py",),
            "Duplicate and copy clustering is an EIEF evidence contract surface.",
        ),
        (
            "src/ai4binance/external_intel/scoring/source_credibility.py"
        ): FileClassification(
            "src/ai4binance/external_intel/scoring/source_credibility.py",
            "KEEP",
            ("tests/test_external_intel_scoring.py",),
            "Source credibility scoring is an EIEF evidence contract surface.",
        ),
        "src/ai4binance/mcp/server.py": FileClassification(
            "src/ai4binance/mcp/server.py",
            "ENTRY_POINT",
            ("pyproject.toml:ai4binance-mcp", "src/ai4binance/mcp/server.py:__main__"),
            "Optional read-only MCP server entry point.",
        ),
        "src/ai4binance/ops/folder_structure_audit.py": FileClassification(
            "src/ai4binance/ops/folder_structure_audit.py",
            "ENTRY_POINT",
            (
                "src/ai4binance/ops/folder_structure_audit.py:__main__",
                "tests/test_folder_structure_audit.py",
            ),
            "Standalone folder-structure audit command with tests.",
        ),
        "src/ai4binance/ops/financial_leak_guard.py": FileClassification(
            "src/ai4binance/ops/financial_leak_guard.py",
            "ENTRY_POINT",
            (
                "scripts/quality.ps1:Financial leak guard",
                "tests/test_financial_leak_guard.py",
            ),
            "Fail-closed public artifact guard for private Binance financial values.",
        ),
        "src/ai4binance/ops/privacy_leak_guard.py": FileClassification(
            "src/ai4binance/ops/privacy_leak_guard.py",
            "ENTRY_POINT",
            (
                "scripts/quality.ps1:Privacy leak guard",
                "tests/test_privacy_leak_guard.py",
            ),
            "Fail-closed public artifact guard for KVKK, email and wallet leaks.",
        ),
        "src/ai4binance/ops/jobs.py": FileClassification(
            "src/ai4binance/ops/jobs.py",
            "KEEP",
            (
                "tests/test_agent_runtime_governance.py",
                "docs/compliance/registry_compliance_matrix.md",
            ),
            "Capability-bounded unattended job admission contract.",
        ),
        "src/ai4binance/ops/quality_triage.py": FileClassification(
            "src/ai4binance/ops/quality_triage.py",
            "ENTRY_POINT",
            (
                "src/ai4binance/ops/quality_triage.py:__main__",
                ".github/workflows/nightly_quality_triage.yml",
            ),
            "Nightly quality triage worker and MCP evidence source.",
        ),
        "src/ai4binance/ops/quality_gate/__main__.py": FileClassification(
            "src/ai4binance/ops/quality_gate/__main__.py",
            "ENTRY_POINT",
            (
                "python -m ai4binance.ops.quality_gate",
                "scripts/quality.ps1:Invoke-QualityPytestSelector",
                "tests/test_quality_gate_profiles.py",
            ),
            "Config-driven quality gate helper CLI used by the Windows wrapper.",
        ),
        "src/ai4binance/sandbox.py": FileClassification(
            "src/ai4binance/sandbox.py",
            "KEEP",
            (
                "tests/test_sandbox_migration.py",
                "tests/test_governed_extensions.py",
                "docs/compliance/registry_compliance_matrix.md",
            ),
            "Identity-preserving experiment sandbox compatibility facade is tested.",
        ),
        "src/ai4binance/security_scan.py": FileClassification(
            "src/ai4binance/security_scan.py",
            "KEEP",
            (
                "tests/test_security_scan_migration.py",
                "tests/test_governed_extensions.py",
                "docs/compliance/registry_compliance_matrix.md",
            ),
            "Identity-preserving security-scanner compatibility facade is tested.",
        ),
        "src/ai4binance/tuning/optuna_pilot.py": FileClassification(
            "src/ai4binance/tuning/optuna_pilot.py",
            "KEEP",
            ("tests/test_optuna_pilot.py",),
            "Optional Optuna benchmark pilot is tested and never promotes parameters.",
        ),
        "src/ai4binance/validation/cpcv.py": FileClassification(
            "src/ai4binance/validation/cpcv.py",
            "KEEP",
            ("tests/test_cpcv.py",),
            "CPCV diagnostic is directly tested validation evidence.",
        ),
        "src/ai4binance/validation/integrity_artifacts.py": FileClassification(
            "src/ai4binance/validation/integrity_artifacts.py",
            "KEEP",
            ("tests/test_integrity_artifacts.py",),
            "Indicator/playbook integrity artifact builder is directly tested.",
        ),
        "src/ai4binance/validation/recovery_queue.py": FileClassification(
            "src/ai4binance/validation/recovery_queue.py",
            "KEEP",
            (
                "tests/test_recovery_validation_queue.py",
                "src/ai4binance/enterprise/vnext_gap_audit.py",
            ),
            "Recovery radar candidates are queued for validation evidence safely.",
        ),
        "src/ai4binance/whale_fusion/derivatives/cross_venue.py": FileClassification(
            "src/ai4binance/whale_fusion/derivatives/cross_venue.py",
            "KEEP",
            (
                "tests/test_cross_venue_research.py",
                "docs/procedures/procedure_source_project_integration.md",
            ),
            "Cross-venue derivatives evidence is supplementary research-only context.",
        ),
        "src/ai4binance/research/virtual_runtime.py": FileClassification(
            "src/ai4binance/research/virtual_runtime.py",
            "KEEP",
            (
                "tests/test_research_application.py",
                "tests/test_whale_fusion_application.py",
                "tests/test_validation_pipeline.py",
            ),
            "Virtual runtime remains a governed research-only runtime bridge.",
        ),
        "src/ai4binance/runtime_artifacts/layout.py": FileClassification(
            "src/ai4binance/runtime_artifacts/layout.py",
            "KEEP",
            (
                "src/ai4binance/runtime_artifacts/__init__.py",
                "tests/test_runtime_artifact_layout.py",
                "tests/test_runtime_artifacts_migration.py",
                "config/governance/runtime_artifact_layout_manifest.json",
            ),
            (
                "Identity-preserving runtime artifact layout compatibility facade "
                "is tested."
            ),
        ),
    }
    return tuple(
        registry.get(
            path,
            FileClassification(
                path,
                "ARCHIVE_CANDIDATE",
                (),
                (
                    "No static registry entry exists yet; requires owner review "
                    "before archive."
                ),
            ),
        )
        for path in static_unimported
    )


def _broad_exception_reviews(
    broad_exception_sites: tuple[str, ...],
) -> tuple[BroadExceptionReview, ...]:
    narrowed = (
        BroadExceptionReview(
            "src/ai4binance/market_context.py:281",
            "NARROWED",
            ("RuntimeError", "OSError", "TimeoutError", "ValueError"),
            (
                "tests/test_governed_extensions.py::test_market_context_provider_failures_are_isolated_and_visible",
            ),
            "Keep provider fetch failures fail-closed; do not catch BaseException.",
        ),
        BroadExceptionReview(
            "src/ai4binance/market_context.py:314",
            "NARROWED",
            ("RuntimeError", "OSError", "TimeoutError", "ValueError"),
            (
                "tests/test_governed_extensions.py::test_market_context_provider_failures_are_isolated_and_visible",
            ),
            "Keep provider health failures fail-closed; do not catch BaseException.",
        ),
        BroadExceptionReview(
            "src/ai4binance/infrastructure/subprocess/sandbox.py:230",
            "NARROWED",
            ("RuntimeError", "OSError", "TimeoutError", "ValueError"),
            (
                "tests/test_governed_extensions.py::test_sandbox_executes_only_through_explicit_capable_backend",
            ),
            "Keep backend failures blocked as SANDBOX_BACKEND_FAILED.",
        ),
        BroadExceptionReview(
            "src/ai4binance/infrastructure/security/scanner.py:121",
            "NARROWED",
            ("RuntimeError", "OSError", "TimeoutError", "ValueError"),
            (
                "tests/test_governed_extensions.py::test_security_scanner_is_optional_evidence_only",
            ),
            "Keep scanner adapter failures blocked as SECURITY_SCANNER_FAILED.",
        ),
    )
    retained_by_site = {
        "src/ai4binance/application/validation_pipeline.py:493": BroadExceptionReview(
            "src/ai4binance/application/validation_pipeline.py:493",
            "RETAINED_FAIL_CLOSED_BOUNDARY",
            ("Exception",),
            (
                "tests/test_validation_pipeline.py::test_validation_failure_persists_playbook_and_run_terminal_status",
            ),
            (
                "Retain the ordinary Exception boundary so any playbook failure is "
                "persisted as FAILED before the original error is re-raised."
            ),
        ),
        "src/ai4binance/application/validation_pipeline.py:518": BroadExceptionReview(
            "src/ai4binance/application/validation_pipeline.py:518",
            "RETAINED_FAIL_CLOSED_BOUNDARY",
            ("Exception",),
            (
                "tests/test_validation_pipeline.py::test_validation_failure_persists_playbook_and_run_terminal_status",
            ),
            (
                "Retain the ordinary Exception boundary so the complete run is "
                "persisted as FAILED without swallowing the original error."
            ),
        ),
        "src/ai4binance/events/delivery.py:288": BroadExceptionReview(
            "src/ai4binance/events/delivery.py:288",
            "RETAINED_FAIL_CLOSED_BOUNDARY",
            ("Exception",),
            (
                "tests/test_event_delivery.py::test_handler_failure_preserves_offset_and_stable_idempotency_key",
                "tests/test_event_delivery.py::test_checkpoint_write_failure_is_propagated_without_false_advancement",
            ),
            (
                "Retain the ordinary Exception boundary around the application-owned "
                "durable handler and checkpoint commit so failed work cannot advance "
                "consumer progress; do not catch BaseException."
            ),
        ),
        "src/ai4binance/events/journal.py:456": BroadExceptionReview(
            "src/ai4binance/events/journal.py:456",
            "RETAINED_FAIL_CLOSED_BOUNDARY",
            ("Exception",),
            (
                "tests/test_event_delivery.py::test_ephemeral_failure_cannot_suppress_persisted_durable_delivery",
                "tests/test_event_delivery.py::test_multiple_dispatch_failures_are_preserved",
            ),
            (
                "Retain the ordinary Exception boundary around application-owned "
                "ephemeral subscribers so their failures remain visible without "
                "suppressing durable delivery; do not catch BaseException."
            ),
        ),
        "src/ai4binance/execution/live_spot.py:331": BroadExceptionReview(
            "src/ai4binance/execution/live_spot.py:331",
            "RETAINED_FAIL_CLOSED_BOUNDARY",
            ("Exception",),
            (
                "tests/test_execution_authorization.py::test_unexpected_order_attempt_exception_remains_fail_closed_after_claim",
            ),
            (
                "Retain the ordinary Exception boundary after durable authorization "
                "claim because an adapter or verifier failure cannot prove that no "
                "exchange write occurred; do not catch BaseException."
            ),
        ),
    }
    retained = tuple(
        retained_by_site[site]
        for site in broad_exception_sites
        if site in retained_by_site
    )
    deferred = tuple(
        BroadExceptionReview(
            site,
            "DEFERRED_FAIL_CLOSED_BOUNDARY",
            ("Exception",),
            ("RF-001",),
            (
                "Needs a dedicated focused test before narrowing this fail-closed "
                "runtime boundary."
            ),
        )
        for site in broad_exception_sites
        if site not in retained_by_site
    )
    return (*narrowed, *retained, *deferred)


def _count_cycles(edges: dict[str, set[str]]) -> int:
    visited: set[str] = set()
    stack: set[str] = set()
    path: list[str] = []
    cycles: set[tuple[str, ...]] = set()

    def visit(node: str) -> None:
        visited.add(node)
        stack.add(node)
        path.append(node)
        for dependency in edges[node]:
            if dependency not in visited:
                visit(dependency)
            elif dependency in stack:
                index = path.index(dependency)
                cycles.add((*path[index:], dependency))
        stack.remove(node)
        path.pop()

    for node in edges:
        if node not in visited:
            visit(node)
    return len(cycles)


def _timed(root: Path, command: tuple[str, ...]) -> float:
    started = time.perf_counter()
    # Fixed local diagnostic commands; no user-supplied command text is executed.
    subprocess.run(  # noqa: S603  # nosec B603
        command,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return (time.perf_counter() - started) * 1000


def _is_broad_exception(node: ast.ExceptHandler) -> bool:
    if isinstance(node.type, ast.Name):
        return node.type.id == "Exception"
    return isinstance(node.type, ast.Tuple) and any(
        isinstance(item, ast.Name) and item.id == "Exception" for item in node.type.elts
    )


def _is_excluded(path: Path) -> bool:
    return any(part in _EXCLUDED_PARTS for part in path.parts)


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()
