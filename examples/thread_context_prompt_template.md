# Thread-context mention prompt template

Use this shape when a Slack @mention should include recent replies from the same thread.

Inputs:
- `SLACK_CHANNEL`: Slack channel ID.
- `SLACK_THREAD_TS`: Slack thread timestamp.
- `USER_REQUEST`: request text with the bot mention removed.
- `THREAD_CONTEXT`: recent thread messages, already filtered to text content.

Prompt:

You are responding to a Slack thread request. Use the thread context below to answer accurately, and post the final result back to the same thread.

Slack channel: {{SLACK_CHANNEL}}
Slack thread: {{SLACK_THREAD_TS}}

User request: {{USER_REQUEST}}

Recent thread context:
{{THREAD_CONTEXT}}
