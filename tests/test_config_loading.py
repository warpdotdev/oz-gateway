import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from config import load_config


class ConfigLoadingTests(unittest.TestCase):
    def _write_config(self, body: str) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "config.yaml"
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        return path

    def test_load_config_interpolates_env_and_preserves_mcp_placeholders(self):
        config_path = self._write_config(
            """
            port: 4321
            bots:
              - name: "assistant"
                slack_bot_token: "${SLACK_BOT_TOKEN}"
                slack_signing_secret: "${SLACK_SIGNING_SECRET}"
                oz_api_key: "${OZ_API_KEY}"
                oz_environment_id: "${OZ_ENVIRONMENT_ID}"
                oz_base_url: "${OZ_API_BASE_URL}"
                process_messages: true
                process_interactions: true
                mcp_servers:
                  docs:
                    command: "npx"
                    args:
                      - "-y"
                      - "@example/docs-mcp"
                    env:
                      DOCS_TOKEN: "${DOCS_TOKEN}"
            webhooks:
              - name: "json-task"
                source: "json_prompt"
                oz_api_key: "${WEBHOOK_OZ_API_KEY}"
                oz_environment_id: "${WEBHOOK_OZ_ENVIRONMENT_ID}"
                oz_base_url: "${OZ_API_BASE_URL}"
                auth_header_name: "Authorization"
                auth_token: "${WEBHOOK_AUTH_TOKEN}"
                skill_spec: "${WEBHOOK_SKILL_SPEC}"
                required_payload_fields:
                  - "request"
                static_prompt_fields:
                  SOURCE: "webhook"
                payload_prompt_fields:
                  USER_REQUEST: "request"
            """
        )

        env = {
            "SLACK_BOT_TOKEN": "placeholder-slack-token",
            "SLACK_SIGNING_SECRET": "placeholder-slack-signing-secret",
            "OZ_API_KEY": "placeholder-oz-api-key",
            "OZ_ENVIRONMENT_ID": "placeholder-oz-environment-id",
            "OZ_API_BASE_URL": "https://api.example.com/v1",
            "WEBHOOK_OZ_API_KEY": "placeholder-webhook-oz-api-key",
            "WEBHOOK_OZ_ENVIRONMENT_ID": "placeholder-webhook-oz-environment-id",
            "WEBHOOK_AUTH_TOKEN": "placeholder-webhook-auth-token",
            "WEBHOOK_SKILL_SPEC": "owner/repo:skills/generic",
        }

        with patch.dict(os.environ, env, clear=False):
            config = load_config(config_path)

        self.assertEqual(config.port, 4321)
        self.assertEqual(list(config.bots), ["assistant"])
        bot = config.bots["assistant"]
        self.assertEqual(bot.slack_bot_token, "placeholder-slack-token")
        self.assertEqual(bot.slack_signing_secret, "placeholder-slack-signing-secret")
        self.assertEqual(bot.warp_api_key, "placeholder-oz-api-key")
        self.assertEqual(bot.warp_environment_id, "placeholder-oz-environment-id")
        self.assertEqual(bot.warp_base_url, "https://api.example.com/v1")
        self.assertTrue(bot.process_messages)
        self.assertTrue(bot.process_interactions)
        self.assertEqual(
            bot.mcp_servers["docs"]["env"]["DOCS_TOKEN"],
            "${DOCS_TOKEN}",
        )

        self.assertEqual(list(config.webhooks), ["json-task"])
        webhook = config.webhooks["json-task"]
        self.assertEqual(webhook.source, "json_prompt")
        self.assertEqual(webhook.auth_token, "placeholder-webhook-auth-token")
        self.assertEqual(webhook.skill_spec, "owner/repo:skills/generic")
        self.assertEqual(webhook.required_payload_fields, ["request"])
        self.assertEqual(webhook.static_prompt_fields, {"SOURCE": "webhook"})
        self.assertEqual(webhook.payload_prompt_fields, {"USER_REQUEST": "request"})

    def test_misconfigured_entries_are_skipped_without_blocking_valid_entries(self):
        config_path = self._write_config(
            """
            bots:
              - name: "assistant"
                slack_bot_token: "${SLACK_BOT_TOKEN}"
                slack_signing_secret: "${SLACK_SIGNING_SECRET}"
                oz_api_key: "${OZ_API_KEY}"
                oz_environment_id: "${OZ_ENVIRONMENT_ID}"
              - name: "missing-env"
                slack_bot_token: "${MISSING_SLACK_BOT_TOKEN}"
                slack_signing_secret: "${SLACK_SIGNING_SECRET}"
                warp_api_key: "${OZ_API_KEY}"
                warp_environment_id: "${OZ_ENVIRONMENT_ID}"
            webhooks:
              - name: "json-task"
                source: "json_prompt"
                oz_api_key: "${WEBHOOK_OZ_API_KEY}"
                oz_environment_id: "${WEBHOOK_OZ_ENVIRONMENT_ID}"
              - name: "missing-webhook-env"
                source: "json_prompt"
                oz_api_key: "${MISSING_WEBHOOK_OZ_API_KEY}"
                oz_environment_id: "${WEBHOOK_OZ_ENVIRONMENT_ID}"
            """
        )

        env = {
            "SLACK_BOT_TOKEN": "placeholder-slack-token",
            "SLACK_SIGNING_SECRET": "placeholder-slack-signing-secret",
            "OZ_API_KEY": "placeholder-oz-api-key",
            "OZ_ENVIRONMENT_ID": "placeholder-oz-environment-id",
            "WEBHOOK_OZ_API_KEY": "placeholder-webhook-oz-api-key",
            "WEBHOOK_OZ_ENVIRONMENT_ID": "placeholder-webhook-oz-environment-id",
        }

        with patch.dict(os.environ, env, clear=True):
            config = load_config(config_path)

        self.assertEqual(list(config.bots), ["assistant"])
        self.assertEqual(list(config.webhooks), ["json-task"])

    def test_legacy_warp_config_keys_are_still_accepted(self):
        config_path = self._write_config(
            """
            bots:
              - name: "assistant"
                slack_bot_token: "${SLACK_BOT_TOKEN}"
                slack_signing_secret: "${SLACK_SIGNING_SECRET}"
                warp_api_key: "${OZ_API_KEY}"
                warp_environment_id: "${OZ_ENVIRONMENT_ID}"
                warp_base_url: "${OZ_API_BASE_URL}"
            webhooks:
              - name: "json-task"
                source: "json_prompt"
                warp_api_key: "${WEBHOOK_OZ_API_KEY}"
                warp_environment_id: "${WEBHOOK_OZ_ENVIRONMENT_ID}"
                warp_base_url: "${OZ_API_BASE_URL}"
            """
        )

        env = {
            "SLACK_BOT_TOKEN": "placeholder-slack-token",
            "SLACK_SIGNING_SECRET": "placeholder-slack-signing-secret",
            "OZ_API_KEY": "placeholder-oz-api-key",
            "OZ_ENVIRONMENT_ID": "placeholder-oz-environment-id",
            "OZ_API_BASE_URL": "https://api.example.com/v1",
            "WEBHOOK_OZ_API_KEY": "placeholder-webhook-oz-api-key",
            "WEBHOOK_OZ_ENVIRONMENT_ID": "placeholder-webhook-oz-environment-id",
        }

        with patch.dict(os.environ, env, clear=True):
            config = load_config(config_path)

        self.assertEqual(config.bots["assistant"].warp_api_key, "placeholder-oz-api-key")
        self.assertEqual(
            config.webhooks["json-task"].warp_api_key,
            "placeholder-webhook-oz-api-key",
        )


if __name__ == "__main__":
    unittest.main()
