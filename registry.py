"""
Gateway registry for managing Slack bot and webhook configurations.

Provides a singleton registry for looking up bot and webhook configs by name.
"""
import logging
from typing import Optional

from config import BotConfig, WebhookConfig, GatewayConfig, load_config

logger = logging.getLogger(__name__)


class BotRegistry:
    """
    Registry for managing gateway configurations.
    
    Provides lookup by bot/webhook name and iteration over configured targets.
    """
    
    _instance: Optional["BotRegistry"] = None
    
    def __init__(self, config: GatewayConfig):
        self._config = config
        self._bots = config.bots
        self._webhooks = config.webhooks
    
    @classmethod
    def initialize(cls, config_path: str | None = None) -> "BotRegistry":
        """
        Initialize the singleton registry.
        
        Args:
            config_path: Path to the config file
            
        Returns:
            The initialized registry instance
        """
        config = load_config(config_path)
        cls._instance = cls(config)
        logger.info(
            f"Registry initialized with {len(cls._instance._bots)} bot(s) "
            f"and {len(cls._instance._webhooks)} webhook(s)"
        )
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "BotRegistry":
        """Get the singleton registry instance."""
        if cls._instance is None:
            raise RuntimeError("BotRegistry not initialized. Call initialize() first.")
        return cls._instance
    
    def get_bot(self, name: str) -> BotConfig | None:
        """
        Get a bot configuration by name.
        
        Args:
            name: The bot name
            
        Returns:
            BotConfig if found, None otherwise
        """
        return self._bots.get(name)
    
    def get_all_bots(self) -> list[BotConfig]:
        """Get all registered bot configurations."""
        return list(self._bots.values())
    
    def get_bot_names(self) -> list[str]:
        """Get all registered bot names."""
        return list(self._bots.keys())
    
    def get_webhook(self, name: str) -> WebhookConfig | None:
        """Get a webhook configuration by name."""
        return self._webhooks.get(name)

    def get_all_webhooks(self) -> list[WebhookConfig]:
        """Get all registered webhook configurations."""
        return list(self._webhooks.values())

    def get_webhook_names(self) -> list[str]:
        """Get all registered webhook names."""
        return list(self._webhooks.keys())

    @property
    def port(self) -> int:
        """Get the configured server port."""
        return self._config.port
    
    def __len__(self) -> int:
        return len(self._bots)
    
    def __contains__(self, name: str) -> bool:
        return name in self._bots
