"""Contract and fail-closed tests for technology-language ownership."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ai4binance.governance import repository_validator
from ai4binance.governance.repository_validator import RepositoryFindingKind
from ai4binance.governance.technology_language_policy import (
    POLICY_PATH,
    SCHEMA_PATH,
    STANDARD_PATH,
    evaluate_technology_language_policy,
    load_technology_language_policy,
)

ROOT = Path(__file__).parents[3]


def test_canonical_standard_and_policy_projection_share_one_scope() -> None:
    standard_text = (ROOT / STANDARD_PATH).read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(standard_text.split("---", maxsplit=2)[1])
    policy_payload = yaml.safe_load((ROOT / POLICY_PATH).read_text(encoding="utf-8"))

    assert frontmatter["document_id"] == "AI4B-ARCH-STD-LANG-001"
    assert (
        frontmatter["authority_layer"]
        == "L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES"
    )
    assert frontmatter["authority_scope"] == "technology_language_ownership"
    assert frontmatter["authority_effect"] == "NORMATIVE_CONSTRAINT"
    assert frontmatter["source_of_truth"] is True
    assert policy_payload["authority"]["standard_id"] == frontmatter["document_id"]
    assert (
        policy_payload["authority"]["authority_scope"] == frontmatter["authority_scope"]
    )
    assert policy_payload["authority"]["source_of_truth"] is False
    assert (ROOT / SCHEMA_PATH).is_file()


def test_policy_projection_validates_and_accepts_current_representative_paths() -> None:
    policy = load_technology_language_policy(ROOT)
    paths = (
        ".agents/skills/factory/scripts/validate_factory_state.py",
        ".agents/skills/quality-gate-loop/scripts/invoke_gate.ps1",
        "config/governance/technology_language_ownership.yaml",
        "docs/architecture/diagrams/diagram_registry.yaml",
        "publication/public_manifest.yaml",
        "publication/sanitize_publication.py",
        "pyproject.toml",
        "schemas/governance/technology_language_ownership.schema.json",
        "scripts/quality.ps1",
        "src/ai4binance/local_dashboard/design_source.html",
        "src/ai4binance/local_dashboard/local_views.js",
        "frontend/src/dashboard_shell.ts",
        "frontend/src/command_center.ts",
        "src/ai4binance/governance/technology_language_policy.py",
        "tests/governance/architecture/test_technology_language_policy.py",
    )

    violations = evaluate_technology_language_policy(ROOT, policy, paths)

    assert violations == ()
    assert policy.execution_allowed is False
    assert policy.promotion_status == "RESEARCH_ONLY"
    assert policy.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_compiled_bytecode_is_not_classified_as_authored_source(
    tmp_path: Path,
) -> None:
    policy = load_technology_language_policy(ROOT)
    package = tmp_path / "src" / "package"
    cache = package / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "module.cpython-314.pyc").write_bytes(b"\xff\x00")
    (package / "unsupported.rb").write_text("puts 'unsafe'\n", encoding="utf-8")

    findings = evaluate_technology_language_policy(
        tmp_path,
        policy,
        (
            "src/package/__pycache__/module.cpython-314.pyc",
            "src/package/unsupported.rb",
        ),
    )

    assert not any(finding.path.endswith(".pyc") for finding in findings)
    assert any(
        finding.path == "src/package/unsupported.rb"
        and finding.code == "UNOWNED_SOURCE_LANGUAGE"
        for finding in findings
    )


def test_legacy_dashboard_assets_are_bounded_by_ui_language_owners() -> None:
    policy = load_technology_language_policy(ROOT)
    web_sources = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src").rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".css", ".html", ".js", ".ts", ".tsx"}
    }

    assert web_sources == {
        "src/ai4binance/local_dashboard/design_source.html",
        "src/ai4binance/local_dashboard/local_views.js",
    }
    violations = evaluate_technology_language_policy(ROOT, policy, web_sources)
    assert violations == ()


def test_policy_blocks_placement_forbidden_ownership_and_research_dependency(
    tmp_path: Path,
) -> None:
    policy = load_technology_language_policy(ROOT)
    misplaced_ui = tmp_path / "src" / "authoritative_risk_gate.ts"
    script = tmp_path / "scripts" / "bad.ps1"
    production = tmp_path / "src" / "ai4binance" / "research_bridge.py"
    for path in (misplaced_ui, script, production):
        path.parent.mkdir(parents=True, exist_ok=True)
    misplaced_ui.write_text(
        "const authoritativeRiskGate = () => true;\n",
        encoding="utf-8",
    )
    script.write_text(
        "function Invoke-TradeDecision { return 'BUY' }\n",
        encoding="utf-8",
    )
    production.write_text(
        "from research.julia import strategy\n",
        encoding="utf-8",
    )

    violations = evaluate_technology_language_policy(
        tmp_path,
        policy,
        (
            "src/authoritative_risk_gate.ts",
            "scripts/bad.ps1",
            "src/ai4binance/research_bridge.py",
        ),
    )

    assert {violation.code for violation in violations} == {
        "LANGUAGE_PLACEMENT_VIOLATION",
        "FORBIDDEN_CAPABILITY_OWNERSHIP",
        "RESEARCH_TO_PRODUCTION_DEPENDENCY",
    }


def test_policy_blocks_native_adoption_without_evidence(tmp_path: Path) -> None:
    policy = load_technology_language_policy(ROOT)
    rust_source = tmp_path / "native" / "rust" / "risk_core.rs"
    rust_source.parent.mkdir(parents=True)
    rust_source.write_text("pub fn evaluate() -> bool { false }\n", encoding="utf-8")

    violations = evaluate_technology_language_policy(
        tmp_path,
        policy,
        ("native/rust/risk_core.rs",),
    )

    assert len(violations) == 1
    assert violations[0].code == "ADOPTION_EVIDENCE_MISSING"
    assert violations[0].path == POLICY_PATH.as_posix()


@pytest.mark.parametrize(
    ("relative", "source", "code"),
    [
        (
            "src/sample.py",
            'QUERY = "SELECT value FROM records"',
            "EMBEDDED_SQL_OWNERSHIP",
        ),
        (
            "src/sample.py",
            'HTML = "<style>body { color: red; }</style>"',
            "EMBEDDED_CSS_OWNERSHIP",
        ),
        (
            "scripts/sample.ps1",
            "$body = @{ n_predict = 100; prompt = $input }",
            "FORBIDDEN_CAPABILITY_OWNERSHIP",
        ),
    ],
)
def test_content_ownership_does_not_require_capability_comments(
    tmp_path: Path,
    relative: str,
    source: str,
    code: str,
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    violations = evaluate_technology_language_policy(
        tmp_path,
        load_technology_language_policy(ROOT),
        (relative,),
    )
    assert code in {item.code for item in violations}


def test_repository_validator_blocks_an_incomplete_enforcement_chain(
    tmp_path: Path,
) -> None:
    standard = tmp_path / STANDARD_PATH
    standard.parent.mkdir(parents=True)
    standard.write_text("# Standard\n", encoding="utf-8")

    findings = tuple(
        repository_validator._technology_language_policy_findings(tmp_path, ())
    )

    assert len(findings) == 1
    assert (
        findings[0].kind is RepositoryFindingKind.TECHNOLOGY_LANGUAGE_POLICY_VIOLATION
    )
    assert "enforcement chain is incomplete" in findings[0].detail
    assert findings[0].blocker is True


@pytest.mark.parametrize(
    ("relative", "source", "expected"),
    [
        ("frontend/new.js", "const render = () => 1;", "LEGACY_SOURCE_EXPANSION"),
        (
            "frontend/new.mjs",
            "export const render = () => 1;",
            "LEGACY_SOURCE_EXPANSION",
        ),
        ("services/new.cpp", "int main() { return 0; }", "UNOWNED_SOURCE_LANGUAGE"),
        ("scripts/new.rb", "puts 'sample'", "UNOWNED_SOURCE_LANGUAGE"),
        ("scripts/new", "#!/usr/bin/ruby\nputs 'sample'", "UNRESOLVED_SOURCE_LANGUAGE"),
        ("scripts/new.py", "#!/bin/bash\necho sample", "UNRESOLVED_SOURCE_LANGUAGE"),
        (
            "scripts/new",
            "#!/usr/bin/env -S bash\nfunction risk_gate { true; }",
            "FORBIDDEN_CAPABILITY_OWNERSHIP",
        ),
        (
            "scripts/new.psm1",
            "function Test-RiskGate { return $true }",
            "FORBIDDEN_CAPABILITY_OWNERSHIP",
        ),
        (
            "scripts/new.ps1",
            "$riskGate = { return $true }",
            "FORBIDDEN_CAPABILITY_OWNERSHIP",
        ),
        (
            "frontend/new.ts",
            "let riskGate = () => true;",
            "FORBIDDEN_CAPABILITY_OWNERSHIP",
        ),
        (
            "frontend/new.ts",
            "var tradeDecision = () => 'BUY';",
            "FORBIDDEN_CAPABILITY_OWNERSHIP",
        ),
        (
            "frontend/new.ts",
            "class Engine { riskGate() { return true; } }",
            "FORBIDDEN_CAPABILITY_OWNERSHIP",
        ),
        (
            "frontend/new.ts",
            "const engine = { orderAuthorization: () => true };",
            "FORBIDDEN_CAPABILITY_OWNERSHIP",
        ),
    ],
)
def test_source_classification_and_declaration_escape_paths_are_blocked(
    tmp_path: Path,
    relative: str,
    source: str,
    expected: str,
) -> None:
    """Synthetic rejection fixtures never represent production trading evidence."""
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    violations = evaluate_technology_language_policy(
        tmp_path,
        load_technology_language_policy(ROOT),
        (relative,),
    )
    assert expected in {item.code for item in violations}


def test_ui_external_gate_call_is_not_a_local_definition(tmp_path: Path) -> None:
    target = tmp_path / "frontend" / "client.ts"
    target.parent.mkdir()
    target.write_text("canonical.riskGate(state);\n", encoding="utf-8")
    assert (
        evaluate_technology_language_policy(
            tmp_path,
            load_technology_language_policy(ROOT),
            ("frontend/client.ts",),
        )
        == ()
    )


@pytest.mark.parametrize(
    "header", ["#!/bin/sh", "#!/usr/bin/env bash", "#!/usr/bin/env -S bash -e"]
)
def test_extensionless_operational_wrappers_use_the_registered_owner(
    tmp_path: Path,
    header: str,
) -> None:
    target = tmp_path / "scripts" / "wrapper"
    target.parent.mkdir()
    target.write_text(header + "\necho 'operational wrapper'\n", encoding="utf-8")
    assert (
        evaluate_technology_language_policy(
            tmp_path,
            load_technology_language_policy(ROOT),
            ("scripts/wrapper",),
        )
        == ()
    )
