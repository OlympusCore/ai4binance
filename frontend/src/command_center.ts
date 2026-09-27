// Presentation adapter for the existing local dashboard. No domain authority.
interface SourceMeta {
  status?: string;
  freshness_status?: string;
  observed_at?: string;
  file?: string;
  producer_status?: string;
}
interface BackgroundObservation {
  market?: string;
  symbol?: string;
  virtual_decision_status?: string;
  risk_approved?: boolean;
  last_success_at?: string;
  blockers?: string[];
}
interface HealthFinding {
  finding_id?: string;
  severity?: string;
  status?: string;
  evidence?: string;
}
interface DashboardSnapshot {
  execution_allowed?: boolean;
  live_eligibility_status?: string;
  generated_at?: string;
  sources?: Record<string, SourceMeta>;
  virtual?: BackgroundObservation;
  operational_readiness?: { status?: string; high_priority_finding_count?: number };
  health_findings?: HealthFinding[];
  decision_history?: {status: string; records: DecisionRecord[]; findings: {source: string; status: string}[]};
}
interface DecisionReference {
  artifact_id: string; artifact_kind: string; cycle_id: string; snapshot_id: string;
  payload_sha256: string; status: string;
  payload?: Record<string, unknown>;
}
interface DecisionRecord {
  decision_id: string; cycle_id: string; snapshot_id: string; observed_at: string;
  status: string; source: string; receipt_status: string; payload_status: string;
  historical_authenticity: string; symbol?: string; market?: string; execution_surface: string;
  action?: string; governance_status: string; blockers: string[]; analysis_blockers: string[];
  stages: {name: string; status: string; blockers: string[]}[];
  references: DecisionReference[];
  timeframes?: string[];
}
declare const root: HTMLElement;
declare const state: {
  page: string; market: string; virtualMarket: string; language: string; mode: string;
};
declare const marketSelections: Record<string, string>;
declare const marketCache: Record<string, { symbols?: string[]; timeframes?: string[] }>;
declare let marketFilter: string;
declare let localData: DashboardSnapshot | null;
declare let lastPollFailed: boolean;
declare function render(): void;
declare function renderLocal(content: HTMLElement): void;
declare function go(page: string): void;
declare function loadMarket(suppressRender?: boolean): Promise<void>;
declare function refreshLocal(): Promise<void>;
declare function refreshLearning(): Promise<void>;
declare function sourceInfo(name: string): SourceMeta;
declare const lastLearningAttempt: number;
declare function observedTime(value?: string): string;
declare function auditObserverPanel(): HTMLElement;
declare function healthFindingsPanel(title: string[], limit?: number): HTMLElement;

const commandCopy = {
  en: {
    overview: 'Overview', decision: 'Decision workbench', evidence: 'Evidence & audit',
    system: 'System & data', attention: 'Needs attention', inspect: 'Inspect decision',
    market: 'Market workspace', symbol: 'Selected symbol', timeframe: 'Timeframe',
    all: 'All timeframes', health: 'System health', freshness: 'Market data freshness',
    blockers: 'High-priority findings', current: 'Background paper decision',
    risk: 'Risk approval', riskStage: 'Reported risk stage', validation: 'Validation', governance: 'Governance assessment',
    absent: 'Not supplied by the current API', sources: 'Source provenance',
    reason: 'Reported blockers', lineage: 'Decision lineage', skip: 'Skip to main content',
    source: 'Source', timestamp: 'Source event time', status: 'Status', producer: 'Producer',
    loading: 'LOADING — Reading canonical local sources',
    disconnected: 'DISCONNECTED — Local state unavailable; automatic retry every 30 seconds',
    scope: 'The background observation has its own market and symbol; workspace filters do not change it.',
    noFindings: 'No current health findings reported. This does not grant trading authority.',
    missingFindings: 'DATA_UNAVAILABLE — Health findings were not supplied.',
    details: 'Technical provenance', support: 'Supporting evidence', counter: 'Counter-evidence',
    missing: 'Missing evidence', conflict: 'Conflicting evidence',
    decisionHelp: 'Read the reported result and blockers before inspecting evidence.',
    evidenceHelp: 'Source freshness and audit evidence; full decision lineage is not connected.',
    systemHelp: 'Service health and data readiness are separate observations.',
    overviewHelp: 'Understand safety, freshness and attention items before investigating.',
    marketHelp: 'Separate Spot and Futures research observations from canonical sources.',
    workspace: 'Existing workspaces', inspection: 'Investigate', language: 'Language',
  },
  tr: {
    overview: 'Genel Bakış', decision: 'Karar inceleme', evidence: 'Kanıt ve denetim',
    system: 'Sistem ve veri', attention: 'Dikkat gerektirenler', inspect: 'Kararı incele',
    market: 'Piyasa çalışma alanı', symbol: 'Seçili koin', timeframe: 'Zaman dilimi',
    all: 'Tüm zaman dilimleri', health: 'Sistem sağlığı', freshness: 'Piyasa verisi güncelliği',
    blockers: 'Yüksek öncelikli bulgular', current: 'Arka plan paper kararı',
    risk: 'Risk onayı', riskStage: 'Bildirilen risk aşaması', validation: 'Doğrulama', governance: 'Yönetişim değerlendirmesi',
    absent: 'Mevcut API bu alanı sağlamıyor', sources: 'Veri kaynakları',
    reason: 'Bildirilen engeller', lineage: 'Karar izlenebilirliği', skip: 'Ana içeriğe geç',
    source: 'Kaynak', timestamp: 'Kaynak olay zamanı', status: 'Durum', producer: 'Üretici',
    loading: 'LOADING — Kanonik yerel kaynaklar okunuyor',
    disconnected: 'DISCONNECTED — Yerel durum alınamadı; 30 saniyede bir yeniden denenir',
    scope: 'Arka plan gözleminin kendi piyasa ve koini vardır; çalışma alanı filtreleri onu değiştirmez.',
    noFindings: 'Güncel sağlık bulgusu bildirilmedi. Bu durum işlem yetkisi sağlamaz.',
    missingFindings: 'DATA_UNAVAILABLE — Sağlık bulguları sağlanmadı.',
    details: 'Teknik kaynak bilgisi', support: 'Destekleyici kanıt', counter: 'Karşı kanıt',
    missing: 'Eksik kanıt', conflict: 'Çelişen kanıt',
    decisionHelp: 'Kanıtlardan önce bildirilen sonucu ve engelleri inceleyin.',
    evidenceHelp: 'Kaynak güncelliği ve denetim kanıtları; tam karar zinciri bağlı değil.',
    systemHelp: 'Servis sağlığı ve veri hazırlığı ayrı gözlemlerdir.',
    overviewHelp: 'Önce güvenlik, güncellik ve dikkat gerektiren durumları görün.',
    marketHelp: 'Kanonik kaynaklardan ayrı Spot ve Futures araştırma gözlemleri.',
    workspace: 'Çalışma alanları', inspection: 'İnceleme', language: 'Dil',
  },
};
type CopyKey = keyof typeof commandCopy.en;
function ccText(key: CopyKey): string {
  return commandCopy[state.language === 'tr' ? 'tr' : 'en'][key];
}
function ccLabel(en: string, tr: string): string { return state.language === 'tr' ? tr : en; }
let commandDecisionId = '';
let commandReferenceId = '';
let commandFindingId = '';
const commandTimeframes: Record<string, string> = {};
let commandMarket = '';
function selectedDecision(): DecisionRecord | undefined {
  const records = localData?.decision_history?.records || [];
  // A disappeared selection must not silently become another decision.
  return commandDecisionId ? records.find(item => item.decision_id === commandDecisionId) : records[0];
}
function decisionStage(item: DecisionRecord | undefined, name: string): string {
  return ccValue(item?.stages.find(stage => stage.name === name)?.status);
}
function ccNode<K extends keyof HTMLElementTagNameMap>(
  tag: K, value = '', className = '',
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.textContent = value;
  node.className = className;
  return node;
}
function ccValue(value: unknown): string {
  return typeof value === 'string' && value.length > 0 ? value : 'DATA_UNAVAILABLE';
}
function ccTone(value: string): string {
  return /VETO|FAIL|BLOCK|CONFLICT|NO_TRADE|DENIED|STALE|DISCONNECTED/.test(value)
    ? 'critical' : /UNAVAILABLE|UNKNOWN|NOT_|LOADING|DEGRADED|COLLECTING|FALSE/.test(value)
      ? 'warning' : 'neutral';
}
function ccRatioPercent(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'DATA_UNAVAILABLE';
  return (100 * value).toLocaleString(state.language === 'tr' ? 'tr-TR' : 'en-US',
    {minimumFractionDigits: 2, maximumFractionDigits: 2}) + '%';
}
function ccReportedCount(value: unknown): string {
  return Array.isArray(value) ? String(value.length) : 'DATA_UNAVAILABLE';
}
function commandOpportunityVisible(row: {measurable_plan?: boolean} | undefined): boolean {
  return row?.measurable_plan === true;
}
function commandLevel(value: unknown): {display: string; sortValue: string; toString(): string} | string {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return 'DATA_UNAVAILABLE';
  const display = Number(value).toLocaleString(state.language === 'tr' ? 'tr-TR' : 'en-US', {maximumFractionDigits: 8});
  return {display, sortValue: String(value), toString: () => display};
}
type CommandFailure = 'UNAUTHORIZED' | 'TIMEOUT' | 'HTTP_ERROR' | 'INVALID_DATA' | 'DISCONNECTED';
let commandFailure: CommandFailure | undefined;
let commandRequest: Promise<void> | undefined;
function commandError(error: unknown): CommandFailure {
  const message = error instanceof Error ? error.message : '';
  if (['UNAUTHORIZED', 'HTTP_ERROR', 'INVALID_DATA'].includes(message)) return message as CommandFailure;
  if (error instanceof Error && ['TimeoutError', 'AbortError'].includes(error.name)) return 'TIMEOUT';
  return 'DISCONNECTED';
}
async function commandFetch(url: string, timeout: number): Promise<DashboardSnapshot> {
  const response = await fetch(url, {cache: 'no-store', signal: AbortSignal.timeout(timeout)});
  if ([401, 403].includes(response.status)) throw new Error('UNAUTHORIZED');
  if (!response.ok) throw new Error('HTTP_ERROR');
  let payload: DashboardSnapshot;
  try { payload = await response.json(); } catch { throw new Error('INVALID_DATA'); }
  if (!payload || payload.execution_allowed !== false || payload.live_eligibility_status !== 'LIVE_ORDER_BLOCKED') throw new Error('INVALID_DATA');
  return payload;
}
async function commandRefreshLocal(): Promise<void> {
  if (commandRequest) return commandRequest;
  commandRequest = (async () => {
    try { localData = await commandFetch('/api/state', 8000); lastPollFailed = false; commandFailure = undefined; }
    catch (error) { localData = null; lastPollFailed = true; commandFailure = commandError(error); }
  })();
  try { await commandRequest; } finally { commandRequest = undefined; }
}
function commandConnectionPanel(): HTMLElement {
  const panel = ccNode('section', '', 'cc-connection'); panel.setAttribute('role', 'status');
  panel.append(ccNode('p', commandFailure ? `${commandFailure} · /api/state` : ccText('loading')));
  if (commandFailure) {
    panel.append(ccNode('p', ccLabel('The local state could not be verified. Previous values are withheld; live orders remain blocked. Automatic retry: 30 seconds.',
      'Yerel durum doğrulanamadı. Önceki değerler gösterilmiyor; canlı emirler kapalı. Otomatik yeniden deneme: 30 saniye.')));
    const retry = ccNode('button', ccLabel('Retry local state', 'Yerel veriyi yeniden dene'), 'aw-button');
    retry.type = 'button'; retry.dataset.commandKey = 'retry-state';
    retry.addEventListener('click', async () => { retry.disabled = true; await refreshLocal(); render(); });
    panel.append(retry);
  }
  return panel;
}
function commandSummary(data: DashboardSnapshot | null) {
  const source = data?.sources?.virtual;
  // The API withholds stale domain payloads; also defend this presentation seam.
  const observation = source?.status === 'CURRENT' ? data?.virtual : undefined;
  const history = data?.sources?.market_history;
  return {
    health: ccValue(data?.operational_readiness?.status),
    freshness: ccValue(history?.freshness_status || history?.status),
    readiness: ccValue(history?.status),
    sourceTime: history?.observed_at,
    findingCount: data?.operational_readiness?.high_priority_finding_count,
    decision: ccValue(observation?.virtual_decision_status),
    risk: typeof observation?.risk_approved === 'boolean'
      ? String(observation.risk_approved).toUpperCase() : 'DATA_UNAVAILABLE',
    market: ccValue(observation?.market), symbol: ccValue(observation?.symbol),
    observedAt: observation?.last_success_at,
    blockers: observation?.blockers,
    sourceStatus: ccValue(source?.status),
  };
}
function ccLink(key: CopyKey, page: string): HTMLButtonElement {
  const button = ccNode('button', ccText(key), 'aw-button');
  button.type = 'button';
  button.dataset.commandKey = `link-${key}`;
  button.addEventListener('click', () => go(page));
  return button;
}
function ccPanel(key: CopyKey): HTMLElement {
  const panel = ccNode('section', '', 'aw-panel cc-panel');
  panel.dataset.panelKey = key;
  panel.append(ccNode('h2', ccText(key)));
  return panel;
}
function ccMetric(label: CopyKey, value: string, note = ''): HTMLElement {
  const card = ccNode('div', '', `cc-metric ${ccTone(value)}`);
  card.append(ccNode('dt', ccText(label)), ccNode('dd', value));
  if (note) card.append(ccNode('small', note));
  return card;
}
function ccMetrics(): HTMLElement {
  const summary = commandSummary(localData);
  const grid = ccNode('dl', '', 'cc-metrics');
  grid.append(
    ccMetric('health', summary.health),
    ccMetric('freshness', summary.freshness, `${summary.readiness} · ${observedTime(summary.sourceTime)}`),
    ccMetric('blockers', typeof summary.findingCount === 'number'
      ? String(summary.findingCount) : 'DATA_UNAVAILABLE'),
    ccMetric('current', summary.sourceStatus === 'CURRENT' ? summary.decision : summary.sourceStatus,
      `${summary.market} · ${summary.symbol} · ${observedTime(summary.observedAt)}`),
    ccMetric('risk', summary.risk === 'TRUE' ? 'APPROVED' : summary.risk === 'FALSE' ? 'NOT_APPROVED' : summary.risk),
  );
  return grid;
}
function ccHistoricalSummary(): HTMLElement {
  const panel = ccPanel('decision');
  const selected = selectedDecision();
  panel.append(ccNode('p', ccLabel('Selected historical receipt — separate from the background observation.',
    'Seçili geçmiş kayıt — arka plan gözleminden ayrıdır.')));
  panel.append(ccNode('p', `${selected?.symbol || 'DATA_UNAVAILABLE'} · ${ccValue(selected?.status)} · ${observedTime(selected?.observed_at)}`));
  const grid = ccNode('dl', '', 'cc-metrics');
  grid.append(ccMetric('riskStage', decisionStage(selected, 'risk')),
    ccMetric('validation', decisionStage(selected, 'validation')),
    ccMetric('governance', ccValue(selected?.governance_status)));
  panel.append(grid, ccLink('inspect', 'decision'));
  return panel;
}
function commandFindingKey(item: HealthFinding): string {
  return `${item.finding_id || ''}|${item.evidence || ''}`;
}
function ccFindingDetail(): HTMLElement | undefined {
  if (!commandFindingId) return undefined;
  const panel = ccPanel('attention');
  const finding = localData?.health_findings?.find(item => commandFindingKey(item) === commandFindingId);
  if (!finding) panel.append(ccNode('p', ccLabel('DATA_UNAVAILABLE — The selected finding is no longer present.',
    'DATA_UNAVAILABLE — Seçili bulgu artık mevcut değil.')));
  else {
    panel.append(ccNode('h3', ccValue(finding.finding_id)),
      ccNode('p', `${ccValue(finding.severity)} · ${ccValue(finding.status)}`, 'cc-blockers'),
      ccNode('p', `${ccText('source')}: ${ccValue(finding.evidence)}`));
    panel.append(ccNode('p', ccLabel('Source reference only; this view does not verify the referenced file contents.',
      'Yalnızca kaynak referansı; bu görünüm referans verilen dosyanın içeriğini doğrulamaz.')));
  }
  return panel;
}
function ccAttention(): HTMLElement {
  const panel = ccPanel('attention');
  const findings = localData?.health_findings;
  if (!Array.isArray(findings)) panel.append(ccNode('p', ccText('missingFindings')));
  else if (findings.length === 0) panel.append(ccNode('p', ccText('noFindings')));
  else {
    const list = ccNode('ul', '', 'cc-findings');
    // Ordering is presentation only; backend severity is retained unchanged.
    [...findings].sort((a, b) => (a.severity || 'P9').localeCompare(b.severity || 'P9'))
      .slice(0, 5).forEach(item => {
        const detail = ccNode('details');
        detail.className = ['P0', 'P1'].includes(item.severity || '') ? 'critical' : ccTone(item.status || '');
        detail.append(ccNode('summary', `${item.severity || 'UNKNOWN'} · ${ccValue(item.finding_id)} · ${ccValue(item.status)}`));
        detail.append(ccNode('p', `${ccText('source')}: ${ccValue(item.evidence)}`));
        const open = ccNode('button', ccText('evidence'), 'aw-button'); open.type = 'button';
        open.dataset.commandKey = `finding:${commandFindingKey(item)}`;
        open.addEventListener('click', () => { commandFindingId = commandFindingKey(item); go('evidence'); });
        detail.append(open);
        const row = ccNode('li'); row.append(detail); list.append(row);
      });
    panel.append(list);
  }
  const observation = commandSummary(localData);
  if (observation.blockers?.length) {
    const list = ccNode('ul', '', 'cc-blockers');
    observation.blockers.slice(0, 5).forEach(value => list.append(ccNode('li', value)));
    panel.append(ccNode('h3', ccText('reason')), list);
  }
  const actions = ccNode('div', '', 'cc-actions');
  actions.append(ccLink('inspect', 'decision'), ccLink('evidence', 'evidence'));
  panel.append(actions);
  return panel;
}
function ccDecision(content: HTMLElement): void {
  const history = localData?.decision_history;
  const chooser = ccPanel('decision');
  const label = ccNode('label', ccLabel('Recorded decision', 'Kayıtlı karar'));
  const select = ccNode('select', '', 'aw-button'); select.dataset.commandKey = 'decision-selection';
  const records = history?.records || [];
  records.forEach(item => {
    const option = ccNode('option', `${item.symbol || 'DATA_UNAVAILABLE'} · ${item.action || 'DATA_UNAVAILABLE'} · ${item.observed_at}`);
    option.value = item.decision_id; select.append(option);
  });
  const selected = selectedDecision();
  select.value = selected?.decision_id || ''; select.disabled = records.length === 0;
  select.addEventListener('change', () => { commandDecisionId = select.value; commandReferenceId = ''; render(); });
  label.append(select); chooser.append(label, ccNode('p', ccValue(history?.status)));
  if (history?.findings.length) {
    const findings = ccNode('ul', '', 'cc-blockers');
    history.findings.forEach(item => findings.append(ccNode('li', `${item.source}: ${item.status}`)));
    chooser.append(findings);
  }
  content.append(chooser);
  if (selected) { ccRecordedDecision(content, selected); return; }
  chooser.append(ccNode('p', ccLabel('No matching canonical decision receipt is available. Background observation follows.',
    'Eşleşen kanonik karar kaydı yok. Arka plan gözlemi aşağıdadır.')));
  content.append(ccMetrics());
  const summary = commandSummary(localData);
  const result = ccPanel('current');
  result.append(ccNode('p', `${summary.market} · ${summary.symbol} · ${observedTime(summary.observedAt)}`));
  result.append(ccNode('p', ccText('scope'), 'aw-caption'));
  result.append(ccNode('h3', ccText('reason')));
  if (summary.blockers?.length) {
    const list = ccNode('ul', '', 'cc-blockers');
    summary.blockers.slice(0, 50).forEach(reason => list.append(ccNode('li', reason)));
    result.append(list);
    if (summary.blockers.length > 50) result.append(ccNode('p', `50 / ${summary.blockers.length}`));
  } else result.append(ccNode('p', summary.blockers ? 'EMPTY' : 'DATA_UNAVAILABLE'));
  const evidence = ccNode('dl', '', 'cc-metrics');
  (['support', 'counter', 'missing', 'conflict'] as CopyKey[]).forEach(key =>
    evidence.append(ccMetric(key, 'DATA_UNAVAILABLE', ccText('absent'))));
  const technical = ccNode('details');
  technical.append(ccNode('summary', ccText('lineage')));
  technical.append(ccNode('p', 'decision_id · cycle_id · snapshot_id · evidence_bundle_id · risk_assessment_id · validation_id: DATA_UNAVAILABLE'));
  technical.append(ccNode('p', `${ccText('source')}: /api/state → virtual; ${summary.sourceStatus}`));
  technical.append(ccNode('p', `risk_approved: ${summary.risk}`));
  result.append(technical, ccLink('evidence', 'evidence'));
  content.append(result, evidence);
}
function ccRecordedDecision(content: HTMLElement, item: DecisionRecord): void {
  const panel = ccPanel('decision');
  const status = ccNode('p', `${item.status} · ${item.action || 'DATA_UNAVAILABLE'} · ${item.symbol || 'DATA_UNAVAILABLE'}`, 'cc-connection');
  status.setAttribute('role', 'status');
  panel.append(status, ccNode('p', `${item.observed_at} · ${item.execution_surface}`),
    ccNode('p', ccLabel('Historical receipt; workspace filters do not relabel this record.',
      'Geçmiş döngü kaydı; çalışma alanı filtreleri bu kaydı yeniden etiketlemez.')));
  panel.append(ccNode('p', `${ccText('timeframe')}: ${item.timeframes?.join(' / ') || 'DATA_UNAVAILABLE'}`));
  const decisionBody = item.references.find(ref => ref.artifact_kind === 'DECISION' && ref.status === 'PAYLOAD_HASH_MATCH')?.payload;
  if (typeof decisionBody?.reason_summary === 'string') panel.append(ccNode('p', decisionBody.reason_summary));
  const metrics = ccNode('dl', '', 'cc-metrics');
  metrics.append(ccMetric('riskStage', decisionStage(item, 'risk')),
    ccMetric('validation', decisionStage(item, 'validation')),
    ccMetric('governance', item.governance_status));
  panel.append(metrics, ccNode('h3', ccText('reason')));
  const blockers = [...new Set([...item.blockers, ...item.analysis_blockers, ...item.stages.flatMap(stage => stage.blockers)])];
  const list = ccNode('ul', '', 'cc-blockers');
  blockers.forEach(reason => list.append(ccNode('li', reason)));
  panel.append(list, ccNode('p', ccLabel('Reported stage completion is not approval. Live orders remain blocked.',
    'Bildirilen aşama tamamlanması onay değildir. Canlı emirler kapalıdır.')));
  const stages = ccNode('details'); stages.append(ccNode('summary', ccText('details')));
  item.stages.forEach(stage => stages.append(ccNode('p', `${stage.name}: ${stage.status}`)));
  panel.append(stages);
  const groups = ccNode('dl', '', 'cc-metrics');
  (['support', 'counter', 'missing', 'conflict'] as CopyKey[]).forEach(key => groups.append(
    ccMetric(key, 'DATA_UNAVAILABLE', ccLabel('The source does not classify evidence into this group.', 'Kaynak, kanıtları bu gruba sınıflandırmıyor.'))));
  panel.append(groups, ccNode('p', `${item.receipt_status} · ${item.historical_authenticity}`));
  panel.append(ccNode('p', ccLabel('Each reference reports its own payload availability and hash check. Historical authenticity is not verified.',
    'Her referans kendi içerik durumunu ve hash kontrolünü gösterir. Geçmiş kaydın özgünlüğü doğrulanmadı.')));
  content.append(panel, ccLineage(item));
}
function ccLineage(item: DecisionRecord): HTMLElement {
  const panel = ccPanel('lineage');
  panel.append(ccNode('p', `${item.cycle_id} · ${item.snapshot_id} · ${item.source}`));
  item.references.forEach(ref => {
    const detail = ccNode('details'); detail.dataset.referenceId = ref.artifact_id;
    detail.append(ccNode('summary', `${ref.artifact_kind} · ${ref.status}`));
    const values = ccNode('dl');
    Object.entries(ref).filter(([key]) => key !== 'payload').forEach(([key, value]) => values.append(ccNode('dt', key), ccNode('dd', String(value))));
    if (ref.payload) {
      const explanation = ccNode('dl');
      Object.entries(ref.payload).forEach(([key, value]) => explanation.append(ccNode('dt', key), ccNode('dd', Array.isArray(value) ? value.join(' · ') : String(value))));
      detail.append(explanation);
    }
    detail.append(values);
    if (state.page === 'decision') {
      const button = ccNode('button', ccLabel('Open in evidence', 'Kanıtlarda aç'), 'aw-button');
      button.type = 'button'; button.addEventListener('click', () => {
        commandDecisionId = item.decision_id; commandReferenceId = ref.artifact_id; go('evidence');
      });
      detail.append(button);
    }
    panel.append(detail);
  });
  return panel;
}
function ccSources(): HTMLElement {
  const panel = ccPanel('sources');
  const wrap = ccNode('div', '', 'aw-tablewrap');
  wrap.tabIndex = 0; wrap.setAttribute('role', 'region');
  wrap.setAttribute('aria-label', ccText('sources'));
  const table = ccNode('table');
  table.dataset.tableKey = 'source-provenance';
  table.append(ccNode('caption', ccText('sources')));
  const head = ccNode('thead'); const header = ccNode('tr');
  (['source', 'status', 'timestamp', 'producer'] as CopyKey[]).forEach(key => {
    const cell = ccNode('th', ccText(key)); cell.scope = 'col'; header.append(cell);
  });
  head.append(header); const body = ccNode('tbody');
  Object.entries(localData?.sources || {}).forEach(([name, meta]) => {
    const row = ccNode('tr');
    [name, ccValue(meta.status), observedTime(meta.observed_at), ccValue(meta.producer_status)]
      .forEach(value => row.append(ccNode('td', value)));
    body.append(row);
  });
  table.append(head, body); wrap.append(table); panel.append(wrap);
  if (!body.children.length) panel.append(ccNode('p', 'DATA_UNAVAILABLE'));
  return panel;
}
function renderCommandCenter(content: HTMLElement): boolean {
  if (!['overview', 'decision', 'evidence', 'system'].includes(state.page)) return false;
  if (!localData) {
    content.append(commandConnectionPanel());
    content.append(ccMetrics()); return true;
  }
  if (state.page === 'overview') content.append(ccMetrics(), ccHistoricalSummary(), ccAttention());
  if (state.page === 'decision') ccDecision(content);
  if (state.page === 'evidence') {
    const finding = ccFindingDetail(); if (finding) content.append(finding);
    const selected = selectedDecision();
    if (selected) content.append(ccLineage(selected));
    content.append(ccSources(), healthFindingsPanel(['All reported findings', 'Bildirilen tüm bulgular'], 100), auditObserverPanel());
  }
  if (state.page === 'system') {
    // Reuse the original operational view without copying its implementation.
    const previous = state.page;
    try { state.page = 'overview'; renderLocal(content); }
    finally { state.page = previous; }
  }
  return true;
}

let commandLastPage = '';
const commandExpanded = new Map<string, Set<string>>();
function ccDetailsKey(detail: HTMLDetailsElement): string {
  if (detail.dataset.referenceId) return `reference:${detail.dataset.referenceId}`;
  if (detail.dataset.detailId) return `detail:${detail.dataset.detailId}`;
  return `${detail.closest('article,section')?.querySelector('h2')?.textContent}|${detail.querySelector('summary')?.textContent}`;
}
function captureCommandView(): string | undefined {
  if (commandLastPage) commandExpanded.set(commandLastPage, new Set(
    Array.from(root.querySelectorAll('details[open]')).map(node => ccDetailsKey(node as HTMLDetailsElement)),
  ));
  const active = document.activeElement as HTMLElement | null;
  if (!active || !root.contains(active)) return undefined;
  if (active.dataset.commandKey) return active.dataset.commandKey;
  if (active.tagName === 'SUMMARY') return `detail:${ccDetailsKey(active.parentElement as HTMLDetailsElement)}`;
  const label = active.getAttribute('aria-label');
  return label ? `label:${label}` : undefined;
}
function prepareCommandRender(): void {
  if (state.mode !== 'local' && ['decision', 'system', 'evidence'].includes(state.page)) state.page = 'overview';
  if (commandMarket && commandMarket !== state.market) commandTimeframes[commandMarket] = marketFilter;
  if (commandMarket !== state.market) marketFilter = commandTimeframes[state.market] || 'All';
  commandMarket = state.market;
}
function enhanceCommandShell(focusKey?: string): void {
  const local = state.mode === 'local';
  const pageChanged = commandLastPage !== '' && commandLastPage !== state.page;
  const main = root.querySelector('main')!;
  main.id = 'cc-main'; main.tabIndex = -1;
  if (!root.querySelector('.cc-skip')) {
    const skip = ccNode('a', ccText('skip'), 'cc-skip'); skip.href = '#cc-main'; root.prepend(skip);
  }
  root.querySelector('.cc-skip')!.textContent = ccText('skip');
  root.querySelector('#aw-eyebrow')!.textContent = 'TRADING & GOVERNANCE COMMAND CENTER';
  const safety = root.querySelector('.aw-safety')!;
  safety.classList.add('cc-safety');
  const safetyLabel = ccNode('strong', 'PAPER_TRADING · LIVE_EXECUTION_DISABLED');
  safetyLabel.id = 'aw-safety';
  safety.replaceChildren(safetyLabel,
    ccNode('span', 'MANUAL_CONFIRMATION · LLM_ADVISORY_ONLY'),
    ccNode('span', 'DETERMINISTIC CORE · LIVE_ORDER_BLOCKED'));
  const nav = root.querySelector('#aw-nav')!;
  let mode = root.querySelector('.cc-persistent-mode');
  if (!mode) {
    mode = ccNode('strong', '', 'cc-persistent-mode');
    root.querySelector('.aw-top')!.append(mode);
  }
  mode.textContent = 'PAPER_TRADING · LIVE_EXECUTION_DISABLED';
  root.style.setProperty('--aw-top-height', `${root.querySelector('.aw-top')!.getBoundingClientRect().height}px`);
  if (local) {
    nav.prepend(ccNode('div', ccText('workspace'), 'cc-navlabel'));
    const group = ccNode('div', '', 'cc-navgroup');
    group.append(ccNode('div', ccText('inspection'), 'cc-navlabel'));
    (['decision', 'evidence', 'system'] as const).forEach(page => {
      const button = ccLink(page, page); button.className = 'aw-nav';
      button.dataset.page = page; button.setAttribute('aria-current', state.page === page ? 'page' : 'false');
      group.append(button);
    });
    nav.append(group);
  }
  const titles: Record<string, CopyKey> = { overview: 'overview', decision: 'decision', evidence: 'evidence', system: 'system' };
  const subtitles: Record<string, CopyKey> = { overview: 'overviewHelp', decision: 'decisionHelp', evidence: 'evidenceHelp', system: 'systemHelp' };
  if (local && titles[state.page]) {
    root.querySelector('#aw-title')!.textContent = ccText(titles[state.page]);
    root.querySelector('#aw-subtitle')!.textContent = ccText(subtitles[state.page]);
  }
  if (local && state.page === 'opportunities') root.querySelector('#aw-subtitle')!.textContent = ccText('marketHelp');
  root.querySelector('#aw-status')!.textContent = root.querySelector('#aw-title')!.textContent;
  root.querySelector('.cc-context')?.remove();
  if (local) {
    const context = ccNode('div', '', 'cc-context');
    const field = (key: CopyKey, values: string[], selected: string, change: (value: string) => void) => {
      const label = ccNode('label', ccText(key));
      const select = ccNode('select', '', 'aw-button'); select.dataset.commandKey = key;
      values.forEach(value => { const option = ccNode('option', value); option.value = value; select.append(option); });
      select.value = selected; select.addEventListener('change', () => change(select.value));
      label.append(select); context.append(label);
    };
    field('market', ['Spot', 'Futures'], state.market, value => {
      state.market = value; render();
    });
    const market = state.market === 'Spot' ? 'SPOT' : 'USD_M_FUTURES';
    const symbol = marketSelections[market];
    const cache = marketCache[`${market}|${symbol}`];
    if (cache?.symbols?.length) field('symbol', cache.symbols, symbol, value => {
      marketSelections[market] = value; marketFilter = 'All'; void loadMarket(); render();
    });
    else context.append(ccNode('span', `${ccText('symbol')}: ${symbol || 'DATA_UNAVAILABLE'}`));
    if (cache?.timeframes?.length) field('timeframe', ['All', ...cache.timeframes], marketFilter, value => {
      marketFilter = value; render();
    });
    field('language', ['en', 'tr'], state.language, value => { state.language = value; render(); });
    safety.after(context);
    if (commandFailure && !['overview', 'decision', 'evidence', 'system'].includes(state.page)) {
      root.querySelector('#aw-content')!.prepend(commandConnectionPanel());
    }
  }
  root.querySelectorAll<HTMLTableCellElement>('th').forEach(cell => { cell.scope = 'col'; });
  root.querySelectorAll<HTMLElement>('.aw-tablewrap').forEach(wrap => {
    wrap.tabIndex = 0; wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', wrap.closest('article,section')?.querySelector('h2')?.textContent || ccText('details'));
  });
  root.querySelectorAll<HTMLDetailsElement>('details').forEach(detail => {
    detail.open = detail.dataset.referenceId === commandReferenceId || commandExpanded.get(state.page)?.has(ccDetailsKey(detail)) || false;
  });
  enhanceCommandTables();
  commandLastPage = state.page;
  if (pageChanged) {
    const heading = root.querySelector<HTMLElement>('#aw-title')!;
    heading.tabIndex = -1; heading.focus({ preventScroll: true });
  } else if (focusKey) {
    root.querySelectorAll<HTMLElement>('[data-command-key],[aria-label],summary').forEach(node => {
      const detailKey = node.tagName === 'SUMMARY' ? `detail:${ccDetailsKey(node.parentElement as HTMLDetailsElement)}` : '';
      if (node.dataset.commandKey === focusKey || `label:${node.getAttribute('aria-label')}` === focusKey || detailKey === focusKey) {
        node.focus({ preventScroll: true });
      }
    });
  }
}

// Both legacy market workspaces now share the same non-authoritative selection.
Object.defineProperty(state, 'virtualMarket', {
  get: () => state.market,
  set: (value: string) => { state.market = value; },
});

interface CommandTableState {query: string; column: number; descending: boolean; page: number}
const commandTables = new Map<string, CommandTableState>();
function commandDecimal(value: string, locale = state.language): {value: bigint; scale: number} | undefined {
  const trimmed = value.trim().replace(/[%\s]/g, '');
  const pattern = locale === 'tr' ? /^[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?$/
    : /^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/;
  if (!pattern.test(trimmed)) return undefined;
  const normalized = locale === 'tr' ? trimmed.replace(/\./g, '').replace(',', '.') : trimmed.replace(/,/g, '');
  const [whole, fraction = ''] = normalized.split('.');
  return {value: BigInt(whole + fraction), scale: fraction.length};
}
function commandCompare(a: string, b: string): number {
  const raw = (value: string) => value.startsWith('number:') ? commandDecimal(value.slice(7), 'en') : commandDecimal(value);
  const left = raw(a), right = raw(b);
  if (left && right) {
    const scale = Math.max(left.scale, right.scale);
    const x = left.value * 10n ** BigInt(scale - left.scale);
    const y = right.value * 10n ** BigInt(scale - right.scale);
    return x < y ? -1 : x > y ? 1 : 0;
  }
  // Missing values remain last in ascending order; identifiers remain textual.
  const missing = (value: string) => ['', '—', 'DATA_UNAVAILABLE'].includes(value.trim());
  if (missing(a) !== missing(b)) return missing(a) ? 1 : -1;
  return a.localeCompare(b, state.language === 'tr' ? 'tr-TR' : 'en-US', {numeric: true});
}
function commandTablePage(rows: string[][], view: CommandTableState): number[] {
  const matching = rows.map((cells, index) => ({cells, index}))
    .filter(row => row.cells.join(' ').toLocaleLowerCase().includes(view.query.toLocaleLowerCase()));
  if (view.column >= 0) matching.sort((a, b) => {
    const compared = commandCompare(a.cells[view.column] || '', b.cells[view.column] || '');
    return (view.descending ? -compared : compared) || a.index - b.index;
  });
  return matching.map(row => row.index);
}
function enhanceCommandTables(): void {
  root.querySelectorAll<HTMLTableElement>('#aw-content table').forEach(table => {
    const body = table.tBodies[0]; if (!body || body.rows.length < 2) return;
    const rows = Array.from(body.rows);
    const cells = rows.map(row => Array.from(row.cells, cell => cell.dataset.sortValue === undefined ? cell.textContent || '' : `number:${cell.dataset.sortValue}`));
    const searchable = rows.map(row => row.textContent || '');
    const owner = table.closest<HTMLElement>('[data-panel-key]')?.dataset.panelKey || table.closest('article,section')?.querySelector('h2')?.textContent || '';
    const identity = `${owner}|${table.dataset.tableKey || Array.from(table.querySelectorAll('th'), cell => cell.textContent).join('|')}`;
    const key = `${state.mode}|${state.page}|${state.market}|${identity}`;
    const view = commandTables.get(key) || {query: '', column: -1, descending: false, page: 0};
    commandTables.set(key, view);
    const controls = ccNode('div', '', 'cc-table-controls');
    const label = ccNode('label', ccLabel('Search table', 'Tabloda ara'));
    const search = ccNode('input'); search.type = 'search'; search.value = view.query;
    search.dataset.commandKey = `table-search-${identity}`; label.append(search);
    const status = ccNode('span'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    const previous = ccNode('button', ccLabel('Previous', 'Önceki'), 'aw-button'); previous.type = 'button';
    const next = ccNode('button', ccLabel('Next', 'Sonraki'), 'aw-button'); next.type = 'button';
    previous.dataset.commandKey = `table-previous-${identity}`; next.dataset.commandKey = `table-next-${identity}`;
    const update = () => {
      const matching = commandTablePage(cells, {...view, query: ''}).filter(i => searchable[i].toLocaleLowerCase().includes(view.query.toLocaleLowerCase()));
      const pages = Math.max(1, Math.ceil(matching.length / 25)); view.page = Math.min(view.page, pages - 1);
      body.replaceChildren(...matching.slice(view.page * 25, (view.page + 1) * 25).map(i => rows[i]));
      status.textContent = `${matching.length} / ${rows.length} · ${view.page + 1} / ${pages}`;
      previous.disabled = view.page === 0; next.disabled = view.page >= pages - 1;
      table.querySelectorAll<HTMLTableCellElement>('thead th').forEach((head, i) =>
        head.setAttribute('aria-sort', i !== view.column ? 'none' : view.descending ? 'descending' : 'ascending'));
    };
    search.addEventListener('input', () => { view.query = search.value; view.page = 0; update(); });
    previous.addEventListener('click', () => { view.page--; update(); });
    next.addEventListener('click', () => { view.page++; update(); });
    table.querySelectorAll<HTMLTableCellElement>('thead th').forEach((head, column) => {
      const button = ccNode('button', head.textContent || '', 'cc-sort'); button.type = 'button';
      button.dataset.commandKey = `table-sort-${identity}-${column}`;
      button.addEventListener('click', () => {
        view.descending = view.column === column && !view.descending; view.column = column; view.page = 0; update();
      }); head.replaceChildren(button);
    });
    controls.append(label, previous, next, status); table.before(controls); update();
  });
}
function finishCommandMarketRefresh(suppressRender: boolean): void {
  if (!suppressRender) render();
}
async function pollLocal(): Promise<void> {
  try {
    await refreshLocal();
    await loadMarket(true);
    if (state.mode === 'local' && localData &&
        ['STALE', 'UNAVAILABLE'].includes(sourceInfo('learning').status || '') &&
        Date.now() - lastLearningAttempt >= 60000) await refreshLearning();
    if (state.mode === 'local') render();
  } finally {
    // Rendering failures must not permanently stop source freshness checks.
    setTimeout(() => { void pollLocal(); }, 30000);
  }
}
