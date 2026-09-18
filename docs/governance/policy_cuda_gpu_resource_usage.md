---
document_id: AI4B-GOV-POL-CUDA-001
title: AI4BINANCE CUDA and GPU Resource Usage Policy
document_type: POLICY
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L2_GOVERNANCE_COMPLIANCE
authority_scope: cuda_gpu_resource_usage
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/governance/policy_cuda_gpu_resource_usage.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
implemented_by:
  - src/ai4binance/config.py
  - src/ai4binance/enterprise/gpu.py
  - src/ai4binance/enterprise/resources.py
  - src/ai4binance/backtest/runtime_economics.py
  - src/ai4binance/cli/status.py
  - src/ai4binance/cli/voice.py
  - src/ai4binance/cli/commands.py
  - src/ai4binance/cli/output.py
  - src/ai4binance/learning/model_adaptation.py
validated_by:
  - tests/test_cuda_gpu_resource_usage_policy.py
  - tests/test_gpu_compute_governor.py
  - tests/test_config_reporting.py
  - tests/test_enterprise_resources.py
  - tests/test_backtest_runtime_economics.py
  - tests/test_cli.py
  - tests/test_model_adaptation_gpu_governance.py
---

# AI4BINANCE CUDA and GPU Resource Usage Policy

## ELI10

This policy says CUDA is allowed only when it is safer and more useful than the
CPU baseline. The system must keep working on CPU by default, must keep LLM and
training workloads separated, and must not promote GPU usage permanently until
measurement proves the change is worth it.

## 1. Purpose

This policy defines how CUDA-capable GPU resources may be used by AI4BINANCE.

The policy is designed to:

- preserve deterministic system behavior;
- keep CPU as the default compute mode;
- make CUDA optional instead of mandatory;
- prevent uncontrolled GPU contention;
- keep LLM inference and training GPU-eligible without making them concurrent;
- keep backtesting profile-driven;
- require benchmarking before any permanent GPU promotion;
- preserve a CPU fallback path whenever CUDA is unavailable or not justified;
- keep GPU usage auditable and fail-closed.

GPU acceleration is an optimization, not a correctness dependency.

AI4BINANCE must remain operational in its deterministic research and paper-mode
core when CUDA is unavailable.

## 2. Canonical Compute Policy

The canonical compute policy is:

```text
CPU_DEFAULT
CUDA_OPTIONAL
GPU_RESOURCE_GOVERNED
LLM_GPU_ELIGIBLE
TRAINING_GPU_ELIGIBLE
BACKTEST_PROFILE_DRIVEN
HEAVY_GPU_WORKLOADS_MUTUALLY_EXCLUSIVE
CPU_REFERENCE_IMPLEMENTATION
CPU_FALLBACK_REQUIRED
BENCHMARK_BEFORE_PROMOTION
CORRECTNESS_PARITY_REQUIRED
VRAM_HEADROOM_REQUIRED
GPU_CIRCUIT_BREAKER
GPU_TELEMETRY_REQUIRED
REBENCHMARK_ON_MATERIAL_CHANGE
DETERMINISTIC_CORE_GPU_INDEPENDENT
```

### 2.1 Canonical Policy Matrix

The matrix below is the canonical capability and profile view of the GPU
policy. Every CUDA-eligible path is still governed by `GPU_RESOURCE_GOVERNED`,
remains subject to `GPU_TELEMETRY_REQUIRED`, `VRAM_HEADROOM_REQUIRED`, and
`CPU_FALLBACK_REQUIRED`, and must respect the fail-closed circuit-breaker
model. Lower numeric priority means higher scheduling priority.

| Capability | Profiles | Lease TTL (min) | Priority | Default compute | CUDA stance | Governing rule | Required telemetry | Fallback | Promotion gate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Market ingestion | `n/a` | `n/a` | `0` | `CPU_DEFAULT` | No | Deterministic hot-path ingest stays CPU-only | Not required | CPU only | Not applicable |
| Polars/data processing | `n/a` | `n/a` | `1` | `CPU_DEFAULT` | Benchmark only | GPU only when a profile proves material benefit | Required when CUDA is used | CPU fallback required | `BENCHMARK_BEFORE_PROMOTION` |
| Indicators/features | `n/a` | `n/a` | `2` | `CPU_DEFAULT` | Rare | Determinism remains the default baseline | Required when CUDA is used | CPU fallback required | `BENCHMARK_BEFORE_PROMOTION` |
| Risk | `n/a` | `n/a` | `3` | `CPU_DEFAULT` | No | Critical deterministic core remains GPU-independent | Not required | CPU only | Not applicable |
| Validation | `n/a` | `n/a` | `4` | `CPU_DEFAULT` | No | Veto authority remains CPU-bound and fail-closed | Not required | CPU only | Not applicable |
| Decision governance | `n/a` | `n/a` | `5` | `CPU_DEFAULT` | No | Governance logic remains GPU-independent | Not required | CPU only | Not applicable |
| Paper execution | `n/a` | `n/a` | `6` | `CPU_DEFAULT` | No | Paper execution remains deterministic and CPU-first | Not required | CPU only | Not applicable |
| Voice transcription | `VOICE_TRANSCRIPTION_GPU` | `15` | `7` | `CPU_DEFAULT` | Yes | Voice transcription uses the governed LLM lane | `GPU_TELEMETRY_REQUIRED` | CPU fallback required | `BENCHMARK_BEFORE_PROMOTION` |
| Local LLM | `LLM_INFERENCE_GPU` | `20` | `8` | `CPU_DEFAULT` | Yes | `LLM_GPU_ELIGIBLE` under `GPU_RESOURCE_GOVERNED` | `GPU_TELEMETRY_REQUIRED` | CPU fallback required | `BENCHMARK_BEFORE_PROMOTION` |
| Embeddings/reranker | `EMBEDDING_INFERENCE_GPU`, `RERANKER_INFERENCE_GPU` | `15` | `9` | `CPU_DEFAULT` | Benchmark | Workload dependent and profile driven | Required when CUDA is used | CPU fallback required | `BENCHMARK_BEFORE_PROMOTION` |
| Model training | `TRAINING_GPU` | `90` | `10` | `CPU_DEFAULT` | Yes | `TRAINING_GPU_ELIGIBLE` and cold-path only | `GPU_TELEMETRY_REQUIRED` | CPU fallback required | `BENCHMARK_BEFORE_PROMOTION` |
| Backtesting | `BACKTEST_GPU` | `120` | `11` | `CPU_DEFAULT` | Profile driven | `BACKTEST_PROFILE_DRIVEN` and benchmark gated | Required when CUDA is used | CPU fallback required | `BENCHMARK_BEFORE_PROMOTION` |
| Monte Carlo | `MONTE_CARLO_GPU` | `180` | `12` | `CPU_DEFAULT` | Candidate | Scale dependent and benchmark first | Required when CUDA is used | CPU fallback required | `BENCHMARK_BEFORE_PROMOTION` |
| Auto-Learn | `n/a` | `n/a` | `13` | `CPU_DEFAULT` | Optional experiments | Controlled research only; no promotion authority | Required for experiments | CPU fallback required | Human-governed review |
| Technology intelligence | `TECH_INTELLIGENCE_GPU` | `30` | `14` | `CPU_DEFAULT` | Optional | Outside the hot path and governed by profile | Required when CUDA is used | CPU fallback required | `BENCHMARK_BEFORE_PROMOTION` |
| Benchmark | `BENCHMARK_GPU` | `60` | `15` | `CPU_DEFAULT` | Benchmark only | Dedicated benchmark workloads require explicit approval | `GPU_TELEMETRY_REQUIRED` | CPU fallback required | `BENCHMARK_BEFORE_PROMOTION` |

`HEAVY_GPU_WORKLOADS_MUTUALLY_EXCLUSIVE` applies to every CUDA-eligible row in
the matrix. `CPU_REFERENCE_IMPLEMENTATION` remains the correctness oracle for
all promoted GPU paths.

## 3. Authority

GPU selection must not be controlled independently by:

- an LLM;
- an agent;
- a strategy;
- Auto-Learn;
- training code;
- an individual backtest;
- an external provider adapter.

GPU allocation authority should belong to a deterministic infrastructure
capability such as `GpuResourceGovernor`.

The governor may:

- inspect GPU availability;
- inspect available VRAM;
- inspect currently active AI4BINANCE GPU workloads;
- grant or deny GPU leases;
- select an approved compute profile;
- trigger CPU fallback;
- emit telemetry;
- reject conflicting workloads.

The governor must not:

- change trading risk limits;
- alter strategy parameters;
- authorize live execution;
- terminate unrelated operating-system processes;
- silently change validated computational behavior.

## 4. Compute Profiles

AI4BINANCE should define explicit compute profiles.

### 4.1 CPU Default

```text
profile: CPU_DEFAULT
device: cpu
```

Used for:

- market-data ingestion;
- normalization;
- data-quality validation;
- ordinary feature calculations;
- indicators;
- evidence processing;
- governance;
- risk calculations;
- validation;
- deterministic decision logic;
- execution governance;
- paper execution;
- audit;
- repository validation;
- routine backtesting.

This is the canonical baseline.
The CPU baseline remains the `CPU_REFERENCE_IMPLEMENTATION`.

### 4.2 LLM GPU

```text
profile: LLM_GPU
device: cuda
workload_class: inference
exclusive_heavy_gpu: true
```

Eligible workloads:

- local LLM inference;
- embedding inference when benchmark-justified;
- reranking when benchmark-justified;
- approved AI inference workloads.

LLM inference must remain advisory.
LLM inference is governed by the `LLM_GPU_ELIGIBLE` profile and the
`GPU_RESOURCE_GOVERNED` lease model.

GPU availability must not affect deterministic trade authority.

If GPU inference becomes unavailable:

```text
GPU failure or unavailability
  -> CPU inference
  or
  -> LLM capability degraded
```

The deterministic core must remain operational.

### 4.3 Training GPU

```text
profile: TRAINING_GPU
device: cuda
workload_class: training
exclusive_heavy_gpu: true
```

Eligible workloads:

- PyTorch training;
- fine-tuning;
- approved ML experiments;
- validated model research;
- approved numerical research workloads.

Training must execute outside the trading hot path.
Training is governed by the `TRAINING_GPU_ELIGIBLE` profile and the
`GPU_RESOURCE_GOVERNED` lease model.

Training must not run concurrently with GPU-hosted LLM inference unless a
future benchmark and resource-isolation review explicitly approves that
concurrency.

Default:

```text
LLM_GPU + TRAINING_GPU = DENIED
```

### 4.4 Backtest CPU

```text
profile: BACKTEST_CPU
device: cpu
```

This is the default backtest profile.

Suitable for:

- deterministic strategy backtesting;
- walk-forward validation;
- OOS validation;
- replay;
- rule-based strategies;
- event-driven simulations;
- ordinary numerical analysis.

### 4.5 Backtest GPU Candidate

```text
profile: BACKTEST_GPU_CANDIDATE
device: cuda
status: experimental
```

GPU backtesting may be evaluated for workloads such as:

- sufficiently large vectorized numerical workloads;
- ML-heavy simulation;
- large parameter sweeps;
- matrix-intensive research;
- approved Monte Carlo workloads.

GPU backtesting must not become the default solely because CUDA is available.

## 5. GPU Workload Classes

Every GPU workload must declare a workload class.

```text
LLM_INFERENCE
ML_INFERENCE
MODEL_TRAINING
MODEL_EVALUATION
BACKTEST_ACCELERATION
NUMERICAL_RESEARCH
BENCHMARK
```

Unknown or undeclared workload classes must not automatically receive GPU
access.

Result:

```text
UNKNOWN_GPU_WORKLOAD
-> GPU_DENIED
-> CPU_FALLBACK or BLOCKED
```

## 6. GPU Resource Arbitration

AI4BINANCE should implement an exclusive GPU lease mechanism.
The initial governance layer should treat the local GPU as a centrally managed
`GPU_RESOURCE_GOVERNED` resource.

The lease system must prevent incompatible workloads from concurrently
occupying the GPU.

GPU leases are time-bound. A lease must carry an expiry timestamp, and expired
leases must be treated as non-active so they do not block new admission.

Possible states:

```text
REQUESTED
GRANTED
ACTIVE
RELEASED
EXPIRED
DENIED
FAILED
```

The lease system must not change trading risk limits, authorize live execution,
or silently alter validated computational behavior.

## 7. Default Exclusivity Matrix

| Existing Workload | Requested Workload | Default Decision |
|---|---|---|
| None | LLM inference | ALLOW |
| None | Training | ALLOW |
| None | Approved GPU backtest | ALLOW |
| LLM inference | Training | DENY |
| Training | LLM inference | DENY |
| Training | GPU backtest | DENY |
| GPU backtest | Training | DENY |
| LLM inference | GPU backtest | DENY by default |
| Benchmark | Any heavy workload | DENY by default |

Concurrency must be explicitly benchmarked before being promoted from `DENY`
to `ALLOW`.

## 8. VRAM Safety Policy

GPU allocation must maintain configurable VRAM headroom.

Recommended initial policy:

```yaml
gpu_memory:
  headroom_percent: 20
  allow_full_device_allocation: false
  reject_if_insufficient_headroom: true
```

The exact value must remain profile-driven and hardware-specific.

The system should observe at least:

```text
total_vram
free_vram
allocated_vram
reserved_vram
peak_allocated_vram
peak_reserved_vram
gpu_utilization
active_gpu_processes
```

A workload must not start when the configured safety headroom cannot be
maintained.
This operationalizes `VRAM_HEADROOM_REQUIRED`.

## 9. CUDA Preflight Gate

Before granting GPU access, the resource governor should validate:

```text
GPU_DEVICE_AVAILABLE
CUDA_RUNTIME_AVAILABLE
FRAMEWORK_CUDA_AVAILABLE
APPROVED_DEVICE
APPROVED_COMPUTE_PROFILE
SUFFICIENT_VRAM
NO_CONFLICTING_GPU_LEASE
COMPATIBLE_DRIVER_RUNTIME
WORKLOAD_REGISTERED
BENCHMARK_STATUS_ACCEPTABLE
```

Failure of an optional acceleration gate should normally result in:

```text
GPU_DENIED
-> CPU_FALLBACK
```

rather than system failure.

## 10. Benchmark-Before-Promotion Policy

A workload must not become permanently GPU-default merely because CUDA
execution succeeds.
This is the enforcement path for `BENCHMARK_BEFORE_PROMOTION` and
`REBENCHMARK_ON_MATERIAL_CHANGE`.

Promotion lifecycle:

```text
CPU_BASELINE
    ↓
GPU_CANDIDATE
    ↓
CONTROLLED_BENCHMARK
    ↓
CORRECTNESS_PARITY
    ↓
PERFORMANCE_ANALYSIS
    ↓
RESOURCE_ANALYSIS
    ↓
STABILITY_ANALYSIS
    ↓
PROMOTION_CANDIDATE
    ↓
HUMAN/GOVERNANCE REVIEW
    ↓
GPU_APPROVED
```

A benchmark must compare at least:

```text
CPU wall-clock time
GPU wall-clock time
CPU memory
GPU VRAM
GPU peak VRAM
initialization overhead
data-transfer overhead
throughput
latency
output equivalence
numerical tolerance
repeatability
failure rate
OOM events
thermal/throttling observations
```

A benchmark must measure end-to-end execution rather than kernel execution
alone.

Benchmark clearance must be explicit before a backtest or Monte Carlo workload
may be granted a CUDA lease. The runtime governor must treat that clearance as
a fail-closed approval flag, not as an implicit consequence of device
availability.

## 11. GPU Promotion Gate

Permanent GPU promotion should require all applicable conditions:

```text
CORRECTNESS_PARITY = PASS
NUMERICAL_TOLERANCE = PASS
REPRODUCIBILITY = PASS
NO_NEW_CRITICAL_FAILURE_MODE = PASS
VRAM_HEADROOM = PASS
STABILITY = PASS
END_TO_END_PERFORMANCE_GAIN = MATERIAL
CPU_FALLBACK = VERIFIED
AUDITABILITY = PASS
```

If the GPU provides only negligible end-to-end improvement:

```text
NO_CHANGE
```

The CPU profile remains canonical.
The promotion gate must preserve `CORRECTNESS_PARITY_REQUIRED` and the
`CPU_REFERENCE_IMPLEMENTATION` baseline.

## 12. Numerical Parity

CPU and GPU implementations may produce small floating-point differences.

Critical decisions must not depend on uncontrolled CPU/GPU numerical divergence.

For workloads participating in validated research:

```text
same input
+ same configuration
+ same seed where applicable
-> equivalent result within approved tolerance
```

Tolerance must be explicitly defined for each workload class.

Silent tolerance expansion is prohibited.

## 13. Deterministic Decision Core

The following capabilities should remain CPU-first and CUDA-independent unless
extraordinary evidence justifies otherwise:

```text
Governance
Policy Evaluation
Risk Gates
Validation Gates
Decision Governance
Trade Eligibility
Position Constraints
Execution Authorization
Audit Validation
Repository Governance
```

CUDA failure must not weaken or bypass these controls.
The deterministic decision core remains `DETERMINISTIC_CORE_GPU_INDEPENDENT`.

## 14. Backtest Policy

Backtesting is profile-driven.

Default:

```text
BACKTEST_CPU
```

GPU acceleration requires:

```text
sufficient workload size
+ validated GPU implementation
+ CPU/GPU parity
+ material measured benefit
```

For the governed runtime path, `BACKTEST_GPU_CANDIDATE` workloads may receive a
CUDA lease only when the caller supplies benchmark approval and all other
lease checks pass.

Individual strategies must not hard-code a device such as:

```python
device = "cuda"
```

Compute placement must be injected through the approved compute profile.

## 15. Training Policy

Training belongs to the cold path.

Training must not:

- block the deterministic market-analysis hot path;
- share unrestricted VRAM with local LLM inference;
- modify production model artifacts automatically;
- automatically promote model parameters;
- alter trading risk limits;
- directly modify production strategies.

Training output is:

```text
MODEL_CANDIDATE
```

not:

```text
PRODUCTION_MODEL
```

Promotion remains governed separately.

## 16. LLM Inference Policy

Local LLM inference is GPU-eligible.

However:

```text
LLM availability != system availability
```

and:

```text
LLM output != trade authority
```

If CUDA inference fails:

```text
GPU inference
    ↓
CPU inference if practical
    or
LLM_DEGRADED
```

The deterministic decision pipeline should continue.

## 17. GPU OOM Policy

CUDA Out-of-Memory events must be treated as controlled infrastructure failures.

Required behavior:

```text
OOM detected
    ↓
record incident
    ↓
release current workload resources
    ↓
release GPU lease
    ↓
mark profile degraded
    ↓
CPU fallback where supported
```

The system must not enter an uncontrolled infinite retry loop.

Recommended:

```text
automatic_gpu_retry_limit: 1
```

Repeated OOM events should trigger a GPU circuit breaker.
The implementation must surface a `GPU_CIRCUIT_BREAKER` state instead of
silently retrying forever.

## 18. GPU Circuit Breaker

Suggested states:

```text
CLOSED
OPEN
HALF_OPEN
```

Repeated conditions such as:

```text
CUDA_OOM
CUDA_INITIALIZATION_FAILURE
DRIVER_ERROR
DEVICE_LOST
PERSISTENT_THROTTLING
REPEATED_BENCHMARK_REGRESSION
```

may open the GPU circuit.

The governor should model this as a deterministic `GpuCircuitBreaker` with
`CLOSED`, `OPEN`, and `HALF_OPEN` states so the recovery path remains explicit
and telemetry-driven.

When open:

```text
CUDA_OPTIONAL workloads
-> CPU_ONLY
```

until explicitly revalidated.
Recovery must remain telemetry-driven under `GPU_TELEMETRY_REQUIRED`.

## 19. CPU Fallback

Every CUDA-optional workload should define one of:

```text
CPU_FALLBACK
GRACEFUL_DEGRADATION
BLOCKED_WITH_REASON
```

Implicit crashes are not an acceptable fallback strategy.

Examples:

```text
LLM CUDA failure
-> CPU LLM or LLM_DEGRADED

GPU backtest failure
-> BACKTEST_CPU

training CUDA failure
-> TRAINING_DEFERRED
```

## 20. Observability

Every GPU workload should emit structured telemetry.
Telemetry emission is mandatory under `GPU_TELEMETRY_REQUIRED`.
The runtime governor should materialize a `GpuTelemetryAssessment` so GPU
health, blockers, and headroom checks remain auditable.
The governor may record telemetry failures and open the GPU circuit after
repeated `CUDA_UNAVAILABLE`, `GPU_TELEMETRY_REQUIRED`, or
`VRAM_HEADROOM_REQUIRED` signals.

Recommended fields:

```text
timestamp
job_id
correlation_id
workload_class
compute_profile
device_id
cuda_available
gpu_name
gpu_utilization_pct
vram_total_mb
vram_free_mb
vram_allocated_mb
vram_reserved_mb
peak_vram_allocated_mb
duration_ms
cpu_fallback_used
oom_count
result_status
benchmark_id
```

## 21. Implementation Binding

This policy is already bound to the repository through:

- `src/ai4binance/config.py`, which keeps CPU default device settings and GPU
  toggles explicit;
- `src/ai4binance/enterprise/gpu.py`, which defines the canonical
  `GpuComputePolicy`, `GpuResourceGovernor`, `GpuTelemetrySnapshot`, `GpuLease`,
  and `GpuRuntimeSelection` contracts;
- `src/ai4binance/enterprise/resources.py`, which preserves the broader
  non-GPU resource budget and execution blocks;
- `src/ai4binance/backtest/runtime_economics.py`, which requires measurements
  and keeps GPU visibility fail-closed;
- `src/ai4binance/cli/status.py`, which reports backtest runtime economics and
  current CUDA request state without granting authority;
- `src/ai4binance/cli/voice.py`, which routes voice transcription device
  selection through the shared GPU runtime policy;
- `docs/registries/registry_policy_registry.md`, which records the active policy
  source of truth;
- `docs/registries/registry_gpu_compute_policy.md`, which records the GPU
  workload profiles, lease kinds, and telemetry fields;
- `docs/compliance/registry_compliance_matrix.md`, which records the code and
  test proof;
- `tests/test_cuda_gpu_resource_usage_policy.py`, which verifies the policy
  binding;
- `tests/test_gpu_compute_governor.py`, which verifies the governor contract,
  telemetry model, and lease exclusivity;
- `tests/test_enterprise_resources.py`, `tests/test_config_reporting.py`,
  `tests/test_backtest_runtime_economics.py`, and `tests/test_cli.py`, which
  enforce the governing behavior.

## 22. Final Policy Principles

```text
CORRECTNESS_PARITY > ACCELERATION
DETERMINISM > THROUGHPUT
STABILITY > PEAK PERFORMANCE
CPU_REFERENCE_IMPLEMENTATION > ASSUMED_GPU_BENEFIT
MEASUREMENT > HARDWARE_ENTHUSIASM
GPU_RESOURCE_GOVERNED > COMPETING_PROCESSES
END_TO_END_BENCHMARK > SYNTHETIC_SPEEDUP
CPU_FALLBACK_REQUIRED > CUDA_DEPENDENCY
HUMAN_GOVERNED_PROMOTION > AUTOMATIC_PROMOTION
```
