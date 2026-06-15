import json
import os
import urllib.parse
import urllib.request
from base64 import b64encode

import config


DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


def okta_get(path, params=None):
    url = f"https://{config.OKTA_DOMAIN}/api/v1/{path}"
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"SSWS {config.OKTA_API_TOKEN}")
    req.add_header("Accept", "application/json")
    return urllib.request.urlopen(req)


def okta_list_active_users():
    """Page through all ACTIVE Okta users."""
    users = []
    url = f"https://{config.OKTA_DOMAIN}/api/v1/users?filter=" + urllib.parse.quote('status eq "ACTIVE"') + "&limit=200"
    page = 0
    while url:
        page += 1
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"SSWS {config.OKTA_API_TOKEN}")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req) as resp:
            batch = json.loads(resp.read())
            users.extend(batch)
            link = resp.headers.get("Link", "")
        print(f"  fetched page {page}: +{len(batch)} (total={len(users)})")
        # parse pagination next link from Link header
        next_url = None
        for part in link.split(","):
            part = part.strip()
            if 'rel="next"' in part:
                # format: <https://...>; rel="next"
                start = part.find("<")
                end = part.find(">")
                if start != -1 and end != -1:
                    next_url = part[start + 1:end]
                break
        url = next_url
    return users


def is_service_account(email, first_name, last_name):
    """Detect bot/service accounts that should not go to Greenhouse."""
    local = email.split("@")[0].lower()
    if local.startswith("svc-") or local.startswith("svc_"):
        return True
    full_name = f"{first_name} {last_name}".lower()
    if "(svc)" in full_name or full_name.endswith(" svc"):
        return True
    return False


def greenhouse_request(method, path, body=None):
    url = f"https://harvest.greenhouse.io/v1/{path}"
    creds = b64encode(f"{config.GREENHOUSE_API_KEY}:".encode()).decode()
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Basic {creds}")
    req.add_header("Content-Type", "application/json")
    if config.GREENHOUSE_ON_BEHALF_OF:
        req.add_header("On-Behalf-Of", config.GREENHOUSE_ON_BEHALF_OF)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise Exception(f"Greenhouse API error {e.code}: {e.read().decode()}")


def find_greenhouse_user(email):
    try:
        users = greenhouse_request("GET", f"users?email={urllib.parse.quote(email)}")
    except Exception:
        return None
    if isinstance(users, list) and users:
        return users[0]
    if isinstance(users, dict) and users.get("id"):
        return users
    return None


def slack(message):
    if not config.SLACK_WEBHOOK_URL:
        return
    try:
        urllib.request.urlopen(urllib.request.Request(
            config.SLACK_WEBHOOK_URL,
            data=json.dumps({"text": message}).encode(),
            headers={"Content-Type": "application/json"},
        ))
    except Exception:
        pass


def main():
    print(f"Reconcile run | DRY_RUN={DRY_RUN}")
    print("Fetching Okta active users...")
    users = okta_list_active_users()
    print(f"  {len(users)} active users in Okta")

    eligible = []
    skipped_svc = 0
    skipped_no_email = 0
    skipped_intern = 0
    for u in users:
        profile = u.get("profile", {})
        emp_status = profile.get("employmentStatus", "")
        email = profile.get("email", "").lower().strip()
        first_name = profile.get("firstName", "")
        last_name = profile.get("lastName", "")
        if not email:
            skipped_no_email += 1
            continue
        if emp_status in ("Internship", "Contractor"):
            skipped_intern += 1
            continue
        if is_service_account(email, first_name, last_name):
            skipped_svc += 1
            continue
        eligible.append({
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "employment_status": emp_status,
        })
    print(f"  {len(eligible)} eligible (skipped: {skipped_intern} interns/contractors, {skipped_svc} service accounts, {skipped_no_email} no email)")

    created = 0
    skipped_existing = 0
    errors = 0
    missing = []

    for u in eligible:
        email = u["email"]
        existing = find_greenhouse_user(email)
        if existing:
            skipped_existing += 1
            continue
        missing.append(u)

    print(f"  {len(missing)} eligible Okta users missing in Greenhouse")
    for u in missing:
        email = u["email"]
        print(f"  -> {email} ({u['first_name']} {u['last_name']}, {u['employment_status']})")
        if DRY_RUN:
            continue
        try:
            greenhouse_request("POST", "users", {
                "first_name": u["first_name"],
                "last_name": u["last_name"],
                "email": email,
            })
            created += 1
            slack(f":white_check_mark: Reconcile created Greenhouse user: `{email}` ({u['first_name']} {u['last_name']})")
        except Exception as e:
            errors += 1
            print(f"     ERROR: {e}")
            slack(f":x: Reconcile failed for `{email}`: {e}")

    print(f"\nDone. existing={skipped_existing}, missing={len(missing)}, created={created}, errors={errors}")
    if not DRY_RUN and (created or errors):
        slack(
            f":arrows_counterclockwise: *Greenhouse reconcile*\n"
            f"• Existing: {skipped_existing}\n"
            f"• Missing: {len(missing)}\n"
            f"• Created: {created}\n"
            f"• Errors: {errors}"
        )


if __name__ == "__main__":
    main()
