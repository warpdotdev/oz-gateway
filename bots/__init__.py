"""
Bot handler discovery.

Looks for a handler class in bots/<bot_name>.py.
Falls back to BaseBotHandler if none is found.
"""
import importlib
import importlib.util
import inspect
import logging

from bots.base import BaseBotHandler

logger = logging.getLogger(__name__)


def get_handler(bot_name: str) -> BaseBotHandler:
    """
    Resolve a handler instance for the given bot name.

    Looks for bots/<bot_name>.py with a subclass of BaseBotHandler.
    Falls back to BaseBotHandler if no custom module or class is found.
    """
    # Normalize bot name to a valid Python module name (e.g. "support-assistant" -> "support_assistant").
    module_name = bot_name.replace("-", "_")
    full_module = f"bots.{module_name}"

    # Check if the module file exists before importing, so we do not swallow
    # ModuleNotFoundError from broken imports inside the module.
    if importlib.util.find_spec(full_module) is None:
        logger.debug("No custom handler module for '%s', using default", bot_name)
        return BaseBotHandler()

    module = importlib.import_module(full_module)

    # Find the first BaseBotHandler subclass in the module.
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, BaseBotHandler) and obj is not BaseBotHandler:
            logger.info("Using custom handler %s for bot '%s'", obj.__name__, bot_name)
            return obj()

    logger.debug("No handler subclass found in bots.%s, using default", module_name)
    return BaseBotHandler()
