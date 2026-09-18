"""Fail-closed tests for explicitly approved social text publishing."""

import json
import urllib.error
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from email.message import Message
from io import BytesIO
from pathlib import Path

import pytest

from ai4binance.content import (
    ComplianceStatus,
    ContentClaim,
    ContentDraft,
    ContentSource,
    HttpPublishRequest,
    HttpPublishResponse,
    LocalApprovalQueue,
    PublishAuditStore,
    PublishingConfig,
    PublishReceipt,
    PublishRequest,
    PublishStatus,
    PublishTransportError,
    SocialPlatform,
    SocialPublishingGateway,
    UrllibPublishingTransport,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def draft(draft_id: str = "a" * 64, *, timestamp: datetime = NOW) -> ContentDraft:
    return ContentDraft(
        draft_id=draft_id,
        created_at=timestamp,
        content=(
            "HOTUSDT | Gorunum\nNO_TRADE: OOS evidence incomplete\n"
            "Arastirma amaclidir; islem sinyali degildir."
        ),
        source=ContentSource(
            artifact_type="market_outlook",
            source_artifact="market-outlook/state.json",
            source_sha256="b" * 64,
            evidence_timestamp=timestamp,
            freshness_status="FRESH",
        ),
        claims=(ContentClaim("NO_TRADE", "no_trade_rationale"),),
        compliance_status=ComplianceStatus.PASSED,
    )


def approved_queue(tmp_path: Path, content_draft: ContentDraft) -> LocalApprovalQueue:
    queue = LocalApprovalQueue(tmp_path / "approval.jsonl", clock=lambda: NOW)
    queue.enqueue(content_draft)
    queue.approve(
        content_draft.draft_id,
        approved_by="operator",
        rationale="Reviewed",
        confirmation="APPROVE_LOCAL_DRAFT",
    )
    return queue


@dataclass(slots=True)
class FakeTransport:
    response: HttpPublishResponse | None = None
    error: PublishTransportError | None = None
    requests: list[HttpPublishRequest] = field(default_factory=list)

    def send(self, request: HttpPublishRequest) -> HttpPublishResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("fake transport response is missing")
        return self.response


def request(content_draft: ContentDraft, platform: SocialPlatform) -> PublishRequest:
    pending = PublishRequest(
        draft=content_draft,
        platform=platform,
        requested_by="operator",
        confirmation="temporary",
    )
    return replace(pending, confirmation=pending.required_confirmation)


def gateway(
    tmp_path: Path,
    content_draft: ContentDraft,
    transport: FakeTransport,
    credentials: dict[str, str],
    *,
    platforms: frozenset[SocialPlatform] = frozenset(SocialPlatform),
    interval: timedelta = timedelta(0),
) -> SocialPublishingGateway:
    return SocialPublishingGateway(
        config=PublishingConfig(
            enabled_platforms=platforms,
            minimum_publish_interval=interval,
        ),
        approval_queue=approved_queue(tmp_path, content_draft),
        audit_store=PublishAuditStore(tmp_path / "publishing.jsonl"),
        transport=transport,
        environment=credentials.get,
        clock=lambda: NOW,
    )


def make_receipt(
    *,
    request_id: str,
    draft_id: str,
    status: PublishStatus,
    requested_at: datetime = NOW,
    platform: SocialPlatform = SocialPlatform.X,
) -> PublishReceipt:
    if status is PublishStatus.PUBLISHED:
        return PublishReceipt(
            request_id=request_id,
            draft_id=draft_id,
            platform=platform,
            requested_by="operator",
            requested_at=requested_at,
            status=status,
            blockers=(),
            remote_post_id="remote-1",
            publish_authority_used=True,
        )
    return PublishReceipt(
        request_id=request_id,
        draft_id=draft_id,
        platform=platform,
        requested_by="operator",
        requested_at=requested_at,
        status=status,
        blockers=("PUBLISH_TRANSPORT_FAILED",),
    )


PLATFORM_CASES = (
    (
        SocialPlatform.X,
        {"AI4BINANCE_X_USER_ACCESS_TOKEN": "x-user-token"},
        HttpPublishResponse(201, {}, b'{"data":{"id":"x-123"}}'),
        "https://api.x.com/2/tweets",
        "x-123",
    ),
    (
        SocialPlatform.TELEGRAM,
        {
            "AI4BINANCE_TELEGRAM_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz",
            "AI4BINANCE_TELEGRAM_CHAT_ID": "@ai4binance",
        },
        HttpPublishResponse(200, {}, b'{"ok":true,"result":{"message_id":456}}'),
        "https://api.telegram.org/bot123456:abcdefghijklmnopqrstuvwxyz/sendMessage",
        "456",
    ),
    (
        SocialPlatform.LINKEDIN,
        {
            "AI4BINANCE_LINKEDIN_ACCESS_TOKEN": "linkedin-token",
            "AI4BINANCE_LINKEDIN_AUTHOR_URN": "urn:li:person:abc123",
            "AI4BINANCE_LINKEDIN_VERSION": "202603",
        },
        HttpPublishResponse(201, {"x-restli-id": "urn:li:share:789"}, b""),
        "https://api.linkedin.com/rest/posts",
        "urn:li:share:789",
    ),
)


@pytest.mark.parametrize(
    ("platform", "credentials", "response", "expected_url", "remote_id"),
    PLATFORM_CASES,
)
def test_gateway_publishes_once_after_all_gates(
    tmp_path: Path,
    platform: SocialPlatform,
    credentials: dict[str, str],
    response: HttpPublishResponse,
    expected_url: str,
    remote_id: str,
) -> None:
    content_draft = draft()
    transport = FakeTransport(response=response)
    service = gateway(tmp_path, content_draft, transport, credentials)

    receipt = service.publish(request(content_draft, platform))

    assert receipt.status is PublishStatus.PUBLISHED
    assert receipt.remote_post_id == remote_id
    assert receipt.publish_authority_used is True
    assert receipt.trading_execution_allowed is False
    assert receipt.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert len(transport.requests) == 1
    assert transport.requests[0].url == expected_url
    audit_text = (tmp_path / "publishing.jsonl").read_text(encoding="utf-8")
    for credential_value in credentials.values():
        assert credential_value not in audit_text


def test_gateway_is_default_deny_and_requires_exact_confirmation(
    tmp_path: Path,
) -> None:
    content_draft = draft()
    transport = FakeTransport()
    service = gateway(
        tmp_path,
        content_draft,
        transport,
        {},
        platforms=frozenset(),
    )
    invalid = PublishRequest(content_draft, SocialPlatform.X, "operator", "yes")

    receipt = service.publish(invalid)

    assert receipt.status is PublishStatus.BLOCKED
    assert receipt.blockers == (
        "PUBLISH_PLATFORM_DISABLED",
        "PUBLISH_EXPLICIT_CONFIRMATION_MISSING",
    )
    assert transport.requests == []


def test_gateway_blocks_missing_credentials_without_writing_intent(
    tmp_path: Path,
) -> None:
    content_draft = draft()
    transport = FakeTransport()
    service = gateway(tmp_path, content_draft, transport, {})

    receipt = service.publish(request(content_draft, SocialPlatform.X))

    assert receipt.blockers == ("PUBLISH_CREDENTIALS_MISSING_OR_INVALID",)
    assert transport.requests == []
    assert service.audit_store.path.exists() is False


def test_gateway_rejects_unapproved_changed_and_stale_drafts(tmp_path: Path) -> None:
    content_draft = draft(timestamp=NOW - timedelta(hours=3))
    queue = approved_queue(tmp_path, content_draft)
    changed = replace(content_draft, content=content_draft.content + " changed")
    service = SocialPublishingGateway(
        PublishingConfig(enabled_platforms=frozenset({SocialPlatform.X})),
        queue,
        PublishAuditStore(tmp_path / "publishing.jsonl"),
        FakeTransport(),
        environment=lambda _: "token",
        clock=lambda: NOW,
    )

    receipt = service.publish(request(changed, SocialPlatform.X))

    assert "PUBLISH_DRAFT_NOT_EXACTLY_APPROVED" in receipt.blockers
    assert "PUBLISH_DRAFT_STALE_OR_FUTURE" in receipt.blockers


def test_successful_request_is_idempotent_and_rate_limited(tmp_path: Path) -> None:
    first = draft("a" * 64)
    transport = FakeTransport(
        response=HttpPublishResponse(201, {}, b'{"data":{"id":"x-1"}}')
    )
    service = gateway(
        tmp_path,
        first,
        transport,
        {"AI4BINANCE_X_USER_ACCESS_TOKEN": "token"},
        interval=timedelta(minutes=5),
    )
    assert service.publish(request(first, SocialPlatform.X)).status is (
        PublishStatus.PUBLISHED
    )

    duplicate = service.publish(request(first, SocialPlatform.X))

    assert "PUBLISH_ALREADY_COMPLETED" in duplicate.blockers
    assert "PUBLISH_RATE_LIMIT_ACTIVE" in duplicate.blockers
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "response",
    [
        HttpPublishResponse(500, {}, b'{"error":"rejected"}'),
        HttpPublishResponse(201, {}, b"not-json"),
        HttpPublishResponse(201, {}, b'{"data":{}}'),
    ],
)
def test_provider_failure_is_audited_and_never_auto_retried(
    tmp_path: Path, response: HttpPublishResponse
) -> None:
    content_draft = draft()
    transport = FakeTransport(response=response)
    service = gateway(
        tmp_path,
        content_draft,
        transport,
        {"AI4BINANCE_X_USER_ACCESS_TOKEN": "token"},
    )

    failed = service.publish(request(content_draft, SocialPlatform.X))
    retry = service.publish(request(content_draft, SocialPlatform.X))

    assert failed.status is PublishStatus.FAILED
    assert retry.blockers == ("PUBLISH_PREVIOUS_FAILURE_REVIEW_REQUIRED",)
    assert len(transport.requests) == 1


def test_transport_failure_leaves_review_required_failure(tmp_path: Path) -> None:
    content_draft = draft()
    transport = FakeTransport(error=PublishTransportError("fake"))
    service = gateway(
        tmp_path,
        content_draft,
        transport,
        {"AI4BINANCE_X_USER_ACCESS_TOKEN": "token"},
    )

    receipt = service.publish(request(content_draft, SocialPlatform.X))

    assert receipt.status is PublishStatus.FAILED
    assert receipt.blockers == ("PUBLISH_TRANSPORT_FAILED",)


def test_open_intent_blocks_uncertain_duplicate(tmp_path: Path) -> None:
    content_draft = draft()
    transport = FakeTransport()
    service = gateway(
        tmp_path,
        content_draft,
        transport,
        {"AI4BINANCE_X_USER_ACCESS_TOKEN": "token"},
    )
    publish_request = request(content_draft, SocialPlatform.X)
    request_id = service._request_id(publish_request)
    service.audit_store.begin(
        request_id=request_id,
        draft_id=content_draft.draft_id,
        platform=SocialPlatform.X,
        requested_by="operator",
        timestamp=NOW,
    )

    receipt = service.publish(publish_request)

    assert receipt.blockers == ("PUBLISH_PREVIOUS_ATTEMPT_UNCERTAIN",)
    assert transport.requests == []


@pytest.mark.parametrize(
    ("platform", "credentials"),
    [
        (
            SocialPlatform.TELEGRAM,
            {
                "AI4BINANCE_TELEGRAM_BOT_TOKEN": "invalid",
                "AI4BINANCE_TELEGRAM_CHAT_ID": "chat",
            },
        ),
        (
            SocialPlatform.LINKEDIN,
            {
                "AI4BINANCE_LINKEDIN_ACCESS_TOKEN": "token",
                "AI4BINANCE_LINKEDIN_AUTHOR_URN": "invalid",
                "AI4BINANCE_LINKEDIN_VERSION": "latest",
            },
        ),
    ],
)
def test_platform_credential_shapes_are_fail_closed(
    tmp_path: Path, platform: SocialPlatform, credentials: dict[str, str]
) -> None:
    content_draft = draft()
    service = gateway(tmp_path, content_draft, FakeTransport(), credentials)

    receipt = service.publish(request(content_draft, platform))

    assert receipt.blockers == ("PUBLISH_CREDENTIALS_MISSING_OR_INVALID",)


def test_http_request_rejects_unallowlisted_and_unbounded_inputs() -> None:
    with pytest.raises(ValueError, match="allowlisted"):
        HttpPublishRequest("file:///secret", {}, b"{}", 1.0, 100)
    with pytest.raises(ValueError, match="body"):
        HttpPublishRequest("https://api.x.com/2/tweets", {}, b"", 1.0, 100)


def test_urllib_transport_bounds_success_http_error_and_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_value = HttpPublishRequest("https://api.x.com/2/tweets", {}, b"{}", 1.0, 10)

    class Response:
        status = 201
        headers = Message()

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self, _: int) -> bytes:
            return b"{}"

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    success = UrllibPublishingTransport().send(request_value)
    assert success.status_code == 201

    http_error = urllib.error.HTTPError(
        request_value.url, 429, "rate", Message(), BytesIO(b"{}")
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(http_error),
    )
    assert UrllibPublishingTransport().send(request_value).status_code == 429

    network_error = urllib.error.URLError("offline")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(network_error),
    )
    with pytest.raises(PublishTransportError, match="transport failed"):
        UrllibPublishingTransport().send(request_value)


def test_model_and_config_contracts_reject_unsafe_values() -> None:
    with pytest.raises(ValueError, match="timeout"):
        PublishingConfig(request_timeout_seconds=0)
    with pytest.raises(ValueError, match="interval"):
        PublishingConfig(minimum_publish_interval=-timedelta(seconds=1))
    with pytest.raises(ValueError, match="maximum draft age"):
        PublishingConfig(maximum_draft_age=timedelta(0))
    with pytest.raises(ValueError, match="response bytes"):
        PublishingConfig(maximum_response_bytes=0)
    with pytest.raises(ValueError, match="requester"):
        PublishRequest(draft(), SocialPlatform.X, "", "confirm")
    with pytest.raises(ValueError, match="confirmation"):
        PublishRequest(draft(), SocialPlatform.X, "operator", "")
    with pytest.raises(ValueError, match="identity"):
        PublishReceipt(
            request_id="bad",
            draft_id="b" * 64,
            platform=SocialPlatform.X,
            requested_by="operator",
            requested_at=NOW,
            status=PublishStatus.BLOCKED,
            blockers=("BLOCKED",),
        )
    with pytest.raises(ValueError, match="timestamp"):
        PublishReceipt(
            request_id="a" * 64,
            draft_id="b" * 64,
            platform=SocialPlatform.X,
            requested_by="operator",
            requested_at=NOW.replace(tzinfo=None),
            status=PublishStatus.BLOCKED,
            blockers=("BLOCKED",),
        )
    with pytest.raises(ValueError, match="published receipt"):
        PublishReceipt(
            request_id="a" * 64,
            draft_id="b" * 64,
            platform=SocialPlatform.X,
            requested_by="operator",
            requested_at=NOW,
            status=PublishStatus.PUBLISHED,
            blockers=(),
        )
    with pytest.raises(ValueError, match="non-published receipt"):
        PublishReceipt(
            request_id="a" * 64,
            draft_id="b" * 64,
            platform=SocialPlatform.X,
            requested_by="operator",
            requested_at=NOW,
            status=PublishStatus.BLOCKED,
            blockers=(),
        )
    with pytest.raises(ValueError, match="trading execution"):
        PublishReceipt(
            request_id="a" * 64,
            draft_id="b" * 64,
            platform=SocialPlatform.X,
            requested_by="operator",
            requested_at=NOW,
            status=PublishStatus.BLOCKED,
            blockers=("BLOCKED",),
            trading_execution_allowed=True,
        )
    with pytest.raises(ValueError, match="live trading status"):
        PublishReceipt(
            request_id="a" * 64,
            draft_id="b" * 64,
            platform=SocialPlatform.X,
            requested_by="operator",
            requested_at=NOW,
            status=PublishStatus.BLOCKED,
            blockers=("BLOCKED",),
            live_eligibility_status="LIVE_APPROVED",
        )


def test_publish_audit_store_rejects_duplicate_begin_and_closed_complete(
    tmp_path: Path,
) -> None:
    store = PublishAuditStore(tmp_path / "publish-audit.jsonl")
    request_id = "a" * 64
    draft_id = "b" * 64

    store.begin(
        request_id=request_id,
        draft_id=draft_id,
        platform=SocialPlatform.X,
        requested_by="operator",
        timestamp=NOW,
    )
    state = store.attempt(request_id)
    assert state is not None
    assert state.outcome is None

    with pytest.raises(ValueError, match="already has an audit event"):
        store.begin(
            request_id=request_id,
            draft_id=draft_id,
            platform=SocialPlatform.X,
            requested_by="operator",
            timestamp=NOW,
        )

    store.complete(
        make_receipt(
            request_id=request_id,
            draft_id=draft_id,
            status=PublishStatus.PUBLISHED,
        )
    )
    completed = store.attempt(request_id)
    assert completed is not None
    assert completed.outcome is PublishStatus.PUBLISHED

    with pytest.raises(ValueError, match="no open intent"):
        store.complete(
            make_receipt(
                request_id=request_id,
                draft_id=draft_id,
                status=PublishStatus.PUBLISHED,
            )
        )


def test_publish_audit_store_attempt_and_latest_success_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duplicate_path = tmp_path / "duplicate.jsonl"
    duplicate_path.write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "event_type": "SOCIAL_PUBLISH_INTENT",
                        "timestamp": NOW.isoformat(),
                        "snapshot_id": "c" * 64,
                        "payload": {"draft_id": "d" * 64},
                    },
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "event_type": "SOCIAL_PUBLISH_INTENT",
                        "timestamp": NOW.isoformat(),
                        "snapshot_id": "c" * 64,
                        "payload": {"draft_id": "d" * 64},
                    },
                    sort_keys=True,
                ),
            )
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate social publishing intent"):
        PublishAuditStore(duplicate_path).attempt("c" * 64)

    transition_path = tmp_path / "transition.jsonl"
    transition_path.write_text(
        json.dumps(
            {
                "event_type": "SOCIAL_PUBLISH_FAILED",
                "timestamp": NOW.isoformat(),
                "snapshot_id": "e" * 64,
                "payload": {"receipt": {}},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid social publishing audit transition"):
        PublishAuditStore(transition_path).attempt("e" * 64)

    success_path = tmp_path / "success.jsonl"
    success_store = PublishAuditStore(success_path)
    success_store.begin(
        request_id="f" * 64,
        draft_id="1" * 64,
        platform=SocialPlatform.X,
        requested_by="operator",
        timestamp=NOW,
    )
    success_store.complete(
        make_receipt(
            request_id="f" * 64,
            draft_id="1" * 64,
            status=PublishStatus.PUBLISHED,
            requested_at=NOW,
            platform=SocialPlatform.X,
        )
    )
    assert success_store.latest_success(SocialPlatform.X) == NOW

    monkeypatch.setattr(
        PublishAuditStore,
        "_events",
        lambda _self: (
            {
                "event_type": "SOCIAL_PUBLISH_SUCCEEDED",
                "timestamp": NOW.isoformat(),
                "snapshot_id": "x",
                "payload": "invalid",
            },
        ),
    )
    with pytest.raises(ValueError, match="payload is invalid"):
        success_store.latest_success(SocialPlatform.X)


def test_publish_audit_store_rejects_invalid_schema_timestamps_and_oversize(
    tmp_path: Path,
) -> None:
    invalid_event = tmp_path / "invalid-event.jsonl"
    invalid_event.write_text(
        json.dumps(
            {
                "event_type": "UNSUPPORTED_EVENT",
                "timestamp": NOW.isoformat(),
                "snapshot_id": "a" * 64,
                "payload": {},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="audit event is invalid"):
        PublishAuditStore(invalid_event).attempt("a" * 64)

    non_string_ts = tmp_path / "non-string-ts.jsonl"
    non_string_ts.write_text(
        json.dumps(
            {
                "event_type": "SOCIAL_PUBLISH_INTENT",
                "timestamp": 123,
                "snapshot_id": "a" * 64,
                "payload": {},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="timestamp is invalid"):
        PublishAuditStore(non_string_ts).attempt("a" * 64)

    invalid_ts = tmp_path / "invalid-ts.jsonl"
    invalid_ts.write_text(
        json.dumps(
            {
                "event_type": "SOCIAL_PUBLISH_INTENT",
                "timestamp": "not-a-timestamp",
                "snapshot_id": "a" * 64,
                "payload": {},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="timestamp is invalid"):
        PublishAuditStore(invalid_ts).attempt("a" * 64)

    naive_ts = tmp_path / "naive-ts.jsonl"
    naive_ts.write_text(
        json.dumps(
            {
                "event_type": "SOCIAL_PUBLISH_INTENT",
                "timestamp": "2026-07-13T12:00:00",
                "snapshot_id": "a" * 64,
                "payload": {},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="timestamp is invalid"):
        PublishAuditStore(naive_ts).attempt("a" * 64)

    oversized = tmp_path / "oversized.jsonl"
    oversized.write_text(
        json.dumps(
            {
                "event_type": "SOCIAL_PUBLISH_INTENT",
                "timestamp": NOW.isoformat(),
                "snapshot_id": "a" * 64,
                "payload": {},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsafe or oversized"):
        PublishAuditStore(oversized, maximum_bytes=1).attempt("a" * 64)
