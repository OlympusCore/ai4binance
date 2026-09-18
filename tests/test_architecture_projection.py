from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from ai4binance.ops.architecture_projection import (
    ArchitectureProjectionComponent,
    analyze_architecture_projection_impact,
    build_canonical_architecture_projection,
    render_architecture_projection_markdown,
    write_runtime_architecture_projection_markdown,
)


def _component(component_id: str, source_path: str) -> ArchitectureProjectionComponent:
    return ArchitectureProjectionComponent(
        component_id=component_id,
        canonical_domain="08_RISK",
        logical_plane="DECISION_EXECUTION",
        dependency_layer="domain",
        runtime_class="HOT_PATH_DETERMINISTIC",
        owner="RiskOwner",
        authority_effect="VETO",
        source_paths=(source_path,),
        contract_refs=("docs/contracts/risk.md",),
        test_refs=("tests/test_risk.py",),
        hot_path=True,
        deterministic=True,
        llm_dependency=False,
    )


def test_projection_is_order_independent_and_live_blocked() -> None:
    risk = _component("risk-engine", "src/ai4binance/domain/risk.py")
    evidence = _component("evidence-fusion", "src/ai4binance/domain/evidence.py")

    first = build_canonical_architecture_projection(
        projection_id="AI4B-ARCH-PROJECTION-001",
        components=(risk, evidence),
    )
    second = build_canonical_architecture_projection(
        projection_id="AI4B-ARCH-PROJECTION-001",
        components=(evidence, risk),
    )

    assert first.projection_sha256 == second.projection_sha256
    assert [item.component_id for item in first.components] == [
        "evidence-fusion",
        "risk-engine",
    ]
    assert first.source_of_truth is False
    assert first.execution_allowed is False
    assert first.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_projection_reports_only_exact_changed_source_paths() -> None:
    risk = _component("risk-engine", "src/ai4binance/domain/risk.py")
    evidence = _component("evidence-fusion", "src/ai4binance/domain/evidence.py")
    projection = build_canonical_architecture_projection(
        projection_id="AI4B-ARCH-PROJECTION-001",
        components=(risk, evidence),
    )

    impacted = projection.components_for_paths(
        ("src/ai4binance/domain/risk.py", "docs/ignored.md")
    )

    assert [component.component_id for component in impacted] == ["risk-engine"]


def test_projection_impact_blocks_every_unmapped_changed_path() -> None:
    projection = build_canonical_architecture_projection(
        projection_id="AI4B-ARCH-PROJECTION-001",
        components=(_component("risk-engine", "src/ai4binance/domain/risk.py"),),
    )

    impact = analyze_architecture_projection_impact(
        projection,
        ("docs/architecture/overview.md", "src/ai4binance/domain/risk.py"),
    )

    assert impact.status == "RUNNING_WITH_BLOCKERS"
    assert impact.impacted_component_ids == ("risk-engine",)
    assert impact.unmapped_paths == ("docs/architecture/overview.md",)
    assert impact.blockers == (
        "ARCHITECTURE_PROJECTION_UNMAPPED_PATH:docs/architecture/overview.md",
    )
    assert impact.execution_allowed is False
    assert impact.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    ("changed_paths", "message"),
    [
        ((), "requires changed paths"),
        (
            ("src/ai4binance/domain/risk.py", "src/ai4binance/domain/risk.py"),
            "paths must be unique",
        ),
        (("../risk.py",), "repository-relative"),
    ],
)
def test_projection_impact_rejects_empty_duplicate_or_unsafe_paths(
    changed_paths: tuple[str, ...], message: str
) -> None:
    projection = build_canonical_architecture_projection(
        projection_id="AI4B-ARCH-PROJECTION-001",
        components=(_component("risk-engine", "src/ai4binance/domain/risk.py"),),
    )

    with pytest.raises(ValueError, match=message):
        analyze_architecture_projection_impact(projection, changed_paths)


def test_projection_generated_view_is_evidence_only_and_stable(tmp_path: Path) -> None:
    projection = build_canonical_architecture_projection(
        projection_id="AI4B-ARCH-PROJECTION-001",
        components=(_component("risk-engine", "src/ai4binance/domain/risk.py"),),
    )

    rendered = render_architecture_projection_markdown(projection)
    output_path = write_runtime_architecture_projection_markdown(
        projection,
        tmp_path,
        Path("runtime/reports/architecture_projection.md"),
    )

    assert output_path == tmp_path / "runtime/reports/architecture_projection.md"
    assert output_path.read_text(encoding="utf-8") == rendered
    assert "content_role: GENERATED" in rendered
    assert "source_of_truth: false" in rendered
    assert "execution_allowed: false" in rendered
    assert "LIVE_ORDER_BLOCKED" in rendered


@pytest.mark.parametrize(
    ("output_path", "message"),
    [
        (Path("docs/architecture/projection.md"), "below runtime"),
        (Path("runtime/reports/projection.json"), ".md extension"),
        (Path("C:/outside-repository/projection.md"), "inside the repository"),
    ],
)
def test_projection_generated_view_writer_rejects_unsafe_destinations(
    tmp_path: Path, output_path: Path, message: str
) -> None:
    projection = build_canonical_architecture_projection(
        projection_id="AI4B-ARCH-PROJECTION-001",
        components=(_component("risk-engine", "src/ai4binance/domain/risk.py"),),
    )

    with pytest.raises(ValueError, match=message):
        write_runtime_architecture_projection_markdown(
            projection,
            tmp_path,
            output_path,
        )


def _source_of_truth_component() -> ArchitectureProjectionComponent:
    return replace(
        _component("risk-engine", "src/ai4binance/domain/risk.py"),
        source_of_truth=True,
    )


def _execution_authorizing_component() -> ArchitectureProjectionComponent:
    return replace(
        _component("risk-engine", "src/ai4binance/domain/risk.py"),
        execution_allowed=True,
    )


def _unsafe_path_component() -> ArchitectureProjectionComponent:
    return replace(
        _component("risk-engine", "src/ai4binance/domain/risk.py"),
        source_paths=("../risk.py",),
    )


def _absolute_windows_path_component() -> ArchitectureProjectionComponent:
    return replace(
        _component("risk-engine", "src/ai4binance/domain/risk.py"),
        source_paths=("C:/outside-repository/risk.py",),
    )


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (_source_of_truth_component, "source of truth"),
        (_execution_authorizing_component, "authorize execution"),
        (_unsafe_path_component, "repository-relative"),
        (_absolute_windows_path_component, "repository-relative"),
    ],
)
def test_projection_component_rejects_authority_or_unsafe_paths(
    factory: Callable[[], ArchitectureProjectionComponent], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()
