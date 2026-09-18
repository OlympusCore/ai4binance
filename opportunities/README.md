# Kontrollü Fırsatlar — ELI5

Bu klasör yeni fikirlerin karantina alanıdır. Bir makalede veya grafikte güzel
görünen fikir doğrudan strateji ya da emir değildir.

## Session VWAP örneği

Mevcut araştırma kodu:

1. Açıkça verilen seans başlangıcını kullanır.
2. HLC3 fiyatını hacimle ağırlıklandırır.
3. Göreli hacim, yapı ve üst zaman dilimi uyumu arar.
4. Chop ve ATR'ye göre geç kalmış girişi engeller.
5. Envantersiz Spot SELL'i reddeder.

Sonuç her zaman:

```text
promotion_status=RESEARCH_ONLY
execution_allowed=false
```

## Bir fikir nasıl ilerler?

1. Görsel anlatım deterministik kurala çevrilir.
2. Look-ahead testi eklenir.
3. Fee/slippage içeren backtest çalıştırılır.
4. Walk-forward ve ayrı OOS ölçülür.
5. Trend/range/volatilite rejimleri karşılaştırılır.
6. Parametre hassasiyeti incelenir.
7. İnsan promotion ve risk onayı gerekir.

Bu zincirin herhangi bir halkası eksikse fikir araştırma olarak kalır.
