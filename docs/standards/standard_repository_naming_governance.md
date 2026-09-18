---
document_id: AI4B-GOV-STD-RFG-102
title: AI4BINANCE Repository Naming Governance Standard
document_type: STANDARD
version: 1.0.1
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_effect: NORMATIVE_CONSTRAINT
authority_scope: repository_naming_governance
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/standards/standard_repository_naming_governance.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
related_objects:
  - AI4B-GOV-FABRIC-001
---
# AI4BINANCE Repository Naming Governance Standard

## ELI10

This standard section defines folder, file, Markdown, and canonical path naming rules.

## Source Lineage

- Source file: `docs/standards/standard_repository_file_governance.md`
- Source section start: `## 7. Source Code Structure Standard`
- This file preserves a bounded section of the governed source document.

## 7. Source Code Structure Standard

The canonical Python source package structure is:

```text
src/
└── ai4binance/
    ├── core/
    ├── domain/
    ├── application/
    ├── infrastructure/
    ├── intelligence/
    ├── trading/
    ├── governance/
    ├── assurance/
    ├── learning/
    ├── reporting/
    ├── integrations/
    └── cli/
```

Recommended capability-level structure:

```text
src/ai4binance/intelligence/
├── market_regime/
├── structure/
├── support_resistance/
├── price_action/
├── candlestick/
├── patterns/
├── smc/
├── wyckoff/
├── fibonacci/
├── elliott/
├── trend/
├── momentum/
├── volatility/
├── volume/
├── volume_profile/
├── order_flow/
├── derivatives/
├── long_short/
├── whale/
├── on_chain/
└── news_social/
```

Folders should represent stable domains or capabilities, not temporary agent implementations.

Preferred:

```text
intelligence/whale/
```

Avoid:

```text
whale_agent/
```

Agent topology may change. Repository capability boundaries should remain stable.

## 8. Folder Naming Standard

Default folder naming convention:

```text
lower_snake_case
```

Rules:

```yaml
folder_naming:
  language: en-US
  style: lower_snake_case
  spaces: forbidden
  hyphens: forbidden
  uppercase: forbidden
  turkish_characters: forbidden
  ambiguous_abbreviations: forbidden
  version_suffixes: forbidden
  lifecycle_suffixes: forbidden
```

Valid examples:

```text
market_regime/
support_resistance/
price_action/
order_flow/
decision_governance/
walk_forward/
external_intelligence/
```

Invalid examples:

```text
MarketRegime/
market-regime/
Market_Regime/
market regime/
marketRegime/
trade_strategy_with_non_english_name/
final_folder/
```

## 9. File Naming Standard

Default source file naming convention:

```text
lower_snake_case
```

Python files must use:

```text
<responsibility>.py
```

Good examples:

```text
market_regime_detector.py
position_size_calculator.py
signal_score_calculator.py
decision_gate_evaluator.py
exchange_filter_validator.py
trailing_stop_manager.py
```

Low-quality names must be avoided:

```text
utils.py
helpers.py
common.py
misc.py
functions.py
manager.py
data.py
temp.py
new.py
test2.py
final.py
final_v2.py
```

Prefer focused names:

```text
price_rounding.py
timestamp_parser.py
symbol_normalizer.py
decision_lineage_builder.py
risk_budget_calculator.py
```

Reserved conventional file exceptions:

```text
README.md
AGENTS.md
LICENSE
CHANGELOG.md
CODEOWNERS
SECURITY.md
CONTRIBUTING.md
Dockerfile
Makefile
```

Source-of-truth governed Markdown files must not use uppercase letters in their
filenames unless the file is an explicitly reserved conventional filename.

Allowed reserved conventional exceptions:

```text
AGENTS.md
README.md
```

Incorrect source-of-truth examples:

```text
Policy_Main_Source.md
StandardRepositoryRules.md
```

Correct source-of-truth examples:

```text
policy_main_source.md
standard_repository_rules.md
```

## 10. Governed Markdown Naming Standard

Governed Markdown documents must use:

```text
<document_type>_<domain>_<subject>.md
```

Allowed common prefixes:

```text
policy_
standard_
framework_
registry_
control_
procedure_
runbook_
instruction_
contract_
interface_contract_
event_contract_
data_contract_
output_contract_
schema_
template_
reference_
report_
audit_
adr_
```

Examples:

```text
policy_holding_governance.md
framework_core_vnext_governance.md
standard_repository_file_governance.md
standard_documentation_knowledge_governance.md
registry_compliance_matrix.md
interface_contract_cli_command.md
event_contract_public_spot_stream.md
runbook_github_radar_engine.md
procedure_social_publishing_gateway.md
instruction_audit_trigger_engine.md
reference_binance_websocket_api.md
```

Versions, lifecycle states, owners, authority levels, and source-of-truth state must be stored in metadata, not in governed source document filenames.

Incorrect:

```text
policy_model_adaptation_governance_v2.md
draft_framework_core_vnext_governance.md
approved_registry_compliance_matrix.md
final_standard_repository_file_governance.md
```

Correct:

```text
policy_model_adaptation_governance.md
framework_core_vnext_governance.md
registry_compliance_matrix.md
standard_repository_file_governance.md
```

Filename families and `document_type` semantics must remain aligned, but the
prefix does not always have to be a literal one-to-one copy of the
`document_type` enum value.

Allowed bounded compatibility case:

- files in `docs/reports/**` may use `report_` or `evidence_` filename
  families while preserving `document_type: EVIDENCE_REQUIREMENT` when the
  document records generated findings, audit outputs, readiness records,
  inventories, migration manifests, or split manifests;
- this compatibility does not create a second source of truth for taxonomy;
- the governing taxonomy explanation must remain explicit in governed metadata
  and validation rules.

Incorrect drift examples:

```text
report_repository_findings.md with undocumented custom meaning
evidence_aims_record.md with conflicting document_type semantics
```

## 10A. Terminology Form Guidance

Terminology clarification must preserve semantic boundaries.

Form differences across prose, display labels, enums, and identifiers are
allowed only when the artifact role is clear and the variation does not change
the governed meaning.

Terminology-form guidance must not be used to justify semantic renames, source-
of-truth duplication, or repository-wide replacement programs.

### Validation Terminology Forms

For validation terminology families that already use bounded artifact-specific
forms:

- prose should prefer `out-of-sample` and `walk-forward`;
- display labels or enums may use `OOS` and `WalkForward`;
- identifiers may use `multi_regime_oos` and `walk_forward`.

Mixed forms are acceptable only when the artifact role remains explicit and the
semantic meaning stays unchanged.

### Registry Scope Qualifiers

When prose ambiguity matters, `registry` should be qualified by scope.

Preferred scoped phrases include:

- `governed document registry`;
- `runtime registry`;
- `config-backed registry`;
- `generated local registry`.

This guidance does not change the governed Markdown naming convention
`registry_*.md`.

### Semantic Boundary Protection

The following concept families must not be normalized into one shared term:

- `opportunity`, `signal`, and `decision`;
- `ontology`, `taxonomy`, and `registry`.

Clarification guidance must not be used to justify bulk rename proposals across
distinct governed concepts.

## 11. Canonical Path Standard

Canonical paths must be repository-relative.

Correct:

```text
docs/standards/standard_repository_file_governance.md
src/ai4binance/governance/repository_validator.py
schemas/governance/repository_artifact.schema.json
reports/audits/audit_repository_file_governance_20260817T180000Z.md
```

Incorrect:

```text
C:\vscode-projects\ai4binance\docs\standards\standard_repository_file_governance.md
H:\BackUP\Downloads\Repository-FileGovernanceStandard.md
Drive mirror path for docs/standards/standard_repository_file_governance.md
```

Machine-specific paths may be recorded as `mirror_path`, `source_attachment`, or `local_reference_path`, but never as `canonical_path`.

## 12. Deterministic Enforcement Projection

`policies/repository-validator/manifest-policy.json` remains the bounded,
non-authoritative policy projection for repository naming. The canonical
repository validator connects this scope to `AI4B-GOV-FABRIC-001` with the
distinct terminology and technology-language scopes.

This projection provides deterministic repository validation only. It does not
replace this standard, grant policy eligibility, authorize consequential
change, or alter `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED`.
