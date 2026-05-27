"""
Oz Gateway Server.

A configurable gateway that connects Slack apps and inbound webhooks to Oz
agent environments. Each Slack app or webhook is configured with its own
credentials and Oz environment.
"""
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen
from dotenv import load_dotenv

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request, jsonify

from config import BotConfig, WebhookConfig, get_config_path
from registry import BotRegistry
from warp_agent import create_warp_client, WarpAgentClient
from bots import get_handler
from bots.base import BaseBotHandler
from webhooks.auth import is_webhook_authorized
from webhooks import get_webhook_handler

# Load environment variables (for config path, etc.)
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Thread pool for background task processing
executor = ThreadPoolExecutor(max_workers=10)

# Cache for Slack Bolt apps, Oz clients, and handlers (per bot)
_slack_apps: dict[str, App] = {}
_slack_handlers: dict[str, SlackRequestHandler] = {}
_warp_clients: dict[str, WarpAgentClient] = {}
_bot_handlers: dict[str, BaseBotHandler] = {}
_webhook_warp_clients: dict[str, WarpAgentClient] = {}

# Event deduplication: track processed event IDs to prevent duplicate handling
# Slack retries events if we don't respond within 3 seconds
_processed_events: dict[str, float] = {}  # event_id -> timestamp
_EVENT_CACHE_TTL = 300  # 5 minutes

# Bots whose Slack App failed to initialize (e.g. invalid/rotated token).
# Tracked so a single bad bot does not take down the entire gateway and so
# requests to the failed bot return a clear 503. Details are logged server-side.
_failed_bots: dict[str, str] = {}  # bot_name -> error message


def get_bot_handler(bot_config: BotConfig) -> BaseBotHandler:
    """Get or create a handler for a bot."""
    if bot_config.name not in _bot_handlers:
        _bot_handlers[bot_config.name] = get_handler(bot_config.name)
    return _bot_handlers[bot_config.name]


def get_slack_app(bot_config: BotConfig) -> App:
    """Get or create a Slack Bolt app for a bot."""
    if bot_config.name not in _slack_apps:
        app = App(
            token=bot_config.slack_bot_token,
            signing_secret=bot_config.slack_signing_secret,
        )
        # Register event handlers
        handler = get_bot_handler(bot_config)
        register_event_handlers(app, bot_config, handler)
        _slack_apps[bot_config.name] = app
        _slack_handlers[bot_config.name] = SlackRequestHandler(app)
        logger.info(f"Created Slack app for bot '{bot_config.name}'")
    return _slack_apps[bot_config.name]


def get_slack_handler(bot_config: BotConfig) -> SlackRequestHandler:
    """Get or create a Slack request handler for a bot."""
    # Ensure the app is created first
    get_slack_app(bot_config)
    return _slack_handlers[bot_config.name]


def get_webhook_warp_client(webhook_config: WebhookConfig) -> WarpAgentClient:
    """Get or create an Oz client for a webhook."""
    if webhook_config.name not in _webhook_warp_clients:
        client = create_warp_client(
            api_key=webhook_config.warp_api_key,
            environment_id=webhook_config.warp_environment_id,
            base_url=webhook_config.warp_base_url,
            mcp_servers=webhook_config.mcp_servers,
        )
        _webhook_warp_clients[webhook_config.name] = client
        logger.info(f"Created Oz client for webhook '{webhook_config.name}'")
    return _webhook_warp_clients[webhook_config.name]


def get_warp_client(bot_config: BotConfig) -> WarpAgentClient:
    """Get or create an Oz client for a bot."""
    if bot_config.name not in _warp_clients:
        client = create_warp_client(
            api_key=bot_config.warp_api_key,
            environment_id=bot_config.warp_environment_id,
            base_url=bot_config.warp_base_url,
            mcp_servers=bot_config.mcp_servers,
        )
        _warp_clients[bot_config.name] = client
        logger.info(f"Created Oz client for bot '{bot_config.name}'")
    return _warp_clients[bot_config.name]


def is_duplicate_event(event_id: str | None) -> bool:
    """
    Check if an event has already been processed.
    
    Slack retries events if we don't respond within 3 seconds.
    This prevents duplicate handling of the same event.
    """
    if not event_id:
        return False
    import time
    now = time.time()
    
    # Clean up old entries
    expired = [eid for eid, ts in _processed_events.items() if now - ts > _EVENT_CACHE_TTL]
    for eid in expired:
        del _processed_events[eid]
    
    if event_id in _processed_events:
        logger.info(f"Skipping duplicate event: {event_id}")
        return True
    
    _processed_events[event_id] = now
    return False


def register_event_handlers(app: App, bot_config: BotConfig, handler: BaseBotHandler):
    """Register Slack event handlers for a bot."""

    @app.event("app_mention")
    def handle_app_mention(event, say, client, context):
        """Handle @mentions of the bot."""
        # Deduplicate events - Slack retries if we don't respond within 3 seconds
        event_id = event.get("client_msg_id") or event.get("ts")
        if is_duplicate_event(event_id):
            return

        warp_client = get_warp_client(bot_config)
        handler.on_mention(
            event=event,
            bot_config=bot_config,
            client=client,
            context=context,
            say=say,
            executor=executor,
            warp_client=warp_client,
        )

    @app.event("message")
    def handle_message_events(event, client, context, body, logger):
        """Route top-level message events.

        Bots that don't opt in via ``process_messages: true`` simply ignore
        these events (matches the legacy no-op behavior). Opted-in bots
        receive every message visible to the bot user via ``on_message``.

        We always skip our own bot's messages, message edits/deletes, and
        thread replies (thread replies are handled per-bot in their own
        flow if needed).
        """
        if not getattr(bot_config, "process_messages", False):
            return

        # Skip subtypes that aren't real new top-level messages.
        subtype = event.get("subtype")
        if subtype in {"message_changed", "message_deleted", "bot_message"}:
            return

        # Skip our own bot's messages to prevent self-loops.
        bot_user_id = context.get("bot_user_id", "")
        if bot_user_id and event.get("user") == bot_user_id:
            return
        if event.get("bot_id") and bot_user_id and event.get("user") == bot_user_id:
            return

        # Skip thread replies; only act on top-level messages.
        thread_ts = event.get("thread_ts")
        if thread_ts and thread_ts != event.get("ts"):
            return

        # Deduplicate using ts (client_msg_id is missing for some bot-posted messages).
        event_id = event.get("client_msg_id") or event.get("ts")
        if event_id and is_duplicate_event(f"msg:{event_id}"):
            return

        warp_client = get_warp_client(bot_config)
        try:
            handler.on_message(
                event=event,
                bot_config=bot_config,
                client=client,
                context=context,
                executor=executor,
                warp_client=warp_client,
            )
        except Exception as e:
            logger.error(f"[{bot_config.name}] on_message handler raised: {e}")

    if getattr(bot_config, "process_interactions", False):
        @app.action(re.compile(r".*"))
        def handle_block_actions(ack, body, client, context, logger):
            """Route Slack Block Kit ``block_actions`` payloads.

            Bolt requires `ack()` within 3 seconds; we ack immediately and
            do all real work in the bot's ``on_block_actions`` (typically
            via the executor).
            """
            ack()
            if body.get("type") != "block_actions":
                return

            # Deduplicate by trigger_id (unique per interaction).
            trigger_id = body.get("trigger_id")
            if trigger_id and is_duplicate_event(f"action:{trigger_id}"):
                return

            warp_client = get_warp_client(bot_config)
            try:
                handler.on_block_actions(
                    payload=body,
                    bot_config=bot_config,
                    client=client,
                    context=context,
                    executor=executor,
                    warp_client=warp_client,
                )
            except Exception as e:
                logger.error(f"[{bot_config.name}] on_block_actions handler raised: {e}")


# Flask app for deployment
flask_app = Flask(__name__)

# Initialize registry on module load for WSGI servers such as gunicorn.
# The public repository does not ship an operational config file; callers must
# provide one via GATEWAY_CONFIG_PATH or pass a path to BotRegistry.initialize.
_config_path = get_config_path()
try:
    _registry = BotRegistry.initialize(_config_path)
    # Pre-create Slack apps for all bots. Per-bot failures (e.g. invalid
    # Slack token) are isolated so one bad bot cannot crash the gateway and
    # take every other bot offline. This mirrors the resilience already in
    # config.load_config for per-bot config errors.
    for _bot_config in _registry.get_all_bots():
        try:
            get_slack_app(_bot_config)
        except Exception as _bot_err:
            logger.error(
                f"Failed to initialize Slack app for bot '{_bot_config.name}': {_bot_err}"
            )
            _failed_bots[_bot_config.name] = str(_bot_err)
    _ready_bots = [n for n in _registry.get_bot_names() if n not in _failed_bots]
    logger.info(
        f"Gateway initialized. Ready bots: {_ready_bots}. "
        f"Failed bots: {list(_failed_bots.keys())}"
    )
except Exception as _e:
    logger.error(f"Failed to initialize gateway: {_e}")
    raise


@flask_app.route("/bots/<bot_name>/slack/events", methods=["POST"])
def bot_slack_events(bot_name: str):
    """Handle Slack events for a specific bot."""
    # Handle Slack URL verification challenge first so Slack can still
    # (re)verify endpoints for bots whose App failed to initialize.
    payload = request.get_json(silent=True) or {}
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    if bot_name in _failed_bots:
        logger.warning(
            f"Request for bot '{bot_name}' rejected: init failed ({_failed_bots[bot_name]})"
        )
        return jsonify({
            "error": f"Bot '{bot_name}' failed to initialize",
        }), 503

    registry = BotRegistry.get_instance()
    bot_config = registry.get_bot(bot_name)

    if not bot_config:
        logger.warning(f"Unknown bot requested: {bot_name}")
        return jsonify({"error": f"Bot '{bot_name}' not found"}), 404

    handler = get_slack_handler(bot_config)
    return handler.handle(request)


@flask_app.route("/webhooks/<webhook_name>", methods=["POST"])
def handle_webhook(webhook_name: str):
    """Handle inbound webhook events."""
    registry = BotRegistry.get_instance()
    webhook_config = registry.get_webhook(webhook_name)

    if not webhook_config:
        logger.warning(f"Unknown webhook requested: {webhook_name}")
        return jsonify({"error": f"Webhook '{webhook_name}' not found"}), 404
    if not is_webhook_authorized(webhook_config, request.headers):
        logger.warning(f"Webhook '{webhook_name}' authorization failed")
        return jsonify({"error": "Unauthorized"}), 401

    handler = get_webhook_handler(webhook_config.source)
    if not handler:
        logger.error(f"No handler for webhook source '{webhook_config.source}'")
        return jsonify({"error": f"Unsupported webhook source '{webhook_config.source}'"}), 400

    payload = request.get_json(silent=True) or {}
    warp_client = get_webhook_warp_client(webhook_config)

    try:
        result = handler(payload, webhook_config, warp_client)
        logger.info(f"Webhook '{webhook_name}' processed: run_id={result.get('run_id')}")
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Webhook '{webhook_name}' error: {e}")
        return jsonify({"error": str(e)}), 500


@flask_app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    registry = BotRegistry.get_instance()
    ready_bots = [n for n in registry.get_bot_names() if n not in _failed_bots]
    webhook_names = registry.get_webhook_names()
    return {
        "status": "degraded" if _failed_bots else "ok",
        "config_path": str(_config_path),
        "bots": ready_bots,
        "bot_count": len(ready_bots),
        "failed_bots": list(_failed_bots.keys()),
        "failed_bot_count": len(_failed_bots),
        "webhooks": webhook_names,
        "webhook_count": len(webhook_names),
    }

def _diagnostics_enabled() -> bool:
    """Return whether the optional Oz diagnostics endpoint is enabled."""
    value = os.environ.get("GATEWAY_ENABLE_DIAGNOSTICS", "")
    return value.lower() in {"1", "true", "yes", "on"}


def _diagnostics_timeout() -> float:
    """Return the configured diagnostics timeout in seconds."""
    try:
        return float(os.environ.get("GATEWAY_DIAGNOSTICS_TIMEOUT_SECONDS", "5"))
    except ValueError:
        return 5.0


def _probe_oz_runs_endpoint(kind: str, name: str, base_url: str, api_key: str) -> dict:
    """Probe a configured Oz API target without returning secrets."""
    runs_url = f"{base_url.rstrip('/')}/agent/runs"
    request = UrlRequest(
        runs_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )

    result = {
        "kind": kind,
        "name": name,
        "base_url": base_url,
    }
    try:
        with urlopen(request, timeout=_diagnostics_timeout()) as response:
            result["status"] = response.status
            result["ok"] = 200 <= response.status < 500
    except HTTPError as e:
        result["status"] = e.code
        result["ok"] = e.code < 500
    except (URLError, TimeoutError, OSError) as e:
        logger.warning("Oz diagnostics probe failed for %s '%s': %s", kind, name, e)
        result["ok"] = False
        result["error_type"] = type(e).__name__
    return result


@flask_app.route("/diagnostics/oz", methods=["GET"])
def oz_diagnostics():
    """Optionally test outbound connectivity to configured Oz API targets."""
    if not _diagnostics_enabled():
        return jsonify({"error": "Diagnostics endpoint is disabled"}), 404

    registry = BotRegistry.get_instance()
    targets = [
        _probe_oz_runs_endpoint("bot", bot.name, bot.warp_base_url, bot.warp_api_key)
        for bot in registry.get_all_bots()
    ]
    targets.extend(
        _probe_oz_runs_endpoint(
            "webhook",
            webhook.name,
            webhook.warp_base_url,
            webhook.warp_api_key,
        )
        for webhook in registry.get_all_webhooks()
    )

    return {
        "ok": all(target.get("ok") for target in targets),
        "target_count": len(targets),
        "targets": targets,
    }


@flask_app.route("/", methods=["GET"])
def index():
    """Index page with bot listing."""
    registry = BotRegistry.get_instance()
    webhook_names = registry.get_webhook_names()
    return {
        "service": "Oz Gateway",
        "config_path": str(_config_path),
        "bots": [
            {
                "name": name,
                "events_url": f"/bots/{name}/slack/events",
            }
            for name in registry.get_bot_names()
        ],
        "bot_count": len(registry.get_bot_names()),
        "webhooks": [
            {
                "name": name,
                "url": f"/webhooks/{name}",
            }
            for name in webhook_names
        ],
        "webhook_count": len(webhook_names),
    }


if __name__ == "__main__":
    # Registry is already initialized at module load
    registry = BotRegistry.get_instance()
    port = registry.port
    
    logger.info(f"Starting Oz Gateway on port {port}")
    logger.info(f"Registered bots: {registry.get_bot_names()}")
    
    default_host = ".".join(["0", "0", "0", "0"])
    flask_app.run(host=os.environ.get("HOST", default_host), port=port, debug=False)
