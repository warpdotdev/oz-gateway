# Deployment examples

This directory contains placeholder-only deployment examples. Replace every `<...>` value before using them.

Do not commit real deployment project IDs, service URLs, environment IDs, Slack credentials, Oz API keys, webhook auth tokens, or operational `config.yaml` content.

## Cloud Run overview

A Cloud Run deployment needs two categories of configuration:

1. A runtime `config.yaml` file provided at deploy time, usually mounted from a secret.
2. Secret environment variables referenced by that config, such as Slack tokens, Oz API keys, Oz environment IDs, and webhook auth tokens.

MCP server secrets are different: if they are referenced under a bot's `mcp_servers` block, create them as Oz-managed secrets so the Oz cloud-agent runtime receives them.

## Build and push an image

```sh
PROJECT_ID=<your-gcp-project-id>
REGION=<your-region>
REPOSITORY=<your-artifact-registry-repository>
IMAGE_NAME=oz-gateway
TAG=$(git rev-parse --short HEAD)
IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:$TAG"

gcloud builds submit . --tag "$IMAGE_URI" --project "$PROJECT_ID"
```

## Store gateway config as a secret

Create a local `config.yaml` from `config.example.yaml`, replace placeholders, and then store it in your cloud secret manager. Do not commit it.

```sh
gcloud secrets create OZ_GATEWAY_CONFIG_YAML   --project "$PROJECT_ID"   --replication-policy automatic   --data-file ./config.yaml
```

To update it later:

```sh
gcloud secrets versions add OZ_GATEWAY_CONFIG_YAML   --project "$PROJECT_ID"   --data-file ./config.yaml
```

## Store gateway host secrets

Create one secret per environment variable referenced outside `mcp_servers` in `config.yaml`.

Example placeholders:

```sh
printf '%s' '<xoxb-slack-bot-token>' | gcloud secrets create ASSISTANT_SLACK_BOT_TOKEN   --project "$PROJECT_ID"   --replication-policy automatic   --data-file -

printf '%s' '<slack-signing-secret>' | gcloud secrets create ASSISTANT_SLACK_SIGNING_SECRET   --project "$PROJECT_ID"   --replication-policy automatic   --data-file -

printf '%s' '<wk-oz-api-key>' | gcloud secrets create ASSISTANT_OZ_API_KEY   --project "$PROJECT_ID"   --replication-policy automatic   --data-file -

printf '%s' '<oz-environment-id>' | gcloud secrets create ASSISTANT_OZ_ENVIRONMENT_ID   --project "$PROJECT_ID"   --replication-policy automatic   --data-file -
```

Repeat for webhook secrets and any additional bots.

## Deploy with the example service manifest

Copy the example manifest and replace placeholders:

```sh
cp deploy/cloud-run.service.example.yaml /tmp/oz-gateway-service.yaml
```

Edit `/tmp/oz-gateway-service.yaml`:

- `<your-gcp-project-id>`
- `<your-region>`
- `<your-service-name>`
- `<your-image-uri>`
- `<your-service-account>`
- Secret names and environment variables for your bots and webhooks

Deploy:

```sh
gcloud run services replace /tmp/oz-gateway-service.yaml   --project "$PROJECT_ID"   --region "$REGION"
```

If you prefer flags instead of a manifest, use the same placeholders with `gcloud run deploy` and provider-specific secret flags.

## After deployment

1. Get the service URL:

```sh
gcloud run services describe <your-service-name>   --project "$PROJECT_ID"   --region "$REGION"   --format 'value(status.url)'
```

2. In each Slack app, set the Event Subscriptions request URL to:

```text
https://<your-service-domain>/bots/<bot-name>/slack/events
```

3. If using Slack interactivity, set the Interactivity request URL to the same endpoint.
4. In each external webhook provider, set the webhook URL to:

```text
https://<your-service-domain>/webhooks/<webhook-name>
```

5. Test health:

```sh
curl https://<your-service-domain>/health
```

## Secret rotation

For gateway host secrets, add a new secret version and redeploy or restart the Cloud Run revision if needed:

```sh
printf '%s' '<new-secret-value>' | gcloud secrets versions add <SECRET_NAME>   --project "$PROJECT_ID"   --data-file -
```

For MCP server secrets used by Oz runs, rotate them with the Oz CLI:

```sh
oz secret update --team EXAMPLE_MCP_TOKEN
```
