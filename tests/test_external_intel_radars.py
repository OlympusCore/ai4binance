from __future__ import annotations

from datetime import UTC, datetime

from ai4binance.external_intel.core.enums import (
    DecisionImpact,
    RadarName,
    VerificationStatus,
)
from ai4binance.external_intel.core.interfaces import RadarRequest
from ai4binance.external_intel.radars.news_radar import build_connector as news_radar
from ai4binance.external_intel.radars.regulatory_radar import (
    build_connector as regulatory_radar,
)
from ai4binance.external_intel.radars.security_radar import (
    build_connector as security_radar,
)
from ai4binance.external_intel.radars.x_radar import build_connector as x_radar


def test_unavailable_radars_return_standard_data_unavailable_findings() -> None:
    request = RadarRequest(
        run_id="run_unavailable",
        observed_at=datetime(2026, 8, 9, tzinfo=UTC),
        symbol="HOTUSDT",
    )

    for connector in (x_radar(), news_radar(), security_radar(), regulatory_radar()):
        findings = connector.run(request)
        assert len(findings) == 1
        assert findings[0].verification_status is VerificationStatus.DATA_UNAVAILABLE
        assert findings[0].decision_impact is DecisionImpact.DATA_UNAVAILABLE
        assert "DATA_UNAVAILABLE" in findings[0].blockers
        assert findings[0].execution_allowed is False


def test_security_and_regulatory_radars_keep_risk_specific_identity() -> None:
    request = RadarRequest(
        run_id="run_risk",
        observed_at=datetime(2026, 8, 9, tzinfo=UTC),
    )

    assert security_radar().run(request)[0].radar is RadarName.SECURITY_RADAR
    assert regulatory_radar().run(request)[0].radar is RadarName.REGULATORY_RADAR
