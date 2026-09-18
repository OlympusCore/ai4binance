from pathlib import Path

import pytest

from ai4binance.schema_validation import OfflineSchemaRegistry, SchemaValidationError

SCHEMA_ID = "urn:ai4binance:schema:decisions:decision-candidate:1.0.0"


def test_decision_candidate_schema_is_fail_closed_for_execution() -> None:
    registry = OfflineSchemaRegistry.from_directory(Path("schemas"))
    candidate = {
        "schema_version": "1.0.0",
        "candidate_id": "candidate:btc-breakout",
        "symbol": "BTCUSDT",
        "market_type": "SPOT",
        "requested_action": "BUY",
        "setup_name": "breakout_retest",
        "score": 78,
        "confidence": 0.7,
        "evidence_refs": ["evidence:setup"],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }

    registry.validate(SCHEMA_ID, candidate)

    candidate["execution_allowed"] = True
    with pytest.raises(SchemaValidationError, match="False was expected"):
        registry.validate(SCHEMA_ID, candidate)
