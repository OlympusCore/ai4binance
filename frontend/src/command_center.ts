// Presentation adapter for the existing local dashboard. No domain authority.
interface SourceMeta {
  status?: string;
  freshness_status?: string;
  observed_at?: string | null;
  file?: string;
  producer_status?: string | null;
}
interface RadarRun {
  state?: string; completed_at?: string; started_at?: string; exit_code?: number;
  result?: {result_status?: string; item_count?: number; blockers?: string[]};
}
function commandRadarPresentation(info: RadarRun, now = Date.now()) {
  const running = info.state === 'RUNNING';
  const notRun = !info.state || info.state === 'NOT_RUN';
  const failed = !running && (info.state === 'COMPLETED_WITH_BLOCKERS'
    || (typeof info.exit_code === 'number' && info.exit_code !== 0));
  const completed = Date.parse(info.completed_at || '');
  const age = Number.isFinite(completed) && completed <= now ? now - completed : null;
  const minutes = age === null ? null : Math.floor(age / 60000);
  const ageText = minutes === null ? ccLabel('Not reported', 'Bildirilmedi')
    : minutes < 60 ? ccLabel(`${minutes} min ago`, `${minutes} dakika önce`)
    : minutes < 1440 ? ccLabel(`${Math.floor(minutes / 60)} h ago`, `${Math.floor(minutes / 60)} saat önce`)
    : ccLabel(`${Math.floor(minutes / 1440)} days ago`, `${Math.floor(minutes / 1440)} gün önce`);
  const status = info.result?.result_status || 'UNKNOWN';
  const empty = status === 'NO_CANDIDATES' && !failed;
  return {
    label: running ? ccLabel('Running', 'Çalışıyor') : notRun
      ? ccLabel('Not run', 'Çalıştırılmadı') : failed
        ? ccLabel('Last run blocked', 'Son tarama engellendi')
        : info.state === 'COMPLETED' ? ccLabel('Past run completed', 'Geçmiş tarama tamamlandı')
        : ccLabel('Run status unavailable', 'Tarama durumu mevcut değil'),
    result: empty ? ccLabel('No candidates found', 'Aday bulunamadı') : status,
    age: ageText,
    note: running ? ccLabel('A new scan is running.', 'Yeni tarama sürüyor.') : notRun
      ? ccLabel('Select Refresh to start a bounded research scan.', 'Sınırlı araştırma taraması için Yenile seçin.')
      : ccLabel('Stored result from the last scan. Select Refresh for a new scan.',
        'Son taramanın kayıtlı sonucu. Yeni tarama için Yenile seçin.'),
    empty: empty ? ccLabel('The scan completed without candidates. This is a research result.',
      'Tarama aday bulmadan tamamlandı. Bu bir araştırma sonucudur.')
      : ccLabel('No findings are available. Review the result and reported blockers.',
        'Bulgu mevcut değil. Sonucu ve bildirilen engelleri inceleyin.'),
  };
}
interface ResearchProgress {
  active_symbol?: string; active_timeframe?: string;
  completed_symbol_count?: number; eligible_symbol_count?: number; pending_symbol_count?: number;
}
function commandResearchActivity(research: ResearchProgress, source: SourceMeta = {}) {
  const current = source.freshness_status === 'CURRENT'
    && source.status === 'READY' && source.producer_status === 'READY';
  const idle = current && !research.active_symbol && research.pending_symbol_count === 0
    && typeof research.eligible_symbol_count === 'number' && research.eligible_symbol_count > 0
    && research.completed_symbol_count === research.eligible_symbol_count;
  return {
    symbol: research.active_symbol || ccLabel('No active symbol', 'Aktif koin yok'),
    timeframe: research.active_timeframe || ccLabel('No active timeframe', 'Aktif zaman dilimi yok'),
    note: !current ? ccLabel('Research activity is not verified as current. Inspect source status.',
      'Araştırma faaliyeti güncel olarak doğrulanmadı. Kaynak durumunu inceleyin.') : idle
      ? ccLabel('Scan complete; no symbol is being processed.', 'Tarama tamamlandı; şu anda işlenen koin yok.')
      : research.active_symbol ? ccLabel('Research is processing the reported symbol.',
        'Araştırma bildirilen koini işliyor.')
      : ccLabel('No active work is reported. Review queued symbols and source status.',
        'Aktif çalışma bildirilmedi. Bekleyen koinleri ve kaynak durumunu inceleyin.'),
  };
}
interface BackgroundObservation {
  market?: string | null;
  symbol?: string | null;
  virtual_decision_status?: string | null;
  risk_approved?: boolean | null;
  last_success_at?: string | null;
  blockers?: string[];
  dashboard_simulation_projection?: Record<string, unknown>;
  dashboard_futures_simulation_projection?: Record<string, unknown>;
}

function commandVirtualMarketState(market: string): BackgroundObservation {
  const daemon = localData?.virtual || {};
  const projection = market === 'USD_M_FUTURES'
    ? daemon.dashboard_futures_simulation_projection
    : daemon.dashboard_simulation_projection;
  if (daemon.market === market) return {...daemon, dashboard_simulation_projection: projection};
  const rows = commandVirtualObservations(projection);
  const latest = rows.slice().sort((a, b) =>
    String(b.observed_at || '').localeCompare(String(a.observed_at || '')))[0];
  return {...latest, market, dashboard_simulation_projection: projection};
}

interface VirtualCandidateDiagnostic {
  candidate_id: string; setup: string; timeframe: string; status: string; blockers: string[];
}
interface VirtualValidationEvidence {
  snapshot_id: string; symbol: string; market: string; deployment_path?: string;
  loaded_subject_count: number; symbol_subject_count: number; load_blockers: string[];
}
interface VirtualObservation extends BackgroundObservation {
  snapshot_id?: string;
  candidate_diagnostics?: VirtualCandidateDiagnostic[];
  validation_evidence?: VirtualValidationEvidence;
  state?: string;
  status?: string;
  observed_at?: string;
  completed_at?: string;
  scan_lane?: string;
  candidate_count?: number;
  virtual_runtime_evaluated?: boolean;
  virtual_simulation_outcome?: string;
  virtual_order_ready?: boolean;
}
function commandVirtualObservation(value: unknown): VirtualObservation {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const raw = value as Record<string, unknown>;
  const result: VirtualObservation = {};
  for (const key of ['symbol', 'market', 'state', 'status', 'observed_at',
    'completed_at', 'last_success_at', 'scan_lane', 'snapshot_id', 'virtual_decision_status', 'virtual_simulation_outcome'] as const) {
    if (typeof raw[key] === 'string') result[key] = raw[key];
  }
  for (const key of ['virtual_runtime_evaluated', 'risk_approved', 'virtual_order_ready'] as const) {
    if (typeof raw[key] === 'boolean') result[key] = raw[key];
  }
  if (typeof raw.candidate_count === 'number' && Number.isSafeInteger(raw.candidate_count)
    && raw.candidate_count >= 0) result.candidate_count = raw.candidate_count;
  result.blockers = Array.isArray(raw.blockers)
    ? raw.blockers.filter((item): item is string => typeof item === 'string') : [];
  if (Array.isArray(raw.candidate_diagnostics)) {
    result.candidate_diagnostics = raw.candidate_diagnostics.filter((item): item is VirtualCandidateDiagnostic =>
      !!item && typeof item === 'object' && ['candidate_id', 'setup', 'timeframe', 'status'].every(
        key => typeof item[key] === 'string' && item[key].length > 0) && Array.isArray(item.blockers)
      && item.blockers.every((value: unknown) => typeof value === 'string'));
  }
  const evidence = raw.validation_evidence as Partial<VirtualValidationEvidence> | null;
  if (evidence && ['snapshot_id', 'symbol', 'market'].every(key =>
    typeof raw[key] === 'string' && (evidence as Record<string, unknown>)[key] === raw[key])
    && typeof evidence.loaded_subject_count === 'number' && Number.isSafeInteger(evidence.loaded_subject_count)
    && typeof evidence.symbol_subject_count === 'number' && Number.isSafeInteger(evidence.symbol_subject_count)
    && evidence.symbol_subject_count >= 0 && evidence.symbol_subject_count <= evidence.loaded_subject_count
    && Array.isArray(evidence.load_blockers) && evidence.load_blockers.every(value => typeof value === 'string')) {
    result.validation_evidence = evidence as VirtualValidationEvidence;
  }
  return result;
}
function commandVirtualObservations(value: unknown): VirtualObservation[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  const rows = (value as Record<string, unknown>).symbol_observations;
  return Array.isArray(rows) ? rows.map(commandVirtualObservation)
    .filter(row => typeof row.symbol === 'string' && row.symbol.trim().length > 0) : [];
}
function commandVirtualFlag(value: unknown): string {
  return value === true ? ccLabel('Yes', 'Evet') : value === false
    ? ccLabel('No', 'Hayır') : ccLabel('Not reported', 'Bildirilmedi');
}
function commandVirtualOrderLabel(value: unknown): string {
  return value === true ? ccLabel('Ready', 'Hazır') : value === false
    ? ccLabel('Not ready', 'Hazır değil') : ccLabel('Not reported', 'Bildirilmedi');
}
function commandVirtualFlagCount(rows: VirtualObservation[],
  key: 'virtual_runtime_evaluated' | 'risk_approved' | 'virtual_order_ready'): string {
  const reported = rows.filter(row => typeof row[key] === 'boolean');
  if (!reported.length) return ccLabel('Not reported', 'Bildirilmedi');
  const yes = reported.filter(row => row[key] === true).length;
  const unknown = rows.length - reported.length;
  return `${yes} / ${rows.length}` + (unknown
    ? ccLabel(` · ${unknown} not reported`, ` · ${unknown} bildirilmedi`) : '');
}
interface VirtualSimulationView extends VirtualObservation {
  runtime_display: string; risk_display: string; order_display: string; note: string;
  blocker_records: VirtualObservation[];
}
function commandVirtualSimulationView(market: string, daemon: unknown, projection: unknown,
  scope: string, symbol: string, manual: unknown): VirtualSimulationView {
  const background = commandVirtualObservation(daemon);
  // Merge only the exact symbol, market and observation time; never borrow approvals.
  const rows = commandVirtualObservations(projection).map(row => {
    const sameObservation = background.symbol === row.symbol && background.market === market
      && Date.parse(background.last_success_at || background.observed_at || '') === Date.parse(row.observed_at || '');
    return sameObservation ? {...background, ...row} : row;
  });
  if (scope === 'all') {
    const raw = projection && typeof projection === 'object'
      ? projection as Record<string, unknown> : {};
    const completeCounts = rows.length > 0 && rows.every(row => row.candidate_count !== undefined);
    const total = completeCounts ? rows.reduce((sum, row) => sum + row.candidate_count!, 0) : undefined;
    return {
      state: typeof raw.status === 'string' ? raw.status : 'DATA_UNAVAILABLE',
      virtual_decision_status: ccLabel('Per-coin decisions — see table', 'Koin bazlı kararlar — tabloya bakın'),
      candidate_count: total !== undefined && Number.isSafeInteger(total) ? total : undefined,
      runtime_display: commandVirtualFlagCount(rows, 'virtual_runtime_evaluated'),
      risk_display: commandVirtualFlagCount(rows, 'risk_approved'),
      order_display: commandVirtualFlagCount(rows, 'virtual_order_ready'),
      blockers: [...new Set(rows.flatMap(row => row.blockers || []))],
      blocker_records: rows,
      note: ccLabel('Summary of the latest observation for each coin. Blockers belong to individual coin records; this is not a shared trade decision.',
        'Her koinin son gözleminin özeti. Engeller ilgili koin kayıtlarına aittir; bu ortak bir işlem kararı değildir.'),
    };
  }
  const requested = commandVirtualObservation(manual);
  const selected = rows.find(row => row.symbol === symbol);
  const observation = selected || (requested.symbol === symbol && requested.market === market ? requested : {});
  const noReadyCandidate = observation.blockers?.includes('NO_READY_CANDIDATE') === true;
  return {
    ...observation,
    state: observation.virtual_simulation_outcome || observation.state || 'DATA_UNAVAILABLE',
    runtime_display: commandVirtualFlag(observation.virtual_runtime_evaluated),
    risk_display: commandVirtualFlag(observation.risk_approved),
    order_display: commandVirtualFlag(observation.virtual_order_ready),
    blocker_records: [observation],
    note: noReadyCandidate
      ? ccLabel('Analysis found no ready trade candidate. Virtual execution waits for a complete candidate, risk assessment and the existing validation/governance gates.',
        'Analizde işleme hazır aday bulunmadı. Sanal işlem; tam aday, risk değerlendirmesi ve mevcut doğrulama/yönetişim kapılarını bekliyor.')
      : ccLabel('Only reported values for this coin are shown. Missing evidence is not a negative verdict.',
        'Yalnızca bu koin için bildirilen değerler gösterilir. Eksik kanıt, olumsuz değerlendirme sonucu değildir.'),
  };
}
function commandVirtualSimulationBlockers(view: VirtualSimulationView): HTMLElement {
  const container = ccNode('div');
  for (const record of view.blocker_records) {
    if (!record.blockers?.length) continue;
    const detail = ccNode('details', '', 'cc-panel');
    detail.append(ccNode('summary', `${record.symbol || ccLabel('Selected coin', 'Seçili koin')} · ${record.blockers.length} ${ccLabel('reported blockers', 'bildirilen engel')}`));
    detail.append(ccNode('p', `${observedTime(record.observed_at)} · ${ccValue(record.snapshot_id)}`, 'aw-source'));
    detail.append(ccNode('h3', ccLabel('Candidate-level findings', 'Aday düzeyindeki bulgular')));
    if (record.blockers.includes('NO_READY_CANDIDATE')) detail.append(ccNode('p', ccLabel(
      'No ready trade candidate was reported. The decision and gate findings below also remain binding.',
      'İşleme hazır aday bildirilmedi. Aşağıdaki karar ve kapı bulguları da bağlayıcıdır.')));
    if (record.candidate_count === 0 && record.candidate_diagnostics?.length === 0) {
      detail.append(ccNode('p', ccLabel(
        'Analysis reported zero candidates. There are no candidate-level records for this observation; review the decision and gate findings below.',
        'Analiz sıfır aday bildirdi. Bu gözlemde aday düzeyinde kayıt yok; aşağıdaki karar ve kapı bulgularını inceleyin.')));
    } else if (!record.candidate_diagnostics?.length) detail.append(ccNode('p', ccLabel(
      'Candidate-level reasons were not reported for this observation.', 'Bu gözlem için aday düzeyindeki nedenler bildirilmedi.')));
    for (const candidate of record.candidate_diagnostics || []) {
      detail.append(ccNode('p', `${candidate.setup} · ${candidate.timeframe} · ${candidate.status}`));
      detail.append(ccNode('p', candidate.candidate_id, 'aw-source'));
      const list = ccNode('ul', '', 'cc-blockers');
      for (const code of candidate.blockers) list.append(ccNode('li', commandVirtualCandidateReason(code)));
      detail.append(list);
    }
    const evidence = record.validation_evidence;
    detail.append(ccNode('h3', ccLabel('Loaded OOS evidence scope', 'Yüklenen OOS kanıt kapsamı')));
    detail.append(ccNode('p', evidence ? ccLabel(
      `${evidence.symbol_subject_count} subjects for this coin / ${evidence.loaded_subject_count} loaded. Scope is separate from maturity approval.`,
      `Bu koin için ${evidence.symbol_subject_count} kayıt / yüklenen ${evidence.loaded_subject_count} kayıt. Kapsam, olgunluk onayından ayrıdır.`)
      : ccLabel('Not reported for this observation.', 'Bu gözlem için bildirilmedi.')));
    if (evidence) {
      detail.append(ccNode('p', ccValue(evidence.deployment_path), 'aw-source'));
      for (const code of evidence.load_blockers) detail.append(ccNode('p', code, 'aw-status'));
    }
    const technical = ccNode('details');
    technical.append(ccNode('summary', ccLabel('Decision and gate findings', 'Karar ve kapı bulguları')));
    for (const blocker of record.blockers) technical.append(ccNode('div', commandVirtualCandidateReason(blocker), 'aw-status'));
    detail.append(technical);
    container.append(detail);
  }
  return container;
}
function commandVirtualCandidateReason(code: string): string {
  const labels: Record<string, [string, string]> = {
    ENTRY_TRIGGER_MISSING: ['Entry trigger is absent', 'Giriş tetikleyicisi yok'],
    DIRECTIONAL_STRUCTURE_UNRESOLVED: ['Directional structure is unresolved', 'Yön yapısı netleşmedi'],
    MACRO_STRUCTURE_CONFLICT: ['Macro structure conflicts with the setup', 'Büyük ölçekli yapı kurulumla çelişiyor'],
    SETUP_STRUCTURE_CONFLICT: ['Setup structure is inconsistent', 'Kurulum yapısı tutarsız'],
    MULTI_TIMEFRAME_DIRECTION_CONFLICT: ['Timeframe directions conflict', 'Zaman dilimlerinin yönleri çelişiyor'],
    TRADING_INTELLIGENCE_NO_SELECTED_SCENARIO: ['No scenario was selected', 'Senaryo seçilmedi'],
    REGIME_ROUTE_SPOT_DEFENSIVE_CASH: ['The current regime requires staying in cash', 'Mevcut rejim nakitte kalmayı gerektiriyor'],
    SCENARIO_CONFIRMATION_PENDING: ['Scenario confirmation is pending', 'Senaryo teyidi bekleniyor'],
    COST_FEE_EVIDENCE_UNAVAILABLE: ['Fee evidence is unavailable', 'Komisyon kanıtı mevcut değil'],
    COST_SLIPPAGE_EVIDENCE_UNAVAILABLE: ['Slippage evidence is unavailable', 'Fiyat kayması kanıtı mevcut değil'],
    NET_RISK_REWARD_UNAVAILABLE: ['Net risk-reward could not be established', 'Net risk-getiri oranı belirlenemedi'],
    NO_READY_CANDIDATE: ['No trade candidate passed readiness checks', 'Hazırlık kontrollerini geçen işlem adayı yok'],
    TRADE_CANDIDATE_AND_RISK_PLAN_MISSING: ['A complete candidate and risk plan were not supplied', 'Tam bir aday ve risk planı sağlanmadı'],
    RESOURCE_RAM_HARD_LIMIT: ['Research paused at the approved RAM limit', 'Araştırma onaylı RAM sınırında duraklatıldı'],
    RESOURCE_RAM_SOFT_LIMIT: ['Background validation waits for available RAM', 'Arka plan doğrulaması kullanılabilir RAM bekliyor'],
  };
  if (code.startsWith('REGIME_ROUTE_STRATEGY_BLOCKED:')) return ccLabel(
    'The strategy is excluded by the current regime', 'Strateji mevcut rejimde uygun değil') + ` · ${code}`;
  if (code === 'OOS_RUNTIME_EVIDENCE_UNAVAILABLE:OOS_RUNTIME_SOURCE_MISMATCH') return ccLabel(
    'OOS evidence belongs to a different source version; genuine revalidation is required',
    'OOS kanıtı farklı kaynak sürümüne ait; gerçek yeniden doğrulama gerekiyor') + ` · ${code}`;
  return labels[code] ? `${ccLabel(...labels[code])} · ${code}` : code;
}
interface HealthFinding {
  finding_id?: string;
  severity?: string;
  status?: string;
  evidence?: string;
  facts?: Record<string, unknown>;
}
interface KaizenFinding extends HealthFinding { token: string; action: string | null }
interface KaizenJob {
  state: string; action?: string; finding_present?: boolean; blockers?: string[];
  execution_allowed: false; live_eligibility_status: 'LIVE_ORDER_BLOCKED';
}
interface KaizenActions {
  actions: KaizenFinding[]; targets: Record<string, string[]>; job: KaizenJob;
  execution_allowed: false; live_eligibility_status: 'LIVE_ORDER_BLOCKED';
}
interface DashboardSnapshot {
  schema_version: 'DashboardSnapshot/v1';
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
  simulationScope?: 'all' | 'selected';
};
declare const marketSelections: Record<string, string>;
declare const marketCache: Record<string, { symbols?: string[]; timeframes?: string[] }>;
declare let marketFilter: string;
declare var localData: DashboardSnapshot | null;
declare let lastPollFailed: boolean;
declare function render(): void;
declare function renderLocal(content: HTMLElement): void;
declare function go(page: string): void;
declare function loadMarket(suppressRender?: boolean): Promise<void>;
declare function runMarketRefresh(market?: string, symbol?: string): Promise<void>;
declare function refreshLocal(): Promise<void>;
declare function refreshLearning(): Promise<void>;
declare function sourceInfo(name: string): SourceMeta;
declare const lastLearningAttempt: number;
declare function observedTime(value?: string | null): string;
declare function auditObserverPanel(): HTMLElement;
declare function healthFindingsPanel(title: string[], limit?: number): HTMLElement;
declare function findingCopy(item: HealthFinding): {
  title: string[]; explanation: string[]; action: string[]; evidence: string; severity: string;
};

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
    verifiedPayloads: 'Verified explanation bodies', missingPayloads: 'Unavailable bodies', invalidPayloads: 'Invalid bodies',
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
    verifiedPayloads: 'Doğrulanan açıklama içerikleri', missingPayloads: 'Mevcut olmayan içerikler', invalidPayloads: 'Geçersiz içerikler',
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
function commandShouldLoadMarket(): boolean {
  // The persistent selector needs verified context on every local page.
  return state.mode === 'local';
}
function commandShouldRefreshMarket(): boolean {
  return state.mode === 'local' && ['opportunities', 'virtual-market'].includes(state.page)
    && !commandVirtualAllSymbols()
    && (state.page !== 'opportunities'
      || !commandOpportunityAllSymbols(state.market === 'Spot' ? 'SPOT' : 'USD_M_FUTURES'));
}
const commandOpportunitySymbolSelections: Record<string, string> = {};
function commandVirtualAllSymbols(): boolean {
  return state.page === 'virtual-market' && state.simulationScope !== 'selected';
}
function commandOpportunityAllSymbols(market: string): boolean {
  return state.page === 'opportunities' && commandOpportunitySymbolSelections[market] === 'ALL';
}
function commandOpportunitySymbolMatches(item: { symbol?: string }, market: string): boolean {
  const symbol = commandOpportunitySymbolSelections[market] || marketSelections[market];
  return !symbol || symbol === 'ALL' || item.symbol === symbol;
}
function commandMarketSymbolControl(market: string, symbols: string[], virtual: boolean): HTMLSelectElement {
  const control = ccNode('select', '', 'aw-button');
  control.setAttribute('aria-label', state.language === 'tr' ? 'Sembol' : 'Symbol');
  const selected = virtual ? (commandVirtualAllSymbols() ? 'ALL' : marketSelections[market])
    : commandOpportunitySymbolSelections[market] || marketSelections[market];
  const values = ['ALL', ...symbols.filter(symbol => symbol !== 'ALL')];
  values.forEach(symbol => {
    const option = ccNode('option', symbol || (state.language === 'tr' ? 'Yükleniyor…' : 'Loading…'));
    option.value = symbol; option.selected = symbol === selected; control.append(option);
  });
  control.addEventListener('change', () => {
    if (virtual) state.simulationScope = control.value === 'ALL' ? 'all' : 'selected';
    else commandOpportunitySymbolSelections[market] = control.value === 'ALL' ? 'ALL' : '';
    if (control.value !== 'ALL') {
      marketSelections[market] = control.value; void loadMarket();
    }
    marketFilter = 'All'; render();
  });
  return control;
}
function commandMarketRefreshLabel(market: string): string[] {
  if (commandVirtualAllSymbols()) return ['Refresh virtual market view', 'Sanal piyasa görünümünü yenile'];
  return commandOpportunityAllSymbols(market)
    ? ['Refresh opportunity view', 'Fırsat görünümünü yenile']
    : ['Refresh data and opportunities', 'Veri ve fırsatları yenile'];
}
async function commandRefreshMarketSelection(market: string): Promise<void> {
  if (commandVirtualAllSymbols()) { await refreshLocal(); render(); }
  else if (commandOpportunityAllSymbols(market)) await loadMarket();
  else await runMarketRefresh(market, marketSelections[market]);
}
function commandMarketScopeNote(market: string): string[] {
  if (commandVirtualAllSymbols()) return [
    'Showing canonical simulation observations for all eligible symbols in this market. Wallet totals cover the market.',
    'Bu piyasadaki uygun tüm sembollerin kanonik simülasyon gözlemleri gösteriliyor. Cüzdan toplamları piyasa kapsamındadır.'];
  return commandOpportunityAllSymbols(market)
    ? ['Showing published opportunities for all eligible symbols in this market. Select a symbol for its data quality and history.',
      'Bu piyasadaki uygun tüm sembollerin yayınlanmış fırsatları gösteriliyor. Veri kalitesi ve geçmiş için bir sembol seçin.']
    : ['The selected coin is scanned across every listed timeframe. Price-path performance is not trading profit.',
      'Seçili koin listelenen tüm zaman dilimlerinde taranır. Fiyat hareketi performansı işlem kârı değildir.'];
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
interface AuditRecommendation {
  recommendation?: string | null; method?: string | null; method_result?: string | null;
  observed_at?: string | null; evidence_ref?: string | null;
}
interface AuditMovement {
  cycle_index?: number; system_status?: string | null; observed_at?: string | null;
  new_blockers?: string[]; persistent_blockers?: string[]; resolved_blockers?: string[];
  evidence_ref?: string | null;
}
interface AuditObserver {
  status?: string; loop_id?: string; workflow_pattern?: string;
  movements?: AuditMovement[]; recommendations?: AuditRecommendation[];
}
let commandAuditPage = 0;
function commandAuditTrigger(value: string): string {
  const labels: Record<string, [string, string]> = {
    SCHEDULED_DAILY_QUICK: ['Daily quick audit', 'Günlük hızlı denetim'],
    SCHEDULED_WEEKLY_DEEP: ['Weekly deep audit', 'Haftalık derin denetim'],
    SYSTEM_BLOCKER: ['Reported system blocker', 'Bildirilen sistem engeli'],
    DECISION_AUDIT: ['Decision audit', 'Karar denetimi'],
    PARAMETER_PROMOTION: ['Parameter promotion review', 'Parametre terfi incelemesi'],
    PERFORMANCE_DRIFT: ['Performance drift', 'Performans sapması'],
    SCHEDULED_AUDIT: ['Scheduled audit', 'Zamanlanmış denetim'],
  };
  const label = labels[value]; return label ? ccLabel(...label) : value;
}
function commandAuditAction(value: string): string {
  const labels: Record<string, [string, string]> = {
    appsec: ['Review application security', 'Uygulama güvenliğini incele'],
    vulnerability: ['Review vulnerabilities', 'Güvenlik açıklarını incele'],
    dlp: ['Review data loss prevention', 'Veri kaybı önleme kontrollerini incele'],
    audit: ['Review security audit evidence', 'Güvenlik denetimi kanıtlarını incele'],
    recovery: ['Review recovery controls', 'Kurtarma kontrollerini incele'],
    privacy: ['Review privacy controls', 'Gizlilik kontrollerini incele'],
    access: ['Review access controls', 'Erişim kontrollerini incele'],
    secrets: ['Review credential protection', 'Kimlik bilgisi korumasını incele'],
    'security-daily-quick': ['Run the daily security audit', 'Günlük güvenlik denetimini çalıştır'],
    'security-core-audit': ['Run the core security audit', 'Temel güvenlik denetimini çalıştır'],
    'privacy-boundary': ['Review the privacy boundary', 'Gizlilik sınırını incele'],
    'dge-review': ['Review decision governance', 'Karar yönetişimini incele'],
    'validate-research': ['Validate research evidence', 'Araştırma kanıtlarını doğrula'],
    'lean-governance': ['Review process governance', 'Süreç yönetişimini incele'],
  };
  const key = value.startsWith('check:security:') ? value.slice(15)
    : value.startsWith('run:') ? value.slice(4) : '';
  if (labels[key]) return ccLabel(...labels[key]);
  if (value.startsWith('route:')) return ccLabel('Route for review: ', 'İncelemeye yönlendir: ')
    + commandAuditTrigger(value.slice(6).toUpperCase());
  if (value.startsWith('resolve:')) {
    const code = value.split(':').slice(2).join(':');
    const blockers: Record<string, [string, string]> = {
      RUNTIME_DEGRADED: ['Investigate degraded runtime health', 'Bozulan çalışma sağlığını incele'],
      SELL_EXCEEDS_RECONSTRUCTED_INVENTORY: ['Reconcile sell quantities with inventory evidence', 'Satış miktarlarını envanter kanıtıyla uzlaştır'],
      WALLET_TRADE_HISTORY_QUANTITY_MISMATCH: ['Reconcile wallet and trade history quantities', 'Cüzdan ve işlem geçmişi miktarlarını uzlaştır'],
      TRADE_HISTORY_UNAVAILABLE: ['Restore trade history evidence', 'İşlem geçmişi kanıtını geri yükle'],
    };
    return blockers[code] ? ccLabel(...blockers[code])
      : ccLabel('Investigate reported blocker: ', 'Bildirilen engeli incele: ') + code;
  }
  return ccValue(value);
}
function commandAuditFields(values: [string, string][]): HTMLElement {
  const list = ccNode('dl', '', 'cc-audit-meta');
  for (const [name, value] of values) list.append(ccNode('dt', name), ccNode('dd', value));
  return list;
}
function commandAuditBlockers(label: string, values: string[] | undefined, id: string): HTMLElement {
  const detail = ccNode('details', '', 'cc-audit-blockers'); detail.dataset.detailId = id;
  const codes = Array.isArray(values) ? values.filter(value => typeof value === 'string') : undefined;
  detail.append(ccNode('summary', `${label} · ${codes ? codes.length : ccLabel('Not reported', 'Bildirilmedi')}`));
  if (codes?.length) {
    const list = ccNode('ul'); for (const code of codes) list.append(ccNode('li', code));
    detail.append(list);
  } else detail.append(ccNode('p', codes ? ccLabel('None reported in this cycle.', 'Bu döngüde bildirilmedi.')
    : ccLabel('Source did not report this field.', 'Kaynak bu alanı bildirmedi.')));
  return detail;
}
function commandAuditObserverPanel(observer: AuditObserver): HTMLElement {
  const panel = ccNode('article', '', 'aw-panel cc-audit');
  panel.dataset.panelKey = 'Observed movements and recommendations';
  panel.append(ccNode('h2', ccLabel('Observed movements and recommendations', 'Gözlenen hareketler ve öneriler')));
  const recommendations = Array.isArray(observer.recommendations) ? observer.recommendations.filter(item => item && typeof item === 'object') : [];
  const movements = Array.isArray(observer.movements) ? observer.movements.filter(item => item && typeof item === 'object') : [];
  panel.append(commandAuditFields([
    [ccLabel('Observer method', 'Gözlemci yöntemi'), ccLabel('Auto-Audit Loop + Continuous Assurance', 'Otomatik Denetim Döngüsü + Sürekli Güvence')],
    [ccLabel('Reported status', 'Bildirilen durum'), ccValue(observer.status)],
    [ccLabel('Audit loop', 'Denetim döngüsü'), ccValue(observer.loop_id)],
    [ccLabel('Workflow', 'İş akışı'), ccValue(observer.workflow_pattern)],
  ]));
  panel.append(ccNode('p', ccLabel('Actions below come from the canonical audit record. Routing acceptance requires separate completion evidence.',
    'Aşağıdaki eylemler kanonik denetim kaydından gelir. Yönlendirmeye kabul için tamamlanma kanıtı ayrıca gerekir.'), 'aw-source'));
  const size = 6, pages = Math.max(1, Math.ceil(recommendations.length / size));
  commandAuditPage = Math.max(0, Math.min(commandAuditPage, pages - 1));
  const controls = ccNode('div', '', 'cc-actions');
  const changePage = (delta: number) => { commandAuditPage += delta; render(); };
  const previous = ccNode('button', ccLabel('Previous', 'Önceki'), 'aw-button'); previous.type = 'button';
  previous.dataset.commandKey = 'audit-actions-previous';
  previous.disabled = commandAuditPage === 0; previous.onclick = () => changePage(-1);
  const next = ccNode('button', ccLabel('Next', 'Sonraki'), 'aw-button'); next.type = 'button';
  next.dataset.commandKey = 'audit-actions-next';
  next.disabled = commandAuditPage === pages - 1; next.onclick = () => changePage(1);
  const pageStatus = ccNode('span', `${ccLabel('Recorded actions', 'Kayıtlı eylemler')}: ${ccReportedCount(observer.recommendations)} · ${commandAuditPage + 1} / ${pages}`);
  pageStatus.setAttribute('role', 'status'); pageStatus.setAttribute('aria-live', 'polite');
  controls.append(previous, pageStatus, next);
  panel.append(controls);
  const grid = ccNode('div', '', 'cc-audit-actions');
  for (const item of recommendations.slice(commandAuditPage * size, (commandAuditPage + 1) * size)) {
    const action = ccValue(item.recommendation), method = ccValue(item.method), result = ccValue(item.method_result);
    const card = ccNode('section', '', 'cc-audit-action');
    card.append(ccNode('h3', commandAuditAction(action)));
    const routing = method.startsWith('CONTINUOUS_ASSURANCE:');
    const methodLabel = routing ? ccLabel('Continuous Assurance · ', 'Sürekli Güvence · ')
      + commandAuditTrigger(method.slice(21)) : method === 'AUTO_AUDIT_LOOP'
      ? ccLabel('Automatic audit loop', 'Otomatik denetim döngüsü') : method;
    card.append(commandAuditFields([
      [ccLabel('Method', 'Yöntem'), methodLabel],
      [ccLabel('Observed', 'Gözlem zamanı'), observedTime(item.observed_at)],
      [ccLabel('Method result', 'Yöntem sonucu'), routing && result === 'ACCEPTED'
        ? ccLabel('Routing accepted; completion not reported', 'Yönlendirmeye kabul edildi; tamamlanma bildirilmedi') : result],
    ]));
    const detail = ccNode('details'); detail.dataset.detailId = `audit-action:${action}:${method}:${item.observed_at}`;
    detail.append(ccNode('summary', ccLabel('Action and evidence references', 'Eylem ve kanıt referansları')),
      commandAuditFields([[ccLabel('Action code', 'Eylem kodu'), action],
        [ccLabel('Method code', 'Yöntem kodu'), method], [ccLabel('Result code', 'Sonuç kodu'), result],
        [ccLabel('Evidence', 'Kanıt'), ccValue(item.evidence_ref)]]));
    card.append(detail); grid.append(card);
  }
  if (!recommendations.length) grid.append(ccNode('p', ccLabel('No recorded action is available.', 'Kayıtlı eylem mevcut değil.')));
  panel.append(grid, ccNode('h3', ccLabel('Blocker movements by cycle', 'Döngüye göre engel hareketleri')));
  for (const movement of movements) {
    const id = `audit-cycle:${observer.loop_id}:${movement.cycle_index}:${movement.observed_at}`;
    const detail = ccNode('details', '', 'cc-audit-cycle'); detail.dataset.detailId = id;
    const summary = ccNode('summary', `${ccLabel('Cycle', 'Döngü')} ${movement.cycle_index ?? '—'} · ${ccValue(movement.system_status)} · ${observedTime(movement.observed_at)}`);
    summary.append(ccNode('span', `${ccLabel('New', 'Yeni')}: ${ccReportedCount(movement.new_blockers)} · ${ccLabel('Persistent', 'Kalıcı')}: ${ccReportedCount(movement.persistent_blockers)} · ${ccLabel('Resolved', 'Çözülen')}: ${ccReportedCount(movement.resolved_blockers)}`, 'cc-audit-counts'));
    detail.append(summary);
    detail.append(commandAuditBlockers(ccLabel('New blockers', 'Yeni engeller'), movement.new_blockers, id + ':new'),
      commandAuditBlockers(ccLabel('Persistent blockers', 'Kalıcı engeller'), movement.persistent_blockers, id + ':persistent'),
      commandAuditBlockers(ccLabel('Resolved blockers', 'Çözülen engeller'), movement.resolved_blockers, id + ':resolved'),
      commandAuditFields([[ccLabel('Evidence', 'Kanıt'), ccValue(movement.evidence_ref)]]));
    panel.append(detail);
  }
  if (!movements.length) panel.append(ccNode('p', ccLabel('No cycle movement is reported.', 'Döngü hareketi bildirilmedi.')));
  return panel;
}
function commandOpportunityVisible(row: {measurable_plan?: boolean} | undefined): boolean {
  return row?.measurable_plan === true;
}
interface NewsRadarResult {
  items?: {asset?: string | null; symbol?: string | null; verification_status?: string}[];
  articles?: {title?: string; canonical_uri?: string; published_at?: string; retrieved_at?: string; provider_id?: string}[];
}
function commandNewsSummary(result: NewsRadarResult) {
  const count = Array.isArray(result.items)
    ? String(result.items.filter(item => item.verification_status === 'VERIFIED'
      && Boolean(item.asset?.trim() || item.symbol?.trim())).length) : '—';
  return {
    count,
    note: ccLabel('Only verified findings associated with an asset or symbol are counted.',
      'Yalnızca bir varlık veya sembolle ilişkilendirilmiş doğrulanmış bulgular sayılır.'),
    coverage: ccLabel('Per-symbol coverage is not supplied by this bounded general-news feed.',
      'Bu sınırlı genel haber akışı sembol bazında kapsam bilgisi sağlamıyor.'),
    findings: ccLabel('Reported findings are listed below with their verification status. Fetched articles are not verified coin events.',
      'Bildirilen bulgular doğrulama durumlarıyla aşağıda listelenir. Alınan yazılar doğrulanmış koin olayları değildir.'),
  };
}
function commandNewsArticles(result: NewsRadarResult): HTMLElement {
  const section = ccNode('section', '', 'aw-panel');
  section.append(ccNode('h3', ccLabel('Fetched source articles', 'Kaynaklardan alınan yazılar')));
  section.append(ccNode('p', ccLabel('These public articles have not been classified or independently verified as eligible-coin news.',
    'Bu genel yazılar uygun koin haberi olarak sınıflandırılmadı veya bağımsız doğrulanmadı.'), 'aw-status'));
  const articles = Array.isArray(result.articles) ? result.articles.slice(0, 12) : [];
  if (!articles.length) section.append(ccNode('p', ccLabel('No source article metadata was supplied.',
    'Kaynak yazı bilgisi sağlanmadı.'), 'aw-empty'));
  articles.forEach(article => {
    const entry = ccNode('div', '', 'aw-row');
    const title = ccNode('span', article.title || ccLabel('Untitled article', 'Başlıksız yazı'));
    try {
      const url = new URL(article.canonical_uri || '');
      if (url.protocol === 'https:' && !url.username && !url.password) {
        const link = ccNode('a', title.textContent || '');
        link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
        title.replaceChildren(link);
      }
    } catch { /* Missing or invalid source URLs remain plain text. */ }
    entry.append(title, ccNode('span', `${article.provider_id || '—'} · ${observedTime(article.published_at || article.retrieved_at)}`));
    section.append(entry);
  });
  return section;
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
  let payload: unknown;
  try { payload = await response.json(); } catch { throw new Error('INVALID_DATA'); }
  if (!isDashboardSnapshot(payload)) throw new Error('INVALID_DATA');
  return payload;
}
function isDashboardSnapshot(value: unknown): value is DashboardSnapshot {
  const record = (item: unknown): item is Record<string, unknown> =>
    item !== null && typeof item === 'object' && !Array.isArray(item);
  const strings = (item: unknown): item is string[] =>
    Array.isArray(item) && item.every(entry => typeof entry === 'string');
  const optionalStrings = (item: Record<string, unknown>, keys: string[]) =>
    keys.every(key => item[key] === undefined || typeof item[key] === 'string');
  if (!record(value) || value.schema_version !== 'DashboardSnapshot/v1' ||
      value.execution_allowed !== false || value.live_eligibility_status !== 'LIVE_ORDER_BLOCKED' ||
      typeof value.generated_at !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value.generated_at) ||
      !Number.isFinite(Date.parse(value.generated_at)) ||
      !record(value.sources) || !Array.isArray(value.services) ||
      !Array.isArray(value.health_findings) || !record(value.operational_readiness) ||
      typeof value.operational_readiness.status !== 'string' || !record(value.decision_history)) return false;
  if (!Object.values(value.sources).every(source => record(source) && typeof source.status === 'string' &&
      (source.observed_at === undefined || source.observed_at === null || typeof source.observed_at === 'string') &&
      (source.producer_status === undefined || source.producer_status === null || typeof source.producer_status === 'string') &&
      optionalStrings(source, ['file', 'freshness_status']) &&
      (source.producer_blockers === undefined || strings(source.producer_blockers)))) return false;
  if (value.virtual !== undefined && (!record(value.virtual) ||
      !['market', 'symbol', 'virtual_decision_status', 'last_success_at'].every(key => {
        const entry = (value.virtual as Record<string, unknown>)[key];
        return entry === undefined || entry === null || typeof entry === 'string';
      }) ||
      (value.virtual.risk_approved !== undefined && value.virtual.risk_approved !== null && typeof value.virtual.risk_approved !== 'boolean') ||
      (value.virtual.blockers !== undefined && !strings(value.virtual.blockers)))) return false;
  if (!['finding_count', 'high_priority_finding_count'].every(key => {
    const count = (value.operational_readiness as Record<string, unknown>)[key];
    return count === undefined || (typeof count === 'number' && Number.isInteger(count) && count >= 0);
  })) return false;
  if (!value.services.every(service => record(service) && typeof service.service === 'string' &&
      typeof service.required === 'boolean' && strings(service.blockers))) return false;
  if (!value.health_findings.every(finding => record(finding) &&
      ['finding_id', 'severity', 'status', 'evidence'].every(key => typeof finding[key] === 'string'))) return false;
  const history = value.decision_history;
  return typeof history.status === 'string' && Array.isArray(history.records) &&
    history.records.every(item => record(item) &&
      ['decision_id', 'cycle_id', 'snapshot_id', 'observed_at', 'status', 'source', 'receipt_status',
       'payload_status', 'historical_authenticity', 'execution_surface', 'governance_status'].every(key => typeof item[key] === 'string') &&
      strings(item.blockers) && strings(item.analysis_blockers) && Array.isArray(item.stages) &&
      item.stages.every(stage => record(stage) && typeof stage.name === 'string' && typeof stage.status === 'string' && strings(stage.blockers)) &&
      Array.isArray(item.references) && item.references.every(ref => record(ref) &&
        ['artifact_id', 'artifact_kind', 'cycle_id', 'snapshot_id', 'payload_sha256', 'status'].every(key => typeof ref[key] === 'string') &&
        (ref.payload === undefined || record(ref.payload))) &&
      (item.timeframes === undefined || strings(item.timeframes))) &&
    Array.isArray(history.findings) && history.findings.every(item => record(item) && typeof item.source === 'string' && typeof item.status === 'string');
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
  const observation = commandSummary(localData);
  const current = ccPanel('current');
  current.append(ccNode('p', `${observation.market} · ${observation.symbol} · ${observedTime(observation.observedAt)}`),
    ccNode('p', `${observation.decision} · ${ccText('risk')}: ${observation.risk}`),
    ccNode('p', ccLabel('Latest background observation. The recorded receipt below belongs to its own past cycle.',
      'Son arka plan gözlemi. Aşağıdaki kayıt kendi geçmiş döngüsüne aittir.')));
  if (observation.blockers?.length) {
    const reasons = ccNode('ul', '', 'cc-blockers');
    observation.blockers.forEach(code => reasons.append(ccNode('li', commandVirtualCandidateReason(code))));
    current.append(reasons);
  }
  content.append(current);
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
  const status = ccNode('p', `${ccLabel('Recorded cycle freshness', 'Kayıtlı döngü güncelliği')}: ${item.status} · ${item.action || 'DATA_UNAVAILABLE'} · ${item.symbol || 'DATA_UNAVAILABLE'}`, 'cc-connection');
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
  blockers.forEach(reason => list.append(ccNode('li', commandVirtualCandidateReason(reason))));
  panel.append(list, ccNode('p', ccLabel('Reported stage completion is not approval. Live orders remain blocked.',
    'Bildirilen aşama tamamlanması onay değildir. Canlı emirler kapalıdır.')));
  const stages = ccNode('details'); stages.append(ccNode('summary', ccText('details')));
  item.stages.forEach(stage => stages.append(ccNode('p', `${stage.name}: ${stage.status}`)));
  panel.append(stages);
  panel.append(ccDecisionEvidence(item), ccNode('p', `${item.receipt_status} · ${item.historical_authenticity}`));
  panel.append(ccNode('p', ccLabel('Each reference reports its own payload availability and hash check. Historical authenticity is not verified.',
    'Her referans kendi içerik durumunu ve hash kontrolünü gösterir. Geçmiş kaydın özgünlüğü doğrulanmadı.')));
  content.append(panel, ccLineage(item));
}
function ccDecisionEvidence(item: DecisionRecord): HTMLElement {
  const section = ccNode('section');
  section.append(ccNode('h3', ccLabel('Evidence payload availability', 'Kanıt içeriği erişilebilirliği')));
  const verified = item.references.filter(ref => ref.status === 'PAYLOAD_HASH_MATCH' && ref.payload).length;
  const invalid = item.references.filter(ref => ref.status === 'PAYLOAD_INVALID').length;
  const missing = item.references.length - verified - invalid;
  const metrics = ccNode('dl', '', 'cc-metrics');
  metrics.append(ccMetric('verifiedPayloads', `${verified} / ${item.references.length}`),
    ccMetric('missingPayloads', String(missing)), ccMetric('invalidPayloads', String(invalid)));
  section.append(metrics);
  if (!verified) section.append(ccNode('p', ccLabel(
    'This recorded cycle contains references without explanation bodies. It cannot be repaired by relabeling the receipt.',
    'Bu kayıtlı döngüde açıklama içerikleri olmadan referanslar var. Kayıt yeniden etiketlenerek onarılamaz.')));
  section.append(ccNode('p', ccLabel(
    'Supporting, counter and conflicting evidence classifications were not reported. Payload hash checks do not establish these classifications or trading approval.',
    'Destekleyici, karşı ve çelişen kanıt sınıfları bildirilmedi. İçerik hash kontrolü bu sınıfları veya işlem onayını oluşturmaz.')));
  return section;
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
  if (local && !['overview', 'opportunities', 'research', 'news', 'recommendations', 'kaizen', 'decision', 'evidence', 'system', 'virtual-market', 'binance-wallet'].includes(state.page)) {
    const context = ccNode('div', '', 'cc-context');
    const field = (key: CopyKey, values: string[], selected: string, change: (value: string) => void) => {
      const label = ccNode('label', ccText(key));
      const select = ccNode('select', '', 'aw-button'); select.dataset.commandKey = key;
      values.forEach(value => { const option = ccNode('option', value); option.value = value; select.append(option); });
      select.value = selected; select.addEventListener('change', () => change(select.value));
      label.append(select); context.append(label);
    };
    field('market', ['Spot', 'Futures'], state.market, value => {
      state.market = value; void loadMarket(); render();
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
  if (local && commandFailure && !['overview', 'decision', 'evidence', 'system'].includes(state.page)) {
    root.querySelector('#aw-content')!.prepend(commandConnectionPanel());
  }
  root.querySelectorAll<HTMLTableCellElement>('th').forEach(cell => { cell.scope = 'col'; });
  if (local && commandVirtualAllSymbols()) root.querySelectorAll<HTMLElement>('#aw-content article').forEach(panel => {
    if (['Selected coin data quality', 'Seçili koinin veri kalitesi'].includes(panel.querySelector('h2')?.textContent || '')) panel.remove();
  });
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

let commandKaizenSelection: KaizenFinding | undefined;
let commandKaizenActions: KaizenActions | undefined;
let commandKaizenPending = false;
let commandKaizenError = '';
let commandKaizenAcknowledgement = '';
let commandKaizenMarket = 'SPOT';
let commandKaizenSymbol = '';
function commandKaizenLabel(action: string | null): string {
  if (action === 'REFRESH_CANDLES') return ccLabel('Refresh native candles for one eligible symbol', 'Uygun bir sembolün yerel mum verisini yenile');
  if (action === 'RESTART_MARKET_HISTORY') return ccLabel('Restart only the existing market-history service', 'Yalnızca mevcut market-history servisini yeniden başlat');
  if (action === 'REFRESH_LEARNING') return ccLabel('Refresh the canonical learning summary', 'Kanonik öğrenim özetini yenile');
  return ccLabel('No bounded apply operation is available for this finding.', 'Bu bulgu için sınırlı bir uygulama işlemi mevcut değil.');
}
function commandKaizenResponse(value: unknown): value is KaizenActions {
  const data = value as Partial<KaizenActions> | null;
  return !!data && data.execution_allowed === false && data.live_eligibility_status === 'LIVE_ORDER_BLOCKED'
    && Array.isArray(data.actions) && !!data.targets && typeof data.targets === 'object' && !Array.isArray(data.targets)
    && !!data.job && typeof data.job.state === 'string' && data.job.execution_allowed === false
    && data.job.live_eligibility_status === 'LIVE_ORDER_BLOCKED'
    && data.actions.every(item => !!item && typeof item === 'object' && typeof item.token === 'string' && /^[a-f0-9]{64}$/.test(item.token)
      && (item.action === null || ['REFRESH_CANDLES', 'RESTART_MARKET_HISTORY', 'REFRESH_LEARNING'].includes(item.action)))
    && Object.entries(data.targets).every(([market, symbols]) => ['SPOT', 'USD_M_FUTURES'].includes(market)
      && Array.isArray(symbols) && symbols.every(symbol => typeof symbol === 'string' && /^[A-Z0-9]{2,30}$/.test(symbol)));
}
async function commandLoadKaizen(): Promise<void> {
  const response = await fetch('/api/kaizen/actions', {cache: 'no-store', signal: AbortSignal.timeout(8000)});
  const data: unknown = await response.json();
  if (!response.ok || !commandKaizenResponse(data)) throw new Error('KAIZEN_ACTIONS_UNAVAILABLE');
  commandKaizenActions = data;
}
async function commandChooseKaizen(item: HealthFinding): Promise<void> {
  if (commandKaizenPending) return;
  commandKaizenPending = true; commandKaizenError = ''; commandKaizenAcknowledgement = ''; render();
  try {
    await commandLoadKaizen();
    commandKaizenSelection = commandKaizenActions?.actions.find(value => commandFindingKey(value) === commandFindingKey(item));
    if (!commandKaizenSelection?.action) throw new Error('KAIZEN_FINDING_UNAVAILABLE');
    const targets = commandKaizenActions!.targets;
    commandKaizenMarket = targets.SPOT?.length ? 'SPOT' : 'USD_M_FUTURES';
    commandKaizenSymbol = targets[commandKaizenMarket]?.[0] || '';
  } catch { commandKaizenSelection = undefined; commandKaizenError = 'KAIZEN_FINDING_UNAVAILABLE'; }
  finally { commandKaizenPending = false; render(); }
}
async function commandApplyKaizen(): Promise<void> {
  const selected = commandKaizenSelection;
  if (!selected?.action || commandKaizenPending) return;
  commandKaizenPending = true; commandKaizenError = ''; render();
  try {
    const request: Record<string, unknown> = {token: selected.token, confirmed: true};
    if (selected.action === 'REFRESH_CANDLES') Object.assign(request, {market: commandKaizenMarket, symbol: commandKaizenSymbol});
    const response = await fetch('/api/kaizen/apply', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(request), cache: 'no-store', signal: AbortSignal.timeout(8000)});
    if (!response.ok) throw new Error('KAIZEN_APPLY_REJECTED');
    const acknowledgement = await response.json() as KaizenJob;
    if (typeof acknowledgement.state !== 'string' || acknowledgement.execution_allowed !== false || acknowledgement.live_eligibility_status !== 'LIVE_ORDER_BLOCKED') {
      throw new Error('KAIZEN_ACKNOWLEDGEMENT_INVALID');
    }
    if (['BUSY', 'COOLDOWN'].includes(acknowledgement.state)) {
      commandKaizenAcknowledgement = acknowledgement.state; await commandLoadKaizen(); return;
    }
    // Acknowledgement is not proof of resolution; display the canonical job and fresh finding.
    for (let attempt = 0; attempt < 60; attempt++) {
      await commandLoadKaizen();
      render();
      if (!['RUNNING', 'PENDING'].includes(commandKaizenActions!.job.state)) break;
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    await refreshLocal();
  } catch { commandKaizenError = 'KAIZEN_APPLY_REJECTED_OR_RESULT_UNAVAILABLE'; }
  finally { commandKaizenPending = false; render(); }
}
function commandKaizenPanel(): HTMLElement {
  const panel = ccNode('article', '', 'aw-panel');
  panel.dataset.panelKey = 'Current Kaizen backlog';
  panel.append(ccNode('h2', ccLabel('Current Kaizen backlog', 'Güncel Kaizen kuyruğu')));
  const wrap = ccNode('div', '', 'aw-tablewrap'); const table = ccNode('table');
  const head = ccNode('thead'); const headings = ccNode('tr');
  [['Priority', 'Öncelik'], ['Finding', 'Bulgu'], ['Why it matters', 'Neden önemli'],
    ['Safe next action', 'Güvenli sonraki adım'], ['Evidence', 'Kanıt'], ['Apply', 'Uygula']]
    .forEach(([en, tr]) => headings.append(ccNode('th', ccLabel(en, tr))));
  head.append(headings); const body = ccNode('tbody');
  const findings = localData?.health_findings || [];
  findings.slice(0, 20).forEach(item => {
    const copy = findingCopy(item); const row = ccNode('tr');
    [copy.severity, copy.title[state.language === 'tr' ? 1 : 0], copy.explanation[state.language === 'tr' ? 1 : 0],
      copy.action[state.language === 'tr' ? 1 : 0], copy.evidence].forEach(value => row.append(ccNode('td', value)));
    const cell = ccNode('td'); const button = ccNode('button', ccLabel('Apply', 'Uygula'), 'aw-button'); button.type = 'button';
    const supported = ['MARKET_HISTORY_INCOMPLETE', 'LEARNING_SUMMARY_EMPTY'].includes(item.finding_id || '')
      || (item.finding_id === 'SERVICE_NOT_READY' && item.facts?.service === 'market-history');
    button.disabled = !supported || commandKaizenPending;
    button.setAttribute('aria-label', `${ccLabel('Apply', 'Uygula')}: ${row.cells[1].textContent}`);
    button.dataset.commandKey = `kaizen-apply-${commandFindingKey(item)}`;
    if (!supported) button.title = commandKaizenLabel(null);
    button.addEventListener('click', () => { void commandChooseKaizen(item); }); cell.append(button); row.append(cell); body.append(row);
  });
  table.append(head, body); wrap.append(table); panel.append(wrap);
  if (!findings.length) panel.append(ccNode('p', ccLabel('No current finding is reported.', 'Güncel bulgu bildirilmedi.')));
  if (commandKaizenError) panel.append(ccNode('p', ccLabel(
    'The action or its result is unavailable. Refresh the summary and select the current finding again.',
    'İşlem veya sonucu kullanılamıyor. Özeti yenileyip güncel bulguyu yeniden seçin.'), 'cc-blockers'));
  if (commandKaizenAcknowledgement) panel.append(ccNode('p', ccLabel(
    'No new action started. Another action is active or the one-minute cooldown has not ended.',
    'Yeni işlem başlatılmadı. Başka bir işlem sürüyor veya bir dakikalık bekleme süresi bitmedi.'), 'cc-blockers'));
  const selected = commandKaizenSelection;
  if (selected) {
    const detail = ccNode('section'); detail.setAttribute('aria-label', ccLabel('Apply action preview', 'Uygulama önizlemesi'));
    detail.append(ccNode('h3', commandKaizenLabel(selected.action)), ccNode('p', ccLabel(
      'This applies the displayed local operation. Data, risk, validation, and live-order vetoes remain active. A completed operation may leave the finding unresolved.',
      'Gösterilen yerel işlem uygulanır. Veri, risk, doğrulama ve canlı emir engelleri korunur. İşlem tamamlansa bile bulgu devam edebilir.')));
    if (selected.action === 'REFRESH_CANDLES') {
      const marketLabel = ccNode('label', ccLabel('Target market', 'Hedef piyasa')); const market = ccNode('select', '', 'aw-button');
      for (const [value, label] of [['SPOT', 'Spot'], ['USD_M_FUTURES', 'Futures']]) {
        const option = ccNode('option', label); option.value = value; option.selected = value === commandKaizenMarket; market.append(option);
      }
      market.addEventListener('change', () => { commandKaizenMarket = market.value; commandKaizenSymbol = commandKaizenActions?.targets[market.value]?.[0] || ''; render(); });
      const symbolLabel = ccNode('label', ccLabel('Target symbol', 'Hedef sembol')); const symbol = ccNode('select', '', 'aw-button');
      (commandKaizenActions?.targets[commandKaizenMarket] || []).forEach(value => {
        const option = ccNode('option', value); option.value = value; option.selected = value === commandKaizenSymbol; symbol.append(option);
      });
      symbol.addEventListener('change', () => { commandKaizenSymbol = symbol.value; });
      market.disabled = commandKaizenPending; symbol.disabled = commandKaizenPending;
      marketLabel.append(market); symbolLabel.append(symbol); detail.append(marketLabel, symbolLabel);
    }
    const apply = ccNode('button', commandKaizenPending ? ccLabel('Applying…', 'Uygulanıyor…') : ccLabel('Confirm and apply', 'Onayla ve uygula'), 'aw-button');
    apply.type = 'button'; apply.disabled = commandKaizenPending || (selected.action === 'REFRESH_CANDLES' && !commandKaizenSymbol);
    apply.addEventListener('click', () => { void commandApplyKaizen(); });
    const cancel = ccNode('button', ccLabel('Close', 'Kapat'), 'aw-button'); cancel.type = 'button';
    cancel.addEventListener('click', () => { commandKaizenSelection = undefined; render(); }); detail.append(apply, cancel);
    panel.append(detail);
  }
  const job = commandKaizenActions?.job;
  if (job && job.state !== 'NOT_RUN') {
    const status = ccNode('p', `${commandKaizenLabel(job.action || null)} · ${job.state}`); status.setAttribute('role', 'status');
    if (job.finding_present !== undefined) status.append(ccNode('span', job.finding_present
      ? ccLabel(' · Finding remains; resolution is not verified.', ' · Bulgu devam ediyor; çözüm doğrulanmadı.')
      : ccLabel(' · Original finding is absent from the latest snapshot.', ' · Son görüntüde önceki bulgu bulunmuyor.')));
    if (job.blockers?.length) status.append(ccNode('span', ` · ${job.blockers.join(' · ')}`)); panel.append(status);
  }
  return panel;
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
