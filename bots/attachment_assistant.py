"""Example handler that includes Slack attachment metadata in the Oz prompt."""

from bots.base import BaseBotHandler
from config import BotConfig


class AttachmentAssistantHandler(BaseBotHandler):
    """Mention handler that summarizes attached Slack files without exposing tokens."""

    def _format_files(self, event: dict) -> str:
        files = event.get("files") or []
        if not files:
            return "No Slack files were attached to the mention."

        formatted = []
        for file_info in files:
            title = file_info.get("title") or file_info.get("name") or "untitled"
            mimetype = file_info.get("mimetype") or file_info.get("filetype") or "unknown type"
            size = file_info.get("size")
            permalink = file_info.get("permalink")
            parts = [f"title={title!r}", f"type={mimetype!r}"]
            if size is not None:
                parts.append(f"size_bytes={size}")
            if permalink:
                parts.append(f"permalink={permalink}")
            formatted.append("- " + ", ".join(parts))
        return "\n".join(formatted)

    def build_prompt(self, user_request: str, channel: str, thread_ts: str, bot_config: BotConfig, event: dict) -> str:
        return (
            "You are handling a Slack request that may include file attachments.\n"
            "Use the attachment metadata to decide what additional context you need. "
            "Do not assume private Slack file URLs are accessible unless your runtime has "
            "the appropriate Slack API credentials.\n\n"
            f"Slack channel: {channel}\n"
            f"Slack thread: {thread_ts}\n\n"
            f"User request: {user_request}\n\n"
            "Attachment metadata:\n"
            f"{self._format_files(event)}"
        )
