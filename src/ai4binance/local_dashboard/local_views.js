  let localData = null;
const marketSelections = {SPOT:'',USD_M_FUTURES:''};
  const marketCache = {};
  const marketLoading = new Set();
  const marketAttempts = {};
  let marketFilter = 'All';
  let marketVisiblePage = '';
  const selectedMarket = () => (state.page==='virtual-market'?state.virtualMarket:state.market)==='Spot'?'SPOT':'USD_M_FUTURES';
  const marketKey = market => market+'|'+marketSelections[market];
  const monitorLabel = value => ({CURRENT:t('Verified','Doğrulandı'),NOT_SCANNED:t('Not scanned','Taranmadı'),STALE:t('Stale','Eski'),INVALID:t('Invalid','Geçersiz'),UNAVAILABLE:t('Missing','Eksik'),DATA_BLOCKED:t('Data blocked','Veri engeli'),CONFIRMATION_PENDING:t('Awaiting confirmation','Teyit bekliyor'),FUTURES_RESEARCH_RADAR:t('Research candidate','Araştırma adayı'),WATCHLIST:t('Watchlist','İzleme'),PENDING_HORIZON:t('Awaiting 3 closed bars','3 kapanmış mum bekleniyor'),NOT_EVALUABLE:t('Not measurable','Ölçülemiyor'),EVALUATED:t('Measured','Ölçüldü'),BULLISH:t('Bullish','Yukarı'),BEARISH:t('Bearish','Aşağı'),BULLISH_CAUTION:t('Bullish · Caution','Yukarı · Temkinli'),BEARISH_CAUTION:t('Bearish · Caution','Aşağı · Temkinli'),WATCH_ONLY:t('Watch only','Yön teyidi yok'),NEUTRAL:t('Neutral','Nötr'),TARGET_FIRST:t('Target first','Önce hedef'),INVALIDATED_FIRST:t('Stop first','Önce stop'),FAVORABLE:t('Favorable','Lehte'),ADVERSE:t('Adverse','Aleyhte'),MIXED:t('Mixed','Karma'),UNRESOLVED:t('Unresolved','Belirsiz')})[value] || value || '—';
  const level = value => value===null||value===undefined||value===''||!Number.isFinite(Number(value))?'—':Number(value).toLocaleString(state.language==='tr'?'tr-TR':'en-US',{maximumFractionDigits:8});
  const completeOpportunityPlan = row => {
    const direction=String(row?.direction||'').toUpperCase(),names=['entry','stop_loss','tp1','tp2','tp3','target_risk_reward'];
    const market=String(row?.market||'').toUpperCase(),side=String(row?.side||'').toUpperCase(),quantity=Number(row?.quantity),leverage=row?.leverage;
    const expectedSide=market==='SPOT'?(direction.startsWith('BULLISH')?'BUY':'SELL'):market==='USD_M_FUTURES'?(direction.startsWith('BULLISH')?'LONG':'SHORT'):'';
    if(!['BULLISH','BEARISH','BULLISH_CAUTION','BEARISH_CAUTION'].includes(direction)||side!==expectedSide||!Number.isFinite(quantity)||quantity<=0||!names.every(name=>Number.isFinite(Number(row?.[name]))&&Number(row[name])>0))return false;
    if(market==='USD_M_FUTURES'&&(!Number.isInteger(leverage)||leverage<1||leverage>125))return false;
    const [entry,stop,tp1,tp2,tp3]=names.slice(0,5).map(name=>Number(row[name]));
    return direction.startsWith('BULLISH')?stop<entry&&entry<tp1&&tp1<tp2&&tp2<tp3:stop>entry&&entry>tp1&&tp1>tp2&&tp2>tp3;
  };
  const signedPercent = value => value===null||value===undefined||!Number.isFinite(Number(value))?'—':(Number(value)>0?'+':'')+Number(value).toLocaleString(state.language==='tr'?'tr-TR':'en-US',{minimumFractionDigits:2,maximumFractionDigits:2})+'%';
  async function loadMarket(){
    if(!['opportunities','virtual-market'].includes(state.page)||state.mode!=='local')return;
    const market=selectedMarket(),key=marketKey(market);if(marketLoading.has(key))return;marketLoading.add(key);
    try{
      const response=await fetch('/api/markets?market='+encodeURIComponent(market)+'&symbol='+encodeURIComponent(marketSelections[market]),{cache:'no-store',signal:AbortSignal.timeout(12000)});
      if(!response.ok)throw new Error('MARKET_VIEW_UNAVAILABLE');
      const data=await response.json();if(data.execution_allowed!==false||data.live_eligibility_status!=='LIVE_ORDER_BLOCKED')throw new Error('MARKET_AUTHORITY_INVALID');
      if(!marketSelections[market])marketSelections[market]=data.symbol||'';
      marketCache[market+'|'+(data.symbol||'')]=data;
      if(data.symbol && data.stale && !['RUNNING','PENDING'].includes(data.refresh?.state) && Date.now()-(marketAttempts[market+'|'+data.symbol]||0)>300000)await runMarketRefresh(market,data.symbol);
    }catch{marketCache[key]={error:true,symbol:marketSelections[market],timeframes:market==='SPOT'?['5m','15m','1h','4h','1d']:['5m','15m','1h']};}
    finally{marketLoading.delete(key);render();}
  }
  async function runMarketRefresh(market=selectedMarket(),symbol=marketSelections[market]){
    if(!symbol)return;
    const key=market+'|'+symbol;marketAttempts[key]=Date.now();
    const data=marketCache[key]||{};data.refresh={state:'RUNNING'};marketCache[key]=data;render();
    try{
      const response=await fetch('/api/markets/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({market,symbol}),signal:AbortSignal.timeout(12000)});
      if(!response.ok)throw new Error('MARKET_REFRESH_FAILED');
      data.refresh=await response.json();
    }catch{data.refresh={state:'FAILED'};}
    render();
  }
  function marketMonitor(content,virtual=false){
    const market=selectedMarket(),key=marketKey(market),data=marketCache[key];
    const switcher=segment(virtual?'virtualMarket':'market',['Spot','Futures']);
    const selected=data||{timeframes:market==='SPOT'?['5m','15m','1h','4h','1d']:['5m','15m','1h']};
    const job=selected.refresh||{},running=job.state==='RUNNING',pending=job.state==='PENDING';
    const coin=el('select','aw-button');coin.setAttribute('aria-label',t('Coin','Koin'));
    for(const symbol of selected.symbols||[selected.symbol||'']){const option=el('option','',symbol||t('Loading coins…','Koinler yükleniyor…'));option.value=symbol;option.selected=symbol===marketSelections[market];coin.appendChild(option);}
    coin.addEventListener('change',()=>{marketSelections[market]=coin.value;marketFilter='All';loadMarket();render();});
    const action=button(running||pending?['Refreshing…','Yenileniyor…']:['Refresh data and opportunities','Veri ve fırsatları yenile'],()=>runMarketRefresh());
    action.disabled=running||pending;
    action.disabled=running||!marketSelections[market];
    append(content,append(el('div','aw-toolbar'),switcher,coin,action));
    const message=selected.error?['Data could not be read. Retry refresh.','Veriler okunamadı. Yenilemeyi tekrar deneyin.']:job.state==='DATA_BLOCKED'?['Market data is unavailable or invalid; this is not a no-opportunity result.','Piyasa verisi kullanılamıyor veya geçersiz; bu fırsat yok sonucu değildir.']:job.state==='FAILED'?['Refresh failed; previous evidence retains its original date.','Yenileme başarısız; önceki kanıtın tarihi korunuyor.']:job.state==='BUSY'?['Another coin is refreshing. Try again when it completes.','Başka bir koin yenileniyor. Tamamlanınca tekrar deneyin.']:pending?['The canonical market-history collector is preparing verified candles.','Kanonik market-history toplayıcısı doğrulanmış mumları hazırlıyor.']:running?['Validating canonical local candles and updating research observations…','Kanonik yerel mumlar doğrulanıyor ve araştırma kayıtları güncelleniyor…']:['The selected coin is scanned across every listed timeframe. Price-path performance is not trading profit.','Seçili koin listelenen tüm zaman dilimlerinde taranır. Fiyat hareketi performansı işlem kârı değildir.'];
    const note=el('div','aw-status',message);note.setAttribute('role','status');content.appendChild(note);
    const viewKey=state.page+'|'+market;
    if(marketVisiblePage!==viewKey || (!data&&!marketLoading.has(key))){marketVisiblePage=viewKey;queueMicrotask(loadMarket);}
    if(virtual)virtualWalletPanels(content);
    const tfs=selected.timeframes||[],quality=selected.quality||[],universe=selected.universe||{},universeQuality=universe.quality||[];
    const q=panel(['All eligible coin data quality','Uygun tüm koinlerin veri kalitesi'],badge(universe.generated_at?['Checked','Kontrol edildi']:['Unavailable','Veri yok'],universe.generated_at?'neutral':'warn'));
    const coverageCount=value=>value===null||value===undefined?'—':String(value);
    q.appendChild(table([['TF','TF'],['Current / universe','Güncel / evren'],['Stale','Eski'],['Invalid','Geçersiz'],['Unavailable','Kullanılamıyor'],['Refresh / queue','Yenileme / kuyruk']],tfs.map(tf=>{const row=universeQuality.find(r=>r.timeframe===tf)||{};return [tf,coverageCount(row.current_count)+' / '+coverageCount(row.universe_count),coverageCount(row.stale_count),coverageCount(row.invalid_count),coverageCount(row.unavailable_count),coverageCount(row.refresh_required_count)+' / '+coverageCount(row.pending_count)];})));
    q.appendChild(row(['Last all-market check','Son tüm-piyasa kontrolü'],observedTime(universe.generated_at)));content.appendChild(q);
    const selectedQuality=panel(['Selected coin data quality','Seçili koinin veri kalitesi'],badge(selected.stale?['Scan stale','Tarama eski']:selected.generated_at?['Checked','Kontrol edildi']:['Not scanned','Taranmadı'],selected.stale?'warn':'neutral'));
    selectedQuality.appendChild(table([['TF','TF'],['Status','Durum'],['Closed / required bars','Kapalı / gereken mum'],['Total stored bars','Kayıtlı toplam mum'],['Last closed candle','Son mum kapanışı'],['Gaps','Boşluk'],['Checksum','Sağlama'],['Reason','Neden']],tfs.map(tf=>{const row=quality.find(r=>r.timeframe===tf)||{};return [tf,monitorLabel(row.status||'NOT_SCANNED'),String(row.candle_count??'—')+' / '+String(row.required_candles??'—'),String(row.total_candles??'—'),observedTime(row.last_close),String(row.gap_count??'—'),row.checksum_verified?t('Verified','Doğrulandı'):'—',(row.blockers||[]).join(' · ')||'—'];})));
    selectedQuality.appendChild(row(['Last selected-coin analysis','Son seçili-koin analizi'],observedTime(selected.generated_at)));content.appendChild(selectedQuality);
    if(virtual)return;
    const generation=universe.generation_health||{},generationPanel=panel(['Opportunity generation health','Fırsat üretim sağlığı'],badge(String(generation.rejected_attempt_count??0)+' '+t('rejected attempts','reddedilen deneme'),Number(generation.rejected_attempt_count||0)?'warn':'neutral'));
    generationPanel.appendChild(kpis([[['Evaluated attempts','Değerlendirilen deneme'],String(generation.evaluated_attempt_count??0),['All bounded generation attempts','Tüm sınırlı üretim denemeleri']],[['Published opportunities','Yayınlanan fırsat'],String(generation.published_opportunity_count??0),['Complete measurable contracts only','Yalnızca tam ve ölçülebilir sözleşmeler']],[['Rejected attempts','Reddedilen deneme'],String(generation.rejected_attempt_count??0),['Excluded from opportunity performance','Fırsat performansına dahil değildir']]]));
    const reasonRows=Object.entries(generation.rejected_by_reason||{}).sort((a,b)=>Number(b[1])-Number(a[1])||String(a[0]).localeCompare(String(b[0]))).slice(0,12);
    generationPanel.appendChild(table([['Rejection reason','Red nedeni'],['Count','Sayı']],reasonRows.map(([reason,count])=>[monitorLabel(reason),String(count)])));
    const recentRejections=(generation.recent_rejections||[]).slice().reverse().slice(0,20);
    generationPanel.appendChild(table([['Observed','Gözlem'],['Coin / TF','Koin / TF'],['Outcome / stage','Sonuç / aşama'],['Missing fields','Eksik alanlar'],['Reason','Neden']],recentRejections.map(r=>[observedTime(r.observed_at),String(r.symbol||'—')+' / '+String(r.timeframe||'—'),monitorLabel(r.outcome)+' / '+monitorLabel(r.failed_stage),(r.missing_fields||[]).join(' · ')||'—',(r.reason_codes||[]).join(' · ')||'—'])));
    if(!recentRejections.length)generationPanel.appendChild(el('div','aw-empty',['No rejected opportunity-generation attempts are recorded.','Kayıtlı reddedilmiş fırsat üretim denemesi yok.']));
    generationPanel.appendChild(el('div','aw-status',['Rejected attempts are diagnostic evidence, not opportunities, and never enter opportunity performance.','Reddedilen denemeler teşhis kanıtıdır; fırsat değildir ve fırsat performansına girmez.']));content.appendChild(generationPanel);
    const filters=el('div','aw-toolbar');['All',...tfs].forEach(tf=>{const b=button(tf==='All'?['All timeframes','Tüm zaman dilimleri']:tf,()=>{marketFilter=tf;render();});b.setAttribute('aria-pressed',String(marketFilter===tf));filters.appendChild(b);});content.appendChild(filters);
    const visible=tfs.includes(marketFilter)?[marketFilter]:tfs;
    for(const tf of visible){
      const p=panel(tf+' '+t('potential all-coin opportunities','potansiyel tüm-koin fırsatları'));
      const candidates=(universe.opportunities||[]).filter(r=>r.timeframe===tf&&completeOpportunityPlan(r));
      const headers=[['Observed at','Gözlem zamanı'],['Coin symbol','Koin simge'],['Side','Taraf'],['State','Durum'],['Quantity','Miktar'],['Reference','Referans'],['Entry','Giriş'],['Stop','Stop'],['TP1 / TP2 / TP3','TP1 / TP2 / TP3'],['R/R','R/R']];
      if(market==='USD_M_FUTURES')headers.push(['Leverage','Kaldıraç']);
      p.appendChild(table(headers,candidates.map(r=>{const values=[observedTime(r.observed_at),r.symbol,r.side,monitorLabel(r.status),level(r.quantity),level(r.reference_price),level(r.entry),level(r.stop_loss),[r.tp1,r.tp2,r.tp3].map(level).join(' / '),level(r.target_risk_reward)];if(market==='USD_M_FUTURES')values.push(level(r.leverage));return values;})));
      const coverage=universe.opportunity_coverage||{};
      p.appendChild(el('div','aw-status',t('Monitor coverage: ','İzleme kapsamı: ')+String(coverage.monitored_symbol_count??0)+' / '+String(coverage.universe_count??0)+t(' coins. Unmonitored coins remain explicitly pending, not absent opportunities.',' koin. İzlenmeyen koinler fırsat yok sayılmaz; açıkça beklemede kalır.')));
      if(coverage.status&&coverage.status!=='CANDIDATES_AVAILABLE')p.appendChild(el('div','aw-status',t('Canonical opportunity state: ','Kanonik fırsat durumu: ')+coverage.status));
      if(!candidates.length)p.appendChild(el('div','aw-empty',[market==='USD_M_FUTURES'?'No measurable opportunity with Coin / Long-Short / Leverage / Quantity / Entry / Stop / TP1 / TP2 / TP3 / R/R is available.':'No measurable opportunity with Coin / Buy-Sell / Quantity / Entry / Stop / TP1 / TP2 / TP3 / R/R is available.',market==='USD_M_FUTURES'?'Koin / Long-Short / Kaldıraç / Miktar / Entry / Stop / TP1 / TP2 / TP3 / R/R alanları tam ve ölçülebilir bir fırsat yok.':'Koin / Buy-Sell / Miktar / Entry / Stop / TP1 / TP2 / TP3 / R/R alanları tam ve ölçülebilir bir fırsat yok.']));
      candidates.forEach(r=>p.appendChild(detail([[['Setup','Kurulum'],r.setup_name||'—'],[['Observed','Gözlem'],observedTime(r.observed_at)],[['Evidence / blockers','Kanıt / engeller'],(r.blockers||[]).join(' · ')||'—'],[['Record ID','Kayıt kimliği'],r.opportunity_id||'—']],['Observation details','Gözlem ayrıntıları'])));
      content.appendChild(p);
    }
    const history=(selected.history||[]).filter(r=>visible.includes(r.timeframe)&&completeOpportunityPlan(r));
    for(const potential of [false,true]){
      const p=panel(potential?['Potential opportunity records and performance','Potansiyel fırsat kayıtları ve performansı']:['Past observations and performance','Geçmiş fırsatlar ve performansı']);
      const rows=history.filter(r=>(r.category==='POTENTIAL')===potential).slice().reverse();
      p.appendChild(table([['Recorded','Kayıt zamanı'],['Coin / TF','Koin / TF'],['Direction','Yön'],['Evaluation','Ölçüm'],['Outcome','Sonuç'],['MFE %','Lehte azami %'],['MAE %','Aleyhte azami %'],['Potential R','Potansiyel R']],rows.slice(0,100).map(r=>{const o=r.outcome||{},entry=Number(r.entry);const pct=value=>value===null||value===undefined||!(entry>0)?'—':level(100*Number(value)/entry);return [observedTime(r.observed_at),r.symbol+' / '+r.timeframe,monitorLabel(r.direction),monitorLabel(o.status),o.status==='EVALUATED'?monitorLabel(o.final_outcome_class):(o.outcome_reason_codes||[]).join(' · ')||'—',pct(o.maximum_favorable_excursion),pct(o.maximum_adverse_excursion),level(o.potential_r_multiple)];})));
      if(!rows.length)p.appendChild(el('div','aw-empty',['No recorded observations yet. New observations are saved automatically on refresh.','Henüz kayıt yok. Yeni gözlemler yenilemede otomatik kaydedilir.']));
      append(p,el('div','aw-status',['Horizon: 3 closed bars after observation. No fees, funding, slippage or executed P&L. Historical results require a recorded timestamp and price.','Ölçüm: gözlemden sonraki 3 kapanmış mum. Komisyon, fonlama, kayma ve gerçekleşmiş K/Z dahil değildir. Eski sonuçlar için kayıtlı zaman ve fiyat kanıtı gerekir.']),el('div','aw-status',t('Records shown: ','Gösterilen kayıt: ')+Math.min(rows.length,100)+' / '+rows.length));content.appendChild(p);
    }
  }
  function virtualWalletPanels(content){
    const market=selectedMarket(),selected=marketCache[marketKey(market)]||{},payload=selected.wallet||{};
    const name=market==='SPOT'?'Virtual_Spot_Wallet':'Virtual_Futures_Wallet';
    const wallet=(payload.wallets||{})[name];
    if(!wallet){content.appendChild(missingPanel(name,['Verified virtual wallet journal is unavailable.','Doğrulanmış sanal cüzdan jurnali kullanılamıyor.']));return;}
    const changes=wallet.period_changes||{},daily=changes.daily||{},weekly=changes.weekly||{},monthly=changes.monthly||{};
    const coverage=value=>value==='SINCE_INCEPTION'?t('Since wallet inception','Cüzdan başlangıcından beri'):t('Full period','Tam dönem');
    const net=Number(wallet.equity_usdt)-Number(wallet.initial_equity_usdt);
    const p=panel(name,badge(payload.status==='CURRENT'?['Verified journal','Doğrulanmış jurnal']:['Wallet unavailable','Cüzdan kullanılamıyor'],payload.status==='CURRENT'?'':'warn'));
    p.appendChild(kpis([[['Current value · USDT','Mevcut değer · USDT'],level(wallet.equity_usdt),['Independent virtual capital','Bağımsız sanal sermaye']],[['Available · USDT','Kullanılabilir · USDT'],level(wallet.cash_usdt),['Available virtual cash','Kullanılabilir sanal nakit']],[['Net virtual P&L · USDT','Net sanal K/Z · USDT'],level(net),['Current equity − initial equity','Mevcut değer − başlangıç değeri']],[['Daily change','Günlük değişim'],signedPercent(daily.percent_change),coverage(daily.coverage)],[['Weekly change','Haftalık değişim'],signedPercent(weekly.percent_change),coverage(weekly.coverage)],[['Monthly change','Aylık değişim'],signedPercent(monthly.percent_change),coverage(monthly.coverage)]]));
    p.appendChild(row(['Wallet inception','Başlangıç zamanı'],observedTime(wallet.inception_at)));
    p.appendChild(detail([[['Initial equity · USDT','Başlangıç değeri · USDT'],level(wallet.initial_equity_usdt)],[['Realized P&L · USDT','Gerçekleşen K/Z · USDT'],level(wallet.realized_pnl_usdt)],[['Unrealized P&L · USDT','Açık K/Z · USDT'],level(wallet.unrealized_pnl_usdt)],[['Fees · USDT','Komisyon · USDT'],level(wallet.fees_paid_usdt)],[['Slippage · USDT','Kayma · USDT'],level(wallet.slippage_cost_usdt)],[['Funding · USDT','Fonlama · USDT'],level(wallet.funding_cost_usdt)],[['Open positions','Açık pozisyon'],String(wallet.open_position_count??'—')],[['Open risk · USDT','Açık risk · USDT'],level(wallet.current_open_risk_usdt)],[['Max drawdown','Azami düşüş'],signedPercent(100*Number(wallet.max_drawdown_ratio||0))],[['Position side','Pozisyon yönü'],wallet.position_side||'—'],[['Entry / mark','Giriş / piyasa'],level(wallet.position_entry_price)+' / '+level(wallet.position_mark_price)],[['Notional / margin · USDT','Notional / teminat · USDT'],level(wallet.position_notional_usdt)+' / '+level(wallet.isolated_margin_usdt)],[['Leverage','Kaldıraç'],wallet.leverage??'—'],[['Liquidation','Likidasyon'],level(wallet.liquidation_price)]],['Wallet details','Cüzdan detayı']));
    content.appendChild(p);
    const tradeRecords=(payload.trade_records||[]).filter(item=>item.market===market&&Number(item.entry)>0&&Number(item.stop_loss)>0&&Array.isArray(item.take_profit_levels)&&item.take_profit_levels.length&&item.take_profit_levels.every(value=>Number(value)>0));
    const trades=panel(['Virtual trade records','Sanal işlem kayıtları'],badge(String(tradeRecords.length)+' '+t('records','kayıt'),tradeRecords.length?'neutral':'warn'));
    if(tradeRecords.length){const headers=[['Opened','Açılış'],['Coin / TF','Koin / TF'],['Direction','Yön'],['Status','Durum'],['Entry','Giriş'],['Stop loss','Stop loss'],['Take-profit levels','Kâr-al seviyeleri'],['Quantity','Miktar'],['Realized P&L · USDT','Gerçekleşen K/Z · USDT']];if(market==='USD_M_FUTURES')headers.push(['Leverage','Kaldıraç']);trades.appendChild(table(headers,tradeRecords.map(item=>{const values=[observedTime(item.opened_at),item.symbol+' / '+item.timeframe,monitorLabel(item.direction),monitorLabel(item.status),level(item.entry),level(item.stop_loss),item.take_profit_levels.map(level).join(' / '),level(item.quantity),level(item.realized_pnl_usdt)];if(market==='USD_M_FUTURES')values.push(level(item.leverage));return values;})));}
    else trades.appendChild(el('div','aw-empty',['No virtual trade with a complete entry, stop-loss, and take-profit plan has been recorded. Pending opportunities are listed on Opportunities.','Tam giriş, stop-loss ve kâr-al planı olan sanal işlem kaydı yok. Teyit bekleyen fırsatlar Opportunities ekranında listelenir.']));
    append(trades,el('div','aw-status',['Only journal-backed virtual positions with complete numeric entry, stop-loss, and take-profit levels are displayed.','Yalnızca jurnal kaynaklı ve sayısal giriş, stop-loss, kâr-al seviyeleri tam olan sanal pozisyonlar gösterilir.']));content.appendChild(trades);
    const daemon=localData?.virtual||{},projection=daemon.dashboard_simulation_projection||{},observations=Array.isArray(projection.symbol_observations)?projection.symbol_observations:[];
    const scope=state.simulationScope==='selected'?'selected':'all',selectedObservation=observations.find(item=>item.symbol===marketSelections[market]),manualSimulation=selected.refresh?.simulation||{};
    const simulation=scope==='all'?{state:daemon.status||'NOT_RUN',virtual_decision_status:daemon.virtual_decision_status,candidate_count:daemon.candidate_count,virtual_order_ready:daemon.virtual_order_ready,blockers:daemon.blockers||[],observed_at:daemon.last_success_at,scan_lane:daemon.scan_lane}:{...(selectedObservation||manualSimulation),state:selectedObservation?.state||manualSimulation.state||'PENDING'};
    const action=panel(['Autonomous simulation action','Otonom simülasyon aksiyonu'],badge(statusLabel(simulation.state||'NOT_RUN'),simulation.state==='COMPLETED'||simulation.state==='RUNNING'?'':'warn'));
    const allChoice=button(t('All eligible coins','Tüm uygun koinler'),()=>{state.simulationScope='all';render();}),selectedChoice=button(t('Selected coin','Seçili koin'),()=>{state.simulationScope='selected';render();});allChoice.setAttribute('aria-pressed',String(scope==='all'));selectedChoice.setAttribute('aria-pressed',String(scope==='selected'));append(action,append(el('div','aw-toolbar'),allChoice,selectedChoice));
    if(scope==='all'){append(action,row(['Coverage','Kapsam'],String(projection.scanned_symbol_count??0)+' / '+String(projection.eligible_symbol_count??'—')),row(['Pending background scans','Bekleyen arka plan taraması'],String(projection.pending_symbol_count??'—')),row(['Current background coin','Güncel arka plan koini'],daemon.symbol||'—'),row(['Scan lane','Tarama hattı'],daemon.scan_lane||'—'),row(['Last full coverage','Son tam kapsam'],observedTime(projection.last_full_coverage_at)));const rows=observations.slice().sort((a,b)=>String(b.observed_at||'').localeCompare(String(a.observed_at||''))).slice(0,100);action.appendChild(table([['Observed','Gözlem'],['Coin','Koin'],['Lane','Hat'],['Cycle','Döngü'],['Decision','Karar'],['Candidates','Aday'],['Virtual order','Sanal emir']],rows.map(item=>[observedTime(item.observed_at),item.symbol||'—',item.scan_lane||'—',item.state||'—',item.virtual_decision_status||'—',String(item.candidate_count??'—'),item.virtual_order_ready===true?t('Ready','Hazır'):t('Not ready','Hazır değil')])));append(action,el('div','aw-status',t('All-coin coverage is bounded to the canonical eligible universe. Records shown: ','Tüm-koin kapsamı kanonik uygun evren ile sınırlıdır. Gösterilen kayıt: ')+rows.length+' / '+observations.length));}else{append(action,row(['Selected coin','Seçili koin'],marketSelections[market]||'—'),row(['Observed','Gözlem'],observedTime(simulation.observed_at||simulation.completed_at)),row(['Scan lane','Tarama hattı'],simulation.scan_lane||'—'));}
    append(action,row(['Decision','Karar'],simulation.virtual_decision_status||'—'),row(['Virtual order prepared','Sanal emir hazır'],simulation.virtual_order_ready===true?t('Yes','Evet'):t('No','Hayır')),row(['Analyzed candidates','Analiz edilen aday'],String(simulation.candidate_count??'—')));
    (simulation.blockers||[]).slice(0,12).forEach(value=>action.appendChild(el('div','aw-status',value)));
    content.appendChild(action);
  }
  let lastPollFailed = false;
  let learningRefreshPending = false;
  let learningRefreshError = false;
  let lastLearningAttempt = 0;
  let walletRefreshPending = false;
  let walletRefreshError = false;
  let walletRefreshStatus = {state:'NOT_RUN',blockers:[]};
  async function refreshLearning(){
    if(learningRefreshPending || localData?.radars?.learning?.state==='RUNNING')return;
    learningRefreshPending=true;learningRefreshError=false;lastLearningAttempt=Date.now();render();
    try{
      const response=await fetch('/api/radars/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({radar:'learning'}),cache:'no-store',signal:AbortSignal.timeout(8000)});
      if(!response.ok)throw new Error('LEARNING_REFRESH_FAILED');
      const job=await response.json();
      if(localData)localData.radars={...(localData.radars||{}),learning:job};
    }catch{learningRefreshError=true;}
    finally{learningRefreshPending=false;render();}
  }
  function learningToolbar(){
    const job=localData?.radars?.learning||{state:'NOT_RUN'};
    const running=learningRefreshPending||job.state==='RUNNING';
    const action=button(running?['Refreshing…','Yenileniyor…']:['Refresh summary','Özeti yenile'],refreshLearning);
    action.disabled=running;action.dataset.choice='refresh-learning';
    const message=learningRefreshError?['Refresh could not start; try again.','Yenileme başlatılamadı; tekrar deneyin.']:job.state==='COMPLETED_WITH_BLOCKERS'?['Refresh did not complete successfully. You can retry.','Yenileme başarıyla tamamlanmadı. Yeniden deneyebilirsiniz.']:running?['Analyzing the current evidence…','Mevcut kanıtlar analiz ediliyor…']:job.state==='COMPLETED'?['Evidence checked; unchanged content retains its recent summary time.','Kanıtlar kontrol edildi; içerik değişmediyse yakın tarihli özet zamanı korunur.']:['Stale summaries refresh automatically.','Eski özetler otomatik yenilenir.'];
    const note=el('div','aw-status',message);note.setAttribute('role','status');
    return append(el('div','aw-toolbar'),note,action);
  }
  const statusLabel = value => ({CURRENT:t('Current','Güncel'),STALE:t('Stale','Eski'),UNAVAILABLE:t('Unavailable','Veri yok'),INVALID:t('Invalid','Geçersiz'),READY:t('Ready','Hazır'),DISABLED:t('Disabled','Devre dışı'),NO_ELIGIBLE_DEPTH_TARGETS:t('No eligible targets','Uygun hedef yok'),COLLECTING:t('Collecting','Toplanıyor'),DEGRADED:t('Degraded','Kısıtlı'),RUNNING:t('Running','Çalışıyor'),PENDING:t('Queued','Sırada'),COMPLETED:t('Completed','Tamamlandı'),FAILED:t('Failed','Başarısız'),NOT_RUN:t('Not run','Çalıştırılmadı'),NOT_APPLIED:t('Not applied','Uygulanmadı'),BLOCKED:t('Blocked','Engelli')})[value] || value || '—';
  const numeric = value => value===null || value===undefined || value==='' || !Number.isFinite(Number(value)) ? '—' : money(Number(value));
  const privateValue = value => state.hideBalances ? '••••' : numeric(value);
  const observedTime = value => value ? new Date(value).toLocaleString(state.language==='tr'?'tr-TR':'en-US',{timeZone:'Europe/Istanbul'}) : '—';
  function sourceInfo(name){return localData?.sources?.[name] || {status:'UNAVAILABLE'};}
  function sourceBadge(name){const source=sourceInfo(name),producer=source.producer_status;const healthy=['CURRENT','READY'].includes(source.status)&&['READY',undefined].includes(producer);const label=statusLabel(source.status)+(producer?' / '+statusLabel(producer):'');return badge(label,healthy?'':'warn');}
  function sourceNote(name){const source=sourceInfo(name);const producer=source.producer_service?' · '+t('Producer: ','Üretici: ')+source.producer_service+' '+statusLabel(source.producer_status):'';return el('div','aw-status',t('Source: ','Kaynak: ')+(source.file||'—')+' · '+observedTime(source.observed_at)+' · '+statusLabel(source.status)+producer);}
  const humanBytes = value => Number.isFinite(Number(value)) ? (Number(value)/(1024**3)).toFixed(2)+' GiB' : '—';
  function findingCopy(item){
    const facts=item?.facts||{};
    const copies={
      MARKET_HISTORY_INCOMPLETE:{title:['Candle history is incomplete','Mum geçmişi tamamlanmadı'],explanation:['Opportunity generation remains unavailable until required timeframe streams are usable. A fresh state file is not proof of usable candles.','Gerekli zaman dilimi akışları kullanılabilir olana kadar fırsat üretimi kapalı kalır. Güncel durum dosyası, kullanılabilir mum verisi kanıtı değildir.'],action:['Keep the canonical collector running and resolve its reported blockers; do not bypass data-quality gates.','Kanonik toplayıcıyı çalışır tutun ve bildirilen engelleri giderin; veri kalitesi kapılarını atlamayın.']},
      MARKET_DEPTH_PARTIAL_COVERAGE:{title:['L2 depth coverage is partial','L2 derinlik kapsamı kısmi'],explanation:['The depth SQLite journal contains order-book events. Its file size does not satisfy OHLCV candle-history requirements.','Derinlik SQLite günlüğü emir defteri olaylarını içerir. Dosya boyutu OHLCV mum geçmişi gereksinimini karşılamaz.'],action:['Use this journal only for microstructure evidence and continue the separate candle-history recovery.','Bu günlüğü yalnızca mikro yapı kanıtı olarak kullanın ve ayrı mum geçmişi kurtarmasını sürdürün.']},
      FUTURES_RESEARCH_NOT_READY:{title:['Futures research is not ready','Futures araştırması hazır değil'],explanation:['The research ingest has not completed its eligible universe, so opportunity output must remain fail-closed.','Araştırma alımı uygun evreni tamamlamadı; bu nedenle fırsat çıktısı kapalı kalmalıdır.'],action:['Resolve the exact reported integrity or ingest blocker and rerun validation without weakening checks.','Bildirilen kesin bütünlük veya alım engelini giderin; kontrolleri zayıflatmadan doğrulamayı yeniden çalıştırın.']},
      SERVICE_NOT_READY:{title:['A background service needs attention','Bir arka plan servisi dikkat gerektiriyor'],explanation:['Heartbeat health and data readiness are separate. This service reported a non-ready state.','Heartbeat sağlığı ile veri hazırlığı ayrıdır. Bu servis hazır olmayan bir durum bildirdi.'],action:['Inspect the reported blocker and process ownership before any targeted restart.','Hedefli yeniden başlatmadan önce bildirilen engeli ve süreç sahipliğini inceleyin.']},
      LEARNING_SUMMARY_EMPTY:{title:['Learning summary has no evidence-backed items','Öğrenim özetinde kanıta dayalı öğe yok'],explanation:['No lesson or measured experiment is recorded; the system must not invent recommendations.','Kayıtlı ders veya ölçülmüş deney yoktur; sistem öneri uydurmamalıdır.'],action:['Refresh learning only after new canonical evidence is available.','Öğrenimi yalnızca yeni kanonik kanıt oluştuğunda yenileyin.']}
    };
    const copy=copies[item?.finding_id]||{title:[item?.finding_id||'Unknown finding',item?.finding_id||'Bilinmeyen bulgu'],explanation:['A canonical source reported a non-ready state.','Kanonik bir kaynak hazır olmayan durum bildirdi.'],action:['Inspect the attached evidence before acting.','Harekete geçmeden önce ekli kanıtı inceleyin.']};
    return {...copy,evidence:item?.evidence||'—',status:item?.status||'UNAVAILABLE',severity:item?.severity||'P3',facts};
  }
  function healthFindingsPanel(title,limit=12){
    const findings=(localData?.health_findings||[]).slice(0,limit);const p=panel(title,badge(String(findings.length)+' '+t('items','öğe'),findings.length?'warn':'neutral'));
    if(findings.length)p.appendChild(table([['Priority','Öncelik'],['Finding','Bulgu'],['Why it matters','Neden önemli'],['Safe next action','Güvenli sonraki adım'],['Evidence','Kanıt']],findings.map(item=>{const copy=findingCopy(item);return [copy.severity,text(copy.title),text(copy.explanation),text(copy.action),copy.evidence];})));
    else p.appendChild(el('div','aw-status',['No current deterministic health finding is reported.','Güncel deterministik sağlık bulgusu bildirilmedi.']));
    return p;
  }
  function blockerList(content,values){if(!values?.length)return;const p=panel(['Reported blockers','Kaynağın bildirdiği engeller']);values.slice(0,12).forEach(value=>p.appendChild(el('div','aw-status',value)));content.appendChild(p);}
  function missingPanel(title,note){const p=panel(title,badge(['Data unavailable','Veri yok'],'warn'));p.appendChild(el('div','aw-empty',note));return p;}
  const radarKey = label => ({'Web Radar':'web','GitHub Radar':'github','Haber Radarı':'news'})[label];
  const radarStateLabel = value => ({NOT_RUN:t('Not run','Çalıştırılmadı'),RUNNING:t('Running','Çalışıyor'),COMPLETED:t('Completed','Tamamlandı'),COMPLETED_WITH_BLOCKERS:t('Completed with blockers','Engellerle tamamlandı')})[value] || value || '—';
  function radarInfo(label){return localData?.radars?.[radarKey(label)] || {state:'NOT_RUN',result:{}};}
  async function refreshLocal(){
    try{const response=await fetch('/api/state',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!response.ok)throw new Error('LOCAL_SOURCE_UNAVAILABLE');const payload=await response.json();if(payload.execution_allowed!==false||payload.live_eligibility_status!=='LIVE_ORDER_BLOCKED')throw new Error('INVALID_SOURCE_AUTHORITY');localData=payload;lastPollFailed=false;}
    catch{localData=null;lastPollFailed=true;}
  }
  async function refreshWallet(){
    if(walletRefreshPending)return;
    walletRefreshPending=true;walletRefreshError=false;render();
    try{
      const response=await fetch('/api/wallet/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'refresh'}),cache:'no-store',signal:AbortSignal.timeout(8000)});
      if(!response.ok)throw new Error('WALLET_REFRESH_START_FAILED');
      walletRefreshStatus=await response.json();
      for(let attempt=0;attempt<30&&walletRefreshStatus.state==='RUNNING';attempt+=1){await new Promise(resolve=>setTimeout(resolve,500));await refreshLocal();walletRefreshStatus=localData?.wallet_refresh||walletRefreshStatus;}
      await refreshLocal();walletRefreshStatus=localData?.wallet_refresh||walletRefreshStatus;
      walletRefreshError=lastPollFailed||walletRefreshStatus.state!=='COMPLETED';
    }catch{walletRefreshError=true;}
    finally{walletRefreshPending=false;render();}
  }
  async function runRadar(label){
    const key=radarKey(label);if(!key)return;
    try{const response=await fetch('/api/radars/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({radar:key}),cache:'no-store',signal:AbortSignal.timeout(8000)});if(!response.ok)throw new Error('RADAR_START_FAILED');const status=await response.json();if(localData){localData.radars={...(localData.radars||{}),[key]:status};}lastPollFailed=false;}
    catch{lastPollFailed=true;}
    render();
  }
  function radarToolbar(label){const info=radarInfo(label);const disabled=info.state==='RUNNING';const action=button(disabled?['Refreshing…','Yenileniyor…']:['Refresh','Yenile'],()=>runRadar(label));action.disabled=disabled;action.setAttribute('aria-label',text(['Run '+label,' '+label+' çalıştır']));return append(el('div','aw-toolbar'),segment('radar',['Web Radar','GitHub Radar']),append(el('div','aw-toolbar'),badge(radarStateLabel(info.state),info.state==='COMPLETED'?'':'warn'),action));}
  function radarResultPanel(label){
    const info=radarInfo(label);const result=info.result||{};const title=label+' '+t('run','çalıştırması');const tag=badge(radarStateLabel(info.state),info.state==='COMPLETED'?'':'warn');const p=panel(title,tag);
    append(p,row(['Started','Başlangıç'],observedTime(info.started_at)),row(['Completed','Tamamlanma'],observedTime(info.completed_at)),row(['Result','Sonuç'],result.result_status||'—'));
    const items=result.items||[];
    if(label==='Web Radar'&&items.length){p.appendChild(table([['Area','Alan'],['Finding','Bulgu'],['Topic','Başlık'],['Action','Karar'],['Confidence','Güven']],items.map(i=>[i.technology_area||'—',i.title||'—',i.research_topic||'—',i.recommended_action||'—',Number.isFinite(Number(i.confidence))?Number(i.confidence).toFixed(2):'—'])));}
    else if(label==='GitHub Radar'&&items.length){p.appendChild(table([['Capability','Kabiliyet'],['Repository','Depo'],['Topic','Başlık'],['Action','Karar'],['License','Lisans']],items.map(i=>[i.capability_id||'—',i.repository||'—',i.research_topic||'—',i.recommended_action||'—',i.license_id||'—'])));}
    else if(label==='Haber Radarı'&&items.length){p.appendChild(table([['Asset','Varlık'],['Event','Olay'],['Claim','İddia'],['Verification','Doğrulama']],items.map(i=>[i.asset||i.symbol||'—',i.event_type||'—',i.claim||'—',i.verification_status||'—'])));}
    else if(info.state==='NOT_RUN'){p.appendChild(el('div','aw-empty',['Select Refresh to start this bounded, local research run.','Bu sınırlı yerel araştırmayı başlatmak için Yenile seçin.']));}
    else if(info.state==='RUNNING'){p.appendChild(el('div','aw-empty',['The radar is running. This view refreshes automatically.','Radar çalışıyor. Bu görünüm otomatik yenilenir.']));}
    else{p.appendChild(el('div','aw-empty',['No eligible findings were returned. Inspect the reported blockers before retrying.','Uygun bulgu dönmedi. Yeniden denemeden önce bildirilen engelleri inceleyin.']));}
    if(result.blockers?.length)result.blockers.slice(0,8).forEach(value=>p.appendChild(el('div','aw-status',value)));
    return p;
  }
  function renderLocal(content){
    if(!['opportunities','virtual-market'].includes(state.page))marketVisiblePage='';
    if(!localData){content.appendChild(missingPanel(['Local connection','Yerel bağlantı'],lastPollFailed?['Connection interrupted; retrying automatically.','Bağlantı kesildi; otomatik yeniden deneniyor.']:['Reading local sources…','Yerel kaynaklar okunuyor…']));return;}
    if(state.page==='overview'){
      const services=localData.services||[];const requiredServices=services.filter(s=>s.required);const ready=requiredServices.filter(s=>s.status==='READY').length;
      const readiness=localData.operational_readiness||{},history=localData.market_history||{},depth=localData.market_depth||{};
      append(content,kpis([[['Operational readiness','Operasyonel hazırlık'],statusLabel(readiness.status),String(readiness.high_priority_finding_count??'—')+' '+t('high-priority findings','yüksek öncelikli bulgu')],[['Candle streams ready','Hazır mum akışı'],String(history.completed_streams??'—')+' / '+String(history.total_streams??'—'),statusLabel(sourceInfo('market_history').status)],[['L2 live symbols','L2 canlı koin'],String(depth.live_symbol_count??'—')+' / '+String(depth.configured_symbol_count??'—'),humanBytes(depth.database_bytes)]]));
      const p=panel(['Background services','Arka plan servisleri']);p.appendChild(table([['Service','Servis'],['Status','Durum'],['Useful age','Faydalı yaş'],['PID','PID'],['Blocker','Engel']],services.map(s=>[s.service,statusLabel(s.status),Number.isFinite(Number(s.age_seconds))?String(s.age_seconds)+' s':'—',s.child_pid||s.pid||'—',(s.blockers||[]).slice(0,2).join(' · ')||'—'])));content.appendChild(p);
      p.appendChild(row(['Required service heartbeat','Zorunlu servis heartbeat'],ready+' / '+requiredServices.length,['Service liveness only; not data readiness','Yalnızca servis canlılığı; veri hazırlığı değildir']));
      const c=panel(['Data sources','Veri kaynakları']);[['account','BinanceWallet'],['virtual','VirtualMarket'],['market_history','OHLCV candle history'],['market_depth','L2 depth journal'],['futures_research','Futures Research'],['discovery','Skill Discovery'],['learning','Kaizen']].forEach(([key,label])=>c.appendChild(row(label,sourceBadge(key),observedTime(sourceInfo(key).observed_at))));content.appendChild(c);return;
    }
    if(state.page==='binance-wallet'){
      const account=localData.account||{};const portfolio=account.portfolio||{};
      const walletJob=localData.wallet_refresh||walletRefreshStatus;
      const refresh=button(walletRefreshPending?['Refreshing…','Yenileniyor…']:['Refresh wallet','Cüzdanı yenile'],refreshWallet);refresh.disabled=walletRefreshPending;
      append(content,append(el('div','aw-toolbar'),sourceBadge('account'),button(state.hideBalances?['Show balances','Tutarları göster']:['Hide balances','Tutarları gizle'],()=>{state.hideBalances=!state.hideBalances;render();}),refresh));
      content.appendChild(el('div','aw-status',walletRefreshError?['The canonical wallet refresh did not complete; reported blockers remain visible.','Kanonik cüzdan yenileme tamamlanmadı; bildirilen engeller görünür kalır.']:walletRefreshPending?['Running the canonical read-only wallet refresh…','Kanonik salt-okunur cüzdan yenilemesi çalışıyor…']:walletJob.state==='COMPLETED'?['Verified account snapshot refreshed; trading remains disabled.','Doğrulanmış hesap anlık görüntüsü yenilendi; işlem kapalı kalır.']:['Refresh runs the canonical read-only wallet cycle; trading remains disabled.','Yenile, kanonik salt-okunur cüzdan döngüsünü çalıştırır; işlem kapalı kalır.']));
      if(walletJob.blockers?.length)walletJob.blockers.slice(0,8).forEach(value=>content.appendChild(el('div','aw-status',value)));
      append(content,kpis([[['Valued assets · USDT','Değerlenen varlıklar · USDT'],privateValue(portfolio.total_value_usdt),['Canonical Spot valuation · Not combined account equity','Kanonik Spot değerleme · Birleşik hesap toplamı değil']],[['Unrealized P&L · USDT','Açık K/Z · USDT'],privateValue(portfolio.unrealized_pnl_usdt),['As reported by account source','Hesap kaynağının bildirdiği değer']],[['Latest source timestamp','Son kaynak zamanı'],observedTime(sourceInfo('account').observed_at),statusLabel(sourceInfo('account').status)]]));
      const p=panel(['Spot inventory','Spot varlıkları'],badge(statusLabel(account.spot?.wallet_status),'warn'));const valued=new Map((account.valued_assets||[]).map(a=>[a.asset,a]));
      p.appendChild(table([['Asset','Varlık'],['Free','Kullanılabilir'],['Locked','Kilitli'],['Value · USDT','Değer · USDT']],(account.inventory||[]).map(a=>[a.asset,privateValue(a.free),privateValue(a.locked),privateValue(valued.get(a.asset)?.value_usdt)])));
      if(!(account.inventory||[]).length)p.appendChild(el('div','aw-empty',['No current inventory to display','Gösterilecek güncel envanter yok']));
      append(p,row(['Unpriced assets','Fiyatlanamayan varlık'],String(account.unpriced_asset_count??'—')),row(['Futures wallet status','Futures cüzdan durumu'],statusLabel(account.futures?.wallet_status)),row(['Reported Futures positions','Bildirilen Futures pozisyonu'],String(account.futures_position_count??'—')));content.appendChild(p);content.appendChild(sourceNote('account'));blockerList(content,account.blockers);return;
    }
    if(state.page==='opportunities'){
      marketMonitor(content);return;
    }
    if(state.page==='research'){
      const research=localData.futures_research||{};const discovery=localData.discovery||{};
      append(content,kpis([[['Completed symbols','Tamamlanan koin'],String(research.completed_symbol_count??'—')+' / '+String(research.eligible_symbol_count??'—'),['Futures multi-timeframe research','Futures çoklu zaman dilimi araştırması']],[['Queued symbols','Bekleyen koin'],String(research.pending_symbol_count??'—'),statusLabel(research.phase)],[['Discovery candidates','Keşif adayı'],String(discovery.candidates_kept??'—'),['Existing discovery output','Mevcut keşif çıktısı']]]));
      const p=panel(['Research activity','Araştırma faaliyeti'],sourceBadge('futures_research'));append(p,row(['Active symbol','Aktif koin'],research.active_symbol||'—'),row(['Active timeframe','Aktif TF'],research.active_timeframe||'—'),sourceNote('futures_research'));content.appendChild(p);
      content.appendChild(radarToolbar(state.radar));content.appendChild(radarResultPanel(state.radar));blockerList(content,research.blockers);return;
    }
    if(state.page==='virtual-market'){
      marketMonitor(content,true);
      const v=localData.virtual||{},collection=localData.market_history||{};
      append(content,kpis([[['Collector cycles','Toplayıcı döngüsü'],String(v.cycle_count??'—'),['Shared runtime; not a per-wallet count','Ortak runtime; cüzdan bazlı sayım değil']],[['Candidate count','Aday sayısı'],String(v.candidate_count??'—'),statusLabel(v.research_status)],[['Virtual decision','Sanal karar'],v.virtual_decision_status||'—',['Canonical virtual runtime result','Kanonik sanal runtime sonucu']]]));
      const coverage=panel(['All-market background collection','Tüm piyasa arka plan toplama'],sourceBadge('market_history'));
      append(coverage,row(['Refresh cadence','Yenileme aralığı'],collection.refresh_interval_seconds?String(collection.refresh_interval_seconds/60)+' min':'—'),row(['Collector state','Toplayıcı durumu'],statusLabel(collection.status)),row(['Active market','Aktif piyasa'],collection.active_market||'—'),row(['Spot universe','Spot evreni'],String(collection.spot_universe_count??'—')),row(['USD-M Futures universe','USD-M Futures evreni'],String(collection.futures_universe_count??'—')),row(['Completed symbols','Tamamlanan koin'],String(collection.completed_symbols??'—')+' / '+String(collection.total_symbols??'—')),row(['Completed data streams','Tamamlanan veri akışı'],String(collection.completed_streams??'—')+' / '+String(collection.total_streams??'—')));const schedule=collection.timeframe_refresh_schedule||[];if(schedule.length)coverage.appendChild(table([['TF','TF'],['Cadence','Periyot'],['Data source','Veri kaynağı'],['Network','Ağ']],schedule.map(item=>[item.timeframe,String(Number(item.interval_seconds)/60)+' min',item.source,item.network_download?t('Download','İndirme'):t('Local derive','Yerel türetim')])));
      content.appendChild(coverage);const futuresResearch=localData.futures_research||{},monitor=futuresResearch.opportunity_monitor||{},learning=futuresResearch.learning||{};const futuresPanel=panel(['Futures background opportunity review','Futures arka plan fırsat incelemesi'],sourceBadge('futures_research'));append(futuresPanel,row(['Current monitor coin','Güncel izleme koini'],monitor.symbol||futuresResearch.monitor_symbol||'—'),row(['Candidates / evaluated','Aday / değerlendirilen'],String(monitor.candidate_count??'—')+' / '+String(monitor.evaluated_outcome_count??'—')),row(['Favorable / adverse outcomes','Olumlu / olumsuz sonuçlar'],String(monitor.favorable_outcome_count??'—')+' / '+String(monitor.adverse_outcome_count??'—')),row(['Research lessons / experiments','Araştırma dersi / deneyi'],String(learning.lesson_count??'—')+' / '+String(learning.experiment_count??'—')));if((learning.lesson_codes||[]).length)futuresPanel.appendChild(el('div','aw-status',(learning.lesson_codes||[]).join(' · ')));content.appendChild(futuresPanel);content.appendChild(sourceNote('market_history'));blockerList(content,collection.blockers);content.appendChild(sourceNote('virtual'));blockerList(content,v.blockers);return;
    }
    if(state.page==='news'){
      const info=radarInfo('Haber Radarı');const result=info.result||{};
      append(content,kpis([[['Verified news','Doğrulanmış haber'],result.item_count===undefined?'—':String(result.item_count),result.result_status||t('Not run','Çalıştırılmadı')],[['Universe coverage','Evren kapsamı'],'—',['Classification is applied only when supplied by the canonical result','Sınıflama yalnızca kanonik sonuçta sunulduğunda uygulanır']],[['Last scan','Son tarama'],observedTime(info.completed_at),radarStateLabel(info.state)]]));
      const action=button(info.state==='RUNNING'?['Refreshing…','Yenileniyor…']:['Refresh news radar','Haber radarını yenile'],()=>runRadar('Haber Radarı'));action.disabled=info.state==='RUNNING';append(content,append(el('div','aw-toolbar'),el('div','aw-status',t('Eligible-coin news scan','Uygun koin haber taraması')),append(el('div','aw-toolbar'),badge(radarStateLabel(info.state),info.state==='COMPLETED'?'':'warn'),action)));
      const p=panel(['Coin news','Koin haberleri'],badge(result.result_status||radarStateLabel(info.state),info.state==='COMPLETED'?'':'warn'));append(p,badge(['Stablecoins excluded by universe policy','Evren politikasında stablecoin hariç']),badge(['Wrapped excluded by universe policy','Evren politikasında wrapped hariç']),badge(['Leveraged tokens excluded by universe policy','Evren politikasında kaldıraçlı token hariç']));
      p.appendChild(el('div','aw-empty',info.state==='NOT_RUN'?['Select Refresh to run the configured allowlisted public-news source.','Yapılandırılmış izinli genel haber kaynağını çalıştırmak için Yenile seçin.']:result.item_count?['Verified findings are listed below.','Doğrulanmış bulgular aşağıda listelenir.']:['No verified eligible finding was returned. Reported blockers remain visible below.','Doğrulanmış uygun bulgu dönmedi. Bildirilen engeller aşağıda görünür.']));content.appendChild(p);content.appendChild(radarResultPanel('Haber Radarı'));return;
    }
    if(state.page==='kaizen'){
      content.appendChild(learningToolbar());
      const learning=localData.learning||{},findings=localData.health_findings||[];
      append(content,kpis([[['Actionable Kaizen signals','Eyleme dönük Kaizen sinyali'],String(findings.length),['Deterministically derived from canonical health evidence','Kanonik sağlık kanıtından deterministik türetilir']],[['Recorded lessons','Kaydedilen öğrenimler'],String(learning.lesson_count??'—'),['Canonical learning summary','Kanonik öğrenim özeti']],[['Recorded experiments','Kaydedilen deneyler'],String(learning.experiment_count??'—'),['No measured-benefit claim','Ölçülmüş fayda iddiası yok']]]));
      content.appendChild(healthFindingsPanel(['Current Kaizen backlog','Güncel Kaizen kuyruğu']));return;
    }
    if(state.page==='recommendations'){
      content.appendChild(learningToolbar());
      const learning=localData.learning||{},readiness=localData.operational_readiness||{};append(content,kpis([[['System health','Sistem sağlığı'],statusLabel(readiness.status),String(readiness.finding_count??'—')+' '+t('findings','bulgu')],[['Recorded lessons','Kaydedilen öğrenimler'],String(learning.lesson_count??'—'),['Canonical learning summary','Kanonik öğrenim özeti']],[['Recorded experiments','Kaydedilen deneyler'],String(learning.experiment_count??'—'),['No measured-benefit claim','Ölçülmüş fayda iddiası yok']]]));
      content.appendChild(healthFindingsPanel(['Evidence-backed system recommendations','Kanıta dayalı sistem önerileri']));return;
    }
    content.appendChild(missingPanel(['Evidence','Kanıtlar'],['No validated evidence package is connected.','Doğrulanmış kanıt paketi bağlı değil.']));
  }
  async function pollLocal(){
    await refreshLocal();
    await loadMarket();
    if(state.mode==='local' && localData && ['STALE','UNAVAILABLE'].includes(sourceInfo('learning').status) && Date.now()-lastLearningAttempt>=60000)await refreshLearning();
    if(state.mode==='local')render();setTimeout(pollLocal,30000);
  }
