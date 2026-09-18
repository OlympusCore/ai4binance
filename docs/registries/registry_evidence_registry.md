---
document_id: AI4B-GOV-REG-EVID-001
title: AI4BINANCE Evidence Registry
document_type: REGISTRY
version: 1.0.0
status: ACTIVE
owner: Audit Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: evidence_registry
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/registries/registry_evidence_registry.md
schema_refs:
  - schemas/governance/repository_artifact.schema.json
validated_by:
  - src/ai4binance/governance/repository_validator.py
  - tests/test_repository_validator.py
---

# AI4BINANCE Evidence Registry

## ELI10

This registry tracks evidence artifacts used for audit, validation, and decision lineage.

## Registry Contract

Evidence entries must identify source artifact, hash/provenance where safe, generated time, retention class, and consumer claims.

| evidence_id | name | owner | lifecycle_status | source_artifact | retention_class | claim_binding |
| --- | --- | --- | --- | --- | --- | --- |
| PENDING | Pending canonical evidence entry | Audit Governance | DRAFT | PENDING | AUDIT_REQUIRED | PENDING |
| AIO-EVID-001 | AI orchestration operational readiness KPI evidence | Enterprise Governance | ACTIVE | `docs/reports/governance/evidence_ai_orchestration_operational_readiness.md` | AUDIT_REQUIRED | Supports report-only/advisory AI orchestration governance readiness; does not support live or deployment readiness |
| AIO-EVID-002 | AI orchestration per-agent review records | Enterprise Governance | ACTIVE | `docs/reports/governance/evidence_ai_orchestration_agent_review_records.md` | AUDIT_REQUIRED | Supports per-agent role-package review completion for `AIO-MAO-001` |
| AIO-EVID-003 | AI orchestration AIMS risk-impact records | Enterprise Governance | ACTIVE | `docs/reports/governance/evidence_ai_orchestration_risk_impact_records.md` | AUDIT_REQUIRED | Supports AIMS risk-impact closure for `AIMS-AI-008` only |
| AIMS-EVID-001 | AIMS baseline control record | Enterprise Governance | ACTIVE | `docs/reports/governance/evidence_aims_baseline_control_record.md` | AUDIT_REQUIRED | Supports internal AIMS documentation baseline control coverage; does not support certification or live readiness |
| AIMS-EVID-002 | AIMS per-system risk and impact records | Enterprise Governance | ACTIVE | `docs/reports/governance/evidence_aims_per_system_risk_impact_records.md` | AUDIT_REQUIRED | Supports internal AIMS risk-impact baseline for `AIMS-AI-001` through `AIMS-AI-007` |
| AIMS-EVID-003 | AIMS provider control review | Security and Privacy Governance | ACTIVE | `docs/reports/governance/evidence_aims_provider_control_review.md` | AUDIT_REQUIRED | Supports internal provider-control baseline; provider output remains advisory-only |
| AIMS-EVID-004 | AIMS internal audit schedule | Audit Governance | ACTIVE | `docs/reports/governance/evidence_aims_internal_audit_schedule.md` | AUDIT_REQUIRED | Supports internal AIMS audit-program scheduling and review cadence |
| AIMS-EVID-005 | AIMS management review minutes | Enterprise Governance | ACTIVE | `docs/reports/governance/evidence_aims_management_review_minutes.md` | AUDIT_REQUIRED | Supports internal management review record for documentation baseline only |
| AIMS-EVID-006 | AIMS CAPA records | Quality Governance | ACTIVE | `docs/reports/governance/evidence_aims_capa_records.md` | AUDIT_REQUIRED | Supports closure of internal AIMS baseline evidence gaps; external certification remains excluded |
| AIMS-EVID-007 | AIMS platform blocker closure map | Quality Governance | ACTIVE | `docs/reports/governance/report_platform_blocker_closure_map.md` | AUDIT_REQUIRED | Supports traceable closure mapping for remaining platform blockers; does not support live readiness |
