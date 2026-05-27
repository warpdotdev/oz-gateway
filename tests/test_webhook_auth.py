import unittest
from types import SimpleNamespace

from webhooks.auth import is_webhook_authorized


class WebhookAuthTests(unittest.TestCase):
    def test_webhooks_without_configured_token_are_allowed(self):
        config = SimpleNamespace(auth_token=None, auth_header_name=None)

        self.assertTrue(is_webhook_authorized(config, {}))

    def test_authorization_header_accepts_exact_or_bearer_token(self):
        config = SimpleNamespace(
            auth_token="placeholder-webhook-token",
            auth_header_name=None,
        )

        self.assertTrue(
            is_webhook_authorized(
                config,
                {"Authorization": "placeholder-webhook-token"},
            )
        )
        self.assertTrue(
            is_webhook_authorized(
                config,
                {"Authorization": "Bearer placeholder-webhook-token"},
            )
        )

    def test_wrong_or_missing_token_is_rejected(self):
        config = SimpleNamespace(
            auth_token="placeholder-webhook-token",
            auth_header_name=None,
        )

        self.assertFalse(is_webhook_authorized(config, {}))
        self.assertFalse(
            is_webhook_authorized(config, {"Authorization": "wrong-token"})
        )

    def test_custom_header_name_is_supported(self):
        config = SimpleNamespace(
            auth_token="placeholder-webhook-token",
            auth_header_name="X-Webhook-Token",
        )

        self.assertTrue(
            is_webhook_authorized(
                config,
                {"X-Webhook-Token": "placeholder-webhook-token"},
            )
        )
        self.assertFalse(
            is_webhook_authorized(
                config,
                {"Authorization": "placeholder-webhook-token"},
            )
        )


if __name__ == "__main__":
    unittest.main()
