"""Tests for HTTP status codes returned by the /webhooks/<name> route.

The route distinguishes client errors (bad payload shape, missing required
fields -- raised as ``ValueError`` by handlers) from unexpected internal
errors.
"""
import importlib
import os
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class WebhookStatusCodeTests(unittest.TestCase):
    def setUp(self):
        self._original_modules = {
            name: sys.modules.get(name)
            for name in [
                "app",
                "dotenv",
                "flask",
                "slack_bolt",
                "slack_bolt.adapter",
                "slack_bolt.adapter.flask",
                "oz_agent_sdk",
            ]
        }
        for name in self._original_modules:
            sys.modules.pop(name, None)

        dotenv_module = types.ModuleType("dotenv")
        dotenv_module.load_dotenv = lambda *args, **kwargs: None
        sys.modules["dotenv"] = dotenv_module

        flask_module = types.ModuleType("flask")

        class FakeFlask:
            def __init__(self, name):
                self.name = name
                self.routes = []

            def route(self, rule, methods=None):
                def decorator(func):
                    self.routes.append((rule, tuple(methods or ()), func))
                    return func

                return decorator

            def run(self, *args, **kwargs):
                return None

        flask_module.Flask = FakeFlask
        flask_module.request = SimpleNamespace(
            get_json=lambda silent=False: {},
            headers={},
        )
        # Tag responses so the route's `return jsonify(...), status` tuple is
        # observable from tests without a real Flask test client.
        flask_module.jsonify = lambda payload: ("JSONIFIED", payload)
        sys.modules["flask"] = flask_module

        slack_bolt_module = types.ModuleType("slack_bolt")

        class FakeSlackApp:
            def __init__(self, token, signing_secret):
                self.token = token
                self.signing_secret = signing_secret

            def event(self, *_args, **_kwargs):
                return lambda func: func

            def action(self, *_args, **_kwargs):
                return lambda func: func

        slack_bolt_module.App = FakeSlackApp
        sys.modules["slack_bolt"] = slack_bolt_module

        adapter_module = types.ModuleType("slack_bolt.adapter")
        adapter_flask_module = types.ModuleType("slack_bolt.adapter.flask")

        class FakeSlackRequestHandler:
            def __init__(self, app):
                self.app = app

            def handle(self, request):
                return {"handled": True}

        adapter_flask_module.SlackRequestHandler = FakeSlackRequestHandler
        sys.modules["slack_bolt.adapter"] = adapter_module
        sys.modules["slack_bolt.adapter.flask"] = adapter_flask_module

        oz_module = types.ModuleType("oz_agent_sdk")
        oz_module.OzAPI = lambda *args, **kwargs: SimpleNamespace()
        sys.modules["oz_agent_sdk"] = oz_module

        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.config_path = Path(temp_dir.name) / "config.yaml"
        self.config_path.write_text(
            textwrap.dedent(
                """
                bots: []
                webhooks:
                  - name: "json-task"
                    source: "json_prompt"
                    oz_api_key: "${OZ_API_KEY}"
                    oz_environment_id: "${OZ_ENVIRONMENT_ID}"
                    required_payload_fields:
                      - "request"
                    static_prompt_fields:
                      SOURCE: "test"
                """
            ),
            encoding="utf-8",
        )

        env = {
            "GATEWAY_CONFIG_PATH": str(self.config_path),
            "OZ_API_KEY": "placeholder-oz-api-key",
            "OZ_ENVIRONMENT_ID": "placeholder-oz-environment-id",
        }
        self._env_patcher = patch.dict(os.environ, env, clear=False)
        self._env_patcher.start()
        self.addCleanup(self._env_patcher.stop)

        self.app_module = importlib.import_module("app")

    def tearDown(self):
        for name, module in self._original_modules.items():
            sys.modules.pop(name, None)
            if module is not None:
                sys.modules[name] = module

    def _invoke_with_handler(self, handler):
        """Invoke the /webhooks/<name> route with a stubbed webhook handler."""
        self.app_module.request = SimpleNamespace(
            get_json=lambda silent=False: {},
            headers={},
        )
        # Skip auth and force the handler to be the one provided.
        with patch.object(self.app_module, "is_webhook_authorized", return_value=True), \
             patch.object(self.app_module, "get_webhook_handler", return_value=handler), \
             patch.object(
                 self.app_module,
                 "get_webhook_warp_client",
                 return_value=SimpleNamespace(),
             ):
            return self.app_module.handle_webhook("json-task")

    def test_value_error_from_handler_returns_400(self):
        def handler(payload, webhook_config, warp_client):
            raise ValueError("Missing required payload field(s): request")

        body, status = self._invoke_with_handler(handler)
        self.assertEqual(status, 400)
        # body is ("JSONIFIED", {"error": "..."}) via the FakeFlask jsonify
        self.assertEqual(body[1]["error"], "Missing required payload field(s): request")

    def test_unexpected_exception_from_handler_returns_500(self):
        def handler(payload, webhook_config, warp_client):
            raise RuntimeError("network down")

        body, status = self._invoke_with_handler(handler)
        self.assertEqual(status, 500)
        self.assertEqual(body[1]["error"], "network down")


if __name__ == "__main__":
    unittest.main()
