# AI4Binance CLI

## ELI10

Bu belge terminalde yazilabilen AI4BINANCE komutlarinin sozlugudur. Her komutun
adini, ne ise yaradigini ve hangi alanda guvenli kaldigini anlatir; yeni komut
gelirse bu liste de guncellenmelidir.


## Amac

`AI4Binance CLI`, AI4BINANCE EnterpriseAI vNext icin rapor-odakli ve
fail-closed komut arayuzudur. Komutlar piyasa arastirmasi, dogrulama,
yonetisim, portfoy gorunurlugu, runtime denetimi, muhasebe toplama ve Spot
canli islem onizleme akislari icin kullanilir.

Varsayilan guvenlik durusu degismez:

- Zayif, eksik veya dogrulanmamis kanitta `NO_TRADE`.
- OOS ve risk onayi tamamlanmamis islerde `RESEARCH_ONLY`.
- Canli emir kapilari tamamlanmadiginda `LIVE_ORDER_BLOCKED`.
- CLI, LLM veya danisman ajan nihai emir otoritesi degildir.

## Bakim Kurali

CLI komutu yaratildiginda, guncellendiginde, alias eklendiginde veya
silindiginde bu dosya ayni degisiklik setinde guncellenmelidir. Komut
katalogunun ana kaynagi `src/ai4binance/cli/commands.py` icindeki
`COMMAND_SPECS` listesidir. Bu belgedeki komut tablosu ile `COMMAND_SPECS`
senkron kalmak zorundadir; `tests/test_cli.py` bu kuralin en azindan komut
adi ve katalog ozeti seviyesinde korunmasini denetler.

## Calistirma

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli commands --format text
.\.venv\Scripts\python.exe -m ai4binance.cli status --format json
```

Genel secenekler:

| Secenek | Kapsam |
| --- | --- |
| `--format json\|text` | Desteklenen komutlarda JSON veya kisa metin cikti uretir. |
| `--confirm-live` | Yalnizca CLI onay kapisini isaretler; tek basina emir gondermez. |
| `--symbol` | Arastirma veya dogrulama sembolunu komut bazinda sinirli sekilde degistirir. |
| `subject` | Slash komutlari icin opsiyonel konu alanidir, ornek: `/scan spot`. |

## Komut Kapsamlari

| Grup | Kapsam |
| --- | --- |
| `core` | Guvenli durum ozeti ve komut yardimi. |
| `governance` | OEK, QAQC, ajan, skill ve repo hijyen denetimleri. |
| `market-research` | Kamu verisiyle Spot arastirmasi ve yerel kanit arama. |
| `validation` | Dogrulama verisi, backtest ozeti ve governed crew planlari. |
| `portfolio` | Portfoy, firsat, manuel aksiyon ve sembol tarama gorunurlugu. |
| `runtime` | Read-only runtime ve voice donguleri. |
| `accounting` | Read-only muhasebe snapshot, reconcile, status ve UI raporu. |
| `live-spot` | Spot emir onizleme ve tam onayli onizleme hash'iyle fail-closed yerlestirme. |

## Komut Katalogu

<!-- CLI_COMMAND_TABLE_START -->
| Komut | Grup | Alias | Katalog ozeti | Kapsam |
| --- | --- | --- | --- | --- |
| `status` | `core` | `summary` | Print the fail-closed default trading status. | Varsayilan karar durumunu, zaman dilimlerini ve canli kapilarin neden kapali oldugunu raporlar. |
| `commands` | `core` | `help` | List command groups, aliases, and examples. | Kullanilabilir komutlari grup, alias ve ornekleriyle listeler. |
| `system-report` | `core` | - | Build a secret-safe whole-system operator report. | QAQC, OEK, Lean, runtime, validation, firsat, muhasebe ve skill-discovery durumunu tek raporda toplar. |
| `agents` | `governance` | - | List governed advisory agents and live-authority counts. | Danisman ajan katalogunu ve canli otorite sayimlarini gorunur kilar. |
| `agentic-skills` | `governance` | - | Recommend a governed workflow pattern for a bounded task. | Sinirli gorevler icin uygun governed agentic workflow desenini onerir. |
| `skills-audit` | `governance` | - | Audit repo-local Agent Skills without installing or executing them. | Repo-local skill'leri kurmadan ve calistirmadan denetler. |
| `skill-discovery-once` | `governance` | - | Run one quarantine-first external Agent Skill discovery cycle. | Harici skill adaylarini tek dongude karantinaya alarak arastirir. |
| `skill-discovery-daemon` | `governance` | - | Run continuous skill discovery while the computer session is active. | Oturum aktifken surekli skill discovery dongusu calistirir. |
| `skill-discovery-status` | `governance` | - | Read the last continuous skill discovery state. | Son continuous skill discovery durumunu okur. |
| `privacy-boundary` | `governance` | - | Scan for Computer.md-derived local personal details outside Computer.md. | `Computer.md` disina tasan yerel/kisisel ayrinti risklerini raporlar. |
| `enterprise-intake` | `governance` | - | Convert a raw prompt file into a General Manager summary-only directive. | Ham prompt dosyasini Genel Mudur icin ozet-only direktife cevirir. |
| `quality-system-audit` | `governance` | `qaqc-audit` | Run the QAQC enterprise system audit. | QAQC sistem denetimini report-only sekilde calistirir. |
| `agent-stack-audit` | `governance` | - | Audit the governed modern AI agent stack. | RAG, context, memory, tools, MCP, skills, hooks, subagents, orchestration, eval ve eksik governance/security/audit/provenance katmanlarini fail-closed denetler. |
| `oek-gap-analysis` | `governance` | `oek-audit` | Check an agent, skill, workflow, or config change against the OEK. | Ajan, skill, workflow veya config degisikligini OEK'e gore denetler. |
| `repository-cleanup-audit` | `governance` | `cleanup-audit` | Run the report-only repository cleanup and stability audit. | Kaynak silmeden repo temizligi, yalinlik ve stabilite risklerini raporlar. |
| `lean-governance` | `governance` | - | Review operational excellence guardrails. | Operasyonel mukemmellik ve yalin yonetisim guardrail'lerini gozden gecirir. |
| `qaqc-agent` | `governance` | - | Show the QAQC-Agent governance review. | QAQC-Agent yonetisim incelemesini gosterir. |
| `analyze-public` | `market-research` | - | Acquire public Spot data and produce a deterministic NO_TRADE analysis. | Kamu Spot verisiyle deterministik ve emir yetkisiz analiz uretir. |
| `research-public` | `market-research` | `research` | Run the safe public research workflow. | Guvenli kamu arastirma akisini calistirir. |
| `archive-public` | `market-research` | - | Archive public market candles without wallet contamination. | Cuzdan etkisi katmadan kamu mum verisini arsivler. |
| `whale-fusion-research` | `market-research` | - | Run whale-fusion research with provider blockers surfaced. | Provider eksikleri ve blocker'lari acikca raporlayarak whale-fusion arastirmasi yapar. |
| `second-brain` | `market-research` | - | Search the local second-brain evidence index. | Yerel second-brain kanit indeksinde arama yapar. |
| `sync-validation-data` | `validation` | - | Sync Binance Vision validation data for the validation symbol. | Dogrulama sembolu icin Binance Vision verisini senkronize eder. |
| `validate-research` | `validation` | `validate` | Run validation research gates. | Arastirma adaylarini dogrulama kapilarindan gecirir. |
| `validation-summary` | `validation` | `backtests` | Summarize persisted validation run cards. | Kalici dogrulama/backtest run kartlarini ozetler. |
| `backtest-results` | `validation` | - | Compatibility alias for validation-summary output. | Eski kullanimlarla uyumlu validation-summary ciktisi saglar. |
| `crew-plan` | `validation` | - | Show the governed validation crew plan. | Governed validation crew planini gosterir. |
| `portfolio` | `portfolio` | `/portfolio` | Show read-only portfolio/account snapshot status. | Read-only portfoy ve hesap snapshot durumunu raporlar. |
| `opportunities` | `portfolio` | `/opportunities`, `ops` | Show visible research opportunities and execution blockers. | Firsat radarini aktif/pasif olarak raporlar; arastirma item'i varsa exit code 0 doner, execution blocker'lari yine gorunur kalir. |
| `manual-actions` | `portfolio` | `/manual-actions` | Show pending manual actions. | Bekleyen manuel aksiyonlari listeler. |
| `approvals` | `portfolio` | `/approvals` | Show recorded manual approvals. | Kayitli manuel onaylari gosterir. |
| `scan-spot` | `portfolio` | `scan` subject `spot`, `/scan spot` | Scan configured Spot watch symbols with explicit blockers. | Konfigure Spot izleme sembollerini blocker'lariyla tarar. |
| `scan-futures` | `portfolio` | `scan` subject `futures`, `/scan futures` | Scan configured USD-M Futures watch symbols as research-only evidence. | USD-M Futures izleme sembollerini yalnizca research-only kanit olarak tarar. |
| `scan-all` | `portfolio` | `scan` subject `all`, `/scan all` | Scan configured Spot and USD-M Futures watch symbols. | Spot ve USD-M Futures izleme listelerini birlikte tarar. |
| `runtime-once` | `runtime` | - | Run one read-only runtime cycle. | Tek read-only runtime dongusu calistirir. |
| `runtime-daemon` | `runtime` | - | Run the read-only runtime daemon. | Read-only runtime daemon'unu calistirir. |
| `voice-once` | `runtime` | - | Run one voice assistant cycle. | Tek voice assistant dongusu calistirir. |
| `voice-daemon` | `runtime` | - | Run the voice assistant daemon. | Voice assistant daemon'unu calistirir. |
| `accounting-collect-once` | `accounting` | - | Collect one read-only accounting REST snapshot. | Tek read-only accounting REST snapshot toplar. |
| `accounting-collect-daemon` | `accounting` | - | Run the read-only accounting REST daemon. | Read-only accounting REST daemon'unu calistirir. |
| `accounting-ws-once` | `accounting` | - | Collect one read-only accounting WebSocket snapshot. | Tek read-only accounting WebSocket snapshot toplar. |
| `accounting-ws-daemon` | `accounting` | - | Run the read-only accounting WebSocket daemon. | Read-only accounting WebSocket daemon'unu calistirir. |
| `accounting-reconcile-once` | `accounting` | - | Run one accounting reconciliation pass. | Tek muhasebe mutabakat gecisi calistirir. |
| `accounting-ui-report` | `accounting` | - | Build the local accounting UI report. | Yerel muhasebe UI raporunu olusturur. |
| `accounting-status` | `accounting` | - | Show accounting file freshness and reconciliation status. | Muhasebe dosya tazeligi ve mutabakat durumunu raporlar. |
| `live-preview-spot` | `live-spot` | `live-preview` | Create a Spot order preview hash without authority. | Emir yetkisi vermeden Spot order preview hash'i olusturur. |
| `live-place-spot` | `live-spot` | `live-place` | Place an exact approved Spot preview only after all live gates pass. | Sadece tum canli kapilar gecerse onayli preview hash'iyle Spot emir katmanina ilerler. |
<!-- CLI_COMMAND_TABLE_END -->

## Sinirlar

- `live-preview-spot` emir gondermez; yalnizca onizleme ve hash kaniti uretir.
- `live-place-spot` dahil her canli akista tum live gate'ler tamamlanmadan sonuc
  `LIVE_ORDER_BLOCKED` kalir.
- Arastirma ve Futures kaynaklari Spot kararlarina yalnizca yardimci kanit
  olabilir; dogrulanmamis kanit execution yetkisine donusmez.
- `opportunities` komutunda aktif radar, trade onayi degildir. Bu komut firsat
  arastirmasinin calistigini raporlar; `NO_READY_CANDIDATE`,
  `VALIDATION_GATE_REQUIRED` veya benzeri blocker'lar execution hattini kapali
  tutar.
- Cuzdan ve inventory bilgisi raporlama ve gercek execution kontrolu icindir;
  historik backtest butunlugunu etkilememelidir.

