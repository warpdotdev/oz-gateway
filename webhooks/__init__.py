"""Webhook handler discovery for the public Oz Gateway."""
import importlib
import importlib.util
import logging
from collections.abc import Callable

from webhooks.event_forwarder import handle_event_forwarder_event
from webhooks.json_prompt import handle_json_prompt_event

logger = logging.getLogger(__name__)

_BUILT_IN_HANDLERS: dict[str, Callable] = {
    "json_prompt": handle_json_prompt_event,
    "event_forwarder": handle_event_forwarder_event,
}


def _normalize_source(source: str) -> str:
    return source.replace("-", "_")


def _load_dynamic_handler(source: str):
    """Load ``webhooks/<source>.py`` and return a handler callable if present."""
    module_name = _normalize_source(source)
    full_module = f"webhooks.{module_name}"

    if importlib.util.find_spec(full_module) is None:
        return None

    module = importlib.import_module(full_module)
    for attr_name in (f"handle_{module_name}_event", "handle_event"):
        handler = getattr(module, attr_name, None)
        if callable(handler):
            return handler

    logger.warning("Webhook module %s did not expose a handler function", full_module)
    return None


def get_webhook_handler(source: str):
    """Return the handler function for a webhook source, or None."""
    normalized_source = _normalize_source(source)
    return _BUILT_IN_HANDLERS.get(normalized_source) or _load_dynamic_handler(normalized_source)
