"""Compatibility exports for canonical blocker contracts and configuration loading."""

from ai4binance.application.blocker_registry import (
    load_blocker_registry as load_blocker_registry,
)
from ai4binance.domain import blockers as _canonical_blockers
from ai4binance.domain.blockers import (
    _ACTIVE_BLOCKING_STATES as _ACTIVE_BLOCKING_STATES,
)
from ai4binance.domain.blockers import (
    _AUTHORITY_CONFLICT_CODES as _AUTHORITY_CONFLICT_CODES,
)
from ai4binance.domain.blockers import (
    _BLOCKER_CODE_RE as _BLOCKER_CODE_RE,
)
from ai4binance.domain.blockers import (
    _DOMAIN_PREFIXES as _DOMAIN_PREFIXES,
)
from ai4binance.domain.blockers import (
    _FORBIDDEN_BLOCKER_CODES as _FORBIDDEN_BLOCKER_CODES,
)
from ai4binance.domain.blockers import (
    _LIFECYCLE_TRANSITIONS as _LIFECYCLE_TRANSITIONS,
)
from ai4binance.domain.blockers import (
    _NOT_WAIVABLE_CODES as _NOT_WAIVABLE_CODES,
)
from ai4binance.domain.blockers import (
    BLOCKER_REGISTRY_PATH as BLOCKER_REGISTRY_PATH,
)
from ai4binance.domain.blockers import (
    Blocker as Blocker,
)
from ai4binance.domain.blockers import (
    BlockerAuthority as BlockerAuthority,
)
from ai4binance.domain.blockers import (
    BlockerClass as BlockerClass,
)
from ai4binance.domain.blockers import (
    BlockerDefinition as BlockerDefinition,
)
from ai4binance.domain.blockers import (
    BlockerDomain as BlockerDomain,
)
from ai4binance.domain.blockers import (
    BlockerEffect as BlockerEffect,
)
from ai4binance.domain.blockers import (
    BlockerLifecycleState as BlockerLifecycleState,
)
from ai4binance.domain.blockers import (
    BlockerOccurrence as BlockerOccurrence,
)
from ai4binance.domain.blockers import (
    BlockerRegistry as BlockerRegistry,
)
from ai4binance.domain.blockers import (
    BlockerRegistryEntry as BlockerRegistryEntry,
)
from ai4binance.domain.blockers import (
    BlockerScope as BlockerScope,
)
from ai4binance.domain.blockers import (
    BlockerSeverity as BlockerSeverity,
)
from ai4binance.domain.blockers import (
    ClearanceRule as ClearanceRule,
)
from ai4binance.domain.blockers import (
    WaiverRequirements as WaiverRequirements,
)
from ai4binance.domain.blockers import (
    _definition_from_payload as _definition_from_payload,
)
from ai4binance.domain.blockers import (
    _domain_from_code as _domain_from_code,
)
from ai4binance.domain.blockers import (
    _optional_bool as _optional_bool,
)
from ai4binance.domain.blockers import (
    _optional_int as _optional_int,
)
from ai4binance.domain.blockers import (
    _optional_string as _optional_string,
)
from ai4binance.domain.blockers import (
    _optional_string_list as _optional_string_list,
)
from ai4binance.domain.blockers import (
    _optional_waiver as _optional_waiver,
)
from ai4binance.domain.blockers import (
    _require_nonblank as _require_nonblank,
)
from ai4binance.domain.blockers import (
    _require_unique_nonblank as _require_unique_nonblank,
)
from ai4binance.domain.blockers import (
    _required_bool as _required_bool,
)
from ai4binance.domain.blockers import (
    _required_clearance as _required_clearance,
)
from ai4binance.domain.blockers import (
    _required_int as _required_int,
)
from ai4binance.domain.blockers import (
    _required_string as _required_string,
)
from ai4binance.domain.blockers import (
    _required_string_list as _required_string_list,
)
from ai4binance.domain.blockers import (
    _required_waiver as _required_waiver,
)
from ai4binance.domain.blockers import (
    _string_key as _string_key,
)
from ai4binance.domain.blockers import (
    _string_value as _string_value,
)
from ai4binance.domain.blockers import (
    _validate_alias as _validate_alias,
)
from ai4binance.domain.blockers import (
    _validate_blocker_code as _validate_blocker_code,
)
from ai4binance.domain.blockers import (
    _validate_waiver_for_code as _validate_waiver_for_code,
)
from ai4binance.domain.blockers import (
    _waiver_from_payload as _waiver_from_payload,
)
from ai4binance.domain.blockers import (
    blocker_from_payload as blocker_from_payload,
)
from ai4binance.domain.blockers import (
    blocker_registry_from_payload as blocker_registry_from_payload,
)
from ai4binance.domain.blockers import (
    validate_lifecycle_transition as validate_lifecycle_transition,
)

_validate_execution_authority_conflict_effect = (
    _canonical_blockers._validate_execution_authority_conflict_effect
)
