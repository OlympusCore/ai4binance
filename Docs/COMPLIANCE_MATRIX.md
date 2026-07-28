# Uyumluluk Matrisi — ELI5

Son denetim: **2026-07-14**

Bu belge “dosya var mı?” değil, “kod var mı, test var mı, gerçek akışa bağlı mı
ve gerekli dış kanıt mevcut mu?” sorularını ayrı ayrı değerlendirir.

## Durum anahtarı

- **TAMAM**: Kod, test ve gerekli application bağlantısı mevcut.
- **KISMİ**: Güvenli temel mevcut; provider, gerçek veri kanıtı veya uçtan uca bağlantı eksik.
- **ARAŞTIRMA**: Hesaplama mevcut fakat OOS/promotion kanıtı yok.
- **YOK**: Özellik uygulanmamış veya güvenlik nedeniyle bilinçli kapalı.

## Güncel platform matrisi

| Yetenek | Kod ve test kanıtı | Durum | Kalan engel |
|---|---|---|---|
| Güvenli Spot varsayılanları | `config.py`, `safety.py`, `test_config_reporting.py`, `test_safety.py` | TAMAM | Live bilinçli kapalı |
| Immutable snapshot ve ortak agent sözleşmesi | `schemas.py`, `test_schemas.py` | TAMAM | — |
| Dependency-aware paralel orchestrator | `agents/orchestrator.py`, `agents/telemetry.py`, ilgili testler | TAMAM | Hard process-timeout yalnız izole backend ile mümkün |
| Agent governance registry | `agents/catalog.py`, `agents/registry.py`, `test_agent_registry.py` | TAMAM | Hard-gate promotion kanıtı yok |
| Agentic workflow pattern catalog | `governance/agentic_patterns.py`, `.agents/skills/agentic-workflow-patterns`, `test_agentic_patterns.py` | TAMAM | Pattern seçimi ve plan kontratı var; autonomous/live execution yok |
| Public Spot REST acquisition | `exchange/client.py`, `data/acquisition.py`, ilgili testler | TAMAM | WebSocket streaming değil |
| Binance Vision historical ingestion | `data/binance_vision.py`, `test_binance_vision.py` | TAMAM | Uzun dönem dataset'in gerçekten indirilmesi operatör işi |
| Binance Vision bütünlük/güvenlik | SHA-256, host allowlist, HTTPS, bounded response | TAMAM | Upstream erişilebilirliği dış bağımlılık |
| Read-only private account reader | `exchange/private.py`, `portfolio/wallet.py`, `application/runtime.py` | TAMAM | `Secrets/bnc.env` allowlist loader, dar ACL ve gerçek Spot/USD-M GET smoke kanıtı mevcut; write yetkisi yok |
| Spot inventory ve SELL semantiği | `domain.py`, `risk.py`, wallet capture testleri | KISMİ | Gerçek hesapla açık-order reconciliation kanıtı gerekli |
| Rebalancing proposal agent | — | YOK | Wallet, hedef allocation ve insan onay workflow'u gerekli |
| Core teknik göstergeler | `indicators.py`, `agents/technical.py`, ilgili testler | ARAŞTIRMA | Çok-rejim OOS promotion gerekli |
| Market Outlook Intelligent Engine | `outlook/`, `application/research.py`, `test_market_outlook.py` | KISMİ | Gerçek macro calendar/news provider ve tam TPO/composite auction profile gerekli |
| Advanced teknik agentlar | `agents/advanced.py`, `test_advanced_agents.py` | ARAŞTIRMA | Bazıları proxy/diagnostic; contextual statistics eksik |
| Trend events ve cross yönetimi | `agents/trend_events.py`, `test_trend_events_agent.py` | ARAŞTIRMA | OOS promotion gerekli |
| PriceAction SUCCESS/PARTIAL sözleşmesi | `schemas.py`, `strategies/price_action.py`, orchestrator entegrasyon testi | TAMAM | Setup edge kanıtı ayrıca gerekli |
| Strategy registry | `strategies/registry.py`, `strategies/compression.py`, `strategies/regime_playbooks.py` | KISMİ | 10/20 playbook hesaplama üretir; yeni adaylar OOS bekler |
| Candidate arbitration | `strategies/arbitration.py`, `test_stage_governance.py` | TAMAM | Portfolio çapında korelasyon optimizasyonu yok |
| WHALE-FUSION | `whale_fusion/`, application ve entegrasyon testleri | ARAŞTIRMA | Provider envelope/replay provenance-freshness-finality kapısı var; gerçek provider ve OOS kanıtı eksik |
| WHALE-FUSION → Strategy etkileşimi | bounded supplementary ±5 modifier, `test_stage_governance.py` | TAMAM | Tek başına trigger/hard-gate olamaz |
| Confluence correlation governance | `agents/specialists.py`, `test_agents.py` | TAMAM | OOS ağırlık kalibrasyonu eksik |
| RiskEngine ve Binance filtreleri | `risk.py`, `exchange/filters.py` | TAMAM | Gerçek wallet context olmadan onay vermez |
| İlk 5 aday risk değerlendirmesi | `RiskEngine.evaluate_many`, RiskAgent metadata testleri | TAMAM | Toplam portfolio risk dağıtımı kısmi |
| Paper execution ve lifecycle | `execution/`, paper/lifecycle testleri | TAMAM | Exchange-benzeri kalıcı order state machine kısmi |
| Backtest gerçekçilik kontrolleri | `backtest/`, realism ve robustness testleri | TAMAM | Gerçek uzun dönem BTCUSDT validation raporu repository'de yok |
| Look-ahead / recursive / lineage integrity | `validation/integrity.py`, `test_validation_integrity.py` | TAMAM | Gerçek artifact akışında her feature ailesi için çalıştırılmalı |
| Walk-forward ve OOS | `validation/`, statistical evidence, `test_walk_forward.py` | TAMAM | Gerçek multi-regime promotion artifact'ı yok |
| Purge/embargo ve overfit statistics | `validation/overfit.py`, walk-forward config, ilgili testler | TAMAM | Promotion pipeline zorunlu bağlantısı ve gerçek veri kanıtı gerekli |
| Tuning ve sensitivity | `tuning/`, tuning governance testleri | TAMAM | Dataset revision mevcut; Optuna yalnız optional izole benchmark ve promotion yetkisiz |
| Promotion Board → Strategy Registry | `tuning/promotion.py`, `test_tuning_governance.py` | TAMAM | Yalnız PAPER_APPROVED; live yetkisi yok |
| Controlled learning engine | `learning/`, wallet-learning testleri | TAMAM | Üretim parametresini değiştiremez |
| Learning application wiring | `application/learning_loop.py`, `application/research.py` | TAMAM | Varsayılan kapalı; açıkça configure edilmelidir |
| Append-only audit ve secret redaction | `storage/jsonl.py`, storage/security testleri | TAMAM | Merkezi retention/rotation politikası yok |
| Deterministik event/order replay | `events/journal.py`, `execution/order_state.py`, `test_event_journal.py` | KISMİ | Kalıcı journal/restart replay hazır; application startup wiring'i yok |
| Connector readiness | `exchange/readiness.py`, runtime smoke kanıtı, `test_connector_stream_readiness.py` | KISMİ | Gerçek private GET bağlantısı doğrulandı; sürekli WebSocket/session lifecycle yok |
| Public stream recovery | `exchange/stream_state.py`, `exchange/public_stream.py`, ilgili testler | KISMİ | Resmî kline/parser/lifecycle contract hazır; gerçek WebSocket/REST runtime adapter'ı yok |
| Paper restart reconciliation | `execution/recovery.py`, `test_paper_recovery_risk_flow.py` | KISMİ | Journal recovery hazır; gerçek exchange snapshot provider'ı bağlanmadı |
| Risk-flow circuit breakers | `portfolio/risk_flow.py`, ilgili testler | TAMAM | Proposal-only; live yetkisi vermez |
| Governed research radar | `research_catalog.py`, `test_research_catalog.py` | TAMAM | Dış adayların revision/license/reproduction kanıtı ayrıca üretilmeli |
| External skill supply-chain gate | `governance/supply_chain.py`, governance testleri | TAMAM | Her gerçek aday için pinned commit/hash/lisans taraması ayrıca gerekli |
| Development assurance run card | `governance/development.py`, governance testleri | KISMİ | Sözleşme hazır; bütün geliştirme akışlarında zorunlu persistence bağlantısı yok |
| Governed lesson lifecycle | `learning/governance.py`, runtime governance testleri | KISMİ | Summary staging hazır; kalıcı approval/expiry worker'ı bağlı değil |
| Capability-bounded jobs | `ops/jobs.py`, nightly manifest ve admission testleri | KISMİ | Admission hazır; bütün unattended runner'lara zorunlu bağlanmadı |
| Advisory fixture evaluation | `agents/evaluation.py`, runtime governance testleri | KISMİ | Deterministik grader hazır; provider-backed fixture runner bağlı değil |
| Read-only Market Outlook DAG | `governance/workflow.py`, runtime governance testleri | TAMAM | Görselleştirme UI'ı yok; graph işlem yetkisi vermez |
| Visual sidecar security gate | `governance/sidecar.py`, runtime governance testleri | TAMAM | Langflow kurulmadı/başlatılmadı; ayrı açık yetki ve pinned image gerekir |
| Performans regresyon kapısı | `ops/performance.py`, `test_performance_guard.py` | TAMAM | Yalnız aynı ortam ölçümlerini kıyaslar; harici teknoloji benchmark'ları bekliyor |
| Exchange resilience gate | `exchange/resilience.py`, ilgili testler | TAMAM | Sürekli WebSocket runtime yok |
| Open-order reconciliation | `portfolio/reconciliation.py`, ilgili testler | KISMİ | Gerçek exchange order snapshot wiring'i gerekli |
| Portfolio risk budget | `portfolio/risk_budget.py`, `portfolio/rebalancing.py`, `portfolio/correlation.py`, ilgili testler | KISMİ | Korelasyon/HHI diagnostic hazır; gerçek bucket-state persistence ve multi-symbol portfolio backtest kanıtı yok |
| Advisory Agent v2 | `agents/advisory.py`, `test_advisory_v2.py` | TAMAM | Provider/LLM çağrısı bilinçli olarak ayrı; signal/execution yetkisi yok |
| Research run card / hypothesis / decay | `research_governance.py`, ilgili testler | TAMAM | Gerçek uzun dönem artifact akışında operatör kullanımı gerekli |
| News/context provider ingestion | `market_context.py`, application wiring, ilgili testler | KISMİ | Gerçek provider seçimi/adapter'ı ve freshness SLA gerekli |
| Crew/Local LLM/RAG process planı | `governance/crew.py`, `rag.py`, ilgili testler | KISMİ | Stdlib index, loopback provider runner ve HTML UI mevcut; sürekli worker/eval harness yok |
| Experiment sandbox | `sandbox.py`, AST ve backend capability testleri | KISMİ | Gerçek Docker/OS izolasyon backend'i gerekli |
| Opsiyonel security scan | `security_scan.py`, evidence-first adapter testleri | KISMİ | Pinned Strix kurulumu ve ayrı yetkili CI job yok |
| Ed25519 WebSocket `session.logon` | `exchange/ws_api.py`, `execution/live_spot.py`, `test_ed25519_ws_live.py` | KISMİ | İmza/session/read/order metotları hazır; gerçek testnet auth, reconnect soak ve subscription lifecycle eksik |
| Live Spot order adapter | write adapter yok | YOK | Açık kullanıcı talebi dahil bütün live-gate kanıtları gerekli |

## İki geçmiş çalışmanın güncel karşılaştırması

### İlk kalite/Spot-native çalışmasından kalanlar

- Python 3.12.10, Ruff, MyPy, Pytest ve güvenli Spot varsayılanları korunuyor.
- Bağımlılıkların tek kaynağı `pyproject.toml`; `requirements.txt` editable extras
  yönlendirmesi olarak kalıyor.
- Futures verisi yalnız WHALE-FUSION supplementary araştırma kanalında bulunuyor;
  Spot order semantiğini yönetmiyor.
- Eski “127 test ve düşük coverage” sonucu güncel değildir.

### Kademeli performans/stabilite çalışmasından sonra kapanan boşluklar

- Immutable snapshot, ortak `AgentResult`, fail-closed live gate, public data,
  teknik agentlar, candidate/risk, paper lifecycle, backtest, walk-forward,
  tuning, promotion, WHALE-FUSION ve controlled-learning bileşenleri eklendi.
- Candidate arbitration, PriceAction `SUCCESS/PARTIAL` kabulü, ilk 5 aday risk
  değerlendirmesi ve Promotion Board/Strategy Registry bağlantısı uygulanmıştır.
- Kalite betiği fail-fast çalışır; format, lint, type, test ve Bandit kapıları vardır.
- Kalıcı event journal, stream gap/backfill state machine, paper restart recovery,
  risk-flow circuit breaker, yönetişimli research radar ve ortam-bağlı performans
  regresyon kapısı eklendi.

## Bilinçli olarak tamamlanmayan büyük işler

1. Ed25519 Spot WebSocket gerçek testnet auth, reconnect soak ve subscription lifecycle kanıtı.
2. Gerçek provider'lı on-chain, sosyal, news ve liquidation stream ingestion.
3. Hesap-geneli Spot/Futures envanter, pozisyon ve açık-emir reconciliation raporu.
4. Proposal-only rebalancing için kalıcı bucket-state ve OOS-governed allocation policy.
5. RAG/CAG/FAISS knowledge governance ve gerçek Docker/OS experiment sandbox backend'i.
6. Uzun dönem gerçek BTCUSDT verisiyle multi-regime OOS promotion kanıtı.
7. Live Spot order adapterı ve eksiksiz live eligibility kanıtı.

Bu maddeler küçük yamalar değildir. Dış servis, kullanıcı yetkisi, veri seti veya
ayrı güvenlik tasarımı gerektirir; varmış gibi işaretlenmemelidir.

## Son doğrulama özeti

```text
Python: 3.12.10
Pytest: 491 passed
Branch coverage: 90.63%
Ruff format/lint: passed
MyPy strict: passed
Bandit: passed
Candidate arbitration 100k: 0.278356 s
Agent orchestrator 100-cycle mean: 5.024 ms/cycle
Agent orchestrator 100-cycle p95: 6.584 ms/cycle
```

Benchmark değerleri aynı makinedeki kısa yerel ölçümdür; donanımlar arasında
performans garantisi değildir.

## Değişmeyen güvenlik sonucu

```text
NO_TRADE when evidence is weak
RESEARCH_ONLY when OOS is incomplete
LIVE_ORDER_BLOCKED when any live gate is missing
```

## Operasyonel kalite döngüsü

Nightly Quality Triage; Ruff format/lint, MyPy, Pytest/coverage ve Bandit
kapılarını bağımsız çalıştırır. Tek çalışma lock'u, komut/job timeout'u,
bounded-secret-redacted çıktı, atomik `state.json` ve append-only `runs.jsonl`
kanıtı uygulanmıştır. GitHub Actions izni yalnız `contents: read` olup otomatik
fix, commit, push, merge, deploy, trading veya parameter promotion yetkisi yoktur.

Kanıt: `src/ai4binance/ops/quality_triage.py`,
`tests/test_quality_triage.py`, `.github/workflows/nightly-quality-triage.yml`.

## Öncelikli güçlendirme dilimi A-G

Uygulanan güvenli dikey dilimler:

1. Append-only disk event journal, checkpoint doğrulama ve restart replay.
2. Public/private connector readiness kanıt ayrımı.
3. Sequence-gap, backpressure, staleness ve REST backfill stream state machine.
4. Paper order restart recovery, pending-cancel ve bilinmeyen emir karantinası.
5. Teklif-hızı, aktif emir, turnover, ret serisi ve cooldown risk-flow kapıları.
6. Revision/license/hypothesis/OOS aşamalı, kurulum yetkisiz research radar.
7. Aynı ortama bağlı benchmark kanıtı ve fail-closed performans regresyon kapısı.

Bu dilimler test edilmiş altyapıdır. Gerçek provider/socket bağlantısı, harici
adayların reproduction koşuları ve canlı işlem yetkisi kapsam dışı kalmıştır.

## Agent yönetişimi güçlendirme dilimi H-M

1. Dış skill/plugin için pinned commit, SHA-256, lisans ve capability karantina kapısı.
2. Spec → red test → minimal implementation → iki inceleme → kalite kapısı run card'ı.
3. Deduplication, contradiction, validation, insan onayı ve expiry lesson lifecycle'ı.
4. Nightly işler için path/capability/lock/timeout kanıtlı admission manifesti.
5. Advisory trace için redacted hash, citation, blocker ve latency fixture grader'ı.
6. Market Outlook için canlı yetkisiz typed DAG ve görsel sidecar default-deny kapısı.

Langflow, Hermes veya başka bir harici agent runtime'ı kurulmamış ve başlatılmamıştır.
Sidecar ancak pinned image, localhost, auth, SSRF, ağ-kapalı çalışma, read-only
artifact, resource limit ve secrets/exchange-adapter yokluğu kanıtlanırsa pilot
değerlendirmesine geçebilir.

## Read-only Evidence MCP güçlendirme dilimi

1. Market Outlook, araştırma çalışmasından sonra atomik `state.json` olarak
   yayımlanır; execution yetkisi taşıyan outlook reddedilir.
2. Quality Triage ve Market Outlook yalnız sabit allowlist yollarından okunur.
3. Boyut, JSON şekli, zorunlu alanlar, timezone, freshness, SHA-256 ve blocker
   sınırları fail-closed doğrulanır.
4. Secret-benzeri alanlar MCP cevabından önce redakte edilir.
5. MCP SDK çekirdek bağımlılık değildir; `mcp>=1.27,<2` opsiyonel extra olarak
   sınırlandırılmıştır.
6. Codex/ChatGPT kaydı otomatik yapılmaz. HTTP, OAuth, credential, wallet ve order
   araçları bu dikey dilimin kapsamı dışındadır.

Kanıt: `src/ai4binance/mcp/`, `src/ai4binance/outlook/storage.py`,
`tests/test_mcp_evidence.py`, `tests/test_mcp_server.py`,
`tests/test_research_application.py`, `Docs/AI4BINANCE_MCP.md`.

## Evidence-Backed X Draft Queue güçlendirme dilimi

1. `EvidenceGateway` çıktısı doğrudan deterministik `ContentDraftEngine` girişidir.
2. Yalnız fresh, read-only ve live-blocked Market Outlook kanıtı kabul edilir.
3. Kaynak SHA-256, timestamp, artefakt yolu ve alan-bazlı claim bağları saklanır.
4. 280 karakter, disclaimer, kâr vaadi, dış link, mention ve secret-benzeri metin
   kontrolleri fail-closed çalışır.
5. Taslaklar yerel append-only kuyruğa idempotent eklenir; approval/reject/expiry
   geçişleri immutable audit olayıdır.
6. X API/OAuth/credential, ağ çağrısı ve publishing adapter'ı yoktur. Yerel
   `APPROVED` durumu yayın yetkisi vermez.

Durum: **P0 TAMAM**, **P2 bu dikey dilim için TAMAM**; P1/P3/P5 henüz **YOK**.

Kanıt: `src/ai4binance/content/`, `tests/test_content_draft_queue.py`,
`Docs/EVIDENCE_BACKED_X_DRAFT_QUEUE.md`.

## Explicit social publishing gateway

1. X, Telegram ve LinkedIn text request adapter'ları resmi endpoint sözleşmelerine
   göre uygulanmıştır.
2. Platform allowlist'i default-deny; credential'lar yalnız environment üzerinden
   okunur ve audit artefaktına yazılmaz.
3. Exact approved-draft eşleşmesi ve platform/draft bazlı açık kullanıcı confirmation
   zorunludur.
4. Durable intent-before-send, tek deneme, idempotency, freshness, rate-limit ve
   append-only outcome audit kapıları uygulanmıştır.
5. Provider başarısı yalnız HTTP durumu ve doğrulanmış remote post/message ID ile
   kabul edilir.
6. Otomatik yayın, retry, medya, thread/reply, delete/edit ve OAuth login akışı
   kapsam dışıdır.

Durum: **P4 KISMİ**. Kod ve deterministik testler tamamdır; gerçek X/Telegram/LinkedIn
credential, scope/rol, hesap ve provider erişim kanıtı bulunmadığı için gerçek yayın
hazırlığı `EXTERNAL_AUTH_BLOCKED` kalır.

Kanıt: `src/ai4binance/content/publishing*.py`,
`tests/test_social_publishing.py`, `Docs/SOCIAL_PUBLISHING_GATEWAY.md`.

## OpenBB / Freqtrade esinli validation ve provider yönetişimi

1. Look-ahead ve recursive-stability kontrolleri tek bir fail-closed gösterge
   bütünlüğü promotion raporunda birleştirildi.
2. Birleşik rapor yalnız promotion kanıtı üretir; execution veya live-order
   yetkisi veremez.
3. Market-context sağlayıcıları revision, lisans kimliği, host/kategori allowlist'i
   ve azami veri yaşı bildirmek zorundadır.
4. Bayat, gelecek zamanlı, değiştirilmiş, istenmemiş kategorili veya allowlist dışı
   kanıt event'i reddedilir ve açık blocker üretir.
5. Provider provenance Market Outlook haber snapshot'ında korunur.
6. OpenBB/Freqtrade paketi kurulmamış, kaynak kodu kopyalanmamış ve lisans sınırı
   genişletilmemiştir.

Durum: yerel contract ve deterministik testler **TAMAM**; tüm gerçek gösterge
ailelerinde artifact-temelli batch çalışma **KISMI**; gerçek harici provider
adaptörü `EXTERNAL_PROVIDER_BLOCKED`; promotion `RESEARCH_ONLY`; live işlem
`LIVE_ORDER_BLOCKED`.

Kanıt: `src/ai4binance/validation/integrity.py`,
`src/ai4binance/market_context.py`, `tests/test_validation_integrity.py`,
`tests/test_governed_extensions.py`, `Docs/OPENBB_FREQTRADE_STRENGTHENING.md`.

## Resmî Binance Public Spot Stream contract

1. Raw/combined kline ve `serverShutdown` payload'ları bounded, typed ve
   fail-closed doğrulanır.
2. Yalnız `15m`, `1h`, `4h`, `1d` ve yalnız kapalı mumlar karar kanıtı olabilir.
3. Trade-ID continuity mevcut gap/backfill state machine'e bağlanmıştır.
4. Duplicate/eski/açık/sequence kanıtsız mumlar açık blocker üretir.
5. 23 saat 55 dakika planlı rollover, server shutdown ve bounded subscription
   policy sözleşmeleri uygulanmıştır.
6. Kapalı mum hash-linked `SPOT_KLINE_CLOSED` journal event'ine dönüşebilir.

Durum: payload, lifecycle ve journal contract'ları **TAMAM**; gerçek WebSocket
transport ve REST backfill runtime wiring'i **KISMİ**; private user-data
`EXTERNAL_AUTH_BLOCKED`; live işlem `LIVE_ORDER_BLOCKED`.

Kanıt: `src/ai4binance/exchange/public_stream.py`,
`src/ai4binance/exchange/stream_state.py`, `tests/test_public_spot_stream.py`,
`tests/test_connector_stream_readiness.py`, `Docs/PUBLIC_SPOT_STREAM_CONTRACT.md`.

## Wallet-first resident runtime ve voice security boundary

1. Spot ve USD-M Futures private reader'ları yalnız resmi host ve sabit signed-GET
   allowlist'i kullanır; order veya withdraw endpoint'i içermez.
2. `ReadOnlyRuntimeCycle` wallet kontrollerini public market acquisition'dan önce
   çalıştırır. Eksik wallet kontrolü iki marketi de `NO_TRADE` ve `DEGRADED`
   durumda bırakır.
3. Spot ve Futures advisory durumları ayrıdır. Futures yön bağlamı public
   derivatives kanıtından gelir fakat OOS eksikliği nedeniyle `RESEARCH_ONLY`
   ve `FUTURES_OOS_NOT_APPROVED` kalır.
4. Resident supervisor tek-instance lock, stale-PID recovery, atomik ve bakiye
   içermeyen state dosyası ve Windows Logon Task kurulum scripti sağlar.
5. Voice gateway yalnız speaker + liveness doğrulaması ve exact-match salt-okunur
   intent kabul eder. Voice hiçbir koşulda execution yetkisi üretemez.
6. Gerçek mikrofon/ASR/wake-word/speaker enrollment bağımlılıkları ve kullanıcı
   ses kaydı bulunmadığından owner-only audio runtime `EXTERNAL_SETUP_BLOCKED`.

Durum: resident wallet-first runtime ve Windows startup **TAMAM**; gerçek credential
ile dual-market smoke **EXTERNAL_AUTH_BLOCKED**; voice security contract **TAMAM**;
mikrofonlu owner-only voice runtime **EXTERNAL_SETUP_BLOCKED**; live işlem
`LIVE_ORDER_BLOCKED`.

Kanıt: `src/ai4binance/application/runtime.py`,
`src/ai4binance/portfolio/futures.py`, `src/ai4binance/ops/runtime.py`,
`src/ai4binance/voice/`, `tests/test_runtime_cycle.py`,
`tests/test_runtime_supervisor.py`, `tests/test_voice_gateway.py`,
`Scripts/install_startup_task.ps1`, `Docs/READ_ONLY_RUNTIME.md`.

## Investment Management Assistant

1. Spot ve USD-M Futures açık emir payload'ları order kimliği, side, type, status,
   price, original/executed/remaining quantity alanlarıyla fail-closed normalize edilir.
2. Mevcut Spot envanteri, Futures LONG/SHORT pozisyonları, açık emirler ve yeni setup
   radarları aynı wallet-first çevrimde değerlendirilir.
3. Yalnız `HOLD_REVIEW`, `REDUCE_RISK_REVIEW`, `OPEN_ORDER_REVIEW`, `WATCHLIST` ve
   `NO_ACTION` etiketleri üretilebilir.
4. Öneri etiketi order create/cancel, position close, risk değişikliği veya live-mode
   yetkisi değildir; `execution_allowed=false` ve `LIVE_ORDER_BLOCKED` sabittir.
5. Wallet veya Futures account snapshot yoksa yönetim raporu öneri üretmeden açık
   blocker döndürür.

Durum: typed yönetim motoru ve resident runtime bağlantısı **TAMAM**; gerçek wallet
önerileri `EXTERNAL_AUTH_BLOCKED`; otomatik portfolio mutation **YOK** ve bilinçli
olarak kapsam dışıdır.

Kanıt: `src/ai4binance/portfolio/orders.py`,
`src/ai4binance/portfolio/investment.py`, `src/ai4binance/application/runtime.py`,
`tests/test_investment_management.py`, `tests/test_runtime_cycle.py`.
