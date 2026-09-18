---
document_id: AI4B-GOV-REG-GPU-001
title: AI4BINANCE GPU Compute Policy Registry
document_type: REGISTRY
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: gpu_compute_policy
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/registries/registry_gpu_compute_policy.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
implemented_by:
  - src/ai4binance/enterprise/gpu.py
  - src/ai4binance/cli/status.py
  - src/ai4binance/cli/voice.py
  - src/ai4binance/learning/model_adaptation.py
validated_by:
  - tests/test_gpu_compute_governor.py
  - tests/test_cuda_gpu_resource_usage_policy.py
  - tests/test_model_adaptation_gpu_governance.py
---

# AI4BINANCE GPU Compute Policy Registry

## ELI10

This registry is the bridge between the GPU policy words and the code that
enforces them. It says which workload kind maps to which GPU lease kind, which
profile name applies, and which telemetry fields must exist before the GPU is
allowed to run.

## Registry Contract

Every GPU-eligible workload must map to one canonical profile and one canonical
lease kind.

| workload_kind | canonical_profile | lease_kind | default_device | telemetry_required | cpu_fallback_required | benchmark_required |
| --- | --- | --- | --- | --- | --- | --- |
| `VOICE_TRANSCRIPTION` | `VOICE_TRANSCRIPTION_GPU` | `LLM_GPU` | `cpu` | true | true | false |
| `LLM_INFERENCE` | `LLM_INFERENCE_GPU` | `LLM_GPU` | `cpu` | true | true | false |
| `EMBEDDING_INFERENCE` | `EMBEDDING_INFERENCE_GPU` | `LLM_GPU` | `cpu` | true | true | false |
| `RERANKER_INFERENCE` | `RERANKER_INFERENCE_GPU` | `LLM_GPU` | `cpu` | true | true | false |
| `MODEL_TRAINING` | `TRAINING_GPU` | `TRAINING_GPU` | `cpu` | true | true | false |
| `BACKTEST_ACCELERATION` | `BACKTEST_GPU` | `BACKTEST_GPU` | `cpu` | true | true | true |
| `MONTE_CARLO` | `MONTE_CARLO_GPU` | `BACKTEST_GPU` | `cpu` | true | true | true |
| `TECH_INTELLIGENCE` | `TECH_INTELLIGENCE_GPU` | `OPTIONAL_GPU` | `cpu` | true | true | false |
| `BENCHMARK` | `BENCHMARK_GPU` | `BENCHMARK_GPU` | `cpu` | true | true | true |

## Registry Notes

- `CPU_DEFAULT` remains the system baseline for every workload that does not
  explicitly justify GPU use.
- `GPU_RESOURCE_GOVERNED` means device choice is centrally decided by
  `GpuResourceGovernor`, not by the caller.
- `LLM_GPU_ELIGIBLE` and `TRAINING_GPU_ELIGIBLE` are separate lease lanes and
  must not be treated as a shared default concurrency pool.
- `GpuPolicyMatrixRow` now carries profile/workload bindings, lease TTL, and
  priority so the governor can derive per-profile lease duration and canonical
  scheduling order from one row.
- `BACKTEST_PROFILE_DRIVEN` means backtest GPU use remains conditional on the
  governed benchmark/promotion state.
- `BACKTEST_GPU` and `MONTE_CARLO` workloads require explicit benchmark
  approval before `GpuResourceGovernor` may grant a CUDA lease.
- `GPU_CIRCUIT_BREAKER` means repeated CUDA failures can open a governed
  breaker that blocks GPU selection until revalidation closes it.
- Telemetry observations may feed the breaker directly so repeated telemetry
  failures can move the governor from `CLOSED` to `OPEN`.
- `GPU_TELEMETRY_REQUIRED` means memory allocated, reserved, peak values, and
  device telemetry must be observable before GPU promotion.
- `VRAM_HEADROOM_REQUIRED` means the selected workload must have enough free
  memory headroom for the configured policy.
- `HEAVY_GPU_WORKLOADS_MUTUALLY_EXCLUSIVE` means the single local GPU lease
  must be treated as exclusive until a later benchmark proves overlap is safe.
