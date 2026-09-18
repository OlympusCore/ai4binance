---
document_id: AI4B-RUNTIME-RUN-001
title: AI4BINANCE Read-Only Runtime
document_type: RUNBOOK
version: 1.0.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: read_only_runtime
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: read_only_runtime_runbook
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/runbooks/runbook_read_only_runtime.md
---

# Wallet-First Read-Only Runtime

## ELI10

This document explains the read-only helper that runs when the computer is on. Helper
Reports account and market status, but does not open orders, cancel orders, and live trading is blocked
from starting.


This runtime runs on Windows session startup, and handles Spot and USD-M Futures account
status before market analysis. It is a read-only advisory layer.
It does not include interfaces for creating orders, canceling orders, or opening live positions.

## Security Order

```text
Spot wallet GET + Futures account GET
  -> Have both accounts been verified?
  -> Spot public snapshot
  -> Spot research outlook
  -> USD-M public derivatives features
  -> dual-market RESEARCH_ONLY report
```

If one of the wallet services is unavailable or an error occurs, no public market call is made.
A `NO_TRADE`, `DEGRADED`, and open blocker is generated for both markets.

## Commands

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli runtime-once
.\.venv\Scripts\python.exe -m ai4binance.cli runtime-daemon
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\install_startup_task.ps1
```

The task runs only in the current user session. It uses a single-instance lock, atomic, and
secret-safe `runtime/state/runtime.json` file. Wallet balances are stored in the state file
unwritten.

`status` and `virtual-runtime-once` share the same canonical virtual-market gate
payload helper. Both commands remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED`;
the shared helper only keeps the envelope consistent across CLI surfaces.

## Credential limit

The runtime requires previously defined `BINANCE_API_KEY` and `BINANCE_API_SECRET`
environment variables, or if they are not present, the ones in the allowlist
Reads the `secrets/bnc.env` file. Two sources are not mixed with each other and secret
The values are not written to the process environment.
The **Binance** key should have only read permissions. Withdrawal and order
Credentials should be kept closed. The system runs but in `DEGRADED` state if credentials are missing.
It leaves and does not proceed with the market recommendation.

## Security

`ai4binance.voice` uses a real microphone and local `faster-whisper` Turkish STT.
Every command must start exactly with the `asistan` wake phrase and continue as
an exact-match read-only intent in the allowlist. Order, risk-change, credential,
and live-mode commands are not in the allowlist.

Speaker embedding, physical enrollment and replay-resistant liveness backend is still not implemented
is not bound. Therefore, local session and microphone controls are owner verification /no_check
unspecified: real `SpeakerVerification` not provided in gateway
`VOICE_OWNER_VERIFICATION_UNAVAILABLE` blocks all commands securely.
The system's ability to only see the microphone does not enable owner-only access.
Inventory, position, and order commands containing quantity without owner verification
fail-closed is applied. System status without quantity, market view, and blocker
Summary runs in the local Windows session; health status becomes `LIMITED`. Real-time report
Only this secure system status summary is spoken.

Financial reports are not sent by default to the external Edge TTS service.
`EdgeTtsSpeaker` is disabled by default and must be explicitly enabled for external service usage, and is installed
The runtime falls back to local Windows SAPI output.

The `asistan mikrofonu kapat` command latches the mute state, completes the
capture/transcribe loop, and closes the daemon normally. There is no active
listener for voice-based unmute inside the same daemon; restart the
`AI4BINANCE-Voice-Assistant` task manually or log in again to listen again. The
`asistan dinlemeyi durdur` command also closes the daemon but does not produce a
mute health status.

Recorder, STT and TTS's expected transient errors do not overflow out of the daemon loop.
Secret and non-financial amount-containing health summary atomically
It is written to the file `runtime/state/private/voice-health.json`. `state`, `updated_at`, last error
code, component error counters, accept/reject command counters, and `listening/muted` fields
Trackable. Cannot grant execution permission for the health file.

The report `runtime/state/private/account-management.json` is the source of the audio response, default
is older than 180 seconds, more than 30 seconds in the future, or lacks timezone information
is rejected when missing. The file's Windows ACL is also restricted to the operator account, SYSTEM and
Administrators must be restricted; freshness check should replace the file ACL's
Does not pass.

## Investment Management Assistant

Each wallet-first approach examines the following fields together:

- Spot inventory
- Direction of open futures positions for USD-M
- Open orders for Spot and Futures
- Spot setup candidates and Futures derivatives radar statuses.

Generated action labels are only suggestions:

```text
HOLD_REVIEW
REDUCE_RISK_REVIEW
OPEN_ORDER_REVIEW
WATCHLIST
NO_ACTION
```

`OPEN_ORDER_REVIEW` does not cancel orders; `REDUCE_RISK_REVIEW` does not close
positions; `WATCHLIST` does not create new orders. The normalized identity of
open orders and remaining quantities are stored in the wallet snapshot, but
wallet balances are not written to the runtime state.

```text
execution_allowed=false
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```


