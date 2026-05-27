"""
Configuration loading for Oz Gateway.

Loads bot configurations from a YAML file, with support for environment
variable interpolation.

## Interpolation boundary

``${VAR}`` references in the gateway YAML config are resolved at load
time against the gateway process environment (``os.environ``) -- with
one exception. Values under any bot or webhook ``mcp_servers`` block are passed
through verbatim, *without* interpolation.

The reason: each MCP server is spawned inside the Oz cloud environment,
not inside the gateway process. Its credentials (e.g. ``EXAMPLE_API_KEY``) belong in
the Oz environment's secret store, where the Oz runtime can resolve them
for the spawned process. Interpolating those values here would (a) require
those secrets to also exist in the gateway host env, and (b) ship the
resolved plaintext through the Oz API. Leaving them unexpanded keeps the
resolution domain co-located with the process that actually needs the
secret.

Practical consequence: inside ``mcp_servers``, use ``${VAR}`` to reference
an Oz environment secret. To reference a gateway-resolved secret, place the
``${VAR}`` reference somewhere outside ``mcp_servers``.
"""
import os
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)
DEFAULT_OZ_API_BASE_URL = "https://app.warp.dev/api/v1"


def get_default_oz_api_base_url() -> str:
    """Return the default Oz API base URL for configs that omit one."""
    return os.environ.get("OZ_API_BASE_URL", DEFAULT_OZ_API_BASE_URL)


def get_config_path(config_path: str | Path | None = None) -> Path:
    """Resolve the required gateway YAML config path."""
    resolved = config_path or os.environ.get("GATEWAY_CONFIG_PATH")
    if not resolved:
        raise FileNotFoundError(
            "Gateway config path is required. Set GATEWAY_CONFIG_PATH to a YAML "
            "configuration file or pass config_path explicitly."
        )
    return Path(resolved)


def get_config_value(
    data: dict,
    key: str,
    *,
    legacy_key: str | None = None,
    default=None,
    required: bool = False,
):
    """Return a config value, accepting an optional legacy key alias."""
    if key in data:
        return data[key]
    if legacy_key and legacy_key in data:
        return data[legacy_key]
    if required:
        raise KeyError(key)
    return default


@dataclass
class BotConfig:
    """Configuration for a single Slack bot."""
    name: str
    slack_bot_token: str
    slack_signing_secret: str
    warp_api_key: str
    warp_environment_id: str
    warp_base_url: str = field(default_factory=get_default_oz_api_base_url)
    # MCP server config passed verbatim to the Oz API; values inside this
    # block bypass gateway ``${VAR}`` interpolation by design -- see the
    # module docstring for the rationale.
    mcp_servers: dict | None = None
    # Opt-in: route top-level Slack `message` events (not just @-mentions)
    # to the bot's `on_message` handler. Default off because most bots
    # only want to respond when explicitly invoked.
    process_messages: bool = False
    # Opt-in: route Slack `block_actions` (Block Kit button clicks) to
    # the bot's `on_block_actions` handler. Default off because most
    # bots don't post interactive Block Kit messages.
    process_interactions: bool = False

    def __post_init__(self):
        """Validate required fields."""
        if not self.name:
            raise ValueError("Bot name is required")
        if not self.slack_bot_token:
            raise ValueError(f"Bot '{self.name}': slack_bot_token is required")
        if not self.slack_signing_secret:
            raise ValueError(f"Bot '{self.name}': slack_signing_secret is required")
        if not self.warp_api_key:
            raise ValueError(f"Bot '{self.name}': oz_api_key is required")
        if not self.warp_environment_id:
            raise ValueError(f"Bot '{self.name}': oz_environment_id is required")


@dataclass
class WebhookConfig:
    """Configuration for an inbound webhook that triggers Oz agent runs."""
    name: str
    source: str  # e.g. "json_prompt"
    warp_api_key: str
    warp_environment_id: str
    warp_base_url: str = field(default_factory=get_default_oz_api_base_url)
    # MCP server config passed verbatim to the Oz API, same as BotConfig.
    mcp_servers: dict | None = None
    skill_spec: str | None = None
    required_payload_fields: list[str] | None = None
    static_prompt_fields: dict[str, str] | None = None
    payload_prompt_fields: dict[str, str] | None = None
    auth_header_name: str | None = None
    auth_token: str | None = None

    def __post_init__(self):
        if not self.name:
            raise ValueError("Webhook name is required")
        if not self.source:
            raise ValueError(f"Webhook '{self.name}': source is required")
        if not self.warp_api_key:
            raise ValueError(f"Webhook '{self.name}': oz_api_key is required")
        if not self.warp_environment_id:
            raise ValueError(f"Webhook '{self.name}': oz_environment_id is required")


@dataclass
class GatewayConfig:
    """Configuration for the gateway server."""
    bots: dict[str, BotConfig]
    webhooks: dict[str, WebhookConfig]
    port: int = 3000

    @classmethod
    def from_dict(cls, data: dict) -> "GatewayConfig":
        """Create config from a dictionary."""
        bots = {}
        for bot_data in data.get("bots", []):
            bot = BotConfig(
                name=bot_data["name"],
                slack_bot_token=bot_data["slack_bot_token"],
                slack_signing_secret=bot_data["slack_signing_secret"],
                warp_api_key=get_config_value(
                    bot_data,
                    "oz_api_key",
                    legacy_key="warp_api_key",
                    required=True,
                ),
                warp_environment_id=get_config_value(
                    bot_data,
                    "oz_environment_id",
                    legacy_key="warp_environment_id",
                    required=True,
                ),
                warp_base_url=get_config_value(
                    bot_data,
                    "oz_base_url",
                    legacy_key="warp_base_url",
                    default=get_default_oz_api_base_url(),
                ),
                mcp_servers=bot_data.get("mcp_servers"),
                process_messages=bool(bot_data.get("process_messages", False)),
                process_interactions=bool(bot_data.get("process_interactions", False)),
            )
            bots[bot.name] = bot

        webhooks = {}
        for webhook_data in data.get("webhooks", []):
            webhook = WebhookConfig(
                name=webhook_data["name"],
                source=webhook_data["source"],
                warp_api_key=get_config_value(
                    webhook_data,
                    "oz_api_key",
                    legacy_key="warp_api_key",
                    required=True,
                ),
                warp_environment_id=get_config_value(
                    webhook_data,
                    "oz_environment_id",
                    legacy_key="warp_environment_id",
                    required=True,
                ),
                warp_base_url=get_config_value(
                    webhook_data,
                    "oz_base_url",
                    legacy_key="warp_base_url",
                    default=get_default_oz_api_base_url(),
                ),
                mcp_servers=webhook_data.get("mcp_servers"),
                skill_spec=webhook_data.get("skill_spec"),
                required_payload_fields=webhook_data.get("required_payload_fields"),
                static_prompt_fields=webhook_data.get("static_prompt_fields"),
                payload_prompt_fields=webhook_data.get("payload_prompt_fields"),
                auth_header_name=webhook_data.get("auth_header_name"),
                auth_token=webhook_data.get("auth_token"),
            )
            webhooks[webhook.name] = webhook
        
        return cls(
            bots=bots,
            webhooks=webhooks,
            port=data.get("port", 3000),
        )


def interpolate_env_vars(value: str) -> str:
    """
    Interpolate environment variables in a string.
    
    Supports ${VAR_NAME} syntax.
    """
    if not isinstance(value, str):
        return value
    
    pattern = r'\$\{([^}]+)\}'
    
    def replace(match):
        var_name = match.group(1)
        env_value = os.environ.get(var_name)
        if env_value is None:
            raise ValueError(f"Environment variable '{var_name}' is not set")
        return env_value
    
    return re.sub(pattern, replace, value)


def interpolate_dict(data: dict) -> dict:
    """Recursively interpolate environment variables in a dictionary."""
    result = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = interpolate_dict(value)
        elif isinstance(value, list):
            result[key] = [
                interpolate_dict(item) if isinstance(item, dict) 
                else interpolate_env_vars(item) if isinstance(item, str)
                else item
                for item in value
            ]
        elif isinstance(value, str):
            result[key] = interpolate_env_vars(value)
        else:
            result[key] = value
    return result


def load_config(config_path: str | Path | None = None) -> GatewayConfig:
    """
    Load gateway configuration from a YAML file.
    
    Args:
        config_path: Path to the config file. If None, uses GATEWAY_CONFIG_PATH.
    
    Returns:
        GatewayConfig instance
    """
    config_path = get_config_path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    logger.info(f"Loading config from {config_path}")
    
    with open(config_path) as f:
        raw_config = yaml.safe_load(f) or {}
    if not isinstance(raw_config, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {config_path}")
    
    # Interpolate environment variables for top-level config (excluding the bots
    # and webhooks lists, which are processed individually below).
    raw_bots = raw_config.get("bots", [])
    raw_webhooks = raw_config.get("webhooks", [])
    top_level_config = {
        key: value
        for key, value in raw_config.items()
        if key not in {"bots", "webhooks"}
    }
    config_data = interpolate_dict(top_level_config)

    # Process each bot individually so that a misconfigured bot (e.g. a missing
    # environment variable) does not prevent other bots from loading.
    bots = {}
    for raw_bot in raw_bots:
        raw_bot = dict(raw_bot)
        bot_name = raw_bot.get("name", "<unknown>")
        try:
            # ``mcp_servers`` is Oz's resolution domain (see module docstring):
            # pop it out before gateway ``${VAR}`` interpolation and re-attach the
            # raw subtree so the literal placeholders survive to the Oz API.
            raw_mcp_servers = raw_bot.pop("mcp_servers", None)
            bot_data = interpolate_dict(raw_bot)
            bot_data["mcp_servers"] = raw_mcp_servers
            bot = BotConfig(
                name=bot_data["name"],
                slack_bot_token=bot_data["slack_bot_token"],
                slack_signing_secret=bot_data["slack_signing_secret"],
                warp_api_key=get_config_value(
                    bot_data,
                    "oz_api_key",
                    legacy_key="warp_api_key",
                    required=True,
                ),
                warp_environment_id=get_config_value(
                    bot_data,
                    "oz_environment_id",
                    legacy_key="warp_environment_id",
                    required=True,
                ),
                warp_base_url=get_config_value(
                    bot_data,
                    "oz_base_url",
                    legacy_key="warp_base_url",
                    default=get_default_oz_api_base_url(),
                ),
                mcp_servers=bot_data.get("mcp_servers"),
                process_messages=bool(bot_data.get("process_messages", False)),
                process_interactions=bool(bot_data.get("process_interactions", False)),
            )
            bots[bot.name] = bot
        except (ValueError, KeyError) as e:
            logger.error(f"Skipping bot '{bot_name}': {e}")

    # Process each webhook individually (same resilience as bots).
    webhooks = {}
    for raw_wh in raw_webhooks:
        raw_wh = dict(raw_wh)
        wh_name = raw_wh.get("name", "<unknown>")
        try:
            raw_mcp_servers = raw_wh.pop("mcp_servers", None)
            wh_data = interpolate_dict(raw_wh)
            wh_data["mcp_servers"] = raw_mcp_servers
            wh = WebhookConfig(
                name=wh_data["name"],
                source=wh_data["source"],
                warp_api_key=get_config_value(
                    wh_data,
                    "oz_api_key",
                    legacy_key="warp_api_key",
                    required=True,
                ),
                warp_environment_id=get_config_value(
                    wh_data,
                    "oz_environment_id",
                    legacy_key="warp_environment_id",
                    required=True,
                ),
                warp_base_url=get_config_value(
                    wh_data,
                    "oz_base_url",
                    legacy_key="warp_base_url",
                    default=get_default_oz_api_base_url(),
                ),
                mcp_servers=wh_data.get("mcp_servers"),
                skill_spec=wh_data.get("skill_spec"),
                required_payload_fields=wh_data.get("required_payload_fields"),
                static_prompt_fields=wh_data.get("static_prompt_fields"),
                payload_prompt_fields=wh_data.get("payload_prompt_fields"),
                auth_header_name=wh_data.get("auth_header_name"),
                auth_token=wh_data.get("auth_token"),
            )
            webhooks[wh.name] = wh
        except (ValueError, KeyError) as e:
            logger.error(f"Skipping webhook '{wh_name}': {e}")

    config = GatewayConfig(bots=bots, webhooks=webhooks, port=config_data.get("port", 3000))
    logger.info(f"Loaded {len(config.bots)} bot(s) and {len(config.webhooks)} webhook(s)")
    
    return config
