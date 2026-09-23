"""Real voice runtime contracts tested without microphone or network."""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai4binance.enterprise import GpuTelemetryAssessment
from ai4binance.voice import (
    EdgeTtsSpeaker,
    FallbackSpeechOutput,
    FasterWhisperTranscriber,
    PrivateAccountStateReader,
    SoundDeviceRecorder,
    VoiceAssistantRuntime,
    VoiceCommandGateway,
    VoiceHealthStore,
    VoiceIntent,
    VoiceReportScheduler,
    VoiceResponseBuilder,
    WindowsSapiSpeaker,
    assess_local_session,
    assess_speaker,
    interactive_windows_user,
    microphone_available,
    wait_for_private_state,
)
from ai4binance.voice.localization import (
    TR_VOICE_COMMAND_PHRASES,
    TR_VOICE_MESSAGES,
    TR_VOICE_WAKE_PHRASE,
)

NOW = datetime(2026, 7, 14, tzinfo=UTC)


def voice_command(intent_name: str) -> str:
    phrase = next(
        phrase
        for phrase, mapped_intent in TR_VOICE_COMMAND_PHRASES.items()
        if mapped_intent == intent_name
    )
    return f"{TR_VOICE_WAKE_PHRASE} {phrase}"


def account_payload() -> dict[str, object]:
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "state": "DEGRADED",
        "spot": {
            "action": "HOLD",
            "bias": "BULLISH",
            "wallet_status": "READY",
            "blockers": [],
        },
        "futures": {
            "action": "NO_TRADE",
            "bias": "BEARISH",
            "wallet_status": "READY",
            "blockers": ["FUTURES_OOS_NOT_APPROVED"],
        },
        "inventory": [{"asset": "HOT", "total": "100"}],
        "futures_positions": [
            {
                "symbol": "HOTUSDT",
                "side": "LONG",
                "quantity": "5",
                "unrealized_pnl": "-1",
            }
        ],
        "open_orders": [
            {
                "market": "SPOT",
                "symbol": "HOTUSDT",
                "side": "BUY",
                "status": "PARTIALLY_FILLED",
                "remaining_quantity": "90",
            }
        ],
        "blockers": ["FUTURES_OOS_NOT_APPROVED"],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def write_state(path: Path) -> None:
    path.write_text(json.dumps(account_payload()), encoding="utf-8")


def test_voice_response_builder_reads_inventory_positions_orders_and_outlooks(
    tmp_path: Path,
) -> None:
    path = tmp_path / "account.json"
    write_state(path)
    builder = VoiceResponseBuilder(PrivateAccountStateReader(path))

    assert TR_VOICE_MESSAGES.inventory_item(asset="HOT", total="100") in (
        builder.respond(VoiceIntent.INVENTORY)
    )
    assert "HOTUSDT LONG" in builder.respond(VoiceIntent.FUTURES_POSITIONS)
    assert "90" in builder.respond(VoiceIntent.OPEN_ORDERS)
    assert builder.respond(VoiceIntent.SPOT_OUTLOOK).startswith("Spot")
    assert "NO_TRADE" in builder.respond(VoiceIntent.FUTURES_OUTLOOK)
    assert builder.respond(VoiceIntent.REPEAT).startswith("Futures")


def test_private_state_reader_rejects_secret_invalid_and_executing_payloads(
    tmp_path: Path,
) -> None:
    path = tmp_path / "account.json"
    with pytest.raises(ValueError, match="unavailable"):
        PrivateAccountStateReader(path).read()
    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        PrivateAccountStateReader(path).read()
    path.write_text('{"BINANCE_API_KEY":"forbidden"}', encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden"):
        PrivateAccountStateReader(path).read()
    path.write_text('{"execution_allowed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="cannot grant"):
        PrivateAccountStateReader(path).read()


class Recorder:
    def __init__(self, audio: object | None = object()) -> None:
        self.audio = audio

    def capture(self) -> object | None:
        return self.audio


class Transcriber:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript

    def transcribe(self, audio: object) -> str:
        assert audio is not None
        return self.transcript


class Speaker:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


def runtime(
    transcript: str,
    speaker: Speaker,
    *,
    telemetry_assessment: GpuTelemetryAssessment | None = None,
) -> VoiceAssistantRuntime:
    verification = assess_speaker(
        enrolled=True, score=0.95, threshold=0.8, liveness_passed=True
    )
    return VoiceAssistantRuntime(
        recorder=Recorder(),
        transcriber=Transcriber(transcript),
        speaker=speaker,
        gateway=VoiceCommandGateway(lambda intent: f"response {intent.value}"),
        session=assess_local_session(
            interactive_user=True,
            microphone_available=True,
            owner_verification=verification,
        ),
        scheduler=VoiceReportScheduler(interval_seconds=60),
        status_responder=lambda: "scheduled report",
        telemetry_assessment=telemetry_assessment,
        clock=lambda: NOW,
        health_store=None,
    )


def test_voice_runtime_speaks_allowed_command_and_stops() -> None:
    speaker = Speaker()
    service = runtime(voice_command("SYSTEM_STATUS"), speaker)

    result = service.run_once()

    assert result is not None
    assert result.accepted is True
    assert speaker.spoken == ["response SYSTEM_STATUS"]

    stop = runtime(voice_command("STOP_LISTENING"), speaker)
    assert stop.run(max_cycles=3) == 1


def test_voice_runtime_skips_silence_rejects_unknown_and_schedules() -> None:
    speaker = Speaker()
    service = runtime("bilinmeyen komut", speaker)
    service.recorder = Recorder(None)
    assert service.run_once() is None
    service.recorder = Recorder()
    rejected = service.run_once()
    assert rejected is not None
    assert rejected.accepted is False
    assert speaker.spoken == []

    service.scheduler.last_report_at = NOW - timedelta(seconds=61)
    service.run_once()
    assert speaker.spoken == ["scheduled report"]


def test_voice_scheduler_requires_aware_time_and_respects_interval() -> None:
    scheduler = VoiceReportScheduler(interval_seconds=60)
    assert scheduler.due(NOW) is False
    assert scheduler.due(NOW + timedelta(seconds=59)) is False
    assert scheduler.due(NOW + timedelta(seconds=60)) is True
    with pytest.raises(ValueError, match="timezone-aware"):
        scheduler.due(datetime(2026, 7, 14))


def test_private_reader_bounds_shape_and_response_controls(tmp_path: Path) -> None:
    path = tmp_path / "account.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be an object"):
        PrivateAccountStateReader(path).read()
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="size limit"):
        PrivateAccountStateReader(path, max_bytes=1).read()

    builder = VoiceResponseBuilder(PrivateAccountStateReader(path))
    assert builder.respond(VoiceIntent.REPEAT) == TR_VOICE_MESSAGES.repeat_unavailable
    assert builder.respond(VoiceIntent.STOP_LISTENING) == (
        TR_VOICE_MESSAGES.stop_listening
    )
    assert builder.respond(VoiceIntent.MUTE) == TR_VOICE_MESSAGES.mute
    assert builder.respond(VoiceIntent.SYSTEM_STATUS) == (
        TR_VOICE_MESSAGES.account_report_unavailable
    )

    write_state(path)
    assert "Sistem DEGRADED" in builder.respond(VoiceIntent.SYSTEM_STATUS)
    assert builder.respond(VoiceIntent.BLOCKERS).startswith(
        TR_VOICE_MESSAGES.blockers("").split(":")[0]
    )


def test_runtime_mute_empty_transcript_and_cycle_validation() -> None:
    speaker = Speaker()
    service = runtime("", speaker)
    assert service.run_once() is None
    with pytest.raises(ValueError, match="positive"):
        service.run(max_cycles=0)

    muted = runtime(voice_command("MUTE"), speaker)
    result = muted.run_once()
    assert result is not None
    assert muted.muted is True
    assert speaker.spoken[-1].endswith("MUTE")
    muted.scheduler.last_report_at = NOW - timedelta(seconds=61)
    muted.run_once()
    assert "scheduled" not in speaker.spoken


class WhisperModelStub:
    def transcribe(
        self, audio: object, **kwargs: object
    ) -> tuple[list[object], object]:
        assert audio == "audio"
        assert kwargs["language"] == "tr"
        return [SimpleNamespace(text=" hello "), SimpleNamespace(text=" world")], {}


class FallbackWhisperModelFactory:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, *args: object, **kwargs: object) -> WhisperModelStub:
        del args
        self.calls.append(dict(kwargs))
        if kwargs.get("device") == "cuda":
            raise RuntimeError("CUDA unavailable")
        return WhisperModelStub()


def test_whisper_adapter_initializes_and_transcribes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import faster_whisper  # type: ignore[import-not-found]
    import truststore  # type: ignore[import-not-found]

    monkeypatch.setattr(truststore, "inject_into_ssl", lambda: None)
    calls: list[dict[str, object]] = []

    def build_whisper_model(*args: object, **kwargs: object) -> WhisperModelStub:
        calls.append(dict(kwargs))
        return WhisperModelStub()

    monkeypatch.setattr(faster_whisper, "WhisperModel", build_whisper_model)
    adapter = FasterWhisperTranscriber("tiny", tmp_path / "models")
    assert adapter.transcribe("audio") == "hello world"
    assert calls == [
        {
            "device": "cpu",
            "compute_type": "int8",
            "download_root": str(tmp_path / "models"),
        }
    ]


def test_whisper_adapter_falls_back_to_cpu_when_cuda_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import faster_whisper
    import truststore

    monkeypatch.setattr(truststore, "inject_into_ssl", lambda: None)
    factory = FallbackWhisperModelFactory()
    monkeypatch.setattr(faster_whisper, "WhisperModel", factory)

    adapter = FasterWhisperTranscriber(
        "tiny",
        tmp_path / "models",
        device="cuda",
        compute_type="float16",
    )

    assert adapter.transcribe("audio") == "hello world"
    assert factory.calls == [
        {
            "device": "cuda",
            "compute_type": "float16",
            "download_root": str(tmp_path / "models"),
        },
        {
            "device": "cpu",
            "compute_type": "int8",
            "download_root": str(tmp_path / "models"),
        },
    ]


def test_sound_recorder_distinguishes_signal_and_silence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np  # type: ignore[import-not-found]
    import sounddevice  # type: ignore[import-not-found]

    monkeypatch.setattr(sounddevice, "wait", lambda: None)
    monkeypatch.setattr(
        sounddevice,
        "rec",
        lambda *args, **kwargs: np.asarray([[0.1], [0.1]], dtype=np.float32),
    )
    assert SoundDeviceRecorder(capture_seconds=0.001).capture() is not None
    monkeypatch.setattr(
        sounddevice,
        "rec",
        lambda *args, **kwargs: np.asarray([[0.0], [0.0]], dtype=np.float32),
    )
    assert SoundDeviceRecorder(capture_seconds=0.001).capture() is None


def test_sound_recorder_normalizes_portaudio_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sounddevice

    monkeypatch.setattr(
        sounddevice,
        "rec",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            sounddevice.PortAudioError("disconnected")
        ),
    )
    with pytest.raises(RuntimeError, match="capture failed"):
        SoundDeviceRecorder(capture_seconds=0.001).capture()


def test_speech_outputs_validate_tools_and_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("ai4binance.voice.runtime.shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="external TTS is disabled"):
        EdgeTtsSpeaker().speak("test")

    executable = Path(sys.executable).parent / "edge-playback.exe"
    monkeypatch.setattr(
        "ai4binance.voice.runtime.shutil.which", lambda name: str(executable)
    )
    monkeypatch.setattr(
        "ai4binance.voice.runtime.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    EdgeTtsSpeaker(external_service_allowed=True).speak("test")
    monkeypatch.setattr(
        "ai4binance.voice.runtime.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )
    with pytest.raises(RuntimeError, match="failed"):
        EdgeTtsSpeaker(external_service_allowed=True).speak("test")

    script = tmp_path / "speak.ps1"
    script.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "ai4binance.voice.runtime.shutil.which",
        lambda name: "C:/Windows/powershell.exe",
    )
    monkeypatch.setattr(
        "ai4binance.voice.runtime.subprocess.run", lambda *args, **kwargs: None
    )
    WindowsSapiSpeaker(script).speak("test")

    primary = Speaker()
    fallback = Speaker()
    monkeypatch.setattr(primary, "speak", lambda text: (_ for _ in ()).throw(OSError()))
    FallbackSpeechOutput(primary, fallback).speak("yedek")
    assert fallback.spoken == ["yedek"]


def test_environment_audio_probes_handle_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sounddevice

    monkeypatch.setattr(
        sounddevice, "query_devices", lambda: [{"max_input_channels": 1}]
    )
    assert microphone_available() is True
    monkeypatch.setattr(
        sounddevice,
        "query_devices",
        lambda: (_ for _ in ()).throw(RuntimeError()),
    )
    assert microphone_available() is False
    assert isinstance(interactive_windows_user(), bool)


def test_private_state_wait_detects_ready_and_timeout(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    assert wait_for_private_state(state, timeout_seconds=0) is False
    state.write_text("{}", encoding="utf-8")
    assert wait_for_private_state(state, timeout_seconds=0.1) is True


def test_private_state_reader_rejects_stale_future_and_naive_reports(
    tmp_path: Path,
) -> None:
    path = tmp_path / "account.json"
    payload = account_payload()
    payload["created_at"] = (NOW - timedelta(seconds=181)).isoformat()
    path.write_text(json.dumps(payload), encoding="utf-8")
    reader = PrivateAccountStateReader(path, clock=lambda: NOW)
    with pytest.raises(ValueError, match="stale"):
        reader.read()

    payload["created_at"] = (NOW + timedelta(seconds=31)).isoformat()
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="future"):
        reader.read()

    payload["created_at"] = "2026-07-14T00:00:00"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="naive"):
        reader.read()


class CountingRecorder(Recorder):
    def __init__(self, audio: object | None = object()) -> None:
        super().__init__(audio)
        self.calls = 0

    def capture(self) -> object | None:
        self.calls += 1
        return super().capture()


def test_mute_latches_and_stops_all_future_capture_and_transcription() -> None:
    speaker = Speaker()
    service = runtime(voice_command("MUTE"), speaker)
    recorder = CountingRecorder()
    service.recorder = recorder

    result = service.run_once()
    assert result is not None
    assert result.intent is VoiceIntent.MUTE
    assert recorder.calls == 1
    assert service.muted is True
    assert service.run_once() is None
    assert recorder.calls == 1


class FailingRecorder:
    def capture(self) -> object | None:
        raise RuntimeError("device disconnected")


class FailingTranscriber:
    def transcribe(self, audio: object) -> str:
        raise RuntimeError("model temporarily unavailable")


def test_transient_audio_errors_are_health_reported_without_killing_daemon(
    tmp_path: Path,
) -> None:
    speaker = Speaker()
    service = runtime(voice_command("SYSTEM_STATUS"), speaker)
    health_path = tmp_path / "voice-health.json"
    service.health_store = VoiceHealthStore(health_path)
    service.recorder = FailingRecorder()

    assert service.run_once() is None
    payload = json.loads(health_path.read_text(encoding="utf-8"))
    assert payload["state"] == "DEGRADED"
    assert payload["last_error_code"] == "VOICE_RECORDER_FAILED"
    assert payload["execution_allowed"] is False

    service.recorder = Recorder()
    service.transcriber = FailingTranscriber()
    assert service.run_once() is None
    payload = json.loads(health_path.read_text(encoding="utf-8"))
    assert payload["last_error_code"] == "VOICE_STT_FAILED"
    assert payload["stt_failures"] == 1


def test_tts_failure_is_reported_and_command_result_survives(tmp_path: Path) -> None:
    class FailingSpeaker:
        def speak(self, text: str) -> None:
            raise RuntimeError(text)

    service = runtime(voice_command("SYSTEM_STATUS"), Speaker())
    health_path = tmp_path / "voice-health.json"
    service.health_store = VoiceHealthStore(health_path)
    service.speaker = FailingSpeaker()

    result = service.run_once()

    assert result is not None
    assert result.accepted is True
    payload = json.loads(health_path.read_text(encoding="utf-8"))
    assert payload["last_error_code"] == "VOICE_TTS_FAILED"
    assert payload["tts_failures"] == 1


def test_scheduled_safe_status_report_works_without_owner_verification(
    tmp_path: Path,
) -> None:
    speaker = Speaker()
    service = runtime(voice_command("SYSTEM_STATUS"), speaker)
    service.session = assess_local_session(
        interactive_user=True, microphone_available=True
    )
    service.recorder = Recorder(None)
    service.scheduler.last_report_at = NOW - timedelta(seconds=61)
    health_path = tmp_path / "voice-health.json"
    service.health_store = VoiceHealthStore(health_path)

    assert service.run_once() is None
    assert speaker.spoken == [service.status_responder()]
    payload = json.loads(health_path.read_text(encoding="utf-8"))
    assert payload["state"] == "LIMITED"
    assert payload["last_blocker"] == "VOICE_OWNER_VERIFICATION_UNAVAILABLE"


def test_voice_health_store_persists_gpu_telemetry_assessment(
    tmp_path: Path,
) -> None:
    speaker = Speaker()
    service = runtime(
        voice_command("SYSTEM_STATUS"),
        speaker,
        telemetry_assessment=_gpu_assessment(),
    )
    health_path = tmp_path / "voice-health.json"
    service.health_store = VoiceHealthStore(health_path)
    service.recorder = Recorder(None)

    assert service.run_once() is None
    payload = json.loads(health_path.read_text(encoding="utf-8"))
    assessment = payload["telemetry_assessment"]

    assert assessment["source_label"] == "nvidia-smi"
    assert assessment["healthy"] is True
    assert assessment["blockers"] == []


def _gpu_assessment() -> GpuTelemetryAssessment:
    return GpuTelemetryAssessment(
        observed_at=NOW,
        source_label="nvidia-smi",
        cuda_available=True,
        device_name="NVIDIA GeForce RTX 4090",
        driver_version="555.85",
        total_vram_bytes=24_064_000_000,
        free_vram_bytes=18_048_000_000,
        gpu_utilization_pct=19,
        active_gpu_processes=1,
        headroom_percent=30,
        healthy=True,
        blockers=(),
    )
