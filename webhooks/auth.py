"""Shared webhook authentication helpers."""
import hmac


def _extract_bearer_token(header_value: str) -> str:
    prefix = "Bearer "
    if header_value.startswith(prefix):
        return header_value[len(prefix):]
    return header_value


def is_webhook_authorized(webhook_config, headers) -> bool:
    """Validate an optional static token configured for a webhook.

    Webhooks without ``auth_token`` remain unauthenticated for backwards
    compatibility. Token values are compared without logging or returning the
    configured secret.
    """
    expected_token = getattr(webhook_config, "auth_token", None)
    if not expected_token:
        return True

    header_name = getattr(webhook_config, "auth_header_name", None) or "Authorization"
    provided_token = headers.get(header_name, "")
    if not provided_token:
        return False

    provided_token = _extract_bearer_token(provided_token)
    return hmac.compare_digest(provided_token, expected_token)
