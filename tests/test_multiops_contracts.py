from __future__ import annotations

from dataclasses import replace

import pytest

from ai4binance.multiops import (
    DEFAULT_MULTI_OPS_DOMAINS,
    MultiOpsRegistry,
    OpsBlocker,
    OpsCapability,
    OpsCheckResult,
    OpsControlPlanePolicy,
    OpsDomain,
    OpsDomainDefinition,
    OpsVerdict,
    build_default_multiops_registry,
)
from ai4binance.multiops.agentops import (
    CAPABILITIES as AGENTOPS_CAPABILITIES,
)
from ai4binance.multiops.agentops import (
    DOMAIN as AGENTOPS_DOMAIN,
)
from ai4binance.multiops.aiops import (
    CAPABILITIES as AIOPS_CAPABILITIES,
)
from ai4binance.multiops.aiops import (
    DOMAIN as AIOPS_DOMAIN,
)
from ai4binance.multiops.dataops import (
    CAPABILITIES as DATAOPS_CAPABILITIES,
)
from ai4binance.multiops.dataops import (
    DOMAIN as DATAOPS_DOMAIN,
)
from ai4binance.multiops.devsecops import (
    CAPABILITIES as DEVSECOPS_CAPABILITIES,
)
from ai4binance.multiops.devsecops import (
    DOMAIN as DEVSECOPS_DOMAIN,
)
from ai4binance.multiops.llmops import (
    CAPABILITIES as LLMOPS_CAPABILITIES,
)
from ai4binance.multiops.llmops import (
    DOMAIN as LLMOPS_DOMAIN,
)
from ai4binance.multiops.mlops import (
    CAPABILITIES as MLOPS_CAPABILITIES,
)
from ai4binance.multiops.mlops import (
    DOMAIN as MLOPS_DOMAIN,
)
from ai4binance.multiops.ragops import (
    CAPABILITIES as RAGOPS_CAPABILITIES,
)
from ai4binance.multiops.ragops import (
    DOMAIN as RAGOPS_DOMAIN,
)
from ai4binance.multiops.tradeops import (
    CAPABILITIES as TRADEOPS_CAPABILITIES,
)
from ai4binance.multiops.tradeops import (
    DOMAIN as TRADEOPS_DOMAIN,
)


def test_default_multiops_registry_covers_every_domain_and_capability() -> None:
    registry = build_default_multiops_registry()

    assert {definition.domain for definition in registry.domains} == set(OpsDomain)
    assert len(registry.domains) == 8
    assert registry.capabilities_for(OpsDomain.AIOPS) == (
        OpsCapability.HEALTH,
        OpsCapability.INCIDENT,
        OpsCapability.ALERT_CORRELATION,
        OpsCapability.SAFE_RUNBOOKS,
    )
    assert OpsCapability.ORDER_INTENT in registry.capabilities_for(OpsDomain.TRADEOPS)
    assert all(not definition.execution_allowed for definition in registry.domains)
    assert all(
        definition.promotion_status == "RESEARCH_ONLY"
        for definition in registry.domains
    )
    assert all(
        definition.live_eligibility_status == "LIVE_ORDER_BLOCKED"
        for definition in registry.domains
    )


def test_multiops_domain_metadata_packages_match_registry() -> None:
    registry = build_default_multiops_registry()
    module_metadata = {
        AIOPS_DOMAIN: AIOPS_CAPABILITIES,
        MLOPS_DOMAIN: MLOPS_CAPABILITIES,
        LLMOPS_DOMAIN: LLMOPS_CAPABILITIES,
        RAGOPS_DOMAIN: RAGOPS_CAPABILITIES,
        AGENTOPS_DOMAIN: AGENTOPS_CAPABILITIES,
        DATAOPS_DOMAIN: DATAOPS_CAPABILITIES,
        DEVSECOPS_DOMAIN: DEVSECOPS_CAPABILITIES,
        TRADEOPS_DOMAIN: TRADEOPS_CAPABILITIES,
    }

    assert module_metadata.keys() == set(OpsDomain)
    for domain, capabilities in module_metadata.items():
        assert capabilities == registry.capabilities_for(domain)


def test_multiops_registry_rejects_duplicates_missing_domains_and_wrong_scope() -> None:
    registry = build_default_multiops_registry()
    duplicate = (*registry.domains, registry.domains[0])
    missing = tuple(
        definition
        for definition in registry.domains
        if definition.domain is not OpsDomain.RAGOPS
    )

    with pytest.raises(ValueError, match="unique"):
        MultiOpsRegistry(duplicate)
    with pytest.raises(ValueError, match="cover every ops domain"):
        MultiOpsRegistry(missing)
    with pytest.raises(ValueError, match="outside domain scope"):
        registry.validate_capability(
            domain=OpsDomain.TRADEOPS,
            capability=OpsCapability.MODEL_ROUTING,
        )
    with pytest.raises(ValueError, match="cannot be empty"):
        MultiOpsRegistry(())


def test_multiops_domain_policy_and_result_reject_execution_authority() -> None:
    aiops = DEFAULT_MULTI_OPS_DOMAINS[0]

    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(aiops, execution_allowed=True)
    with pytest.raises(ValueError, match="promote"):
        replace(aiops, promotion_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="live blocked"):
        replace(aiops, live_eligibility_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="independent control"):
        replace(aiops, independent_control=False)
    with pytest.raises(ValueError, match="capabilities must be unique"):
        OpsDomainDefinition(
            OpsDomain.AIOPS,
            "AIOps",
            "Duplicate capability guard.",
            (OpsCapability.HEALTH, OpsCapability.HEALTH),
        )
    with pytest.raises(ValueError, match="display name"):
        replace(aiops, display_name="")
    with pytest.raises(ValueError, match="capabilities cannot be empty"):
        replace(aiops, capabilities=())
    with pytest.raises(ValueError, match="external writes"):
        OpsControlPlanePolicy(external_writes_allowed=True)
    with pytest.raises(ValueError, match="cannot authorize execution"):
        OpsControlPlanePolicy(execution_allowed=True)
    with pytest.raises(ValueError, match="max_parallel_checks"):
        OpsControlPlanePolicy(max_parallel_checks=0)
    with pytest.raises(ValueError, match="require evidence"):
        OpsControlPlanePolicy(evidence_required=False)


def test_ops_check_result_contracts_are_fail_closed() -> None:
    passed = OpsCheckResult(
        check_id="ops-check-1",
        domain=OpsDomain.DEVSECOPS,
        capability=OpsCapability.SECRET_SCANNING,
        subject_ref="repo:ai4binance",
        verdict=OpsVerdict.PASSED,
        evidence_refs=("scan:clean",),
        blockers=(),
    )

    assert passed.execution_allowed is False
    assert passed.promotion_status == "RESEARCH_ONLY"
    assert passed.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="cannot have blockers"):
        replace(passed, blockers=(OpsBlocker.LIVE_BLOCKED.value,))
    with pytest.raises(ValueError, match="requires blockers"):
        replace(passed, verdict=OpsVerdict.BLOCKED)
    with pytest.raises(ValueError, match="evidence refs"):
        replace(passed, evidence_refs=("same", "same"))
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(passed, execution_allowed=True)
