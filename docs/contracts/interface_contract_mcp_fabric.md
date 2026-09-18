---
document_id: AI4B-MCP-IFC-002
title: AI4BINANCE MCP Fabric Interface Contract
document_type: INTERFACE_CONTRACT
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: mcp_fabric
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/contracts/interface_contract_mcp_fabric.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# AI4BINANCE MCP Fabric Interface Contract

This contract defines the governed MCP fabric for AI4BINANCE capability access.
It extends the read-only evidence MCP contract without replacing it.

## ELI10

This contract says MCP tools are controlled capability doors. Some doors may
read evidence or run research checks, but no MCP door may secretly become a
trading, risk override, live order, credential, or strategy promotion door.

## Authority Boundary

MCP tools may support:

```text
DISCOVER
ANALYZE
VERIFY
COMPARE
EXPERIMENT
```

MCP tools must not support:

```text
PROMOTE_STRATEGY
OVERRIDE_RISK
AUTHORIZE_LIVE_ORDER
DISABLE_KILL_SWITCH
READ_CREDENTIAL
EXPORT_SECRET
```

Tool discovery is not authority discovery. Every tool remains subject to:

```text
Agent
-> Tool Policy
-> Authorization
-> MCP Gateway
-> Tool
```

## Authority Classes

| Class | Scope | Initial Posture |
| --- | --- | --- |
| `MCP_R0_READ_ONLY` | Read bounded evidence or governed metadata | Broadly allowed |
| `MCP_R1_ANALYZE_COMPUTE` | Analyze or compute research evidence | Allowed |
| `MCP_R2_CREATE_RESEARCH_ARTIFACTS` | Create research artifacts | Governed |
| `MCP_R3_CONTROLLED_STATE_MUTATION` | Controlled state mutation | Exceptional |
| `MCP_X_EXECUTION_SENSITIVE` | Execution-sensitive capability | Blocked |

`MCP_X_EXECUTION_SENSITIVE` tools cannot be allowlisted.

## Fabric Families

Initial MCP fabric families:

- Research MCPs
- Computation MCPs
- Data MCPs
- Control MCPs
- Experiment MCPs

Initial P0 surfaces:

- Quant Research MCP
- Wolfram MCP
- Canonical Market Data MCP
- Evidence MCP
- Governance MCP

These surfaces produce advisory evidence only. They do not produce deterministic
trade decisions, risk overrides, parameter promotion, paper execution approval,
or live order authority.

## Explicitly Blocked Tools

The following tool names are execution-sensitive and must remain denied:

```text
risk.override
governance.override
strategy.promote
parameter.promote
kill_switch.disable
live.enable
order.live.submit
credential.read
secret.export
```

## Safety Invariants

- Direct `Agent -> MCP` routing is prohibited.
- Direct `Agent -> Binance API` routing is prohibited for market data research.
- Wolfram-backed MCP checks are cold-path verification only and require explicit
  provider registration before invocation.
- Quant Research MCP may run bounded deterministic checks and expose Wolfram
  registration status, but missing provider evidence must produce blockers.
- Canonical market data MCP reads validated snapshots only.
- Evidence MCP reads and verifies bounded evidence only.
- Governance MCP can read, check, validate, and explain blockers only.
- Scores may compensate; hard blockers cannot.
- Every MCP response that crosses the advisory boundary keeps
  `RESEARCH_ONLY`, `execution_allowed=false`, and `LIVE_ORDER_BLOCKED`.
