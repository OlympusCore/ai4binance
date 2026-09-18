---
document_id: AI4B-GOV-REG-MDL-001
title: AI4BINANCE Model Registry
document_type: REGISTRY
version: 1.4.0
status: ACTIVE
owner: Model Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: model_registry
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/registries/registry_model_registry.md
schema_refs:
  - schemas/models/model_definition.schema.json
  - schemas/models/model_version.schema.json
  - schemas/models/model_artifact.schema.json
  - schemas/models/model_inference.schema.json
  - schemas/models/model_route_decision.schema.json
validated_by:
  - src/ai4binance/governance/repository_validator.py
  - tests/test_repository_validator.py
  - src/ai4binance/governance/model_registry.py
  - tests/test_model_registry.py
---

# AI4BINANCE Model Registry

## ELI10

This registry tracks canonical model identities, versions, artifacts, intended
use, and authority ceilings. An observed entry is registered for governance
visibility but remains blocked from promotion or execution until its artifact,
license, and validation evidence are independently verified.

## Registry Contract

LLM and ML models are advisory evidence sources. A registry entry cannot grant
decision, risk, strategy-promotion, execution, or live-order authority.

Every governed advisory inference must emit the `model_inference` envelope.
The envelope carries the canonical model identity, model version, task type,
deterministic input snapshot hash, and provenance hash without retaining raw
prompt content. Missing artifact identity remains explicit as `null` and must
continue to block verification rather than being inferred.

## Canonical Model Taxonomy

`Model` is not a generic synonym for every structured object. The registry
accepts the following model-artifact families: `STATISTICAL_MODEL`,
`TABULAR_ML_MODEL`, `REGIME_MODEL`, `ANOMALY_MODEL`, `TIME_SERIES_MODEL`,
`TIME_SERIES_FOUNDATION_MODEL`, `EMBEDDING_MODEL`, `RERANKER_MODEL`, `LLM`,
`EVALUATOR_MODEL`, `ENSEMBLE_MODEL`, `META_MODEL`, and `SCENARIO_MODEL`.

`DOMAIN_MODEL`, `DATA_MODEL`, and `RISK_MODEL` are separate semantic concepts.
They must not be registered as ML artifacts unless they independently satisfy
the identity, version, artifact, license, and authority contract in this
registry. The legacy `src/models/model.py` is registered only as a
`SCENARIO_MODEL`; this does not authorize its relocation or imply an ML model.

The JSON block below is the machine-readable canonical registry projection.
It is embedded in this governed document to preserve this document as the
single source of truth. `OBSERVED_UNVERIFIED` is a fail-closed inventory state,
not model approval or runtime admission.

## Canonical Model Entries

```json model-registry
{
  "schema_version": "1.0.0",
  "entries": [
    {
      "definition": {
        "model_id": "local-ollama-qwen3-8b",
        "name": "Local Qwen 3 8B Advisory Model",
        "model_family": "LLM",
        "provider": "ollama",
        "owner": "Model Governance",
        "intended_use": [
          "ADVISORY_RESEARCH_SYNTHESIS",
          "READ_ONLY_LOCAL_WORKBENCH"
        ],
        "prohibited_use": [
          "FINAL_DECISION",
          "RISK_OVERRIDE",
          "STRATEGY_PROMOTION",
          "ORDER_EXECUTION",
          "LIVE_ORDER_AUTHORIZATION"
        ],
        "authority": {
          "authority_ceiling": "ADVISORY_ONLY",
          "decision_authority": false,
          "risk_override": false,
          "strategy_promotion": false,
          "execution_authority": false,
          "live_order_authority": false
        }
      },
      "version": {
        "model_id": "local-ollama-qwen3-8b",
        "model_version": "qwen3:8b",
        "lifecycle_status": "OBSERVED_UNVERIFIED",
        "input_contract_version": "RAG_ADVISORY_PROMPT_V1",
        "output_contract_version": "ADVISORY_PROVIDER_RESULT_V1",
        "source_path": "src/ai4binance/rag.py"
      },
      "artifact": {
        "artifact_type": "LOCAL_MODEL_MANIFEST",
        "artifact_uri": "ollama://qwen3:8b",
        "artifact_sha256": null,
        "license_status": "UNVERIFIED",
        "rollback_binding": "DISABLE_LOCAL_ADVISORY"
      }
    },
    {
      "definition": {
        "model_id": "price-action-scenario-catalog",
        "name": "Price Action Scenario Catalog",
        "model_family": "SCENARIO_MODEL",
        "provider": "AI4BINANCE_INTERNAL",
        "owner": "Research Governance",
        "intended_use": [
          "RESEARCH_ONLY_SCENARIO_DEFINITION"
        ],
        "prohibited_use": [
          "FINAL_DECISION",
          "RISK_OVERRIDE",
          "STRATEGY_PROMOTION",
          "ORDER_EXECUTION",
          "LIVE_ORDER_AUTHORIZATION"
        ],
        "authority": {
          "authority_ceiling": "ADVISORY_ONLY",
          "decision_authority": false,
          "risk_override": false,
          "strategy_promotion": false,
          "execution_authority": false,
          "live_order_authority": false
        }
      },
      "version": {
        "model_id": "price-action-scenario-catalog",
        "model_version": "SOURCE_CONTRACT_V1",
        "lifecycle_status": "RESEARCH_ONLY",
        "input_contract_version": "BIAS_V1",
        "output_contract_version": "SCENARIO_V1",
        "source_path": "src/models/model.py"
      },
      "artifact": {
        "artifact_type": "SOURCE_CONTRACT",
        "artifact_uri": "src/models/model.py",
        "artifact_sha256": "bc5c018528a6fa872224412448d7ea3003ffdebade7d7a77bd6947f4e20433e2",
        "license_status": "VERIFIED",
        "rollback_binding": "REMOVE_FROM_RESEARCH_CATALOG"
      }
    }
  ]
}
```
