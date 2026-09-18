---
document_id: AI4B-SKILL-POL-001
title: AI4BINANCE Skills Governance
document_type: POLICY
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L2_GOVERNANCE_COMPLIANCE
authority_scope: skills_governance
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/governance/policy_skills_governance.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# AI4BINANCE Agent Skills Governance

## ELI10

This document explains the usage rules for agent skills. Skill files are good
It can carry thoughts and procedures, but it cannot start the vehicle without a security review.
cannot install itself or obtain trading authority.


Agent Skills are useful for packaging procedural agent guidance, examples,
scripts, references, and templates.  In AI4BINANCE they are advisory workflow
assets only.

## Boundary

- `AGENTS.md` remains the always-on project contract.
- `.agents/skills/*/SKILL.md` files are task-specific procedural guidance.
- A skill may improve implementation, review, validation, or documentation
  workflows.
- A skill must not generate final trading signals, approve risk, place orders,
  install external dependencies, or bypass live gates.

## Local Audit

Run the read-only audit:

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli skills-audit --format text
```

The audit checks the Agent Skills frontmatter shape, naming, optional resource
folders, script presence, experimental tool declarations, and AI4BINANCE
authority drift terms.

Reviewed local skills should also declare governance metadata:

```yaml
metadata:
  ai4binance.authority: advisory-only
  ai4binance.version: "1"
  ai4binance.owner: QualityDepartmentManager
  ai4binance.trust_level: local
  ai4binance.last_reviewed: 2026-07-29
  ai4binance.trigger_examples: skills audit; quality gate loop
```

Long skills should use progressive disclosure: keep `SKILL.md` focused on
trigger, workflow, boundaries, and required references; move detailed examples
or scoring rubrics into `references/`.

## External Skills

External skills, repositories, marketplace items, shared chats, and copied
`SKILL.md` content are treated as hostile input until reviewed.  They require:

- credential-free HTTPS source URL;
- pinned revision or immutable content hash;
- license review;
- security review;
- sandbox review for scripts or tools;
- human approval before isolated reproduction.

Passing these checks still does not grant execution, installation, or live order
authority.

## Continuous Discovery

The optional continuous discovery loop is documented in
`docs/workflows/procedure_continuous_skill_discovery.md`. It may scout public repositories, filter
them deterministically, read bounded documentation, score reusable workflow
ideas, and write quarantined review packets under
`runtime/skill_staging/continuous-discovery/`.

It must not install discovered skills, run bundled scripts, import external
code, add dependencies, create live integrations, or publish/merge without human
approval. Every generated draft remains `HUMAN_REVIEW_REQUIRED`,
`RESEARCH_ONLY`, `execution_allowed=false`, `installation_allowed=false`, and
`LIVE_ORDER_BLOCKED`.

Candidates that are not admitted to the local skill library remain visible under
`runtime/skill_staging/continuous-discovery/_admit/<skill-name>/`. The
record includes the rejection reason, GitHub remediation search queries, and the
required `.çzüö` approval marker. When that marker is present, the record may
advance to `READY_FOR_LIBRARY_PR`; actual library admission still requires a
separate reviewed pull request.

## allowed-tools

The Agent Skills specification marks `allowed-tools` as experimental.  In this
project it is only a declaration of intent.  Enforced security must remain in
the deterministic governance, tool policy, supply-chain, risk, and execution
layers.

## Live Status

Skill governance always reports:

```text
promotion_status=RESEARCH_ONLY
execution_allowed=false
live_eligibility_status=LIVE_ORDER_BLOCKED
```
