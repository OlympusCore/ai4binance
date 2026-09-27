"""Compatibility exports for canonical virtual blocker reduction."""

from ai4binance.application.blocker_reduction import (
    _blocker_registry as _blocker_registry,
)
from ai4binance.application.blocker_reduction import (
    _is_known_blocker_code as _is_known_blocker_code,
)
from ai4binance.application.blocker_reduction import (
    reduce_virtual_blockers as reduce_virtual_blockers,
)
from ai4binance.domain.blocker_reduction import (
    _STAGE_NAMES as _STAGE_NAMES,
)
from ai4binance.domain.blocker_reduction import (
    VirtualBlockerReduction as VirtualBlockerReduction,
)
from ai4binance.domain.blocker_reduction import (
    _require_unique_nonblank as _require_unique_nonblank,
)
from ai4binance.domain.blocker_reduction import (
    _unique_sequence as _unique_sequence,
)
