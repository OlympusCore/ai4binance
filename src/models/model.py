"""Research-only scenario models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Bias(StrEnum):
    """Expected direction after confirmation."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


class ScenarioStatus(StrEnum):
    """Validation status required by the platform safety contract."""

    RESEARCH_ONLY = "RESEARCH_ONLY"


@dataclass(frozen=True, slots=True)
class ScenarioFamily:
    """Direction-neutral definition of one price-action family."""

    key: str
    name: str
    structure: str
    confirmation: str
    invalidation: str
    false_positive_risk: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject incomplete catalogue records."""
        for field_name in (
            "key",
            "name",
            "structure",
            "confirmation",
            "invalidation",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        if not self.false_positive_risk:
            raise ValueError("false_positive_risk cannot be empty")

    def for_bias(self, bias: Bias) -> Scenario:
        """Create a mirrored, non-executable directional scenario."""
        zone = "demand/support" if bias is Bias.BULLISH else "supply/resistance"
        return Scenario(
            scenario_id=f"{self.key}:{bias.value.lower()}",
            family=self,
            bias=bias,
            reaction_zone=zone,
        )


@dataclass(frozen=True, slots=True)
class Scenario:
    """One directional scenario variant with no order authority."""

    scenario_id: str
    family: ScenarioFamily
    bias: Bias
    reaction_zone: str
    status: ScenarioStatus = ScenarioStatus.RESEARCH_ONLY
    execution_allowed: bool = False

    @property
    def expected_sequence(self) -> tuple[str, ...]:
        """Return a compact, direction-aware observation sequence."""
        break_word = "upward" if self.bias is Bias.BULLISH else "downward"
        return (
            "observe documented structure",
            f"wait for confirmation around {self.reaction_zone}",
            f"validate {break_word} displacement and retest",
            "reject if invalidation condition occurs",
        )


def _family(
    key: str,
    name: str,
    structure: str,
    confirmation: str,
    invalidation: str,
    *risks: str,
) -> ScenarioFamily:
    return ScenarioFamily(
        key=key,
        name=name,
        structure=structure,
        confirmation=confirmation,
        invalidation=invalidation,
        false_positive_risk=risks,
    )


SCENARIO_FAMILIES: tuple[ScenarioFamily, ...] = (
    _family(
        "qm_quick_retest",
        "QM Quick Retest",
        "QM level is revisited immediately after the structure shift.",
        "Reaction and displacement from the QM level.",
        "Close through the protected swing/zone.",
        "premature entry",
        "weak displacement",
    ),
    _family(
        "qm_late_retest",
        "QM Late Retest",
        "Price expands, forms an extended correction, then revisits the older "
        "QM level.",
        "The late retest holds and reclaims/rejects the level.",
        "Acceptance beyond the QM zone.",
        "stale level",
        "trend already reversed",
    ),
    _family(
        "qm_shadow",
        "QM Shadow",
        "A long wick probes the QM area and price rapidly returns.",
        "Wick rejection plus a confirming close away from the zone.",
        "Body acceptance beyond the wick extreme.",
        "single-candle noise",
        "liquidity spike",
    ),
    _family(
        "qm_re_entry",
        "QM Re-Entry",
        "A main QM creates a smaller nested QM used for a second entry opportunity.",
        "Small-QM reaction remains aligned with the main QM.",
        "Main QM is breached and accepted beyond.",
        "nested-level overfitting",
        "late re-entry",
    ),
    _family(
        "continuation_qm",
        "Continuation QM",
        "A QM-like pullback forms inside an established directional structure.",
        "Protected swing holds and trend structure resumes.",
        "Opposing structure break.",
        "confusing reversal with continuation",
        "chop",
    ),
    _family(
        "ignored_qm",
        "Ignored QM (IQM/QMTR)",
        "Price does not respect the first QM and approaches an ignored-QM level.",
        "Wait for fakeout or decisive reaction at IQM; no blind touch entry.",
        "Continued acceptance beyond IQM.",
        "catching a falling knife",
        "level stacking",
    ),
    _family(
        "two_r_two_s_fakeout",
        "2R/2S Fakeout",
        "Two nearby resistance/support references are swept before reversal.",
        "Sweep, close back inside, and break of the local opposing swing.",
        "Price holds outside both references.",
        "range expansion",
        "ambiguous duplicate levels",
    ),
    _family(
        "ruler",
        "Ruler (Pembaris)",
        "Repeated nearly equal touches create a ruler-like horizontal liquidity line.",
        "Liquidity sweep followed by return through the line.",
        "Sustained breakout and successful continuation retest.",
        "subjective touch count",
        "strong breakout",
    ),
    _family(
        "v_twin",
        "V Twin",
        "Two V-shaped reactions form near the same supply/demand boundary.",
        "Second reaction breaks the intervening swing.",
        "Second V fails beyond the zone.",
        "double-top/bottom misread",
        "unequal pivots",
    ),
    _family(
        "mpl",
        "MPL",
        "Repeated reactions form a decision line before a stop hunt into "
        "supply/demand.",
        "Stop hunt engulfs the previous opposing extreme and displaces.",
        "No engulf/displacement after the hunt.",
        "unclear MPL placement",
        "weak engulf",
    ),
    _family(
        "flag_b",
        "Flag B",
        "A flag-limit zone is defined by a compact pause before continuation "
        "or reversal.",
        "Engulf of the previous swing after the zone reaction.",
        "Acceptance through the flag-limit zone.",
        "ordinary consolidation",
        "late confirmation",
    ),
    _family(
        "flag_a_flag_b",
        "Flag A + Flag B",
        "Two linked flag structures combine a proximal trigger and deeper limit zone.",
        "Expected flag sequence completes and the prior swing is engulfed.",
        "Both flag zones fail.",
        "excessive labeling",
        "sequence mismatch",
    ),
    _family(
        "fakeout_v1",
        "Fakeout V1 (Default)",
        "A direct sweep of the range boundary returns into the range.",
        "Re-entry close plus break of the first internal reaction level.",
        "Price reclaims the sweep extreme.",
        "breakout continuation",
        "no displacement",
    ),
    _family(
        "fakeout_v2",
        "Fakeout V2 (S/R Flip)",
        "A swept level changes role from resistance to support or vice versa.",
        "Role-flip retest holds and structure continues.",
        "Retest closes back through the flipped level.",
        "false role flip",
        "wide retest",
    ),
    _family(
        "fakeout_v3_diamond",
        "Fakeout V3 (Diamond)",
        "Alternating higher and lower pivots form a diamond-like liquidity structure.",
        "Head/sweep completes and the opposite side breaks with displacement.",
        "Price remains inside the diamond or breaks the wrong side.",
        "subjective geometry",
        "late entry",
    ),
    _family(
        "fakeout_v3_diamond_sbr",
        "Fakeout V3 (Diamond SBR)",
        "Diamond fakeout is followed by a support-becomes-resistance or "
        "resistance-becomes-support retest.",
        "SBR/RBS retest holds after the diamond break.",
        "Price re-enters and accepts inside the diamond.",
        "failed flip",
        "complex-pattern overfit",
    ),
    _family(
        "double_sr",
        "Double S/R",
        "Several alternating reactions define paired support and resistance "
        "liquidity shelves.",
        "One shelf is swept and the opposite structure is reclaimed/broken.",
        "Price accepts beyond the swept shelf.",
        "range chop",
        "too many equivalent pivots",
    ),
    _family(
        "compression",
        "Compression (CP)",
        "Progressively smaller pullbacks compress price into a supply/demand boundary.",
        "Boundary reaction breaks the compression trendline with displacement.",
        "Clean breakout through the boundary and successful retest.",
        "compression can fuel breakout",
        "trendline subjectivity",
    ),
    _family(
        "three_drive",
        "3 Drive",
        "Three successive drives exhaust into a common boundary.",
        "Third-drive rejection and break of the last drive base.",
        "A fourth accepted drive or clean boundary break.",
        "forced drive counting",
        "strong trend persistence",
    ),
    _family(
        "compression_liquidity",
        "Compression Liquidity (CLQ)",
        "Compression contains an explicit liquidity line near the terminal zone.",
        "Liquidity is swept, then compression breaks in the reversal direction.",
        "Sweep fails to return or the terminal zone is accepted through.",
        "liquidity-line subjectivity",
        "breakout acceleration",
    ),
    _family(
        "can_can",
        "Can-Can",
        "Repeated narrow oscillations accumulate liquidity beneath supply or "
        "above demand.",
        "Terminal sweep/rejection breaks the oscillation base.",
        "Sustained acceptance through the terminal zone.",
        "ordinary range",
        "premature reversal",
    ),
    _family(
        "can_can_fakeout",
        "Can-Can + Fakeout",
        "Can-Can compression ends with a false supply/demand breakout and return.",
        "Fakeout closes back inside and breaks the last internal pivot.",
        "Price retakes the false-break extreme.",
        "real breakout mistaken for fakeout",
        "weak return",
    ),
)

SCENARIOS: tuple[Scenario, ...] = tuple(
    family.for_bias(bias) for family in SCENARIO_FAMILIES for bias in Bias
)
SCENARIO_BY_ID = {scenario.scenario_id: scenario for scenario in SCENARIOS}


def get_scenario(scenario_id: str) -> Scenario:
    """Return a catalogue scenario or raise an explicit lookup error."""
    try:
        return SCENARIO_BY_ID[scenario_id]
    except KeyError as exc:
        raise ValueError(f"unknown scenario_id: {scenario_id}") from exc
