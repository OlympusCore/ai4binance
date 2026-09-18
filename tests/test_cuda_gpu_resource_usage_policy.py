from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs" / "governance" / "policy_cuda_gpu_resource_usage.md"
POLICY_REGISTRY = ROOT / "docs" / "registries" / "registry_policy_registry.md"
GPU_REGISTRY = ROOT / "docs" / "registries" / "registry_gpu_compute_policy.md"
DOC_INDEX = ROOT / "docs" / "registries" / "registry_documentation_index.md"
COMPLIANCE_MATRIX = ROOT / "docs" / "compliance" / "registry_compliance_matrix.md"


def test_cuda_gpu_resource_policy_is_governed_and_bound_to_system() -> None:
    policy_text = POLICY.read_text(encoding="utf-8")
    registry_text = POLICY_REGISTRY.read_text(encoding="utf-8")
    gpu_registry_text = GPU_REGISTRY.read_text(encoding="utf-8")
    index_text = DOC_INDEX.read_text(encoding="utf-8")
    compliance_text = COMPLIANCE_MATRIX.read_text(encoding="utf-8")

    assert "document_id: AI4B-GOV-POL-CUDA-001" in policy_text
    assert (
        "canonical_path: docs/governance/policy_cuda_gpu_resource_usage.md"
        in policy_text
    )
    assert "## ELI10" in policy_text
    assert "CPU_DEFAULT" in policy_text
    assert "CUDA_OPTIONAL" in policy_text
    assert "GPU_RESOURCE_GOVERNED" in policy_text
    assert "LLM_GPU_ELIGIBLE" in policy_text
    assert "BACKTEST_PROFILE_DRIVEN" in policy_text
    assert "HEAVY_GPU_WORKLOADS_MUTUALLY_EXCLUSIVE" in policy_text
    assert "Canonical Policy Matrix" in policy_text
    assert "GPU leases are time-bound" in policy_text
    assert "Market ingestion" in policy_text
    assert "Local LLM" in policy_text
    assert "Technology intelligence" in policy_text
    assert "CPU_REFERENCE_IMPLEMENTATION" in policy_text
    assert "BENCHMARK_BEFORE_PROMOTION" in policy_text
    assert "benchmark clearance must be explicit" in policy_text.lower()
    assert "CPU_FALLBACK_REQUIRED" in policy_text
    assert "CORRECTNESS_PARITY_REQUIRED" in policy_text
    assert "VRAM_HEADROOM_REQUIRED" in policy_text
    assert "GPU_CIRCUIT_BREAKER" in policy_text
    assert "GPU_TELEMETRY_REQUIRED" in policy_text
    assert "REBENCHMARK_ON_MATERIAL_CHANGE" in policy_text
    assert "DETERMINISTIC_CORE_GPU_INDEPENDENT" in policy_text
    assert "Lease TTL (min)" in policy_text
    assert "Priority" in policy_text
    assert "Voice transcription" in policy_text
    assert "Benchmark" in policy_text
    assert "AI4B-GOV-POL-CUDA-001" in registry_text
    assert "docs/governance/policy_cuda_gpu_resource_usage.md" in registry_text
    assert "AI4B-GOV-REG-GPU-001" in gpu_registry_text
    assert "GpuResourceGovernor" in gpu_registry_text
    assert "GPU_TELEMETRY_REQUIRED" in gpu_registry_text
    gpu_registry_lower = gpu_registry_text.lower()
    assert "explicit benchmark" in gpu_registry_lower
    assert "approval before" in gpu_registry_lower
    assert "docs/governance/policy_cuda_gpu_resource_usage.md" in index_text
    assert "CPU default" in index_text
    assert "optional CUDA, and GPU arbitration rules" in index_text
    assert "registry_gpu_compute_policy.md" in index_text
    assert "CUDA and GPU resource usage policy" in compliance_text
    assert "src/ai4binance/enterprise/gpu.py" in compliance_text
    assert "docs/registries/registry_gpu_compute_policy.md" in compliance_text
    assert "tests/test_gpu_compute_governor.py" in compliance_text
    assert "tests/test_cuda_gpu_resource_usage_policy.py" in compliance_text
    assert "src/ai4binance/learning/model_adaptation.py" in policy_text
    assert "src/ai4binance/learning/model_adaptation.py" in gpu_registry_text
    assert "src/ai4binance/learning/model_adaptation.py" in compliance_text
    assert "tests/test_model_adaptation_gpu_governance.py" in compliance_text
