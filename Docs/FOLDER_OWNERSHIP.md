# Folder Ownership Matrix

This matrix keeps cleanup decisions reviewable. Generated folders may be pruned
after approval; protected and evidence folders need an owner decision first.

Decision values:

- `KEEP_DOMAIN_ROOT`: expected project root, keep even when empty.
- `ARCHIVE_LOCAL`: local/evidence output; archive or prune only by policy.
- `DELETE_EMPTY`: may be removed when confirmed empty and unreferenced.
- `PROTECTED`: never broad-delete or stage content.
- `GENERATED`: reproducible output; cleanup requires explicit mode or `-Apply`.

| Path | Owner area | Type | Decision | Retention | Notes |
| --- | --- | --- | --- | --- | --- |
| `.pytest_cache` | Quality | Generated cache | GENERATED | diagnose first | Current blocker: ACL/ownership diagnosis before forced cleanup. |
| `.mypy_cache` | Quality | Generated cache | GENERATED | on demand | Recreated by MyPy. |
| `.ruff_cache` | Quality | Generated cache | GENERATED | on demand | Recreated by Ruff. |
| `.test-tmp` | Quality | Generated temp | GENERATED | on demand | Historical test temp. |
| `Artifacts/TestTemp` | Quality | Generated temp | GENERATED | 2 days | Use unique pytest basetemp directories. |
| `Logs` | Observability | Generated evidence | ARCHIVE_LOCAL | 7 days active | Archive stale logs, do not bulk delete. |
| `Artifacts/maintenance-archive` | Maintenance | Generated archive | ARCHIVE_LOCAL | manual | Contains cleanup manifests and archived logs. |
| `Artifacts/folder-structure-audit` | Maintenance | Generated report | GENERATED | latest local | Ignored from Git. |
| `Backtest/validation` | Research validation | Evidence | ARCHIVE_LOCAL | explicit scope | Supports RESEARCH_ONLY decisions. |
| `Data` | Data acquisition | Domain state | KEEP_DOMAIN_ROOT | manual | May contain reproducibility inputs. |
| `State` | Runtime state | Domain state | KEEP_DOMAIN_ROOT | manual | Avoid deleting active runtime state. |
| `State/private` | Private runtime state | Protected local state | PROTECTED | never broad-delete | May contain private local-only data. |
| `Secrets` | Security | Protected local state | PROTECTED | never broad-delete | Only `.gitkeep` is commit-eligible. |
| `Models` | Local LLM | Protected local state | PROTECTED | manual | Large local models or placeholders. |
| `Wallet` | Portfolio/accounting | Domain evidence | KEEP_DOMAIN_ROOT | manual | Wallet state must not contaminate backtests. |
| `Orders` | Execution/audit | Domain evidence | KEEP_DOMAIN_ROOT | manual | Preserve rejected order and blocker evidence. |
| `Opportunities` | Advisory radar | Domain evidence | KEEP_DOMAIN_ROOT | manual | Keep blocked opportunity context auditable. |
| `Alerts` | Notifications | Project folder | DELETE_EMPTY | manual | Remove only if empty and unreferenced. |
| `Analysis` | Research/reporting | Project folder | ARCHIVE_LOCAL | manual | Review useful reports before pruning. |
| `factory` | Agent planning | Project folder | ARCHIVE_LOCAL | manual | Governance/planning surface. |
| `Futures` | Supplementary research | Project folder | DELETE_EMPTY | manual | Spot decisions remain primary. |
| `Spot` | Spot domain | Project folder | KEEP_DOMAIN_ROOT | manual | Expected platform domain folder. |
| `intelligence` | Market intelligence | Project folder | DELETE_EMPTY | manual | Remove only if empty and unreferenced. |
| `News` | Sentiment/news | Project folder | DELETE_EMPTY | manual | External inputs need provenance. |
| `Tools` | Local tooling | Project folder | KEEP_DOMAIN_ROOT | manual | Avoid deleting configured local LLM tools. |

Safety defaults stay unchanged: `execution_allowed=false`,
`live_eligibility_status=LIVE_ORDER_BLOCKED`.
