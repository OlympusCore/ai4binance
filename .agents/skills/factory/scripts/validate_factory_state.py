"""Validate the repo-local AI4BINANCE factory contract."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

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

REQUIRED_TEMPLATE_FILES = (
    "factory/templates/brief_template.md",
    "factory/templates/plan_template.md",
    "factory/templates/handoff_template.md",
    "factory/templates/review_template.md",
    "factory/templates/guide_template.md",
)

REQUIRED_SKILLS = (
    "factory",
    "factory-plan",
    "factory-tests",
    "factory-explain",
    "factory-handoff",
    "factory-review",
)

REQUIRED_SAFETY_TERMS = (
    "NO_TRADE",
    "RESEARCH_ONLY",
    "LIVE_ORDER_BLOCKED",
)
REQUIRED_BACKGROUND_MODE = "BACKGROUND_SHIFT"

FORBIDDEN_AUTHORITY_PATTERNS = (
    re.compile(r"allow_auto_live_orders\s*=\s*true", re.IGNORECASE),
    re.compile(r"execution_allowed\s*=\s*true", re.IGNORECASE),
    re.compile(r"live_eligibility_status\s*=\s*READY", re.IGNORECASE),
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _has_skill_frontmatter(text: str, expected_name: str) -> bool:
    return (
        text.startswith("---\n")
        and (f"name: {expected_name}\n" in text)
        and "description:" in text.split("---", 2)[1]
    )


def validate_factory(root: Path) -> list[str]:
    errors: list[str] = []

    required_paths = REQUIRED_FACTORY_FILES + REQUIRED_TEMPLATE_FILES
    for relative_path in required_paths:
        path = root / relative_path
        if not path.is_file():
            errors.append(f"missing required file: {relative_path}")

    state_path = root / "factory/state.md"
    if state_path.is_file():
        state_text = _read_text(state_path)
        for term in REQUIRED_SAFETY_TERMS:
            if term not in state_text:
                errors.append(f"factory/state.md missing safety term: {term}")
        if REQUIRED_BACKGROUND_MODE not in state_text:
            errors.append(
                f"factory/state.md missing background mode: {REQUIRED_BACKGROUND_MODE}"
            )
        for pattern in FORBIDDEN_AUTHORITY_PATTERNS:
            if pattern.search(state_text):
                errors.append(
                    "factory/state.md contains forbidden live authority pattern: "
                    f"{pattern.pattern}"
                )

    handoff_path = root / "factory/handoff.md"
    if handoff_path.is_file():
        handoff_text = _read_text(handoff_path)
        if "LIVE_ORDER_BLOCKED" not in handoff_text:
            errors.append("factory/handoff.md must state LIVE_ORDER_BLOCKED")
        if REQUIRED_BACKGROUND_MODE not in handoff_text:
            errors.append(
                "factory/handoff.md missing background mode: "
                f"{REQUIRED_BACKGROUND_MODE}"
            )
        for pattern in FORBIDDEN_AUTHORITY_PATTERNS:
            if pattern.search(handoff_text):
                errors.append(
                    "factory/handoff.md contains forbidden authority pattern: "
                    f"{pattern.pattern}"
                )

    for skill_name in REQUIRED_SKILLS:
        skill_path = root / ".agents/skills" / skill_name / "SKILL.md"
        if not skill_path.is_file():
            errors.append(f"missing skill: {skill_name}")
            continue
        skill_text = _read_text(skill_path)
        if not _has_skill_frontmatter(skill_text, skill_name):
            errors.append(f"invalid frontmatter for skill: {skill_name}")
        if "LIVE_ORDER_BLOCKED" not in skill_text:
            errors.append(f"skill must preserve LIVE_ORDER_BLOCKED: {skill_name}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate AI4BINANCE factory artifacts and safety terms."
    )
    parser.add_argument(
        "repository_root",
        nargs="?",
        default=".",
        help="Repository root path. Defaults to the current directory.",
    )
    args = parser.parse_args()

    root = Path(args.repository_root).resolve()
    errors = validate_factory(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Factory contract OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
