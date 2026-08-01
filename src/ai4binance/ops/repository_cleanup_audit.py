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
    "Artifacts",
    "Logs",
    "State",
    "Secrets",
    "Models",
    "Data",
    "Backtest",
    "Wallet",
    "Orders",
    "Opportunities",
}


def run_repository_cleanup_audit(workspace_root: Path) -> RepositoryCleanupAuditReport:
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
        root=_verify_root(root),
        inventory=inventory,
        folder_classifications=_folder_classifications(),
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


def _verify_root(root: Path) -> RootVerification:
    workspace_alias = Path("C:/AI-Workspace/02_Projects/ai4binance")
    junction_target: str | None = None
    if workspace_alias.exists():
        try:
            if workspace_alias.resolve() == root:
                junction_target = str(root)
        except OSError:
            junction_target = None
    return RootVerification(
        canonical_root=str(root),
        workspace_junction=str(workspace_alias) if workspace_alias.exists() else None,
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
        docs_files=count_files("Docs", ".md"),
        script_files=count_files("Scripts", ".ps1"),
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
    imports: dict[str, set[str]] = {}
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
        imports[module] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("ai4binance"):
                        imports[module].add(alias.name)
                    if alias.name == "importlib":
                        dynamic_usage.add(relative)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    dynamic_usage.add(relative)
                if node.module and node.module.startswith("ai4binance"):
                    imports[module].add(node.module)
            elif isinstance(node, ast.Call):
                name = getattr(node.func, "id", "")
                attr = getattr(node.func, "attr", "")
                if name in {"getattr", "__import__"} or attr == "import_module":
                    dynamic_usage.add(relative)
            elif isinstance(node, ast.ExceptHandler) and _is_broad_exception(node):
                broad_exceptions.append(f"{relative}:{node.lineno}")

    reverse: dict[str, set[str]] = {name: set() for name in modules}
    exact_edges: dict[str, set[str]] = {name: set() for name in modules}
    for module, dependencies in imports.items():
        for dependency in dependencies:
            if dependency in modules:
                exact_edges[module].add(dependency)
                reverse[dependency].add(module)
                continue
            for candidate in sorted(modules, key=len, reverse=True):
                if dependency.startswith(candidate + "."):
                    reverse[candidate].add(module)
                    break

    static_unimported = tuple(
        modules[module]
        for module in sorted(modules)
        if not reverse[module] and not modules[module].endswith("__init__.py")
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
                "Scripts/cleanup_generated_artifacts.ps1",
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
            tests=("pytest focused adapter tests --no-cov", "Scripts/quality.ps1"),
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
            tests=("accounting focused tests", "Scripts/quality.ps1"),
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
            tests=("Scripts/cleanup_generated_artifacts.ps1 -Mode All",),
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
                "Scripts/quality.ps1",
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
            "Artifacts/TestTemp",
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
            "Secrets",
            "Security",
            "Protected local state",
            "PROTECTED",
            "never broad-delete",
            None,
            "Only placeholder files are commit-eligible; secret contents are not read.",
        ),
        FolderClassification(
            "State/private",
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


def _classify_static_unimported(
    static_unimported: tuple[str, ...],
) -> tuple[FileClassification, ...]:
    registry: dict[str, FileClassification] = {
        "src/ai4binance/agents/advisory.py": FileClassification(
            "src/ai4binance/agents/advisory.py",
            "KEEP",
            ("tests/test_advisory_v2.py", "Docs/COMPLIANCE_MATRIX.md"),
            "Advisory v2 contract is test-backed and intentionally non-executing.",
        ),
        "src/ai4binance/agents/evaluation.py": FileClassification(
            "src/ai4binance/agents/evaluation.py",
            "KEEP",
            ("tests/test_agent_runtime_governance.py", "Docs/COMPLIANCE_MATRIX.md"),
            "Deterministic advisory trace evaluator is a governed contract surface.",
        ),
        "src/ai4binance/backtest/path_monte_carlo.py": FileClassification(
            "src/ai4binance/backtest/path_monte_carlo.py",
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
        "src/ai4binance/exchange/resilience.py": FileClassification(
            "src/ai4binance/exchange/resilience.py",
            "KEEP",
            (
                "tests/test_exchange_portfolio_resilience.py",
                "Docs/COMPLIANCE_MATRIX.md",
            ),
            "Exchange rate-limit and server-time resilience gate.",
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
        "src/ai4binance/ops/jobs.py": FileClassification(
            "src/ai4binance/ops/jobs.py",
            "KEEP",
            ("tests/test_agent_runtime_governance.py", "Docs/COMPLIANCE_MATRIX.md"),
            "Capability-bounded unattended job admission contract.",
        ),
        "src/ai4binance/ops/quality_triage.py": FileClassification(
            "src/ai4binance/ops/quality_triage.py",
            "ENTRY_POINT",
            (
                "src/ai4binance/ops/quality_triage.py:__main__",
                ".github/workflows/nightly-quality-triage.yml",
            ),
            "Nightly quality triage worker and MCP evidence source.",
        ),
        "src/ai4binance/sandbox.py": FileClassification(
            "src/ai4binance/sandbox.py",
            "KEEP",
            ("tests/test_governed_extensions.py", "Docs/COMPLIANCE_MATRIX.md"),
            "Experiment sandbox policy remains advisory and fail-closed.",
        ),
        "src/ai4binance/security_scan.py": FileClassification(
            "src/ai4binance/security_scan.py",
            "KEEP",
            ("tests/test_governed_extensions.py", "Docs/COMPLIANCE_MATRIX.md"),
            "Optional scanner adapter is evidence-only and fail-closed.",
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
        "src/ai4binance/whale_fusion/derivatives/cross_venue.py": FileClassification(
            "src/ai4binance/whale_fusion/derivatives/cross_venue.py",
            "KEEP",
            (
                "tests/test_cross_venue_research.py",
                "Docs/SOURCE_PROJECT_INTEGRATION.md",
            ),
            "Cross-venue derivatives evidence is supplementary research-only context.",
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
            "src/ai4binance/sandbox.py:229",
            "NARROWED",
            ("RuntimeError", "OSError", "TimeoutError", "ValueError"),
            (
                "tests/test_governed_extensions.py::test_sandbox_executes_only_through_explicit_capable_backend",
            ),
            "Keep backend failures blocked as SANDBOX_BACKEND_FAILED.",
        ),
        BroadExceptionReview(
            "src/ai4binance/security_scan.py:119",
            "NARROWED",
            ("RuntimeError", "OSError", "TimeoutError", "ValueError"),
            (
                "tests/test_governed_extensions.py::test_security_scanner_is_optional_evidence_only",
            ),
            "Keep scanner adapter failures blocked as SECURITY_SCANNER_FAILED.",
        ),
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
    )
    return (*narrowed, *deferred)


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
    return isinstance(node.type, ast.Name) and node.type.id == "Exception"


def _is_excluded(path: Path) -> bool:
    return any(part in _EXCLUDED_PARTS for part in path.parts)


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()
