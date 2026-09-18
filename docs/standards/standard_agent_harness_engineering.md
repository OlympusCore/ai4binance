---
document_id: AI4B-ARCH-STD-AGENT-HARNESS-001
title: AI4BINANCE Agent Harness Engineering Standard
document_type: STANDARD
version: 0.1.0
status: DRAFT
owner: Enterprise Architecture
technical_owner: Agent Governance
validation_owner: Quality Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_scope: agent_harness_engineering
authority_effect: NORMATIVE_CONSTRAINT
content_role: EXPLANATORY
source_of_truth: false
source_of_truth_scope: draft_standard
canonical_path: docs/standards/standard_agent_harness_engineering.md
machine_enforceable: false
audit_required: true
evidence_required: true
classification: INTERNAL
dependencies:
  - docs/governance/framework_core_vnext_governance.md
  - docs/registries/registry_agent_registry.md
  - docs/contracts/agent_contract_technical_analysis_agents.md
  - docs/standards/standard_technology_language_ownership.md
related_objects:
  - src/ai4binance/agents/catalog.py
  - src/ai4binance/agents/orchestrator.py
  - src/ai4binance/local_agent/advisory_runner.py
  - src/ai4binance/local_agent/advisory_harness.py
validated_by:
  - tests/governance/architecture/test_agent_harness_standard.py
---

# AI4BINANCE Agent Harness Engineering Standard

## ELI10

The agent harness is the controlled runtime shell around LLM and agent
components. It is not the deterministic trading core, risk engine, validation
engine, decision authority, or execution authority.

This draft records the target engineering shape for future activation. It does
not grant new tool access, framework adoption, strategy promotion, live order
permission, or risk-limit authority.

## 1. Purpose

The AI4BINANCE agent harness defines how advisory agent runs are bounded,
identified, tooled, observed, evaluated, and degraded without moving canonical
trading authority into an agent framework.

The harness owns:

- agent runtime admission;
- agent identity and authority ceilings;
- canonical context binding;
- governed tool gateway controls;
- structured request and response contracts;
- bounded orchestration state;
- policy and guardrail enforcement around advisory components;
- reliability, timeout, retry, cancellation, and fallback behavior;
- security and least-privilege controls;
- observability, evidence, provenance, and lineage;
- replay and evaluation of advisory behavior;
- resource, token, latency, and cost budgets.

The harness does not own:

- deterministic feature calculations;
- final trade decisions;
- risk limits;
- validation or OOS promotion gates;
- governance approval;
- execution eligibility;
- exchange order placement;
- live-order permission.

## 2. Authority Boundary

The agent harness is an engineering control layer around advisory and
orchestration components. It MUST preserve the repository authority split:

```text
DETERMINISTIC_QUALITY_GATE = TECHNICAL_TRUTH
DETERMINISTIC_GOVERNANCE_GATE = POLICY_ELIGIBILITY
HUMAN_GOVERNANCE = CONSEQUENTIAL_AUTHORITY
```

An agent framework, model provider, local LLM, or tool adapter MUST NOT become
an authority source for risk, validation, decision governance, promotion, or
execution.

Required outcomes remain:

```text
execution_allowed=false
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```

unless separately verified higher-authority gates establish a narrower
authorized state.

## 3. Canonical Placement

Frameworks are optional adapters. The canonical harness contracts belong to
AI4BINANCE.

```text
AI4BINANCE Agent Harness Contracts
        |
        +-- Native Python Runtime
        +-- Optional Framework Adapter
        +-- Optional Provider Adapter
```

Do not embed the deterministic core inside LangGraph, CrewAI, AutoGen, OpenAI
Agents SDK, or any other agent framework. A framework adapter may coordinate
advisory work only after the AI4BINANCE harness has already enforced identity,
authority, tool, context, contract, policy, reliability, security, observability,
evidence, evaluation, and resource controls.

The governing rule is:

```text
Harness agents. Do not harness the deterministic core inside an agent framework.
```

## 4. Control Domains

The governed agent harness SHOULD be designed across twelve control domains:

| Domain | Required control |
| --- | --- |
| Identity and Authority | Bind each run to an agent identity, version, role, authority ceiling, allowed operations, and forbidden operations. |
| Context and Snapshot Binding | Bind every advisory run to the same cycle, snapshot, canonical features, source timestamps, and policy versions. |
| Governed Tool Gateway | Mediate tool requests through authority, policy, argument, classification, rate, cost, timeout, output, and evidence checks. |
| Contract and Structured Output | Accept only typed requests, tool calls, observations, results, failures, audit events, and evaluation records. |
| Orchestration and State | Keep application orchestration separate from risk, validation, governance, and execution authority. |
| Policy and Guardrails | Enforce prompt, model, tool, side-effect, data, and authority limits before provider invocation. |
| Reliability and Resilience | Use bounded timeout, retry, backoff, cancellation, idempotency, duplicate suppression, and fail-safe degradation. |
| Security | Preserve least privilege, credential isolation, data classification, prompt-injection handling, and quarantine paths. |
| Observability | Record model, prompt, tool, policy, latency, token, failure, fallback, and authority events. |
| Evidence and Lineage | Link cycle, snapshot, agent run, tool call, observation, evidence, risk, validation, decision, and audit trail identifiers. |
| Evaluation and Replay | Test contract compliance, tool-use accuracy, hallucination risk, evidence completeness, authority compliance, replay consistency, and failure behavior. |
| Resource Governance | Bound token, latency, concurrency, retry, provider, and cost budgets. |

## 5. Required Run Identity

Every admitted agent run SHOULD carry at least:

```text
agent_id
agent_version
role
authority_level
allowed_tools
allowed_data_domains
allowed_operations
forbidden_operations
cycle_id
snapshot_id
policy_version
prompt_version
model_id
model_version
```

Missing identity, missing authority ceiling, or missing snapshot binding MUST
fail closed for trading-sensitive workflows.

## 6. Canonical Context Binding

Agents MUST NOT fetch independent ungoverned market data for a decision cycle.

Correct flow:

```text
Market Sources
  -> Data Quality
  -> Normalization
  -> Canonical Features
  -> Immutable MarketSnapshot
  -> Agent Harness
  -> Bounded Advisory Observations
```

The invariant is:

```text
same decision cycle
= same snapshot_id
= same canonical features
= same source timestamps
```

If an agent needs fresher data, the application must start or request a new
governed cycle. The agent must not silently mix data vintages inside the active
cycle.

## 7. Governed Tool Gateway

Tool access MUST flow through a gateway:

```text
Agent
  -> Tool Request
  -> Authority Check
  -> Policy Check
  -> Argument Validation
  -> Data Classification Check
  -> Rate, Cost, and Timeout Check
  -> Tool Execution
  -> Output Validation
  -> Evidence Envelope
  -> Agent
```

Each tool definition SHOULD declare:

```text
tool_id
tool_version
risk_class
read_write_mode
allowed_roles
timeout_ms
retry_policy
rate_limit
schema
side_effect_class
audit_required
```

Default classifications:

| Side-effect class | Meaning | Baseline agent handling |
| --- | --- | --- |
| CLASS_0_PURE | No external side effect | Allowed when contract-valid. |
| CLASS_1_READ_ONLY | External or repository read | Controlled and audited. |
| CLASS_2_CONTROLLED_WRITE | Internal bounded state write | Governed and idempotent. |
| CLASS_3_CONSEQUENTIAL | Trading, risk, config, security, credential, or authority change | Blocked unless explicitly authorized by higher governance. |

`live_order_tool` is `CLASS_3_CONSEQUENTIAL` and remains unavailable to agents
under the default AI4BINANCE safety posture.

## 8. Structured Contracts

Agents MUST NOT pass unvalidated free text as machine authority. Narrative may
be generated for humans after structured evidence is produced.

Required contract families include:

- `AgentRequestEnvelope`;
- `AgentRunContext`;
- `ToolInvocationRequest`;
- `ToolInvocationResult`;
- `AgentObservation`;
- `AgentEvidence`;
- `AgentResult`;
- `AgentFailure`;
- `AgentEvaluationResult`;
- `AgentAuditEvent`.

An observation SHOULD bind:

```text
observation_type
cycle_id
snapshot_id
symbol
timeframe
finding
supporting_evidence
counter_evidence
confidence
limitations
producer.agent_id
```

## 9. Orchestration Boundary

The application orchestrator may call agents and deterministic services. It
MUST NOT transfer final business-state ownership to an agent orchestrator.

Authority remains:

| Capability | Owner |
| --- | --- |
| Risk authority | Deterministic risk engine |
| Validation authority | Deterministic validation engine |
| Decision authority | Deterministic decision governance |
| Execution eligibility | Governance and execution gates |
| Human approval | Human governance |
| Advisory explanation | Agent harness or provider adapter |

## 10. Reliability Rules

Retry policy MUST depend on failure class:

| Failure | Baseline behavior |
| --- | --- |
| HTTP timeout | Bounded retry may be allowed. |
| Provider unavailable | Degrade advisory capability. |
| Schema violation | Reject; do not retry blindly. |
| Authority denied | Reject; do not retry. |
| Governance blocker | Reject; do not retry. |
| Prompt injection detected | Quarantine and block. |
| Invalid tool arguments | Reject. |
| Token budget exceeded | Terminate safely. |

LLM unavailability MUST NOT break the deterministic core. The deterministic
pipeline should remain able to produce `WAIT`, `NO_TRADE`, `RESEARCH_ONLY`,
`PAPER_ONLY`, or `LIVE_ORDER_BLOCKED` outcomes without provider availability.

## 11. P0 Harness Invariants

The following invariants are mandatory for any future active harness policy:

```text
AGENT_CANNOT_EXECUTE_ORDERS
AGENT_CANNOT_OVERRIDE_RISK
AGENT_CANNOT_OVERRIDE_VALIDATION
AGENT_CANNOT_OVERRIDE_GOVERNANCE
AGENT_CANNOT_PROMOTE_STRATEGY
AGENT_CANNOT_CHANGE_RISK_LIMITS
AGENT_CANNOT_FETCH_UNGOVERNED_MARKET_DATA
AGENT_MUST_USE_CANONICAL_SNAPSHOT
AGENT_TOOL_CALLS_MUST_BE_AUDITED
AGENT_OUTPUT_MUST_VALIDATE_AGAINST_CONTRACT
AGENT_FAILURE_MUST_FAIL_SAFE
LLM_FAILURE_MUST_NOT_BREAK_DETERMINISTIC_CORE
SIDE_EFFECTING_TOOLS_MUST_REQUIRE_EXPLICIT_AUTHORITY
DUPLICATE_TOOL_CALLS_MUST_NOT_CREATE_DUPLICATE_SIDE_EFFECTS
```

## 12. P0 Test Set

Any activation from this draft to an enforceable standard MUST include tests for:

- same snapshot and same policies produce the same deterministic final decision;
- agent unavailable leaves deterministic pipeline available;
- tool timeout uses bounded fallback;
- tool denial has no bypass;
- invalid structured output is rejected;
- stale snapshot cannot authorize a trade;
- prompt injection preserves authority boundaries;
- duplicate tool call remains idempotent;
- risk veto produces `NO_TRADE`;
- validation veto produces `NO_TRADE`;
- governance conflict produces `BLOCKED`;
- agent live-order request produces `LIVE_ORDER_BLOCKED`;
- token budget exhaustion terminates safely.

## 13. Appropriate Agent Uses

Agent or LLM use is appropriate for:

- news interpretation;
- multi-source synthesis;
- technology intelligence;
- audit explanation;
- research planning;
- failure diagnosis;
- strategy critique;
- experiment proposal;
- human-readable decision explanation.

Deterministic services MUST remain responsible for:

- RSI, ATR, EMA, VWAP, spread, and slippage calculation;
- position sizing;
- risk limits;
- leverage constraints;
- data freshness;
- schema validation;
- portfolio exposure;
- OOS gates;
- decision rules;
- execution eligibility.

## 14. Activation Requirements

This draft MUST NOT be treated as active source of truth until a governed change
adds the required policy-as-code projection, schema, registry links, document
lock approval evidence, implementation hooks, and validation evidence.

Activation requires at minimum:

- explicit owner approval;
- document lock registration for the active checksum;
- registry and documentation index alignment;
- machine-readable policy projection;
- schema validation;
- repository validator integration;
- focused success and fail-closed tests;
- canonical quality-gate evidence on a stable repository subject;
- preserved `execution_allowed=false`, `RESEARCH_ONLY`, and
  `LIVE_ORDER_BLOCKED` unless a higher-authority gate separately narrows the
  scope.

Until then this document is a draft engineering target and a guardrail for
future design work, not an authority expansion.

---

**End of Standard**
