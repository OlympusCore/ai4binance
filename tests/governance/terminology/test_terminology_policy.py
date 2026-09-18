"""Deterministic contract tests for the terminology enforcement projection."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from ai4binance.governance import terminology_policy as terminology_module
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


def test_terminology_helpers_and_policy_contract_fail_closed(tmp_path: Path) -> None:
    policy = load_terminology_policy(ROOT)
    term = policy.terms[0]
    with pytest.raises(ValueError, match="standard path"):
        replace(policy, standard_path="docs/other.md")
    with pytest.raises(ValueError, match="standard identifier"):
        replace(policy, standard_id="wrong")
    with pytest.raises(ValueError, match="authority scope"):
        replace(policy, authority_scope="wrong")
    overlap = replace(
        term,
        deprecated_aliases=("legacy",),
        prohibited_terms=("legacy",),
    )
    with pytest.raises(ValueError, match="must not also be prohibited"):
        replace(policy, terms=(overlap,))
    assert terminology_module._normalized_paths(("./docs\\a.md", "", "docs/a.md")) == (
        "docs/a.md",
    )
    assert terminology_module._is_scanned_path("docs/a.md", ("docs",)) is True
    assert terminology_module._is_scanned_path("other/a.md", ("docs",)) is False
    assert terminology_module._contains_term("Trade signal", "trade") is True
    assert terminology_module._contains_term("trader", "trade") is False
    assert terminology_module._read_bounded_text(tmp_path, "../outside") is None
    with pytest.raises(ValueError, match="must be a mapping"):
        terminology_module._mapping([], "value")
    with pytest.raises(ValueError, match="must be an array"):
        terminology_module._items({}, "value")
    with pytest.raises(ValueError, match="non-empty text"):
        terminology_module._string(" ", "value")
    with pytest.raises(ValueError, match="string array"):
        terminology_module._strings([""], "value")
    with pytest.raises(ValueError, match="repository-relative"):
        terminology_module._safe_path("../outside", "value")


def test_terminology_scan_covers_deprecated_missing_and_projection_drift(
    tmp_path: Path,
) -> None:
    loaded_policy = load_terminology_policy(ROOT)
    policy = replace(
        loaded_policy,
        terms=(
            replace(loaded_policy.terms[0], deprecated_aliases=("legacy",)),
        ),
    )
    target = tmp_path / policy.scan_roots[0] / "terms.txt"
    target.parent.mkdir(parents=True)
    target.write_text("legacy", encoding="utf-8")
    paths = (
        policy.excluded_paths[0],
        "missing.txt",
        target.relative_to(tmp_path).as_posix(),
    )
    violations = evaluate_terminology_policy(
        tmp_path,
        policy,
        paths,
    )
    assert any(item.code == "TERMINOLOGY_DEPRECATED_ALIAS" for item in violations)
    standard = tmp_path / STANDARD_PATH
    standard.parent.mkdir(parents=True, exist_ok=True)
    standard.write_text("---\ndocument_id: wrong\n---\n", encoding="utf-8")
    assert any(
        item.code == "TERMINOLOGY_PROJECTION_DRIFT"
        for item in terminology_module._projection_integrity_violations(
            tmp_path, policy
        )
    )
    plain = tmp_path / "plain.md"
    plain.write_text("plain text", encoding="utf-8")
    assert terminology_module._frontmatter(plain) == {}
    assert terminology_module._read_bounded_text(tmp_path, "missing.txt") is None
    oversized = tmp_path / "oversized.txt"
    oversized.write_bytes(b"x" * 2_000_001)
    assert terminology_module._read_bounded_text(tmp_path, "oversized.txt") is None
    with pytest.raises(ValueError, match="duplicate terminology term identifier"):
        replace(policy, terms=(policy.terms[0], policy.terms[0]))
