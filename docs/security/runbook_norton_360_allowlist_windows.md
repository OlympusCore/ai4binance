---
document_id: AI4B-SEC-RUN-002
title: AI4BINANCE Norton 360 Allowlist for Windows
document_type: RUNBOOK
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: norton_360_allowlist_windows
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/security/runbook_norton_360_allowlist_windows.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---

# AI4BINANCE Norton 360 Allowlist for Windows

This runbook defines the manual Norton 360 allowlist procedure for the local
Windows AI4BINANCE workstation when a third-party antivirus product is present.
It does not grant trading authority, relax execution controls, or override the
fail-closed runtime posture.

## ELI10

Norton can spend time rescanning large local AI4BINANCE folders that change all
the time. This checklist tells the operator how to exclude only the known
high-churn local workspace folders so the machine stays responsive without
opening broader security gaps.

The system remains:

```text
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```

## Verified Source

This runbook was prepared on 2026-08-25 using Norton official support guidance
for Windows exclusion paths and false-positive handling. UI labels can drift
slightly across Norton 360 releases, but the validated navigation patterns were:

- `Security -> Antivirus -> Exclusions -> Add exclusion`
- `Security -> Advanced Security -> Computer -> Antivirus -> Exclusions -> Add`

## Preconditions

Before making changes, confirm all of the following:

1. You are on the local `ZEUS` Windows workstation.
2. The repository root is `C:\vscode-projects\ai4binance`.
3. You are signed in with a Windows administrator account.
4. The target exclusions are local AI4BINANCE workspace folders only.
5. You are not excluding the entire `C:\` drive, user profile, browser
   downloads, or general-purpose folders unrelated to AI4BINANCE.

## Approved Folder Allowlist

Add only the following repository-local folders:

```text
C:\vscode-projects\ai4binance\.venv
C:\vscode-projects\ai4binance\artifacts
C:\vscode-projects\ai4binance\backtest
C:\vscode-projects\ai4binance\data
C:\vscode-projects\ai4binance\logs
C:\vscode-projects\ai4binance\models
C:\vscode-projects\ai4binance\reports
C:\vscode-projects\ai4binance\runtime
C:\vscode-projects\ai4binance\runtime\skill_staging
C:\vscode-projects\ai4binance\state
C:\vscode-projects\ai4binance\tools
```

Do not add:

- `C:\`
- `C:\Users\husey`
- `C:\Users\husey\Downloads`
- browser cache folders
- email attachment folders
- unrelated development workspaces

## Primary Procedure

1. Open `Norton 360`.
2. In the left navigation, click `Security`.
3. Open the `Antivirus` area.
4. Open the `Exclusions` tab.
5. Click `Add exclusion` or `Add`.
6. Browse to one approved AI4BINANCE folder.
7. Confirm the selection with `Open` or `Save`.
8. Repeat until all approved folders are present.
9. Close Norton 360 after the list is complete.

If the product shows the older or alternate Windows layout, use:

1. Open `Norton 360`.
2. Click `Security`.
3. Go to `Advanced Security`.
4. Open `Computer`.
5. Open `Antivirus`.
6. Open `Exclusions`.
7. Click `Add`.
8. Add each approved folder one by one.

## Post-Change Validation

After the allowlist is complete, validate from the repository root:

```powershell
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\optimize_windows_ai4binance.ps1 -Apply
```

Expected output characteristics:

```text
active_power_scheme = Turbo
preferred_power_scheme = Turbo
power_plan = ALREADY_OPTIMAL
long_paths = ALREADY_ENABLED
execution_allowed = false
promotion_status = RESEARCH_ONLY
live_eligibility_status = LIVE_ORDER_BLOCKED
defender_exclusion = THIRD_PARTY_AV_PRESENT_MANUAL_REVIEW_REQUIRED
norton_allowlist = MANUAL_PRODUCT_UI_REQUIRED
```

The script does not read Norton's internal exclusion list. Validation is
operational:

- local indexing optimization remains applied,
- antivirus status still shows a third-party product is present,
- AI4BINANCE remains fail-closed,
- repeated builds, tests, and runtime activity should feel lighter on the local
  machine.

## If Norton Blocks a Known-Safe File

If Norton still quarantines or flags a known-safe local artifact:

1. Do not disable all protection as a first response.
2. Record the exact file path and alert text.
3. Confirm the file is inside the approved AI4BINANCE workspace scope.
4. Re-check that the parent folder is already allowlisted.
5. If needed, submit the file to Norton as a false positive through the Norton
   Submission Portal.
6. Preserve:

```text
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```

## Rollback

If a folder was excluded by mistake:

1. Open `Norton 360`.
2. Go back to `Security -> Antivirus -> Exclusions`.
3. Hover over or select the incorrect exclusion.
4. Remove the exclusion using the UI remove action.
5. Re-run the optimization script without changing execution authority.

## Audit Notes

- This is a local workstation performance and stability control only.
- It does not authorize live trading.
- It does not widen tool permissions.
- It does not weaken repository governance.
- It should be revisited whenever Norton 360 significantly changes the Windows
  product UI.
