"""Fail-closed boundary coverage for architecture projection contracts."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from ai4binance.ops.architecture_projection import (
    ArchitectureProjectionComponent,
    ArchitectureProjectionImpact,
    CanonicalArchitectureProjection,
)


def component(component_id: str = "risk-engine") -> ArchitectureProjectionComponent:
    """Create one valid, evidence-only component declaration."""
    return ArchitectureProjectionComponent(
        component_id=component_id,
        canonical_domain="08_RISK",
        logical_plane="DECISION_EXECUTION",
        dependency_layer="domain",
        runtime_class="HOT_PATH_DETERMINISTIC",
        owner="RiskOwner",
        authority_effect="VETO",
        source_paths=("src/ai4binance/domain/risk.py",),
        contract_refs=("docs/contracts/risk.md",),
        test_refs=("tests/test_risk.py",),
        hot_path=True,
        deterministic=True,
        llm_dependency=False,
    )


def projection(
    components: tuple[ArchitectureProjectionComponent, ...] = (component(),),
) -> CanonicalArchitectureProjection:
    """Create a valid canonical projection for constructor boundary tests."""
    return CanonicalArchitectureProjection(
        projection_id="AI4B-ARCH-PROJECTION-001",
        components=components,
        projection_sha256="0" * 64,
    )


def impact() -> ArchitectureProjectionImpact:
    """Create a valid impact result for fail-closed constructor tests."""
    return ArchitectureProjectionImpact(
        projection_id="AI4B-ARCH-PROJECTION-001",
        projection_sha256="0" * 64,
        changed_paths=("a.py",),
        impacted_component_ids=("risk-engine",),
        unmapped_paths=(),
        blockers=(),
        status="READY",
    )


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: replace(component(), component_id=""), "component id is required"),
        (
            lambda: replace(component(), contract_refs=()),
            "contract references are required",
        ),
        (
            lambda: replace(
                component(),
                test_refs=("tests/test_risk.py", "tests/test_risk.py"),
            ),
            "must be unique",
        ),
        (
            lambda: replace(component(), live_eligibility_status="LIVE_ELIGIBLE"),
            "live-order blocked",
        ),
    ],
)
def test_component_rejects_incomplete_or_authorizing_metadata(
    factory: Callable[[], ArchitectureProjectionComponent], message: str
) -> None:
    """A projection component cannot be incomplete or become authoritative."""
    with pytest.raises(ValueError, match=message):
        factory()


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: replace(projection(), projection_id=""), "id is required"),
        (lambda: replace(projection(), components=()), "requires components"),
        (
            lambda: replace(projection(), components=(component("z"), component("a"))),
            "must be sorted",
        ),
        (
            lambda: replace(projection(), components=(component(), component())),
            "must be unique",
        ),
        (lambda: replace(projection(), projection_sha256="short"), "hash is invalid"),
        (lambda: replace(projection(), source_of_truth=True), "source of truth"),
        (lambda: replace(projection(), execution_allowed=True), "authorize execution"),
        (
            lambda: replace(projection(), live_eligibility_status="LIVE_ELIGIBLE"),
            "live-order blocked",
        ),
    ],
)
def test_projection_rejects_invalid_identity_or_authority(
    factory: Callable[[], CanonicalArchitectureProjection], message: str
) -> None:
    """The generated crosswalk cannot define authority or execution."""
    with pytest.raises(ValueError, match=message):
        factory()


def test_projection_rejects_unsafe_path_lookup() -> None:
    """Exact path lookup rejects traversal before calculating impact."""
    with pytest.raises(ValueError, match="repository-relative"):
        projection().components_for_paths(("../outside.py",))


def test_projection_and_impact_payloads_keep_safety_flags_false() -> None:
    """Read-only serialization cannot gain authority during projection."""
    assert projection().to_payload()["execution_allowed"] is False
    assert impact().to_payload()["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: replace(impact(), projection_id=""), "impact identity is invalid"),
        (
            lambda: replace(impact(), changed_paths=("a.py", "a.py")),
            "changed paths must be unique",
        ),
        (
            lambda: replace(impact(), changed_paths=("z.py", "a.py")),
            "paths must be sorted",
        ),
        (lambda: replace(impact(), changed_paths=("../a.py",)), "repository-relative"),
        (lambda: replace(impact(), status="INVALID"), "status is invalid"),
        (
            lambda: replace(impact(), unmapped_paths=("a.py",)),
            "status must reflect mapping",
        ),
        (lambda: replace(impact(), execution_allowed=True), "authorize execution"),
        (
            lambda: replace(impact(), live_eligibility_status="LIVE_ELIGIBLE"),
            "live-order blocked",
        ),
    ],
)
def test_impact_rejects_invalid_state_or_authority(
    factory: Callable[[], ArchitectureProjectionImpact], message: str
) -> None:
    """Impact results keep mapping gaps and live authority fail-closed."""
    with pytest.raises(ValueError, match=message):
        factory()
