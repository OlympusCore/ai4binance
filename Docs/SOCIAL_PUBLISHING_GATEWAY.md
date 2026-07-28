# X, Telegram ve LinkedIn Publishing Gateway

Bu katman, yalnız yerel approval kuyruğunda tam içerik eşleşmesiyle `APPROVED`
olan taslakları X, Telegram veya LinkedIn'e metin olarak gönderebilir. Varsayılan
configuration hiçbir platformu etkinleştirmez ve gerçek credential içermez.

## Zorunlu kapılar

1. Platform `PublishingConfig.enabled_platforms` allowlist'inde olmalıdır.
2. Kuyruktaki onay, gönderilecek taslağın tamamıyla birebir eşleşmelidir.
3. Onay metni tam olarak `PUBLISH_<PLATFORM>:<draft_id>` olmalıdır.
4. Kaynak kanıt iki saatlik varsayılan freshness penceresinde kalmalıdır.
5. Content compliance yeniden çalıştırılmalıdır.
6. Platform credential'ları yalnız environment üzerinden gelmelidir.
7. Önce durable `SOCIAL_PUBLISH_INTENT`, sonra tek ağ çağrısı yazılmalıdır.
8. Başarı veya başarısızlık append-only audit outcome olarak kaydedilmelidir.
9. Açık intent, önceki başarısızlık veya önceki başarı otomatik tekrar gönderimini
   engeller.
10. Sosyal yayınlama hiçbir koşulda trading execution veya live-order yetkisi
    vermez.

## Platform sözleşmeleri

### X

- Endpoint: `POST https://api.x.com/2/tweets`
- Credential: `AI4BINANCE_X_USER_ACCESS_TOKEN`
- Token, app-only bearer değil kullanıcı adına yazabilen OAuth user-context token
  olmalıdır.

### Telegram

- Endpoint: `POST https://api.telegram.org/bot<TOKEN>/sendMessage`
- Credential: `AI4BINANCE_TELEGRAM_BOT_TOKEN`
- Hedef: `AI4BINANCE_TELEGRAM_CHAT_ID`
- Bot hedef chat/channel üzerinde mesaj gönderme yetkisine sahip olmalıdır.

### LinkedIn

- Endpoint: `POST https://api.linkedin.com/rest/posts`
- Credential: `AI4BINANCE_LINKEDIN_ACCESS_TOKEN`
- Author: `AI4BINANCE_LINKEDIN_AUTHOR_URN`
- Version header: `AI4BINANCE_LINKEDIN_VERSION` (`YYYYMM`)
- Üye yayını için `w_member_social`; organizasyon yayını için uygun
  `w_organization_social` erişimi ve sayfa rolü gerekir.

## Programatik kullanım

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
    audit_store=PublishAuditStore(Path("Artifacts/content/publishing.jsonl")),
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

Gerçek credential veya gerçek hesapla gönderim testi repository doğrulamasının bir
parçası değildir. Provider scope, hesap rolü, ücret/plan ve platform policy
uygunluğu dış kanıt olarak ayrıca doğrulanmalıdır.

## Bilinçli kapsam dışı

- Otomatik veya zamanlanmış yayın
- Medya upload
- Thread, reply, comment veya DM
- Silme/düzenleme
- Credential edinme veya OAuth login akışı
- Başarısız isteği otomatik retry etme
