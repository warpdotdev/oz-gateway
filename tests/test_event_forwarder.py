import unittest
from types import SimpleNamespace

from webhooks.event_forwarder import handle_event_forwarder_event


class FakeWarpClient:
    def __init__(self):
        self.prompt = None
        self.skill_spec = None

    def submit_task(self, prompt, skill_spec=None):
        self.prompt = prompt
        self.skill_spec = skill_spec
        return {"run_id": "run_456", "run_link": "https://oz.example/runs/run_456"}


class EventForwarderTests(unittest.TestCase):
    def test_forwards_sanitized_payload(self):
        config = SimpleNamespace(
            name="event-forwarder",
            source="event_forwarder",
            skill_spec="owner/repo:skills/event/SKILL.md",
            required_payload_fields=["event_type"],
            static_prompt_fields={"TASK_SOURCE": "generic_event_webhook"},
            payload_prompt_fields={"EVENT_TYPE": "event_type"},
        )
        client = FakeWarpClient()

        result = handle_event_forwarder_event(
            {
                "event_id": "evt_1",
                "event_type": "example.created",
                "authorization": "Bearer secret",
                "nested": {"api_key": "secret-key", "safe": "value"},
            },
            config,
            client,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["event_id"], "evt_1")
        self.assertEqual(client.skill_spec, "owner/repo:skills/event/SKILL.md")
        self.assertIn("EVENT_TYPE: example.created", client.prompt)
        self.assertIn('"authorization": "[redacted]"', client.prompt)
        self.assertIn('"api_key": "[redacted]"', client.prompt)
        self.assertIn('"safe": "value"', client.prompt)
        self.assertNotIn("Bearer secret", client.prompt)
        self.assertNotIn("secret-key", client.prompt)


if __name__ == "__main__":
    unittest.main()
