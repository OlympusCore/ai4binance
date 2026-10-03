"""Deterministic contract tests for the terminology enforcement projection."""

from __future__ import annotations

import gzip
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


def test_compiled_bytecode_is_not_scanned_as_text_but_source_still_is(
    tmp_path: Path,
) -> None:
    policy = load_terminology_policy(ROOT)
    package = tmp_path / "src" / "package"
    cache = package / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "module.cpython-314.pyc").write_bytes(b"\xff\x00signal = trade")
    (package / "module.py").write_text("signal = trade\n", encoding="utf-8")

    findings = evaluate_terminology_policy(
        tmp_path,
        policy,
        (
            "src/package/__pycache__/module.cpython-314.pyc",
            "src/package/module.py",
        ),
    )

    assert not any(finding.path.endswith(".pyc") for finding in findings)
    assert any(
        finding.path == "src/package/module.py"
        and finding.code == "TERMINOLOGY_PROHIBITED_TERM"
        for finding in findings
    )


def test_registry_is_not_a_second_source_of_truth() -> None:
    payload = yaml.safe_load((ROOT / POLICY_PATH).read_text(encoding="utf-8"))

    assert payload["source_of_truth"] is False
    assert payload["authority"]["source_of_truth"] is False
    assert payload["authority"]["standard_path"] == STANDARD_PATH.as_posix()


@pytest.mark.parametrize(
    "content",
    [None, b"\xff", b"x" * 2_000_001],
    ids=["missing", "invalid_utf8", "oversized"],
)
def test_unreadable_registered_source_is_a_blocker(
    tmp_path: Path,
    content: bytes | None,
) -> None:
    target = tmp_path / "config" / "source.yaml"
    target.parent.mkdir()
    if content is not None:
        target.write_bytes(content)
    findings = evaluate_terminology_policy(
        tmp_path,
        load_terminology_policy(ROOT),
        ("config/source.yaml",),
    )
    assert any(
        item.code == "TERMINOLOGY_SOURCE_UNREADABLE" and item.blocker
        for item in findings
    )


def test_alias_cannot_reassign_another_canonical_term() -> None:
    policy = load_terminology_policy(ROOT)
    first = TerminologyTerm("first", "Canonical Name", "one", (), (), ())
    second = TerminologyTerm("second", "Other", "two", ("canonical   NAME",), (), ())
    with pytest.raises(ValueError, match="alias collision with canonical"):
        replace(policy, terms=(first, second))


@pytest.mark.parametrize("oversized", [False, True])
def test_compressed_sources_are_scanned_with_a_decompressed_size_bound(
    tmp_path: Path,
    oversized: bool,
) -> None:
    target = tmp_path / "src" / "source.js.gz"
    target.parent.mkdir()
    content = b"x" * 2_000_001 if oversized else b"signal = trade"
    target.write_bytes(gzip.compress(content))
    findings = evaluate_terminology_policy(
        tmp_path,
        load_terminology_policy(ROOT),
        ("src/source.js.gz",),
    )
    expected = (
        "TERMINOLOGY_SOURCE_UNREADABLE" if oversized else "TERMINOLOGY_PROHIBITED_TERM"
    )
    assert any(item.code == expected and item.blocker for item in findings)


@pytest.mark.parametrize(
    "text", ["signal  =  trade", "SIGNAL\t=\tTRADE", "signal\n=\ntrade"]
)
def test_registered_prohibition_cannot_escape_through_whitespace(text: str) -> None:
    assert terminology_module._contains_term(text, "signal = trade")


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
    for unsafe_path in ("../outside", "/absolute", "C:/absolute", "folder\\file"):
        with pytest.raises(ValueError, match="repository-relative"):
            terminology_module._safe_path(unsafe_path, "value")


def test_terminology_scan_covers_deprecated_missing_and_projection_drift(
    tmp_path: Path,
) -> None:
    loaded_policy = load_terminology_policy(ROOT)
    policy = replace(
        loaded_policy,
        terms=(replace(loaded_policy.terms[0], deprecated_aliases=("legacy",)),),
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


def test_semantic_concept_alias_cannot_collapse_declared_boundary(
    tmp_path: Path,
) -> None:
    target = tmp_path / "src/example.py"
    target.parent.mkdir()
    target.write_text("Opportunity = Signal\n", encoding="utf-8")
    findings = evaluate_terminology_policy(
        tmp_path, load_terminology_policy(ROOT), ("src/example.py",)
    )
    assert any(
        item.code == "TERMINOLOGY_SEMANTIC_BOUNDARY_COLLAPSE" for item in findings
    )
