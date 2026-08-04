# Wallet-First Read-Only Runtime

## ELI10

Bu belge bilgisayar acikken calisabilen salt-okunur yardimciyi anlatir. Yardimci
hesap ve piyasa durumunu raporlar, ama emir acmaz, iptal etmez ve canli islem
baslatmaz.


Bu runtime Windows oturum açılışında çalışabilen, Spot ve USD-M Futures hesap
durumunu piyasa analizinden önce kontrol eden salt-okunur danışmanlık katmanıdır.
Emir oluşturma, iptal etme veya canlı işlem açma yüzeyi içermez.

## Güvenlik sırası

```text
Spot wallet GET + Futures account GET
  -> iki hesap da doğrulandı mı?
  -> Spot public snapshot
  -> Spot research outlook
  -> USD-M public derivatives features
  -> dual-market RESEARCH_ONLY report
```

Wallet servislerinden biri yoksa veya hata verirse public market çağrısı yapılmaz.
Her iki market için `NO_TRADE`, `DEGRADED` ve açık blocker üretilir.

## Komutlar

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli runtime-once
.\.venv\Scripts\python.exe -m ai4binance.cli runtime-daemon
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  .\Scripts\install_startup_task.ps1
```

Görev yalnız mevcut kullanıcı oturumunda çalışır. Tek-instance lock, atomik ve
secret-safe `State/runtime.json` kullanır. Wallet bakiyeleri state dosyasına
yazılmaz.

## Credential sınırı

Runtime önce birlikte tanımlanmış `BINANCE_API_KEY` ve `BINANCE_API_SECRET`
environment değişkenlerini, bunlar yoksa yalnız allowlist içindeki
`Secrets/bnc.env` dosyasını okur. İki kaynak birbiriyle karıştırılmaz ve secret
değerleri process environment'a yazılmaz.
Anahtar Binance tarafında yalnız okuma yetkili olmalıdır. Withdrawal ve order
izinleri kapalı tutulmalıdır. Credential yoksa sistem çalışır fakat `DEGRADED`
kalır ve market önerisine geçmez.

## Ses güvenliği

`ai4binance.voice` gerçek mikrofonu ve yerel `faster-whisper` Türkçe STT'yi kullanır.
Her komut tam olarak `asistan` uyandırma ifadesiyle başlamalı ve devamı exact-match,
salt-okunur intent allowlist'inde bulunmalıdır. Emir, risk değişikliği, credential ve
live-mode komutları allowlist içinde değildir.

Speaker embedding, fiziksel enrollment ve replay-resistant liveness backend'i henüz
bağlı değildir. Bu nedenle yerel oturum ve mikrofon kontrolleri owner doğrulaması
sayılmaz: gerçek `SpeakerVerification` verilmemişse gateway
`VOICE_OWNER_VERIFICATION_UNAVAILABLE` ile bütün komutları güvenli biçimde reddeder.
Sistemin yalnızca mikrofon görmesi owner-only erişimi etkinleştirmez.
Owner doğrulaması yokken miktar içeren envanter, pozisyon ve emir komutları
fail-closed reddedilir. Miktar içermeyen sistem durumu, piyasa görünümü ve blocker
özeti yerel Windows oturumunda çalışır; health durumu `LIMITED` olur. Zamanlı rapor
yalnızca bu güvenli sistem durumu özetini seslendirir.

Finansal raporlar varsayılan olarak harici Edge TTS servisine gönderilmez.
`EdgeTtsSpeaker` dış servis kullanımı açıkça etkinleştirilmedikçe kapalıdır ve kurulu
runtime yerel Windows SAPI çıkışına düşer.

`asistan mikrofonu kapat` komutu mute durumunu latch eder, capture/transcribe
döngüsünü bitirir ve daemon normal biçimde kapanır. Aynı daemon içinde sesle unmute
yoktur; tekrar dinlemek için `AI4BINANCE-Voice-Assistant` görevi elle yeniden
başlatılmalı veya kullanıcı yeniden oturum açmalıdır. `asistan dinlemeyi durdur` da
daemon'ı kapatır ancak mute sağlık durumu üretmez.

Recorder, STT ve TTS'nin beklenen geçici hataları daemon döngüsünden dışarı taşmaz.
Secret ve finansal miktar içermeyen sağlık özeti atomik olarak
`State/private/voice-health.json` dosyasına yazılır. `state`, `updated_at`, son hata
kodu, bileşen hata sayaçları, kabul/red komut sayaçları ve `listening/muted` alanları
izlenebilir. Sağlık dosyası yürütme yetkisi veremez.

Sesli yanıt kaynağı olan `State/private/account-management.json` raporu varsayılan
olarak 180 saniyeden eskiyse, 30 saniyeden fazla gelecekteyse veya timezone bilgisi
yoksa reddedilir. Dosyanın Windows ACL'si ayrıca yalnız operatör hesabı, SYSTEM ve
Administrators ile sınırlandırılmalıdır; freshness kontrolü dosya ACL'sinin yerine
geçmez.

## Investment Management Assistant

Her wallet-first çevrim aşağıdaki alanları birlikte inceler:

- Spot envanteri,
- USD-M Futures açık pozisyon yönü,
- Spot ve Futures açık emirleri,
- Spot setup adayları ve Futures derivatives radar durumları.

Üretebileceği aksiyon etiketleri yalnız öneridir:

```text
HOLD_REVIEW
REDUCE_RISK_REVIEW
OPEN_ORDER_REVIEW
WATCHLIST
NO_ACTION
```

`OPEN_ORDER_REVIEW` emri iptal etmez; `REDUCE_RISK_REVIEW` pozisyonu kapatmaz;
`WATCHLIST` yeni emir oluşturmaz. Açık emirlerin normalized kimliği ve kalan miktarı
wallet snapshot içinde tutulur, ancak wallet bakiyeleri runtime state'e yazılmaz.

```text
execution_allowed=false
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```

