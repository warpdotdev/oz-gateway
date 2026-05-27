# Oz Gateway

Oz Gateway is a small Flask service that connects Slack apps and generic JSON webhooks to Oz cloud-agent environments.

Use it when you want a Slack mention or an authenticated webhook request to start an Oz run in a configured environment, optionally with MCP servers attached to the run.

## What it does

- Accepts Slack Events API requests at `/bots/<bot-name>/slack/events`.
- Starts an Oz cloud-agent run with the configured API key, environment ID, and optional MCP server config.
- Posts Oz session links and failure messages back to the Slack thread through Slack Bolt's Web API client.
- Accepts generic JSON webhooks at `/webhooks/<webhook-name>` and maps selected payload fields into an Oz prompt.
- Loads credentials and runtime settings from environment variables referenced by `config.yaml`.

This repository intentionally does not include an operational `config.yaml`, real keys, real environment IDs, deployment project IDs, or private workflow-specific bot handlers.

## Repository files

- `app.py` — Flask routes and Slack Bolt integration.
- `config.py` — YAML config loading and environment-variable interpolation.
- `bots/base.py` — default Slack mention behavior.
- `webhooks/json_prompt.py` — generic JSON-to-prompt webhook handler.
- `config.example.yaml` — sanitized sample gateway configuration.
- `.env.example` — sanitized local environment variable template.
- `deploy/` — optional Cloud Run deployment examples with placeholders.

## Prerequisites

- Python 3.12 or compatible Python 3.x runtime.
- A Slack workspace where you can create and install Slack apps.
- An Oz API key.
- An Oz cloud-agent environment ID for each bot or webhook target.
- Optional: Docker for containerized local runs.
- Optional: Google Cloud CLI for Cloud Run deployment.

## Slack app setup

Create one Slack app per configured bot.

1. Go to <https://api.slack.com/apps> and select **Create New App**.
2. Choose **From scratch**, give it a public-safe app name, and choose your Slack workspace.
3. In **OAuth & Permissions**, add the minimum bot scopes:
   - `app_mentions:read` — receive mentions of the bot.
   - `chat:write` — post status and run links back to Slack.
4. Add optional scopes only if your custom bot handler needs them:
   - `channels:history` for public-channel message history.
   - `groups:history`, `im:history`, or `mpim:history` for private channels, DMs, or group DMs.
   - `channels:read` if your handler needs channel metadata.
5. In **Event Subscriptions**, enable events and set the Request URL after your gateway is reachable:
   - Local tunnel: `https://<your-tunnel-domain>/bots/<bot-name>/slack/events`
   - Deployed service: `https://<your-service-domain>/bots/<bot-name>/slack/events`
6. Subscribe to bot events:
   - `app_mention` for the default mention-driven flow.
   - `message.channels` only if a handler has `process_messages: true` and you need top-level messages.
7. If a custom handler uses Block Kit buttons or menus, enable **Interactivity & Shortcuts** and use the same request URL: `https://<your-service-domain>/bots/<bot-name>/slack/events`.
8. Install the app to the workspace and copy these values into your secret store or local `.env`:
   - Bot User OAuth Token, usually starting with `xoxb-`.
   - Signing Secret from **Basic Information**.

Slack requires the Request URL to verify successfully. For local development, start this service first and expose it with a tunnel such as ngrok or Cloudflare Tunnel before saving the URL in Slack.

## Oz API and environment setup

1. Create an Oz API key in Warp settings under **Cloud platform** → **Oz Cloud API Keys**.
2. Create or select an Oz cloud-agent environment for the work this bot or webhook should run.
3. Store the API key in the gateway host environment, not in `config.yaml`.
4. Put the environment ID in the gateway host environment, not in `config.yaml`.
5. Set `OZ_API_BASE_URL` to the public Oz API base URL for your account. The sample uses `https://app.warp.dev/api/v1`; check the current Warp API docs if your organization uses a different endpoint.

Each configured bot or webhook can use a different API key and environment ID.

## Configuration model

The gateway requires `GATEWAY_CONFIG_PATH` at startup. The sample `.env.example` sets it to `./config.yaml` for local development.

For local development:

```sh
cp .env.example .env
cp config.example.yaml config.yaml
```

Then edit `.env` and `config.yaml` with your own placeholder-safe names and credentials. Do not commit either `.env` or `config.yaml`.

### Environment-variable interpolation

Most string values in `config.yaml` can use `${VAR_NAME}` syntax. At startup, the gateway replaces those references with values from the gateway process environment.

Example:

```yaml
oz_api_key: "${ASSISTANT_OZ_API_KEY}"
```

If `ASSISTANT_OZ_API_KEY` is missing, that bot or webhook is skipped and an error is logged. Missing top-level values can prevent the service from starting. Legacy `warp_api_key`, `warp_environment_id`, and `warp_base_url` keys are still accepted, but new configs should use `oz_api_key`, `oz_environment_id`, and `oz_base_url`.

### MCP server secret boundary

Values inside any bot or webhook `mcp_servers` block are intentionally not interpolated by the gateway. The gateway passes that block through to Oz as-is.

Use this split:

- Gateway host/container environment: Slack bot tokens, Slack signing secrets, Oz API keys, Oz environment IDs, webhook auth tokens, `GATEWAY_CONFIG_PATH`, and `PORT`.
- Oz environment secrets: credentials consumed by MCP servers during an Oz run, such as third-party API keys referenced inside `mcp_servers`.

For example, this placeholder remains literal in the gateway and is resolved only inside the Oz cloud-agent runtime if you created an Oz-managed secret named `EXAMPLE_MCP_TOKEN`:

```yaml
mcp_servers:
  example_tool:
    command: "example-mcp-server"
    env:
      EXAMPLE_MCP_TOKEN: "${EXAMPLE_MCP_TOKEN}"
```

Create Oz-managed secrets with the Oz CLI, choosing the correct scope for your use case:

```sh
oz secret create --team EXAMPLE_MCP_TOKEN
```

Do not copy MCP secrets into `.env` unless the gateway process itself also needs them.

## Local development

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp config.example.yaml config.yaml
```

Edit `.env` and `config.yaml`, then run:

```sh
python app.py
```

The service listens on the configured `port` from `config.yaml` when run directly. The sample uses `3000`.

Health check:

```sh
curl http://localhost:3000/health
```

Expose local Slack endpoints with a tunnel:

```sh
ngrok http 3000
```

Then set your Slack Event Subscriptions request URL to:

```text
https://<your-tunnel-domain>/bots/<bot-name>/slack/events
```

## Docker local run

Build the image:

```sh
docker build -t oz-gateway:local .
```

Run it with your local `.env` and a read-only mounted `config.yaml`:

```sh
docker run --rm \
  --env-file .env \
  -e GATEWAY_CONFIG_PATH=/app/config.yaml \
  -p 3000:3000 \
  -v "$PWD/config.yaml:/app/config.yaml:ro" \
  oz-gateway:local
```

The image does not copy an operational `config.yaml`; provide one at runtime with a bind mount, container secret, or platform-specific secret volume.

## Generic JSON webhooks

Configure generic webhooks under `webhooks` in `config.yaml` with `source: json_prompt`.

A webhook can:

- Require specific JSON payload fields with `required_payload_fields`.
- Copy payload values into prompt fields with `payload_prompt_fields`.
- Add fixed prompt fields with `static_prompt_fields`.
- Attach an Oz skill with `skill_spec`.
- Require a static token with `auth_token`.

Example request:

```sh
curl -X POST http://localhost:3000/webhooks/json-task \
  -H "Authorization: Bearer $JSON_TASK_WEBHOOK_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"request":"Summarize this payload","request_id":"example-123"}'
```

### Webhook auth

Webhook auth is optional in code for backwards compatibility, but public deployments should set `auth_token` for every webhook.

- Default header: `Authorization`.
- Custom header: set `auth_header_name` in the webhook config.
- Accepted token formats: `Bearer <token>` or the raw token value.
- Token comparison uses constant-time comparison and does not log the configured secret.

## Optional Cloud Run deployment

The `deploy/` directory contains a placeholder Cloud Run service manifest and deployment notes.

High-level flow:

1. Build and push an image to your container registry.
2. Store `config.yaml` content in a secret manager entry or equivalent platform secret.
3. Store Slack, Oz, and webhook secrets as secret environment variables.
4. Deploy a service using placeholders from `deploy/cloud-run.service.example.yaml`.
5. Update Slack Event Subscriptions and webhook providers to use the deployed service URL.

See `deploy/README.md` for concrete placeholder commands.

## Endpoints

- `GET /` — list configured bots and webhooks.
- `GET /health` — health check with loaded bot and webhook names.
- `GET /diagnostics/oz` — optional outbound Oz API connectivity diagnostic. It is disabled unless `GATEWAY_ENABLE_DIAGNOSTICS=true` and never returns API keys.
- `POST /bots/<bot-name>/slack/events` — Slack Events API and interactivity endpoint.
- `POST /webhooks/<webhook-name>` — generic webhook endpoint.

## Public-safety checklist

Before publishing or deploying a fork:

- Do not commit `.env`.
- Do not commit `config.yaml`.
- Do not commit real API keys, Slack tokens, signing secrets, webhook auth tokens, or third-party MCP credentials.
- Do not commit real Oz environment IDs, cloud project IDs, service URLs, customer names, or proprietary bot/workflow names.
- Keep deployment examples placeholder-based.
- Prefer cloud/provider secret managers for gateway host secrets.
- Prefer Oz-managed secrets for MCP server credentials used inside Oz runs.
