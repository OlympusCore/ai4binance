# OpenBB ve Freqtrade Esinli Güçlendirme

## ELI10

Bu rapor, OpenBB ve Freqtrade gibi olgun projelerden alinan tasarim fikirlerinin
AI4BINANCE'e nasil guvenli uyarlandigini anlatir. Harici paket kurmadan, kod
kopyalamadan ve islem yetkisi genisletmeden ders alma hedeflenir.


## Amaç

Bu dilim, iki olgun projenin faydalı tasarım ilkelerini AI4BINANCE'ın mevcut
validation-first mimarisine bağımsız olarak uygular. Harici paket kurulmaz, kaynak
kod kopyalanmaz ve işlem yetkisi genişletilmez.

## Freqtrade eşlemesi: gösterge bütünlüğü

`validation/integrity.py` içindeki `analyze_indicator_integrity` tek bir
deterministik raporda iki bağımsız kontrol çalıştırır:

1. Batch ve tarihsel prefix sonuçlarını karşılaştırarak look-ahead sapmasını arar.
2. Farklı başlangıç/warmup noktalarındaki son değerleri karşılaştırarak recursive
   kararsızlığı arar.

Herhangi bir bileşen bloklanırsa birleşik raporun `promotion_allowed` alanı
`False` olur. Rapor hiçbir koşulda execution veya live-order yetkisi vermez.

## OpenBB eşlemesi: sağlayıcı yönetişimi

Her read-only market-context sağlayıcısı aşağıdaki kanıtları açıkça bildirir:

- sabit sağlayıcı kimliği ve revision;
- veri kullanım lisans kimliği;
- kategori ve HTTPS host allowlist'i;
- izin verilen azami event yaşı;
- official-source ve credential gereksinimi bilgisi.

Registry; sağlayıcı kimliği, kaynak hostu, izin verilen ve gerçekten istenen
kategori, retrieval zamanı, freshness ve içerik SHA-256 değerini doğrular. Başarısız
kanıt event listesinden çıkarılır ve açık blocker olarak saklanır. Provider
provenance bilgisi Market Outlook haber snapshot'ına eklenir.

## Lisans ve bağımlılık sınırı

- OpenBB AGPL-3.0 ve Freqtrade GPL-3.0 kodu bu repoya kopyalanmamıştır.
- Bu dilim iki projeyi runtime bağımlılığı yapmaz.
- Gerçek OpenBB/provider adaptörü, veri seti, tarih aralığı, kullanım şartları,
  rate-limit ve credential kararı verilmeden tamamlanmış sayılmaz.
- Harici bağlayıcı yoksa mevcut sistem deterministik araştırma akışını sürdürür;
  harici provider readiness iddiasında bulunmaz.

## Doğrulama

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_validation_integrity.py tests\test_governed_extensions.py --no-cov -q
.\Scripts\quality.ps1
```

## Durum

- Yerel bütünlük ve provenance sözleşmeleri: `TAMAM`
- Tüm gerçek gösterge ailelerine artifact-temelli toplu uygulama: `KISMI`
- Gerçek OpenBB veya başka harici provider adaptörü: `EXTERNAL_PROVIDER_BLOCKED`
- OOS promotion: mevcut OOS kapıları geçmeden `RESEARCH_ONLY`
- Live işlem: `LIVE_ORDER_BLOCKED`

