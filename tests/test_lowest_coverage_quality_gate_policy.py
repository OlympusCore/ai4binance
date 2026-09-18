"""Fail-closed unit coverage for quality-gate policy parsing and selection."""

from pathlib import Path

import pytest

from ai4binance.ops.quality_gate import policy as quality_policy


def test_policy_parsing_helpers_reject_wrong_shape_without_guessing() -> None:
    with pytest.raises(ValueError, match="mapping"):
        quality_policy._affected_mapping("invalid")
    with pytest.raises(ValueError, match="mapping: profiles"):
        quality_policy._mapping({}, "profiles")
    with pytest.raises(ValueError, match="mapping: profiles"):
        quality_policy._optional_mapping({"profiles": []}, "profiles")
    with pytest.raises(ValueError, match="list: mappings"):
        quality_policy._sequence({}, "mappings")
    with pytest.raises(ValueError, match="list: mappings"):
        quality_policy._optional_sequence({"mappings": "invalid"}, "mappings")
    assert quality_policy._string_sequence("invalid") == ()
    assert quality_policy._matches_any_prefix("src/x.py", ("docs/",)) is False
    assert quality_policy._matching_prefix_length("src/x.py", ("docs/",)) == -1


def test_policy_helpers_keep_only_existing_tests_and_most_specific_mapping(
    tmp_path: Path,
) -> None:
    test_path = tmp_path / "tests" / "test_example.py"
    test_path.parent.mkdir()
    test_path.write_text("def test_example(): pass\n", encoding="utf-8")
    mapping = quality_policy.AffectedTestMapping(
        name="specific",
        path_prefixes=("src/ai4binance/",),
        tests=("tests/test_example.py", "tests/test_example.py", "missing.py"),
    )
    broad = quality_policy.AffectedTestMapping(
        name="broad", path_prefixes=("src/",), tests=("missing.py",)
    )
    assert quality_policy._existing_tests_with_no_cov(tmp_path, mapping.tests) == (
        "tests/test_example.py",
        "--no-cov",
    )
    assert quality_policy._most_specific_matching_mappings(
        "src/ai4binance/example.py", (broad, mapping)
    ) == (mapping,)
    with pytest.raises(
        quality_policy.AffectedScopeResolutionError, match="no existing"
    ):
        quality_policy._existing_tests_with_no_cov(tmp_path, ("missing.py",))


def test_changed_paths_and_profile_resolution_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        quality_policy.subprocess,  # type: ignore[attr-defined]
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 1, "stdout": ""})(),
    )
    with pytest.raises(
        quality_policy.AffectedScopeResolutionError, match="discovery failed"
    ):
        quality_policy.changed_repository_paths(tmp_path)

    profile = quality_policy.QualityGateProfile(
        name="custom",
        verification_status="CUSTOM",
        canonical_quality_authority=False,
        format_check="ruff",
        lint="ruff",
        type_check="mypy",
        pytest_scope="unsupported",
        fail_fast=True,
        full_suite=False,
        execution_trigger="test",
    )
    policy = quality_policy.QualityGatePolicy(
        version=1,
        profiles={"custom": profile},
        default_when_clean=(),
        affected_mappings=(),
        standard_impact_mappings=(),
        required_tests=(),
        unknown_impact_escalates_to="standard",
    )
    with pytest.raises(ValueError, match="unknown quality gate profile"):
        quality_policy.resolve_profile_pytest_arguments(policy, "unknown", tmp_path)
    with pytest.raises(ValueError, match="unsupported pytest scope"):
        quality_policy.resolve_profile_pytest_arguments(policy, "custom", tmp_path)


def test_profile_scope_variants_preserve_required_and_full_semantics(
    tmp_path: Path,
) -> None:
    test_path = tmp_path / "tests" / "test_example.py"
    test_path.parent.mkdir()
    test_path.write_text("def test_example(): pass\n", encoding="utf-8")
    profiles = {
        scope: quality_policy.QualityGateProfile(
            name=scope,
            verification_status="TEST",
            canonical_quality_authority=False,
            format_check="ruff",
            lint="ruff",
            type_check="mypy",
            pytest_scope=scope,
            fail_fast=True,
            full_suite=False,
            execution_trigger="test",
        )
        for scope in ("affected", "required", "full")
    }
    policy = quality_policy.QualityGatePolicy(
        version=1,
        profiles=profiles,
        default_when_clean=("tests/test_example.py",),
        affected_mappings=(),
        standard_impact_mappings=(),
        required_tests=("tests/test_example.py",),
        unknown_impact_escalates_to="standard",
    )
    assert quality_policy.resolve_profile_pytest_arguments(
        policy, "affected", tmp_path, (" ",)
    ) == ("tests/test_example.py", "--no-cov")
    assert quality_policy.resolve_profile_pytest_arguments(
        policy, "required", tmp_path, ("",)
    ) == ("tests/test_example.py", "--no-cov")
    assert (
        quality_policy.resolve_profile_pytest_arguments(policy, "full", tmp_path) == ()
    )


def test_load_policy_rejects_non_mapping_document(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text("- invalid\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a mapping"):
        quality_policy.load_quality_gate_policy(path)
