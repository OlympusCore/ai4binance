"""Read-only architecture migration classifications for Kaizen planning."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

_CLASSIFICATION_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}


class ArchitectureModuleEvidence(Protocol):
    """Static evidence required to classify one Python module."""

    @property
    def internal_dependencies(self) -> tuple[str, ...]: ...

    @property
    def internal_dependents(self) -> tuple[str, ...]: ...

    @property
    def test_owners(self) -> tuple[str, ...]: ...

    @property
    def hotspot_reasons(self) -> tuple[str, ...]: ...


class ArchitectureMigrationAction(StrEnum):
    """Allowed evidence-only migration recommendations for source modules."""

    KEEP = "KEEP"
    MOVE = "MOVE"
    SPLIT = "SPLIT"
    MERGE = "MERGE"
    FACADE = "FACADE"
    DEPRECATE = "DEPRECATE"
    REMOVE_CANDIDATE = "REMOVE_CANDIDATE"


@dataclass(frozen=True, slots=True)
class ArchitectureMigrationClassification:
    """Deterministic, non-authoritative migration classification for one module."""

    source_path: str
    public_symbols: tuple[str, ...]
    current_role: str
    canonical_domain: str
    logical_plane: str
    runtime_class: str
    hot_path: bool
    side_effects: tuple[str, ...]
    imports: tuple[str, ...]
    imported_by: tuple[str, ...]
    entrypoint_or_dynamic_usage: tuple[str, ...]
    test_owners: tuple[str, ...]
    classification: ArchitectureMigrationAction
    target_paths: tuple[str, ...]
    facade_required: bool
    confidence: str
    blockers: tuple[str, ...]
    rollback_unit: str

    def __post_init__(self) -> None:
        if not self.source_path.startswith("src/ai4binance/"):
            raise ValueError("architecture source path must be repository-relative")
        if not self.current_role.strip():
            raise ValueError("architecture current role is required")
        if not self.canonical_domain.strip() or not self.logical_plane.strip():
            raise ValueError(
                "architecture canonical domain and logical plane are required"
            )
        if not self.runtime_class.strip():
            raise ValueError("architecture runtime class is required")
        if self.confidence not in _CLASSIFICATION_CONFIDENCE:
            raise ValueError("architecture classification confidence is invalid")
        if (
            self.classification
            in {
                ArchitectureMigrationAction.KEEP,
                ArchitectureMigrationAction.MOVE,
                ArchitectureMigrationAction.SPLIT,
                ArchitectureMigrationAction.MERGE,
                ArchitectureMigrationAction.FACADE,
            }
            and not self.target_paths
        ):
            raise ValueError("architecture migration target paths are required")
        if (
            self.classification is ArchitectureMigrationAction.FACADE
            and not self.facade_required
        ):
            raise ValueError("facade classifications must preserve a facade")
        if not self.rollback_unit.strip():
            raise ValueError("architecture rollback unit is required")

    def to_payload(self) -> dict[str, object]:
        return {
            "source_path": self.source_path,
            "public_symbols": list(self.public_symbols),
            "current_role": self.current_role,
            "canonical_domain": self.canonical_domain,
            "logical_plane": self.logical_plane,
            "runtime_class": self.runtime_class,
            "hot_path": self.hot_path,
            "side_effects": list(self.side_effects),
            "imports": list(self.imports),
            "imported_by": list(self.imported_by),
            "entrypoint_or_dynamic_usage": list(self.entrypoint_or_dynamic_usage),
            "test_owners": list(self.test_owners),
            "classification": self.classification.value,
            "target_paths": list(self.target_paths),
            "facade_required": self.facade_required,
            "confidence": self.confidence,
            "blockers": list(self.blockers),
            "rollback_unit": self.rollback_unit,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class _ArchitectureMigrationRule:
    action: ArchitectureMigrationAction
    current_role: str
    canonical_domain: str
    logical_plane: str
    runtime_class: str
    hot_path: bool
    target_paths: tuple[str, ...]
    facade_required: bool = False
    confidence: str = "MEDIUM"
    blockers: tuple[str, ...] = ()


def build_architecture_migration_classification(
    *,
    source_root: Path,
    source_path: Path,
    baseline: ArchitectureModuleEvidence,
) -> ArchitectureMigrationClassification:
    relative_path = source_path.relative_to(source_root).as_posix()
    repository_path = f"src/ai4binance/{relative_path}"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    rule = _architecture_migration_rule(relative_path)
    entrypoint_usage = _entrypoint_or_dynamic_usage(relative_path, tree)
    side_effects = _side_effect_signals(tree)
    facade_required = rule.facade_required and (
        rule.action is ArchitectureMigrationAction.FACADE
        or bool(baseline.internal_dependents)
        or bool(baseline.test_owners)
        or bool(entrypoint_usage)
    )
    blockers = list(rule.blockers)
    if (
        baseline.hotspot_reasons
        and rule.action is not ArchitectureMigrationAction.SPLIT
    ):
        blockers.append("HOTSPOT_DECOMPOSITION_REVIEW_REQUIRED")
    if entrypoint_usage:
        blockers.append("ENTRYPOINT_OR_DYNAMIC_USAGE_REVIEW_REQUIRED")
    if baseline.internal_dependents and rule.action in {
        ArchitectureMigrationAction.MOVE,
        ArchitectureMigrationAction.SPLIT,
        ArchitectureMigrationAction.MERGE,
    }:
        blockers.append("IMPORT_MIGRATION_REQUIRED")
    if side_effects and rule.action in {
        ArchitectureMigrationAction.MOVE,
        ArchitectureMigrationAction.SPLIT,
        ArchitectureMigrationAction.MERGE,
    }:
        blockers.append("SIDE_EFFECT_BOUNDARY_REVIEW_REQUIRED")
    if not baseline.test_owners:
        blockers.append("TEST_OWNERSHIP_EVIDENCE_MISSING")
    if facade_required:
        blockers.append("PUBLIC_IMPORT_COMPATIBILITY_REQUIRED")
    return ArchitectureMigrationClassification(
        source_path=repository_path,
        public_symbols=_public_symbols(tree),
        current_role=rule.current_role,
        canonical_domain=rule.canonical_domain,
        logical_plane=rule.logical_plane,
        runtime_class=rule.runtime_class,
        hot_path=rule.hot_path,
        side_effects=side_effects,
        imports=baseline.internal_dependencies,
        imported_by=baseline.internal_dependents,
        entrypoint_or_dynamic_usage=entrypoint_usage,
        test_owners=baseline.test_owners,
        classification=rule.action,
        target_paths=rule.target_paths,
        facade_required=facade_required,
        confidence=rule.confidence,
        blockers=tuple(sorted(set(blockers))),
        rollback_unit=f"RESTORE_SOURCE_AND_IMPORTS:{repository_path}",
    )


def _architecture_migration_rule(relative_path: str) -> _ArchitectureMigrationRule:
    facade_targets = {
        "cli.py": "src/ai4binance/cli/__main__.py",
        "application/virtual_runtime.py": (
            "src/ai4binance/application/services/virtual_runtime.py"
        ),
        "application/whale_fusion.py": (
            "src/ai4binance/application/orchestration/whale_fusion.py"
        ),
        "cli/output.py": "src/ai4binance/cli/presentation/output.py",
        "cli/parser.py": "src/ai4binance/cli/bootstrap/parser.py",
        "cli/shared.py": "src/ai4binance/cli/bootstrap/shared.py",
        "cli/skill_discovery.py": ("src/ai4binance/cli/bootstrap/skill_discovery.py"),
        "core/exchange_errors.py": "src/ai4binance/core/errors/exchange.py",
        "exchange/errors.py": "src/ai4binance/core/errors/exchange.py",
        "infrastructure/opportunity_artifact_loader.py": (
            "src/ai4binance/infrastructure/filesystem/opportunity_artifact_loader.py"
        ),
        "markets.py": "src/ai4binance/domain/market/markets.py",
        "observability/__init__.py": (
            "src/ai4binance/infrastructure/observability/__init__.py"
        ),
        "observability/local.py": (
            "src/ai4binance/infrastructure/observability/local.py"
        ),
        "runtime_artifacts/__init__.py": (
            "src/ai4binance/infrastructure/filesystem/runtime_artifacts/__init__.py"
        ),
        "runtime_artifacts/layout.py": (
            "src/ai4binance/infrastructure/filesystem/runtime_artifacts/layout.py"
        ),
        "sandbox.py": "src/ai4binance/infrastructure/subprocess/sandbox.py",
        "security_scan.py": "src/ai4binance/infrastructure/security/scanner.py",
        "universe/filters.py": "src/ai4binance/domain/market/filters.py",
    }
    if relative_path == "__init__.py":
        return _keep_rule_for_target(relative_path, "src/ai4binance")
    if relative_path in facade_targets:
        return _facade_rule_for_target(facade_targets[relative_path])
    root_file_rule = _root_file_migration_rule(relative_path)
    if root_file_rule is not None:
        return root_file_rule
    root = relative_path.split("/", maxsplit=1)[0]
    if root in {
        "core",
        "domain",
        "application",
        "compatibility",
        "infrastructure",
        "integrations",
        "cli",
    }:
        return _target_tree_migration_rule(relative_path)
    return _legacy_package_migration_rule(relative_path)


def _root_file_migration_rule(
    relative_path: str,
) -> _ArchitectureMigrationRule | None:
    if relative_path in {"reporting.py", "opportunity_report.py"}:
        return _ArchitectureMigrationRule(
            action=ArchitectureMigrationAction.MERGE,
            current_role="SERIALIZATION_AND_REPORTING",
            canonical_domain="14_EVIDENCE",
            logical_plane="DATA & EVIDENCE PLANE",
            runtime_class="SHARED_CONTRACT",
            hot_path=False,
            target_paths=("src/ai4binance/core/serialization/primitives.py",),
            facade_required=True,
            blockers=("SEMANTIC_PARITY_REQUIRED",),
        )
    split_targets = {
        "domain.py": "domain/decision|domain/risk|domain/validation",
        "historical_replay_evaluation.py": (
            "domain/research|domain/portfolio|domain/evidence|"
            "application/orchestration|infrastructure/persistence"
        ),
        "historical_replay_state.py": (
            "domain/portfolio|domain/evidence|infrastructure/persistence"
        ),
        "internal_radar.py": (
            "domain/evidence|application/pipelines|infrastructure/filesystem"
        ),
        "opportunity_radar.py": "domain/intelligence|application/pipelines",
        "rag.py": "domain/intelligence|domain/evidence|integrations/llm",
        "rag_corrective.py": (
            "domain/intelligence|application/pipelines|integrations/llm"
        ),
        "research_runtime.py": (
            "domain/research|application/pipelines|infrastructure/filesystem"
        ),
        "schemas.py": "core/contracts|core/serialization",
        "virtual_wallet_journal.py": (
            "domain/portfolio|domain/evidence|application/services|"
            "infrastructure/persistence"
        ),
    }
    if relative_path in split_targets:
        return _split_migration_rule(
            role="MIXED_LEGACY_MODULE",
            target_paths=_target_paths(split_targets[relative_path]),
        )
    move_targets = {
        "config.py": "infrastructure/configuration/settings.py",
        "decision.py": "domain/decision/model.py",
        "governance_primitives.py": "domain/governance/primitives.py",
        "historical_replay_application.py": (
            "application/orchestration/historical_replay.py"
        ),
        "historical_replay_persistence.py": (
            "infrastructure/persistence/historical_replay.py"
        ),
        "indicators.py": "domain/features/indicators.py",
        "internal_radar_vision.py": "integrations/llm/internal_radar_vision.py",
        "market_context.py": "domain/snapshot/market_context.py",
        "markets.py": "domain/market/markets.py",
        "opportunities.py": "domain/setup/opportunities.py",
        "opportunity_intelligence.py": (
            "domain/intelligence/opportunity_intelligence.py"
        ),
        "opportunity_ledger.py": "infrastructure/persistence/opportunity_ledger.py",
        "opportunity_outcomes.py": "domain/research/opportunity_outcomes.py",
        "opportunity_policy.py": "domain/strategy/opportunity_policy.py",
        "opportunity_scanner.py": ("domain/intelligence/opportunity_scanner.py"),
        "privacy_boundary.py": "infrastructure/security/privacy_boundary.py",
        "research_catalog.py": "domain/research/catalog.py",
        "research_governance.py": "domain/research/governance.py",
        "risk.py": "domain/risk/model.py",
        "runtime_research_context.py": "domain/snapshot/research_context.py",
        "safety.py": "domain/risk/safety.py",
        "sandbox.py": "infrastructure/subprocess/sandbox.py",
        "schema_validation.py": "core/serialization/schema_validation.py",
        "scoring.py": "domain/strategy/scoring.py",
        "security_scan.py": "infrastructure/security/scanner.py",
        "validation_pipeline_runtime.py": (
            "application/pipelines/validation_runtime.py"
        ),
        "wire_contracts.py": "core/contracts/wire.py",
    }
    target = move_targets.get(relative_path)
    return (
        _move_rule_for_target(f"src/ai4binance/{target}", confidence="HIGH")
        if target is not None
        else None
    )


def _target_tree_migration_rule(relative_path: str) -> _ArchitectureMigrationRule:
    root = relative_path.split("/", maxsplit=1)[0]
    if relative_path == "domain/market/markets.py":
        return _keep_rule_for_target(
            relative_path,
            "src/ai4binance/domain/market",
        )
    if relative_path.startswith("domain/research/"):
        return _keep_rule_for_target(
            relative_path,
            "src/ai4binance/domain/research",
        )
    if relative_path.startswith("infrastructure/security/"):
        return _keep_rule_for_target(
            relative_path,
            "src/ai4binance/infrastructure/security",
        )
    exact_moves = {
        "domain/memory.py": "domain/learning/memory.py",
        "domain/memory_metrics.py": "domain/learning/memory_metrics.py",
        "domain/opportunity_observation.py": (
            "domain/evidence/opportunity_observation.py"
        ),
        "domain/universe.py": "domain/market/universe.py",
    }
    if relative_path in exact_moves:
        return _move_rule_for_target(
            f"src/ai4binance/{exact_moves[relative_path]}",
            confidence="HIGH",
        )
    if relative_path == "domain/__init__.py":
        return _facade_rule_for_target("src/ai4binance/domain/__init__.py")
    if relative_path == "infrastructure/persistence/safe_json.py":
        return _split_migration_rule(
            role="MIXED_SERIALIZATION_AND_PERSISTENCE",
            target_paths=_target_paths("core/serialization|infrastructure/persistence"),
        )
    if root == "application":
        return _application_migration_rule(relative_path)
    if root == "compatibility":
        return _keep_rule_for_target(
            relative_path,
            "src/ai4binance/compatibility",
            confidence="HIGH",
            blockers=("COMPATIBILITY_BOUNDARY_REVIEW_REQUIRED",),
        )
    if root == "cli":
        return _cli_migration_rule(relative_path)
    confidence = "LOW" if root == "domain" else "HIGH"
    blockers = ("CANONICAL_DOMAIN_REVIEW_REQUIRED",) if root == "domain" else ()
    return _keep_rule_for_target(
        relative_path,
        f"src/ai4binance/{root}",
        confidence=confidence,
        blockers=blockers,
    )


def _application_migration_rule(relative_path: str) -> _ArchitectureMigrationRule:
    if relative_path == "application/__init__.py" or relative_path.startswith(
        "application/orchestration/"
    ):
        return _keep_rule_for_target(
            relative_path,
            "src/ai4binance/application",
        )
    prefix_moves = {
        "application/context/": "application/services/context/",
        "application/governance/": "application/services/governance/",
    }
    for prefix, target_prefix in prefix_moves.items():
        if relative_path.startswith(prefix):
            return _move_rule_for_target(
                "src/ai4binance/" + target_prefix + relative_path.removeprefix(prefix)
            )
    move_targets = {
        "learning_loop.py": "application/pipelines/learning_loop.py",
        "live_readiness.py": "application/services/live_readiness.py",
        "opportunity_observation.py": (
            "application/use_cases/opportunity_observation.py"
        ),
        "research.py": "application/use_cases/research.py",
        "runtime.py": "application/orchestration/runtime.py",
        "validation_pipeline.py": "application/pipelines/validation.py",
        "virtual_runtime_eligibility.py": (
            "domain/validation/virtual_runtime_eligibility.py"
        ),
        "virtual_runtime_evidence.py": ("domain/evidence/virtual_runtime_evidence.py"),
        "virtual_runtime_performance.py": (
            "domain/portfolio/virtual_runtime_performance.py"
        ),
        "virtual_runtime_portfolio.py": (
            "domain/portfolio/virtual_runtime_portfolio.py"
        ),
        "whale_fusion.py": "application/orchestration/whale_fusion.py",
    }
    leaf = relative_path.removeprefix("application/")
    target = move_targets.get(leaf)
    if target is not None:
        return _move_rule_for_target(
            f"src/ai4binance/{target}",
            confidence="HIGH",
        )
    return _keep_rule_for_target(
        relative_path,
        "src/ai4binance/application",
        confidence="LOW",
        blockers=("APPLICATION_TARGET_REVIEW_REQUIRED",),
    )


def _cli_migration_rule(relative_path: str) -> _ArchitectureMigrationRule:
    if relative_path.startswith(
        ("cli/bootstrap/", "cli/commands/", "cli/presentation/")
    ):
        return _keep_rule_for_target(relative_path, "src/ai4binance/cli")
    if relative_path == "cli/commands.py":
        return _split_migration_rule(
            role="CLI_COMMAND_AGGREGATE",
            target_paths=("src/ai4binance/cli/commands",),
            facade_required=True,
        )
    leaf = relative_path.rsplit("/", maxsplit=1)[-1]
    if leaf == "output.py":
        target = "cli/presentation/output.py"
    elif leaf in {"parser.py", "shared.py", "skill_discovery.py"}:
        target = f"cli/bootstrap/{leaf}"
    else:
        target = f"cli/commands/{leaf}"
    return _move_rule_for_target(
        f"src/ai4binance/{target}",
        confidence="HIGH",
    )


def _legacy_package_migration_rule(
    relative_path: str,
) -> _ArchitectureMigrationRule:
    root, separator, tail = relative_path.partition("/")
    if not separator:
        return _unresolved_keep_rule(relative_path)
    if relative_path == "research/virtual_runtime.py":
        return _split_migration_rule(
            role="MIXED_VIRTUAL_RESEARCH_RUNTIME",
            target_paths=_target_paths(
                "domain/research|domain/portfolio|domain/evidence|application/services"
            ),
            facade_required=True,
        )
    if relative_path == "research/virtual_runtime_attribution.py":
        return _facade_rule_for_target(
            "src/ai4binance/domain/research/virtual_runtime_attribution.py"
        )
    direct_bases = {
        "allocation": "domain/portfolio/allocation",
        "comparison": "domain/intelligence/comparison",
        "funding": "domain/portfolio/funding",
        "intelligence": "domain/intelligence",
        "observability": "infrastructure/observability",
        "outlook": "domain/intelligence/outlook",
        "runtime_artifacts": "infrastructure/filesystem/runtime_artifacts",
        "storage": "infrastructure/persistence/storage",
        "strategies": "domain/strategy",
        "universe": "domain/market",
    }
    if root in direct_bases:
        return _move_rule_for_target(
            f"src/ai4binance/{direct_bases[root]}/{tail}",
            confidence="HIGH",
        )
    candidate_spec = _legacy_target_candidate_specs().get(root)
    if candidate_spec is None:
        return _unresolved_keep_rule(relative_path)
    candidates = _target_paths(candidate_spec)
    if tail == "__init__.py":
        return _split_migration_rule(
            role="MIXED_LEGACY_PACKAGE_API",
            target_paths=candidates,
            facade_required=True,
        )
    target_base = _select_target_base(relative_path, candidates)
    return _move_rule_for_target(
        f"{target_base}/{root}/{tail}",
        blockers=("RULE_BASED_TARGET_REVIEW_REQUIRED",),
    )


def _legacy_target_candidate_specs() -> dict[str, str]:
    return {
        "account": "domain/portfolio",
        "accounting": (
            "domain/portfolio|domain/evidence|cli/presentation|integrations/binance"
        ),
        "agents": (
            "domain/intelligence|domain/evidence|domain/risk|domain/validation|"
            "application/orchestration|integrations/llm"
        ),
        "cli_parts": "cli/commands|cli/presentation|cli/bootstrap",
        "content": (
            "application/services|application/orchestration|"
            "application/ports/outbound|domain/evidence|"
            "infrastructure/persistence|cli/presentation"
        ),
        "data": (
            "domain/market|domain/snapshot|domain/features|domain/evidence|"
            "infrastructure/persistence|integrations/binance"
        ),
        "enterprise": (
            "application/services|domain/governance|domain/evidence|"
            "infrastructure/observability|infrastructure/persistence|"
            "cli/presentation"
        ),
        "events": ("core/contracts|infrastructure/event_fabric|infrastructure/clocks"),
        "exchange": ("domain/market|domain/validation|integrations/binance"),
        "execution": (
            "domain/execution|domain/evidence|application/use_cases|"
            "integrations/binance"
        ),
        "external_intel": (
            "domain/technology_intelligence|domain/evidence|"
            "application/ports/outbound|infrastructure/persistence|"
            "integrations/external_intelligence|integrations/news|cli/commands"
        ),
        "github_radar": (
            "domain/technology_intelligence|domain/evidence|"
            "infrastructure/persistence|integrations/external_intelligence"
        ),
        "governance": (
            "domain/governance|infrastructure/security|infrastructure/observability"
        ),
        "learning": "domain/learning|infrastructure/persistence",
        "local_agent": ("domain/evidence|application/orchestration|integrations/llm"),
        "mcp": (
            "application/ports/inbound|integrations/mcp_clients|infrastructure/security"
        ),
        "multiops": (
            "core/contracts|application/services|domain/governance|"
            "infrastructure/observability"
        ),
        "ontology": "core/contracts|domain/governance",
        "ops": (
            "application/use_cases|infrastructure/observability|"
            "infrastructure/filesystem|infrastructure/security"
        ),
        "portfolio": (
            "domain/portfolio|domain/risk|domain/evidence|application/orchestration"
        ),
        "research": (
            "domain/research|domain/portfolio|domain/risk|domain/execution|"
            "domain/evidence|infrastructure/persistence"
        ),
        "scanners": "domain/intelligence|application/orchestration",
        "skills": (
            "application/services|application/orchestration|"
            "domain/governance|integrations/external_intelligence"
        ),
        "trust": "domain/governance|domain/evidence|domain/validation",
        "tuning": (
            "domain/research|domain/learning|domain/validation|"
            "infrastructure/persistence"
        ),
        "validation": (
            "domain/validation|domain/evidence|application/scheduling|"
            "infrastructure/persistence"
        ),
        "voice": (
            "application/ports/inbound|application/orchestration|cli/presentation"
        ),
        "whale_fusion": (
            "domain/intelligence|domain/evidence|application/orchestration|"
            "integrations/binance|integrations/onchain|"
            "integrations/external_intelligence"
        ),
    }


def _target_paths(specification: str) -> tuple[str, ...]:
    return tuple(f"src/ai4binance/{path}" for path in specification.split("|"))


def _select_target_base(
    relative_path: str,
    candidates: tuple[str, ...],
) -> str:
    normalized = relative_path.lower().replace("-", "_")
    preferences = (
        ("private|privacy|security|gateway|tool_policy", "infrastructure/security"),
        ("risk", "domain/risk"),
        (
            "validation|integrity|overfit|walk_forward|quality|compliance|promotion",
            "domain/validation|domain/governance",
        ),
        (
            "evidence|audit|report|ledger|telemetry|traceability",
            "domain/evidence|infrastructure/observability",
        ),
        ("storage|archive|journal|queue|local_baseline", "infrastructure/persistence"),
        ("clock", "infrastructure/clocks"),
        ("event|bus|trigger", "infrastructure/event_fabric"),
        (
            "client|transport|provider|stream|retrieval|feed|radar",
            "integrations/",
        ),
        ("contract|interface|enum|/ids.|models", "core/contracts"),
        (
            "orchestr|workflow|runtime|runner|job|agent",
            "application/orchestration|application/services|application/use_cases",
        ),
        ("policy|governance|authority|approval", "domain/governance"),
        (
            "feature|fusion|score|classifier|analy|technical",
            "domain/intelligence|domain/technology_intelligence",
        ),
        ("output|dashboard|localization", "cli/presentation"),
    )
    for keyword_spec, target_spec in preferences:
        if not any(word in normalized for word in keyword_spec.split("|")):
            continue
        for target_fragment in target_spec.split("|"):
            for candidate in candidates:
                if f"/{target_fragment}" in candidate:
                    return candidate
    return candidates[0]


def _keep_rule_for_target(
    relative_path: str,
    target_root: str,
    *,
    confidence: str = "HIGH",
    blockers: tuple[str, ...] = (),
) -> _ArchitectureMigrationRule:
    role, domain, plane, runtime_class, hot_path = _target_path_metadata(
        target_root.rstrip("/") + "/"
    )
    return _ArchitectureMigrationRule(
        action=ArchitectureMigrationAction.KEEP,
        current_role=role,
        canonical_domain=domain,
        logical_plane=plane,
        runtime_class=runtime_class,
        hot_path=hot_path,
        target_paths=(f"src/ai4binance/{relative_path}",),
        confidence=confidence,
        blockers=blockers,
    )


def _unresolved_keep_rule(relative_path: str) -> _ArchitectureMigrationRule:
    return _keep_rule_for_target(
        relative_path,
        "src/ai4binance",
        confidence="LOW",
        blockers=("ARCHITECTURE_CLASSIFICATION_RULE_MISSING",),
    )


def _move_rule_for_target(
    target_path: str,
    *,
    confidence: str = "MEDIUM",
    blockers: tuple[str, ...] = (),
) -> _ArchitectureMigrationRule:
    role, domain, plane, runtime_class, hot_path = _target_path_metadata(target_path)
    return _ArchitectureMigrationRule(
        action=ArchitectureMigrationAction.MOVE,
        current_role=role,
        canonical_domain=domain,
        logical_plane=plane,
        runtime_class=runtime_class,
        hot_path=hot_path,
        target_paths=(target_path,),
        facade_required=True,
        confidence=confidence,
        blockers=blockers,
    )


def _facade_rule_for_target(target_path: str) -> _ArchitectureMigrationRule:
    role, domain, plane, runtime_class, hot_path = _target_path_metadata(target_path)
    return _ArchitectureMigrationRule(
        action=ArchitectureMigrationAction.FACADE,
        current_role=f"LEGACY_{role}_API",
        canonical_domain=domain,
        logical_plane=plane,
        runtime_class=runtime_class,
        hot_path=hot_path,
        target_paths=(target_path,),
        facade_required=True,
        confidence="HIGH",
    )


def _split_migration_rule(
    *,
    role: str,
    target_paths: tuple[str, ...],
    facade_required: bool = False,
) -> _ArchitectureMigrationRule:
    return _ArchitectureMigrationRule(
        action=ArchitectureMigrationAction.SPLIT,
        current_role=role,
        canonical_domain="UNRESOLVED",
        logical_plane="CROSS_PLANE_REVIEW_REQUIRED",
        runtime_class="MIXED_RUNTIME_CLASS",
        hot_path=False,
        target_paths=target_paths,
        facade_required=facade_required,
        blockers=(
            "CANONICAL_DOMAIN_SPLIT_REQUIRED",
            "TARGET_DECOMPOSITION_REQUIRED",
        ),
    )


def _target_path_metadata(
    target_path: str,
) -> tuple[str, str, str, str, bool]:
    specifications = {
        "/core/contracts/": (
            "CONTRACT|01_REGISTRIES|DATA & EVIDENCE PLANE|SHARED_CONTRACT|1"
        ),
        "/core/serialization/": (
            "SERIALIZATION|01_REGISTRIES|DATA & EVIDENCE PLANE|SHARED_CONTRACT|1"
        ),
        "/domain/market/": (
            "MARKET_DATA|02_MARKET_DATA|DATA & EVIDENCE PLANE|DETERMINISTIC_HOT_PATH|1"
        ),
        "/domain/snapshot/": (
            "SHARED_SNAPSHOT|03_SHARED_MARKET_STATE|DATA & EVIDENCE PLANE|"
            "DETERMINISTIC_HOT_PATH|1"
        ),
        "/domain/technology_intelligence/": (
            "TECHNOLOGY_INTELLIGENCE|04_INTELLIGENCE|INTELLIGENCE PLANE|"
            "RESEARCH_COLD_PATH|0"
        ),
        "/domain/intelligence/": (
            "INTELLIGENCE|04_INTELLIGENCE|INTELLIGENCE PLANE|ANALYTICAL_HOT_PATH|1"
        ),
        "/domain/features/": (
            "CANONICAL_FEATURES|05_DETERMINISTIC_ANALYTICS|INTELLIGENCE PLANE|"
            "DETERMINISTIC_HOT_PATH|1"
        ),
        "/domain/strategy/": (
            "STRATEGY|05_DETERMINISTIC_ANALYTICS|INTELLIGENCE PLANE|"
            "DETERMINISTIC_HOT_PATH|1"
        ),
        "/domain/setup/": (
            "SETUP|06_AGENT_OBSERVATIONS|INTELLIGENCE PLANE|DETERMINISTIC_HOT_PATH|1"
        ),
        "/domain/decision/": (
            "DECISION|07_DECISION|DECISION & EXECUTION PLANE|DETERMINISTIC_HOT_PATH|1"
        ),
        "/domain/risk/": (
            "RISK|08_RISK|DECISION & EXECUTION PLANE|DETERMINISTIC_HOT_PATH|1"
        ),
        "/domain/portfolio/": (
            "PORTFOLIO|09_PORTFOLIO|DECISION & EXECUTION PLANE|DETERMINISTIC_HOT_PATH|1"
        ),
        "/domain/execution/": (
            "EXECUTION|10_EXECUTION|DECISION & EXECUTION PLANE|DETERMINISTIC_HOT_PATH|1"
        ),
        "/domain/validation/": (
            "VALIDATION|11_VALIDATION|CONTROL & ASSURANCE PLANE|"
            "DETERMINISTIC_HOT_PATH|1"
        ),
        "/domain/learning/": (
            "LEARNING|12_LEARNING|CONTROL & ASSURANCE PLANE|RESEARCH_COLD_PATH|0"
        ),
        "/domain/governance/": (
            "GOVERNANCE|13_GOVERNANCE|CONTROL & ASSURANCE PLANE|GOVERNED_CONTROL|0"
        ),
        "/domain/evidence/": (
            "EVIDENCE|14_EVIDENCE|DATA & EVIDENCE PLANE|EVIDENCE_PROCESSING|0"
        ),
        "/domain/research/": (
            "RESEARCH|18_RESEARCH_CAPABILITY|INTELLIGENCE PLANE|RESEARCH_COLD_PATH|0"
        ),
        "/infrastructure/security/": (
            "SECURITY_ADAPTER|16_SECURITY|CONTROL & ASSURANCE PLANE|GOVERNED_CONTROL|0"
        ),
        "/infrastructure/observability/": (
            "OBSERVABILITY_ADAPTER|15_AUDIT_OBSERVABILITY|"
            "CONTROL & ASSURANCE PLANE|GOVERNED_CONTROL|0"
        ),
        "/infrastructure/event_fabric/": (
            "EVENT_FABRIC_ADAPTER|17_EVENT_FABRIC|"
            "ORCHESTRATION + EVENT FABRIC|IO_ADAPTER|1"
        ),
        "/infrastructure/": (
            "INFRASTRUCTURE_ADAPTER|14_EVIDENCE|DATA & EVIDENCE PLANE|IO_ADAPTER|0"
        ),
        "/integrations/binance/": (
            "BINANCE_ADAPTER|02_MARKET_DATA|DATA & EVIDENCE PLANE|IO_ADAPTER|0"
        ),
        "/integrations/": (
            "EXTERNAL_INTEGRATION_ADAPTER|04_INTELLIGENCE|"
            "DATA & EVIDENCE PLANE|IO_ADAPTER|0"
        ),
        "/application/": (
            "APPLICATION_SERVICE|00_META|ORCHESTRATION + EVENT FABRIC|"
            "GOVERNED_ORCHESTRATION|0"
        ),
        "/cli/": (
            "CLI_ADAPTER|00_META|ORCHESTRATION + EVENT FABRIC|PRESENTATION_ADAPTER|0"
        ),
        "/core/": (
            "CORE_CONTRACT|01_REGISTRIES|DATA & EVIDENCE PLANE|SHARED_CONTRACT|1"
        ),
        "/domain/": (
            "DOMAIN_CAPABILITY|00_META|DATA & EVIDENCE PLANE|DETERMINISTIC_HOT_PATH|1"
        ),
    }
    for marker, specification in specifications.items():
        if marker not in target_path:
            continue
        role, domain, plane, runtime_class, hot_path = specification.split("|")
        return role, domain, plane, runtime_class, hot_path == "1"
    return (
        "UNRESOLVED_MODULE",
        "00_META",
        "ORCHESTRATION + EVENT FABRIC",
        "UNCLASSIFIED_RUNTIME",
        False,
    )


def _public_symbols(tree: ast.Module) -> tuple[str, ...]:
    declared_exports: set[str] = set()
    discovered: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                discovered.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            names = _assignment_names(node)
            discovered.update(name for name in names if not name.startswith("_"))
            if "__all__" in names:
                value = node.value
                if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
                    declared_exports.update(
                        item.value
                        for item in value.elts
                        if isinstance(item, ast.Constant)
                        and isinstance(item.value, str)
                    )
    return tuple(sorted(declared_exports or discovered))


def _assignment_names(
    node: ast.Assign | ast.AnnAssign,
) -> tuple[str, ...]:
    targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
    return tuple(target.id for target in targets if isinstance(target, ast.Name))


def _entrypoint_or_dynamic_usage(
    relative_path: str,
    tree: ast.Module,
) -> tuple[str, ...]:
    signals: set[str] = set()
    if relative_path.endswith("/__main__.py"):
        signals.add("PACKAGE_ENTRYPOINT")
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_module_main_guard(node.test):
            signals.add("MODULE_ENTRYPOINT")
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        if call_name in {"__import__", "import_module"}:
            signals.add("DYNAMIC_IMPORT")
        if call_name in {"getattr", "setattr", "delattr"}:
            signals.add("DYNAMIC_ATTRIBUTE_ACCESS")
    return tuple(sorted(signals))


def _is_module_main_guard(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "__name__"
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.Eq)
        and len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Constant)
        and node.comparators[0].value == "__main__"
    )


def _side_effect_signals(tree: ast.Module) -> tuple[str, ...]:
    signals: set[str] = set()
    external_io_imports = {
        "httpx",
        "requests",
        "socket",
        "sqlite3",
        "subprocess",
        "urllib",
    }
    io_calls = {
        "connect",
        "mkdir",
        "open",
        "popen",
        "replace",
        "request",
        "run",
        "unlink",
        "urlopen",
        "write_bytes",
        "write_text",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(
                alias.name.split(".", maxsplit=1)[0] in external_io_imports
                for alias in node.names
            ):
                signals.add("EXTERNAL_IO_DEPENDENCY")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".", maxsplit=1)[0] in external_io_imports:
                signals.add("EXTERNAL_IO_DEPENDENCY")
        elif isinstance(node, ast.Call):
            if _call_name(node.func).lower() in io_calls:
                signals.add("POTENTIAL_IO_CALL")
    for node in tree.body:
        value: ast.expr | None = None
        if isinstance(node, ast.Expr):
            value = node.value
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
        if isinstance(value, ast.Call):
            signals.add("TOP_LEVEL_CALL")
    return tuple(sorted(signals))


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
