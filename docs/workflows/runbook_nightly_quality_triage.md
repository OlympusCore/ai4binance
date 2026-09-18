---
document_id: AI4B-QA-RUN-001
title: AI4BINANCE Nightly Quality Triage
document_type: RUNBOOK
version: 1.0.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: nightly_quality_triage
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: nightly_quality_triage_workflow
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/workflows/runbook_nightly_quality_triage.md
---

# Nightly Quality Triage Loop

## ELI10

This document explains how the night quality control will be conducted as a report-only process. Control
scripts find and report issues, but do not change code, commit, push, or deploy
does not execute and does not send an order.


This loop triggers every night at 01:17 UTC and manually when quality doors are independent /no_check
Runs. Source code, parameters, risk limits, or trading state
Cannot modify; cannot commit, push, PR, merge, deploy, or send an order.

## Fixed Doors

- Ruff format
- Ruff lint
- MyPy strict
- Pytest and branch coverage
- Bandit

It operates with fixed arguments without using the command shell. A door's failure
Does not prevent the operation of other doors. Command timeout limit is 600 seconds, job
The limit is 20 minutes. The second work is rejected by the lock at the same time.

## Evidence

Output is stored under `runtime/artifacts/quality/triage/`:

- `state.json`: atomic state snapshot of the last completed run
- `runs.jsonl`: secret-redacted append-only run log

CI artifact retention period is 30 days. Repository-local artifacts generated in the working tree
artifacts are not tracked by Git.

## Local Run

```powershell
.\.venv\Scripts\python.exe -m ai4binance.ops.quality_triage `
  --repository-root . `
  --output-directory artifacts\quality-triage `
  --revision LOCAL
```

Success is only accepted when all gates provide a zero exit code. For each result:

```text
mode=TRIAGE_ONLY
execution_allowed=false
live_eligibility_status=LIVE_ORDER_BLOCKED
```



