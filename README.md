# Okta → Greenhouse User Sync

Automatically syncs user lifecycle events from Okta to Greenhouse Recruiting:
- **New users** created in Okta → added to Greenhouse as Basic users
- **Deactivated users** in Okta → disabled in Greenhouse

Runs every 30 minutes via GitHub Actions.

## Setup

### 1. Greenhouse API Key
1. In Greenhouse, go to **Configure** → **Dev Center** → **API Credential Management**
2. Create a new **Harvest API** key with **User Management** permissions
3. Note the `On-Behalf-Of` user ID (a Greenhouse site admin user ID)

### 2. Okta API Token
1. In Okta Admin, go to **Security** → **API** → **Tokens**
2. Create a new token with read access to the System Log and Users

### 3. Repository Secrets
Add these secrets in the GitHub repo settings:
- `OKTA_DOMAIN` — e.g., `devrev.okta.com`
- `OKTA_API_TOKEN` — Okta API token
- `GREENHOUSE_API_KEY` — Greenhouse Harvest API key
- `GREENHOUSE_ON_BEHALF_OF` — Greenhouse site admin user ID
- `SLACK_WEBHOOK_URL` — (optional) Slack webhook for notifications
