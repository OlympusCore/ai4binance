# AI4BINANCE EnterpriseAI vNext

AI4BINANCE, Binance Spot verisini inceleyen, strateji fikirlerini test eden ve
kanıt yetersizse işlem açmayan bir araştırma platformudur. Kâr garantisi vermez.

## ELI5: Sistem ne yapıyor?

Sistemi bir kontrol kulesi gibi düşünün:

1. Binance'ten yalnızca piyasa verisini alır.
2. Verinin bozuk veya eski olup olmadığını kontrol eder.
3. Uzman ajanlar aynı veri fotoğrafını inceler.
4. Strateji motoru yalnızca araştırma adayı oluşturur.
5. Risk motoru eksik kanıtların tamamını blocker olarak yazar.
6. Backtest, walk-forward ve tuning adayı geçmişte sınar.
7. Kanıt yeterli değilse sonuç `NO_TRADE` olur.

```text
Public data -> immutable snapshot -> agents -> candidate -> risk
            -> backtest/walk-forward/tuning -> human review
```

## Bugünkü gerçek durum

| Alan | Durum |
|---|---|
| Python | 3.12.10 |
| Ajan kataloğu | 48 tanım; 34 analiz ajanı |
| Teknik analiz | 10 core, 23 advanced ve 1 trend-events ajanı |
| Strateji | 20 playbook; 10 hesaplama üreten playbook |
| Supertrend | ATR14 + OHLC4 + multiplier 2, research-only |
| Backtest | Olay tabanlı Spot long motoru mevcut |
| Walk-forward/OOS | Kod mevcut; gerçek uzun dönem kanıtı eksik |
| Tuning | Sınırlı ve insan onaylı governance mevcut |
| Araştırma sağlamlığı | Kline/aggTrade revision, scalable integrity, queue-fill replay, SPA/MCS, Monte Carlo ve CPCV mevcut |
| Paper lifecycle | Mevcut; otomatik CLI emri değil |
| Wallet | Salt-okunur HMAC REST adaptörü mevcut, CLI'ye bağlı değil |
| WebSocket/Ed25519 | İmza, `session.logon`, read-only account/orders ve gate-enforced order metotları hazır; gerçek testnet/production oturumu dış yetki bekliyor |
| Canlı emir | Uygulanmadı ve engelli |

Doğrulanmış kalite baz çizgisi:

```text
236 tests passed
coverage 90.36%
Ruff 0
MyPy 0
```

## Kurulum

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Adım adım kullanım

### 1. Önce kaliteyi kontrol et

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  .agents\skills\quality-gate-loop\scripts\invoke_gate.ps1 `
  -RepositoryRoot C:\vscode-projects\ai4binance
```

### 2. Güvenli varsayılan durumu gör

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli status
```

Beklenen güvenli sonuç:

```text
NO_TRADE
LIVE_ORDER_BLOCKED
```

### 3. Ajan kataloğunu gör

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli agents
```

### 3a. QAQC-Agent sürekli iyileştirme raporunu gör

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli qaqc-agent
```

`QAQC-Agent`, 5S, Hoshin Kanri, Kaizen, Six Sigma ve Poka-Yoke üzerinden
rapor-only düzenleme/iyileştirme önerisi üretir; emir veya canlı yetki vermez.

### 4. Public Spot analizi çalıştır

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli analyze-public
```

API anahtarı veya emir yetkisi kullanmaz.

### WHALE-FUSION Faz 1-2-3-4-5-6-7-8

Bu motoru üç ayrı dedektörün ortak veri sözlüğü gibi düşünün. İlk üç faz:

1. Balina, sosyal medya ve türev olaylarının isimlerini ve kaynak kanıtını tanımlar.
2. Binance USD-M public verisinden OI, long/short oranları, funding, taker akışı,
   mark/index farkı, order-book dengesi ve büyük işlemleri okur.
3. OI değişimi, z-score, percentile ve fiyat-OI rejimini deterministik hesaplar.
4. Sağlayıcıdan gelen on-chain transferi doğrular; Binance, DEX, bridge,
   staking, token-unlock, market-maker, stablecoin, yeni cüzdan ve parçalı
   transfer olaylarına ayırır.
5. Allowlist içindeki sosyal hesaplardan gelen canonical postları doğrular;
   kategori, olay, stance, varlık, eskilik, duplicate ve çelişki kontrollerini
   uygular.
6. On-chain, sosyal ve derivatives kanallarını time-decay ve sabit ağırlıklarla
   birleştirir; aynı kanalın tekrarlarını ortalama alır ve çelişki cezası uygular.
7. Fusion sonucunu aynı `snapshot_id` ile immutable market snapshot'a bağlar,
   research-only `whale` ajanına verir ve idempotent JSONL audit'e kaydeder.
8. Application service aynı cycle'daki canonical kanıtları fusion, audit, snapshot,
   orchestrator ve raporlama zincirinden geçirir; güvenli CLI çıktısı üretir.

Bu veri Spot kararına yalnızca yardımcı araştırma kanıtıdır. Tek başına sinyal,
risk onayı veya emir yetkisi üretmez. Faz 4 dış sağlayıcıya bağlanmaz; sağlayıcı
adaptörlerinin kullanacağı güvenli çekirdektir. Faz 5 de gerçek sosyal platforma
bağlanmaz; provider adaptörünün açıkça etiketlediği olayları doğrular. Faz 6 birleşik
skoru üretir ama bu skor final Spot sinyali veya execution izni değildir.

Varsayılan fusion ağırlıkları:

```text
on-chain 40% | social 25% | derivatives 35%
```

En az iki bağımsız kanal yoksa `INDEPENDENT_FUSION_CHANNELS_INSUFFICIENT` döner.
Fusion ajanı yalnız supplementary evidence üretir; confluence, validation ve
`NO_TRADE` güvenlik akışının sahipliğini değiştirmez.

Provider olmadan güvenli Faz 8 smoke komutu:

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli whale-fusion-research
```

Varsayılan boş cycle, nötr skor ve `INDEPENDENT_FUSION_CHANNELS_INSUFFICIENT`
blocker'ıyla `NO_TRADE` döndürür.

### 5. Veriyi arşivle ve doğrula

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli archive-public
.\.venv\Scripts\python.exe -m ai4binance.cli validate-research
```

## Güvenlik kuralları

- Varsayılan mod `paper/manual`dır.
- Spot SELL yalnız mevcut envanteri azaltabilir; naked short yoktur.
- Ajanlar emir gönderemez.
- OOS kanıtı olmayan yöntem hard gate olamaz.
- Private key ve API secret loglanamaz veya Git'e eklenemez.
- `--confirm-live` tek başına hiçbir emri açmaz.

## Belgeler

- [ELI5 belge haritası](Docs/README.md)
- [Mimari](Docs/ARCHITECTURE.md)
- [Yol haritası](Docs/ROADMAP.md)
- [Uyumluluk matrisi](Docs/COMPLIANCE_MATRIX.md)
- [Backtest açıklaması](Backtest/README.md)
- [Secrets güvenliği](Secrets/README.md)

## Canlı uygunluk

```text
execution_allowed=false
LIVE_ORDER_BLOCKED
```
