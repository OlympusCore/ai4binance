# Mimari — ELI5

## Büyük resim

Platform bir fabrikaya benzer. Her bölüm tek iş yapar ve sonraki bölüme denetlenmiş
bir paket verir.

```text
Binance public data
  -> DataAcquisitionAgent
  -> immutable MarketSnapshot
  -> DataQuality + Liquidity
  -> 34 analysis agents
  -> Confluence
  -> StrategyCandidate
  -> Risk
  -> Validation
  -> NO_TRADE / research artifact / paper-only lifecycle
```

## Neden tek snapshot?

Bütün ajanların aynı fotoğrafa bakması gerekir. Biri saat 10:00, diğeri 10:05
verisini kullanırsa sonuç karşılaştırılamaz. Bu nedenle `MarketSnapshot` döngü
boyunca değişmez ve bütün sonuçlar aynı `snapshot_id` taşır.

## Katmanlar

### 1. Exchange ve data

- `exchange/transport.py`: sınırlandırılmış public HTTPS GET.
- `exchange/client.py`: time, exchangeInfo, ticker, book ticker ve klines.
- `exchange/private.py`: yalnız read-only account/open-orders HMAC REST.
- `data/acquisition.py`: açık mumu çıkarır ve ortak snapshot üretir.
- `data/archive.py`: checksum'lı Parquet araştırma arşivi.

Private REST adaptörü CLI'ye bağlı değildir ve account/open-orders/`myTrades`
için signed GET-only allowlist kullanır. `exchange/ws_api.py`; Ed25519 imza,
allowlist Binance host, bounded response eşleştirme, `session.logon`, read-only
`account.status`/`openOrders.status` ve authenticated order request çekirdeğini
sağlar. `execution/live_spot.py` içindeki order metotları bütün `LiveGateInput`
koşullarını ve birebir preview hash onayını içeride tekrar doğrular. CLI canlı emir
göndermez; varsayılan durum `LIVE_ORDER_BLOCKED` kalır.

### 2. Ajanlar

- 47 toplam governance tanımı vardır.
- 34 tanesi analiz aşamasındadır.
- 10 core ve 23 advanced ajan yanında `trend_events` ajanı bulunur.
- Trend events; OHLC4, Supertrend ATR14/multiplier2, EMA cross ve confirmed swing
  bilgisi üretir.
- Ajanlar final sinyal veya emir yetkisine sahip değildir.

Bağımsız ajanlar bounded thread pool içinde paralel çalışır. Bağımlı ajan bir önceki
sonuç hazır değilse `BLOCKED` olur.

### 2.1 Market Outlook Intelligent Engine

`outlook/` katmanı yeni teknik gösterge hesaplamaz. Aynı immutable snapshot'a ait
mevcut trend, rejim, volatilite, destek/direnç, setup, news ve volume-profile agent
çıktılarını typed bir `MarketOutlook` sözleşmesinde sentezler. Çıktı şunları içerir:

- 1d, 4h, 1h ve 15m bias,
- pro-trend yönü ve timeframe çatışması,
- market regime, volatility state ve macro-cycle proxy,
- en fazla beş research setup,
- kaynaklı high-impact event'ler,
- ATR-buffered support/resistance zone'ları,
- TPO/composite sınırlamaları ve volume-weighted POC proxy.

Outlook engine sinyal üretmez, risk onayı vermez ve emir yetkisi taşımaz. Gerçek
TPO auction profile, single-print ve composite balance-area hesabı henüz yoktur;
volume-profile sonucu yalnızca `PROXY_ONLY` ve `RESEARCH_ONLY` bağlamdır.

### 3. Strateji ve risk

`strategies/` araştırma adayları üretir. `risk.py`; equity, spread, slippage,
cooldown, günlük kayıp, envanter ve Binance filtrelerini denetler. Risk hesabının
yapılabilmesi, emrin onaylandığı anlamına gelmez.

### 4. Paper lifecycle

`execution/` gerçek borsaya emir göndermez. Fee/slippage, staged exit, stop-first
sıralama, monotonik trailing ve closure review simüle edilir. Ledger append-only
JSONL kullanabilir.

### 5. Backtest, walk-forward ve tuning

- Sinyal yalnız kapanmış mumları görür.
- Giriş en erken sonraki mum açılışındadır.
- Stop ve hedef aynı mumdaysa stop önce kabul edilir.
- Walk-forward parametreyi train'de seçer ve takip eden OOS'ta bir kez ölçer.
- OOS raporu etkili örnek sayısı, güven aralığı, confirmatory/exploratory etiketi
  ve Bonferroni multiple-testing düzeltmesini ayrıca kaydeder.
- Tuning yalnız whitelist ve bounded parametreleri tarar.
- Başarılı sonuç en fazla `STAGED_CANDIDATE` olur; otomatik canlı yetki vermez.

### 5.1 Research governance

- `research_governance.py`: falsifiable hypothesis lifecycle, hash-linked run card
  ve yalnız demotion önerebilen strategy decay evaluator içerir.
- Run card dataset/config/strategy/artifact SHA-256, code revision, seed, maliyet
  varsayımları, metrikler ve blocker'ları taşır.
- Eksik health kanıtı sağlıklı sayılmaz; decay otomasyonu recovery veya promotion
  yapamaz ve insan reapproval gerektirir.

### 5.2 Backtest integrity ve overfit kanıtı

- `validation/integrity.py`: batch/prefix karşılaştırmalı look-ahead analizi,
  warmup-offset recursive stability analizi ve point-in-time feature lineage gate'i.
- `WalkForwardConfig.purge_size` train/test sınırındaki label overlap riskini;
  `embargo_size` ise ardışık fold başlangıçları arasındaki explicit boşluğu yönetir.
- `validation/overfit.py`: getiri skew/kurtosis ve hypothesis count kullanan
  Deflated Sharpe kanıtı ile train-winner/OOS-rank tabanlı selection-overfit
  diagnostic'i üretir.
- Bu raporların tamamı `execution_allowed=false` kalır ve yalnız promotion'ı
  bloke edebilir.

### 5.3 Deterministik event ve order state

- `events/`: enjekte edilebilir UTC/simulated clock, SHA-256 bağlantılı immutable
  event ve contiguous sequence doğrulayan bounded event bus.
- `execution/order_state.py`: submitted, accepted, partially-filled, filled,
  cancelled ve rejected geçişlerini aynı reducer ile replay eder.
- Partial fill miktarı, remaining quantity ve ağırlıklı ortalama fill fiyatı
  deterministik olarak yeniden kurulur; illegal geçiş veya hash/sequence sapması
  açık hata üretir.

### 5.4 Exchange, portfolio ve advisory dayanıklılığı

- `exchange/resilience.py`: request-weight budget ve server-time drift gate'i.
- `portfolio/reconciliation.py`: local/exchange açık emirlerini client-order-id ile
  read-only karşılaştırır.
- `portfolio/risk_budget.py`: gross, symbol, correlation-group ve strategy exposure
  limitlerini yalnız proposal düzeyinde değerlendirir.
- `agents/advisory.py`: hash'li evidence packet, kaynak citation doğrulaması,
  bull/bear/risk/data-quality rolleri, conflict raporu ve retry-bounded checkpoint.
  Advisory çıktı hiçbir koşulda signal, promotion veya execution yetkisi taşımaz.

### 6. Learning ve LLM sınırı

Learning motoru ders ve deney adayı önerebilir. Üretim parametresi aktive edemez,
risk artıramaz ve emir veremez. Advisory LLM yalnız açıklar ve denetler.

### 7. WHALE-FUSION araştırma sınırı

- `whale_fusion/models.py`: balina, sosyal ve türev olayları için immutable ve
  provenance zorunlu sözleşmeler.
- `whale_fusion/derivatives/binance_client.py`: yalnız public HTTPS GET kullanan
  Binance USD-M collector; private/account/order endpointi kabul etmez.
- `whale_fusion/features.py`: OI değişimi, z-score/percentile, fiyat-OI rejimi,
  funding/basis bağlamı, taker imbalance ve top/global divergence hesapları.
- `whale_fusion/onchain/providers.py`: dış sağlayıcı için ağ çağrısız, immutable
  envelope/replay sınırı sağlar; HTTPS host/provider allowlist'i, payload SHA-256,
  boyut, freshness, finality ve chain-event deduplikasyonunu fail-closed doğrular.
- `whale_fusion/onchain/normalizer.py`: kabul edilen sağlayıcı envelope'ının canonical
  transfer payload'ını katı biçimde doğrular; ağ çağrısı yapmaz.
- `whale_fusion/onchain/registry.py`: chain + address anahtarlı, provenance zorunlu
  ve immutable wallet-label registry.
- `whale_fusion/onchain/classifier.py`: büyük transferleri Binance, DEX, bridge,
  staking, unlock, market-maker, stablecoin, accumulation/distribution, yeni cüzdan
  ve parçalı-transfer olaylarına deterministik ayırır.
- `whale_fusion/social/registry.py`: kurucu, proje ekibi, fon yöneticisi,
  market-maker yöneticisi, balina, analist, borsa, regülatör, güvenlik ve unlock/
  governance hesaplarını platform bazında allowlist eder.
- `whale_fusion/social/normalizer.py`: provider'ın açık event-type, stance ve asset
  metadata'sını katı canonical post modeline çevirir; metinden serbest sinyal çıkarmaz.
- `whale_fusion/social/engine.py`: verified hesap, confidence, freshness, asset,
  duplicate ve karşıt stance kontrollerini yapar.
- `whale_fusion/fusion.py`: on-chain `%40`, social `%25`, derivatives `%35`
  ağırlıklarıyla channel-average, linear time-decay ve contradiction penalty
  uygular. En az iki bağımsız kanal zorunludur; derivatives Spot bağlamında
  supplementary kalır.
- `whale_fusion/integration.py`: `FusionResult` ile `MarketSnapshot` arasında
  snapshot ID, symbol ve timestamp tutarlılığı kurar; orijinal snapshot'ı değiştirmez.
- `whale_fusion/agent.py`: yalnız `whale` governance tanımını özel fusion agent'a
  bağlar; hard-gate uygunluğu yoktur ve authority/promotion sapmasını reddeder.
- `whale_fusion/audit.py`: deterministik record ID ile restart-sonrası idempotent,
  secret-redacted ve append-only JSONL fusion audit'i üretir.
- `application/whale_fusion.py`: canonical cycle'ı engine → audit → immutable
  snapshot → orchestrator sırasıyla yürütür. Audit hatasını
  `FUSION_AUDIT_WRITE_FAILED` olarak raporlar ve execution kapalı kalır.
- `cli.py whale-fusion-research`: provider çağrısı yapmadan güvenli research pipeline
  raporu üretir; testlerde canonical cycle enjekte edilebilir.

ELI5: Futures piyasası kalabalığın kaldıraçlı davranışını gösteren ek bir kamera
gibidir. Spot karar motorunun direksiyonunu tutmaz. Çıktı her zaman
`RESEARCH_ONLY`, `execution_allowed=false` kalır.

## Stabilite kuralları

1. Ağ, dosya sistemi ve core hesaplar ayrı tutulur.
2. Decimal hesapları para/filtre sınırlarında korunur.
3. Hata mesajları secret içermez.
4. Veri yoksa sessiz fallback yerine blocker üretilir.
5. Her davranış değişikliği pytest, Ruff ve MyPy ile doğrulanır.
6. Orchestrator bir analiz çevriminde tek bounded thread pool kullanır; dependency
   katmanları bu pool'u tekrar kullanırken sonuçlar stabil isim sırasıyla toplanır.
7. `agents/telemetry.py` karar sonucuna karışmadan per-agent süre, durum ve blocker
   sayısını bounded bir sink'e yazar; yüksek-cardinality serbest metin taşımaz.
8. `market_context.py` yalnız explicit provider ID, HTTPS host allowlist, health
   probe ve provenance doğrulamasıyla Market Outlook'a event bağlar.
9. `sandbox.py` AST allowlist ve backend capability gate uygular; gerçek izolasyon
   backend'i yoksa çalıştırmayı reddeder. `security_scan.py` da scanner yoksa bloke olur.

### Read-only Evidence MCP sınırı

- `outlook/storage.py`, son deterministik Market Outlook'u atomik bir state
  artefaktına yazar.
- `mcp/evidence.py`, yalnız sabit allowlist artefaktlarını boyut, şema, SHA-256,
  freshness ve yetki alanlarıyla doğrular.
- `mcp/server.py`, opsiyonel FastMCP SDK üzerinden yalnız yerel STDIO taşımasını
  ve dört salt-okunur aracı sunar.
- Araçlar dosya yolu, shell komutu, credential, wallet, risk, promotion veya emir
  parametresi kabul etmez.
- MCP bulunamazsa çekirdek çalışma etkilenmez; artefakt bulunamazsa açık blocker
  üretilir. Bütün cevaplar `RESEARCH_ONLY` ve `LIVE_ORDER_BLOCKED` kalır.

## Bilinen açık sınırlar

- Ed25519 request/session çekirdeği var; gerçek testnet/production auth kanıtı,
  reconnect soak ve user-data subscription lifecycle dış doğrulama bekliyor.
- Read-only `myTrades` tabanlı ağırlıklı maliyet esası var; 1000 kaydı aşan tam
  pagination ve BNB gibi üçüncü-varlık fee conversion harici fiyat kanıtı bekliyor.
- Rate-limit/time-drift policy var; gerçek WebSocket reconnect, gap backfill ve
  exchange stream state machine henüz yok.
- Wallet reader gerçek uygulama akışına bağlı değil.
- Rebalancing proposal agent yok.
- Market-context registry, health ve provenance wiring var; gerçek macro/news
  provider adaptörü kullanıcı seçimi bekliyor.
- WHALE-FUSION gerçek on-chain/social provider adapter ve OOS promotion kanıtı yok.
  Sağlayıcı envelope/replay admission sınırı tamamdır, ancak gerçek adapter seçimi,
  credential, ham-event persistence ve retention yönetimi bekliyor.
- ADL hesabı private account bağlamı gerektirdiği için public collector'da yok.
- Crew/Local LLM/RAG process planı, stdlib ikinci-beyin index'i, loopback
  llama.cpp advisory runner ve HTML UI artefaktı mevcut; provider yoksa açık
  blocker üretir.
- Gerçek uzun dönem BTCUSDT OOS/paper kanıtı henüz promotion sağlamıyor.
- Deflated Sharpe ve selection-overfit modelleri var; gerçek run-card akışında
  zorunlu promotion gate bağlantısı sonraki validation-pipeline dilimidir.

## Canlı durum

```text
NO_TRADE
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```
