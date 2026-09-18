"""Controlled learning with no deployment or execution authority."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai4binance.learning.engine import ControlledLearningEngine
    from ai4binance.learning.governance import (
        GovernedLesson,
        LessonStatus,
        stage_learning_summary,
    )
    from ai4binance.learning.lifecycle import (
        GovernedLessonLifecycleStore,
        GovernedLessonLifecycleWorker,
        LessonTransitionRequest,
    )
    from ai4binance.learning.model_adaptation import (
        ModelAdaptationAssessment,
        ModelAdaptationCandidate,
        ModelAdaptationMethod,
        ModelAdaptationRuntimeDecision,
        assess_model_adaptation_candidate,
        select_model_adaptation_runtime,
    )
    from ai4binance.learning.models import LearningSummary
    from ai4binance.learning.storage import LearningStore

__all__ = (
    "ControlledLearningEngine",
    "GovernedLesson",
    "GovernedLessonLifecycleStore",
    "GovernedLessonLifecycleWorker",
    "LearningStore",
    "LearningSummary",
    "LessonStatus",
    "LessonTransitionRequest",
    "ModelAdaptationAssessment",
    "ModelAdaptationCandidate",
    "ModelAdaptationMethod",
    "ModelAdaptationRuntimeDecision",
    "assess_model_adaptation_candidate",
    "select_model_adaptation_runtime",
    "stage_learning_summary",
)

_EXPORTS = {
    "ControlledLearningEngine": (
        "ai4binance.learning.engine",
        "ControlledLearningEngine",
    ),
    "GovernedLesson": ("ai4binance.learning.governance", "GovernedLesson"),
    "GovernedLessonLifecycleStore": (
        "ai4binance.learning.lifecycle",
        "GovernedLessonLifecycleStore",
    ),
    "GovernedLessonLifecycleWorker": (
        "ai4binance.learning.lifecycle",
        "GovernedLessonLifecycleWorker",
    ),
    "LearningStore": ("ai4binance.learning.storage", "LearningStore"),
    "LearningSummary": ("ai4binance.learning.models", "LearningSummary"),
    "LessonStatus": ("ai4binance.learning.governance", "LessonStatus"),
    "LessonTransitionRequest": (
        "ai4binance.learning.lifecycle",
        "LessonTransitionRequest",
    ),
    "ModelAdaptationAssessment": (
        "ai4binance.learning.model_adaptation",
        "ModelAdaptationAssessment",
    ),
    "ModelAdaptationCandidate": (
        "ai4binance.learning.model_adaptation",
        "ModelAdaptationCandidate",
    ),
    "ModelAdaptationMethod": (
        "ai4binance.learning.model_adaptation",
        "ModelAdaptationMethod",
    ),
    "ModelAdaptationRuntimeDecision": (
        "ai4binance.learning.model_adaptation",
        "ModelAdaptationRuntimeDecision",
    ),
    "assess_model_adaptation_candidate": (
        "ai4binance.learning.model_adaptation",
        "assess_model_adaptation_candidate",
    ),
    "select_model_adaptation_runtime": (
        "ai4binance.learning.model_adaptation",
        "select_model_adaptation_runtime",
    ),
    "stage_learning_summary": (
        "ai4binance.learning.governance",
        "stage_learning_summary",
    ),
}


def __getattr__(name: str) -> object:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
