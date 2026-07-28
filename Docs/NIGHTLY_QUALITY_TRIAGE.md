# Nightly Quality Triage Loop

Bu loop her gece 01:17 UTC'de ve elle tetiklendiğinde kalite kapılarını bağımsız
çalıştırır. Kaynak kodu, parametreleri, risk limitlerini veya trading state'ini
değiştiremez; commit, push, PR, merge, deploy ya da emir gönderemez.

## Sabit kapılar

- Ruff format
- Ruff lint
- MyPy strict
- Pytest ve branch coverage
- Bandit

Her komut shell kullanılmadan sabit argümanlarla çalışır. Bir kapının başarısızlığı
diğer kapıların çalışmasını engellemez. Komut başına süre sınırı 600 saniye, job
sınırı 20 dakikadır. Aynı anda ikinci çalışma lock tarafından reddedilir.

## Kanıt

Çıktılar `Artifacts/quality-triage/` altında tutulur:

- `state.json`: son tamamlanan çalışmanın atomik durum fotoğrafı
- `runs.jsonl`: secret-redacted append-only çalışma günlüğü

CI artifact retention süresi 30 gündür. Repository çalışma ağacında üretilen yerel
artifact'lar Git tarafından izlenmez.

## Yerel çalışma

```powershell
.\.venv\Scripts\python.exe -m ai4binance.ops.quality_triage `
  --repository-root . `
  --output-directory Artifacts\quality-triage `
  --revision LOCAL
```

Başarı yalnız bütün kapılar sıfır exit code verdiğinde kabul edilir. Her sonuçta:

```text
mode=TRIAGE_ONLY
execution_allowed=false
live_eligibility_status=LIVE_ORDER_BLOCKED
```
