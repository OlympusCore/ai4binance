# Yol Haritası — ELI5

## ELI10

Bu belge yolculuk haritasi gibidir. Hangi parca hazir, hangi parca arastirma
asamasinda, hangi parca guvenlik nedeniyle kapali gorunur; boylece sistemin
nerede oldugu hizlica anlasilir.


İşaretler:

- ✅ Kod ve test mevcut.
- 🟡 Kod var fakat gerçek veri/entegrasyon/promotion kanıtı eksik.
- ⛔ Henüz uygulanmadı veya güvenlik nedeniyle kapalı.

## Faz 0 — Güvenli temel ✅

- Python 3.12.10, typed modeller, immutable snapshot
- `NO_TRADE` ve `LIVE_ORDER_BLOCKED` varsayılanı
- Secret redaction ve append-only audit
- Pytest, Ruff ve MyPy kalite kapısı

## Faz 1 — Spot data ✅ / 🟡

- ✅ Public Spot REST, exchangeInfo, klines, ticker ve book ticker
- ✅ Kapalı mum, freshness ve veri kalite kontrolleri
- ✅ Checksum'lı Parquet arşivi
- ✅ Dört timeframe'ı tek checksum zincirinde mühürleyen dataset revision manifesti
- 🟡 Uzun dönem BTCUSDT validation arşiv derinliği dış veri toplamaya bağlı
- 🟡 Ed25519 imza + `session.logon` + read-only account/orders + gate-enforced
  order request çekirdeği tamam; gerçek testnet auth/reconnect soak bekliyor

## Faz 2 — Analiz ajanları ✅ / 🟡

- ✅ 47 governance tanımı ve 34 analiz ajanı
- ✅ 10 core + 23 advanced + trend-events implementasyonu
- ✅ Supertrend ATR14/OHLC4/multiplier2 ve cross primitive'leri
- ✅ Typed Market Outlook synthesis: multi-TF bias, regime, setup radar,
  high-impact event contract, ATR-buffered levels ve TPO/composite proxy sınırı
- 🟡 Advanced ajanların gerçek OOS/false-positive kanıtı eksik
- 🟡 News/sentiment/derivatives provider'ları bağlı değil
- 🟡 Gerçek TPO auction profile, single prints ve composite balance-area hesabı yok;
  mevcut volume-weighted POC yalnızca research proxy

## Faz 3 — Strateji, risk ve paper ✅ / 🟡

- ✅ 20 playbook registry ve 10 hesaplama üreten playbook
- ✅ Sıkışma, reaksiyon istatistiği, hacimli kırılım ve retest doğrulamalı
  `compression_breakout` research playbook'u
- ✅ Risk, lot/tick/notional, spread/slippage ve Spot inventory kontrolleri
- ✅ Paper lifecycle, staged exit, trailing ve closure review
- ✅ Hash-linked event replay ve partial-fill order state reducer
- ✅ Read-only open-order reconciliation ve proposal-only portfolio risk budget
- 🟡 Read-only wallet adaptörü var fakat CLI/application wiring yok
- ⛔ Rebalancing proposal agent
- ⛔ Gerçek veya otomatik emir adaptörü

## Faz 4 — Backtest ve doğrulama ✅ / 🟡

- ✅ Next-bar-open, fee/slippage, stop-first ve same-bar trailing koruması
- ✅ Opsiyonel candle-volume participation, fiyat etkisi ve partial-entry-fill stress
- ✅ Rolling/anchored walk-forward ve OOS rejim raporu
- ✅ Bounded tuning, sensitivity ve human promotion board
- ✅ Cost stress ve seeded bootstrap
- ✅ OOS güven aralığı, effective sample size, confirmatory etiketi ve
  multiple-testing correction yönetişimi
- ✅ Hash-linked research run card, hypothesis lifecycle ve demotion-only decay
- ✅ Look-ahead, recursive stability ve temporal feature-lineage gate'leri
- ✅ Purge/embargo walk-forward pencereleri
- ✅ CPCV purge/embargo split diagnostic ve mum-yolu Monte Carlo
- ✅ Bounded, artifact-temelli indikatör/strateji integrity kataloğu
- ✅ İzole Optuna benchmark adaptörü; optional paket yoksa fail-closed blocker
- ✅ `aggTrades` revision, mum reconciliation ve trade-flow lineage sözleşmesi
- ✅ Logaritmik checkpoint + bounded refinement integrity taraması
- ✅ Seeded block-bootstrap SPA ve model-confidence-set diagnostic
- ✅ Sequence-aware read-only L2 book çekirdeği ve konservatif queue-fill replay
- ✅ `range_rotation`, `volatility_expansion` ve ölçülebilir liquidity-sweep playbook'ları
- ✅ Cost-basis kâr tabanı ve gerçekleşmiş satıştan türetilen rebuy bandı
- ✅ Multi-symbol korelasyon, HHI ve correlated-exposure diagnostic
- ✅ Deflated Sharpe ve selection-overfit diagnostic sözleşmeleri
- 🟡 Gerçek uzun dönem dataset ve çoklu rejim promotion kanıtı eksik
- 🟡 Multi-symbol korelasyon diagnostic mevcut; gerçek portfolio backtest kanıtı yok

## Faz 5 — Controlled learning 🟡

- ✅ Lesson ve experiment recommendation modelleri
- ✅ Atomik summary ve append-only audit
- 🟡 Validation/paper artifact'larını otomatik toplayan learning loop bağlı değil
- ⛔ Otomatik production activation; bilinçli olarak yasak

## Faz 6 — Knowledge ve sandbox 🟡

- ✅ WHALE-FUSION Faz 1: olay taksonomisi, immutable modeller ve provenance
- ✅ WHALE-FUSION Faz 2: public Binance USD-M OI/ratio/funding/taker/
  mark-index/depth/aggregate-trade collector ve liquidation parser
- ✅ WHALE-FUSION Faz 3: OI feature engine ve dört fiyat-OI rejimi
- ✅ WHALE-FUSION Faz 4: canonical on-chain normalizer, wallet-label registry,
  whale-event classifier ve split-transfer detector
- ✅ WHALE-FUSION Faz 5: social account registry, canonical post normalizer,
  freshness/confidence/dedup kontrolleri ve contradiction detector
- ✅ WHALE-FUSION Faz 6: üç kanallı fusion score, time-decay, channel-average,
  minimum bağımsız kanal ve contradiction penalty
- ✅ WHALE-FUSION Faz 7: snapshot envelope, advisory whale agent, orchestrator
  wiring ve restart-idempotent JSONL audit
- ✅ WHALE-FUSION Faz 8: application assembly service, audit-failure blocker ve
  `whale-fusion-research` güvenli CLI komutu
- 🟡 Futures verisi yalnız supplementary `RESEARCH_ONLY` kanıttır
- 🟡 On-chain çekirdek hazır; gerçek indexer/provider adapter henüz bağlı değil
- 🟡 Social çekirdek hazır; gerçek X/Telegram/provider adapter henüz bağlı değil
- 🟡 Fusion score orchestrator'a bağlı fakat yalnız `RESEARCH_ONLY`; OOS validation
  ve promotion kanıtı bekliyor
- 🟡 CLI canonical/boş cycle çalıştırır; gerçek provider ingestion henüz bağlı değil
- ⛔ ADL private account metriği ve sürekli WebSocket connection manager
- ✅ Explicit market-context provider registry, health isolation, HTTPS host
  allowlist, content hash ve ResearchApplication wiring
- 🟡 Gerçek macro/news provider seçimi ve adapter'ı dış entegrasyon bekliyor
- ✅ Crew/Local LLM/RAG process planı typed, loopback-only ve fail-closed
- ✅ Stdlib second-brain RAG index, loopback llama.cpp advisory runner ve HTML UI
- 🟡 Provider-backed sürekli runner, eval harness ve zengin UI
- Opsiyonel FAISS adapter
- ✅ AST allowlist, kaynak limitleri ve fail-closed sandbox backend capability gate
- 🟡 Gerçek ağ-kapalı Docker/OS sandbox backend'i henüz bağlı değil
- ✅ Opsiyonel security-scanner/SARIF adapter sözleşmesi; scanner yoksa bloke
- ✅ Advisory Agent v2 evidence packet, citation, role-conflict ve checkpoint sınırı
- ✅ Exchange request-weight ve server-time drift gate'i
- 🟡 WebSocket reconnect/gap-backfill runtime ve CCXT read-only conformance adapter'ı yok

## Faz 7 — Canlı uygunluk ⛔

Canlı işlem ancak bütün teknik kanıtlar ve açık kullanıcı yetkisi tamamlandıktan
sonra ayrı bir proje fazında değerlendirilebilir. Bugün:

```text
execution_allowed=false
LIVE_ORDER_BLOCKED
```

## Önerilen sonraki sıra

1. Development run card persistence'ını append-only audit'e bağla ve CI'da zorunlu kıl.
2. Governed lesson approval/expiry kayıtlarını `ControlledLearningLoop` store'una bağla.
3. Capability admission'ı Nightly Quality Triage runner girişinde zorunlu kıl.
4. Advisory fixture runner'ı redacted provider testleriyle besle; promotion kanıtı sayma.
5. Kalıcı event journal ve stream recovery çekirdeğini application startup'a bağla.
6. Gerçek public WebSocket adapter'ını sequence-gap/backfill sözleşmesiyle ekle.
7. Harici araştırma adaylarını pinned revision ile reproduce edip performans kapısından geçir.
8. Mühürlü BTCUSDT dataset revision ile purge/embargo OOS kanıtı üret.
9. En son, ayrı onayla izole Langflow pilotu ve gerçek Ed25519 testnet oturumunu
   doğrula; production yetkisini ayrı tut.

