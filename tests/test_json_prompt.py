import unittest
from types import SimpleNamespace

from webhooks.json_prompt import handle_json_prompt_event


class FakeWarpClient:
    def __init__(self):
        self.submitted = []

    def submit_task(self, prompt, skill_spec=None):
        self.submitted.append({"prompt": prompt, "skill_spec": skill_spec})
        return {
            "run_id": "run-placeholder",
            "session_link": "https://oz.example.com/sessions/run-placeholder",
            "run_link": "https://oz.example.com/runs/run-placeholder",
        }


class JsonPromptTests(unittest.TestCase):
    def _config(self, **overrides):
        defaults = {
            "name": "json-task",
            "source": "json_prompt",
            "skill_spec": "owner/repo:skills/generic",
            "required_payload_fields": ["request"],
            "static_prompt_fields": {"SOURCE": "webhook"},
            "payload_prompt_fields": {
                "USER_REQUEST": "request",
                "TICKET_ID": "ticket_id",
            },
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_maps_json_payload_to_prompt_and_dispatches_oz_run(self):
        warp_client = FakeWarpClient()
        config = self._config()

        response = handle_json_prompt_event(
            {"request": "Summarize this payload", "ticket_id": 123},
            config,
            warp_client,
        )

        self.assertEqual(
            warp_client.submitted,
            [
                {
                    "prompt": (
                        "SOURCE: webhook\n"
                        "USER_REQUEST: Summarize this payload\n"
                        "TICKET_ID: 123"
                    ),
                    "skill_spec": "owner/repo:skills/generic",
                }
            ],
        )
        self.assertEqual(
            response,
            {
                "ok": True,
                "run_id": "run-placeholder",
                "session_link": "https://oz.example.com/sessions/run-placeholder",
                "run_link": "https://oz.example.com/runs/run-placeholder",
            },
        )

    def test_required_payload_fields_are_enforced(self):
        with self.assertRaisesRegex(ValueError, "Missing required payload field"):
            handle_json_prompt_event({}, self._config(), FakeWarpClient())

    def test_payload_must_be_json_object(self):
        with self.assertRaisesRegex(ValueError, "must be a JSON object"):
            handle_json_prompt_event([], self._config(), FakeWarpClient())

    def test_prompt_fields_must_be_configured(self):
        config = self._config(
            required_payload_fields=[],
            static_prompt_fields=None,
            payload_prompt_fields=None,
        )

        with self.assertRaisesRegex(ValueError, "No prompt fields configured"):
            handle_json_prompt_event({}, config, FakeWarpClient())


if __name__ == "__main__":
    unittest.main()
