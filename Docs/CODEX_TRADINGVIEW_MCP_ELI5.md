# Codex + TradingView MCP Kurulumu (Windows, ELI5)

> **Güncel sınır:** TradingView dış/advisory kanıttır. AI4BINANCE için wallet,
> emir veya hard-gate doğrulama kaynağı değildir.

Bu rehber, Codex'in yerel TradingView Desktop grafiğini MCP üzerinden
okuyabilmesidir.

## 1. Sistem nasıl çalışıyor?

Bunu üç parçalı bir oyuncak telefon gibi düşünün:

```text
Codex  <->  TradingView MCP  <->  TradingView Desktop
 beyin       tercüman             grafik ekranı
```

- Codex, MCP sunucusuna standart giriş/çıkış üzerinden komut verir.
- MCP sunucusu, yalnızca bu bilgisayardaki `127.0.0.1:9222` adresine bağlanır.
- TradingView Desktop, `--remote-debugging-port=9222` seçeneğiyle açılmalıdır.
- TradingView web sayfası yeterli değildir; Desktop uygulaması gerekir.

## 2. Yerel yollar

Yeni bir `C:\AI-Workspace\Tools` klasörü oluşturmak zorunlu değildir. Mevcut
depo doğrudan kullanılabilir; aşağıdaki yer tutucuyu kendi yerel MCP depo
yolunuzla değiştirin:

```text
<TRADINGVIEW_MCP_ROOT>
```

Codex ile birlikte gelen araçlar:

```text
Node:
%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe

pnpm:
%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd
```

Codex kullanıcı yapılandırması:

```text
%USERPROFILE%\.codex\config.toml
```

## 3. Ön koşulları kontrol et

Normal PowerShell açın ve aşağıdaki komutları tek tek çalıştırın:

```powershell
Test-Path "<TRADINGVIEW_MCP_ROOT>\src\server.js"
Test-Path "<TRADINGVIEW_MCP_ROOT>\package.json"
Test-Path "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
Test-Path "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd"
```

Dört komutun da `True` döndürmesi gerekir.

Node sürümünü kontrol edin:

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" --version
```

TradingView MCP, Node.js 18 veya daha yeni bir sürüm ister.

## 4. MCP bağımlılıklarını kur

Bu işlem yalnızca `<TRADINGVIEW_MCP_ROOT>` içine `node_modules` oluşturur.
İlk kurulum internet bağlantısı gerektirir.

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd" `
  --dir "<TRADINGVIEW_MCP_ROOT>" install
```

Kurulumu kontrol edin:

```powershell
Test-Path "<TRADINGVIEW_MCP_ROOT>\node_modules\@modelcontextprotocol\sdk"
Test-Path "<TRADINGVIEW_MCP_ROOT>\node_modules\chrome-remote-interface"
```

İki sonuç da `True` olmalıdır.

## 5. Codex'e MCP sunucusunu tanıt

Önce Codex Desktop'ı tamamen kapatın. Ardından şu dosyayı Not Defteri veya VS
Code ile açın:

```text
%USERPROFILE%\.codex\config.toml
```

Mevcut içeriği silmeden dosyanın sonuna ekleyin:

```toml
[mcp_servers.tradingview]
command = '%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
args = ['<TRADINGVIEW_MCP_ROOT>\src\server.js']
startup_timeout_sec = 120
```

Önemli noktalar:

- Claude rehberindeki `.mcp.json` dosyasını Codex için oluşturmayın.
- Claude'a ait `claude mcp add` komutunu kullanmayın.
- Codex Desktop bu kurulumda `config.toml` ve `[mcp_servers.*]` biçimini kullanır.
- Var olan `[mcp_servers.node_repl]` gibi kayıtları silmeyin.
- `H:` sürücüsü Codex başlatılırken bağlı olmalıdır.

## 6. Codex'i yeniden başlat

1. Codex Desktop'ın kapalı olduğundan emin olun.
2. Codex Desktop'ı yeniden açın.
3. Yeni bir görev başlatın.
4. Şunu yazın:

```text
TradingView MCP araçlarını listele. Henüz grafikte hiçbir değişiklik yapma.
```

`tv_health_check`, `tv_launch`, `chart_get_state` gibi araçlar görünüyorsa MCP
sunucusu Codex tarafından yüklenmiştir.

## 7. TradingView Desktop'ı debug modunda aç

Önce normal açık TradingView Desktop pencerelerini tamamen kapatın. Sonra:

```powershell
Set-Location "<TRADINGVIEW_MCP_ROOT>"
cmd.exe /c scripts\launch_tv_debug.bat
```

Alternatif olarak, MCP araçları Codex'te görünüyorsa şunu isteyin:

```text
tv_launch ile TradingView Desktop'ı debug modunda başlat.
```

WindowsApps üzerinden başlatma `Access is denied` hatası verirse `tv_launch`,
uygulamayı `%LOCALAPPDATA%\tradingview-mcp\` altına kopyalayan yerel fallback
yöntemini kullanabilir. `WindowsApps` izinlerini `icacls` ile değiştirmeyin.

## 8. 9222 portunu kontrol et

```powershell
Test-NetConnection 127.0.0.1 -Port 9222
```

Beklenen sonuç:

```text
TcpTestSucceeded : True
```

`False` ise TradingView doğru debug seçeneğiyle açılmamıştır veya uygulama henüz
hazır değildir.

## 9. Bağlantı sağlık testini yap

Codex'e şunu yazın:

```text
Yalnızca tv_health_check çalıştır. Grafikte, alarmda, sembolde veya zaman
diliminde değişiklik yapma. Sonucu açıkla.
```

Beklenen ana alanlar:

```json
{
  "success": true,
  "cdp_connected": true,
  "api_available": true
}
```

`cdp_connected: false` ise önce 9222 portunu ve TradingView Desktop'ı kontrol edin.

## 10. İlk güvenli okuma testi

TradingView'de gerçek bir grafik sekmesi açın. `New Tab` veya karşılama ekranı
yeterli değildir. Sonra Codex'e şu promptu verin:

```text
Önce tv_health_check, sonra chart_get_state çalıştır.
Yalnızca mevcut sembolü, zaman dilimini ve görünen indikatör adlarını raporla.
Sembolü, zaman dilimini, indikatörleri, çizimleri, alarmları veya Pine kodunu
değiştirme. Emir verme veya broker arayüzü kullanma.
```

## 11. Blogdaki Claude adımlarının Codex karşılığı

| Blogdaki Claude adımı | Codex karşılığı |
|---|---|
| Claude Code kur | Codex Desktop zaten kuruluysa yeniden kurma gerekmez |
| `claude mcp add` | `config.toml` içine `[mcp_servers.tradingview]` ekle |
| `~/.claude/.mcp.json` | `%USERPROFILE%\.codex\config.toml` |
| Claude Code'u yeniden başlat | Codex Desktop'ı tamamen kapatıp aç |
| `tv_health_check` | Aynı MCP aracı Codex'te de kullanılır |
| Claude promptları | Aynı amaç, fakat Codex'e açık güvenlik sınırlarıyla verilir |

## 12. Sorun giderme

### MCP araçları görünmüyor

1. `config.toml` başlığının `[mcp_servers.tradingview]` olduğunu kontrol edin.
2. `command` ve `args` yollarının gerçekten var olduğunu kontrol edin.
3. `node_modules` kurulumunu kontrol edin.
4. Codex Desktop'ı tamamen kapatıp yeniden açın.

### `Cannot find package` veya `ERR_MODULE_NOT_FOUND`

Bağımlılıklar kurulmamıştır. 4. adımdaki `pnpm install` komutunu yeniden
çalıştırın.

### `cdp_connected: false` veya `ECONNREFUSED`

- TradingView Desktop açık mı?
- Gerçek bir grafik sekmesi açık mı?
- `Test-NetConnection 127.0.0.1 -Port 9222` sonucu `True` mu?
- TradingView normal yöntemle değil, debug betiği veya `tv_launch` ile mi açıldı?

### 9222 başka program tarafından kullanılıyor

Önce kullanan süreci bulun:

```powershell
Get-NetTCPConnection -LocalPort 9222 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress, LocalPort, State, OwningProcess
```

Süreci anlamadan kapatmayın. Port değiştirmek gerekirse MCP kaynak kodunun ve
TradingView başlatma seçeneğinin aynı portu kullanması gerekir.

### H: sürücüsü yokken Codex açıldı

H: sürücüsünü bağlayın ve Codex Desktop'ı yeniden başlatın. Daha kalıcı bir yol
istenirse depo `C:\AI-Workspace\Tools\tradingview-mcp` altına taşınabilir; iki
ayrı kopya tutmayın.

## 13. AI4BINANCE güvenlik sınırı

TradingView MCP güçlüdür: grafik değiştirebilir, çizim yapabilir, alarm
oluşturabilir ve Pine Script düzenleyebilir. Bu nedenle AI4BINANCE içinde varsayılan
mod salt-okunur olmalıdır.

Her TradingView görevine şu sınırı ekleyin:

```text
TradingView MCP yalnızca araştırma ve görsel analiz yardımcısıdır.
Gerçek emir gönderme, broker paneli kullanma veya canlı işlem yetkisi verme.
Alarm, çizim, sembol, zaman dilimi, indikatör veya Pine kodu değişikliği için
önce açık kullanıcı onayı iste.
MCP çıktısını deterministik sinyal yerine kullanma.
Kanıt zayıf veya çelişkiliyse NO_TRADE ve RESEARCH_ONLY döndür.
```

TradingView MCP bağlantısının başarılı olması, AI4BINANCE sisteminin canlı işleme
uygun olduğu anlamına gelmez:

```text
LIVE_ORDER_BLOCKED
RESEARCH_ONLY
```

## Kaynaklar

- [Humbled Trader bağlantı rehberi](https://www.humbledtrader.com/blog/connect-claude-to-tradingview-mcp/)
- [TradingView MCP GitHub deposu](https://github.com/tradesdontlie/tradingview-mcp)
- [TradingView MCP kurulum rehberi](https://github.com/tradesdontlie/tradingview-mcp/blob/main/SETUP_GUIDE.md)
- [OpenAI Codex belgeleri](https://developers.openai.com/codex/)
