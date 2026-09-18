---
document_id: AI4B-GOV-AGT-GEMINI-001
title: AI4BINANCE Gemini Provider Adapter Instructions
document_type: INSTRUCTION
version: 1.0.1
status: ACTIVE
owner: Enterprise Governance
authority_level: PROVIDER_ADAPTER
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: gemini_provider_adapter
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: OPERATIONAL
source_of_truth: false
source_of_truth_scope: provider_adapter
canonical_path: GEMINI.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
language: en-US
scope: repository_root
---

# AI4BINANCE Gemini Provider Adapter Instructions

## ELI10

This file points Gemini-based development workflows back to the repository
operating contract. It does not define separate trading, safety, or governance
authority.

## Operating Contract

Gemini workflows must follow `AGENTS.md` and the governed knowledge under
`docs/`. If this adapter appears to conflict with higher-authority repository
instructions, the higher-authority instruction prevails and the conflict must be
reported as `GOVERNANCE_CONFLICT`.

## Safety Boundary

This adapter does not authorize live execution, production deployment, risk-limit
changes, credential handling, or trading decisions. AI4BINANCE remains
`RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately approved through the
governed lifecycle.
