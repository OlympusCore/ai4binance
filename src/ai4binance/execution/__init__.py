"""Paper-only execution and persistent lifecycle primitives."""

from ai4binance.execution.authorization import (
    ExecutionAuthorizationAlreadyConsumedError,
    ExecutionAuthorizationConsumption,
    ExecutionAuthorizationEnvelope,
    ExecutionAuthorizationLedgerUnavailableError,
    ExecutionAuthorizationSource,
    LocalExecutionAuthorizationLedger,
)
from ai4binance.execution.ledger import PaperLedger
from ai4binance.execution.lifecycle import PaperLifecycleEngine
from ai4binance.execution.live_order_lifecycle import (
    LiveOrderLifecycleEvent,
    LiveOrderLifecycleJournal,
    LiveOrderLifecycleRecord,
    LiveOrderLifecycleStage,
    LiveOrderLifecycleStateMachine,
)
from ai4binance.execution.live_readiness import (
    LiveReadinessBuilder,
    LiveReadinessEvidence,
)
from ai4binance.execution.live_spot import (
    GatedSpotOrderExecutor,
    LiveCommandResult,
    LiveCommandStatus,
    OrderDestinationVerification,
    ReadOnlySpotOrderHistoryVerifier,
)
from ai4binance.execution.live_spot_adapter import (
    LiveSpotOrderAdapter,
    LiveSpotOrderPlacement,
)
from ai4binance.execution.manual_approval import (
    ApprovalQueueRecord,
    ApprovalRequest,
    ApprovalStatus,
    LocalApprovalQueue,
    ManualActionProposal,
    ManualActionType,
)
from ai4binance.execution.order_command import SpotOrderCommand
from ai4binance.execution.order_preview import (
    SpotOrderPreview,
    SpotOrderPreviewBuilder,
)
from ai4binance.execution.order_state import OrderStateMachine
from ai4binance.execution.paper import PaperBroker
from ai4binance.execution.recovery import (
    PaperOrderRecoveryReport,
    PendingCancelAssessment,
    assess_pending_cancel,
    recover_paper_orders,
)
from ai4binance.execution.trailing import (
    DEFAULT_TRAILING_MULTIPLIER,
    update_long_trailing_stop,
)

__all__ = (
    "DEFAULT_TRAILING_MULTIPLIER",
    "ApprovalQueueRecord",
    "ApprovalRequest",
    "ApprovalStatus",
    "ExecutionAuthorizationAlreadyConsumedError",
    "ExecutionAuthorizationConsumption",
    "ExecutionAuthorizationEnvelope",
    "ExecutionAuthorizationLedgerUnavailableError",
    "ExecutionAuthorizationSource",
    "GatedSpotOrderExecutor",
    "LiveCommandResult",
    "LiveCommandStatus",
    "LiveOrderLifecycleEvent",
    "LiveOrderLifecycleJournal",
    "LiveOrderLifecycleRecord",
    "LiveOrderLifecycleStage",
    "LiveOrderLifecycleStateMachine",
    "LiveReadinessBuilder",
    "LiveReadinessEvidence",
    "LiveSpotOrderAdapter",
    "LiveSpotOrderPlacement",
    "LocalApprovalQueue",
    "LocalExecutionAuthorizationLedger",
    "ManualActionProposal",
    "ManualActionType",
    "OrderDestinationVerification",
    "OrderStateMachine",
    "PaperBroker",
    "PaperLedger",
    "PaperLifecycleEngine",
    "PaperOrderRecoveryReport",
    "PendingCancelAssessment",
    "ReadOnlySpotOrderHistoryVerifier",
    "SpotOrderCommand",
    "SpotOrderPreview",
    "SpotOrderPreviewBuilder",
    "assess_pending_cancel",
    "recover_paper_orders",
    "update_long_trailing_stop",
)
