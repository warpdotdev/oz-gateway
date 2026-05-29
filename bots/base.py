"""
Base bot handler with default Slack-to-Oz behavior.

Subclass this and override methods to customize per-bot logic.
"""
import logging
import re

from config import BotConfig

logger = logging.getLogger(__name__)


class BaseBotHandler:
    """
    Default handler for Slack bot mentions.

    Override any method to customize behavior for a specific bot.
    """

    def extract_prompt(self, text: str, bot_user_id: str) -> str:
        """Extract the user's request from the mention text, removing the bot mention."""
        pattern = f"<@{bot_user_id}>"
        return re.sub(pattern, "", text).strip()

    def build_prompt(self, user_request: str, channel: str, thread_ts: str, bot_config: BotConfig, event: dict) -> str:
        """
        Build the full prompt sent to the Oz agent.

        Override this to customize what the agent sees.
        """
        return (
            "You are handling a request that originated from Slack.\n"
            f"Slack channel: {channel}\n"
            f"Slack thread: {thread_ts}\n"
            "Post useful results back to this Slack thread when you have a final answer.\n\n"
            f"User request: {user_request}\n\n"
            "Before starting, inspect the repository or workspace instructions available "
            "to you, then use the tools and skills that are relevant to the request."
        )

    def on_task_submitted(self, channel: str, thread_ts: str, session_link: str | None, client):
        """Called after the task is submitted to Oz. Posts session link by default."""
        if session_link:
            client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=f"🔗 <{session_link}|View Session>")

    def on_session_link_available(self, channel: str, thread_ts: str, session_link: str, client):
        """Called when a session link becomes available for the run. No-op by default."""
        pass

    def on_run_link_available(self, channel: str, thread_ts: str, run_link: str, client):
        """Called when a run link should be shared before a session link is available. No-op by default."""
        pass

    def on_status_update(self, channel: str, thread_ts: str, status: str, client):
        """Called on each status change during polling. No-op by default."""
        pass

    def on_task_complete(
        self,
        channel: str,
        thread_ts: str,
        state: str,
        status_msg: str,
        session_link: str | None,
        task_id: str,
        last_posted_status: str | None,
        client,
    ):
        """Called when the task reaches a terminal state. Only posts on failure/timeout by default."""
        if state == "FAILED":
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"❌ Task failed\n\n{status_msg}\n\nTask ID: `{task_id}`",
            )
        elif state == "TIMEOUT":
            pass

    def on_task_error(self, channel: str, thread_ts: str, error: Exception, client):
        """Called when an exception occurs during task processing."""
        client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"❌ Sorry, I encountered an error processing your request:\n```{str(error)}```",
        )

    def process_task(
        self, bot_config: BotConfig, channel: str, thread_ts: str, prompt: str, client, warp_client,
        previous_run_id: str | None = None,
    ):
        """
        Background task: submit to Oz, poll, and post results.

        If ``previous_run_id`` is provided, continue that run via the followups
        API so the agent keeps the prior conversation and workspace state. If
        the followup can't be sent (e.g. the run isn't in a terminal state yet),
        fall back to starting a fresh run.

        Override for fundamentally different task flows.
        """
        last_posted_status = None
        posted_run_link = False
        posted_session_link = False

        def _on_run_update(task):
            nonlocal last_posted_status, posted_session_link
            if task.session_link and not posted_session_link and not posted_run_link:
                self.on_session_link_available(channel, thread_ts, task.session_link, client)
                posted_session_link = True
            if task.status_message and task.status_message.message:
                status = task.status_message.message
                if status != last_posted_status:
                    self.on_status_update(channel, thread_ts, status, client)
                    last_posted_status = status

        try:
            logger.info(f"[{bot_config.name}] Processing task: {prompt[:100]}...")

            submit_result = None
            if previous_run_id:
                try:
                    logger.info(
                        f"[{bot_config.name}] Continuing thread via followup to run {previous_run_id}"
                    )
                    submit_result = warp_client.submit_followup(previous_run_id, prompt)
                except Exception as e:
                    logger.warning(
                        f"[{bot_config.name}] Followup to run {previous_run_id} failed "
                        f"({e}); starting a new run instead"
                    )
                    submit_result = None

            if submit_result is None:
                submit_result = warp_client.submit_task(prompt)

            run_id = submit_result["run_id"]
            session_link = submit_result.get("session_link")
            run_link = submit_result.get("run_link")

            self.on_task_submitted(channel, thread_ts, session_link, client)
            if session_link and not posted_session_link:
                self.on_session_link_available(channel, thread_ts, session_link, client)
                posted_session_link = True
            elif run_link and not posted_run_link:
                self.on_run_link_available(channel, thread_ts, run_link, client)
                posted_run_link = True

            result = warp_client.poll_task(
                run_id=run_id,
                poll_interval=5.0,
                on_status_update=_on_run_update,
            )
            if result.get("session_link") and not posted_session_link and not posted_run_link:
                self.on_session_link_available(channel, thread_ts, result["session_link"], client)
                posted_session_link = True
            elif result.get("run_link") and not posted_run_link and not posted_session_link:
                self.on_run_link_available(channel, thread_ts, result["run_link"], client)
                posted_run_link = True

            self.on_task_complete(
                channel=channel,
                thread_ts=thread_ts,
                state=result.get("state", "UNKNOWN"),
                status_msg=result.get("status_message", ""),
                session_link=result.get("session_link"),
                task_id=result.get("task_id", "unknown"),
                last_posted_status=last_posted_status,
                client=client,
            )

            # Record the run_id so followups in this thread continue this run.
            from app import set_thread_run_id
            set_thread_run_id(bot_config.name, channel, thread_ts, result.get("run_id", run_id))

            logger.info(f"[{bot_config.name}] Task {result.get('task_id', 'unknown')} completed with state {result.get('state')}")

        except Exception as e:
            logger.error(f"[{bot_config.name}] Error processing task: {e}")
            self.on_task_error(channel, thread_ts, e, client)

    def on_mention(self, event: dict, bot_config: BotConfig, client, context: dict, say, executor, warp_client):
        """
        Handle an @mention of the bot.

        Override for completely custom mention handling.
        """
        channel = event["channel"]
        user = event["user"]
        text = event["text"]
        ts = event["ts"]
        thread_ts = event.get("thread_ts", ts)
        bot_user_id = context.get("bot_user_id", "")

        user_request = self.extract_prompt(text, bot_user_id)

        if not user_request:
            say(
                text="👋 Hi! Please tell me what you'd like me to do. For example:\n"
                     "• `@assistant summarize this thread`\n"
                     "• `@assistant draft a response to the latest question`",
                thread_ts=thread_ts,
            )
            return

        logger.info(f"[{bot_config.name}] Received mention from {user}: {user_request[:100]}...")

        prompt = self.build_prompt(user_request, channel, thread_ts, bot_config, event)

        # Look up the most recent Oz run for this Slack thread to continue it
        from app import get_thread_run_id
        previous_run_id = get_thread_run_id(bot_config.name, channel, thread_ts)

        executor.submit(
            self.process_task,
            bot_config,
            channel,
            thread_ts,
            prompt,
            client,
            warp_client,
            previous_run_id,
        )

    def on_message(self, event: dict, bot_config: BotConfig, client, context: dict, executor, warp_client):
        """
        Handle a top-level Slack ``message`` event in a channel the bot is in.

        Default: no-op. Override and opt in via ``process_messages: true`` in
        ``config.yaml`` for bots that want to process channel messages without
        requiring an @mention.
        """
        return None

    def on_block_actions(self, payload: dict, bot_config: BotConfig, client, context: dict, executor, warp_client):
        """
        Handle a Slack Block Kit interactivity payload (``block_actions``).

        Default: no-op. Override and opt in via ``process_interactions: true``
        in ``config.yaml`` for bots that post interactive Block Kit messages.
        """
        return None
