import json
import os
import urllib.parse
import urllib.request

import config
import greenhouse


def okta_get(path):
    url = f"https://{config.OKTA_DOMAIN}/api/v1/{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"SSWS {config.OKTA_API_TOKEN}")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def slack(message):
    if not config.SLACK_WEBHOOK_URL:
        return
    try:
        urllib.request.urlopen(urllib.request.Request(
            config.SLACK_WEBHOOK_URL,
            data=json.dumps({"text": message}).encode(),
            headers={"Content-Type": "application/json"},
        ))
    except Exception as e:
        print(f"  WARNING: Slack notification failed: {e}")


def main():
    email = os.environ.get("CREATE_EMAIL", "").strip().lower()
    if not email:
        raise SystemExit("CREATE_EMAIL not provided")

    print(f"Looking up {email} in Okta...")
    user = okta_get(f"users/{urllib.parse.quote(email)}")
    profile = user.get("profile", {})
    first_name = profile.get("firstName", "")
    last_name = profile.get("lastName", "")
    employment_status = profile.get("employmentStatus", "")
    okta_status = user.get("status", "")
    print(f"  Okta status: {okta_status}, employmentStatus: {employment_status}")
    print(f"  Name: {first_name} {last_name}")

    if okta_status != "ACTIVE":
        print(f"  WARNING: Okta status is '{okta_status}' — proceeding anyway since this is a manual override")

    print(f"\nChecking if {email} already exists in Greenhouse...")
    try:
        existing = greenhouse.request("GET", f"users?primary_email={urllib.parse.quote(email)}")
    except Exception as e:
        print(f"  lookup error: {e}")
        existing = None

    if existing:
        record = existing[0] if isinstance(existing, list) and existing else existing
        if isinstance(record, dict) and record.get("id"):
            print(f"  Already in Greenhouse (id={record.get('id')}, deactivated={record.get('deactivated')})")
            slack(f":information_source: Manual create skipped: `{email}` already in Greenhouse")
            return

    print(f"\nCreating Greenhouse user...")
    result = greenhouse.request("POST", "users", {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": email,
    })
    print(f"  Created. id={result.get('id')}")
    slack(f":white_check_mark: Manually created Greenhouse user: `{email}` ({first_name} {last_name})")


if __name__ == "__main__":
    main()
