---
document_id: AI4B-SOCIAL-PROC-001
title: AI4BINANCE Social Publishing Gateway
document_type: PROCEDURE
version: 1.0.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: social_publishing_gateway
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: social_publishing_gateway_procedure
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/procedures/procedure_social_publishing_gateway.md
---

# X, Telegram, and LinkedIn Publishing Gateway

## ELI10

This document explains the API for sending messages to X, Telegram, or LinkedIn. Only full
approved texts can be tested; by default, no platform is open
and social-media approval is not trading approval.


This layer, only with full content match in the local approval queue, is `APPROVED`
You can send draft texts to X, Telegram, or LinkedIn as text. Default
The configuration does not enable any platform and does not contain real credentials.

## Mandatory Doors

1. Platform `PublishingConfig.enabled_platforms` allowlist should be in place.
2. The approval in the queue must exactly match the entire draft to be sent.
3. The approval text must exactly be `PUBLISH_<PLATFORM>:<draft_id>`.
4. The source proof must remain within the two-hour default freshness window.
5. Content compliance should be re-run.
6. Platform credentials must come only through the environment.
7. First, a durable `SOCIAL_PUBLISH_INTENT`, then a single network call should be written.
8. Success or failure should be recorded as an append-only audit outcome.
9. Open intent should automatically retry on previous failure or previous success
   engeller.
10. Social publishing must never have trading execution or live-order permissions
    grants no authority.

## Platform contracts

### X

- Endpoint: `POST https://api.x.com/2/tweets`
- Credential: `AI4BINANCE_X_USER_ACCESS_TOKEN`
- The token must be an OAuth user-context token that can write on behalf of a user, not app-only bearer
  should be used.

### Telegram

- Endpoint: `POST https://api.telegram.org/bot<TOKEN>/sendMessage`
- Credential: `AI4BINANCE_TELEGRAM_BOT_TOKEN`
- Hedef: `AI4BINANCE_TELEGRAM_CHAT_ID`
- The bot must have the permission to send messages on the target chat/channel.

### LinkedIn

- Endpoint: `POST https://api.linkedin.com/rest/posts`
- Credential: `AI4BINANCE_LINKEDIN_ACCESS_TOKEN`
- Author: `AI4BINANCE_LINKEDIN_AUTHOR_URN`
- Version header: `AI4BINANCE_LINKEDIN_VERSION` (`YYYYMM`)
- For member publication: `w_member_social`; for organization publication: appropriate
Access to `w_organization_social` and page role is required.

## Programmatic Usage

```python
from datetime import timedelta
from pathlib import Path

from ai4binance.content import (
    PublishAuditStore,
    PublishRequest,
    PublishingConfig,
    SocialPlatform,
    SocialPublishingGateway,
    UrllibPublishingTransport,
)

gateway = SocialPublishingGateway(
    config=PublishingConfig(
        enabled_platforms=frozenset({SocialPlatform.X}),
        minimum_publish_interval=timedelta(minutes=5),
    ),
    approval_queue=approval_queue,
    audit_store=PublishAuditStore(Path("runtime/audit/content_publishing.jsonl")),
    transport=UrllibPublishingTransport(),
)
publish_request = PublishRequest(
    draft=approved_draft,
    platform=SocialPlatform.X,
    requested_by="operator",
    confirmation=f"PUBLISH_X:{approved_draft.draft_id}",
)
receipt = gateway.publish(publish_request)
```

Real credential or real account sending test repository validation's a
It is not a part. Provider scope, account role, fee/plan, and platform policy
The suitability must also be verified as external evidence.

## Intentional out-of-scope

- Automatic or scheduled publication
- Medya upload
- Thread, reply, comment, or DM
- Delete/Edit
- Credential acquisition or OAuth login flow
- Automatic retry for failed requests


