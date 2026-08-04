# Harici Araştırma Kaynak İzleme Listesi

## ELI10

Bu rapor, dis projelerden bakilabilecek fikirlerin izleme listesidir. Listedeki
projeler kurulmus veya guvenilir ilan edilmis degildir; her biri once lisans,
guvenlik ve insan incelemesi ister.


Bu belge, 16 Temmuz 2026 tarihinde yalnızca okunur `git ls-remote` ile alınan
HEAD commit referanslarını kaydeder. Kaynak kodu klonlanmamış, kurulmamış veya
çalıştırılmamıştır. Bu kayıt, `ExternalComponentManifest` değildir: lisans ve
içerik SHA-256 kanıtı, güvenlik taraması, sandbox incelemesi ve insan onayı
tamamlanana kadar her kaynak karantinadadır.

Ortak durum: `DISCOVERED`, `execution_allowed=false`,
`installation_allowed=false`, `LIVE_ORDER_BLOCKED`.

| Kaynak | Sabit commit | Sadece değerlendirilebilecek katkı | Zorunlu blokör |
| --- | --- | --- | --- |
| whittlem/pycryptobot | `1fa9aaef141725623899230daa585e17fa7ba007` | Statik tarayıcı / yapılandırma fikirleri | Kod veya strateji ithali yok |
| sammchardy/python-binance | `7d7b7fb029631db74852b2e84ed237911307495f` | REST/WS sözleşmesi karşılaştırması | Yeni SDK bağımlılığı yok |
| quantopian/zipline | `014f1fc339dc8b7671d29be2d85ce57d3daec343` | Olay-temelli backtest semantiği | Python sürümü/uyumluluk doğrulaması |
| obra/superpowers | `d884ae04edebef577e82ff7c4e143debd0bbec99` | Araştırma iş akışı fikri | Eklenti/skill kurulumu yok |
| ivopetiz/algotrading | `73ce60420bd1266c61ab4d25ae260100bd20e0c7` | Predicate ve olay mimarisi | Look-ahead incelemesi |
| conor19w/Binance-Futures-Trading-Bot | `c7e7f1fa34d5ccf8ef0b686eeb6c01241cdaa4e7` | Futures strateji karşı-örneği | Spot dışı yürütme kesin ret |
| chrisconlan/algorithmic-trading-with-python | `ebe01087c7d9172db72bc3c9adc1eee5e882ac49` | Metrik / maliyet modeli fikri | Zaman serisi OOS yeniden üretimi |
| ZENALC/algobot | `0b54b6012d1377944813a9fca5f24cfcfbca4491` | İnceleme girdisi | Lisans ve Python 3.12 uyumluluğu |
| TauricResearch/TradingAgents | `01477f9afb7a47b849ed4c9259d3a4738d9fda` | Araştırma rol ayrımı | LLM sinyal/risk yetkisi kesin ret |
| Roibal/Cryptocurrency-Trading-Bots-Python-Beginner-Advance | `6cd9f639ac7f9d914d556738ca3aeeef53618146` | Piyasa mikro-yapı araştırması | Arbitraj/yürütme otomasyonu yok |
| PyPatel/Options-Trading-Strategies-in-Python | `c7b8a0de9b7232a1615a02acbed70bf2959fbe44` | Senaryo ve volatilite araştırması | Spot sinyaline doğrudan bağlama yok |
| NousResearch/hermes-agent | `659d1123c49ee6828627d07432ed8cf62578434a` | Araç sınırı / lesson iş akışı | Self-modification ve cron yetkisi yok |
| Hudie/crypto_algo_trading | `88d3f2a6c399cfb6105b9bdb7bcede308d3b4492` | Piyasa-bağlam mimarisi | Futures metrikleri Spot sinyalini yönetemez |
| CyberPunkMetalHead/Binance-News-Sentiment-Bot | `099b2039d51b155473555c3d104a1770024adb69` | Kaynak olay tiplemesi | Haberle otomatik emir kesin ret |
| Open-Trader/opentrader | `8b8e24599599df214b12b4263553885854015b4b` | Karşı-örnek / risk incelemesi | Grid, DCA ve martingale kesin ret |

Bir kaynak ancak şu sıralamayla ilerleyebilir:

1. Lisans dosyasının ve seçilmiş içeriğin SHA-256 kanıtını üret.
2. `ExternalComponentManifest` oluştur; URL, commit ve lisans katalog kaydıyla
   bire bir eşleşsin.
3. Güvenlik taraması, sandbox incelemesi ve açık insan onayını kaydet.
4. `ExternalResearchIntake` ile karantina blokörlerini katalogda koru.
5. Ancak `REPRODUCTION_PENDING` durumunda, salt-izole ve emir yetkisiz deney
   yürüt.

Hiçbir adım canlı işlem yetkisi vermez.

