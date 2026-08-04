# Evidence-Backed X Draft Queue

## ELI10

Bu rapor, kanita dayali sosyal medya taslak kuyrugunun nasil tasarlandigini
anlatir. Sistem yazi taslagi uretebilir ve onay kuyruguna koyabilir, ama tek
basina yayin yapamaz.


Bu dikey dilim, doğrulanmış Market Outlook kanıtını deterministik bir X taslağına
dönüştürür ve yerel append-only onay kuyruğuna ekler. Ağ çağrısı, X API anahtarı,
OAuth, medya yükleme veya yayınlama adapter'ı içermez.

## Akış ve güven sınırı

```text
Artifacts/market-outlook/state.json
  -> EvidenceGateway (allowlist, SHA-256, schema, freshness, authority)
  -> ContentDraftEngine (bounded template, claims, citations, compliance)
  -> LocalApprovalQueue (append-only REVIEW_REQUIRED/APPROVED/REJECTED/EXPIRED)
  -> STOP (publishing adapter yok)
```

Taslak ve bütün kuyruk olayları aşağıdaki sabitleri taşır:

```text
publish_allowed=false
execution_allowed=false
live_eligibility_status=LIVE_ORDER_BLOCKED
```

`APPROVED`, yalnız yerel editoryal incelemenin kaydıdır. Tek başına gönderim yetkisi
veya işlem uygunluğu anlamına gelmez. Ayrı publishing gateway kapıları
`Docs/SOCIAL_PUBLISHING_GATEWAY.md` belgesinde tanımlıdır.

## Makineyle doğrulanan kapılar

- Kaynak türü yalnız `market_outlook` olabilir.
- Kanıt `FRESH` olmalı ve veri gövdesi bulunmalıdır.
- Kaynak execution yetkisi taşıyamaz; live durumu `LIVE_ORDER_BLOCKED` kalır.
- 1D, 4H ve 1H bias alanları eksiksiz ve allowlist değerlerinden olmalıdır.
- Taslak 280 karakteri aşamaz ve araştırma/işlem-sinyali uyarısını içerir.
- Kâr garantisi, dış link, kullanıcı mention'ı ve secret-benzeri metin engellenir.
- Her iddia, kaynak artefakt alanına bağlanır; kaynak yolu, hash'i ve timestamp'i
  taslakta saklanır.
- Aynı kaynak/template/içerik aynı SHA-256 `draft_id` değerini üretir ve ikinci
  enqueue yeni olay yazmaz.
- Kuyruk bozulması, yetki manipülasyonu ve geçersiz durum geçişi fail-closed
  reddedilir.
- Yerel approval için tam `APPROVE_LOCAL_DRAFT` confirmation değeri gerekir.

## Yerel kullanım

```python
from pathlib import Path

from ai4binance.content import (
    ContentDraftEngine,
    EvidenceBackedDraftQueue,
    LocalApprovalQueue,
)
from ai4binance.mcp import EvidenceGateway

workflow = EvidenceBackedDraftQueue(
    evidence_gateway=EvidenceGateway(Path("Artifacts")),
    draft_engine=ContentDraftEngine(),
    approval_queue=LocalApprovalQueue(Path("Artifacts/content/approval.jsonl")),
)
receipt = workflow.ingest_market_outlook()
print(receipt.draft.draft_id, receipt.enqueued, receipt.publish_attempted)
```

Onay örneği yalnız yerel durum kaydı üretir:

```python
workflow.approval_queue.approve(
    receipt.draft.draft_id,
    approved_by="operator",
    rationale="Kaynak ve metin yerel olarak incelendi",
    confirmation="APPROVE_LOCAL_DRAFT",
)
```

## Kapsam dışı / sonraki aşamalar

- P1 read-only X intelligence provider adapter'ları
- P3 içerik takvimi ve performans raporu
- P4 kullanıcı onaylı text publishing gateway uygulanmıştır; gerçek provider
  credential/scope doğrulaması dış bağımlılıktır.
- P5 medya, thread ve kontrollü reply desteği

P5 için medya, thread/reply policy, upload lifecycle ve ayrı approval kapsamı
gereklidir. Bunlar text publishing yetkisine dahil değildir.

