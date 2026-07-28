# ruff: noqa: RUF001
"""Deterministic owner-voice gate limited to read-only advisory intents."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class VoiceIntent(StrEnum):
    SYSTEM_STATUS = "SYSTEM_STATUS"
    SPOT_OUTLOOK = "SPOT_OUTLOOK"
    FUTURES_OUTLOOK = "FUTURES_OUTLOOK"
    INVENTORY = "INVENTORY"
    FUTURES_POSITIONS = "FUTURES_POSITIONS"
    OPEN_ORDERS = "OPEN_ORDERS"
    BLOCKERS = "BLOCKERS"
    REPEAT = "REPEAT"
    STOP_LISTENING = "STOP_LISTENING"
    MUTE = "MUTE"


LOCAL_NON_SENSITIVE_INTENTS = frozenset(
    {
        VoiceIntent.SYSTEM_STATUS,
        VoiceIntent.SPOT_OUTLOOK,
        VoiceIntent.FUTURES_OUTLOOK,
        VoiceIntent.BLOCKERS,
        VoiceIntent.REPEAT,
        VoiceIntent.STOP_LISTENING,
        VoiceIntent.MUTE,
    }
)


@dataclass(frozen=True, slots=True)
class SpeakerVerification:
    enrolled: bool
    score: float
    threshold: float
    liveness_passed: bool
    accepted: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0 or not 0.0 <= self.threshold <= 1.0:
            raise ValueError("speaker score and threshold must be between zero and one")
        if self.accepted == bool(self.blockers):
            raise ValueError("speaker acceptance and blockers disagree")


def assess_speaker(
    *, enrolled: bool, score: float, threshold: float, liveness_passed: bool
) -> SpeakerVerification:
    blockers: list[str] = []
    if not enrolled:
        blockers.append("VOICE_OWNER_NOT_ENROLLED")
    if score < threshold:
        blockers.append("VOICE_SPEAKER_MISMATCH")
    if not liveness_passed:
        blockers.append("VOICE_LIVENESS_FAILED")
    return SpeakerVerification(
        enrolled=enrolled,
        score=score,
        threshold=threshold,
        liveness_passed=liveness_passed,
        accepted=not blockers,
        blockers=tuple(blockers),
    )


@dataclass(frozen=True, slots=True)
class VoiceIntentParser:
    wake_phrase: str = "asistan"
    phrases: tuple[tuple[str, VoiceIntent], ...] = (
        ("sistem durumu", VoiceIntent.SYSTEM_STATUS),
        ("spot görünümünü oku", VoiceIntent.SPOT_OUTLOOK),
        ("futures görünümünü oku", VoiceIntent.FUTURES_OUTLOOK),
        ("envanteri oku", VoiceIntent.INVENTORY),
        ("futures pozisyonlarını oku", VoiceIntent.FUTURES_POSITIONS),
        ("açık emirleri oku", VoiceIntent.OPEN_ORDERS),
        ("işlem engellerini oku", VoiceIntent.BLOCKERS),
        ("son raporu tekrarla", VoiceIntent.REPEAT),
        ("dinlemeyi durdur", VoiceIntent.STOP_LISTENING),
        ("mikrofonu kapat", VoiceIntent.MUTE),
    )

    def normalize(self, transcript: str) -> str:
        return " ".join(transcript.casefold().strip(" .,!?:;\t\r\n").split())

    def has_wake_phrase(self, transcript: str) -> bool:
        normalized = self.normalize(transcript)
        return normalized == self.wake_phrase or normalized.startswith(
            f"{self.wake_phrase} "
        )

    def parse(self, transcript: str) -> VoiceIntent | None:
        normalized = self.normalize(transcript)
        prefix = f"{self.wake_phrase} "
        if not normalized.startswith(prefix):
            return None
        command = normalized.removeprefix(prefix)
        return next(
            (intent for phrase, intent in self.phrases if command == phrase),
            None,
        )


@dataclass(frozen=True, slots=True)
class LocalVoiceSession:
    """Authenticated interactive-session trust for read-only microphone commands."""

    interactive_user: bool
    microphone_available: bool
    owner_verification: SpeakerVerification | None
    accepted: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.accepted == bool(self.blockers):
            raise ValueError("local voice session acceptance and blockers disagree")


def assess_local_session(
    *,
    interactive_user: bool,
    microphone_available: bool,
    owner_verification: SpeakerVerification | None = None,
) -> LocalVoiceSession:
    blockers: list[str] = []
    if not interactive_user:
        blockers.append("VOICE_INTERACTIVE_USER_REQUIRED")
    if not microphone_available:
        blockers.append("VOICE_MICROPHONE_UNAVAILABLE")
    return LocalVoiceSession(
        interactive_user,
        microphone_available,
        owner_verification,
        not blockers,
        tuple(blockers),
    )


@dataclass(frozen=True, slots=True)
class VoiceCommandResult:
    accepted: bool
    intent: VoiceIntent | None
    response: str
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("voice commands cannot grant execution authority")
        if self.accepted == bool(self.blockers):
            raise ValueError("voice result acceptance and blockers disagree")


@dataclass(frozen=True, slots=True)
class VoiceCommandGateway:
    """Accept only owner-verified, exact-match, read-only intents."""

    responder: Callable[[VoiceIntent], str]
    parser: VoiceIntentParser = VoiceIntentParser()

    def handle(
        self, transcript: str, verification: SpeakerVerification
    ) -> VoiceCommandResult:
        if not verification.accepted:
            return VoiceCommandResult(
                False,
                None,
                "Speaker verification failed.",
                verification.blockers,
            )
        return self._respond(transcript)

    def handle_local(
        self, transcript: str, session: LocalVoiceSession
    ) -> VoiceCommandResult:
        if not session.accepted:
            return VoiceCommandResult(
                False,
                None,
                "Yerel ses oturumu doğrulanamadı.",
                session.blockers,
            )
        verification = session.owner_verification
        if verification is None:
            intent = self.parser.parse(transcript)
            if intent in LOCAL_NON_SENSITIVE_INTENTS:
                return self._respond(transcript)
            return VoiceCommandResult(
                False,
                None,
                "Kullanıcı ses doğrulaması yapılandırılmadı.",
                ("VOICE_OWNER_VERIFICATION_UNAVAILABLE",),
            )
        if not verification.accepted:
            return VoiceCommandResult(
                False,
                None,
                "Kullanıcı ses doğrulaması başarısız.",
                verification.blockers,
            )
        return self._respond(transcript)

    def _respond(self, transcript: str) -> VoiceCommandResult:
        if not self.parser.has_wake_phrase(transcript):
            return VoiceCommandResult(
                False,
                None,
                "Uyandırma ifadesi gerekli.",
                ("VOICE_WAKE_PHRASE_REQUIRED",),
            )
        intent = self.parser.parse(transcript)
        if intent is None:
            return VoiceCommandResult(
                False,
                None,
                "Komut izin listesinde değil.",
                ("VOICE_INTENT_NOT_ALLOWED",),
            )
        response = self.responder(intent).strip()
        if not response:
            return VoiceCommandResult(
                False,
                intent,
                "Voice response unavailable.",
                ("VOICE_RESPONSE_UNAVAILABLE",),
            )
        return VoiceCommandResult(True, intent, response, ())
