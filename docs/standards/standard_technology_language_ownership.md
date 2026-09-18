---
document_id: AI4B-ARCH-STD-LANG-001
title: AI4BINANCE Technology Language Ownership and Usage Standard
document_type: STANDARD
version: 1.0.1
status: ACTIVE
owner: Enterprise Architecture
technical_owner: Engineering Governance
validation_owner: Quality Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_scope: technology_language_ownership
authority_effect: NORMATIVE_CONSTRAINT
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/standards/standard_technology_language_ownership.md
related_objects:
  - AI4B-GOV-FABRIC-001
machine_enforceable: true
audit_required: true
evidence_required: true
classification: INTERNAL
dependencies:
  - docs/governance/framework_core_vnext_governance.md
  - docs/standards/standard_governed_knowledge_metadata.md
  - docs/standards/standard_repository_file_governance.md
related_objects:
  - config/governance/technology_language_ownership.yaml
  - schemas/governance/technology_language_ownership.schema.json
implemented_by:
  - src/ai4binance/governance/technology_language_policy.py
  - src/ai4binance/governance/repository_validator.py
validated_by:
  - tests/governance/architecture/test_technology_language_policy.py
---

# AI4BINANCE Technology Language Ownership and Usage Standard

## ELI10

This standard decides which implementation technologies may own each technical
responsibility. It binds production code, services, adapters, user interfaces,
scripts, build logic, and operational tooling. It does not redefine domain,
risk, trading, compliance, or canonical schema field semantics.

## 1. Purpose

This standard defines the approved programming, query, configuration, contract, presentation, and automation languages for AI4BINANCE EnterpriseAI vNext.

Its objectives are to:

- preserve a clear language ownership model;
- prevent uncontrolled polyglot architecture;
- assign each language to a bounded technical responsibility;
- protect deterministic and auditable decision boundaries;
- minimize duplicate implementations;
- improve runtime performance where evidence justifies native acceleration;
- reduce build, deployment, testing, and maintenance complexity;
- preserve interoperability through explicit contracts;
- prevent scripting and UI technologies from owning trading, risk, or governance decisions;
- enforce evidence-based migration of performance-critical code.

This standard does **not** authorize a language merely because it appears in the approved technology set. New usage must remain justified by architecture, benchmark evidence, and repository governance.

### 1.1 Normative Authority Boundary

This document is the single canonical source for
`technology_language_ownership`. It has `NORMATIVE_CONSTRAINT` effect over:

- language ownership;
- runtime responsibility;
- implementation boundaries;
- cross-language interoperability;
- technology adoption gates;
- scripting boundaries;
- performance-language promotion.

It is binding on production source code, services, libraries, scripts, adapters,
frontend implementation, build logic, and operational tooling.

It is not authoritative for:

- enterprise constitution;
- domain semantics;
- risk or trading policy definitions;
- canonical schema field semantics;
- compliance requirements owned by higher authority;
- promotion, execution, or live-order permission.

Authority comparisons MUST be resolved only within the same
`authority_scope`. A technology implementation must satisfy both this standard
for technology ownership and the applicable domain contract for domain
semantics. Compliance with either source does not compensate for a violation of
the other.

The machine-readable policy at
`config/governance/technology_language_ownership.yaml` is an enforcement
projection of this standard. It is not a second source of normative authority.

---

## 2. Core Principles

The following rules are mandatory:

1. **Python remains the canonical application and orchestration language.**
2. **Rust is the preferred deterministic native CPU acceleration language.**
3. **CUDA C++ is reserved for justified GPU-compute workloads.**
4. **SQL owns persistent analytical query logic, not application business logic.**
5. **TypeScript owns the human-facing web application layer.**
6. **CSS owns presentation only.**
7. **Go is permitted for high-throughput networking and ingestion services only when benchmark evidence justifies a separate service.**
8. **Julia is restricted to quantitative research, numerical experimentation, simulation, and validated research tooling.**
9. **Java 25+ is permitted only for justified long-running streaming or event-processing services where it provides measurable architectural value.**
10. **PowerShell owns Windows operational automation.**
11. **Bash owns Linux, container, and CI operational automation.**
12. **YAML/TOML are configuration formats, not business-rule engines.**
13. **JSON Schema defines machine-readable contracts and validation boundaries.**
14. **No scripting, UI, configuration, or research language may bypass deterministic trading, risk, validation, compliance, or governance controls.**
15. **No benchmark means no performance-driven rewrite.**

---

## 3. Canonical Technology Language Stack

| Priority | Technology | Canonical Responsibility | Authority Level |
|---:|---|---|---|
| 1 | Python 3.14 | Intelligence, orchestration, application logic, governance integration | Primary |
| 2 | Rust | Deterministic CPU performance and native hot paths | Performance Core |
| 3 | CUDA C++ | GPU acceleration and massively parallel compute | GPU Core |
| 4 | SQL | Persistent analytical data access and query execution | Data |
| 5 | TypeScript | Human interface and web application layer | Presentation/Application Edge |
| 6 | CSS | Visual presentation and design system | Presentation |
| 7 | Go | High-throughput networking, ingestion, WebSocket/data services | Specialized Service |
| 8 | Julia | Quant research, simulations, numerical algorithms | Research |
| 9 | Java 25+ | Streaming/event systems and long-running backend services | Specialized Service |
| 10 | PowerShell | Windows operations and developer tooling | Operations |
| 11 | Bash | Linux, containers, CI/CD, operational scripting | Operations |
| 12 | YAML/TOML | Declarative configuration | Configuration |
| 13 | JSON Schema | Contracts, validation, governed-object schemas | Contract Authority |

---

## 4. Language Authority Model

```text
                         AI4BINANCE EnterpriseAI vNext
                                      |
                         +------------+------------+
                         |                         |
                 DECISION / CONTROL          CONTRACT / DATA
                         |                         |
                     Python                  JSON Schema
                         |                         |
              +----------+----------+          SQL / TOML
              |                     |
            Rust                 CUDA C++
              |
       Deterministic Core
              |
     +--------+---------+
     |                  |
Specialized Services   Research
     |                  |
   Go / Java           Julia
     |
     +----------------------------------+
                                        |
                                 PRESENTATION
                                        |
                                 TypeScript
                                        |
                                       CSS
                                        |
                                  OPERATIONS
                                        |
                              PowerShell / Bash
```

Higher layers may invoke lower-level capabilities through explicit contracts, but lower-level or peripheral technologies must not redefine canonical governance or decision authority.

---

## 5. Python 3.14 Standard

### 5.1 Role

Python is the canonical application language for AI4BINANCE.

### 5.2 Approved Uses

Python SHOULD own:

- application orchestration;
- strategy orchestration;
- trading intelligence;
- AI/ML integration;
- agent coordination;
- ontology integration;
- deterministic decision orchestration;
- risk orchestration;
- validation and OOS workflows;
- governance enforcement;
- audit integration;
- research-to-production pipelines;
- CLI entry points;
- API services where appropriate;
- observability integration;
- configuration loading;
- schema validation;
- native-extension bindings.

### 5.3 Restrictions

Python MUST NOT:

- bypass canonical risk gates;
- delegate final trading authority to an LLM;
- contain duplicated implementations of canonical Rust/CUDA hot paths;
- use ad hoc scripts as hidden production services;
- embed environment-specific operational logic that belongs in PowerShell/Bash;
- silently fall back to non-deterministic behavior.

### 5.4 Governance Position

```text
Python = Canonical Control Plane
```

---

## 6. Rust Standard

### 6.1 Role

Rust is the preferred native language for deterministic, CPU-intensive, latency-sensitive, memory-sensitive, and parallel workloads.

### 6.2 Approved Uses

Rust MAY own:

- deterministic historical replay;
- market-event processing;
- tick processing;
- candle aggregation;
- feature computation;
- order-book transformations;
- pattern scanning;
- high-volume normalization;
- CPU-parallel analytics;
- deterministic simulation primitives;
- serialization hot paths;
- native computational libraries.

### 6.3 Adoption Gate

Rust MUST NOT be introduced solely because native code is assumed to be faster.

A Rust migration requires evidence such as:

- profiler output;
- benchmark results;
- CPU saturation evidence;
- latency measurements;
- memory-pressure evidence;
- throughput limitations;
- deterministic correctness requirements.

### 6.4 Interoperability

Preferred integration order:

1. stable process/service contract where isolation is beneficial;
2. Python native extension through a governed binding layer;
3. FFI only where explicit ownership, ABI, tests, and failure behavior are documented.

### 6.5 Governance Position

```text
Rust = Deterministic CPU Data Plane
```

---

## 7. CUDA C++ Standard

### 7.1 Role

CUDA C++ is reserved for workloads that demonstrate material benefit from GPU parallelism.

### 7.2 Approved Uses

CUDA C++ MAY own:

- massively parallel feature computation;
- large matrix/tensor operations;
- batched simulations;
- scenario evaluation;
- GPU-native numerical kernels;
- computationally intensive backtesting components;
- selected model/inference acceleration components.

### 7.3 Restrictions

CUDA C++ MUST NOT be used for:

- ordinary business logic;
- orchestration;
- governance;
- configuration;
- simple data transformations;
- workloads where transfer overhead exceeds compute benefit.

### 7.4 Adoption Gate

GPU implementation requires:

- CPU baseline;
- GPU benchmark;
- transfer-overhead measurement;
- deterministic/correctness validation;
- reproducibility evidence;
- graceful CPU fallback where required by architecture.

### 7.5 Governance Position

```text
CUDA C++ = GPU Compute Plane
```

---

## 8. SQL Standard

### 8.1 Role

SQL owns structured persistence, analytical querying, aggregation, and data retrieval.

### 8.2 Approved Uses

SQL SHOULD be used for:

- historical analytical queries;
- persisted event retrieval;
- audit-query workloads;
- portfolio/accounting data retrieval;
- performance analytics;
- research datasets;
- operational reporting;
- governed database constraints where appropriate.

### 8.3 Restrictions

SQL MUST NOT become the hidden owner of:

- trading decisions;
- risk policy;
- strategy logic;
- governance policy;
- application orchestration.

Material domain logic SHOULD remain in canonical application or deterministic-core layers.

---

## 9. TypeScript Standard

### 9.1 Role

TypeScript owns the human-facing web interface and browser application layer.

### 9.2 Approved Uses

TypeScript MAY own:

- dashboards;
- market visualization;
- opportunity radar;
- virtual-market UI;
- research UI;
- risk dashboards;
- validation/OOS dashboards;
- governance consoles;
- audit explorers;
- system-health interfaces;
- API clients;
- WebSocket clients;
- user interaction logic.

### 9.3 Prohibited Uses

TypeScript MUST NOT own:

- canonical trading decisions;
- risk calculations used as authoritative gates;
- deterministic replay;
- exchange simulation;
- portfolio accounting truth;
- governance enforcement;
- order authorization.

### 9.4 Governance Position

```text
TypeScript = Human Interface Plane
```

---

## 10. CSS Standard

### 10.1 Role

CSS owns visual presentation only.

### 10.2 Approved Uses

CSS MAY define:

- layout;
- typography;
- responsive behavior;
- design tokens;
- component styling;
- visual themes;
- chart-adjacent presentation.

### 10.3 Restrictions

CSS MUST NOT encode:

- business decisions;
- permission logic;
- risk states as unvalidated logic;
- trading rules;
- governance rules.

Visual representation MUST NOT be treated as canonical system state.

---

## 11. Go Standard

### 11.1 Role

Go is a specialized service language for high-concurrency network and ingestion workloads.

### 11.2 Approved Uses

Go MAY be used for:

- high-throughput WebSocket ingestion;
- exchange connectivity services;
- market-data collectors;
- fan-out/fan-in networking;
- lightweight long-running data services;
- protocol adapters;
- data-edge services.

### 11.3 Adoption Gate

Go requires evidence that the workload is materially constrained by:

- connection concurrency;
- networking overhead;
- I/O scheduling;
- service isolation;
- operational simplicity.

### 11.4 Restrictions

Go MUST NOT create:

- a second trading engine;
- a second risk engine;
- duplicate canonical strategy logic;
- duplicate governance logic.

### 11.5 Governance Position

```text
Go = Optional Network / Data Edge
```

---

## 12. Julia Standard

### 12.1 Role

Julia is a research and numerical-computing language.

### 12.2 Approved Uses

Julia MAY be used for:

- quantitative research;
- numerical experiments;
- mathematical prototyping;
- simulation studies;
- optimization research;
- statistical experiments;
- research-grade performance exploration.

### 12.3 Research Output Promotion Rule

Julia MUST remain research-only. Julia runtime code MUST NOT enter a production
decision path merely because a research result is promoted.

A Julia research finding may inform a separately governed production
implementation only after:

1. reproducible research evidence;
2. validation;
3. OOS evaluation;
4. anti-overfitting review;
5. contract definition;
6. a production implementation decision in an approved production language;
7. canonical tests;
8. governance approval.

### 12.4 Governance Position

```text
Julia = Research Plane
```

---

## 13. Java 25+ Standard

### 13.1 Role

Java is a specialized backend option for durable, long-running, high-throughput streaming or event-driven services.

### 13.2 Approved Uses

Java MAY be used for:

- event-stream processing;
- durable backend services;
- long-running JVM workloads;
- integration with JVM-native streaming ecosystems;
- specialized enterprise integration.

### 13.3 Adoption Gate

Java MUST only be introduced when existing Python, Rust, or Go solutions do not satisfy a documented requirement at acceptable complexity.

### 13.4 Restrictions

Java MUST NOT duplicate canonical:

- trading logic;
- risk logic;
- governance logic;
- validation logic;
- data contracts.

### 13.5 Governance Position

```text
Java = Optional Specialized Streaming Service
```

---

## 14. PowerShell Standard

### 14.1 Role

PowerShell owns Windows operational automation.

### 14.2 Approved Uses

PowerShell MAY own:

- Windows bootstrap;
- environment validation;
- local developer tooling;
- service start/stop wrappers;
- test launchers;
- lint/type-check launchers;
- repository health checks;
- toolchain validation;
- local operational workflows.

### 14.3 Restrictions

PowerShell MUST NOT contain:

- trading logic;
- strategy logic;
- risk calculations;
- governance decisions;
- portfolio/accounting logic;
- duplicated Python application logic.

### 14.4 Wrapper Rule

Where practical:

```text
PowerShell
    |
    v
Canonical Python CLI
```

PowerShell SHOULD remain a thin operational wrapper.

---

## 15. Bash Standard

### 15.1 Role

Bash owns Linux, container, and CI operational automation.

### 15.2 Approved Uses

Bash MAY own:

- Linux bootstrap;
- container entry points;
- CI tasks;
- build wrappers;
- environment validation;
- service wrappers;
- deployment preparation where explicitly authorized.

### 15.3 Restrictions

Bash MUST NOT contain authoritative:

- trading logic;
- risk logic;
- governance logic;
- business rules.

### 15.4 Wrapper Rule

Where practical:

```text
Bash
  |
  v
Canonical Python CLI
```

Bash and PowerShell MUST NOT maintain parallel copies of complex domain logic.

---

## 16. YAML / TOML Standard

### 16.1 Role

YAML and TOML are declarative configuration formats.

### 16.2 Preferred Usage

**TOML SHOULD be preferred for:**

- Python project configuration;
- developer tooling;
- stable local configuration;
- strongly structured repository configuration.

**YAML SHOULD be preferred for:**

- CI workflows;
- infrastructure declarations;
- deployment/configuration documents where ecosystem requirements justify YAML;
- human-readable structured operational configuration.

### 16.3 Restrictions

YAML/TOML MUST NOT become executable policy engines.

Configuration MUST be:

- schema-aware where practical;
- versioned;
- validated;
- bounded;
- auditable.

---

## 17. JSON Schema Standard

### 17.1 Role

JSON Schema is the canonical machine-readable contract mechanism unless a higher-level canonical contract explicitly specifies otherwise.

### 17.2 Approved Uses

JSON Schema SHOULD define:

- governed objects;
- event payloads;
- API contracts;
- audit records;
- risk inputs/outputs;
- strategy inputs/outputs;
- validation artifacts;
- configuration contracts;
- inter-service messages;
- persisted structured artifacts.

### 17.3 Mandatory Properties

Critical schemas SHOULD define, where relevant:

- `$id`;
- schema version;
- object version;
- required fields;
- type constraints;
- enums;
- numerical bounds;
- nullability;
- additional-property policy;
- identifiers;
- timestamps;
- provenance metadata;
- validation metadata.

### 17.4 Authority Boundary

JSON Schema owns the machine-readable structure and field semantics of the
specific canonical contract that declares it as source of truth. This
technology standard owns the selection and interoperability rules for JSON
Schema; it MUST NOT redefine the domain meaning, risk policy, or trading policy
expressed by a canonical schema.

### 17.5 Governance Position

```text
JSON Schema = Contract Authority within its declared contract scope
```

---

## 18. Cross-Language Ownership Matrix

| Capability | Python | Rust | CUDA C++ | SQL | TypeScript | CSS | Go | Julia | Java | PowerShell | Bash | YAML/TOML | JSON Schema |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Application orchestration | OWNER | Support | No | No | No | No | No | No | No | Wrapper | Wrapper | Config | Contract |
| Deterministic trading core | OWNER | Native implementation if approved | Acceleration | No | No | No | No | Research | No | No | No | Config | Contract |
| CPU hot paths | Support | OWNER | No | No | No | No | Optional | Research | Optional | No | No | No | Contract |
| GPU compute | Orchestrator | Support | OWNER | No | No | No | No | Research | No | No | No | Config | Contract |
| Market-data ingestion | ORCHESTRATOR | Optional | No | Storage | Client | No | Service owner if approved | Research | Optional | No | No | Config | Contract |
| Risk engine | OWNER | Native support | GPU support if justified | Storage | Display | No | No | Research | No | No | No | Config | Contract |
| Governance | OWNER | Enforced boundary | No | Storage | Display | No | No | No | No | No | No | Config | Contract |
| Validation/OOS | OWNER | Native support | GPU support | Storage | Display | No | No | Research | No | No | No | Config | Contract |
| Quant research | OWNER | Optional | Optional | Data | No | No | No | OWNER | No | No | No | Config | Contract |
| Web UI | API | No | No | Data | OWNER | OWNER | API | No | API | No | No | Config | Contract |
| Windows operations | CLI target | No | No | No | No | No | No | No | No | OWNER | No | Config | No |
| Linux/CI operations | CLI target | No | No | No | No | No | No | No | No | No | OWNER | Config | No |

Legend:

- **OWNER**: canonical responsibility within the named capability scope;
- **ORCHESTRATOR**: owns coordination while an approved bounded service may own its implementation;
- **Service owner if approved**: owns only the explicitly approved service boundary;
- **Native implementation if approved**: implements an approved hot path without owning domain semantics;
- **Acceleration**: performance support without independent decision authority;
- **Support**: permitted implementation support;
- **Optional**: requires evidence-based justification;
- **Research**: non-production authority;
- **Wrapper**: operational entry point only;
- **No**: not approved for that responsibility.

---

## 19. Performance Migration Standard

Performance optimization MUST follow:

```text
PROFILE
   |
   v
MEASURE
   |
   v
CLASSIFY BOTTLENECK
   |
   +--> I/O-bound ----------------> Python async / Go if justified
   |
   +--> CPU-bound ----------------> Optimize Python -> Rust if justified
   |
   +--> Vectorized numerical -----> NumPy/Polars/native -> Rust
   |
   +--> GPU-parallel -------------> CUDA C++
   |
   +--> Query-bound --------------> SQL/index/data-layout optimization
   |
   +--> UI-bound -----------------> TypeScript/browser optimization
```

A rewrite MUST NOT be approved without measurable evidence.

Required evidence SHOULD include:

- baseline benchmark;
- profiler evidence;
- target metric;
- expected improvement;
- correctness baseline;
- deterministic equivalence test;
- regression test;
- rollback strategy.

---

## 20. Polyglot Architecture Control

A new language or runtime MUST NOT be introduced unless all of the following are documented:

- problem statement;
- current limitation;
- why approved existing languages are insufficient;
- expected measurable benefit;
- operational cost;
- build-system impact;
- security impact;
- testing impact;
- observability impact;
- deployment impact;
- ownership;
- rollback plan;
- governance approval.

Default decision:

```text
NO_EVIDENCE -> NO_NEW_LANGUAGE
```

---

## 21. Duplication Control

The repository MUST NOT contain competing authoritative implementations of the same capability.

Prohibited examples:

```text
Python trading engine
+
Go trading engine
+
Java trading engine
```

or:

```text
Python risk engine
+
TypeScript risk engine
```

or:

```text
bootstrap.ps1 containing domain logic
+
bootstrap.sh containing duplicated domain logic
```

Preferred model:

```text
One Canonical Implementation
          |
          +--> Explicit Contract
          |
          +--> Thin Adapters / Bindings / Wrappers
```

---

## 22. Determinism and Safety Requirements

Any language participating in decision-critical processing MUST preserve:

- deterministic inputs;
- explicit timestamps;
- canonical identifiers;
- schema validation;
- stable ordering where required;
- reproducible calculations;
- bounded concurrency;
- documented numeric precision;
- auditable state transitions;
- structured errors;
- fail-closed behavior.

Non-deterministic or advisory systems MUST NOT authorize:

- live orders;
- risk overrides;
- strategy promotion;
- governance bypass;
- compliance bypass;
- validation bypass.

---

## 23. Interoperability Standard

Cross-language communication SHOULD prefer explicit versioned contracts.

Preferred order:

1. JSON Schema-governed events/messages;
2. typed API contracts;
3. Arrow/Parquet for analytical data exchange;
4. stable database contracts;
5. native bindings where performance evidence requires them;
6. raw FFI only as a controlled last-mile mechanism.

Every cross-language boundary MUST define:

- owner;
- input contract;
- output contract;
- error contract;
- version;
- compatibility rules;
- timeout behavior;
- retry behavior where applicable;
- deterministic expectations;
- observability requirements.

---

## 24. Repository Placement Guidance

Recommended high-level ownership:

```text
ai4binance/
|
+-- src/                         # Python canonical application
|
+-- native/
|   +-- rust/                    # Rust native performance modules
|   +-- cuda/                    # CUDA C++ kernels/modules
|
+-- services/
|   +-- go/                      # Evidence-approved Go services only
|   +-- java/                    # Evidence-approved Java services only
|
+-- research/
|   +-- julia/                   # Julia research, non-authoritative
|
+-- frontend/
|   +-- src/                     # TypeScript
|   +-- styles/                  # CSS/design system
|
+-- schemas/                     # JSON Schema
|
+-- config/                      # YAML/TOML
|
+-- sql/                         # SQL migrations/queries/models
|
+-- scripts/
|   +-- windows/                 # PowerShell
|   +-- unix/                    # Bash
|
+-- tests/
|
+-- docs/
```

Existing canonical repository structure MUST take precedence over this illustrative layout where conflicts exist.

### 24.1 Machine-Readable Projection and Enforcement

The enforcement chain is:

```text
Canonical Markdown Standard
          |
          v
Machine-Readable Policy Projection
          |
          v
Repository Validator / Quality Gate
          |
          v
Run-Scoped Evidence
```

`AI4B-GOV-FABRIC-001` connects this distinct scope with terminology and
repository-naming enforcement without merging their authority scopes. The
fabric is non-authoritative and cannot grant policy eligibility, consequential
change authority, promotion, or live execution.

The policy projection MUST:

- identify this document as its human authority;
- declare `source_of_truth: false`;
- use a schema-validated, versioned structure;
- encode language placement, forbidden ownership, interoperability, and
  adoption-evidence rules;
- fail closed when the policy, schema, evidence reference, or inspected boundary
  is invalid;
- preserve `execution_allowed: false`, `RESEARCH_ONLY`, and
  `LIVE_ORDER_BLOCKED`.

Repository enforcement MUST detect at least:

- implementation-language files outside their allowed roots;
- scripting or UI definitions that claim prohibited trading, risk, strategy, or
  governance ownership;
- production references to research-only Julia code;
- Rust, CUDA C++, Go, or Java adoption without the required evidence references.

Static checks are boundary evidence. They MUST NOT be represented as proof that
all semantic duplication is absent.

---

## 25. CI / Quality Gate Requirements

Each approved technology MUST have appropriate quality gates.

| Technology | Minimum Gate |
|---|---|
| Python | Ruff, type checking, pytest, security/static checks as governed |
| Rust | `cargo fmt`, `cargo clippy`, `cargo test` |
| CUDA C++ | compile validation, unit/integration tests, CPU/GPU equivalence where relevant |
| SQL | migration validation, query tests, schema checks |
| TypeScript | formatting/lint, type-check, unit tests, build |
| CSS | lint/build/UI regression as appropriate |
| Go | `gofmt`, `go vet`, `go test` |
| Julia | reproducibility tests, numerical validation, research evidence |
| Java | compile, static analysis, unit/integration tests |
| PowerShell | syntax/static analysis, bounded operational tests |
| Bash | shell linting, syntax validation, bounded operational tests |
| YAML/TOML | parser/schema/config validation |
| JSON Schema | schema validation and contract tests |

No gate may report success unless it was actually executed.

---

## 26. Security Requirements

All language layers MUST:

- avoid embedded credentials;
- avoid uncontrolled dynamic execution;
- validate untrusted inputs;
- preserve least privilege;
- use governed dependency sources;
- pin or constrain dependencies according to repository policy;
- produce structured auditable errors;
- prevent secrets from entering logs;
- avoid unsafe deserialization;
- reject malformed contracts fail-closed where required.

Native-code components require additional review for:

- memory safety;
- integer overflow;
- concurrency safety;
- FFI boundaries;
- GPU memory handling;
- undefined behavior.

---

## 27. Change-Control Rule

Any proposal that changes language ownership MUST include:

```text
CURRENT_STATE
TARGET_STATE
RATIONALE
BENCHMARK_EVIDENCE
ARCHITECTURAL_IMPACT
SECURITY_IMPACT
GOVERNANCE_IMPACT
TEST_PLAN
ROLLBACK_PLAN
```

Without sufficient evidence:

```text
NO_CHANGE
```

---

## 28. Canonical Decision Summary

```text
Python 3.14
    -> Intelligence + orchestration

Rust
    -> Deterministic CPU performance

CUDA C++
    -> GPU performance

SQL
    -> Persistent analytical data

TypeScript
    -> Human interface

CSS
    -> Presentation

Go
    -> High-throughput networking, ingestion, WebSocket/data services

Julia
    -> Quant research, simulations, numerical algorithms

Java 25+
    -> Streaming/event systems, long-running backend services

PowerShell
    -> Windows operations

Bash
    -> Linux / CI operations

YAML/TOML
    -> Configuration

JSON Schema
    -> Contracts
```

---

## 29. Final Architecture Rule

The approved stack is intentionally polyglot but MUST remain bounded.

The governing rule is:

> **Use Python by default. Use Rust or CUDA only for measured performance-critical paths. Use Go or Java only for justified specialized services. Keep Julia runtime code research-only and promote validated findings through a separately governed production implementation. Keep TypeScript/CSS in the human-interface layer. Keep PowerShell/Bash operational. Keep configuration declarative. Keep contracts explicit and machine-validatable.**

The existence of an approved technology does not create permission to duplicate canonical logic.

```text
Verified Evidence > Assumed Performance
Canonical Ownership > Language Preference
Deterministic Decision > Runtime Convenience
Contract Boundary > Hidden Coupling
Reuse > Reimplementation
Measured Bottleneck > Premature Rewrite
Governance > Local Optimization
```

---

## 30. Compliance Status Values

Language-governance reviews SHOULD use the following statuses:

```text
COMPLIANT
CONDITIONALLY_COMPLIANT
NON_COMPLIANT
NOT_VERIFIED
BLOCKED
NO_CHANGE
```

For decision-critical ambiguity, the system MUST prefer the restrictive outcome.

---

**End of Standard**

