# AI4BINANCE Read-Only Evidence MCP

Bu dikey dilim Codex ve ChatGPT uyumlu MCP istemcilerinin doğrulanmış araştırma
artefaktlarını okumasını sağlar. Deterministik sinyal, risk, parametre terfisi,
cüzdan ve emir katmanlarına erişim vermez.

## Güven sınırı

- Yalnız `Artifacts` altındaki sabit allowlist yolları okunur.
- Araç çağrısı dosya yolu kabul etmez.
- Maksimum artefakt boyutu, JSON şeması, zaman damgası, freshness ve SHA-256
  kanıtı doğrulanır.
- Secret benzeri alanlar MCP cevabından önce redakte edilir.
- Yetki iddia eden artefakt `EVIDENCE_AUTHORITY_VIOLATION` ile reddedilir.
- Her cevap `RESEARCH_ONLY`, `execution_allowed=false` ve
  `LIVE_ORDER_BLOCKED` taşır.

Araçlar:

- `health_check`
- `get_quality_triage`
- `get_market_outlook`
- `get_research_blockers`

## Opsiyonel kurulum

MCP SDK çekirdek çalışmanın bağımlılığı değildir. Açık operatör kararıyla:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[mcp]"
```

Yerel STDIO sunucusunu doğrudan doğrulamak için:

```powershell
.\.venv\Scripts\ai4binance-mcp.exe --artifact-root Artifacts
```

Codex proje yapılandırması örneği:

```toml
[mcp_servers.ai4binance_evidence]
command = ".venv/Scripts/ai4binance-mcp.exe"
args = ["--artifact-root", "Artifacts"]
cwd = "C:/AI-Workspace/02_Projects/ai4binance"
enabled_tools = [
  "health_check",
  "get_quality_triage",
  "get_market_outlook",
  "get_research_blockers",
]
required = false
startup_timeout_sec = 10
tool_timeout_sec = 10
```

Bu yapılandırma otomatik olarak oluşturulmaz. Paket kurulumu ve Codex MCP kaydı
ayrı, açık operatör eylemidir.

## Artefakt yolları

```text
Artifacts/quality-triage/state.json
Artifacts/market-outlook/state.json
```

Eksik, bozuk, eski veya yetki sınırını ihlal eden dosya sessiz fallback üretmez;
açık blocker döndürür. MCP bağlantısının sağlıklı olması canlı işlem uygunluğu
kanıtı değildir.


## ELI10

Bu belge, Codex veya ChatGPT gibi yardimcilarin sadece hazir kanit dosyalarini
okuyabilmesini anlatir. Yani sistemin defterine bakabilirler, ama emir veremez,
para hareketi yapamaz ve risk kurallarini degistiremezler.

