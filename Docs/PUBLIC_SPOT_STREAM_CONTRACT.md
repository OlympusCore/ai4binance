# Public Binance Spot Stream Contract

## ELI10

Bu belge Binance Spot public veri mesajlarinin nasil kontrol edilecegini anlatir.
Sistem sadece guvenilir, kapanmis ve dogru zaman dilimindeki mumlari kanit sayar;
bu katman API anahtari veya emir kullanmaz.


## Kapsam

Bu dikey dilim yalnız Binance Spot public market-data payload'larını doğrular.
Ağ bağlantısı açmaz, API anahtarı kullanmaz ve order yöntemi içermez.

Desteklenen karar zaman dilimleri:

- `15m`
- `1h`
- `4h`
- `1d`

## Uygulanan sözleşmeler

1. Raw ve combined `kline` payload şekilleri typed modele çevrilir.
2. Symbol, timeframe, zaman sınırları, OHLCV ve trade-ID lineage doğrulanır.
3. Yalnız `x=true` kapalı mum `OHLCVCandle` olabilir.
4. Açık, eski, duplicate veya sequence kanıtı olmayan mum karar dışı kalır.
5. Trade-ID gap ve bounded queue mevcut `PublicStreamRecovery` motoruna bağlanır.
6. `serverShutdown` planlı reconnect durumu üretir.
7. Bağlantı yaşı 23 saat 55 dakikada planlı rollover gerektirir.
8. Subscription sayısı, lowercase kimlik, kontrol mesaj hızı, pong deadline ve
   message byte sınırları açık policy'de korunur.
9. Kabul edilen kapalı mum deterministik `SPOT_KLINE_CLOSED` domain event'ine
   çevrilebilir ve hash-linked journal'a yazılabilir.

## Fail-closed sonuçlar

```text
OPEN_KLINE_NOT_DECISION_ELIGIBLE
DUPLICATE_OR_OLD_CLOSED_KLINE
KLINE_TRADE_SEQUENCE_UNAVAILABLE
STREAM_SEQUENCE_GAP
STREAM_BACKPRESSURE_LIMIT_EXCEEDED
STREAM_SERVER_SHUTDOWN
STREAM_CONNECTION_ROLLOVER_REQUIRED
```

Bu kanıtların hiçbiri execution izni vermez:

```text
execution_allowed=false
LIVE_ORDER_BLOCKED
```

## Bilinçli kapsam dışı

- Gerçek WebSocket network transport.
- Ping/pong frame gönderimi.
- REST snapshot adapter'ının runtime otomasyonu.
- Private user-data stream.
- `executionReport` ve balance reconciliation.
- API key, Ed25519 session veya order endpoint'i.
- `python-binance`, OctoBot veya başka harici runtime bağımlılığı.

## Doğrulama

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_public_spot_stream.py tests\test_connector_stream_readiness.py --no-cov -q
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .agents\skills\quality-gate-loop\scripts\invoke_gate.ps1 -RepositoryRoot .
```

