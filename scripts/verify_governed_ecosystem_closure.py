"""Fail-closed preflight for the governed-ecosystem closure contracts."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ai4binance.governance.authority import load_external_authority_registry
from ai4binance.schema_validation import (
    OfflineSchemaRegistry,
    validate_contract_schema_mappings,
)


def verify_governed_ecosystem_closure(*, as_of: date) -> dict[str, object]:
    """Validate local contracts and report unresolved authority applicability."""
    repository_root = Path(__file__).resolve().parents[1]
    schema_root = repository_root / "schemas"
    registry = load_external_authority_registry(
        repository_root / "config/governance/external_authorities.yaml",
        schema_root=schema_root,
    )
    schema_registry = OfflineSchemaRegistry.from_directory(schema_root)
    validate_contract_schema_mappings(schema_registry)
    blockers = registry.applicability_blockers(as_of=as_of)
    return {
        "as_of": as_of.isoformat(),
        "external_authority_entry_count": len(registry.entries),
        "contract_schema_mappings_valid": True,
        "blockers": blockers,
        "status": "CLEAR" if not blockers else "BLOCKED",
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", required=True, type=date.fromisoformat)
    parser.add_argument("--require-clear", action="store_true")
    arguments = parser.parse_args()
    report = verify_governed_ecosystem_closure(as_of=arguments.as_of)
    print(json.dumps(report, sort_keys=True))
    return 2 if arguments.require_clear and report["status"] != "CLEAR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
