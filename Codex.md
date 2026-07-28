# Codex İçin ELI5 Başlangıç

Bir görevde şu sırayı izle:

1. `Custom_Instructions_Core.md` hedef ve güvenlik kurallarını oku.
2. `CleanCodes.md` kod kalite kurallarını oku.
3. İlgili alt klasörde `AGENTS.md` varsa onu oku.
4. Değişiklikten önce Git durumunu ve tam kalite baz çizgisini ölç.
5. En küçük güvenli değişikliği yap ve regresyon testi ekle.
6. Pytest, Ruff ve MyPy tamamen yeşil olmadan tamamlandı deme.

Her zaman:

```text
weak evidence -> NO_TRADE
weak OOS -> RESEARCH_ONLY
missing live gate -> LIVE_ORDER_BLOCKED
```

LLM final sinyal, risk onayı veya emir otoritesi değildir.
