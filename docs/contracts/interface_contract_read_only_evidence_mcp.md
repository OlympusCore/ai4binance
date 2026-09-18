---
document_id: AI4B-MCP-IFC-001
title: AI4BINANCE Read-Only Evidence MCP
document_type: INTERFACE_CONTRACT
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: read_only_evidence_mcp
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/contracts/interface_contract_read_only_evidence_mcp.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# AI4BINANCE Read-Only Evidence MCP

This contract defines the advisory read-only MCP surface for Codex and
ChatGPT-compatible MCP clients. It enables bounded access to validated local
evidence artifacts. It does not provide deterministic signal authority, risk
authority, parameter migration authority, wallet access, order access, or
promotion authority.

## Safety Boundary

- Direct path `agent -> MCP -> anything` is not provided to the Agent.
- All MCP calls go through the governance gateway:

```text
Agent
-> Tool Policy
-> Authorization
-> MCP Gateway
-> Tool
```

- Canonical AI4BINANCE MCP Gateway surfaces:

```text
Filesystem MCP
GitHub MCP
PostgreSQL MCP
Research MCP
Wolfram MCP
Quant Research MCP
Canonical Market Data MCP
Evidence MCP
Governance MCP
future Binance READ-ONLY adapter
```

- Only the fixed allowlist paths under `Artifacts` are readable.
- Caller-supplied file paths are not accepted.
- Maximum artifact size, JSON schema, timestamp, freshness, and SHA-256
  evidence are validated.
- Similar secret fields are redacted before the MCP response.
- Artifact claiming authority is rejected with `EVIDENCE_AUTHORITY_VIOLATION`.
- Every response keeps `RESEARCH_ONLY`, `execution_allowed=false`, and
  `LIVE_ORDER_BLOCKED`.
- Quantitative MCP output is cold-path verification evidence only. It cannot
  become trading hot-path logic, authorize paper execution, authorize live
  execution, promote strategies, promote parameters, or modify risk limits.
- External Wolfram MCP invocation requires explicit provider registration,
  endpoint configuration, credential configuration, and operator approval. Missing
  provider registration returns blockers such as `WOLFRAM_MCP_DISABLED`,
  `WOLFRAM_MCP_ENDPOINT_MISSING`, and `WOLFRAM_MCP_CREDENTIAL_MISSING`.
- The broader MCP fabric is governed by
  `docs/contracts/interface_contract_mcp_fabric.md`.

Example policy:

```yaml
tool_policy:
  agent: research_agent
  allowed:
    - github.search
    - filesystem.read
  denied:
    - filesystem.delete
    - shell.admin
    - exchange.place_order
```

This policy is represented at code level by `McpGatewayContract`. Even if a
tool is allowed, it is only an MCP invocation permission; trading, risk,
promotion, parameter, or live execution authority is not included.

Tools:

- `health_check`
- `get_quality_triage`
- `get_market_outlook`
- `get_research_blockers`
- `market.get_snapshot`
- `market.get_data_quality`
- `market.get_provenance`
- `evidence.get`
- `evidence.verify`
- `evidence.get_provenance`
- `evidence.find_conflicts`
- `evidence.build_bundle`
- `governance.get_policy`
- `governance.get_authority`
- `governance.check_action`
- `governance.check_contract`
- `governance.get_blockers`
- `quant_research.get_capabilities`
- `quant_research.verify_formula`
- `quant_research.assess_statistics`
- `quant_research.wolfram_status`

## Optional Setup

MCP SDK is not dependent on the core execution work. With explicit operator decision:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[mcp]"
```

To directly validate the local STDIO server:

```powershell
.\.venv\scripts\ai4binance-mcp.exe --artifact-root Artifacts
```

Example of Codex project configuration:

```toml
[mcp_servers.ai4binance_evidence]
command = ".venv/scripts/ai4binance-mcp.exe"
args = [
  "--artifact-root",
  "Artifacts",
  "--wolfram-mcp-enabled",
  "--wolfram-mcp-endpoint-ref",
  "local-wolfram-mcp",
  "--wolfram-mcp-credential-configured",
]
cwd = "${workspaceFolder}"
enabled_tools = [
  "health_check",
  "get_quality_triage",
  "get_market_outlook",
  "get_research_blockers",
  "market.get_snapshot",
  "market.get_data_quality",
  "market.get_provenance",
  "evidence.get",
  "evidence.verify",
  "evidence.get_provenance",
  "evidence.find_conflicts",
  "evidence.build_bundle",
  "governance.get_policy",
  "governance.get_authority",
  "governance.check_action",
  "governance.check_contract",
  "governance.get_blockers",
  "quant_research.get_capabilities",
  "quant_research.verify_formula",
  "quant_research.assess_statistics",
  "quant_research.wolfram_status",
]
required = false
startup_timeout_sec = 10
tool_timeout_sec = 10
```

This configuration is not automatically generated. Package installation, Codex
MCP registration, Wolfram endpoint setup, and credential provisioning are
separate, explicit operator actions. Credential values must not be stored in this
repository or returned through MCP tool output.

## Artifact paths

```text
runtime/artifacts/quality/triage/state.json
runtime/artifacts/decisions/market_outlook/state.json
```

Missing, corrupted, outdated, or unauthorized files do not produce silent
fallbacks; they return an explicit blocker. A healthy MCP connection is not
proof of live processing capability or trading suitability.


## ELI10

Codex or ChatGPT helpers may read ready-made proof files through this surface.
They can read the system's evidence ledger, but they cannot issue commands,
move funds, change risk rules, promote strategies, or approve live orders.

