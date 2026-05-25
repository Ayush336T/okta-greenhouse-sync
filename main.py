import json
import urllib.request
import urllib.parse
from base64 import b64encode
from datetime import datetime, timezone, timedelta

import config


def okta_request(path, params=None):
    """Make a GET request to the Okta API."""
    url = f"https://{config.OKTA_DOMAIN}/api/v1/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"SSWS {config.OKTA_API_TOKEN}")
    req.add_header("Accept", "application/json")

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def greenhouse_request(method, path, body=None):
    """Make a request to the Greenhouse Harvest API."""
    url = f"https://harvest.greenhouse.io/v1/{path}"
    credentials = b64encode(f"{config.GREENHOUSE_API_KEY}:".encode()).decode()

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Basic {credentials}")
    req.add_header("Content-Type", "application/json")
    if config.GREENHOUSE_ON_BEHALF_OF:
        req.add_header("On-Behalf-Of", config.GREENHOUSE_ON_BEHALF_OF)

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise Exception(f"Greenhouse API error {e.code}: {error_body}")


def send_slack_notification(message):
    """Send a notification to Slack via webhook."""
    if not config.SLACK_WEBHOOK_URL:
        return

    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        config.SLACK_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"  WARNING: Slack notification failed: {e}")


def get_recent_okta_events(event_type, since):
    """Get recent Okta system log events of a specific type."""
    since_str = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    events = okta_request("logs", {
        "filter": f'eventType eq "{event_type}"',
        "since": since_str,
        "sortOrder": "ASCENDING",
    })
    return events


def get_user_details(user_id):
    """Get full user profile from Okta."""
    return okta_request(f"users/{user_id}")


def find_greenhouse_user(email):
    """Find a user in Greenhouse by email."""
    try:
        users = greenhouse_request("GET", f"users?email={urllib.parse.quote(email)}")
        if users:
            return users[0]
    except Exception:
        pass
    return None


def create_greenhouse_user(first_name, last_name, email):
    """Create a new Basic user in Greenhouse."""
    body = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
    }
    return greenhouse_request("POST", "users", body)


def disable_greenhouse_user(user_id):
    """Disable a user in Greenhouse."""
    body = {"disabled": True}
    return greenhouse_request("PATCH", f"users/{user_id}", body)


def process_new_users(since):
    """Process user.lifecycle.create events from Okta."""
    events = get_recent_okta_events("user.lifecycle.create", since)
    created = 0

    for event in events:
        targets = event.get("target", [])
        for target in targets:
            if target.get("type") != "User":
                continue

            user_id = target.get("id")
            email = target.get("alternateId")
            display_name = target.get("displayName", "")

            if not email:
                continue

            # Check if already exists in Greenhouse
            existing = find_greenhouse_user(email)
            if existing:
                print(f"  {email} already exists in Greenhouse, skipping")
                continue

            # Get full name from Okta profile
            try:
                user = get_user_details(user_id)
                first_name = user.get("profile", {}).get("firstName", "")
                last_name = user.get("profile", {}).get("lastName", "")
            except Exception:
                parts = display_name.split(" ", 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ""

            try:
                result = create_greenhouse_user(first_name, last_name, email)
                print(f"  Created Greenhouse user: {email}")
                send_slack_notification(
                    f":white_check_mark: Created Greenhouse user: `{email}` ({first_name} {last_name})"
                )
                created += 1
            except Exception as e:
                print(f"  ERROR creating {email} in Greenhouse: {e}")
                send_slack_notification(
                    f":x: Failed to create Greenhouse user `{email}`: {e}"
                )

    return created


def process_deactivated_users(since):
    """Process user.lifecycle.deactivate events from Okta."""
    events = get_recent_okta_events("user.lifecycle.deactivate", since)
    deactivated = 0

    for event in events:
        targets = event.get("target", [])
        for target in targets:
            if target.get("type") != "User":
                continue

            email = target.get("alternateId")
            if not email:
                continue

            # Find in Greenhouse
            gh_user = find_greenhouse_user(email)
            if not gh_user:
                print(f"  {email} not found in Greenhouse, skipping")
                continue

            if gh_user.get("disabled"):
                print(f"  {email} already disabled in Greenhouse, skipping")
                continue

            try:
                disable_greenhouse_user(gh_user["id"])
                print(f"  Disabled Greenhouse user: {email}")
                send_slack_notification(
                    f":no_entry: Disabled Greenhouse user: `{email}`"
                )
                deactivated += 1
            except Exception as e:
                print(f"  ERROR disabling {email} in Greenhouse: {e}")
                send_slack_notification(
                    f":x: Failed to disable Greenhouse user `{email}`: {e}"
                )

    return deactivated


def main():
    print("=" * 60)
    print("Okta → Greenhouse User Sync")
    print(f"Run time: {datetime.now(timezone.utc).isoformat()}")
    print(f"Lookback: {config.LOOKBACK_MINUTES} minutes")
    print("=" * 60)

    since = datetime.now(timezone.utc) - timedelta(minutes=config.LOOKBACK_MINUTES)

    print("\nChecking for new users...")
    created = process_new_users(since)

    print("\nChecking for deactivated users...")
    deactivated = process_deactivated_users(since)

    print(f"\nDone. Created: {created}, Deactivated: {deactivated}")

    if created or deactivated:
        send_slack_notification(
            f":arrows_counterclockwise: *Okta→Greenhouse sync complete*\n"
            f"• Users created: {created}\n"
            f"• Users disabled: {deactivated}"
        )


if __name__ == "__main__":
    main()
