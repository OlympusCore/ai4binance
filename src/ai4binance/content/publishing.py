"""Explicitly approved, default-deny text publishing gateway."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock

from ai4binance.content.policy import ContentCompliancePolicy
from ai4binance.content.publishing_audit import PublishAuditStore
from ai4binance.content.publishing_models import (
    PublishingConfig,
    PublishReceipt,
    PublishRequest,
    PublishStatus,
    SocialPlatform,
)
from ai4binance.content.publishing_transport import (
    HttpPublishRequest,
    HttpPublishResponse,
    PublishingTransport,
    PublishTransportError,
)
from ai4binance.content.queue import LocalApprovalQueue

_LINKEDIN_VERSION_PATTERN = re.compile(r"^\d{6}$")
_LINKEDIN_AUTHOR_PATTERN = re.compile(
    r"^urn:li:(?:person|organization):[A-Za-z0-9_-]+$"
)
_TELEGRAM_TOKEN_PATTERN = re.compile(r"^\d+:[A-Za-z0-9_-]{20,}$")


@dataclass(slots=True)
class SocialPublishingGateway:
    """Publish approved text only after every explicit local gate passes."""

    config: PublishingConfig
    approval_queue: LocalApprovalQueue
    audit_store: PublishAuditStore
    transport: PublishingTransport
    environment: Callable[[str], str | None] = field(default=os.getenv)
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    policy: ContentCompliancePolicy = field(default_factory=ContentCompliancePolicy)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def publish(self, request: PublishRequest) -> PublishReceipt:
        """Perform at most one external POST after durable intent persistence."""
        now = self._now()
        request_id = self._request_id(request)
        with self._lock:
            blockers = self._preflight(request, request_id, now)
            if blockers:
                return self._receipt(
                    request, request_id, now, PublishStatus.BLOCKED, blockers
                )
            credentials = self._credentials(request.platform)
            if credentials is None:
                return self._receipt(
                    request,
                    request_id,
                    now,
                    PublishStatus.BLOCKED,
                    ("PUBLISH_CREDENTIALS_MISSING_OR_INVALID",),
                )
            outbound = self._build_request(request, credentials)
            try:
                self.audit_store.begin(
                    request_id=request_id,
                    draft_id=request.draft.draft_id,
                    platform=request.platform,
                    requested_by=request.requested_by,
                    timestamp=now,
                )
            except (OSError, ValueError):
                return self._receipt(
                    request,
                    request_id,
                    now,
                    PublishStatus.BLOCKED,
                    ("PUBLISH_AUDIT_INTENT_FAILED",),
                )

            try:
                response = self.transport.send(outbound)
                remote_id, response_blocker = self._validate_response(
                    request.platform, response
                )
            except PublishTransportError:
                response = None
                remote_id = None
                response_blocker = "PUBLISH_TRANSPORT_FAILED"

            if remote_id is None:
                receipt = self._receipt(
                    request,
                    request_id,
                    now,
                    PublishStatus.FAILED,
                    (response_blocker,),
                    http_status=(response.status_code if response else None),
                    authority_used=True,
                )
            else:
                if response is None:
                    raise RuntimeError("validated social response is missing")
                receipt = self._receipt(
                    request,
                    request_id,
                    now,
                    PublishStatus.PUBLISHED,
                    (),
                    remote_post_id=remote_id,
                    http_status=response.status_code,
                    authority_used=True,
                )
            try:
                self.audit_store.complete(receipt)
            except (OSError, ValueError):
                return self._receipt(
                    request,
                    request_id,
                    now,
                    PublishStatus.FAILED,
                    ("PUBLISH_AUDIT_OUTCOME_FAILED_REVIEW_REQUIRED",),
                    http_status=receipt.http_status,
                    authority_used=True,
                )
            return receipt

    def _preflight(
        self, request: PublishRequest, request_id: str, now: datetime
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if request.platform not in self.config.enabled_platforms:
            blockers.append("PUBLISH_PLATFORM_DISABLED")
        if request.confirmation != request.required_confirmation:
            blockers.append("PUBLISH_EXPLICIT_CONFIRMATION_MISSING")
        try:
            approved = self.approval_queue.approved_draft_matches(request.draft)
        except (OSError, ValueError, json.JSONDecodeError):
            blockers.append("PUBLISH_APPROVAL_QUEUE_INVALID")
        else:
            if not approved:
                blockers.append("PUBLISH_DRAFT_NOT_EXACTLY_APPROVED")
        age = now - request.draft.source.evidence_timestamp
        if age < -self.config.maximum_draft_age or age > self.config.maximum_draft_age:
            blockers.append("PUBLISH_DRAFT_STALE_OR_FUTURE")
        compliance = self.policy.evaluate(request.draft.content)
        if compliance.blockers:
            blockers.extend(f"PUBLISH_{item}" for item in compliance.blockers)
        try:
            attempt = self.audit_store.attempt(request_id)
            latest = self.audit_store.latest_success(request.platform)
        except (OSError, ValueError, json.JSONDecodeError):
            blockers.append("PUBLISH_AUDIT_INVALID")
        else:
            if attempt is not None:
                if attempt.outcome is PublishStatus.PUBLISHED:
                    blockers.append("PUBLISH_ALREADY_COMPLETED")
                elif attempt.outcome is PublishStatus.FAILED:
                    blockers.append("PUBLISH_PREVIOUS_FAILURE_REVIEW_REQUIRED")
                else:
                    blockers.append("PUBLISH_PREVIOUS_ATTEMPT_UNCERTAIN")
            if (
                latest is not None
                and now - latest < self.config.minimum_publish_interval
            ):
                blockers.append("PUBLISH_RATE_LIMIT_ACTIVE")
        return tuple(dict.fromkeys(blockers))

    def _credentials(self, platform: SocialPlatform) -> Mapping[str, str] | None:
        names = {
            SocialPlatform.X: ("AI4BINANCE_X_USER_ACCESS_TOKEN",),
            SocialPlatform.TELEGRAM: (
                "AI4BINANCE_TELEGRAM_BOT_TOKEN",
                "AI4BINANCE_TELEGRAM_CHAT_ID",
            ),
            SocialPlatform.LINKEDIN: (
                "AI4BINANCE_LINKEDIN_ACCESS_TOKEN",
                "AI4BINANCE_LINKEDIN_AUTHOR_URN",
                "AI4BINANCE_LINKEDIN_VERSION",
            ),
        }[platform]
        values = {name: (self.environment(name) or "").strip() for name in names}
        if any(not value or len(value) > 2_048 for value in values.values()):
            return None
        if (
            platform is SocialPlatform.TELEGRAM
            and not _TELEGRAM_TOKEN_PATTERN.fullmatch(
                values["AI4BINANCE_TELEGRAM_BOT_TOKEN"]
            )
        ):
            return None
        if platform is SocialPlatform.LINKEDIN and (
            not _LINKEDIN_AUTHOR_PATTERN.fullmatch(
                values["AI4BINANCE_LINKEDIN_AUTHOR_URN"]
            )
            or not _LINKEDIN_VERSION_PATTERN.fullmatch(
                values["AI4BINANCE_LINKEDIN_VERSION"]
            )
        ):
            return None
        return values

    def _build_request(
        self, request: PublishRequest, credentials: Mapping[str, str]
    ) -> HttpPublishRequest:
        headers = {"Content-Type": "application/json"}
        if request.platform is SocialPlatform.X:
            url = "https://api.x.com/2/tweets"
            headers["Authorization"] = (
                f"Bearer {credentials['AI4BINANCE_X_USER_ACCESS_TOKEN']}"
            )
            payload: Mapping[str, object] = {"text": request.draft.content}
        elif request.platform is SocialPlatform.TELEGRAM:
            token = credentials["AI4BINANCE_TELEGRAM_BOT_TOKEN"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": credentials["AI4BINANCE_TELEGRAM_CHAT_ID"],
                "text": request.draft.content,
                "link_preview_options": {"is_disabled": True},
            }
        else:
            url = "https://api.linkedin.com/rest/posts"
            headers.update(
                {
                    "Authorization": (
                        f"Bearer {credentials['AI4BINANCE_LINKEDIN_ACCESS_TOKEN']}"
                    ),
                    "LinkedIn-Version": credentials["AI4BINANCE_LINKEDIN_VERSION"],
                    "X-Restli-Protocol-Version": "2.0.0",
                }
            )
            payload = {
                "author": credentials["AI4BINANCE_LINKEDIN_AUTHOR_URN"],
                "commentary": request.draft.content,
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            }
        body = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return HttpPublishRequest(
            url=url,
            headers=headers,
            body=body,
            timeout_seconds=self.config.request_timeout_seconds,
            maximum_response_bytes=self.config.maximum_response_bytes,
        )

    @staticmethod
    def _validate_response(
        platform: SocialPlatform, response: HttpPublishResponse
    ) -> tuple[str | None, str]:
        if platform is SocialPlatform.LINKEDIN:
            remote_id = response.headers.get("x-restli-id")
            if response.status_code == 201 and remote_id and len(remote_id) <= 256:
                return remote_id, ""
            return None, "PUBLISH_PROVIDER_REJECTED_OR_RECEIPT_INVALID"
        try:
            data = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, "PUBLISH_PROVIDER_RECEIPT_INVALID"
        if not isinstance(data, Mapping):
            return None, "PUBLISH_PROVIDER_RECEIPT_INVALID"
        if platform is SocialPlatform.X:
            payload = data.get("data")
            remote_id = payload.get("id") if isinstance(payload, Mapping) else None
            if response.status_code == 201 and isinstance(remote_id, str):
                return remote_id[:256], ""
        else:
            payload = data.get("result")
            remote_id = (
                payload.get("message_id") if isinstance(payload, Mapping) else None
            )
            if (
                response.status_code == 200
                and data.get("ok") is True
                and isinstance(remote_id, (str, int))
            ):
                return str(remote_id)[:256], ""
        return None, "PUBLISH_PROVIDER_REJECTED_OR_RECEIPT_INVALID"

    @staticmethod
    def _request_id(request: PublishRequest) -> str:
        identity = f"{request.platform.value}:{request.draft.draft_id}"
        return hashlib.sha256(identity.encode("ascii")).hexdigest()

    @staticmethod
    def _receipt(
        request: PublishRequest,
        request_id: str,
        now: datetime,
        status: PublishStatus,
        blockers: tuple[str, ...],
        *,
        remote_post_id: str | None = None,
        http_status: int | None = None,
        authority_used: bool = False,
    ) -> PublishReceipt:
        return PublishReceipt(
            request_id=request_id,
            draft_id=request.draft.draft_id,
            platform=request.platform,
            requested_by=request.requested_by.strip(),
            requested_at=now,
            status=status,
            blockers=blockers,
            remote_post_id=remote_post_id,
            http_status=http_status,
            publish_authority_used=authority_used,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("publishing gateway clock must be timezone-aware")
        return value
