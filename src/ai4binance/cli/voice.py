"""Voice command handlers for the safe CLI dispatcher."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ai4binance.config import Settings
from ai4binance.ops import SingleInstanceLease
from ai4binance.voice import (
    EdgeTtsSpeaker,
    FallbackSpeechOutput,
    FasterWhisperTranscriber,
    PrivateAccountStateReader,
    SoundDeviceRecorder,
    VoiceAssistantRuntime,
    VoiceCommandGateway,
    VoiceIntent,
    VoiceReportScheduler,
    VoiceResponseBuilder,
    WindowsSapiSpeaker,
    assess_local_session,
    interactive_windows_user,
    microphone_available,
    wait_for_private_state,
)


def run_voice_command(
    command: str,
    settings: Settings,
    *,
    max_cycles: int | None,
) -> int:
    if not wait_for_private_state(settings.private_runtime_state_path):
        return 2
    try:
        voice_runtime = build_voice_runtime(settings)
        if command == "voice-once":
            voice_runtime.run(max_cycles=1)
            return 0
        lease = SingleInstanceLease(settings.runtime_state_path.with_name("voice.lock"))
        with lease:
            voice_runtime.run(max_cycles=max_cycles)
        return 0
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "error": "VOICE_RUNTIME_FAILED",
                    "category": type(error).__name__,
                    "execution_allowed": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


def build_voice_runtime(settings: Settings) -> VoiceAssistantRuntime:
    """Build a local-interactive, read-only Turkish voice assistant."""
    available = microphone_available()
    session = assess_local_session(
        interactive_user=interactive_windows_user(),
        microphone_available=available,
    )
    if not session.accepted:
        raise RuntimeError("voice session requirements are unavailable")
    reader = PrivateAccountStateReader(
        settings.private_runtime_state_path,
        max_bytes=settings.voice_state_max_bytes,
    )
    responder = VoiceResponseBuilder(reader)
    repository_root = Path(__file__).resolve().parents[3]
    speaker = FallbackSpeechOutput(
        primary=EdgeTtsSpeaker(settings.voice_tts_voice),
        fallback=WindowsSapiSpeaker(repository_root / "Scripts" / "speak.ps1"),
    )
    return VoiceAssistantRuntime(
        recorder=SoundDeviceRecorder(
            capture_seconds=settings.voice_capture_seconds,
            sample_rate=settings.voice_sample_rate,
            silence_rms=settings.voice_silence_rms,
        ),
        transcriber=FasterWhisperTranscriber(
            settings.voice_model_name,
            settings.voice_model_directory,
        ),
        speaker=speaker,
        gateway=VoiceCommandGateway(responder.respond),
        session=session,
        scheduler=VoiceReportScheduler(settings.voice_report_interval_seconds),
        status_responder=lambda: responder.respond(VoiceIntent.SYSTEM_STATUS),
    )
