---
document_id: AI4B-GOV-STD-RFG-101
title: AI4BINANCE Repository Structure Governance Standard
document_type: STANDARD
version: 1.0.5
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_scope: repository_structure_governance
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/standards/standard_repository_structure_governance.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# AI4BINANCE Repository Structure Governance Standard

## ELI10

This standard section defines canonical repository and docs folder structure.

## Source Lineage

- Source file: `docs/standards/standard_repository_file_governance.md`
- Source section start: `## 5. Canonical Repository Structure`
- This file preserves a bounded section of the governed source document.

## 5. Canonical Repository Structure

Repository filing governance follows the main authority and storage pyramid
below. Lower layers may implement higher layers, but they must not silently
override, weaken, or duplicate them with different semantics.

Authority pyramid assignment is metadata-driven, not folder-driven. A folder is
placement evidence only; it does not create authority by itself. The validator
must derive authority from the combined evidence set:

```text
authority = metadata + registered policy + canonical path + validation + downstream usage
```

When these signals disagree, the most conservative validated authority applies
and unresolved contradictions remain visible as governance findings instead of
being hidden by the document's folder location.

```text
L0  External Mandatory Constraints
    Regulations, legal/compliance constraints, exchange terms

L1  Core Constitution
    AI4BINANCE core principles, safety, trading authority, fail-closed rules

L2  Governance / Compliance
    Compliance matrix, governance framework, assurance rules

L3  Canonical Contracts
    Schemas, data contracts, event contracts, output contracts, decision contracts

L4  Repository Instructions
    AGENTS.md, provider instructions, root repository operating rules

L5  Standards / Policies / Controls
    File governance, documentation governance, security, lifecycle, naming

L6  Registries / Ontology / Workflows
    Agent registry, strategy registry, model registry, policy registry, ontology mappings

L7  Code / Configuration
    src, config, tests, tools, scripts

L8  Evidence / Runtime / Reports
    runtime/analysis, runtime/data, runtime/state, runtime/logs,
    runtime/audit, runtime/artifacts, runtime/reports, runtime/test,
    runtime/tmp
```

Within L8, `runtime/` is the canonical grouping root for mutable, generated,
reproducible, and execution/run-produced outputs. Those outputs must be routed
into the appropriate governed subtree under `runtime/` rather than spread
across legacy top-level roots.

Repository root describes the system; `runtime/` describes what the system
produces while operating. If deleting a file would make the repository
undefined or remove governed authority, that file must live outside
`runtime/` and under the governed source, policy, schema, registry, or docs
surface that owns it.

The canonical first-level runtime structure is:

```text
runtime/
├── analysis/
├── artifacts/
├── audit/
├── cache/
├── data/
├── logs/
├── reports/
├── state/
├── test/
└── tmp/
```

`runtime/analysis/` stores generated intermediate analysis outputs.
`runtime/test/` stores test-run outputs such as ACL, Hypothesis, pytest, and
repository-validator run bundles. `runtime/tmp/` remains the disposable
temporary subtree. Protected runtime support surfaces such as `runtime/models/`
may remain when an explicit consumer, retention rule, or protection policy
requires them; those surfaces do not weaken the canonical first-level runtime
tree.

`docs/` is the governed knowledge center. Source mirrors under `schemas/`,
`policies/`, `ontology/`, and `workflows/` must remain implementation or
machine-consumption mirrors unless a governed document explicitly declares them
as the canonical source for that concept.

The canonical top-level repository structure is:

```text
ai4binance/
├── AGENTS.md
├── CLAUDE.md
├── GEMINI.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
├── .gitattributes
├── .env.example
├── docs/
├── schemas/
├── config/
├── src/
├── tests/
├── migrations/
├── scripts/
├── tools/
└── runtime/
```

Top-level folders must represent stable repository domains, not temporary implementation choices.

Repository support folders such as `.agents/`, `.codex/`, `.github/`,
`.vscode/`, and `factory/` are allowed operational surfaces, but they are not
canonical product-domain roots. Historical or local-only roots such as
`artifacts/`, `backtest/`, `data/`, `logs/`, `models/`, `ontology/`,
`opportunities/`, `reports/`, and the legacy top-level `state/` root must be
treated as legacy or protected runtime or machine-mirror surfaces until an
approved migration record moves their contents under the canonical target
`runtime/state/`. They must not be promoted as canonical source-of-truth
locations.

Legacy runtime aliases such as `runtime/acl-test/` are not canonical first-level
runtime domains. New ACL test outputs must target `runtime/test/acl/`.

A folder must not simultaneously serve as:

- source code storage
- runtime state storage
- generated artifact storage
- human-readable report storage
- local-only cache storage

Incorrect:

```text
src/strategy/reports/
src/ai4binance/runtime_state/
docs/.pytest_cache/
```

Correct:

```text
src/ai4binance/trading/strategy/
runtime/reports/strategy/
runtime/state/
```

## 6. docs/ Folder Structure Standard

The canonical documentation structure is:

```text
docs/
├── README.md
├── governance/
│   ├── constitution/
│   ├── authority/
│   ├── decision/
│   ├── execution/
│   ├── promotion/
│   └── repository/
├── architecture/
│   ├── system/
│   ├── data/
│   ├── decision/
│   ├── runtime/
│   └── integration/
├── compliance/
├── policies/
├── controls/
├── standards/
├── contracts/
├── registries/
├── ontology/
├── workflows/
├── security/
├── assurance/
├── runbooks/
├── adr/
└── references/
```

`docs/registries/registry_documentation_index.md` may remain as the documentation map.

Within the canonical tree, `docs/governance/` groups governed constitutional,
authority, decision, execution, promotion, and repository-governance knowledge.
`docs/architecture/` groups system, data, decision, runtime, and integration
architecture knowledge. These subtrees define the canonical information
architecture even when older flat files still exist during an approved
migration window.

Canonical governed Markdown documentation must reside under `docs/` unless the
file is an approved repository entrypoint, provider adapter entrypoint, or a
scope-local instruction file whose location is required by repository/tool
discovery or filesystem scope semantics.

Approved Markdown location classes are:

```text
GOVERNED_CANONICAL_MD
  -> docs/**

DOCUMENTATION_INDEX_EXCEPTION_MD
  -> docs/README.md

ENTRYPOINT_OR_SCOPED_INSTRUCTION_MD
  -> README.md
  -> AGENTS.md
  -> CLAUDE.md
  -> GEMINI.md
  -> **/AGENTS.md

GOVERNED_OPERATIONAL_EXCEPTION_MD
  -> factory/brief.md
  -> factory/guide.md
  -> factory/handoff.md
  -> factory/plan.md
  -> factory/review.md

NONCANONICAL_OPERATIONAL_STATE_MD
  -> factory/log.md
  -> factory/progress.md
  -> factory/state.md

GENERATED_RUNTIME_MD
  -> runtime/**
```

`GENERATED_RUNTIME_MD` is not canonical governed documentation by default.
Human-readable runtime reports, audits, and diagnostics do not gain authority
merely because they use Markdown. A generated runtime Markdown artifact may
become governed documentation only through an explicit review, classification,
and promotion process.

`GOVERNED_OPERATIONAL_EXCEPTION_MD` is a narrow allowlisted exception class.
These files are governed operational workflow surfaces and must not be expanded
by convention alone. New members require explicit governance approval.

`DOCUMENTATION_INDEX_EXCEPTION_MD` is an approved docs-root navigation
exception. It remains an interpretation index and must not be treated as a
higher-authority governed source merely because it lives under `docs/`.

`NONCANONICAL_OPERATIONAL_STATE_MD` may remain outside `runtime/` only when a
specific workflow depends on path-stable local state surfaces. These files must
not declare canonical authority and must remain advisory or operational state,
not source-of-truth governance.

All other governed Markdown documents should follow:

```text
<document_type>_<domain>_<subject>.md
```

Examples:

```text
docs/standards/standard_repository_file_governance.md
docs/standards/standard_documentation_knowledge_governance.md
docs/references/reference_governed_knowledge_taxonomy.md
docs/contracts/interface_contract_cli_command.md
docs/contracts/event_contract_public_spot_stream.md
docs/runbooks/runbook_read_only_runtime.md
docs/controls/control_repository_validation_rules.md
```

Additional documentation support folders such as `procedures/`, `providers/`,
`roadmap/`, `schemas/`, `templates/`, `archive/`, and promoted evidence
surfaces such as `docs/reports/` may remain only when they have explicit
registry ownership and documented migration status. These legacy or support
surfaces must not be presented as the canonical `docs/` information
architecture. Operational plans, diff plans, implementation reports, and other
run-produced Markdown belong under `runtime/reports/`, not under `docs/`.

PascalCase documentation folders such as
`Docs/`, `Governance/`, `Contracts/`, `Standards/`, `Policies/`, `Registries/`,
`Schemas/`, `Workflows/`, and `Providers/` must be migrated to lowercase
canonical paths through an approved migration record.
