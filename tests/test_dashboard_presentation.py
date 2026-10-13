"""Deterministic test-only inputs for the dashboard presentation boundary."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_kaizen_apply_preview_and_result_preserve_human_click_boundary() -> None:
    """Disposable DOM and responses only; no real dashboard or service operation."""
    node = shutil.which("node")
    assert node is not None
    script = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import vm from 'node:vm';
class Element {
  constructor(tag) {this.tagName=tag;this.children=[];this.dataset={};
    this.attributes={};this.listeners={};}
  append(...nodes) {this.children.push(...nodes);}
  setAttribute(key,value) {this.attributes[key]=value;}
  addEventListener(key,value) {this.listeners[key]=value;}
  get cells() {return this.children;}
}
const findings=[
  {finding_id:'MARKET_HISTORY_INCOMPLETE',evidence:'TEST_ONLY_1'},
  {finding_id:'SERVICE_NOT_READY',evidence:'TEST_ONLY_2',facts:{service:'market-history'}},
  {finding_id:'LEARNING_SUMMARY_EMPTY',evidence:'TEST_ONLY_3'},
  {finding_id:'SERVICE_NOT_READY',evidence:'TEST_ONLY_4',facts:{service:'runtime'}}];
const safe={execution_allowed:false,live_eligibility_status:'LIVE_ORDER_BLOCKED'};
const data={...safe,actions:findings.map((item,i)=>({...item,
  token:String(i+1).repeat(64),
  action:['REFRESH_CANDLES','RESTART_MARKET_HISTORY','REFRESH_LEARNING',null][i]})),
  targets:{SPOT:['TESTUSDT'],USD_M_FUTURES:['OTHERUSDT']},job:{state:'NOT_RUN',...safe}};
let posts=[];
const context=vm.createContext({
  state:{market:'Spot',language:'en',mode:'local',page:'kaizen'},
  localData:{health_findings:findings},document:{createElement:tag=>new Element(tag)},
  render:()=>{},refreshLocal:async()=>{},AbortSignal:{timeout:()=>undefined},
  findingCopy:item=>({severity:'P1',title:[item.finding_id,item.finding_id],
    explanation:['TEST_ONLY','TEST_ONLY'],action:['TEST_ONLY','TEST_ONLY'],evidence:item.evidence}),
  fetch:async(path,options)=>{
    if(options.method==='POST'){posts.push(JSON.parse(options.body));
      data.job={state:'COMPLETED',action:'REFRESH_LEARNING',finding_present:true,...safe};
      return {ok:true,json:async()=>data.job};}
    return {ok:true,json:async()=>data};
  }});
vm.runInContext(stripTypeScriptTypes(readFileSync('frontend/src/command_center.ts','utf8')),context);
const evaluate=source=>vm.runInContext(source,context);
context.data=data;context.findings=findings;
assert.equal(evaluate('commandKaizenResponse(data)'),true);
for(const value of [null,{...data,execution_allowed:true},{...data,actions:[null]},
  {...data,targets:{SPOT:['ALL','../../test']}},{...data,job:{state:'COMPLETED',execution_allowed:true}}]){
  context.bad=value;assert.equal(evaluate('commandKaizenResponse(bad)'),false);
}
const panel=evaluate('commandKaizenPanel()');
const rows=panel.children[1].children[0].children[1].children;
assert.equal(rows.length,4);
assert.equal(rows[3].cells[5].children[0].disabled,true);
await evaluate('commandChooseKaizen(findings[0])');
assert.equal(posts.length,0);
const preview=evaluate('commandKaizenPanel()').children.at(-1);
assert.equal(preview.attributes['aria-label'],'Apply action preview');
const selectors=preview.children.filter(node=>node.tagName==='label');
assert.equal(selectors[1].children[0].children.length,1);
assert.equal(selectors[1].children[0].children[0].value,'TESTUSDT');
await evaluate('commandChooseKaizen(findings[2])');
assert.equal(posts.length,0);
await evaluate('commandApplyKaizen()');
assert.equal(posts.length,1);
assert.equal(posts[0].confirmed,true);
assert.equal(posts[0].token,'3'.repeat(64));
assert.deepEqual(Object.keys(posts[0]).sort(),['confirmed','token']);
const result=evaluate('commandKaizenPanel()').children.at(-1);
assert.equal(result.attributes.role,'status');
assert.match(result.children[0].textContent,/Finding remains/);
assert.match(result.textContent,/COMPLETED/);
assert.equal(evaluate("commandKaizenLabel('REFRESH_LEARNING')"),
  'Refresh the canonical learning summary');
context.state.language='tr';
assert.equal(evaluate("commandKaizenLabel('REFRESH_LEARNING')"),
  'Kanonik öğrenim özetini yenile');
console.log('KAIZEN_CLICK_BOUNDARY_PASS');
"""
    completed = subprocess.run(  # noqa: S603 - fixed test-only local script.
        [node, "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert "KAIZEN_CLICK_BOUNDARY_PASS" in completed.stdout


def test_dashboard_types_are_strictly_checked() -> None:
    completed = subprocess.run(
        [sys.executable, "-B", "scripts/check_dashboard_types.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_combined_check_rejects_incompatible_ambient_contract_and_toolchain(
    tmp_path: Path,
) -> None:
    """Only this disposable test copy contains the deliberate type mismatch."""
    shutil.copytree(ROOT / "frontend", tmp_path / "frontend")
    shutil.copytree(ROOT / "config/interface", tmp_path / "config/interface")
    (tmp_path / "scripts").mkdir()
    checker = tmp_path / "scripts/check_dashboard_types.py"
    shutil.copyfile(ROOT / "scripts/check_dashboard_types.py", checker)
    adapter = tmp_path / "frontend/src/command_center.ts"
    source = adapter.read_text(encoding="utf-8")
    adapter.write_text(
        source.replace(
            "declare function render(): void;",
            "declare function render(): Promise<void>;",
        )
        + "\nconst testOnlyReturn: Promise<void> = render();\n",
        encoding="utf-8",
    )
    command = [sys.executable, "-B", str(checker)]
    result = subprocess.run(  # noqa: S603 - fixed test-only compiler command.
        command, capture_output=True, text=True, check=False, timeout=60
    )
    assert result.returncode != 0
    assert "dashboard-composed.ts" in result.stderr
    assert "Type 'void' is not assignable to type 'Promise<void>'" in result.stderr
    pins = tmp_path / "config/interface/dashboard_toolchain.toml"
    pins.write_text('node = "0.0.0"\ntypescript = "0.0.0"\n', encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed test-only compiler command.
        command, capture_output=True, text=True, check=False, timeout=60
    )
    assert result.returncode != 0
    assert "DASHBOARD_TOOLCHAIN_VERSION_MISMATCH" in result.stderr


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
context.state.mode='local';context.state.page='overview';
assert.equal(evaluate('commandShouldLoadMarket()'),true);
assert.equal(evaluate('commandShouldRefreshMarket()'),false);
context.state.page='virtual-market';
assert.equal(evaluate('commandShouldRefreshMarket()'),false);
context.state.simulationScope='selected';
assert.equal(evaluate('commandShouldRefreshMarket()'),true);
context.state.mode='sample';
assert.equal(evaluate('commandShouldLoadMarket()'),false);
assert.equal(evaluate('commandShouldRefreshMarket()'),false);
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
// Test-only reports distinguish retrieval, verification, and symbol association.
assert.equal(evaluate('commandNewsSummary({}).count'), '—');
assert.equal(evaluate('commandNewsSummary({items:[]}).count'), '0');
assert.equal(evaluate(`commandNewsSummary({items:[
  {verification_status:'UNVERIFIED'},
  {asset:'TEST_ONLY',verification_status:'PARTIALLY_VERIFIED'},
  {verification_status:'VERIFIED'},
  {symbol:'  ',verification_status:'VERIFIED'},
  {symbol:'TEST_ONLY',verification_status:'VERIFIED'}]}).count`), '1');
// Test-only DOM: hostile feed titles and URLs must not become executable content.
class NewsElement {
  constructor(tag) { this.tagName=tag; this.children=[]; this.dataset={}; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children=nodes; }
}
context.document={createElement: tag => new NewsElement(tag)};
context.URL=URL;
context.observedTime=value => value || '—';
context.newsFixture={articles:[
  {title:'<script>test-only</script>',canonical_uri:'https://example.com/news',
   provider_id:'test-only',published_at:'test-only-time'},
  {title:'Test-only hostile URL',canonical_uri:'javascript:alert(1)'},
  {title:'Test-only credentials',canonical_uri:'https://user:secret@example.com/'},
  {title:'Test-only invalid URL',canonical_uri:'broken'}]};
const articlePanel=evaluate('commandNewsArticles(newsFixture)');
const rows=articlePanel.children.slice(2);
assert.equal(rows.length,4);
const link=rows[0].children[0].children[0];
assert.equal(link.tagName,'a');
assert.equal(link.textContent,'<script>test-only</script>');
assert.equal(link.href,'https://example.com/news');
assert.equal(link.rel,'noopener noreferrer');
assert.equal(rows[0].children[1].textContent,'test-only · test-only-time');
for (const row of rows.slice(1)) assert.equal(row.children[0].children.length,0);
assert.equal(evaluate('commandNewsArticles({})').children.length,3);
assert.equal(JSON.stringify(evaluate(`commandTablePage([['-10.00'],['-2.00'],['1.00']],
  {query:'',column:0,descending:false,page:0})`)), '[0,1,2]');
assert.equal(JSON.stringify(evaluate(`commandTablePage([['1.09'],['1.1'],['1.2']],
  {query:'',column:0,descending:false,page:0})`)), '[0,1,2]');
assert.equal(evaluate("commandCompare('9007199254740993.01','9007199254740993.02')"),
  -1);
evaluate("state.language='tr'");
assert.match(evaluate('commandNewsSummary({}).coverage'), /sembol baz/);
assert.equal(evaluate("commandCompare('1.234,09','1.234,1')"), -1);
assert.equal(evaluate("commandCompare('-10,00','-2,00')"), -1);
evaluate("state.language='en'");
assert.equal(evaluate('commandLevel(null)'), 'DATA_UNAVAILABLE');
assert.equal(evaluate('commandLevel(0).sortValue'), '0');
context.AbortSignal={timeout:()=>undefined};
const testSnapshot=()=>({schema_version:'DashboardSnapshot/v1',
  generated_at:'2026-09-27T00:00:00Z',
  execution_allowed:false,live_eligibility_status:'LIVE_ORDER_BLOCKED',sources:{},services:[],
  health_findings:[],operational_readiness:{status:'UNAVAILABLE'},
  decision_history:{status:'DATA_UNAVAILABLE',records:[],findings:[]}});
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
context.fetch=async()=>({ok:true,status:200,json:async()=>testSnapshot()});
await evaluate('commandRefreshLocal()');
assert.equal(evaluate('commandFailure'),undefined);
assert.equal(evaluate(`commandError(Object.assign(new Error('slow'),
  {name:'TimeoutError'}))`), 'TIMEOUT');
let requests=0, finishRequest;
context.fetch=()=>{requests++;return new Promise(resolve=>{finishRequest=resolve;});};
const firstRequest=evaluate('commandRefreshLocal()');
const secondRequest=evaluate('commandRefreshLocal()');
assert.equal(requests,1);
finishRequest({ok:true,status:200,json:async()=>testSnapshot()});
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
// Exercise the real loader seam with explicitly test-only API responses.
const legacy=readFileSync('src/ai4binance/local_dashboard/local_views.js','utf8');
const loader=legacy.slice(legacy.indexOf('  async function loadMarket('),
  legacy.indexOf('  async function runMarketRefresh('));
vm.runInContext(loader,context);
context.marketSelections={SPOT:'',USD_M_FUTURES:''};context.marketCache={};
context.marketLoading=new Set();context.marketAttempts={};
context.selectedMarket=()=>context.state.market==='Spot'?'SPOT':'USD_M_FUTURES';
context.marketKey=market=>market+'|'+context.marketSelections[market];
context.finishCommandMarketRefresh=()=>{};
let marketReads=0,marketWrites=0;
context.runMarketRefresh=async()=>{marketWrites++;};
context.fetch=async()=>{marketReads++;return {ok:true,json:async()=>({
  symbol:'TEST_ONLY_BTCUSDT',symbols:['TEST_ONLY_BTCUSDT'],stale:true,
  execution_allowed:false,live_eligibility_status:'LIVE_ORDER_BLOCKED'})};};
context.state.mode='local';context.state.page='overview';context.state.market='Spot';
await evaluate('loadMarket(true)');
assert.equal(context.marketSelections.SPOT,'TEST_ONLY_BTCUSDT');
assert.equal(context.marketCache['SPOT|TEST_ONLY_BTCUSDT'].symbols.length,1);
assert.equal(marketReads,1);assert.equal(marketWrites,0);
context.state.market='Futures';
await evaluate('loadMarket(true)');
assert.equal(context.marketSelections.USD_M_FUTURES,'TEST_ONLY_BTCUSDT');
assert.equal(marketReads,2);assert.equal(marketWrites,0);
context.state.page='virtual-market';
await evaluate('loadMarket(true)');
assert.equal(marketWrites,1);
context.state.mode='sample';
await evaluate('loadMarket(true)');
assert.equal(marketReads,3);assert.equal(marketWrites,1);
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


def test_market_all_symbol_filter_preserves_single_symbol_requests() -> None:
    """ALL is a test-only display selection, never an exchange symbol or job."""
    node = shutil.which("node")
    assert node is not None
    script = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import vm from 'node:vm';
class Element {
  constructor(tag) { this.tagName=tag;this.children=[];this.events={};this.dataset={}; }
  append(child) { this.children.push(child); }
  setAttribute(key,value) { this[key]=value; }
  addEventListener(key,callback) { this.events[key]=callback; }
}
let reads=0,writes=0,snapshotReads=0,renders=0;
const context=vm.createContext({
  document:{createElement:tag=>new Element(tag)},
  state:{mode:'local',page:'opportunities',market:'Spot',language:'en'},
  marketSelections:{SPOT:'TEST_ONLY_A',USD_M_FUTURES:'TEST_ONLY_F'},
  loadMarket:async()=>{reads++;},
  refreshLocal:async()=>{snapshotReads++;},
  runMarketRefresh:async(market,symbol)=>{
    assert.equal(market,'SPOT');assert.equal(symbol,'TEST_ONLY_B');writes++;
  },render:()=>{renders++;},
});
vm.runInContext(stripTypeScriptTypes(
  readFileSync('frontend/src/command_center.ts','utf8')),context);
const evaluate=expression=>vm.runInContext(expression,context);
const select=evaluate(
  "commandMarketSymbolControl('SPOT',['TEST_ONLY_A','TEST_ONLY_B'],false)");
assert.deepEqual(select.children.map(item=>item.value),['ALL','TEST_ONLY_A','TEST_ONLY_B']);
assert.equal(select.children.find(item=>item.selected).value,'TEST_ONLY_A');
select.value='ALL';select.events.change();
assert.equal(context.marketSelections.SPOT,'TEST_ONLY_A');
assert.equal(context.marketSelections.USD_M_FUTURES,'TEST_ONLY_F');
assert.equal(reads,0);assert.equal(writes,0);
assert.equal(evaluate("commandOpportunitySymbolMatches({symbol:'TEST_ONLY_B'},'SPOT')"),true);
assert.equal(evaluate('commandShouldRefreshMarket()'),false);
await evaluate("commandRefreshMarketSelection('SPOT')");
assert.equal(reads,1);assert.equal(writes,0);
select.value='TEST_ONLY_B';select.events.change();
assert.equal(context.marketSelections.SPOT,'TEST_ONLY_B');
assert.equal(evaluate("commandOpportunitySymbolMatches({symbol:'TEST_ONLY_A'},'SPOT')"),false);
assert.equal(evaluate("commandOpportunitySymbolMatches({symbol:'TEST_ONLY_B'},'SPOT')"),true);
assert.equal(evaluate('commandShouldRefreshMarket()'),true);
await evaluate("commandRefreshMarketSelection('SPOT')");
assert.equal(writes,1);
context.state.market='Futures';
assert.equal(evaluate("commandOpportunityAllSymbols('USD_M_FUTURES')"),false);
const futures=evaluate(
  "commandMarketSymbolControl('USD_M_FUTURES',['TEST_ONLY_F'],false)");
futures.value='ALL';futures.events.change();
assert.equal(context.marketSelections.USD_M_FUTURES,'TEST_ONLY_F');
assert.equal(context.marketSelections.SPOT,'TEST_ONLY_B');
context.state.page='virtual-market';
const virtual=evaluate(
  "commandMarketSymbolControl('SPOT',['TEST_ONLY_A','TEST_ONLY_B'],true)");
assert.deepEqual(virtual.children.map(item=>item.value),['ALL','TEST_ONLY_A','TEST_ONLY_B']);
assert.equal(virtual.children.find(item=>item.selected).value,'ALL');
assert.equal(evaluate('commandVirtualAllSymbols()'),true);
assert.equal(evaluate("commandOpportunityAllSymbols('USD_M_FUTURES')"),false);
assert.equal(evaluate('commandShouldRefreshMarket()'),false);
virtual.value='ALL';virtual.events.change();
assert.equal(context.marketSelections.SPOT,'TEST_ONLY_B');
assert.equal(context.marketSelections.USD_M_FUTURES,'TEST_ONLY_F');
assert.equal(context.state.simulationScope,'all');
const beforeVirtualRefresh=renders;
await evaluate("commandRefreshMarketSelection('SPOT')");
assert.equal(snapshotReads,1);assert.equal(writes,1);
assert.equal(renders,beforeVirtualRefresh+1);
assert.match(evaluate("commandMarketScopeNote('SPOT')[0]"),/all eligible symbols/);
virtual.value='TEST_ONLY_A';virtual.events.change();
assert.equal(context.state.simulationScope,'selected');
assert.equal(context.marketSelections.SPOT,'TEST_ONLY_A');
assert.equal(evaluate('commandVirtualAllSymbols()'),false);
assert.equal(evaluate('commandShouldRefreshMarket()'),true);
const virtualFutures=evaluate(
  "commandMarketSymbolControl('USD_M_FUTURES',['ALL','TEST_ONLY_F'],true)");
assert.deepEqual(virtualFutures.children.map(item=>item.value),['ALL','TEST_ONLY_F']);
virtualFutures.value='ALL';virtualFutures.events.change();
assert.equal(context.marketSelections.SPOT,'TEST_ONLY_A');
assert.equal(context.marketSelections.USD_M_FUTURES,'TEST_ONLY_F');
const beforeFuturesRefresh=renders;
await evaluate("commandRefreshMarketSelection('USD_M_FUTURES')");
assert.equal(snapshotReads,2);assert.equal(writes,1);
assert.equal(renders,beforeFuturesRefresh+1);
context.state.simulationScope='selected';
const restored=evaluate("commandMarketSymbolControl('SPOT',['TEST_ONLY_A'],true)");
assert.equal(restored.children.find(item=>item.selected).value,'TEST_ONLY_A');
context.state.page='opportunities';
assert.equal(evaluate("commandOpportunitySymbolMatches({symbol:'TEST_ONLY_A'},'SPOT')"),true);
assert.equal(evaluate("commandOpportunitySymbolMatches({symbol:'TEST_ONLY_B'},'SPOT')"),false);
context.state.language='tr';
const localized=evaluate("commandMarketSymbolControl('SPOT',[],false)");
assert.equal(localized['aria-label'],'Sembol');
assert.equal(localized.children[0].value,'ALL');
console.log('OPPORTUNITY_SYMBOL_FILTER_PASS');
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
    assert completed.stdout.strip() == "OPPORTUNITY_SYMBOL_FILTER_PASS"


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
