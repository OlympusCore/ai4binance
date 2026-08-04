# Belge Haritası — ELI5

## ELI10

Bu dosya belge dolabinin haritasidir. Hangi konuyu merak ediyorsan hangi belgeye
bakacagini soyler; kalici kurallar `Docs`, gecici operasyon kayitlari `Reports`
altindadir.


Bu klasörün amacı “hangi belgeye bakmalıyım?” sorusunu kolaylaştırmaktır.

1. Yeni başlıyorsanız kökteki `README.md` dosyasını okuyun.
2. Ust ic norm ve anayasal emir kaynagi icin `AI4Binance_OEK.md` okuyun.
3. Parçaların nasıl bağlandığını görmek için `ARCHITECTURE.md` okuyun.
4. Neyin tamamlandığını görmek için `ROADMAP.md` okuyun.
5. Bir iddianın kod kanıtını görmek için `COMPLIANCE_MATRIX.md` okuyun.
6. Holding/Genel Müdür/QAQC sınırı için `HOLDING_GOVERNANCE.md` okuyun.
7. Skill supply-chain ve ajan yetki sınırı için `SKILLS_GOVERNANCE.md` okuyun.
8. Model adaptation ve fine-tuning sınırı için
   `MODEL_ADAPTATION_GOVERNANCE.md` okuyun.
9. Cleanup ve retention kararları için `FOLDER_OWNERSHIP.md` okuyun.
10. Repository cleanup ve stabilite audit runbook'u için
    `REPOSITORY_CLEANUP_AND_STABILITY_AUDIT.md` okuyun.
11. Gecici operasyon planlari, diff planlari, watchlist ve uygulama raporlari
    icin `Reports/operations/` klasorunu kullanin.
12. TradingView bağlantısı için `CODEX_TRADINGVIEW_MCP_ELI5.md` okuyun.
13. Salt okunur Codex/ChatGPT evidence katmanı için `AI4BINANCE_MCP.md` okuyun.
14. `web-socket-api.md`, Binance WebSocket API referans snapshot'ıdır; mevcut
    uygulamanın WebSocket kullandığını kanıtlamaz.

## Tek cümlelik durum

Araştırma ve paper altyapısı çalışıyor; WebSocket/Ed25519, gerçek wallet wiring,
uzun dönem OOS kanıtı ve canlı emir yürütme tamamlanmadığı için canlı işlem kapalıdır.

## OEK Anayasal Kaynak

`AI4Binance_OEK.md` ust ic norm ve `BoardDirective` authority source dosyasidir.
GM prompt-order zinciri `OEK_AUTHORITY_SOURCE:Docs/AI4Binance_OEK.md` ve
`OEK_CONSTITUTION_COMPLIANCE` olmadan directive uretmez. Bu kaynak emir
hiyerarsisini belirler; canli islem, para transferi, secret erisimi, risk
artisi, production deploy veya promotion yetkisini tek basina acmaz.

## Yerel Gizlilik Sınırı

Yerel bilgisayar profili yalnız `Computer.md` içinde tutulur. Diğer Markdown,
kod, test fixture, log veya raporlar bu özel değerleri kopyalamaz; gerektiğinde
sadece `Computer.md` referansı kullanılır.

## Yazılı Onay ve Talimat Senkronu

Kullanıcı sistem düzeltmesi için yazılı onay verdiğinde ilgili `.md` talimatı
aynı bounded diff içinde güncellenebilir. `WRITTEN_APPROVAL_DOC_SYNC` kuralı,
bu güncellemenin yalnız redakte edilmiş sistem kuralı, kapsam sınırı, kalite
kanıtı ve blocker durumunu kaydetmesini ister; `Computer.md` dışına özel
bilgisayar profili veya gizli değer kopyalanmaz.

