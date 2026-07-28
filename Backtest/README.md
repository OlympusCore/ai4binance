# Backtest — ELI5

Backtest, “bu fikir geçmişte nasıl davranırdı?” sorusunu sorar. Geleceği bilmez ve
kâr garantisi vermez.

## Motorun kuralları

1. Yalnız kapanmış mumlar stratejiye gösterilir.
2. Sinyal oluştuğu mumdan işlem açılmaz; en erken sonraki mum açılışı kullanılır.
3. Fee ve slippage uygulanır.
4. Stop ve hedef aynı mumda görülürse kötü ihtimal olan stop önce kabul edilir.
5. Trailing stop, mevcut mumun çıkış kontrolünden sonra güncellenir.
6. Veri biterken açık pozisyon muhafazakâr maliyetle kapatılır.
7. Wallet verisi tarihsel backtest'e karıştırılmaz.

## Walk-forward nedir?

Veri sırayla küçük sınavlara bölünür:

```text
train -> hemen arkasındaki OOS test -> sonraki train -> sonraki OOS test
```

Parametre yalnız train bölümünde seçilir. Gelecekteki OOS sonucu seçimi etkileyemez.

## Tuning neden otomatik üretim değildir?

Tuning yalnız izinli ve sınırlı parametreleri dener. En iyi görünen tek noktaya
güvenilmez; komşu parametrelerin de kararlı olması gerekir. Başarılı sonuç en fazla
`STAGED_CANDIDATE` olur ve insan incelemesi ister.

## Çalıştırma

Önce public veriyi arşivleyin:

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli archive-public
.\.venv\Scripts\python.exe -m ai4binance.cli validate-research
```

## Çıktı nasıl okunur?

- Yüksek getiri tek başına yeterli değildir.
- Max drawdown, trade count, OOS fold tutarlılığı ve maliyet stresi birlikte okunur.
- Az işlem veya tek rejimde yoğunlaşan edge blocker üretir.
- Backtest başarısı canlı uygunluk vermez.

```text
BACKTEST_AVAILABLE
REAL_DATA_PROMOTION_EVIDENCE_INCOMPLETE
LIVE_ORDER_BLOCKED
```
