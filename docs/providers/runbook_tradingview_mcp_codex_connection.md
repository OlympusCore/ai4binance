---
document_id: AI4B-MCP-RUN-002
title: Codex TradingView MCP ELI10 Guide
document_type: RUNBOOK
version: 1.0.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: ADVISORY
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: tradingview_mcp_codex_connection
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: EXPLANATORY
source_of_truth: false
source_of_truth_scope: tradingview_mcp_codex_connection
canonical_path: docs/providers/runbook_tradingview_mcp_codex_connection.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# Codex + TradingView MCP Kurulumu (Windows, ELI5)

## ELI10

This guide explains how Codex can read information from the TradingView screen. This information
It is merely an auxiliary proof; reading the graph alone is not sufficient to constitute a buy-sell order, risk approval, or
does not grant live-trading permission.

This runbook is an `L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS` operational
specialization. It may guide local provider setup, but it may not widen or
override higher-authority governance, risk, execution, or promotion controls.


> **Current Limit:** TradingView external/advisory is evidence. For AI4BINANCE, wallet,
> It is not an order source or a hard-gate validation source.

This guide shows how to use the local TradingView Desktop chart of Codex via MCP
okuyabilmesidir.

## 1. How does the system work?

Think of this as a three-part toy phone:

```text
Codex  <->  TradingView MCP  <->  TradingView Desktop
brain translator graphic screen
```

- Codex sends commands to the MCP server through standard input/output.
- The MCP server connects only to the address `127.0.0.1:9222` on this computer.
- TradingView Desktop should be opened with the option `--remote-debugging-port=9222`.
- The TradingView web page is insufficient; a desktop application is required.

## 2. Yerel yollar

Creating a new `C:\AI-Workspace\Tools` folder is not mandatory. Existing
repository can be used directly; replace the placeholder below with your local MCP repository
path:

```text
<TRADINGVIEW_MCP_ROOT>
```

Tools included with Codex:

```text
Node:
%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe

pnpm:
%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd
```

Codex user configuration:

```text
%USERPROFILE%\.codex\config.toml
```

## 3. Check the prerequisites

Open Normal PowerShell and run the following commands one by one:

```powershell
Test-Path "<TRADINGVIEW_MCP_ROOT>\src\server.js"
Test-Path "<TRADINGVIEW_MCP_ROOT>\package.json"
Test-Path "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
Test-Path "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd"
```

All four commands must return `True`.

Check Node version:

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" --version
```

TradingView MCP requires Node.js 18 or newer.

## 4. MCP dependencies install

This process only creates a `node_modules` directory inside `<TRADINGVIEW_MCP_ROOT>`.
The initial installation requires an internet connection.

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd" `
  --dir "<TRADINGVIEW_MCP_ROOT>" install
```

Kurulumu kontrol edin:

```powershell
Test-Path "<TRADINGVIEW_MCP_ROOT>\node_modules\@modelcontextprotocol\sdk"
Test-Path "<TRADINGVIEW_MCP_ROOT>\node_modules\chrome-remote-interface"
```

Both results must be `True`.

## 5. Register MCP server with Codex

First, completely close Codex Desktop. Then open the following file with Notepad or VS
Code:

```text
%USERPROFILE%\.codex\config.toml
```

Append the following content to the end of the file without deleting its existing content:

```toml
[mcp_servers.tradingview]
command = '%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
args = ['<TRADINGVIEW_MCP_ROOT>\src\server.js']
startup_timeout_sec = 120
```

Important notes:

- Do not create the `.mcp.json` file in the Claude guide for Codex.
- Do not use the `claude mcp add` command that belongs to Claude.
- Codex Desktop uses the `config.toml` and `[mcp_servers.*]` format in this setup.
- Do not delete existing entries such as `[mcp_servers.node_repl]`.
- The `H:` drive must be connected when Codex starts.

## 6. Restart Codex

1. Ensure that Codex Desktop is closed.
2. Restart Codex Desktop.
3. Start a new task.
4. Type the following:

```text
List all TradingView MCP tools. Do not make any changes to the chart yet.
```

If tools like `tv_health_check`, `tv_launch`, and `chart_get_state` are visible, MCP
The server was loaded by Codex.

## 7. Open TradingView Desktop in debug mode

First, close all normal open TradingView Desktop windows. Then:

```powershell
Set-Location "<TRADINGVIEW_MCP_ROOT>"
cmd.exe /c scripts\launch_tv_debug.bat
```

Alternatively, if the MCP tools are visible in Codex, request this:

```text
Launch TradingView Desktop with tv_launch in debug mode.
```

If starting via `WindowsApps` results in the `Access is denied` error, use `tv_launch`,
The local fallback that copies the application to `%LOCALAPPDATA%\tradingview-mcp\`
You can use this method. Do not change the `WindowsApps` permissions using `icacls`.

## 8. 9222 portunu kontrol et

```powershell
Test-NetConnection 127.0.0.1 -Port 9222
```

Expected result:

```text
TcpTestSucceeded : True
```

`False` means TradingView is not opened with the correct debug option or the application is not yet
ready.

## 9. Perform a connection health test

Write this to Codex:

```text
Run only tv_health_check. Do not make any changes in the chart, alarm, symbol, or time
zone. Explain the result.
```

Expected main fields:

```json
{
  "success": true,
  "cdp_connected": true,
  "api_available": true
}
```

If `cdp_connected: false`, first check port 9222 and TradingView Desktop.

## 10. First secure read test

Open a real chart tab in TradingView. `New Tab` or welcome screen
It is not sufficient. Then give this prompt to Codex:

```text
Run `tv_health_check` first, then `chart_get_state`.
Report only the current symbol, time frame, and visible indicator names.
Symbol, time zone, indicators, plots, alerts, or Pine code
Modification. Giving orders or using the broker interface.
```

## 11. Codex Equivalent of the Claude Steps in the Blog

| Claude step in the blog | Codex equivalent |
|---|---|
| Install Claude Code | Do not reinstall when Codex Desktop is already installed |
| `claude mcp add` | Add `[mcp_servers.tradingview]` into `config.toml` |
| `~/.claude/.mcp.json` | `%USERPROFILE%\.codex\config.toml` |
| Restart Claude Code | Completely close and reopen Codex Desktop |
| `tv_health_check` | The same MCP tool is also used in Codex |
| Claude prompts | Same purpose, but given with open security boundaries to Codex |

## 12. Sorun giderme

### MCP tools are not visible

1. Ensure that the `config.toml` header is `[mcp_servers.tradingview]`.
2. Ensure that the `command` and `args` paths actually exist.
3. `node_modules` kurulumunu kontrol edin.
4. Close and restart Codex Desktop completely.

### `Cannot find package` or `ERR_MODULE_NOT_FOUND`

Dependencies are not installed. Run the `pnpm install` command from step 4 again
Run.

### `cdp_connected: false` or `ECONNREFUSED`

- Is TradingView Desktop open?
- Is a real graphics tab open?
- Does `Test-NetConnection 127.0.0.1 -Port 9222` return `True`?
- Was TradingView opened using a debug script or `tv_launch` instead of the normal method?

### 9222 is being used by another program

First, find the user process:

```powershell
Get-NetTCPConnection -LocalPort 9222 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress, LocalPort, State, OwningProcess
```

Do not close the process without understanding it. If port change is required, modify the MCP source code and
The TradingView startup option must use the same port.

### H: Codex opened when driver is absent

H: Connect the driver and restart Codex Desktop. More permanent way
The `C:\AI-Workspace\tools\tradingview-mcp` directory can be moved under the `istenirse` folder; two
Do not keep separate copies.

## 13. AI4BINANCE Security Limit

TradingView MCP is powerful: can change charts, draw, set alerts
can create and edit Pine Script. Therefore, AI4BINANCE has the default
The module must be read-only.

Add this limit to her TradingView task:

```text
TradingView MCP is solely a research and visual analysis assistant.
Granting actual order sending, using the broker panel, or providing live trading permissions.
Alarm, drawing, symbol, time zone, indicator or Pine script change
Request explicit user approval first.
Do not use MCP output instead of a deterministic signal.
If the proof is weak or contradictory, return NO_TRADE and RESEARCH_ONLY.
```

Successful connection to TradingView MCP enables the AI4BINANCE system to operate in live mode
It does not mean appropriate:

```text
LIVE_ORDER_BLOCKED
RESEARCH_ONLY
```

## Kaynaklar

- [Humbled Trader connection guide](https://www.humbledtrader.com/blog/connect-claude-to-tradingview-mcp/)
- [TradingView MCP GitHub deposu](https://github.com/tradesdontlie/tradingview-mcp)
- [TradingView MCP setup rehberi](https://github.com/tradesdontlie/tradingview-mcp/blob/main/SETUP_GUIDE.md)
- [OpenAI Codex belgeleri](https://developers.openai.com/codex/)
