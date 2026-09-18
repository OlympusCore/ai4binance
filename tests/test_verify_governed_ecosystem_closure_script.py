from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path
from typing import Protocol, cast

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "verify_governed_ecosystem_closure.py"


class GovernedEcosystemClosureModule(Protocol):
    def verify_governed_ecosystem_closure(
        self, *, as_of: date
    ) -> dict[str, object]: ...


def _load_script_module() -> GovernedEcosystemClosureModule:
    specification = importlib.util.spec_from_file_location(
        "verify_governed_ecosystem_closure", SCRIPT
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return cast(GovernedEcosystemClosureModule, module)


def test_preflight_reports_current_external_authority_blockers() -> None:
    module = _load_script_module()
    report = module.verify_governed_ecosystem_closure(as_of=date(2026, 9, 13))
    blockers = report["blockers"]

    assert report["contract_schema_mappings_valid"] is True
    assert report["status"] == "BLOCKED"
    assert isinstance(blockers, tuple)
    assert "EXTERNAL_AUTHORITY_REVIEW_REQUIRED:EU_AI_ACT" in blockers
    assert report["execution_allowed"] is False
