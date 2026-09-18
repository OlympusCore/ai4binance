---
document_id: AI4B-RADAR-RUN-001
title: AI4BINANCE GitHub Radar Engine
document_type: RUNBOOK
version: 1.0.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: github_radar_engine
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: github_radar_engine_workflow
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/workflows/runbook_github_radar_engine.md
---

# AI4BINANCE GitHub Radar Engine

GitHub Radar is not a repository selection engine. Core decision unit:

```text
repository@pinned_revision × atomic_capability
```

Each unit, along with its proof and risk, identifies which local capability gap, agent
It explains that the modern agent-stack layer is affected. Radar will never affect
code cloning, setup, import, execution, parameter upgrade or live order
Permission is not generated.

## Canonical Contracts

- `config/research/github_research_ontology.yaml`: R00-R30 domainleri, ilk 62
Atomic capability and V01-V12 validation profiles.
- `config/research/research_scoring.yaml`: hard gates and 100-point rubric.
- `config/research/repository_evaluation_schema.json`: evaluation output
For JSON Schema.

Points are only commented after hard gate review. Results from `POC`, separate
You do not have the authority to create a POC without human approval. `ADOPT_IDEA`, only for your idea
It is recommended to reapply locally in a clean and tested manner; dependency acquisition
It is not a decision to copy code.

## Yerel capability baseline

```powershell
.\.venv\Scripts\python.exe -m ai4binance.github_radar `
  --repository-root (Resolve-Path .).Path `
  baseline `
  --output artifacts\GitHubRadar\local_baseline.json
```

Baseline ontology, current agent registry, modern stack goals, file evidence
vNext gap audit is paired. A file's existence alone is not proof of production
It remains a blocker until the validation profiles are executed.

## Evaluate Previously Issued Evidence

```powershell
.\.venv\Scripts\python.exe -m ai4binance.github_radar `
  --repository-root (Resolve-Path .).Path `
  evaluate `
  --input tests\fixtures\github_radar\repository_evidence.json `
  --output artifacts\GitHubRadar\evaluation.json
```

Input: HTTPS URL without credential, 40-character pinned revision, license,
SHA-256 bound proof fragments, 12 rubric ratings, and passed hard gates are carried.
The result of the engine is currently the `ResearchCatalogEntry` contract with `RESEARCH_ONLY` as
links them. `execution_allowed=false` and `LIVE_ORDER_BLOCKED` are constants.

## Salt-okunur GitHub discovery

If the Anonim GitHub API limit is not sufficient, the token is only `GITHUB_TOKEN` environment
It is read from the variable; it does not appear in the command line or report.

```powershell
$env:GITHUB_TOKEN = "<session-secret>"
.\.venv\Scripts\python.exe -m ai4binance.github_radar `
  --repository-root (Resolve-Path .).Path `
  discover `
  --capability R26-C01 `
  --repositories-per-query 3 `
  --documents-per-repository 20 `
  --output artifacts\GitHubRadar\discovery.json
```

Discovery only makes GitHub HTTPS GET requests. By default, README,
LICENSE, `pyproject.toml`, requirements, docs, examples, and tests surfaces
okur; does not clone or import the repository code. Each file is hashed with SHA-256.
is connected to the evidence. Result `HUMAN_RATINGS_REQUIRED`
`LOCAL_REPRODUCTION_PENDING`, `EXTERNAL_CODE_INSTALL_BLOCKED`, and
`LIVE_ORDER_BLOCKED` blockers remain in effect.

## Phased Expansion

1. First slice: ontology, local baseline, scoring and Research Catalog connection.
2. Second slice: Read-only discovery via GitHub API, revision parsing,
Bounded document/test tree derivation and static risk scanning. Implemented.
3. Third slice: one-way adapter and ADR package to the stabil evidence graph surface.
4. Fourth slice: capability catalog reviewed by domain owners /no_stick
Expansion to over 300+ units in controlled party formats.

The second and subsequent slices do not grant new permissions. Clone/install/execute and POC are allowed for each
Time is separate and subject to explicit human approval.

## ELI10

Instead of bringing the entire big toy box of Radar home, focus on the missing single
Think of it as a checklist for searching a single part. A well-presented project on GitHub
When it finds it, it does not execute it. First, it writes about which small deficiency it could address, the evidence of the claim, and the risks.
The final word still belongs to humans and current security gates.
It says.


