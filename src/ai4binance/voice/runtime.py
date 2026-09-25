"""Real microphone/STT/TTS runtime bounded to read-only advisory intents."""

from __future__ import annotations

import json
import os
import shutil
import subprocess  # nosec B404
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast

from ai4binance.enterprise import GpuTelemetryAssessment
from ai4binance.voice.gateway import (
    LocalVoiceSession,
    VoiceCommandGateway,
    VoiceCommandResult,
    VoiceIntent,
)
from ai4binance.voice.localization import TR_VOICE_MESSAGES


class AudioRecorder(Protocol):
    def capture(self) -> object | None: ...


class SpeechTranscriber(Protocol):
    def transcribe(self, audio: object) -> str: ...


class SpeechOutput(Protocol):
    def speak(self, text: str) -> None: ...


class WhisperSegment(Protocol):
    text: str


class WhisperBackend(Protocol):
    def transcribe(
        self, audio: object, **kwargs: object
    ) -> tuple[Sequence[WhisperSegment], object]: ...


class WhisperModelFactory(Protocol):
    def __call__(
        self,
        model_name: str,
        *,
        device: str,
        compute_type: str,
        download_root: str,
    ) -> WhisperBackend: ...


@dataclass(frozen=True, slots=True)
class PrivateAccountStateReader:
    path: Path
    max_bytes: int = 2_000_000
    max_age_seconds: float = 180.0
    future_tolerance_seconds: float = 30.0
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC), repr=False)

    def read(self) -> Mapping[str, object]:
        try:
            if self.path.stat().st_size > self.max_bytes:
                raise ValueError("private account report exceeds size limit")
            raw = self.path.read_text(encoding="utf-8")
        except OSError:
            raise ValueError("private account report is unavailable") from None
        if "BINANCE_API_KEY" in raw or "BINANCE_API_SECRET" in raw:
            raise ValueError("private account report contains forbidden fields")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("private account report is invalid JSON") from None
        if not isinstance(payload, Mapping):
            raise ValueError("private account report must be an object")
        if payload.get("execution_allowed") is not False:
            raise ValueError("private account report cannot grant execution")
        created_at = payload.get("created_at")
        if not isinstance(created_at, str):
            raise ValueError("private account report has no freshness timestamp")
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(
                "private account report freshness timestamp is invalid"
            ) from None
        now = self.clock()
        if created.tzinfo is None or created.utcoffset() is None:
            raise ValueError("private account report freshness timestamp is naive")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("private account reader clock must be timezone-aware")
        age = (now - created).total_seconds()
        if age < -self.future_tolerance_seconds:
            raise ValueError("private account report timestamp is in the future")
        if age > self.max_age_seconds:
            raise ValueError("private account report is stale")
        return cast(Mapping[str, object], payload)


@dataclass(slots=True)
class VoiceResponseBuilder:
    state_reader: PrivateAccountStateReader
    last_response: str = ""

    def respond(self, intent: VoiceIntent) -> str:
        if intent is VoiceIntent.REPEAT:
            return self.last_response or TR_VOICE_MESSAGES.repeat_unavailable
        if intent is VoiceIntent.STOP_LISTENING:
            return TR_VOICE_MESSAGES.stop_listening
        if intent is VoiceIntent.MUTE:
            return TR_VOICE_MESSAGES.mute
        try:
            payload = self.state_reader.read()
            response = self._build(intent, payload)
        except ValueError:
            response = TR_VOICE_MESSAGES.account_report_unavailable
        self.last_response = response[:1_200]
        return self.last_response

    def _build(self, intent: VoiceIntent, payload: Mapping[str, object]) -> str:
        if intent is VoiceIntent.SYSTEM_STATUS:
            spot = _mapping(payload.get("spot"))
            futures = _mapping(payload.get("futures"))
            blockers = _texts(payload.get("blockers"))
            return TR_VOICE_MESSAGES.system_status(
                state=payload.get("state", "UNKNOWN"),
                spot_wallet_status=spot.get("wallet_status", "UNKNOWN"),
                futures_wallet_status=futures.get("wallet_status", "UNKNOWN"),
                blockers=_join_or_none(blockers),
            )
        if intent is VoiceIntent.SPOT_OUTLOOK:
            return _market_outlook("Spot", _mapping(payload.get("spot")))
        if intent is VoiceIntent.FUTURES_OUTLOOK:
            return _market_outlook("Futures", _mapping(payload.get("futures")))
        if intent is VoiceIntent.INVENTORY:
            inventory = _mappings(payload.get("inventory"))
            items = [
                TR_VOICE_MESSAGES.inventory_item(
                    asset=item.get("asset", "UNKNOWN"),
                    total=item.get("total", "0"),
                )
                for item in inventory[:10]
            ]
            return TR_VOICE_MESSAGES.inventory(_join_or_none(items))
        if intent is VoiceIntent.FUTURES_POSITIONS:
            positions = _mappings(payload.get("futures_positions"))
            items = [
                TR_VOICE_MESSAGES.futures_position_item(
                    symbol=item.get("symbol", "UNKNOWN"),
                    side=item.get("side", "UNKNOWN"),
                    quantity=item.get("quantity", "0"),
                    unrealized_pnl=item.get("unrealized_pnl", "0"),
                )
                for item in positions[:10]
            ]
            return TR_VOICE_MESSAGES.futures_positions(_join_or_none(items))
        if intent is VoiceIntent.OPEN_ORDERS:
            orders = _mappings(payload.get("open_orders"))
            items = [
                TR_VOICE_MESSAGES.open_order_item(
                    market=item.get("market", "UNKNOWN"),
                    symbol=item.get("symbol", "UNKNOWN"),
                    side=item.get("side", "UNKNOWN"),
                    status=item.get("status", "UNKNOWN"),
                    remaining_quantity=item.get("remaining_quantity", "0"),
                )
                for item in orders[:10]
            ]
            return TR_VOICE_MESSAGES.open_orders(_join_or_none(items))
        blockers = _texts(payload.get("blockers"))
        return TR_VOICE_MESSAGES.blockers(_join_or_none(blockers))


def _mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else {}


def _mappings(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [
        cast(Mapping[str, object], item) for item in value if isinstance(item, Mapping)
    ]


def _texts(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value]


def _join_or_none(items: Sequence[str]) -> str:
    return ", ".join(items) if items else TR_VOICE_MESSAGES.none_value


def _market_outlook(label: str, market: Mapping[str, object]) -> str:
    blockers = _texts(market.get("blockers"))
    return TR_VOICE_MESSAGES.market_outlook(
        label=label,
        action=market.get("action", "NO_TRADE"),
        bias=market.get("bias", "UNKNOWN"),
        blockers=_join_or_none(blockers),
    )


@dataclass(frozen=True, slots=True)
class SoundDeviceRecorder:
    capture_seconds: float = 4.0
    sample_rate: int = 16_000
    silence_rms: float = 0.008

    def capture(self) -> object | None:
        import numpy as np
        import sounddevice as sd

        try:
            audio = sd.rec(
                int(self.capture_seconds * self.sample_rate),
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
            )
            sd.wait()
        except sd.PortAudioError:
            raise RuntimeError("microphone capture failed") from None
        flattened = np.asarray(audio, dtype=np.float32).reshape(-1)
        rms = float(np.sqrt(np.mean(np.square(flattened))))
        return flattened if rms >= self.silence_rms else None


@dataclass(slots=True)
class FasterWhisperTranscriber:
    model_name: str
    model_directory: Path
    device: str = "cpu"
    compute_type: str = "int8"
    fallback_device: str = "cpu"
    fallback_compute_type: str = "int8"
    _model: WhisperBackend = field(init=False, repr=False)

    def __post_init__(self) -> None:
        import truststore
        from faster_whisper import WhisperModel

        truststore.inject_into_ssl()
        self.model_directory.mkdir(parents=True, exist_ok=True)
        try:
            self._model = self._load_model(
                WhisperModel,
                device=self.device,
                compute_type=self.compute_type,
            )
        except (OSError, RuntimeError, ValueError):
            if (
                self.device == self.fallback_device
                and self.compute_type == self.fallback_compute_type
            ):
                raise
            self._model = self._load_model(
                WhisperModel,
                device=self.fallback_device,
                compute_type=self.fallback_compute_type,
            )

    def _load_model(
        self,
        whisper_model: WhisperModelFactory,
        *,
        device: str,
        compute_type: str,
    ) -> WhisperBackend:
        return whisper_model(
            self.model_name,
            device=device,
            compute_type=compute_type,
            download_root=str(self.model_directory),
        )

    def transcribe(self, audio: object) -> str:
        segments, _info = self._model.transcribe(
            audio,
            language="tr",
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(str(segment.text).strip() for segment in segments).strip()


@dataclass(frozen=True, slots=True)
class EdgeTtsSpeaker:
    voice: str = "tr-TR-EmelNeural"
    timeout_seconds: float = 60.0
    external_service_allowed: bool = False

    def speak(self, text: str) -> None:
        if not self.external_service_allowed:
            raise RuntimeError("external TTS is disabled for financial reports")
        bounded = text.strip()[:1_200]
        executable = shutil.which("edge-playback")
        if not bounded or executable is None:
            raise RuntimeError("Edge TTS playback is unavailable")
        resolved = Path(executable).resolve()
        if resolved.parent != Path(sys.executable).resolve().parent:
            raise RuntimeError("Edge TTS executable is outside the active runtime")
        completed = subprocess.run(  # noqa: S603  # nosec B603
            [str(resolved), "--voice", self.voice, "--text", bounded],
            check=False,
            capture_output=True,
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError("Edge TTS playback failed")


@dataclass(frozen=True, slots=True)
class WindowsSapiSpeaker:
    script_path: Path

    def speak(self, text: str) -> None:
        bounded = text.strip()[:1_200]
        if not bounded or not self.script_path.is_file():
            raise RuntimeError("Windows SAPI fallback is unavailable")
        executable = shutil.which("powershell.exe")
        if executable is None:
            raise RuntimeError("Windows PowerShell is unavailable")
        subprocess.run(  # noqa: S603  # nosec B603
            [
                str(Path(executable).resolve()),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.script_path.resolve()),
                "-Text",
                bounded,
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )


@dataclass(frozen=True, slots=True)
class FallbackSpeechOutput:
    primary: SpeechOutput
    fallback: SpeechOutput

    def speak(self, text: str) -> None:
        try:
            self.primary.speak(text)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            self.fallback.speak(text)


@dataclass(slots=True)
class VoiceReportScheduler:
    interval_seconds: float = 1_800.0
    last_report_at: datetime | None = None

    def due(self, now: datetime) -> bool:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("voice scheduler timestamp must be timezone-aware")
        if self.last_report_at is None:
            self.last_report_at = now
            return False
        if (now - self.last_report_at).total_seconds() < self.interval_seconds:
            return False
        self.last_report_at = now
        return True


@dataclass(slots=True)
class VoiceRuntimeHealth:
    state: str = "STARTING"
    updated_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error_code: str = ""
    last_blocker: str = ""
    consecutive_failures: int = 0
    recorder_failures: int = 0
    stt_failures: int = 0
    tts_failures: int = 0
    accepted_commands: int = 0
    rejected_commands: int = 0
    muted: bool = False
    listening: bool = True
    telemetry_assessment: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class VoiceHealthStore:
    path: Path = Path("runtime/state/private/voice-health.json")

    def save(self, health: VoiceRuntimeHealth) -> None:
        payload = {
            "state": health.state,
            "updated_at": health.updated_at,
            "last_success_at": health.last_success_at,
            "last_error_at": health.last_error_at,
            "last_error_code": health.last_error_code,
            "last_blocker": health.last_blocker,
            "consecutive_failures": health.consecutive_failures,
            "recorder_failures": health.recorder_failures,
            "stt_failures": health.stt_failures,
            "tts_failures": health.tts_failures,
            "accepted_commands": health.accepted_commands,
            "rejected_commands": health.rejected_commands,
            "muted": health.muted,
            "listening": health.listening,
            "telemetry_assessment": health.telemetry_assessment,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
            encoding="utf-8",
        )
        temporary.replace(self.path)


@dataclass(slots=True)
class VoiceAssistantRuntime:
    recorder: AudioRecorder
    transcriber: SpeechTranscriber
    speaker: SpeechOutput
    gateway: VoiceCommandGateway
    session: LocalVoiceSession
    scheduler: VoiceReportScheduler
    status_responder: Callable[[], str]
    telemetry_assessment: GpuTelemetryAssessment | None = None
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    health: VoiceRuntimeHealth = field(default_factory=VoiceRuntimeHealth)
    health_store: VoiceHealthStore | None = field(default_factory=VoiceHealthStore)
    health_heartbeat_seconds: float = 30.0
    _last_health_write_at: datetime | None = field(default=None, init=False, repr=False)
    muted: bool = False

    def __post_init__(self) -> None:
        if self.telemetry_assessment is not None:
            self.health.telemetry_assessment = self.telemetry_assessment.to_payload()

    def run_once(self) -> VoiceCommandResult | None:
        now = self.clock()
        if self.muted:
            self._publish_health(now, force=True)
            return None
        if self.scheduler.due(now):
            try:
                self.speaker.speak(self.status_responder())
            except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
                self._record_error("VOICE_TTS_FAILED", now, "tts_failures")
        try:
            audio = self.recorder.capture()
        except (OSError, RuntimeError, ValueError):
            self._record_error("VOICE_RECORDER_FAILED", now, "recorder_failures")
            return None
        if audio is None:
            self._record_success(now)
            return None
        try:
            transcript = self.transcriber.transcribe(audio)
        except (OSError, RuntimeError, ValueError):
            self._record_error("VOICE_STT_FAILED", now, "stt_failures")
            return None
        if not transcript:
            self._record_success(now)
            return None
        result = self.gateway.handle_local(transcript, self.session)
        if result.accepted:
            self.health.accepted_commands += 1
            if result.intent is VoiceIntent.MUTE:
                self.muted = True
                self.health.muted = True
                self.health.listening = False
                self.health.state = "MUTED"
            elif result.intent is VoiceIntent.STOP_LISTENING:
                self.health.listening = False
                self.health.state = "STOPPED"
            try:
                self.speaker.speak(result.response)
            except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
                self._record_error("VOICE_TTS_FAILED", now, "tts_failures")
        else:
            self.health.rejected_commands += 1
            self.health.last_blocker = result.blockers[0]
        terminal = result.intent in {VoiceIntent.MUTE, VoiceIntent.STOP_LISTENING}
        self._record_success(now, preserve_state=terminal)
        return result

    def _record_success(self, now: datetime, *, preserve_state: bool = False) -> None:
        self.health.updated_at = now
        self.health.last_success_at = now
        self.health.consecutive_failures = 0
        if not preserve_state and not self._owner_verified():
            self.health.state = "LIMITED"
            self.health.last_blocker = "VOICE_OWNER_VERIFICATION_UNAVAILABLE"
        elif not preserve_state:
            self.health.state = "HEALTHY"
        self._publish_health(now)

    def _owner_verified(self) -> bool:
        verification = self.session.owner_verification
        return verification is not None and verification.accepted

    def _record_error(self, code: str, now: datetime, counter: str) -> None:
        self.health.state = "DEGRADED"
        self.health.updated_at = now
        self.health.last_error_at = now
        self.health.last_error_code = code
        self.health.consecutive_failures += 1
        setattr(self.health, counter, int(getattr(self.health, counter)) + 1)
        self._publish_health(now, force=True)

    def _publish_health(self, now: datetime, *, force: bool = False) -> None:
        if self.health_store is None:
            return
        due = self._last_health_write_at is None or (
            now - self._last_health_write_at
        ) >= timedelta(seconds=self.health_heartbeat_seconds)
        if not force and not due:
            return
        try:
            self.health_store.save(self.health)
            self._last_health_write_at = now
        except OSError:
            return

    def run(self, *, max_cycles: int | None = None) -> int:
        if max_cycles is not None and max_cycles < 1:
            raise ValueError("max_cycles must be positive")
        completed = 0
        while max_cycles is None or completed < max_cycles:
            result = self.run_once()
            completed += 1
            if result is not None and result.intent in {
                VoiceIntent.STOP_LISTENING,
                VoiceIntent.MUTE,
            }:
                break
        return completed


def microphone_available() -> bool:
    try:
        import sounddevice as sd

        devices = sd.query_devices()
    except (ImportError, OSError, RuntimeError):
        return False
    return any(int(device.get("max_input_channels", 0)) > 0 for device in devices)


def interactive_windows_user() -> bool:
    return os.name == "nt" and bool(os.environ.get("USERNAME"))


def wait_for_private_state(path: Path, timeout_seconds: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.is_file():
            return True
        time.sleep(1.0)
    return False
