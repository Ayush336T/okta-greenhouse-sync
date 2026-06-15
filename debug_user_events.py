import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

OKTA_DOMAIN = os.environ.get("OKTA_DOMAIN", "devrev.okta.com")
OKTA_API_TOKEN = os.environ.get("OKTA_API_TOKEN", "")
EMAIL = os.environ.get("DEBUG_EMAIL", "maxwell.paris@devrev.ai")
HOURS = int(os.environ.get("DEBUG_HOURS", "48"))


def okta_get(path, params=None):
    url = f"https://{OKTA_DOMAIN}/api/v1/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"SSWS {OKTA_API_TOKEN}")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    since = (datetime.now(timezone.utc) - timedelta(hours=HOURS)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    print(f"Looking up Okta events for {EMAIL} since {since}")
    events = okta_get("logs", {
        "filter": f'target.alternateId eq "{EMAIL}"',
        "since": since,
        "sortOrder": "ASCENDING",
    })
    print(f"Found {len(events)} events:")
    for e in events:
        print(f"  {e.get('published')} | {e.get('eventType')} | outcome={e.get('outcome', {}).get('result')}")
    # also fetch the user record
    print("\n--- Okta user record ---")
    try:
        user = okta_get(f"users/{urllib.parse.quote(EMAIL)}")
        print(f"  status: {user.get('status')}")
        print(f"  activated: {user.get('activated')}")
        print(f"  lastLogin: {user.get('lastLogin')}")
        print(f"  employmentStatus: {user.get('profile', {}).get('employmentStatus')}")
    except Exception as e:
        print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()
