"""Deterministic test-only inputs for the dashboard presentation boundary."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_types_are_strictly_checked() -> None:
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-B", "scripts/check_dashboard_types.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


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
assert.equal(evaluate('ccRatioPercent(null)'), 'DATA_UNAVAILABLE');
assert.equal(evaluate('ccRatioPercent(undefined)'), 'DATA_UNAVAILABLE');
assert.equal(evaluate('ccRatioPercent(0)'), '0.00%');
assert.equal(evaluate('ccRatioPercent(NaN)'), 'DATA_UNAVAILABLE');
assert.equal(evaluate('ccRatioPercent(0.1)'), '10.00%');
assert.equal(evaluate('ccReportedCount(undefined)'), 'DATA_UNAVAILABLE');
assert.equal(evaluate('ccReportedCount([])'), '0');
assert.equal(evaluate('commandOpportunityVisible(undefined)'), false);
assert.equal(evaluate('commandOpportunityVisible({measurable_plan:true})'), true);
assert.equal(evaluate('commandOpportunityVisible({measurable_plan:false,score:99})'),
  false);
assert.equal(JSON.stringify(evaluate(`commandTablePage([['-10.00'],['-2.00'],['1.00']],
  {query:'',column:0,descending:false,page:0})`)), '[0,1,2]');
assert.equal(JSON.stringify(evaluate(`commandTablePage([['1.09'],['1.1'],['1.2']],
  {query:'',column:0,descending:false,page:0})`)), '[0,1,2]');
assert.equal(evaluate("commandCompare('9007199254740993.01','9007199254740993.02')"),
  -1);
evaluate("state.language='tr'");
assert.equal(evaluate("commandCompare('1.234,09','1.234,1')"), -1);
assert.equal(evaluate("commandCompare('-10,00','-2,00')"), -1);
evaluate("state.language='en'");
assert.equal(evaluate('commandLevel(null)'), 'DATA_UNAVAILABLE');
assert.equal(evaluate('commandLevel(0).sortValue'), '0');
context.AbortSignal={timeout:()=>undefined};
context.localData=null;context.lastPollFailed=false;
for(const [status,expected] of [[403,'UNAUTHORIZED'],[503,'HTTP_ERROR']]){
  context.fetch=async()=>({ok:false,status});
  await evaluate('commandRefreshLocal()');
  assert.equal(evaluate('commandFailure'),expected);
  assert.equal(context.localData,null);
}
context.fetch=async()=>({ok:true,status:200,json:async()=>({execution_allowed:true})});
await evaluate('commandRefreshLocal()');
assert.equal(evaluate('commandFailure'),'INVALID_DATA');
context.fetch=async()=>({ok:true,status:200,json:async()=>({execution_allowed:false,
  live_eligibility_status:'LIVE_ORDER_BLOCKED'})});
await evaluate('commandRefreshLocal()');
assert.equal(evaluate('commandFailure'),undefined);
assert.equal(evaluate(`commandError(Object.assign(new Error('slow'),
  {name:'TimeoutError'}))`), 'TIMEOUT');
let requests=0, finishRequest;
context.fetch=()=>{requests++;return new Promise(resolve=>{finishRequest=resolve;});};
const firstRequest=evaluate('commandRefreshLocal()');
const secondRequest=evaluate('commandRefreshLocal()');
assert.equal(requests,1);
finishRequest({ok:true,status:200,json:async()=>({execution_allowed:false,
  live_eligibility_status:'LIVE_ORDER_BLOCKED'})});
await Promise.all([firstRequest,secondRequest]);
assert.equal(JSON.stringify(evaluate(`commandTablePage([['a','10'],['b','2'],['c','2']],
  {query:'',column:1,descending:false,page:0})`)), '[1,2,0]');
assert.equal(JSON.stringify(evaluate(`commandTablePage([['Alpha'],['Beta']],
  {query:'ALPHA',column:-1,descending:false,page:0})`)), '[0]');
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
context.localData={decision_history:{records:[{decision_id:'TEST_ONLY_1'},
  {decision_id:'TEST_ONLY_2'}]}};
assert.equal(evaluate('selectedDecision().decision_id'),'TEST_ONLY_1');
evaluate("commandDecisionId='TEST_ONLY_2'");
assert.equal(evaluate('selectedDecision().decision_id'),'TEST_ONLY_2');
context.localData.decision_history.records.pop();
assert.equal(evaluate('selectedDecision()'),undefined);
let renders=0, schedules=0;
context.localData=null;
context.refreshLocal=async()=>{};
context.loadMarket=async suppress=>assert.equal(suppress,true);
context.render=()=>{renders++;};
context.setTimeout=(callback,delay)=>{assert.equal(delay,30000);schedules++;};
context.state.mode='local';
await evaluate('pollLocal()');
assert.equal(renders,1); assert.equal(schedules,1);
context.render=()=>{throw new Error('TEST_ONLY_RENDER_FAILURE');};
await assert.rejects(evaluate('pollLocal()'),/TEST_ONLY_RENDER_FAILURE/);
assert.equal(schedules,2);
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


def test_localized_and_missing_row_values_remain_dom_nodes() -> None:
    node = shutil.which("node")
    assert node is not None
    script = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import vm from 'node:vm';
class Node {
  constructor(value) { this.value=value; this.children=[]; }
  appendChild(child) { assert.ok(child instanceof Node); this.children.push(child); }
}
const context=vm.createContext({Node,
  el:(tag,css,value)=>new Node(Array.isArray(value)?value[0]:value),
  append:(parent,...children)=>{
    children.forEach(c=>parent.appendChild(c));return parent;
  },
});
const shell=readFileSync('frontend/src/dashboard_shell.ts','utf8');
const start=shell.indexOf('  function row(');
const source=shell.slice(start, shell.indexOf('\n',start));
vm.runInContext(stripTypeScriptTypes(source),context);
const value=expression=>vm.runInContext(expression+'.children[1].value',context);
assert.equal(value("row('method',['Test-only method','Translation'])"),
  'Test-only method');
assert.equal(value("row('missing',undefined)"),'DATA_UNAVAILABLE');
assert.equal(value("row('zero',0)"),0);
assert.equal(value("row('node',new Node('test'))"),'test');
console.log('ROW_DOM_PASS');
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
    assert completed.stdout.strip() == "ROW_DOM_PASS"
