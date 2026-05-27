"""Example handler that forwards top-level Slack channel messages to Oz."""
import logging

from bots.base import BaseBotHandler
from config import BotConfig

logger = logging.getLogger(__name__)


class ChannelForwarderHandler(BaseBotHandler):
    """
    Opt-in message handler for event-forwarding use cases.

    Enable with ``process_messages: true`` for a bot named ``channel-forwarder``
    or copy this pattern into your own handler module.
    """

    def on_message(self, event: dict, bot_config: BotConfig, client, context: dict, executor, warp_client):
        text = (event.get("text") or "").strip()
        if not text:
            return None

        channel = event["channel"]
        ts = event["ts"]
        thread_ts = event.get("thread_ts", ts)
        user = event.get("user", "unknown")

        logger.info("[%s] Forwarding top-level Slack message from %s", bot_config.name, user)
        prompt = (
            "A Slack channel message was forwarded to you by an event-forwarding bot.\n"
            "Decide whether action is needed based on the configured skill or repository "
            "instructions. If no action is needed, keep the response brief.\n\n"
            f"Slack channel: {channel}\n"
            f"Slack message timestamp: {ts}\n"
            f"Slack user: {user}\n\n"
            f"Message text: {text}"
        )
        executor.submit(self.process_task, bot_config, channel, thread_ts, prompt, client, warp_client)
        return None
