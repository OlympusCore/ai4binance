"""Deterministic test-only inputs for the dashboard presentation boundary."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_icons_preserve_geometry_and_decorative_rendering() -> None:
    """Test-only DOM fixture verifies the existing ten Lucide 1.17.0 icons."""
    node = shutil.which("node")
    assert node is not None, "Dashboard packaging requires an existing Node runtime"
    script = r"""
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import vm from 'node:vm';
// This local DOM fixture is test-only, not a browser or production observation.
class Element {
  constructor(tag, name = '') {
    this.tagName = tag; this.dataset = {lucide: name};
    this.className = 'test-only-decoration'; this.attributes = {};
    this.children = []; this.replacement = null;
  }
  setAttribute(key, value) { this.attributes[key] = value; }
  appendChild(child) { this.children.push(child); }
  replaceWith(node) { assert.equal(this.replacement, null); this.replacement = node; }
}
const document = {createElementNS(namespace, tag) {
  assert.equal(namespace, 'http://www.w3.org/2000/svg');
  assert.ok(['svg', 'path', 'circle', 'rect'].includes(tag));
  return new Element(tag);
}};
const context = vm.createContext({document});
const source = readFileSync('frontend/src/dashboard_icons.ts','utf8');
vm.runInContext(stripTypeScriptTypes(source), context);
const geometry = vm.runInContext('dashboardIconGeometry', context);
// Derived from the original vendored bundle before migration, preserving node order.
assert.equal(createHash('sha256').update(JSON.stringify(geometry)).digest('hex'),
  '39f61d7d558c53f54a8ad28ddc1f9cdb819a9da6f42bafc5e6d90096d8e91336');
const shell = readFileSync('frontend/src/dashboard_shell.ts','utf8');
const markup = readFileSync('src/ai4binance/local_dashboard/design_source.html','utf8');
const pages = shell.slice(
  shell.indexOf('  const pages:'), shell.indexOf('  const opportunities'));
const names = new Set([
  ...Array.from(pages.matchAll(/\['[^']+','([^']+)',/g), match => match[1]),
  ...Array.from(markup.matchAll(/data-lucide="([^"]+)"/g), match => match[1]),
]);
assert.equal(names.size, 10);
for (const name of names) assert.ok(Object.hasOwn(geometry, name), name);
const placeholders = [...names, 'test-only-missing', '__proto__']
  .map(name => new Element('i',name));
context.root = {querySelectorAll(selector) {
  assert.equal(selector, 'i[data-lucide]');
  return placeholders.filter(item => item.replacement === null);
}};
vm.runInContext('renderDashboardIcons(root)', context);
for (const placeholder of placeholders.slice(0,10)) {
  const svg = placeholder.replacement;
  assert.equal(svg.tagName, 'svg');
  assert.equal(svg.attributes['aria-hidden'], 'true');
  assert.equal(svg.attributes.focusable, 'false');
  assert.equal(svg.attributes.width, '16');
  assert.equal(svg.attributes.height, '16');
  assert.equal(svg.attributes.viewBox, '0 0 24 24');
  assert.equal(svg.attributes.stroke, 'currentColor');
  assert.ok(svg.attributes.class.includes('test-only-decoration'));
  const rendered = svg.children.map(child => [child.tagName, child.attributes]);
  assert.equal(JSON.stringify(rendered),
    JSON.stringify(geometry[placeholder.dataset.lucide]));
}
assert.equal(placeholders[10].replacement, null);
assert.equal(placeholders[11].replacement, null);
vm.runInContext('renderDashboardIcons(root)', context);
console.log('DASHBOARD_ICONS_PASS');
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
    assert completed.stdout.strip() == "DASHBOARD_ICONS_PASS"


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
