from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = (
    ROOT / ".agents" / "skills" / "factory" / "scripts" / "validate_factory_state.py"
)
REQUIRED_SKILLS = (
    "factory",
    "factory-plan",
    "factory-tests",
    "factory-explain",
    "factory-handoff",
    "factory-review",
)
REQUIRED_FACTORY_FILES = (
    "factory/state.md",
    "factory/brief.md",
    "factory/plan.md",
    "factory/handoff.md",
    "factory/review.md",
    "factory/guide.md",
    "factory/progress.md",
    "factory/log.md",
    "factory/decisions.jsonl",
)
REQUIRED_TEMPLATES = (
    "factory/templates/brief_template.md",
    "factory/templates/plan_template.md",
    "factory/templates/handoff_template.md",
    "factory/templates/review_template.md",
    "factory/templates/guide_template.md",
)
SAFETY_TERMS = ("NO_TRADE", "RESEARCH_ONLY", "LIVE_ORDER_BLOCKED")
BACKGROUND_MODE = "BACKGROUND_SHIFT"
BACKGROUND_CONTRACT_FILES = (
    "factory/state.md",
    "factory/plan.md",
    "factory/handoff.md",
    "factory/guide.md",
    "docs/workflows/runbook_governed_software_factory.md",
    ".agents/skills/factory/SKILL.md",
    ".agents/skills/factory-handoff/SKILL.md",
)


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("factory_validator", VALIDATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_factory_artifacts_exist() -> None:
    for relative_path in REQUIRED_FACTORY_FILES + REQUIRED_TEMPLATES:
        assert (ROOT / relative_path).is_file(), relative_path


def test_factory_skills_have_frontmatter_and_live_blocker() -> None:
    for skill_name in REQUIRED_SKILLS:
        skill_path = ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")

        assert text.startswith("---\n")
        assert f"name: {skill_name}\n" in text
        assert "description:" in text.split("---", 2)[1]
        assert "LIVE_ORDER_BLOCKED" in text


def test_factory_state_preserves_safety_terms() -> None:
    state_text = (ROOT / "factory" / "STATE.md").read_text(encoding="utf-8")
    handoff_text = (ROOT / "factory" / "HANDOFF.md").read_text(encoding="utf-8")

    for term in SAFETY_TERMS:
        assert term in state_text
    assert "LIVE_ORDER_BLOCKED" in handoff_text
    assert BACKGROUND_MODE in state_text
    assert BACKGROUND_MODE in handoff_text
    assert "allow_auto_live_orders=true" not in state_text
    assert "execution_allowed=true" not in handoff_text


def test_factory_uses_background_shift_contract() -> None:
    for relative_path in BACKGROUND_CONTRACT_FILES:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert BACKGROUND_MODE in text
        assert "overnight" not in text.lower()


def test_factory_validator_accepts_current_contract() -> None:
    validator = _load_validator()

    errors = validator.validate_factory(ROOT)

    assert errors == []
