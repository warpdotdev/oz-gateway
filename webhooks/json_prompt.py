"""
Generic JSON-to-Oz prompt webhook handler.

This handler is intentionally small: it validates required JSON payload fields,
combines payload-derived values with static config-controlled prompt fields,
and dispatches an Oz cloud agent run using the configured skill.
"""
import logging

from webhooks.errors import WebhookValidationError

logger = logging.getLogger(__name__)


def _validate_required_fields(payload: dict, required_fields: list[str]) -> None:
    missing_fields = [
        field
        for field in required_fields
        if payload.get(field) is None or payload.get(field) == ""
    ]
    if missing_fields:
        raise WebhookValidationError(
            f"Missing required payload field(s): {', '.join(missing_fields)}"
        )


def _build_prompt(payload: dict, webhook_config) -> str:
    required_fields = webhook_config.required_payload_fields or []
    _validate_required_fields(payload, required_fields)

    prompt_fields = dict(webhook_config.static_prompt_fields or {})
    for prompt_key, payload_key in (webhook_config.payload_prompt_fields or {}).items():
        value = payload.get(payload_key)
        if value is not None:
            prompt_fields[prompt_key] = str(value)

    if not prompt_fields:
        raise WebhookValidationError("No prompt fields configured for json_prompt webhook")

    return "\n".join(f"{key}: {value}" for key, value in prompt_fields.items())


def handle_json_prompt_event(payload: dict, webhook_config, warp_client):
    """
    Handle a generic JSON webhook by spawning an Oz cloud agent run.

    Returns a small dict for logging/HTTP response purposes.
    """
    if not isinstance(payload, dict):
        raise WebhookValidationError("Webhook payload must be a JSON object")

    prompt = _build_prompt(payload, webhook_config)

    logger.info(
        "Dispatching JSON prompt webhook run: webhook=%s source=%s",
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
    run_link = submit_result.get("run_link")
    if run_link:
        response["run_link"] = run_link

    return response
