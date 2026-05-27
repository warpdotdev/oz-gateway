# Event-forwarding prompt template

Use this shape when an external system sends a generic JSON event to the gateway.

Inputs:
- `CONFIGURED_PROMPT_FIELDS`: static and payload-derived fields from `config.yaml`.
- `SANITIZED_EVENT_PAYLOAD`: full JSON payload after redacting obvious secret-bearing keys.

Prompt:

A generic JSON event was forwarded to you by an Oz Gateway webhook. Use the configured instructions and payload fields to decide what action is appropriate.

Configured prompt fields:
{{CONFIGURED_PROMPT_FIELDS}}

Sanitized event payload:
{{SANITIZED_EVENT_PAYLOAD}}
