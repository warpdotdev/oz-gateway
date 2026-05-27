"""Example handler that includes recent Slack thread context in the Oz prompt."""
import logging

from bots.base import BaseBotHandler
from config import BotConfig

logger = logging.getLogger(__name__)


class ThreadContextHandler(BaseBotHandler):
    """Mention handler that fetches recent thread replies before submitting a task."""

    def _fetch_thread_messages(self, client, channel: str, thread_ts: str) -> list[dict]:
        try:
            response = client.conversations_replies(channel=channel, ts=thread_ts, limit=20)
            return response.get("messages", [])
        except Exception as e:
            logger.warning("Unable to fetch Slack thread context: %s", e)
            return []

    def _format_thread_messages(self, messages: list[dict]) -> str:
        if not messages:
            return "No thread context was available."

        formatted = []
        for message in messages:
            sender = message.get("user") or message.get("bot_id") or "unknown"
            text = (message.get("text") or "").strip()
            ts = message.get("ts", "unknown timestamp")
            if text:
                formatted.append(f"- {sender} at {ts}: {text}")
        return "\n".join(formatted) if formatted else "No text messages were available in the thread."

    def on_mention(self, event: dict, bot_config: BotConfig, client, context: dict, say, executor, warp_client):
        channel = event["channel"]
        user = event["user"]
        text = event["text"]
        ts = event["ts"]
        thread_ts = event.get("thread_ts", ts)
        bot_user_id = context.get("bot_user_id", "")

        user_request = self.extract_prompt(text, bot_user_id)
        if not user_request:
            say(
                text="Mention me with a request, and I will include recent thread context in the prompt.",
                thread_ts=thread_ts,
            )
            return

        logger.info("[%s] Received thread-context mention from %s", bot_config.name, user)
        thread_context = self._format_thread_messages(
            self._fetch_thread_messages(client, channel, thread_ts)
        )
        prompt = (
            "You are responding to a Slack thread request. Use the thread context below "
            "to answer accurately, and post the final result back to the same thread.\n\n"
            f"Slack channel: {channel}\n"
            f"Slack thread: {thread_ts}\n\n"
            f"User request: {user_request}\n\n"
            "Recent thread context:\n"
            f"{thread_context}"
        )
        executor.submit(self.process_task, bot_config, channel, thread_ts, prompt, client, warp_client)
