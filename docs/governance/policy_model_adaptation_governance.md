---
document_id: AI4B-MODEL-POL-001
title: AI4BINANCE Model Adaptation Governance
document_type: POLICY
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L2_GOVERNANCE_COMPLIANCE
authority_scope: model_adaptation_governance
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/governance/policy_model_adaptation_governance.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# AI4BINANCE Model Adaptation Governance

## ELI10

This document explains how to keep the ideas of model training or fine-tuning in check
explains the boundary. Model improvement may be research, but it cannot by itself provide signal, risk,
The system cannot grant parameter override or live order permissions.


PEFT, LoRA, and QLoRA work is handled inside AI4BINANCE as a research candidate
alinir. This layer is a deterministic trading core, risk gate, execution gate or
Cannot generate a valid command.

## Required Evidence

A model adaptation candidate without the following references remains only
remains `RESEARCH_ONLY`:

- dataset lineage reference
- offline evaluation reference
- out-of-sample evidence reference
- model card reference
- red-team review reference
- risk review reference

Even if all references are present, the result can only be `STAGED_CANDIDATE`.
Live order compatibility remains `LIVE_ORDER_BLOCKED`.

## Evaluation Contract

Use:

```python
from ai4binance.learning.model_adaptation import (
    ModelAdaptationCandidate,
    ModelAdaptationMethod,
    assess_model_adaptation_candidate,
)
```

Assessment outputs:

- `recommendation`: `RESEARCH_ONLY` or `STAGED_CANDIDATE`
- `blockers`: missing evidence and `LIVE_ORDER_BLOCKED`
- `required_reviews`: dataset, OOS, red-team, and quality review records
- `execution_allowed=false`

This board does not promote model weights, deploy adapters, change risk limits,
or generate final trading signals.
