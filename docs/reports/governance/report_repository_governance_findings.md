---
document_id: AI4B-GOV-EVID-REPO-FINDINGS-001
title: AI4BINANCE Repository Governance Findings
document_type: EVIDENCE_REQUIREMENT
version: 1.0.0
status: ACTIVE
owner: Enterprise Engineering Governance
authority_level: ADVISORY
authority_layer: L8_REPORTS_EVIDENCE_INVENTORIES
authority_scope: repository_governance_findings
content_role: GENERATED
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/reports/governance/report_repository_governance_findings.md
created_at_utc: 2026-08-19T19:55:22.364829+00:00
---

# AI4BINANCE Repository Governance Validation

## ELI10

This report checks whether repository files follow the governed knowledge and file-structure rules. It is report-only: it lists blockers but does not change files, approve trading or widen authority.

## Summary

- status: `PASS`
- policy: `AI4B-GOV-REPO-POLICY@1.0.0`
- artifact_count: `798`
- governed_knowledge_count: `112`
- finding_count: `0`
- blocker_count: `0`
- repository_health_score: `100`
- execution_allowed: `False`
- promotion_status: `RESEARCH_ONLY`
- live_eligibility_status: `LIVE_ORDER_BLOCKED`
- evidence_registry: `docs/registries/registry_evidence_registry.md`
- blocker_closure_map: `docs/reports/governance/report_platform_blocker_closure_map.md`

## Findings

- No findings.

## Recommended Actions

- No recommended actions.

## Dashboard Metrics

- root_clutter_count: `0`
- duplicate_source_of_truth_count: `0`
- unclassified_artifact_count: `0`
- cache_runtime_leakage_count: `0`
- stale_document_count: `0`
- missing_metadata_count: `0`
- broken_canonical_path_count: `0`
- policy_schema_mismatch_count: `0`
- unresolved_governance_blocker_count: `0`
- source_artifact_count: `636`
- governance_artifact_count: `162`
- runtime_artifact_count: `0`
- cache_artifact_count: `0`
- report_artifact_count: `0`
- archive_artifact_count: `0`

## Safety

- Repository validation is deterministic and report-only.
- It does not rewrite files, approve waivers, alter risk, or place orders.
- Live eligibility remains `LIVE_ORDER_BLOCKED`.
