---
document_id: AI4B-TIA-INS-001
title: AI4BINANCE Technology Intelligence Analyzer Instruction
document_type: INSTRUCTION
version: 1.0.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: technology_intelligence_analyzer
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: technology_intelligence_analyzer_workflow
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/workflows/instruction_technology_intelligence_analyzer.md
dependencies: 
implemented_by: 
validated_by: 
  - AI4B-EIEF-FRM-001
  - AI4B-EAACIE-INS-001
  - src/ai4binance/external_intel/technology/analyzer.py
  - config/research/technology_intelligence_criteria.yaml
  - tests/test_open_web_intelligence.py
---

# AI4BINANCE Technology Intelligence Analyzer Instruction

## ELI10

The Technology Intelligence Analyzer is a research filter. It looks for useful
technology developments, asks for evidence, checks risk and validation needs,
and keeps every output advisory-only. It does not install tools, promote
strategies, create trade signals, or grant live-order authority.

## Purpose

The analyzer classifies external technology evidence into governed research
areas for AI4BINANCE. Its output supports the External Intelligence and Evidence
Fabric, Auto-Audit, DGE visibility, YKB reporting, and controlled improvement
planning.

The analyzer answers this question:

```text
Does this development improve evidence quality, deterministic decision support,
validation depth, risk control, security, reproducibility, or auditability
without weakening the LIVE_ORDER_BLOCKED boundary?
```

## Authority Boundary

All analyzer outputs must preserve:

```text
decision_authority=ADVISORY_ONLY
promotion_status=RESEARCH_ONLY
execution_allowed=false
installation_allowed=false
live_eligibility_status=LIVE_ORDER_BLOCKED
```

The analyzer must not:

- create final trade signals;
- authorize live orders;
- change leverage, position sizing, or risk limits;
- install dependencies;
- execute external code;
- bypass provider terms, robots restrictions, or source access controls;
- treat social repetition as independent evidence;
- treat backtest success as production approval.

## Research Criteria

Each candidate must be mapped to at least one governed area.

| Area | Research question | Required evidence |
| --- | --- | --- |
| `data-engineering` | New data source, dataset, stream, schema, lineage, provenance, or freshness control? | Source provenance, freshness contract, schema validation, data-quality review. |
| `protocol-exchange-api` | New protocol, exchange API feature, market-data stream, endpoint, or tool protocol? | Official documentation, rate-limit review, authorization boundary, idempotency review. |
| `strategy-signal-research` | New algorithm, method, strategy, indicator, pattern, factor, or regime hypothesis? | Hypothesis register, leakage review, transaction-cost model, OOS validation path. |
| `model-method-optimization` | New model, optimization method, fine-tuning approach, embedding method, or AutoML pattern? | Model card, determinism or seed review, multiple-testing review, performance baseline. |
| `backtest-validation` | Better backtesting, walk-forward validation, OOS validation, benchmark design, or simulator realism? | Leakage review, time-series split review, walk-forward review, fee/slippage/fill review. |
| `risk-control` | Better drawdown, exposure, liquidity, correlation, kill-switch, or fail-closed risk controls? | Fail-closed state tests, limit invariant tests, risk veto review, human approval gate review. |
| `application-security` | Better security, supply-chain, prompt-injection, secrets, vulnerability, or abuse-case control? | Threat model, static security review, secret leak review, supply-chain review. |
| `blockchain-feature` | New on-chain, blockchain, mempool, wallet, bridge, tokenomics, or smart-contract intelligence? | Source provenance, wallet privacy boundary, chain finality review, smart-contract risk review. |
| `agent-architecture` | New AI skill, agent, multi-agent architecture, handoff, guardrail, or tool-use capability? | Typed state contract, least-privilege tool review, deterministic merge order, human approval gate. |
| `workflow-orchestrator-pipeline` | New loop, workflow, orchestrator, pipeline, durable execution model, scheduler, or autonomous routine? | Bounded concurrency, retry budget, degraded states, audit trace. |
| `ontology-knowledge-graph` | New ontology, semantic contract, entity-resolution, knowledge-graph, Graph RAG, or evidence-graph capability? | Source-of-truth review, entity/relationship contract review, provenance graph review. |

## Scoring Rubric

Use `config/research/technology_intelligence_criteria.yaml` as the
machine-readable scoring source.

Scores use a 0 to 5 scale and the following dimensions:

- `strategic_relevance`;
- `evidence_strength`;
- `validation_readiness`;
- `risk_reduction`;
- `determinism_compatibility`;
- `integration_cost_inverse`;
- `security_posture`;
- `local_only_compatibility`;
- `auditability`.

## Hard Gates

Any of the following blockers must stop promotion beyond research triage:

```text
NO_PRIMARY_SOURCE
NO_PROVENANCE
UNOFFICIAL_API
LICENSE_REVIEW_REQUIRED
LOOKAHEAD_RISK
DATA_LEAKAGE_RISK
UNBOUNDED_AUTONOMY
SECRET_EXPOSURE_RISK
LIVE_AUTHORITY_CONFUSION
NO_OOS_PATH
GOVERNANCE_CONFLICT
EXTERNAL_CODE_EXECUTION_REQUIRED
DEPENDENCY_INSTALL_REQUIRED_WITHOUT_APPROVAL
```

If the blocker can affect trading execution, the output must include:

```text
LIVE_ORDER_BLOCKED
```

## Output States

The analyzer may emit only the following governed statuses:

```text
WATCH
RESEARCH_CANDIDATE
EXPERIMENT_READY
VALIDATION_REQUIRED
PAPER_ONLY_CANDIDATE
REJECTED
BLOCKED
```

`EXPERIMENT_READY`, `VALIDATION_REQUIRED`, and `PAPER_ONLY_CANDIDATE` still do
not grant installation, production, or live-order authority.

## Workflow

```text
SOURCE
-> CLAIM
-> PRIMARY_SOURCE_CHECK
-> TECHNOLOGY_AREA_CLASSIFICATION
-> EVIDENCE_REQUIREMENT_MAPPING
-> HARD_GATE_REVIEW
-> SCORING
-> VALIDATION_PLAN
-> ADVISORY_OUTPUT
-> AUDIT_TRACE
```

## Acceptance Criteria

1. The analyzer keeps every output advisory-only.
2. Missing evidence remains explicit instead of being inferred.
3. Official sources are preferred for provider, protocol, exchange, and security
   claims.
4. Strategy, signal, model, and optimization claims require leakage and OOS
   validation paths.
5. Agent and workflow claims require typed state, least privilege, bounded
   concurrency, deterministic merge order, degraded states, and audit trace.
6. Security and blockchain claims require trust-boundary review before any
   experiment.
7. No candidate can remove `RESEARCH_ONLY`, `execution_allowed=false`, or
   `LIVE_ORDER_BLOCKED`.

## Live Compatibility

```text
RESEARCH_ONLY
execution_allowed=false
LIVE_ORDER_BLOCKED
```


