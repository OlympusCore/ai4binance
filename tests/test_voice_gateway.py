# ruff: noqa: RUF001
"""Owner-voice security boundary tests."""

import pytest

from ai4binance.voice import (
    VoiceCommandGateway,
    VoiceIntent,
    assess_local_session,
    assess_speaker,
)


def test_voice_gateway_allows_only_verified_read_only_intent() -> None:
    seen: list[VoiceIntent] = []

    def responder(intent: VoiceIntent) -> str:
        seen.append(intent)
        return "NO_TRADE"

    gateway = VoiceCommandGateway(responder)
    verified = assess_speaker(
        enrolled=True, score=0.91, threshold=0.8, liveness_passed=True
    )

    result = gateway.handle(" Asistan spot görünümünü oku ", verified)

    assert result.accepted is True
    assert result.intent is VoiceIntent.SPOT_OUTLOOK
    assert result.response == "NO_TRADE"
    assert seen == [VoiceIntent.SPOT_OUTLOOK]
    assert result.execution_allowed is False


def test_voice_gateway_rejects_non_owner_replay_and_unknown_commands() -> None:
    called = False

    def responder(_intent: VoiceIntent) -> str:
        nonlocal called
        called = True
        return "unexpected"

    gateway = VoiceCommandGateway(responder)
    rejected = assess_speaker(
        enrolled=True, score=0.2, threshold=0.8, liveness_passed=False
    )
    result = gateway.handle("spot görünümünü oku", rejected)
    assert result.accepted is False
    assert result.blockers == ("VOICE_SPEAKER_MISMATCH", "VOICE_LIVENESS_FAILED")
    assert called is False

    verified = assess_speaker(
        enrolled=True, score=0.9, threshold=0.8, liveness_passed=True
    )
    no_wake = gateway.handle("hemen emir gönder", verified)
    assert no_wake.blockers == ("VOICE_WAKE_PHRASE_REQUIRED",)
    unknown = gateway.handle("asistan hemen emir gönder", verified)
    assert unknown.accepted is False
    assert unknown.blockers == ("VOICE_INTENT_NOT_ALLOWED",)
    assert called is False


def test_voice_models_reject_inconsistent_or_invalid_security_state() -> None:
    with pytest.raises(ValueError, match="between zero and one"):
        assess_speaker(enrolled=True, score=1.1, threshold=0.8, liveness_passed=True)
    missing = assess_speaker(
        enrolled=False, score=1.0, threshold=0.8, liveness_passed=True
    )
    assert missing.accepted is False
    assert missing.blockers == ("VOICE_OWNER_NOT_ENROLLED",)


def test_local_interactive_voice_accepts_only_read_only_allowlist() -> None:
    gateway = VoiceCommandGateway(lambda intent: intent.value)
    verified = assess_speaker(
        enrolled=True, score=0.91, threshold=0.8, liveness_passed=True
    )
    session = assess_local_session(
        interactive_user=True,
        microphone_available=True,
        owner_verification=verified,
    )

    accepted = gateway.handle_local("Asistan açık emirleri oku.", session)
    rejected = gateway.handle_local("Asistan pozisyonu kapat", session)

    assert accepted.accepted is True
    assert accepted.intent is VoiceIntent.OPEN_ORDERS
    assert accepted.execution_allowed is False
    assert rejected.blockers == ("VOICE_INTENT_NOT_ALLOWED",)


def test_local_voice_requires_interactive_user_and_microphone() -> None:
    gateway = VoiceCommandGateway(lambda intent: intent.value)
    session = assess_local_session(interactive_user=False, microphone_available=False)

    result = gateway.handle_local("sistem durumu", session)

    assert result.accepted is False
    assert result.blockers == (
        "VOICE_INTERACTIVE_USER_REQUIRED",
        "VOICE_MICROPHONE_UNAVAILABLE",
    )


def test_local_voice_limits_sensitive_intents_without_owner_verification() -> None:
    gateway = VoiceCommandGateway(lambda intent: intent.value)
    session = assess_local_session(interactive_user=True, microphone_available=True)

    status = gateway.handle_local("asistan sistem durumu", session)
    sensitive = gateway.handle_local("asistan envanteri oku", session)

    assert status.accepted is True
    assert sensitive.accepted is False
    assert sensitive.blockers == ("VOICE_OWNER_VERIFICATION_UNAVAILABLE",)


def test_wake_phrase_is_required_even_for_verified_speaker() -> None:
    gateway = VoiceCommandGateway(lambda intent: intent.value)
    verified = assess_speaker(
        enrolled=True, score=0.91, threshold=0.8, liveness_passed=True
    )

    result = gateway.handle("sistem durumu", verified)

    assert result.accepted is False
    assert result.blockers == ("VOICE_WAKE_PHRASE_REQUIRED",)
