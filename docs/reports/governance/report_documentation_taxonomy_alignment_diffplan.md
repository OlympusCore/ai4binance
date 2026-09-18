---
document_id: AI4B-GOV-EVID-DOC-TAX-DIFFPLAN-001
title: AI4BINANCE Documentation Taxonomy Alignment Diff Plan
document_type: EVIDENCE_REQUIREMENT
version: 1.0.0
status: ACTIVE
owner: Enterprise Engineering Governance
authority_level: ADVISORY
authority_layer: L8_REPORTS_EVIDENCE_INVENTORIES
authority_scope: documentation_taxonomy_alignment_diffplan
content_role: GENERATED
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/reports/governance/report_documentation_taxonomy_alignment_diffplan.md
created_at_utc: 2026-08-29T00:00:00Z
---

# AI4BINANCE Documentation Taxonomy Alignment Diff Plan

## ELI10

This report turns the `docs/README.md` and documentation-taxonomy gaps into one
bounded implementation plan. It is evidence-only. It does not rename files,
rewrite authority, or approve promotion by itself.

## Scope

- `docs/README.md`
- documentation taxonomy semantics that affect governed Markdown naming and
  `document_type` interpretation
- report and evidence metadata consistency under `docs/reports/**`

## Out of Scope

- governed file renames
- broad reclassification outside the documentation index and taxonomy surfaces
- runtime retention cleanup
- provider-adapter rewrites
- registry-wide metadata migration beyond the minimum taxonomy decision

## Verified Current State

- `docs/README.md` declares the documentation authority pyramid and is an
  approved docs-index filename exception.
- Authority layers 1 through 8 are structurally present in `docs/README.md`,
  but their tables are empty.
- Layer 9 currently contains mixed entries spanning contracts, governance,
  registries, reports, references, templates, architecture, ADR, compliance,
  controls, procedures, providers, runbooks, schemas, and standards.
- Existing `report_*` and `evidence_*` files under `docs/reports/**` use
  `document_type: EVIDENCE_REQUIREMENT`.
- Current validation controls explicitly enforce the governed Markdown naming
  pattern and approved location exceptions, but they do not resolve the
  semantic gap between `report_*` and `document_type: EVIDENCE_REQUIREMENT`.

## Gap Summary

| Gap | Current state | Risk | Bound |
| --- | --- | --- | --- |
| Authority index drift | `docs/README.md` leaves Layers 1-8 empty and uses Layer 9 as a mixed catch-all list. | Readers and agents can infer the wrong authority layer from the index. | Repair `docs/README.md` only. |
| Taxonomy drift | `report_*` and `evidence_*` filenames do not align cleanly with `document_type: EVIDENCE_REQUIREMENT`. | Naming rules and metadata semantics can diverge over time. | Decide taxonomy policy before renames. |
| Ambiguous remediation order | A direct rename-first fix can create duplicate source-of-truth or broken references. | Governance drift and validator churn. | Decide semantics first, then update index, then validate, then consider renames. |

## Decision Point

One bounded taxonomy decision is required before any wider cleanup:

1. Keep `document_type: EVIDENCE_REQUIREMENT` for report and evidence records,
   and explicitly document that `report_` and `evidence_` are approved filename
   families whose prefixes do not have to equal `document_type`.
2. Introduce narrower taxonomy values such as `REPORT` and `EVIDENCE`, then
   migrate metadata and validator expectations in one governed slice.

## Recommended Path

Recommended path: choose option 1 for the first bounded slice.

Reason:

- It repairs the interpretation surface without forcing immediate file renames.
- It minimizes lock-sensitive churn in governed documents.
- It preserves current report artifacts while making validator semantics
  explicit.
- It avoids creating a larger taxonomy migration before the index is corrected.

## Bounded Diff Sequence

1. Repair `docs/README.md` so each authority layer lists only the document
   families that belong to that layer.
2. Update the taxonomy-defining documentation surface so the relationship
   between `report_*`, `evidence_*`, and `document_type: EVIDENCE_REQUIREMENT`
   is explicit and machine-reviewable.
3. Update the validation control text only if needed to codify that bounded
   taxonomy clarification.
4. Re-run targeted hygiene and validator tests before considering any rename or
   split follow-up.

## Proposed File Impact

Files expected in the next implementation slice:

- `docs/README.md`
- `docs/standards/standard_repository_naming_governance.md`
- `docs/standards/standard_governed_knowledge_metadata.md`
- `docs/controls/control_repository_validation_rules.md`

Files intentionally excluded from the first implementation slice:

- `docs/reports/**` individual report bodies
- `factory/**`
- `runtime/**`
- provider adapter documents other than indirect index references

## `docs/README.md` Target State

The documentation index should be restored to this model:

- Layer 1: only local core-constitution level documents if any are explicitly
  designated under `docs/**`
- Layer 2: governance and compliance
- Layer 3: contracts and schemas
- Layer 4: standards, controls, and quality policy
- Layer 5: registries and roadmap
- Layer 6: architecture, ontology, and ADR
- Layer 7: workflows, procedures, runbooks, providers
- Layer 8: reports, evidence, inventories
- Layer 9: references and templates
- Layer 10: archive and structural placeholders

## Redteam Notes

- Do not let `docs/README.md` silently reclassify a document into a higher
  authority layer than its metadata supports.
- Do not rename `report_*` or `evidence_*` files before the taxonomy rule is
  explicit.
- Do not introduce a second active source of truth for report taxonomy in a new
  standalone note.
- Do not treat generated runtime Markdown as part of this taxonomy repair.

## Verification Plan

Targeted verification for the next implementation slice:

```powershell
PYTHONPATH=src .\.venv\Scripts\python.exe -m pytest tests/test_docs_hygiene.py -q
PYTHONPATH=src .\.venv\Scripts\python.exe -m pytest tests/test_repository_validator.py -q
PYTHONPATH=src .\.venv\Scripts\python.exe -m pytest tests/test_governance_constitution_sync.py -q
```

Optional broader follow-up after the bounded slice:

```powershell
.\scripts\quality.ps1
```

## Acceptance Criteria

- `docs/README.md` no longer uses Layer 9 as a mixed all-documents bucket.
- The taxonomy rule for `report_*` and `evidence_*` versus `document_type` is
  explicit in governed documentation.
- No new duplicate source-of-truth is created for documentation taxonomy.
- Targeted validator and docs-hygiene checks pass, or failures are reported
  explicitly as blockers.

## Safety

- This plan does not approve direct file renames.
- This plan does not weaken document-lock expectations.
- This plan does not change trading posture, which remains `RESEARCH_ONLY` and
  `LIVE_ORDER_BLOCKED`.
