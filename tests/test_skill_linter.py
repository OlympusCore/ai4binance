from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ai4binance.skills import (
    SkillAuditReport,
    SkillManifest,
    SkillSeverity,
    audit_skill_root,
    lint_skill_manifest,
    read_skill,
)
from ai4binance.skills import parser as skill_parser


def write_skill(
    root: Path,
    name: str,
    *,
    frontmatter: str | None = None,
    body: str = "# Skill\n\nUse this for safe advisory work.\n",
) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    content = (
        frontmatter
        or f"---\nname: {name}\ndescription: Use when auditing local skills.\n---\n"
    )
    (skill_dir / "SKILL.md").write_text(content + body, encoding="utf-8")
    return skill_dir


def test_valid_skill_is_read_only_and_research_only(tmp_path: Path) -> None:
    skill_dir = write_skill(
        tmp_path,
        "safe-skill",
        frontmatter=(
            "---\n"
            "name: safe-skill\n"
            "description: Use when auditing local skills.\n"
            "metadata:\n"
            "  ai4binance.authority: advisory-only\n"
            '  ai4binance.version: "1"\n'
            "  ai4binance.owner: QualityDepartmentManager\n"
            "  ai4binance.trust_level: local\n"
            "  ai4binance.last_reviewed: 2026-07-29\n"
            "  ai4binance.trigger_examples: skills audit; skill governance\n"
            "---\n"
        ),
    )

    manifest = read_skill(skill_dir)
    issues = lint_skill_manifest(manifest)

    assert issues == ()
    assert manifest.owner == "QualityDepartmentManager"
    assert manifest.trust_level == "local"
    assert manifest.trigger_examples == ("skills audit", "skill governance")
    assert manifest.execution_allowed is False
    assert manifest.installation_allowed is False
    assert manifest.promotion_status == "RESEARCH_ONLY"
    assert manifest.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_audit_blocks_scripts_and_high_risk_allowed_tools(tmp_path: Path) -> None:
    skill_dir = write_skill(
        tmp_path,
        "risky-skill",
        frontmatter=(
            "---\n"
            "name: risky-skill\n"
            "description: Use when reviewing a skill.\n"
            "allowed-tools: Bash(git:*) Read\n"
            "---\n"
        ),
    )
    (skill_dir / "scripts").mkdir()
    (skill_dir / "scripts" / "run.ps1").write_text(
        "Write-Output test", encoding="utf-8"
    )

    report = audit_skill_root(tmp_path)

    assert report.skill_count == 1
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert "SKILL_HIGH_RISK_TOOL_DECLARED" in report.blockers
    assert "SKILL_SCRIPT_REVIEW_REQUIRED" in report.blockers


def test_audit_surfaces_parse_errors_without_throwing(tmp_path: Path) -> None:
    skill_dir = tmp_path / "broken-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("name: broken-skill\n", encoding="utf-8")

    report = audit_skill_root(tmp_path)

    assert report.skill_count == 0
    assert report.blockers == ("SKILL_PARSE_FAILED",)
    assert report.issues[0].severity is SkillSeverity.BLOCKER


def test_audit_reports_invalid_root_and_empty_root(tmp_path: Path) -> None:
    missing = audit_skill_root(tmp_path / "missing")
    assert missing.blockers == ("SKILL_ROOT_INVALID",)
    assert missing.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    empty = audit_skill_root(tmp_path)
    assert empty.skill_count == 0
    assert empty.issues[0].code == "NO_SKILLS_FOUND"
    assert empty.blockers == ()


def test_linter_flags_name_mismatch_and_live_authority_drift(tmp_path: Path) -> None:
    skill_dir = write_skill(
        tmp_path,
        "actual-name",
        frontmatter=(
            "---\n"
            "name: declared-name\n"
            "description: Use when authorizing live order execution.\n"
            "---\n"
        ),
        body="# Skill\n\nBypass risk gate and place order.\n",
    )

    report = audit_skill_root(skill_dir)
    codes = {issue.code for issue in report.issues}

    assert "SKILL_NAME_DIRECTORY_MISMATCH" in codes
    assert "SKILL_AUTHORITY_DRIFT_REVIEW_REQUIRED" in report.blockers


def test_linter_flags_optional_resources_and_deep_references(tmp_path: Path) -> None:
    skill_dir = write_skill(
        tmp_path,
        "resource-skill",
        frontmatter=(
            "---\n"
            "name: resource-skill\n"
            "description: Use when reviewing skill resources.\n"
            "compatibility: xxxxxxxxxx\n"
            "---\n"
        ),
        body=(
            "# Resource Skill\n\n"
            "Read [details](references/deep/path.md) and scripts/run.ps1.\n"
        ),
    )
    (skill_dir / "assets").mkdir()
    (skill_dir / "references").mkdir()
    (skill_dir / "extra.md").write_text("extra", encoding="utf-8")

    codes = {issue.code for issue in audit_skill_root(skill_dir).issues}

    assert "SKILL_ROOT_EXTRA_FILES" in codes
    assert "SKILL_DEEP_REFERENCE" in codes


def test_linter_flags_required_frontmatter_and_length_limits(tmp_path: Path) -> None:
    skill_dir = write_skill(
        tmp_path,
        "blank-skill",
        frontmatter=(
            f"---\nname: \ndescription: {'x' * 1025}\ncompatibility: {'y' * 501}\n---\n"
        ),
    )

    codes = {issue.code for issue in audit_skill_root(skill_dir).issues}

    assert "SKILL_NAME_MISSING" in codes
    assert "SKILL_DESCRIPTION_TOO_LONG" in codes
    assert "SKILL_COMPATIBILITY_TOO_LONG" in codes


def test_skill_linter_requires_versioned_review_metadata(tmp_path: Path) -> None:
    skill_dir = write_skill(
        tmp_path,
        "thin-skill",
        frontmatter=(
            "---\n"
            "name: thin-skill\n"
            "description: Audit local skills.\n"
            "metadata:\n"
            "  ai4binance.authority: advisory-only\n"
            "  ai4binance.trust_level: unknown\n"
            "---\n"
        ),
    )

    codes = {issue.code for issue in lint_skill_manifest(read_skill(skill_dir))}

    assert "SKILL_VERSION_MISSING" in codes
    assert "SKILL_OWNER_MISSING" in codes
    assert "SKILL_TRUST_LEVEL_INVALID" in codes
    assert "SKILL_LAST_REVIEWED_MISSING" in codes
    assert "SKILL_TRIGGER_EXAMPLES_MISSING" in codes
    assert "SKILL_TRIGGER_DESCRIPTION_WEAK" in codes


def test_skill_linter_recommends_progressive_disclosure_for_dense_skill(
    tmp_path: Path,
) -> None:
    skill_dir = write_skill(
        tmp_path,
        "dense-skill",
        frontmatter=(
            "---\n"
            "name: dense-skill\n"
            "description: Use when auditing dense local skills.\n"
            "metadata:\n"
            "  ai4binance.authority: advisory-only\n"
            "  ai4binance.version: 1\n"
            "  ai4binance.owner: QualityDepartmentManager\n"
            "  ai4binance.trust_level: local\n"
            "  ai4binance.last_reviewed: 2026-07-29\n"
            "  ai4binance.trigger_examples: dense skill audit\n"
            "---\n"
        ),
        body="\n".join(f"Line {index}" for index in range(130)),
    )

    codes = {issue.code for issue in lint_skill_manifest(read_skill(skill_dir))}

    assert "SKILL_PROGRESSIVE_DISCLOSURE_RECOMMENDED" in codes


def test_parser_supports_single_skill_root_and_rejects_bad_shapes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill_dir = write_skill(tmp_path, "single-skill")
    assert skill_parser.discover_skill_paths(skill_dir) == (skill_dir.resolve(),)

    file_path = tmp_path / "not-a-directory.md"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(skill_parser.SkillParseError, match="not a directory"):
        skill_parser.discover_skill_paths(file_path)

    broken = tmp_path / "bad-nested"
    broken.mkdir()
    (broken / "SKILL.md").write_text(
        "---\nname: bad-nested\n  value: nope\n---\n", encoding="utf-8"
    )
    with pytest.raises(skill_parser.SkillParseError, match="nested"):
        skill_parser.read_skill(broken)

    no_close = tmp_path / "no-close"
    no_close.mkdir()
    (no_close / "SKILL.md").write_text("---\nname: no-close\n", encoding="utf-8")
    with pytest.raises(skill_parser.SkillParseError, match="closing"):
        skill_parser.read_skill(no_close)

    monkeypatch.setattr(skill_parser, "MAX_SKILL_MD_BYTES", 1)
    with pytest.raises(skill_parser.SkillParseError, match="exceeds"):
        skill_parser.read_skill(skill_dir)


def test_skill_contracts_reject_authority_drift(tmp_path: Path) -> None:
    manifest = read_skill(write_skill(tmp_path, "contract-skill"))
    with pytest.raises(ValueError, match="execution authority"):
        replace(manifest, execution_allowed=True)
    with pytest.raises(ValueError, match="promote"):
        replace(manifest, promotion_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="live blocked"):
        replace(manifest, live_eligibility_status="LIVE_ELIGIBLE")
    issue = audit_skill_root(tmp_path).issues[0]
    with pytest.raises(ValueError, match="cannot be blank"):
        replace(issue, code="")
    report = audit_skill_root(tmp_path)
    with pytest.raises(ValueError, match="count"):
        SkillAuditReport(
            root=report.root,
            skill_count=99,
            issue_count=report.issue_count,
            blocker_count=report.blocker_count,
            high_risk_capability_count=report.high_risk_capability_count,
            skills=report.skills,
            issues=report.issues,
            blockers=report.blockers,
        )
    with pytest.raises(ValueError, match="authority"):
        replace(report, execution_allowed=True)
    with pytest.raises(ValueError, match="promote"):
        replace(report, promotion_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="live blocked"):
        replace(report, live_eligibility_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="authority"):
        SkillManifest(
            skill_dir=str(tmp_path),
            skill_file=str(tmp_path / "SKILL.md"),
            name="bad",
            description="bad",
            license=None,
            compatibility=None,
            metadata={},
            allowed_tools=None,
            body="",
            referenced_files=(),
            optional_directories=(),
            root_files=(),
            execution_allowed=True,
        )


@pytest.mark.parametrize("name", ["Upper", "-bad", "bad-", "bad--name"])
def test_linter_rejects_invalid_names(tmp_path: Path, name: str) -> None:
    safe_dir = "upper" if name == "Upper" else "skill-dir"
    skill_dir = write_skill(
        tmp_path,
        safe_dir,
        frontmatter=f"---\nname: {name}\ndescription: Use when testing names.\n---\n",
    )

    codes = {issue.code for issue in audit_skill_root(skill_dir).issues}

    assert "SKILL_NAME_INVALID" in codes
