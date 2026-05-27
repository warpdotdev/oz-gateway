"""Generic JSON event-forwarding webhook handler."""
import json
import logging
from typing import Any

from webhooks.json_prompt import _validate_required_fields

logger = logging.getLogger(__name__)

_SENSITIVE_KEY_PARTS = ("token", "secret", "password", "api_key", "apikey", "authorization")


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, child in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in _SENSITIVE_KEY_PARTS):
                sanitized[key] = "[redacted]"
            else:
                sanitized[key] = _sanitize_payload(child)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    return value


def _configured_prompt_fields(payload: dict, webhook_config) -> dict[str, str]:
    prompt_fields = dict(webhook_config.static_prompt_fields or {})
    for prompt_key, payload_key in (webhook_config.payload_prompt_fields or {}).items():
        value = payload.get(payload_key)
        if value is not None:
            prompt_fields[prompt_key] = str(value)
    return prompt_fields


def _build_prompt(payload: dict, webhook_config) -> str:
    required_fields = webhook_config.required_payload_fields or []
    _validate_required_fields(payload, required_fields)

    prompt_fields = _configured_prompt_fields(payload, webhook_config)
    sanitized_payload = json.dumps(_sanitize_payload(payload), indent=2, sort_keys=True)

    lines = [
        "A generic JSON event was forwarded to you by an Oz Gateway webhook.",
        "Use the configured instructions and payload fields to decide what action is appropriate.",
    ]
    if prompt_fields:
        lines.append("")
        lines.append("Configured prompt fields:")
        lines.extend(f"{key}: {value}" for key, value in prompt_fields.items())

    lines.extend([
        "",
        "Sanitized event payload:",
        sanitized_payload,
    ])
    return "\n".join(lines)


def handle_event_forwarder_event(payload: dict, webhook_config, warp_client):
    """Forward a generic JSON event to an Oz agent run."""
    if not isinstance(payload, dict):
        raise ValueError("Webhook payload must be a JSON object")

    prompt = _build_prompt(payload, webhook_config)
    logger.info(
        "Dispatching event-forwarder webhook run: webhook=%s source=%s",
        webhook_config.name,
        webhook_config.source,
    )
    submit_result = warp_client.submit_task(
        prompt=prompt,
        skill_spec=webhook_config.skill_spec,
    )

    response = {
        "ok": True,
        "run_id": submit_result.get("run_id"),
        "session_link": submit_result.get("session_link"),
    }
    if submit_result.get("run_link"):
        response["run_link"] = submit_result["run_link"]
    if payload.get("event_id"):
        response["event_id"] = payload["event_id"]
    return response
