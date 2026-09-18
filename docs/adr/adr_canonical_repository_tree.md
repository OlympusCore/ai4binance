---
document_id: AI4B-GOV-ADR-001
title: AI4BINANCE Canonical Repository Tree Decision
document_type: ADR
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L6_ARCHITECTURE_ONTOLOGY_ADR
authority_scope: canonical_repository_tree
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/adr/adr_canonical_repository_tree.md
---

# AI4BINANCE Canonical Repository Tree Decision

## ELI10

This decision keeps source, governed knowledge, configuration, tests, tools, and
runtime output in separate folders so cleanup and validation cannot confuse code
with local evidence or private state.

## Decision

AI4BINANCE adopts the canonical repository tree recorded in
`docs/standards/standard_repository_structure_governance.md`.

The canonical tree defines repository placement and storage separation. It does
not define authority by folder position alone. Authority Pyramid assignment must
be derived from governed metadata, registered repository policy, canonical path
validation, successful validator checks, and downstream usage evidence. Folder
location is only one placement signal in that evidence set.

The canonical product-domain roots are:

- `docs/`
- `schemas/`
- `config/`
- `src/`
- `tests/`
- `migrations/`
- `scripts/`
- `tools/`
- `runtime/`

The canonical root files are:

- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
- `README.md`
- `pyproject.toml`
- `uv.lock`
- `.python-version`
- `.gitignore`
- `.gitattributes`
- `.env.example`

Repository support folders such as `.agents/`, `.codex/`, `.github/`,
`.vscode/`, and `factory/` remain allowed operational surfaces. They are not
canonical product-domain roots.

Historical runtime, evidence, or machine-mirror roots such as `artifacts/`,
`backtest/`, `data/`, `logs/`, `models/`, `ontology/`, `opportunities/`,
`reports/`, and the legacy top-level `state/` root remain read-compatible until
an approved migration record moves their contents to `runtime/state/`. New
mutable runtime state should target `runtime/state/` after the affected code
path has tests.

## Safety Constraints

- This decision does not authorize deletion of protected local state.
- This decision does not authorize movement of secrets, account data, local
  models, or validation evidence without an explicit migration manifest.
- Trading authority remains unchanged: `execution_allowed=false`,
  `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED`.

## Validation

The repository validator must represent this tree as policy. Folder cleanup and
runtime migration tools must remain report-only unless a human-approved apply
mode is explicitly invoked.
