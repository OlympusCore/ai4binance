# Kaynak Proje Entegrasyonu

Bu çalışma `ai4bspot`, `ai4bfutures` ve `ai4cryptotrade` incelemesinden çıkan
fikirleri AI4BINANCE güvenlik sözleşmesi içinde yeniden uygular. Kaynak depolardan
toplu dosya kopyalanmamıştır.

## Uygulanan katkılar

### ai4bspot

- `exchange/ws_api.py`: Ed25519 canonical signature payload, PEM doğrulama,
  official-host allowlist, bounded unsolicited queue, `session.logon`, read-only
  account/open-orders ve authenticated request çekirdeği.
- `execution/live_spot.py`: `order.test`, `order.place` ve `order.cancel` için
  deterministik iç live gate. Eksik tek bir gate veya farklı preview hash exchange
  çağrısını tamamen engeller.
- `portfolio/cost_basis.py`: signed GET-only `myTrades` üzerinden fee-aware
  weighted-average maliyet ve realized PnL.
- `portfolio/rebalancing.py`: immutable core/strategic/tactical/cash bucket modeli,
  stage/cooldown/hysteresis ve fee-aware proposal-only rebalancing.

### ai4bfutures

- `whale_fusion/derivatives/cross_venue.py`: freshness, sequence, field validity,
  coverage ve venue-concentration gate'li supplementary multi-venue araştırma
  skoru.
- Aynı modülde median/MAD robust normalization. Yetersiz history `None`, sıfır
  dispersion deterministik zero-score üretir.
- Çıktılar sabit `RESEARCH_ONLY`, `execution_allowed=false` ve
  `LIVE_ORDER_BLOCKED` kalır.

### ai4cryptotrade

- Gap/staleness, kill-switch ve rebalancing fikirleri mevcut daha güçlü
  archive/risk-flow/rebalancing test sözleşmelerine karşılaştırma girdisi oldu.
- Live execution, unsigned approval, futures-notional-as-equity, otomatik short,
  güvensiz model loading ve naive walk-forward kodu alınmadı.

## Canlı emir sınırı

Order metotlarının bulunması canlı yetki anlamına gelmez. `GatedSpotOrderExecutor`
her çağrıda mevcut 35 live prerequisite'i yeniden değerlendirir. Place komutu ayrıca
canonical payload SHA-256 preview hash'inin kullanıcı tarafından onaylanan hash ile
birebir eşleşmesini ister ve `order.test` başarılı olmadan `order.place` çağırmaz.

Varsayılan:

```text
trading_mode=paper
order_mode=manual
allow_auto_live_orders=false
LIVE_ORDER_BLOCKED
```

Gerçek testnet veya production emri bu entegrasyon sırasında gönderilmemiştir.

## Kalan dış kanıtlar

- Gerçek Binance Ed25519 testnet kimlik doğrulaması ve reconnect soak.
- 1000'den fazla fill için tam trade-history pagination.
- BNB/üçüncü varlık fee conversion için point-in-time fiyat kaynağı.
- Kalıcı inventory bucket state ve allocation policy OOS doğrulaması.
- Gerçek multi-venue provider adaptörleri ve uzun dönem OOS kanıtı.
