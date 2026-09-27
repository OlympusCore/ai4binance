"""Deterministic test-only inputs for the dashboard presentation boundary."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_command_center_preserves_reported_safety_and_missing_states() -> None:
    node = shutil.which("node")
    assert node is not None, "Dashboard packaging requires an existing Node runtime"
    script = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import vm from 'node:vm';
const context = vm.createContext({state: {market: 'Spot', virtualMarket: 'Spot'}});
const source = readFileSync('frontend/src/command_center.ts', 'utf8');
vm.runInContext(stripTypeScriptTypes(source), context);
const evaluate = expression => vm.runInContext(expression, context);
assert.equal(evaluate('commandSummary(null).decision'), 'DATA_UNAVAILABLE');
assert.equal(evaluate('commandSummary(null).findingCount'), undefined);
assert.equal(evaluate('commandSummary({virtual:{risk_approved:true}}).risk'),
  'DATA_UNAVAILABLE');
context.fixture = {
  sources: {virtual:{status:'CURRENT'},
    market_history:{status:'COLLECTING',freshness_status:'CURRENT'}},
  virtual:{market:'SPOT',symbol:'TEST_ONLY',virtual_decision_status:'NO_TRADE',risk_approved:false,
    blockers:['TEST_ONLY_RISK_VETO','TEST_ONLY_OOS_NOT_VALIDATED'],score:99},
  operational_readiness:{status:'READY',high_priority_finding_count:0},
};
assert.equal(evaluate('commandSummary(fixture).decision'), 'NO_TRADE');
assert.equal(evaluate('commandSummary(fixture).risk'), 'FALSE');
assert.equal(evaluate('commandSummary(fixture).findingCount'), 0);
assert.equal(evaluate('commandSummary(fixture).market'), 'SPOT');
assert.equal(evaluate('commandSummary(fixture).freshness'), 'CURRENT');
assert.equal(evaluate('commandSummary(fixture).readiness'), 'COLLECTING');
assert.equal(evaluate('commandSummary(fixture).blockers.length'), 2);
assert.equal(evaluate("ccTone('NO_TRADE')"), 'critical');
assert.equal(evaluate("ccTone('GOVERNANCE_CONFLICT')"), 'critical');
assert.equal(evaluate("ccTone('STALE')"), 'critical');
context.fixture.sources.virtual.status = 'STALE';
context.fixture.sources.market_history = {status:'STALE'};
assert.equal(evaluate('commandSummary(fixture).decision'), 'DATA_UNAVAILABLE');
assert.equal(evaluate('commandSummary(fixture).risk'), 'DATA_UNAVAILABLE');
assert.equal(evaluate('commandSummary(fixture).freshness'), 'STALE');
context.fixture.sources.virtual.status = 'INVALID';
assert.equal(evaluate('commandSummary(fixture).decision'), 'DATA_UNAVAILABLE');
evaluate("state.virtualMarket='Futures'");
assert.equal(context.state.market, 'Futures');
evaluate("state.market='Spot'");
assert.equal(context.state.virtualMarket, 'Spot');
// A workspace choice cannot relabel the independently sourced background observation.
context.fixture.sources.virtual.status = 'CURRENT';
context.fixture.virtual.market = 'USD_M_FUTURES';
assert.equal(evaluate('commandSummary(fixture).market'), 'USD_M_FUTURES');
console.log('PRESENTATION_INVARIANTS_PASS');
"""
    completed = subprocess.run(  # noqa: S603
        [node, "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "PRESENTATION_INVARIANTS_PASS"
