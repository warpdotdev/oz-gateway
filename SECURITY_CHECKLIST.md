# Public-readiness security checklist
Use this checklist before publishing or packaging the gateway.
## Required validation
Run the unit tests:
`python3 -m unittest discover -s tests`
Run the sample placeholder audit:
`python3 scripts/audit_public_readiness.py --scope samples`
For a full-repository scan, create an untracked denylist file outside the repo with one proprietary customer, workflow, bot, environment, or internal project term per line. Prefix a line with `re:` to use a regular expression. Then run:
`python3 scripts/audit_public_readiness.py --scope all --terms-file /path/to/private-denylist.txt`
Do not commit the private denylist file.
## Manual public-safety review
- No `.env`, `config.yaml`, service account JSON, private key, or operational deployment config is present.
- `config.example.yaml` and `.env.example` use placeholders for tokens, signing secrets, API keys, environment IDs, auth tokens, and skill specs.
- Examples use generic bot, webhook, skill, and environment names.
- Source and docs do not include customer-specific workflows, private repository names, proprietary codenames, or internal-only deployment URLs.
- Webhook auth examples require a placeholder token and do not document real shared secrets.
- Oz run configuration examples do not resolve or inline MCP secrets; MCP environment values should remain placeholders for the target Oz environment.
