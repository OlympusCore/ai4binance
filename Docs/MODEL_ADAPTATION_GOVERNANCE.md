# AI4BINANCE Model Adaptation Governance

## ELI10

Bu belge model egitme veya uyarlama fikirlerinin nasil sinirda tutulacagini
anlatir. Model iyilestirme arastirma olabilir, ama tek basina sinyal, risk,
parametre terfisi veya canli emir yetkisi veremez.


PEFT, LoRA ve QLoRA calismalari AI4BINANCE icinde arastirma adayi olarak ele
alinir. Bu katman deterministic trading core, risk gate, execution gate veya
canli emir yetkisi uretmez.

## Required Evidence

Bir model adaptation adayi asagidaki referanslar olmadan sadece
`RESEARCH_ONLY` kalir:

- dataset lineage reference
- offline evaluation reference
- out-of-sample evidence reference
- model card reference
- red-team review reference
- risk review reference

Tum referanslar mevcut olsa bile sonuc yalnizca `STAGED_CANDIDATE` olabilir.
Canli emir uygunlugu her zaman `LIVE_ORDER_BLOCKED` olarak kalir.

## Evaluation Contract

Use:

```python
from ai4binance.learning.model_adaptation import (
    ModelAdaptationCandidate,
    ModelAdaptationMethod,
    assess_model_adaptation_candidate,
)
```

Assessment ciktilari:

- `recommendation`: `RESEARCH_ONLY` veya `STAGED_CANDIDATE`
- `blockers`: eksik kanitlar ve `LIVE_ORDER_BLOCKED`
- `required_reviews`: dataset, OOS, red-team ve quality review kayitlari
- `execution_allowed=false`

Bu board model agirligi terfi ettirmez, adapter deploy etmez, risk limitini
degistirmez ve final trading signal uretmez.

