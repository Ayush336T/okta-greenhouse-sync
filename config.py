import os

# Okta
OKTA_DOMAIN = os.environ.get("OKTA_DOMAIN", "devrev.okta.com")
OKTA_API_TOKEN = os.environ.get("OKTA_API_TOKEN", "")

# Greenhouse
GREENHOUSE_API_KEY = os.environ.get("GREENHOUSE_API_KEY", "")
GREENHOUSE_ON_BEHALF_OF = os.environ.get("GREENHOUSE_ON_BEHALF_OF", "")

# How far back to look for events (in minutes)
LOOKBACK_MINUTES = int(os.environ.get("LOOKBACK_MINUTES", "30"))

# Slack notifications
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
