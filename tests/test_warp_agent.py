import importlib
import sys
import types
import unittest
from types import SimpleNamespace


class WarpAgentConfigTests(unittest.TestCase):
    def setUp(self):
        self._original_oz_agent_sdk = sys.modules.get("oz_agent_sdk")
        self._original_warp_agent = sys.modules.get("warp_agent")
        sys.modules.pop("warp_agent", None)

        fake_sdk = types.ModuleType("oz_agent_sdk")

        class FakeRuns:
            def retrieve(self, run_id):
                self.last_retrieved_run_id = run_id
                return SimpleNamespace(
                    state="RUNNING",
                    session_link="https://oz.example.com/sessions/run-placeholder",
                    status_message=SimpleNamespace(message="starting"),
                )

        class FakeAgent:
            def __init__(self):
                self.run_calls = []
                self.runs = FakeRuns()

            def run(self, prompt, config):
                self.run_calls.append({"prompt": prompt, "config": config})
                return SimpleNamespace(run_id="run-placeholder")

        class FakeOzAPI:
            instances = []

            def __init__(self, api_key, base_url):
                self.api_key = api_key
                self.base_url = base_url
                self.agent = FakeAgent()
                FakeOzAPI.instances.append(self)

        fake_sdk.OzAPI = FakeOzAPI
        sys.modules["oz_agent_sdk"] = fake_sdk
        self.fake_oz_api = FakeOzAPI

    def tearDown(self):
        sys.modules.pop("warp_agent", None)
        if self._original_warp_agent is not None:
            sys.modules["warp_agent"] = self._original_warp_agent
        if self._original_oz_agent_sdk is not None:
            sys.modules["oz_agent_sdk"] = self._original_oz_agent_sdk
        else:
            sys.modules.pop("oz_agent_sdk", None)

    def test_submit_task_builds_expected_oz_run_config(self):
        warp_agent = importlib.import_module("warp_agent")

        client = warp_agent.WarpAgentClient(
            api_key="placeholder-oz-api-key",
            environment_id="placeholder-oz-environment-id",
            base_url="https://api.example.com/v1",
            mcp_servers={
                "docs": {
                    "command": "npx",
                    "args": ["-y", "@example/docs-mcp"],
                    "env": {"DOCS_TOKEN": "${DOCS_TOKEN}"},
                }
            },
        )

        result = client.submit_task(
            prompt="Please process this generic request",
            skill_spec="owner/repo:skills/generic",
        )

        oz_instance = self.fake_oz_api.instances[-1]
        self.assertEqual(oz_instance.api_key, "placeholder-oz-api-key")
        self.assertEqual(oz_instance.base_url, "https://api.example.com/v1")
        self.assertEqual(
            oz_instance.agent.run_calls,
            [
                {
                    "prompt": "Please process this generic request",
                    "config": {
                        "environment_id": "placeholder-oz-environment-id",
                        "mcp_servers": {
                            "docs": {
                                "command": "npx",
                                "args": ["-y", "@example/docs-mcp"],
                                "env": {"DOCS_TOKEN": "${DOCS_TOKEN}"},
                            }
                        },
                        "skill_spec": "owner/repo:skills/generic",
                    },
                }
            ],
        )
        self.assertEqual(result["run_id"], "run-placeholder")
        self.assertEqual(result["state"], "RUNNING")
        self.assertEqual(result["status_message"], "starting")
        self.assertEqual(result["run_link"], "https://oz.example.com/runs/run-placeholder")


if __name__ == "__main__":
    unittest.main()
