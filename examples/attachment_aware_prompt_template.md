# Attachment-aware prompt template

Use this shape when a Slack mention includes files. Prefer metadata and stable permalinks over private download URLs.

Inputs:
- `SLACK_CHANNEL`: Slack channel ID.
- `SLACK_THREAD_TS`: Slack thread timestamp.
- `USER_REQUEST`: request text with the bot mention removed.
- `ATTACHMENT_METADATA`: title, MIME/file type, size, and permalink for each file.

Prompt:

You are handling a Slack request that may include file attachments. Use the attachment metadata to decide what additional context you need. Do not assume private Slack file URLs are accessible unless your runtime has the appropriate Slack API credentials.

Slack channel: {{SLACK_CHANNEL}}
Slack thread: {{SLACK_THREAD_TS}}

User request: {{USER_REQUEST}}

Attachment metadata:
{{ATTACHMENT_METADATA}}
