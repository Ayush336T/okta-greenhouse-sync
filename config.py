import os

# Okta
OKTA_DOMAIN = os.environ.get("OKTA_DOMAIN", "devrev.okta.com")
OKTA_API_TOKEN = os.environ.get("OKTA_API_TOKEN", "")

# Greenhouse (Harvest v3 OAuth client-credentials)
GREENHOUSE_CLIENT_ID = os.environ.get("GREENHOUSE_CLIENT_ID", "")
GREENHOUSE_CLIENT_SECRET = os.environ.get("GREENHOUSE_CLIENT_SECRET", "")
# Optional: numeric Greenhouse user_id (Site Admin) to act as. Leave unset to
# act as the credential's own integration user.
GREENHOUSE_SUB_USER_ID = os.environ.get("GREENHOUSE_SUB_USER_ID", "")

# How far back to look for events (in minutes)
LOOKBACK_MINUTES = int(os.environ.get("LOOKBACK_MINUTES", "30"))

# Slack notifications (set via SLACK_WEBHOOK_URL secret in GitHub Actions)
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
