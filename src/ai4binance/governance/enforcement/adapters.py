"""Adapters from existing governed objects into universal enforcement envelopes."""

from __future__ import annotations

import hashlib
import json

from ai4binance.governance.enforcement.contracts import GovernedObjectEnvelope
from ai4binance.governance.execution_authority import ExecutionAuthorityProfile
from ai4binance.governance.policy_as_code import PolicyAsCodeDocument
from ai4binance.governance.repository_validator import (
    GovernedKnowledgeObject,
    RepositoryArtifact,
)
from ai4binance.governance.tool_policy import ToolPolicyDocument


def _sha256(payload: object) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def envelope_from_governed_knowledge(
    knowledge: GovernedKnowledgeObject,
) -> GovernedObjectEnvelope:
    return GovernedObjectEnvelope(
        object_id=knowledge.knowledge_id,
        object_type=knowledge.knowledge_type.value,
        version=knowledge.version,
        lifecycle_state=knowledge.lifecycle_status.value,
        owner=knowledge.owner,
        authority_layer=knowledge.authority_layer,
        authority_effect=(
            knowledge.authority_effect.value
            if knowledge.authority_effect is not None
            else None
        ),
        authority_scope=knowledge.authority_scope,
        source_of_truth=knowledge.source_of_truth,
        canonical_ref=knowledge.canonical_path,
        schema_ref="schemas/governance/governed_object_enforcement.schema.json",
        content_hash=None,
        policy_refs=(knowledge.canonical_path,),
        dependencies=(),
        evidence_refs=(),
        permission_profile_ref=None,
        classification=knowledge.classification.value,
    )


def envelope_from_repository_artifact(
    artifact: RepositoryArtifact,
) -> GovernedObjectEnvelope:
    return GovernedObjectEnvelope(
        object_id=artifact.artifact_id,
        object_type="REPOSITORY_ARTIFACT",
        version=artifact.schema_version or "1.0.0",
        lifecycle_state=artifact.lifecycle_status.value,
        owner=artifact.owner,
        authority_layer=artifact.authority_layer or artifact.observed_expected_layer,
        authority_effect=(
            artifact.authority_effect.value
            if artifact.authority_effect is not None
            else None
        ),
        authority_scope=artifact.authority_scope,
        source_of_truth=artifact.source_of_truth,
        canonical_ref=artifact.canonical_path,
        schema_ref="schemas/governance/repository_artifact.schema.json",
        content_hash=artifact.checksum,
        policy_refs=("docs/standards/standard_repository_file_governance.md",),
        dependencies=artifact.authority_basis,
        evidence_refs=(),
        permission_profile_ref=None,
        classification=artifact.classification.value,
    )


def envelope_from_policy_document(
    document: PolicyAsCodeDocument,
) -> GovernedObjectEnvelope:
    return GovernedObjectEnvelope(
        object_id=document.policy_id,
        object_type="POLICY",
        version=document.version,
        lifecycle_state="ACTIVE",
        owner="Enterprise Governance",
        authority_layer="L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
        authority_effect="NORMATIVE_CONSTRAINT",
        authority_scope="enterprise_governance",
        source_of_truth=True,
        canonical_ref=f"policy_as_code:{document.policy_id}",
        schema_ref="src/ai4binance/governance/policy_as_code.py:PolicyAsCodeDocument",
        content_hash=document.sha256,
        policy_refs=(f"policy_as_code:{document.policy_id}",),
        dependencies=(),
        evidence_refs=(),
        permission_profile_ref=None,
        classification="INTERNAL",
    )


def envelope_from_tool_policy_document(
    document: ToolPolicyDocument,
) -> GovernedObjectEnvelope:
    return GovernedObjectEnvelope(
        object_id=document.policy_id,
        object_type="TOOL_CONTRACT",
        version=document.version,
        lifecycle_state="ACTIVE",
        owner="Enterprise Governance",
        authority_layer="L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
        authority_effect="NORMATIVE_CONSTRAINT",
        authority_scope="tool_governance",
        source_of_truth=True,
        canonical_ref=f"tool_policy:{document.policy_id}",
        schema_ref="src/ai4binance/governance/tool_policy.py:ToolPolicyDocument",
        content_hash=document.sha256,
        policy_refs=(f"tool_policy:{document.policy_id}",),
        dependencies=(),
        evidence_refs=(),
        permission_profile_ref=document.policy_id,
        classification="INTERNAL",
    )


def envelope_from_execution_authority_profile(
    profile: ExecutionAuthorityProfile,
) -> GovernedObjectEnvelope:
    content_hash = _sha256(
        {
            "authority_profile_id": profile.authority_profile_id,
            "automation_mode": profile.automation_mode.value,
            "autonomous_learning_allowed": profile.autonomous_learning_allowed,
            "auto_execution_allowed": profile.auto_execution_allowed,
            "bounded_self_improvement_allowed": (
                profile.bounded_self_improvement_allowed
            ),
            "execution_allowed": profile.execution_allowed,
            "execution_surface": profile.execution_surface.value,
            "live_eligibility_status": profile.live_eligibility_status,
            "live_execution_allowed": profile.live_execution_allowed,
            "paper_execution_allowed": profile.paper_execution_allowed,
            "promotion_status": profile.promotion_status,
            "reason_codes": profile.reason_codes,
            "requires_manual_confirmation": profile.requires_manual_confirmation,
            "simulated_execution_allowed": profile.simulated_execution_allowed,
            "simulated_futures_allowed": profile.simulated_futures_allowed,
            "simulated_spot_allowed": profile.simulated_spot_allowed,
        }
    )
    return GovernedObjectEnvelope(
        object_id=profile.authority_profile_id,
        object_type="EXECUTION_PROFILE",
        version=profile.authority_profile_id,
        lifecycle_state="ACTIVE",
        owner="Enterprise Governance",
        authority_layer="L3_CANONICAL_CONTRACTS_SCHEMAS",
        authority_effect="NORMATIVE_CONSTRAINT",
        authority_scope="execution_governance",
        source_of_truth=True,
        canonical_ref=(
            "src/ai4binance/governance/execution_authority.py:"
            f"{profile.authority_profile_id}"
        ),
        schema_ref=(
            "src/ai4binance/governance/execution_authority.py:ExecutionAuthorityProfile"
        ),
        content_hash=content_hash,
        policy_refs=("src/ai4binance/governance/execution_authority.py",),
        dependencies=(),
        evidence_refs=(),
        permission_profile_ref=profile.authority_profile_id,
        classification="INTERNAL",
    )
