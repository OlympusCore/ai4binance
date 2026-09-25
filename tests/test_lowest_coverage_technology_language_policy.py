"""Boundary coverage for technology-language ownership enforcement."""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from ai4binance.governance import technology_language_policy as policy_module
from ai4binance.governance.technology_language_policy import (
    LanguageRule,
    TechnologyLanguagePolicy,
    evaluate_technology_language_policy,
    load_technology_language_policy,
)

ROOT = Path(__file__).parents[1]


def custom_rule(*, evidence_refs: tuple[str, ...] = ()) -> LanguageRule:
    """Make an isolated language rule for policy boundary tests."""
    return LanguageRule(
        language="custom",
        role="test_only",
        suffixes=(".custom",),
        enforce_placement=False,
        allowed_paths=("src",),
        allowed_capabilities=(),
        forbidden_capabilities=(),
        forbidden_content_patterns=(),
        evidence_required_if_present=True,
        evidence_refs=evidence_refs,
    )


def policy(*, rules: tuple[LanguageRule, ...]) -> TechnologyLanguagePolicy:
    """Reuse canonical metadata while replacing only test language rules."""
    return replace(load_technology_language_policy(ROOT), languages=rules)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: replace(
                policy(rules=(custom_rule(),)),
                human_authority_ref="docs/invalid.md",
            ),
            "human authority reference",
        ),
        (
            lambda: replace(policy(rules=(custom_rule(),)), authority_scope="invalid"),
            "authority scope",
        ),
        (
            lambda: replace(policy(rules=(custom_rule(),)), execution_allowed=True),
            "cannot widen trading authority",
        ),
        (
            lambda: replace(
                policy(rules=(custom_rule(),)), promotion_status="LIVE_ELIGIBLE"
            ),
            "cannot widen trading authority",
        ),
        (
            lambda: replace(
                policy(rules=(custom_rule(),)),
                live_eligibility_status="LIVE_ELIGIBLE",
            ),
            "cannot widen trading authority",
        ),
    ],
)
def test_policy_rejects_invalid_authority_or_safety_metadata(
    factory: Callable[[], TechnologyLanguagePolicy], message: str
) -> None:
    """Technology ownership never widens domain or live-trading authority."""
    with pytest.raises(ValueError, match=message):
        factory()


def test_policy_rejects_duplicate_suffix_owners_and_invalid_patterns() -> None:
    """A suffix has one owner and forbidden content remains valid regex."""
    with pytest.raises(ValueError, match="duplicate owners"):
        policy(rules=(custom_rule(), replace(custom_rule(), language="duplicate")))
    with pytest.raises(ValueError, match="invalid forbidden content pattern"):
        policy(rules=(replace(custom_rule(), forbidden_content_patterns=("(",)),))


def test_policy_reports_unreadable_sources_and_evidence_requirements(
    tmp_path: Path,
) -> None:
    """Unusable source and unavailable adoption proof are explicit findings."""
    source = tmp_path / "src" / "present.custom"
    source.parent.mkdir(parents=True)
    source.write_text("safe content\n", encoding="utf-8")

    missing_evidence = evaluate_technology_language_policy(
        tmp_path,
        policy(rules=(custom_rule(),)),
        ("runtime/ignored.custom", "docs/ignored.txt", "src/present.custom"),
    )
    assert [item.code for item in missing_evidence] == ["ADOPTION_EVIDENCE_MISSING"]

    unavailable_evidence = evaluate_technology_language_policy(
        tmp_path,
        policy(rules=(custom_rule(evidence_refs=("evidence/missing.md",)),)),
        ("src/present.custom",),
    )
    assert [item.code for item in unavailable_evidence] == [
        "ADOPTION_EVIDENCE_UNAVAILABLE"
    ]

    unreadable = evaluate_technology_language_policy(
        tmp_path,
        policy(rules=(custom_rule(),)),
        ("../outside.custom",),
    )
    assert unreadable[0].code == "TECHNOLOGY_SOURCE_UNREADABLE"


@pytest.mark.parametrize(
    ("function", "value", "message"),
    [
        (policy_module._mapping, (), "must be a mapping"),
        (policy_module._string, "", "must be non-empty text"),
        (policy_module._boolean, "false", "must be boolean"),
        (policy_module._strings, ("not", "a", "list"), "must be a string array"),
        (policy_module._safe_paths, ["../unsafe"], "repository-relative POSIX paths"),
        (policy_module._safe_paths, ["/absolute"], "repository-relative POSIX paths"),
        (policy_module._safe_paths, ["C:/absolute"], "repository-relative POSIX paths"),
    ],
)
def test_policy_value_validators_reject_malformed_input(
    function: Callable[[object, str], object], value: object, message: str
) -> None:
    """Policy loader helpers reject malformed and unsafe configuration values."""
    with pytest.raises(ValueError, match=message):
        function(value, "test")
