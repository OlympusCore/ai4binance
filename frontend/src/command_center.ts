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
  generated_at?: string;
  sources?: Record<string, SourceMeta>;
  virtual?: BackgroundObservation;
  operational_readiness?: { status?: string; high_priority_finding_count?: number };
  health_findings?: HealthFinding[];
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
declare function loadMarket(): Promise<void>;
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
    risk: 'Risk approval', validation: 'Validation', governance: 'Governance assessment',
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
    workspace: 'Existing workspaces', inspection: 'Investigate', language: 'Language',
  },
  tr: {
    overview: 'Genel Bakış', decision: 'Karar inceleme', evidence: 'Kanıt ve denetim',
    system: 'Sistem ve veri', attention: 'Dikkat gerektirenler', inspect: 'Kararı incele',
    market: 'Piyasa çalışma alanı', symbol: 'Seçili koin', timeframe: 'Zaman dilimi',
    all: 'Tüm zaman dilimleri', health: 'Sistem sağlığı', freshness: 'Piyasa verisi güncelliği',
    blockers: 'Yüksek öncelikli bulgular', current: 'Arka plan paper kararı',
    risk: 'Risk onayı', validation: 'Doğrulama', governance: 'Yönetişim değerlendirmesi',
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
    workspace: 'Çalışma alanları', inspection: 'İnceleme', language: 'Dil',
  },
};
type CopyKey = keyof typeof commandCopy.en;
function ccText(key: CopyKey): string {
  return commandCopy[state.language === 'tr' ? 'tr' : 'en'][key];
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
function commandSummary(data: DashboardSnapshot | null) {
  const source = data?.sources?.virtual;
  // The API withholds stale domain payloads; also defend this presentation seam.
  const observation = source?.status === 'CURRENT' ? data?.virtual : undefined;
  const history = data?.sources?.market_history;
  return {
    health: ccValue(data?.operational_readiness?.status),
    freshness: ccValue(history?.freshness_status || history?.status),
    readiness: ccValue(history?.status),
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
    ccMetric('freshness', summary.freshness, summary.readiness),
    ccMetric('blockers', typeof summary.findingCount === 'number'
      ? String(summary.findingCount) : 'DATA_UNAVAILABLE'),
    ccMetric('current', summary.decision, `${summary.market} · ${summary.symbol}`),
    ccMetric('risk', summary.risk, 'risk_approved'),
    ccMetric('validation', 'DATA_UNAVAILABLE', ccText('absent')),
    ccMetric('governance', 'DATA_UNAVAILABLE', ccText('absent')),
  );
  return grid;
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
        detail.append(ccNode('summary', `${item.severity || 'UNKNOWN'} · ${ccValue(item.finding_id)} · ${ccValue(item.status)}`));
        detail.append(ccNode('p', `${ccText('source')}: ${ccValue(item.evidence)}`));
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
  result.append(technical, ccLink('evidence', 'evidence'));
  content.append(result, evidence);
}
function ccSources(): HTMLElement {
  const panel = ccPanel('sources');
  const wrap = ccNode('div', '', 'aw-tablewrap');
  wrap.tabIndex = 0; wrap.setAttribute('role', 'region');
  wrap.setAttribute('aria-label', ccText('sources'));
  const table = ccNode('table');
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
    const message = ccNode('p', ccText(lastPollFailed ? 'disconnected' : 'loading'), 'cc-connection');
    message.setAttribute('role', 'status'); content.append(message);
    content.append(ccMetrics()); return true;
  }
  if (state.page === 'overview') content.append(ccMetrics(), ccAttention());
  if (state.page === 'decision') ccDecision(content);
  if (state.page === 'evidence') {
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
  return `${detail.closest('article,section')?.querySelector('h2')?.textContent}|${detail.querySelector('summary')?.textContent}`;
}
function captureCommandView(): string | undefined {
  if (commandLastPage) commandExpanded.set(commandLastPage, new Set(
    Array.from(root.querySelectorAll('details[open]')).map(node => ccDetailsKey(node as HTMLDetailsElement)),
  ));
  const active = document.activeElement as HTMLElement | null;
  return active?.dataset.commandKey;
}
function prepareCommandRender(): void {
  if (state.mode !== 'local' && ['decision', 'system', 'evidence'].includes(state.page)) state.page = 'overview';
}
function enhanceCommandShell(focusKey?: string): void {
  const local = state.mode === 'local';
  const main = root.querySelector('main')!;
  main.id = 'cc-main'; main.tabIndex = -1;
  if (!root.querySelector('.cc-skip')) {
    const skip = ccNode('a', ccText('skip'), 'cc-skip'); skip.href = '#cc-main'; root.prepend(skip);
  }
  root.querySelector('.cc-skip')!.textContent = ccText('skip');
  root.querySelector('#aw-eyebrow')!.textContent = 'TRADING & GOVERNANCE COMMAND CENTER';
  const safety = root.querySelector('.aw-safety')!;
  safety.classList.add('cc-safety');
  safety.replaceChildren(ccNode('strong', 'PAPER_TRADING · LIVE_EXECUTION_DISABLED'),
    ccNode('span', 'MANUAL_CONFIRMATION · LLM_ADVISORY_ONLY'),
    ccNode('span', 'DETERMINISTIC CORE · LIVE_ORDER_BLOCKED'));
  const nav = root.querySelector('#aw-nav')!;
  let mode = root.querySelector('.cc-persistent-mode');
  if (!mode) {
    mode = ccNode('strong', '', 'cc-persistent-mode');
    root.querySelector('.aw-top')!.append(mode);
  }
  mode.textContent = 'PAPER_TRADING · LIVE_EXECUTION_DISABLED';
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
  }
  root.querySelectorAll<HTMLTableCellElement>('th').forEach(cell => { cell.scope = 'col'; });
  root.querySelectorAll<HTMLElement>('.aw-tablewrap').forEach(wrap => {
    wrap.tabIndex = 0; wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', wrap.closest('article,section')?.querySelector('h2')?.textContent || ccText('details'));
  });
  root.querySelectorAll<HTMLDetailsElement>('details').forEach(detail => {
    detail.open = commandExpanded.get(state.page)?.has(ccDetailsKey(detail)) || false;
  });
  commandLastPage = state.page;
  if (focusKey) root.querySelectorAll<HTMLElement>('[data-command-key]').forEach(node => {
    if (node.dataset.commandKey === focusKey) node.focus({ preventScroll: true });
  });
}

// Both legacy market workspaces now share the same non-authoritative selection.
Object.defineProperty(state, 'virtualMarket', {
  get: () => state.market,
  set: (value: string) => { state.market = value; },
});
