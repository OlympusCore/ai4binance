"""Deterministic contract tests for the terminology enforcement projection."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from ai4binance.governance.terminology_policy import (
    POLICY_PATH,
    SCHEMA_PATH,
    STANDARD_PATH,
    TerminologyTerm,
    evaluate_terminology_policy,
    load_terminology_policy,
)

ROOT = Path(__file__).parents[3]


def test_current_projection_is_bound_to_its_normative_standard() -> None:
    policy = load_terminology_policy(ROOT)
    metadata = yaml.safe_load(
        (ROOT / STANDARD_PATH).read_text(encoding="utf-8").split("---", maxsplit=2)[1]
    )

    assert policy.standard_id == metadata["document_id"]
    assert policy.standard_version == metadata["version"]
    assert policy.authority_scope == metadata["authority_scope"]
    assert (ROOT / SCHEMA_PATH).is_file()
    assert evaluate_terminology_policy(ROOT, policy, ()) == ()


def test_policy_rejects_alias_collision_and_duplicate_scoped_term() -> None:
    first = TerminologyTerm(
        "AI4B-TERM-TEST-001",
        "first",
        "test_scope",
        ("shared",),
        (),
        (),
    )
    alias_collision = TerminologyTerm(
        "AI4B-TERM-TEST-002",
        "second",
        "another_scope",
        ("shared",),
        (),
        (),
    )
    duplicate_term = TerminologyTerm(
        "AI4B-TERM-TEST-003",
        "first",
        "test_scope",
        (),
        (),
        (),
    )
    baseline = load_terminology_policy(ROOT)

    with pytest.raises(ValueError, match="alias collision"):
        replace(baseline, terms=(first, alias_collision))
    with pytest.raises(ValueError, match="duplicate canonical terminology"):
        replace(baseline, terms=(first, duplicate_term))


def test_prohibited_term_is_a_blocker_in_a_registered_scan_root(tmp_path: Path) -> None:
    policy = load_terminology_policy(ROOT)
    target = tmp_path / "config" / "unsafe.yaml"
    target.parent.mkdir()
    target.write_text("incorrect: signal = trade\n", encoding="utf-8")

    violations = evaluate_terminology_policy(
        tmp_path,
        policy,
        ("config/unsafe.yaml",),
    )

    assert any(
        violation.code == "TERMINOLOGY_PROHIBITED_TERM"
        and violation.path == "config/unsafe.yaml"
        and violation.blocker
        for violation in violations
    )


def test_registry_is_not_a_second_source_of_truth() -> None:
    payload = yaml.safe_load((ROOT / POLICY_PATH).read_text(encoding="utf-8"))

    assert payload["source_of_truth"] is False
    assert payload["authority"]["source_of_truth"] is False
    assert payload["authority"]["standard_path"] == STANDARD_PATH.as_posix()
