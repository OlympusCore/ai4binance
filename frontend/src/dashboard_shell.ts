/** Dashboard interaction source. Illustrative data stays in the labelled preview mode. */
interface DashboardState {
  page: string;
  market: string;
  virtualMarket: string;
  radar: string;
  hideBalances: boolean;
  language: string;
  density: string;
  radius: number;
  mode: string;
}
declare function prepareCommandRender(): void;
declare function captureCommandView(): string | undefined;
declare function enhanceCommandShell(focusKey?: string): void;
declare function renderCommandCenter(content: HTMLElement): boolean;
declare function renderLocal(content: HTMLElement): void;
declare function observedTime(value?: string): string;
declare function pollLocal(): Promise<void>;
declare function renderDashboardIcons(root: ParentNode): void;
declare const localData: {generated_at?: string} | null;

(() => {
  function requiredElement(parent: ParentNode, selector: string): HTMLElement {
    const node = parent.querySelector<HTMLElement>(selector);
    if (!node) throw new Error('DASHBOARD_ELEMENT_UNAVAILABLE: ' + selector);
    return node;
  }
  const root = requiredElement(document, '#a4-workspace');
  const state: DashboardState = {page:'overview',market:'Spot',virtualMarket:'Spot',radar:'Web Radar',hideBalances:true,language:'en',density:'comfortable',radius:12,mode:'local'};
  const t = (en: string, tr: string) => state.language==='tr'?tr:en;
  const text = (value: unknown): string => Array.isArray(value)?t(value[0],value[1]):String(value);
  const el = <K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, value?: unknown): HTMLElementTagNameMap[K] => {const n=document.createElement(tag);if(className)n.className=className;if(value!==undefined)n.textContent=text(value);return n;};
  const append = <T extends Node>(parent: T,...children: Node[]): T => {children.forEach(child=>parent.appendChild(child));return parent;};
  const badge = (value: unknown,kind='neutral') => el('span','aw-tag '+kind,value);
  const button = (label: unknown,handler: () => void,className='aw-button') => {const b=el('button',className,label);b.type='button';b.addEventListener('click',handler);return b;};
  const money = (value: number | string | undefined) => new Intl.NumberFormat(state.language==='tr'?'tr-TR':'en-US',{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value));
  const sampleTime = '13.09.2026 09:30 UTC+3';
  const pages: [string, string, string | string[], string[]][] = [
    ['overview','layout-dashboard',['Overview','Genel Bakış'],['What needs your attention today?','Bugün neye odaklanmalısın?']],
    ['opportunities','radar',['Opportunities','Fırsatlar'],['Separate Spot and Futures setups · Illustrative levels','Spot ve Futures ayrı · Seviyeler örnek senaryodur']],
    ['research','flask-conical',['Research','Araştırma'],['Technology, strategies, indicators, and system development','Teknoloji, strateji, indikatör ve sistem gelişimi']],
    ['news','newspaper',['News','Haberler'],['All eligible coins · Source and event tracking','Uygun tüm koinler · Kaynak ve olay takibi']],
    ['recommendations','lightbulb',['Recommendations','Öneriler'],['Evidence-led system development','Kanıta dayalı sistem geliştirme önerileri']],
    ['virtual-market','chart-no-axes-combined','VirtualMarket',['Separate wallets, performance, and complete event history','Ayrı cüzdanlar, performans ve tüm hareket kayıtları']],
    ['binance-wallet','wallet','BinanceWallet',['Latest verified account snapshot','En son doğrulanmış hesap durumu']],
    ['kaizen','refresh-cw','Kaizen',['System-wide ideas, experiments, and measured outcomes','Tüm sistem için fikirler, deneyler ve ölçülen sonuçlar']]
  ];
  const opportunities = [
    {id:'DEMO-S01',market:'Spot',coin:'BTCUSDT',tf:'1h',side:'BUY',entry:60000,sl:58800,tp:63600,reason:['Trend continuation','Trend devamı'],expiry:['Next 1h close','Sonraki 1h kapanışı']},
    {id:'DEMO-S02',market:'Spot',coin:'ETHUSDT',tf:'4h',side:'SELL',entry:2400,sl:2320,tp:2600,exit:2500,reason:['Existing position exit','Mevcut pozisyondan çıkış'],expiry:['Inventory verification','Envanter doğrulaması']},
    {id:'DEMO-F01',market:'Futures',coin:'BTCUSDT',tf:'4h',side:'LONG',leverage:3,entry:60000,sl:59400,tp:61800,reason:['Breakout retest','Kırılımın yeniden testi'],expiry:['Next 4h close','Sonraki 4h kapanışı']},
    {id:'DEMO-F02',market:'Futures',coin:'ETHUSDT',tf:'1h',side:'SHORT',leverage:2,entry:2500,sl:2550,tp:2350,reason:['Trend rejection','Trend reddi'],expiry:['Next 1h close','Sonraki 1h kapanışı']}
  ];
  const rr = (row: { sl: number | null; tp: number; entry: number }) => row.sl===null?null:Math.abs(row.tp-row.entry)/Math.abs(row.entry-row.sl);
  const radarItems = [
    {source:'Web Radar',type:['Technology','Teknoloji'],title:['Time-series model comparison','Zaman serisi model karşılaştırması'],measure:['OOS error and inference latency','OOS hata ve çıkarım gecikmesi']},
    {source:'Web Radar',type:['Strategy','Strateji'],title:['Regime-aware strategy selection','Rejime duyarlı strateji seçimi'],measure:['Net OOS expectancy by regime','Rejim bazında net OOS beklentisi']},
    {source:'Web Radar',type:['Indicator','İndikatör'],title:['Adaptive volatility indicators','Uyarlamalı volatilite indikatörleri'],measure:['False signals and signal delay','Yanlış sinyal ve sinyal gecikmesi']},
    {source:'GitHub Radar',type:['System','Sistem'],title:['Data integrity tooling','Veri bütünlüğü araçları'],measure:['Missing bars and validation time','Eksik mum ve doğrulama süresi']},
    {source:'GitHub Radar',type:['Algorithm','Algoritma'],title:['Incremental feature calculation','Artımlı özellik hesaplama'],measure:['Output equivalence, CPU time, memory','Çıktı eşdeğerliği, CPU süresi, bellek']},
    {source:'GitHub Radar',type:['Pattern','Pattern'],title:['Pattern detection benchmarks','Pattern tespit karşılaştırmaları'],measure:['Precision and recall on holdout data','Ayrılmış veride kesinlik ve duyarlılık']}
  ];
  const assets = [{symbol:'BTC',type:'coin'},{symbol:'ETH',type:'coin'},{symbol:'SOL',type:'coin'},{symbol:'ADA',type:'coin'},{symbol:'DOT',type:'coin'},{symbol:'USDT',type:'stablecoin'},{symbol:'WBTC',type:'wrapped'},{symbol:'BTCUP',type:'leveraged'}];
  const newsItems = [{coin:'BTC',title:['Protocol development','Protokol geliştirmesi'],category:['Development','Geliştirme']},{coin:'ETH',title:['Network upgrade tracking','Ağ güncellemesi takibi'],category:['Network','Ağ']},{coin:'SOL',title:['Ecosystem integration','Ekosistem entegrasyonu'],category:['Ecosystem','Ekosistem']}];
  const ideas = [
    {type:['Algorithm','Algoritma'],title:['Incremental feature pipeline','Artımlı özellik hesaplama'],metric:['Calculation time (ms)','Hesaplama süresi (ms)'],proof:['Identical output on replay','Replay üzerinde aynı çıktı']},
    {type:['Strategy','Strateji'],title:['Regime-based strategy comparison','Rejim bazında strateji karşılaştırması'],metric:['Net OOS expectancy','Net OOS beklentisi'],proof:['Untouched holdout results','Dokunulmamış OOS sonuçları']},
    {type:['Model','Model'],title:['Forecast probability calibration','Tahmin olasılığı kalibrasyonu'],metric:['Brier score','Brier skoru'],proof:['Calibration on unseen data','Görülmemiş veride kalibrasyon']},
    {type:['Indicator','İndikatör'],title:['Adaptive volatility normalization','Uyarlamalı volatilite normalizasyonu'],metric:['False signal rate','Yanlış sinyal oranı'],proof:['Comparison with current baseline','Mevcut temel yöntemle karşılaştırma']},
    {type:['Pattern','Pattern'],title:['Pattern validity by regime','Rejim bazında pattern geçerliliği'],metric:['Precision / recall','Kesinlik / duyarlılık'],proof:['Labeled evaluation dataset','Etiketli değerlendirme verisi']},
    {type:['System','Sistem'],title:['Source freshness checks','Kaynak güncelliği kontrolleri'],metric:['Stale data detection delay','Eski veriyi algılama gecikmesi'],proof:['Stale and missing source scenarios','Eski ve eksik kaynak senaryoları']}
  ];
  const kaizenItems = [
    {area:['Data','Veri'],title:['Detect archive gaps earlier','Arşiv boşluklarını erken tespit et'],metric:['Gap detection time','Boşluk tespit süresi'],stage:'idea'},
    {area:['Research','Araştırma'],title:['Reuse reproducible experiment inputs','Tekrarlanabilir deney girdilerini yeniden kullan'],metric:['Time to reproduce a result','Sonucu yeniden üretme süresi'],stage:'experiment'},
    {area:['Risk','Risk'],title:['Make veto causes easier to trace','Veto nedenlerinin izini kolaylaştır'],metric:['Time to find veto evidence','Veto kanıtını bulma süresi'],stage:'idea'},
    {area:['Operations','Operasyon'],title:['Group repeated source errors','Tekrarlanan kaynak hatalarını grupla'],metric:['Duplicate alerts per incident','Olay başına yinelenen uyarı'],stage:'idea'},
    {area:['Interface','Arayüz'],title:['Reach evidence in one step','Kanıta tek adımda ulaş'],metric:['Clicks to evidence','Kanıta ulaşma tıklama sayısı'],stage:'idea'},
    {area:['Accounting','Muhasebe'],title:['Compare wallet and event balances','Cüzdan ve hareket bakiyelerini karşılaştır'],metric:['Unreconciled amount (USDT)','Mutabakat farkı (USDT)'],stage:'idea'}
  ];
  const spotEvents: [string, string, string, string[], number][] = [
    ['09:00:00','INIT','—',['Initial virtual balance','Başlangıç sanal bakiyesi'],10000],
    ['09:05:00','ORDER','BTCUSDT',['BUY 0.02 BTC @ 60,000','BUY 0,02 BTC @ 60.000'],0],
    ['09:05:01','FILL','BTCUSDT',['Buy fill · 0.02 BTC','Alış gerçekleşti · 0,02 BTC'],-1200],
    ['09:05:01','FEE','BTCUSDT',['Trading fee','İşlem komisyonu'],-1.2],
    ['09:10:00','RISK_VETO','SOLUSDT',['Order rejected · missing evidence','Emir reddedildi · kanıt eksik'],0],
    ['09:12:00','ORDER','BTCUSDT',['Limit order · 0.01 BTC','Limit emir · 0,01 BTC'],0],
    ['09:13:00','CANCEL','BTCUSDT',['Limit order canceled','Limit emir iptal edildi'],0],
    ['09:20:00','ORDER','BTCUSDT',['SELL 0.01 BTC @ 61,000','SELL 0,01 BTC @ 61.000'],0],
    ['09:20:01','FILL','BTCUSDT',['Sell fill · 0.01 BTC','Satış gerçekleşti · 0,01 BTC'],610],
    ['09:20:01','FEE','BTCUSDT',['Trading fee','İşlem komisyonu'],-.61]
  ];
  const futuresEvents: [string, string, string, string[], number][] = [
    ['09:00:00','INIT','—',['Initial virtual balance','Başlangıç sanal bakiyesi'],10000],
    ['09:04:00','ORDER','ETHUSDT',['SHORT 0.1 ETH @ 2,500 · 2x','SHORT 0,1 ETH @ 2.500 · 2x'],0],
    ['09:04:01','FILL','ETHUSDT',['Opened · margin reserved: 125 USDT','Açıldı · ayrılan teminat: 125 USDT'],0],
    ['09:04:01','FEE','ETHUSDT',['Entry fee','Giriş komisyonu'],-.25],
    ['09:08:00','FUNDING','ETHUSDT',['Funding payment','Fonlama ödemesi'],-.10],
    ['09:15:00','AMEND','ETHUSDT',['SL amended · 2,550 → 2,500','SL değişti · 2.550 → 2.500'],0],
    ['09:25:00','EXIT','ETHUSDT',['TP fill @ 2,400 · margin released','TP gerçekleşti @ 2.400 · teminat serbest'],10],
    ['09:25:00','FEE','ETHUSDT',['Exit fee','Çıkış komisyonu'],-.24]
  ];
  const walletSnapshots: Record<string, { cash: number; equity: number }> = {Spot:{cash:9408.19,equity:10018.19},Futures:{cash:10009.41,equity:10009.41}};
  function go(page: string){state.page=page;render();}
  function kpis(items: [unknown, unknown, unknown][]){const grid=el('div','aw-kpis');items.forEach(([label,value,note])=>append(grid,append(el('div','aw-kpi'),el('div','aw-kpi-label',label),el('div','aw-kpi-value',value),el('div','aw-kpi-note',note))));return grid;}
  function panel(title: unknown,tag?: HTMLElement){const p=el('article','aw-panel');p.dataset.panelKey=String(Array.isArray(title)?title[0]:title);const head=append(el('div','aw-panelhead'),el('h2','',title));if(tag)head.appendChild(tag);p.appendChild(head);return p;}
  function row(label: unknown,value: unknown,note?: unknown){const left=el('div','',label);if(note)left.appendChild(el('small','',note));return append(el('div','aw-row'),left,value instanceof Node?value:el('span','',value ?? 'DATA_UNAVAILABLE'));}
  function detail(fields: [unknown, unknown][],label=['Evidence & details','Kanıt ve ayrıntılar']){const d=el('details');append(d,el('summary','',label));const grid=el('div','aw-detailgrid');fields.forEach(([name,value])=>append(grid,append(el('div'),el('span','',name),el('div','',value))));d.appendChild(grid);return d;}
  function table(headers: unknown[],rows: unknown[][]){const wrap=el('div','aw-tablewrap');const tab=el('table');tab.dataset.tableKey=JSON.stringify(headers.map(h=>Array.isArray(h)?h[0]:h));const head=el('thead');const hr=el('tr');headers.forEach(h=>hr.appendChild(el('th','',h)));head.appendChild(hr);const body=el('tbody');rows.forEach(values=>{const tr=el('tr');values.forEach(v=>tr.appendChild(el('td','',v)));body.appendChild(tr);});append(tab,head,body);wrap.appendChild(tab);return wrap;}
  function segment(prop: 'market' | 'virtualMarket' | 'radar',options: string[]){const group=el('div','aw-segment');group.setAttribute('role','group');group.setAttribute('aria-label',prop);options.forEach(value=>{const b=button(value,()=>{state[prop]=value;render();});b.setAttribute('aria-pressed',String(state[prop]===value));b.dataset.choice=prop+':'+value;group.appendChild(b);});return group;}
  function sampleNote(){return el('div','aw-status',t('Illustrative scenario · ','Örnek senaryo · ')+sampleTime);}
  function overview(content: HTMLElement){
    append(content,kpis([
      [['Research setups','Araştırma adayları'],String(opportunities.length),['Sample: Spot 2 · Futures 2','Örnek: Spot 2 · Futures 2']],
      [['Verified live sources','Doğrulanmış canlı kaynak'],'—',['No connections configured','Kaynak bağlantısı yok']],
      [['Improvement experiments','İyileştirme deneyleri'],String(kaizenItems.filter(i=>i.stage==='experiment').length),['Sample · Benefits not measured','Örnek · Fayda henüz ölçülmedi']]
    ]));
    const cols=el('div','aw-columns');const focus=panel(['Your next steps','Sıradaki adımlar']);
    [['opportunities',['Review Spot / Futures levels','Spot / Futures seviyelerini incele'],['Coin · TF · SL/E/TP · RR','Koin · TF · SL/E/TP · RR']],['research',['Review radar findings','Radar bulgularını incele'],['Web Radar + GitHub Radar','Web Radar + GitHub Radar']],['kaizen',['Measure one improvement','Bir iyileştirmeyi ölç'],['Baseline → experiment → result','Başlangıç → deney → sonuç']]].forEach(([page,label,note])=>focus.appendChild(row(label,button(['Open','Aç'],()=>go(String(page)),'aw-textbutton'),note)));
    const health=panel(['Evidence & freshness','Kanıt ve güncellik']);[['Technical quality','Teknik kalite'],['OOS maturity','OOS olgunluğu'],['Binance account snapshot','Binance hesap durumu']].forEach(label=>health.appendChild(row(label,badge(['Unverified','Doğrulanmadı'],'warn'))));health.appendChild(button(['Inspect evidence','Kanıtı incele'],()=>go('evidence'),'aw-textbutton'));append(cols,focus,health);content.appendChild(cols);
    const summary=panel(['Workspace at a glance','Çalışma alanına bakış']);summary.classList.add('aw-section');summary.appendChild(table([['Area','Alan'],['Scope','Kapsam'],['Status','Durum']],[[t('Opportunities','Fırsatlar'),'Spot BUY/SELL · Futures LONG/SHORT',t('Sample levels','Örnek seviyeler')],['VirtualMarket','VirtualSpotWallet + VirtualFuturesWallet',t('Reconciled sample ledger','Mutabık örnek hareketler')],['BinanceWallet',t('Latest balances and positions','Son bakiye ve pozisyonlar'),t('Disconnected','Bağlı değil')]]));content.appendChild(summary);
  }
  function opportunityPage(content: HTMLElement){
    append(content,append(el('div','aw-toolbar'),segment('market',['Spot','Futures']),badge(['Sample levels · Not live signals','Örnek seviyeler · Canlı sinyal değil'],'warn')));
    const list=opportunities.filter(o=>o.market===state.market);const ratios=list.filter(o=>o.side!=='SELL').map(rr).filter(v=>v!==null);const mean=ratios.reduce((a,b)=>a+b,0)/ratios.length;
    append(content,kpis([[['Watchlist setups','İzlenen aday'],String(list.length),t('Sample · '+state.market,'Örnek · '+state.market)],[['Mean gross RR','Ortalama brüt RR'],mean.toFixed(1)+'R',['Defined entry setups only · Fees excluded','Girişi tanımlı adaylar · Maliyet hariç']],[['Execution-eligible setups','İşleme uygun aday'],'—',['Risk / OOS evidence unavailable','Risk / OOS kanıtı bağlı değil']]]));
    const grid=el('div','aw-tradegrid');list.forEach(o=>{const card=el('article','aw-trade');const heading=append(el('div','aw-panelhead'),el('h2','',o.coin),badge(o.tf));card.appendChild(heading);const direction=el('span','aw-direction'+(['SELL','SHORT'].includes(o.side)?' down':''),o.side);const sub=append(el('div','aw-toolbar'),direction,el('span','aw-caption',o.leverage?t('Leverage: ','Kaldıraç: ')+o.leverage+'x '+t('(sample)','(örnek)'):text(o.reason)));card.appendChild(sub);
      if(o.side==='SELL')card.appendChild(el('div','aw-caption',['Original position plan · Sample exit: '+money(o.exit)+' USDT','Orijinal pozisyon planı · Örnek çıkış: '+money(o.exit)+' USDT']));
      const levels=el('div','aw-levels');[['SL',o.sl],['E',o.entry],['TP',o.tp]].forEach(([label,value])=>append(levels,append(el('div'),el('span','',label+' · USDT'),el('b','',value===null?'—':money(value)))));card.appendChild(levels);
      append(card,row('RR',rr(o)===null?'—':rr(o)?.toFixed(1)+'R',o.side==='SELL'?['Original long plan RR · Inventory exit','Orijinal alış planının RR değeri · Envanter çıkışı']:['Gross price reward / risk','Brüt fiyat ödülü / riski']),badge(['Validation pending','Doğrulama bekleniyor'],'warn'));
      append(card,detail([[['Rationale','Gerekçe'],o.reason],[['Valid until','Geçerlilik'],o.expiry],[['Source','Kaynak'],['Synthetic UI fixture','Sentetik arayüz örneği']],[['Snapshot','Veri zamanı'],sampleTime],[['Missing evidence','Eksik kanıt'],['OOS, costs, risk authorization','OOS, maliyet, risk yetkilendirmesi']],[['Identifier','Kimlik'],o.id]]));grid.appendChild(card);
    });content.appendChild(grid);append(content,el('div','aw-status',['SL: stop loss · E: entry · TP: take profit · RR: gross reward/risk','SL: zarar durdur · E: giriş · TP: kâr al · RR: brüt ödül/risk']),sampleNote());
  }
  function researchPage(content: HTMLElement){
    append(content,kpis([[['Research topics','Araştırma başlığı'],String(radarItems.length),['Sample · Technology to system development','Örnek · Teknolojiden sistem gelişimine']],[['Verified sources','Doğrulanmış kaynak'],'0 / '+radarItems.length,['Sample records have no source attached','Örnek kayıtlara kaynak bağlanmadı']],[['Reproduced findings','Tekrarlanmış bulgu'],'0 / '+radarItems.length,['No experiment evidence attached','Deney kanıtı bağlanmadı']]]));
    append(content,append(el('div','aw-toolbar'),segment('radar',['Web Radar','GitHub Radar']),badge(['Source connection pending','Kaynak bağlantısı bekleniyor'],'warn')));
    const list=panel(state.radar,['GitHub Radar'].includes(state.radar)?badge(['Revision + license','Revizyon + lisans']):badge(['Source + publication date','Kaynak + yayın tarihi']));
    radarItems.filter(i=>i.source===state.radar).forEach(i=>{const item=el('div','aw-row');const left=append(el('div'),append(el('div','aw-itemtitle'),el('h3','',i.title),badge(i.type)),el('small','',t('Success metric: ','Başarı ölçütü: ')+text(i.measure)));append(item,left,badge(['To review','İncelenecek'],'warn'));list.appendChild(item);list.appendChild(detail([[['Source URL','Kaynak URL'],'—'],[state.radar==='GitHub Radar'?['Pinned revision','Sabitlenmiş revizyon']:['Publication date','Yayın tarihi'],'—'],[state.radar==='GitHub Radar'?['License / security review','Lisans / güvenlik incelemesi']:['Independent source check','Bağımsız kaynak kontrolü'],['Pending','Bekliyor']],[['Next step','Sonraki adım'],['Verify source and design a bounded comparison','Kaynağı doğrula ve sınırlı karşılaştırma tasarla']]]));});content.appendChild(list);
  }
  function newsPage(content: HTMLElement){
    const eligible=assets.filter(a=>a.type==='coin');const covered=new Set(newsItems.filter(n=>eligible.some(a=>a.symbol===n.coin)).map(n=>n.coin));
    append(content,kpis([[['Universe coverage','Evren kapsamı'],covered.size+' / '+eligible.length,['Sample · Coins with a news record / eligible coins','Örnek · Haber kaydı olan / uygun koin']],[['Verified news sources','Doğrulanmış haber kaynağı'],'0 / '+newsItems.length,['Sample headlines · Sources not connected','Örnek başlıklar · Kaynaklar bağlı değil']],[['Last successful scan','Son başarılı tarama'],'—',['No live news scan has run','Canlı haber taraması yapılmadı']]]));
    const feed=panel(['Eligible coin news','Uygun koin haberleri'],badge(['Sample headlines','Örnek başlıklar'],'warn'));
    const filters=el('div','aw-filterline');[['Stablecoins excluded','Stablecoin hariç'],['Wrapped excluded','Wrapped hariç'],['Leveraged tokens excluded','Kaldıraçlı token hariç']].forEach(v=>filters.appendChild(badge(v)));feed.appendChild(filters);
    newsItems.filter(n=>eligible.some(a=>a.symbol===n.coin)).forEach(n=>{feed.appendChild(row(n.title,badge(n.coin),t('Illustrative headline · ','Örnek başlık · ')+text(n.category)));feed.appendChild(detail([[['Primary source','Birincil kaynak'],'—'],[['Published / event time','Yayın / olay zamanı'],'—'],[['Verification','Doğrulama'],['Unverified sample','Doğrulanmamış örnek']],[['Affected coin','İlgili koin'],n.coin]]));});append(feed,el('div','aw-status',t('Sample universe only; full eligible universe coverage is not connected.','Yalnızca örnek evren; uygun tüm koinlerin canlı kapsamı bağlı değil.')));content.appendChild(feed);
  }
  function recommendationsPage(content: HTMLElement){
    append(content,kpis([[['Development proposals','Geliştirme önerisi'],String(ideas.length),['Sample · Six capability areas','Örnek · Altı yetenek alanı']],[['Evidence-backed proposals','Kanıtı tamamlanan öneri'],'0 / '+ideas.length,['Experimental results pending','Deney sonuçları bekleniyor']],[['Measured improvement','Ölçülen iyileşme'],'—',['No before / after comparison yet','Önce / sonra karşılaştırması yok']]]));
    const grid=el('div','aw-columns');ideas.forEach(i=>{const p=panel(i.type,badge(['Proposal','Öneri']));append(p,el('h3','',i.title),el('div','aw-status',t('Measure: ','Ölçüt: ')+text(i.metric)),detail([[['Expected benefit','Beklenen fayda'],['Hypothesis; not measured','Hipotez; henüz ölçülmedi']],[['Required evidence','Gerekli kanıt'],i.proof],[['Baseline / result','Başlangıç / sonuç'],'— / —'],[['Stage','Aşama'],['Research proposal','Araştırma önerisi']]],['Evaluation plan','Değerlendirme planı']));grid.appendChild(p);});content.appendChild(grid);
  }
  function virtualPage(content: HTMLElement){
    append(content,append(el('div','aw-toolbar'),segment('virtualMarket',['Spot','Futures']),badge(['Independent virtual wallets','Bağımsız sanal cüzdanlar'])));
    const spot=state.virtualMarket==='Spot';const events=spot?spotEvents:futuresEvents;const cash=events.reduce((s,e)=>s+e[4],0);const positionValue=spot ? .01*61000 : 0;const equity=cash+positionValue;const fees=-events.filter(e=>e[1]==='FEE').reduce((s,e)=>s+e[4],0);const funding=spot?0:-.1;const snapshot=walletSnapshots[state.virtualMarket];
    append(content,kpis([[['Virtual equity · USDT','Sanal toplam değer · USDT'],money(equity),spot?'VirtualSpotWallet':'VirtualFuturesWallet'],[['Net change · USDT','Net değişim · USDT'],(equity>=10000?'+':'')+money(equity-10000),['Sample session · After fees and funding','Örnek oturum · Komisyon ve fonlama sonrası']],[['Open positions','Açık pozisyon'],spot?'1':'0',['Sample snapshot · '+sampleTime,'Örnek durum · '+sampleTime]]]));
    const cols=el('div','aw-columns');const wallet=panel(spot?'VirtualSpotWallet':'VirtualFuturesWallet');append(wallet,row(['Cash balance · USDT','Nakit bakiye · USDT'],money(cash)),row(spot?['Asset value · USDT','Varlık değeri · USDT']:['Used margin · USDT','Kullanılan teminat · USDT'],money(positionValue)),row(['Available · USDT','Kullanılabilir · USDT'],money(cash)),row(['Reconciliation difference · USDT','Mutabakat farkı · USDT'],money(Math.abs(snapshot.cash-cash)+Math.abs(snapshot.equity-equity)),['Wallet snapshot versus event ledger','Cüzdan görüntüsü ile hareket defteri farkı']));
    const performance=panel(['Session performance','Oturum performansı']);append(performance,row(['Realized P&L · gross USDT','Gerçekleşen K/Z · brüt USDT'],money(10)),row(['Unrealized P&L · USDT','Açık K/Z · USDT'],money(spot?10:0)),row(['Fees · USDT','Komisyon · USDT'],money(fees)),row(['Funding · USDT','Fonlama · USDT'],money(funding)),row(['Maximum drawdown','Azami düşüş'],'—',['Equity time series required','Toplam değer zaman serisi gerekli']));append(cols,wallet,performance);content.appendChild(cols);
    const holdings=panel(['Positions','Pozisyonlar']);holdings.classList.add('aw-section');holdings.appendChild(table([['Coin','Koin'],['Quantity','Miktar'],['Average entry','Ortalama giriş'],['Sample mark','Örnek değerleme'],['Value · USDT','Değer · USDT']],spot?[['BTC',state.language==='tr'?'0,01':'0.01',money(60000),money(61000),money(610)]]:[['—','—','—','—','—']]));content.appendChild(holdings);
    const journal=panel(['All movements · event log','Tüm hareketler · olay kaydı'],badge(events.length+' '+t('records','kayıt')));let balance=0;const journalRows=events.map((event,index)=>{balance+=event[4];return [(spot?'S':'F')+String(index+1).padStart(3,'0'),event[0],event[1],event[2],text(event[3]),money(event[4]),money(balance)];});journal.appendChild(table([['ID','Kimlik'],['Time','Saat'],['Event','Olay'],['Coin','Koin'],['Movement','Hareket'],['Cash Δ','Nakit Δ'],['Cash balance','Nakit bakiye']],journalRows));append(journal,detail([[['Session','Oturum'],'DEMO-VM-20260913'],[['Wallet','Cüzdan'],spot?'VirtualSpotWallet':'VirtualFuturesWallet'],[['Record IDs','Kayıt kimlikleri'],(spot?'S':'F')+'001–'+(spot?'S':'F')+String(events.length).padStart(3,'0')],[['Coverage','Kapsam'],['All events in this sample session · USDT','Bu örnek oturumdaki tüm olaylar · USDT']]],['Audit context','Denetim bağlamı']));content.appendChild(journal);
  }
  function binancePage(content: HTMLElement){
    append(content,append(el('div','aw-toolbar'),badge(['Disconnected · Read only','Bağlantı yok · Salt okunur'],'warn'),button(state.hideBalances?['Show balances','Tutarları göster']:['Hide balances','Tutarları gizle'],()=>{state.hideBalances=!state.hideBalances;render();})));
    const value=state.hideBalances?'••••':'—';append(content,kpis([[['Total account value · USDT','Toplam hesap değeri · USDT'],value,['Verified valuation required','Doğrulanmış değerleme gerekli']],[['Available funds · USDT','Kullanılabilir tutar · USDT'],value,['Spot and Futures shown separately','Spot ve Futures ayrı gösterilir']],[['Last successful sync','Son başarılı eşitleme'],'—',['Freshness unknown · No current claim','Güncellik bilinmiyor · Güncel durum doğrulanmadı']]]));
    const p=panel(['Account summary','Hesap özeti']);p.appendChild(table([['Account','Hesap'],['Balance','Bakiye'],['Locked / margin','Kilitli / teminat'],['Open P&L','Açık K/Z']],[['Spot',value,value,'—'],['USD-M Futures',value,value,value],['COIN-M Futures',value,value,value]]));append(p,el('div','aw-empty',['No verified account snapshot','Doğrulanmış hesap görüntüsü yok']),detail([[['Snapshot time','Veri zamanı'],'—'],[['Source','Kaynak'],['Binance account integration not connected','Binance hesap bağlantısı kurulmadı']],[['Valuation time','Değerleme zamanı'],'—'],[['Completeness','Eksiksizlik'],['Not verified','Doğrulanmadı']]]));content.appendChild(p);
    const assetsPanel=panel(['Assets & allocation','Varlıklar ve dağılım']);assetsPanel.appendChild(table([['Asset','Varlık'],['Amount','Miktar'],['Value · USDT','Değer · USDT'],['Share','Pay']],[['—',value,value,'—']]));content.appendChild(assetsPanel);
  }
  function kaizenPage(content: HTMLElement){
    append(content,kpis([[['Open improvement ideas','Açık iyileştirme fikri'],String(kaizenItems.length),['Sample · Data, risk, research, operations, UI, accounting','Örnek · Veri, risk, araştırma, operasyon, arayüz, muhasebe']],[['Active experiments','Aktif deney'],String(kaizenItems.filter(i=>i.stage==='experiment').length),['Sample · Bounded change','Örnek · Sınırlı değişiklik']],[['Measured benefit','Ölçülen fayda'],'—',['Baseline and result required','Başlangıç ve sonuç ölçümü gerekli']]]));
    const list=panel(['System improvement queue','Sistem iyileştirme kuyruğu']);kaizenItems.forEach(i=>{append(list,row(i.title,badge(i.stage==='experiment'?['Experiment','Deney']:['Idea','Fikir'],i.stage==='experiment'?'warn':'neutral'),text(i.area)+' · '+text(i.metric)),detail([[['Hypothesis','Hipotez'],i.title],[['Measure','Ölçüt'],i.metric],[['Baseline / result','Başlangıç / sonuç'],'— / —'],[['Decision','Karar'],['Await measurement','Ölçüm bekleniyor']],[['Next step','Sonraki adım'],['Measure baseline, run a bounded experiment','Başlangıcı ölç, sınırlı deney yap']],[['Rollback condition','Geri alma koşulu'],['Regression against baseline or invariant violation','Başlangıca göre gerileme veya değişmez kural ihlali']]],['Improvement record','İyileştirme kaydı']));});content.appendChild(list);
  }
  function evidencePage(content: HTMLElement){const p=panel(['Evidence provenance','Kanıtın kaynağı'],badge('NOT_VERIFIED','warn'));[['Quality gate','Kalite kapısı'],['OOS validation','OOS doğrulaması'],['Auto-Audit','Auto-Audit'],['DGE','DGE']].forEach(v=>p.appendChild(row(v,badge(['Not connected','Bağlı değil'],'warn'))));p.appendChild(detail([[['Run ID','Çalışma kimliği'],'—'],[['Source revision','Kaynak revizyonu'],'—'],[['Generated at','Üretim zamanı'],'—'],[['Data provenance','Veri kökeni'],['Synthetic interface fixtures','Sentetik arayüz örnekleri']]]));content.appendChild(p);content.appendChild(button(['Back to overview','Genel Bakış’a dön'],()=>go('overview')));}
  // @dashboard-adapters
  function render(){
    prepareCommandRender();
    const commandFocus=captureCommandView();
    const active=document.activeElement;
    const focusKey=active instanceof HTMLElement&&root.contains(active)?{page:active.dataset.page,choice:active.dataset.choice}:{};
    root.lang=state.language;root.dataset.density=state.density;root.style.setProperty('--aw-radius',state.radius+'px');
    requiredElement(root, '#aw-demo').textContent=t('Design preview · Sample data','Tasarım taslağı · Örnek veriler');requiredElement(root, '#aw-eyebrow').textContent=t('PERSONAL WORKSPACE','KİŞİSEL ÇALIŞMA ALANI');requiredElement(root, '#aw-safety').textContent=t('Live orders disabled · Manual confirmation','Canlı emirler kapalı · Manuel onay');requiredElement(root, '#aw-footnote').textContent=t('Local preview · No live data connections','Yerel önizleme · Canlı veri bağlantısı yok');
    const current=pages.find(p=>p[0]===state.page);requiredElement(root, '#aw-title').textContent=current?text(current[2]):t('Evidence','Kanıtlar');requiredElement(root, '#aw-subtitle').textContent=current?text(current[3]):t('Source, time, and verification','Kaynak, zaman ve doğrulama');
    const nav=requiredElement(root, '#aw-nav');nav.replaceChildren();pages.forEach(([id,icon,label])=>{const b=button('',()=>go(id),'aw-nav');b.dataset.page=id;b.setAttribute('aria-pressed',String(state.page===id));const i=el('i');i.dataset.lucide=icon;i.setAttribute('aria-hidden','true');append(b,i,el('span','',label));nav.appendChild(b);});nav.appendChild(el('div','aw-sidefoot',['Local workspace · Research only','Yerel çalışma alanı · Yalnızca araştırma']));
    const content=requiredElement(root, '#aw-content');content.replaceChildren();const pageRenderers: Record<string, (content: HTMLElement) => void> = {overview,opportunities:opportunityPage,research:researchPage,news:newsPage,recommendations:recommendationsPage,'virtual-market':virtualPage,'binance-wallet':binancePage,kaizen:kaizenPage,evidence:evidencePage};
    if(state.mode==='local'){if(!renderCommandCenter(content))renderLocal(content);}else{(pageRenderers[state.page] ?? overview)(content);}
    requiredElement(root, '#aw-status').textContent=text(current?current[2]:['Evidence','Kanıtlar']);renderDashboardIcons(root);
    const focusTarget=focusKey.page?root.querySelector<HTMLElement>('[data-page="'+focusKey.page+'"]'):focusKey.choice?root.querySelector<HTMLElement>('[data-choice="'+focusKey.choice+'"]'):null;
    if(focusTarget)focusTarget.focus({preventScroll:true});
    enhanceCommandShell(commandFocus);
    requiredElement(root, '#aw-mode').textContent=state.mode==='local'?t('Design example','Tasarım örneği'):t('Local data','Yerel veriler');
    if(state.mode==='local'){
      requiredElement(root, '#aw-demo').textContent=t('Local data · Read only','Yerel veriler · Salt okunur');
      requiredElement(root, '#aw-footnote').textContent=t('Refresh: 30 seconds · ','Yenileme: 30 saniye · ')+observedTime(localData?.generated_at);
    }
  }
  const modeButton = document.createElement('button');
  modeButton.type='button'; modeButton.id='aw-mode'; modeButton.className='aw-button';
  requiredElement(root, '.aw-zone').after(modeButton);
  modeButton.addEventListener('click',()=>{state.mode=state.mode==='local'?'sample':'local';render();});
  render();
  void pollLocal();

})();
