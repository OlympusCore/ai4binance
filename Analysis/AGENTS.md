# Teknik Analiz Ajanları

> **ELI5:** Ajanlar kanıt üretir; emir vermez. Güncel ajan sayısı ve gerçek
> implementasyon durumu `Docs/COMPLIANCE_MATRIX.md` içinde tutulur.

Her teknik aile ayrı, deterministik ve test edilebilir bir modül olmalıdır.
Her ajan `role`, `allowed_timeframes`, `score_contribution`, `blockers`,
`false_positive_risk`, `required_oos_validation` ve `promotion_status` üretir.

Trend, yapı ve fiyat aksiyonu birincil; volatilite risk filtresi; momentum ve
hacim ikincil; Fibonacci, formasyon ve makro döngü danışman niteliktedir.
Tek mum veya öznel örüntü tek başına hard gate olamaz. OOS ve çoklu rejim kanıtı
olmayan tüm adaylar `RESEARCH_ONLY` veya `STAGED_CANDIDATE` kalır.
