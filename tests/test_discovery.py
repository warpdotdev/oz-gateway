import unittest

from bots import get_handler
from bots.attachment_assistant import AttachmentAssistantHandler
from bots.base import BaseBotHandler
from bots.channel_forwarder import ChannelForwarderHandler
from bots.thread_context import ThreadContextHandler
from webhooks import get_webhook_handler
from webhooks.event_forwarder import handle_event_forwarder_event
from webhooks.json_prompt import handle_json_prompt_event


class DiscoveryTests(unittest.TestCase):
    def test_bot_handler_discovery(self):
        self.assertIsInstance(get_handler("thread-context"), ThreadContextHandler)
        self.assertIsInstance(get_handler("attachment-assistant"), AttachmentAssistantHandler)
        self.assertIsInstance(get_handler("channel-forwarder"), ChannelForwarderHandler)
        self.assertIsInstance(get_handler("unknown-bot"), BaseBotHandler)

    def test_webhook_handler_discovery(self):
        self.assertIs(get_webhook_handler("json_prompt"), handle_json_prompt_event)
        self.assertIs(get_webhook_handler("event-forwarder"), handle_event_forwarder_event)
        self.assertIsNone(get_webhook_handler("missing-source"))


if __name__ == "__main__":
    unittest.main()
