# AI4BINANCE Holding Governance

Bu belge AI4BINANCE enterprise holding katmaninin fail-closed yonetim
kurallarini tanimlar.

## Codex Prompt Intake

- Codex veya kullanici tarafindan yazilan ham prompt sadece
  `GeneralManagerController` tarafindan okunabilir.
- Ham prompt departman mudurlerine, uzman ajanlara, toplantilara, komitelere
  veya interdepartmental mesajlara aktarilmaz.
- Departmanlara sadece redakte edilmis ozet, amac, kisitlar, yetki kapsami,
  kanit referanslari ve blocker listesi verilir.
- Ham promptun kaniti metin olarak degil, `prompt-sha256:<hash>` referansi ile
  tutulur.
- Prompt intake, prompt access karari ve is emri olusturma olaylari
  `EnterpriseAuditJournal` uzerinden dogrulanmis JSONL audit kaydina yazilabilir.
- Ham prompt, API anahtari, gizli deger veya cuzdan bakiyesi iceren
  interdepartmental mesajlar `PROMPT_ACCESS_BLOCKED` ile durdurulur.

## Safety Boundary

Bu katman is emri ve yonetim onizlemesi uretir. Canli emir yetkisi vermez,
risk kapilarini genisletmez ve uretim parametresi terfi ettirmez.

Yerel bilgisayar profili, donanim, editor ve runtime ayrintilari sadece
`Computer.md` icinde tutulur. Kod, test, rapor, prompt, meeting note veya
diger dokumanlar bu degerleri kopyalamaz; gerektiginde yalnizca `Computer.md`
referansi kullanilir. QAQC denetimi bu siniri `COMPUTER_MD_PRIVACY_BOUNDARY`
kontrolu ile fail-closed dogrular.

## Written Approval Documentation Sync

`WRITTEN_APPROVAL_DOC_SYNC` kuralina gore kullanici sistem duzeltmesi veya
iyilestirmesi icin yazili onay verdiginde, ilgili `.md` talimat ve karar
belgeleri ayni bounded diff icinde guncellenebilir. Bu guncelleme yalnizca
redakte edilmis sistem kuralini, kapsam sinirini, kalite kanitini ve blocker
durumunu kaydeder.

Ham prompt, gizli deger, yerel bilgisayar profili, cuzdan bakiyesi veya
credential kopyalanmaz. Yerel bilgisayar bilgisi gerekiyorsa dokumanlar sadece
`Computer.md` referansi kullanir. `.md` guncellemesi tek basina uygulama kaniti
degildir; ilgili kod, test, QAQC ve kalite kapisi ayrica gecmelidir.

Guncellenebilir talimat yuzeyleri sunlardir:

- `Docs/README.md`
- `Docs/HOLDING_GOVERNANCE.md`
- `Docs/COMPLIANCE_MATRIX.md`
- `Docs/FOLDER_OWNERSHIP.md`
- `Docs/REPO_CLEANUP_DIFF_PLAN_20260728.md`
- `Docs/SKILLS_GOVERNANCE.md`
- `Docs/MODEL_ADAPTATION_GOVERNANCE.md`

Varsayilan durumlar korunur:

- `NO_TRADE`
- `RESEARCH_ONLY`
- `HUMAN_REVIEW_REQUIRED`
- `LIVE_ORDER_BLOCKED`

## Quality Department System Audit

Kalite Departmani genel sistem denetimi `quality-system-audit` komutu ile
calisir:

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli quality-system-audit --format text
```

Denetim asagidaki kontrolleri kapsar:

- `QUALITY_AUDIT` departmaninin bagimsiz kontrol ve veto yetkisi.
- `Computer.md` disinda yerel bilgisayar profili sizintisi olmamasi.
- Ham promptun sadece `GeneralManagerController` tarafindan okunmasi.
- Departmanlar arasi mesajlarda raw prompt sizintisinin
  `PROMPT_ACCESS_BLOCKED` ile durdurulmasi.
- `EnterpriseAuditJournal` uzerinde prompt intake, prompt access ve work-order
  audit event yuzeylerinin bulunmasi.
- Skill linter, enterprise task tracker, corrective RAG gate ve model
  adaptation research board yuzeylerinin import edilebilir olmasi.
- Agent lifecycle state machine uzerinde `IDLE`, `PERCEIVE`, `REASON`,
  `PLAN`, `ACT`, `OBSERVE`, `HUMAN_CHECK`, `DONE` ve `ERROR` durumlarinin
  typed contract olarak bulunmasi.
- Yerel bilgisayar profilinin sadece `Computer.md` icinde tutulmasi ve
  baska dokuman, kod, test fixture veya log icine kopyalanmamasini denetleyen
  `COMPUTER_MD_PRIVACY_BOUNDARY` kontrolu.
- Yazili onay verilen sistem duzeltmelerinde ilgili Markdown talimat
  yuzeylerinin redakte edilmis ve kanitlanabilir sekilde senkron tutuldugunu
  dogrulayan `WRITTEN_APPROVAL_DOC_SYNC` kontrolu.
- Governance CLI komutlarinin kayitli olmasi.
- Bu holding governance dokumaninin temel guvenlik terimlerini icermesi.

Rapor `RESEARCH_ONLY` ve `LIVE_ORDER_BLOCKED` kalir. Denetim bulgulari
duzeltme aksiyonu onerir; canli emir, risk artisi veya uretim terfisi yapmaz.
