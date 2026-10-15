"""Invalid metadata cannot turn an ordinary file into governing authority."""

from pathlib import Path

import pytest

from ai4binance.governance import repository_validator as validator
from ai4binance.governance.repository_validator import KnowledgeAuthorityEffect
from tests.test_repository_validator import _knowledge_object, _repository_artifact


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"sensitive": True}, "sensitive repository artifacts must not be hashed"),
        ({"size": -1}, "size cannot be negative"),
        ({"source_of_truth": 1}, "source_of_truth must be boolean"),
        ({"machine_enforceable": 1}, "machine_enforceable must be boolean"),
        ({"audit_required": 1}, "audit_required must be boolean"),
        ({"classification": "INTERNAL"}, "canonical knowledge classification"),
        ({"authority_layer": "folder-name"}, "canonical authority pyramid"),
        ({"authority_effect": "NORMATIVE_CONSTRAINT"}, "canonical authority effects"),
        ({"authority_scope": " "}, "authority_scope cannot be empty"),
        ({"authority_scope": "Engineering Scope"}, "lower_snake_case"),
        ({"observed_expected_layer": "NORMATIVE"}, "canonical authority pyramid"),
        ({"authority_basis": ("source-1", "source-1")}, "unique"),
        ({"authority_basis": (" ",)}, "cannot contain blanks"),
    ],
)
def test_artifact_metadata_rejects_type_path_and_authority_confusion(
    changes: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        _repository_artifact(**changes)


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"authority_layer": "NORMATIVE"}, "canonical authority pyramid"),
        ({"authority_scope": None}, "authority_scope is required"),
        ({"authority_scope": " "}, "authority_scope cannot be empty"),
        ({"authority_scope": "Not_A_Valid_Scope"}, "lower_snake_case"),
        ({"source_of_truth_scope": " "}, "source_of_truth_scope cannot be empty"),
    ],
)
def test_governed_knowledge_requires_explicit_valid_scope_and_layer(
    changes: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        _knowledge_object(**changes)


def test_valid_optional_authority_metadata_remains_a_description() -> None:
    artifact = _repository_artifact(
        authority_scope="repository_operations",
        authority_effect=KnowledgeAuthorityEffect.OPERATIONAL_SPECIALIZATION,
        authority_basis=("explicit-scope",),
    )
    assert artifact.authority_scope == "repository_operations"
    assert artifact.source_of_truth is False
    assert artifact.authority_basis == ("explicit-scope",)


@pytest.mark.parametrize("value", [None, {}, [None], [""], [" "]])
def test_policy_sequence_rejects_untyped_or_blank_paths(value: object) -> None:
    with pytest.raises(ValueError, match=r"list|non-empty"):
        validator._json_string_sequence(value, "test paths")


def test_policy_sequence_normalizes_paths_but_preserves_literal_labels() -> None:
    assert validator._json_string_sequence([" ././docs//source/ "], "paths") == (
        "docs/source",
    )
    assert validator._json_string_sequence(
        [" label/value "], "labels", normalize_paths=False
    ) == ("label/value",)
    assert validator._json_string_sequence([], "optional", allow_empty=True) == ()
    with pytest.raises(ValueError, match="must not be empty"):
        validator._json_string_sequence([], "required")
    with pytest.raises(ValueError, match="non-empty"):
        validator._normalize_repository_policy_path("././")


@pytest.mark.parametrize(
    "value",
    [[], None, {None: "source"}, {" ": "source"}, {"source": None}, {"source": " "}],
)
def test_policy_mapping_rejects_invalid_keys_and_values(value: object) -> None:
    with pytest.raises(ValueError, match=r"mapping|non-empty"):
        validator._json_string_mapping({"bindings": value}, "bindings")


def test_policy_mapping_can_keep_non_path_identifiers_literal() -> None:
    assert validator._json_string_mapping(
        {"bindings": {" label ": " source "}},
        "bindings",
        normalize_keys=False,
        normalize_values=False,
    ) == {"label": "source"}
    assert validator._json_string_mapping(
        {"bindings": {"./docs//index/": "./docs//source/"}}, "bindings"
    ) == {"docs/index": "docs/source"}


@pytest.mark.parametrize("effect", ["", " ", "folder-implied-authority"])
def test_authority_effect_rejects_unknown_or_empty_taxonomy(effect: str) -> None:
    with pytest.raises(ValueError, match="authority_effect"):
        validator._normalize_authority_effect(effect)


@pytest.mark.parametrize("relative", ["../outside.md", "/root.md", "C:/outside.md"])
def test_governed_context_rejects_paths_outside_repository(
    tmp_path: Path, relative: str
) -> None:
    with pytest.raises(ValueError, match="path is invalid"):
        validator.read_verified_governed_document(tmp_path, relative)


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        ("TERMINOLOGY_PROHIBITED_TERM", "TERMINOLOGY_PROHIBITED_TERM"),
        ("TERMINOLOGY_DEPRECATED_ALIAS", "TERMINOLOGY_DEPRECATED_ALIAS"),
    ],
)
def test_terminology_findings_retain_their_canonical_enforcement_kind(
    code: str, kind: str
) -> None:
    assert validator._fabric_finding_kind("terminology", code).value == kind
