# AI4Binance Reports

## ELI10

Bu klasor, bitmis veya tarihli calisma notlarinin kutusudur. Kalici kurallar
`Docs` icinde kalir; diff plani, uygulama raporu, watchlist ve gecici operasyon
kaydi burada saklanir.


Bu klasor gecici operasyon planlari, uygulama raporlari, tarihli izleme
kayitlari ve kanit odakli calisma notlari icindir.

Kalici talimat, anayasa, mimari, sozlesme ve kullanici dokumantasyonu
`Docs/` altinda kalir. Bir belge yeni komut, governance kurali, API sozlesmesi
veya kalici isleyis talimati tanimliyor ise `Docs/`; tarihli bir uygulama
plani, triage kaydi, watchlist, diff plan veya tamamlanmis calisma sonucu
kaydediyor ise `Reports/operations/` altinda tutulur.

Varsayilan guvenlik siniri tum raporlar icin aynidir:

- `execution_allowed=false`
- `promotion_status=RESEARCH_ONLY`
- `live_eligibility_status=LIVE_ORDER_BLOCKED`

