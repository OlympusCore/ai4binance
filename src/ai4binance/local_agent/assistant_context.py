"""Read-only assistant context owned by the Python application boundary."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from ai4binance.schema_validation import OfflineSchemaRegistry


@cache
def request_registry() -> OfflineSchemaRegistry:
    return OfflineSchemaRegistry.from_directory(
        Path(__file__).resolve().parents[3] / "schemas/interface"
    )


def localization() -> dict[str, str]:
    root = Path(__file__).resolve().parents[3]
    return dict(
        yaml.safe_load(
            (root / "config/localization/assistant_wallet.tr-TR.yaml").read_text(
                encoding="utf-8"
            )
        )["messages"]
    )


def system_prompt() -> str:
    root = Path(__file__).resolve().parents[3]
    return str(
        yaml.safe_load(
            (root / "config/agents/local_assistant.yaml").read_text(encoding="utf-8")
        )["system_prompt"]
    )


def is_status_query(text: str) -> bool:
    return bool(
        re.search(
            r"(?:^|[\s/])(?:status|durum|ozet|summary|system|sistem|son durum)"
            r"(?:$|[\s/])",
            normalize_text(text),
        )
    )


def runtime_status(state_directory: Path, now: datetime) -> dict[str, Any]:
    """Consume only fresh safe state; missing observations remain unavailable."""
    try:
        with (state_directory / "runtime.json").open("rb") as stream:
            raw = stream.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("RUNTIME_STATE_TOO_LARGE")
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or payload.get("execution_allowed") is not False
        ):
            raise ValueError("RUNTIME_STATE_INVALID")
        observed = payload.get("updated_at") or payload.get("created_at")
        if not isinstance(observed, str):
            raise ValueError("RUNTIME_TIMESTAMP_INVALID")
        if not -30 <= (now - parse_timestamp(observed)).total_seconds() <= 180:
            raise ValueError("RUNTIME_STATE_STALE")
        if payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED":
            raise ValueError("RUNTIME_AUTHORITY_INVALID")
        if not isinstance(payload.get("blockers"), list) or not all(
            isinstance(item, str) for item in payload["blockers"]
        ):
            raise ValueError("RUNTIME_BLOCKERS_INVALID")
        if not isinstance(payload.get("state"), str):
            raise ValueError("RUNTIME_STATUS_INVALID")
        result = {"state": payload["state"], "blocker_count": len(payload["blockers"])}
        learning = learning_projection(payload.get("controlled_learning"))
        if learning is not None:
            result["controlled_learning"] = learning
        return result
    except OSError, ValueError, TypeError, KeyError:
        return {"state": "DATA_UNAVAILABLE", "blocker_count": None}


def learning_projection(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict) or (
        value.get("execution_allowed") is not False
        or value.get("risk_change_allowed") is not False
        or value.get("promotion_status") != "RESEARCH_ONLY"
        or not isinstance(value.get("status"), str)
    ):
        return None
    counts = ("lesson_count", "experiment_count")
    if not all(type(value.get(key)) is int and value[key] >= 0 for key in counts):
        return None
    return {key: value[key] for key in ("status", "promotion_status", *counts)}


def learning_answer(state_directory: Path, now: datetime) -> str:
    messages = localization()
    learning = runtime_status(state_directory, now).get("controlled_learning")
    if learning is None:
        summary = learning_summary_projection(state_directory, now)
        if summary is None:
            return messages["LearningBoundary"]
        return messages["LearningSummary"].format(
            summary["lesson_count"], summary["experiment_count"]
        )
    return messages["LearningStatus"].format(
        learning["status"], learning["lesson_count"], learning["experiment_count"]
    )


def learning_summary_projection(
    state_directory: Path, now: datetime
) -> dict[str, object] | None:
    try:
        with (state_directory / "learning_summary.json").open("rb") as stream:
            raw = stream.read(2_000_001)
        if len(raw) > 2_000_000:
            return None
        value = json.loads(raw)
        if (
            not -30
            <= (now - parse_timestamp(value["created_at"])).total_seconds()
            <= 86400
        ):
            return None
        if not isinstance(value["lessons"], list) or not isinstance(
            value["experiments"], list
        ):
            return None
        return learning_projection(
            {
                "status": "RESEARCH_ONLY",
                "promotion_status": value.get("promotion_status"),
                "execution_allowed": value.get("execution_allowed"),
                "risk_change_allowed": value.get("risk_change_allowed"),
                "lesson_count": len(value["lessons"]),
                "experiment_count": len(value["experiments"]),
            }
        )
    except OSError, ValueError, TypeError, KeyError, AttributeError:
        return None


def fast_answer(request: dict[str, Any], now: datetime) -> str | None:
    answer = wallet_answer(
        request["input_text"],
        request.get("context_text", ""),
        Path(request["state_path"]),
        now,
    )
    if answer["handled"]:
        return str(answer["message"])
    normalized = normalize_text(request["input_text"])
    if re.search(r"auto[- ]?learn|controlled learning|ogrenme|learning", normalized):
        if re.search(r"aktif mi|calisiyor mu|acik mi|durum|hazir mi", normalized):
            return learning_answer(Path(request["state_directory"]), now)
    if not is_status_query(normalized):
        return None
    status = runtime_status(Path(request["state_directory"]), now)
    messages = localization()
    if status["state"] == "DATA_UNAVAILABLE":
        return messages["RuntimeUnavailable"]
    return messages["RuntimeStatus"].format(status["state"], status["blocker_count"])


def normalize_text(text: str) -> str:
    """Normalize localized user input without changing evidence."""
    decomposed = unicodedata.normalize(
        "NFD", text.strip().lower().replace("\u0131", "i")
    )
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("PRIVATE_ACCOUNT_STATE_TIMESTAMP_INVALID")
    return parsed


def read_verified_account(path: Path, now: datetime) -> dict[str, Any]:
    """Read a bounded snapshot; never expose private records to the caller."""
    with path.open("rb") as stream:
        raw = stream.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("PRIVATE_ACCOUNT_STATE_TOO_LARGE")
    if b"BINANCE_API_KEY" in raw or b"BINANCE_API_SECRET" in raw:
        raise ValueError("PRIVATE_ACCOUNT_STATE_FORBIDDEN_FIELDS")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("PRIVATE_ACCOUNT_STATE_INVALID_SHAPE")
    if (
        payload.get("execution_allowed") is not False
        or payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
    ):
        raise ValueError("PRIVATE_ACCOUNT_STATE_EXECUTION_AUTHORITY_INVALID")
    age = (now - parse_timestamp(payload["created_at"])).total_seconds()
    if not -30 <= age <= 180:
        raise ValueError("PRIVATE_ACCOUNT_STATE_STALE")
    return payload


def wallet_query_kind(text: str) -> str:
    for candidate, pattern in (
        ("OPPORTUNITY", r"firsat|opportunity|setup"),
        ("VALUE", r"deger|bakiye|toplam|ne\s+kadar|kac"),
        ("CONTENTS", r"ne\s+icer|neler\s+var|envanter|varlik"),
        ("DEFINITION", r"tanimli|defined|mevcut\s+mi|var\s+mi"),
    ):
        if re.search(pattern, text):
            return candidate
    return "STATUS"


def wallet_answer(
    input_text: str, context_text: str, state_path: Path, now: datetime
) -> dict[str, object]:
    """Project only the established redacted, advisory wallet answer."""
    wallet = r"(?:binan(?:ce)?[\\_\s-]*wallet|wallet|cuzdan|bakiye|portfoy)"
    text = normalize_text(input_text)
    follow_up = (
        r"(?:ne\s+icer|neler\s+var|su\s*an|guncel|deger|firsat|dalga|sacma|cevap)"
    )
    if not (
        re.search(wallet, text)
        or (
            re.search(follow_up, text)
            and re.search(wallet, normalize_text(context_text))
        )
    ):
        return {
            "handled": False,
            "evidence_status": "NOT_APPLICABLE",
            "query_kind": "NONE",
            "message": "",
        }
    kind = wallet_query_kind(text)
    messages = localization()
    result: dict[str, object] = {
        "handled": True,
        "evidence_status": "DATA_UNAVAILABLE",
        "query_kind": kind,
        "message": messages["AccountUnavailable"],
    }
    try:
        payload = read_verified_account(state_path, now)
        observed = (
            parse_timestamp(payload["created_at"])
            .astimezone(timezone(timedelta(hours=3)))
            .strftime("%Y-%m-%d %H:%M:%S %z")
        )
        observed = observed[:-2] + ":" + observed[-2:]
        status = messages.get(
            str(payload.get("spot", {}).get("wallet_status", "")).title(),
            messages["Unknown"],
        )
        value = None
        try:
            candidate_value = Decimal(
                str(payload.get("portfolio_analytics", {}).get("total_value_usdt"))
            )
            if candidate_value.is_finite() and candidate_value >= 0:
                value = f"{candidate_value:.2f}"
        except InvalidOperation:
            pass
        if kind == "DEFINITION":
            message = messages["Definition"].format(observed, status)
        elif kind == "VALUE":
            message = (
                messages["Value"].format(observed, value)
                if value is not None
                else messages["ValueUnavailable"]
            )
        elif kind == "CONTENTS":
            assets = sorted(
                {
                    item["asset"]
                    for item in payload.get("inventory", [])
                    if isinstance(item, dict)
                    and isinstance(item.get("asset"), str)
                    and re.fullmatch(r"[A-Z0-9]{2,20}", item["asset"])
                }
            )
            message = (
                messages["Contents"].format(len(assets), ", ".join(assets))
                if assets
                else messages["ContentsEmpty"]
            )
        elif kind == "OPPORTUNITY":
            count = sum(
                isinstance(item, dict)
                and item.get("category") == "NEW_OPPORTUNITY"
                and item.get("action") == "WATCHLIST"
                and item.get("execution_allowed") is False
                for item in payload.get("investment_management", {}).get(
                    "recommendations", []
                )
            )
            message = messages["Opportunity"].format(count)
        else:
            message = (
                messages["Status"].format(observed, status, value)
                if value is not None
                else messages["StatusWithoutValue"].format(observed, status)
            )
    except OSError, ValueError, TypeError, KeyError, AttributeError:
        return result
    return {**result, "evidence_status": "VERIFIED_LOCAL_SNAPSHOT", "message": message}


def format_answer(answer: str) -> str:
    answer = re.sub(
        r"(?is)^\s*(?:(?:###\s*)?(?:assistant|asistan)\s*:\s*)+", "", answer.strip()
    )
    lines = answer.splitlines()
    while lines and lines[0].strip().rstrip(":").strip() in {"", "🇹🇷", "\u03b1"}:
        lines.pop(0)
    answer = re.sub(
        r"(?im)\s*\[Europe/Istanbul time:\s*[^\]]+\]\s*$", "", "\n".join(lines)
    ).strip()
    if not answer:
        raise ValueError("LOCAL_LLM_EMPTY_RESPONSE_AFTER_NORMALIZATION")
    return answer


def build_prompt(system_prompt: str, messages: list[dict[str, str]]) -> str:
    parts = ["### System:", system_prompt.strip(), ""]
    for message in messages:
        role = message.get("role")
        content = message.get("content", "").strip()
        if role in {"user", "assistant"} and content:
            parts.extend([f"### {role.title()}:", content, ""])
    return "\n".join([*parts, "### Assistant:"])


def append_history(
    messages: list[dict[str, str]], role: str, content: str, max_turns: int
) -> list[dict[str, str]]:
    """Keep bounded conversational context without accepting system authority."""
    if role not in {"user", "assistant"} or not 1 <= max_turns <= 100:
        raise ValueError("ASSISTANT_HISTORY_INVALID")
    retained = [item for item in messages if item.get("role") in {"user", "assistant"}]
    return [*retained, {"role": role, "content": content}][-(max_turns * 2) :]


def complete(request: dict[str, Any]) -> str:
    from ai4binance.rag import LlamaCppAdvisoryRunner

    response = LlamaCppAdvisoryRunner(
        base_url=request["endpoint"],
        timeout_seconds=float(request["timeout_seconds"]),
        num_predict=request["max_tokens"],
        stop_sequences=("### User:", "### System:", "</s>"),
    ).run(request["prompt"], ())
    if not response.response_text:
        raise ValueError("LOCAL_LLM_COMPLETION_BLOCKED")
    return response.response_text


def dispatch(request: dict[str, Any]) -> object:
    """Route input only to explicit application-owned operations."""
    from collections.abc import Callable

    request_registry().validate(
        "https://ai4binance.local/schemas/interface/assistant_request.schema.json",
        request,
    )

    handlers: dict[str, Callable[[], object]] = {
        "wallet_answer": lambda: wallet_answer(
            request["input_text"],
            request.get("context_text", ""),
            Path(request["state_path"]),
            parse_timestamp(request["now"]),
        ),
        "format_answer": lambda: format_answer(request["answer"]),
        "build_prompt": lambda: build_prompt(
            request["system_prompt"], request["messages"]
        ),
        "system_prompt": system_prompt,
        "append_history": lambda: append_history(
            request["messages"],
            request["role"],
            request["content"],
            request["max_turns"],
        ),
        "recent_context": lambda: "\n".join(
            item["content"]
            for item in request["messages"]
            if item.get("role") == "user"
        )[-6000:],
        "is_status_query": lambda: is_status_query(request["input_text"]),
        "runtime_status": lambda: runtime_status(
            Path(request["state_directory"]), parse_timestamp(request["now"])
        ),
        "fast_answer": lambda: fast_answer(request, parse_timestamp(request["now"])),
        "complete": lambda: complete(request),
    }
    handler = handlers.get(request["operation"])
    if handler is None:
        raise ValueError("ASSISTANT_OPERATION_UNSUPPORTED")
    return handler()


def main() -> int:
    """Serve one JSON request over stdin without logging private input."""
    try:
        raw = sys.stdin.buffer.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("ASSISTANT_REQUEST_TOO_LARGE")
        result = dispatch(json.loads(raw.decode("utf-8-sig")))
        print(json.dumps({"result": result}, ensure_ascii=True))
        return 0
    except OSError, ValueError, TypeError, KeyError:
        print("ASSISTANT_REQUEST_FAILED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
