import json
import os
import urllib.parse
import urllib.request

import config
import greenhouse


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
            # Okta returns MULTIPLE Link headers (rel="self" and rel="next")
            # as separate header lines. resp.headers.get() only returns the
            # first (usually "self"), so pagination silently stopped after
            # page 1 — capping the reconcile at 200 users. Use get_all() to
            # collect every Link header.
            link_headers = resp.headers.get_all("Link") or []
        print(f"  fetched page {page}: +{len(batch)} (total={len(users)})")
        # parse pagination next link from all Link headers
        next_url = None
        for header in link_headers:
            for part in header.split(","):
                part = part.strip()
                if 'rel="next"' in part:
                    # format: <https://...>; rel="next"
                    start = part.find("<")
                    end = part.find(">")
                    if start != -1 and end != -1:
                        next_url = part[start + 1:end]
                    break
            if next_url:
                break
        url = next_url
    return users


def is_service_account(email, first_name, last_name):
    """Detect bot/service/role accounts that should not go to Greenhouse."""
    local = email.split("@")[0].lower()
    # Explicit service prefixes
    if local.startswith("svc-") or local.startswith("svc_"):
        return True
    # Board-member / advisor prefixes (b-*, advisorN)
    if local.startswith("b-") or local.startswith("advisor"):
        return True
    # Automation/placeholder patterns (auto-userN)
    if local.startswith("auto-user") or local.startswith("auto_user"):
        return True
    # Bot / sync / support / role-mailbox suffixes and substrings
    bot_markers = ("-bot", "_bot", "-sync", "_sync", "-support", "_support")
    if local.endswith(bot_markers) or any(m in local for m in bot_markers):
        return True
    # Known role mailboxes / non-human accounts by exact local part
    role_mailboxes = {
        "keyring", "advocacy", "devrevuteam", "meetcomputer",
        "outreach.connect", "talent-review", "figma-bot",
    }
    if local in role_mailboxes:
        return True
    full_name = f"{first_name} {last_name}".lower()
    if "(svc)" in full_name or full_name.endswith(" svc"):
        return True
    return False


def is_eligible_employee(email, emp_status):
    """Only real DevRev employees (Full-Time / blank-Okta-managed) belong in
    Greenhouse. Excludes board members, advisors, and external/vendor emails."""
    # Must be a DevRev-domain mailbox — external/vendor emails are not employees
    if not email.endswith("@devrev.ai"):
        return False
    # Exclude non-employee relationship types
    if emp_status in ("Board Member", "Advisor", "Investor"):
        return False
    return True


def greenhouse_list_all_user_emails():
    """Fetch every Greenhouse user (paginated) and return a set of lowercased emails.

    The per-email lookup GET /v3/users?primary_email=X returns a single user; to avoid
    duplicate-create races we fetch the full list once and match locally.
    v3 uses cursor-based pagination: the first request may set per_page, but once a
    cursor appears in the Link rel="next" URL it must be the ONLY query param — so we
    just follow the returned URL verbatim.
    """
    emails = set()
    url = "users?per_page=500"
    page = 0
    while url:
        page += 1
        batch, resp = greenhouse.request("GET", url, return_response=True)
        link = resp.headers.get("Link", "")
        for u in (batch or []):
            primary = (u.get("primary_email") or "").lower().strip()
            if primary:
                emails.add(primary)
            for addr in u.get("emails", []) or []:
                if isinstance(addr, dict):
                    e = (addr.get("email") or "").lower().strip()
                elif isinstance(addr, str):
                    e = addr.lower().strip()
                else:
                    e = ""
                if e:
                    emails.add(e)
        print(f"  fetched Greenhouse users page {page}: +{len(batch or [])} (total emails={len(emails)})")
        # parse Link header for rel="next" — follow the full URL verbatim (cursor is opaque)
        next_url = None
        for part in link.split(","):
            part = part.strip()
            if 'rel="next"' in part:
                start = part.find("<")
                end = part.find(">")
                if start != -1 and end != -1:
                    next_url = part[start + 1:end]
                break
        url = next_url
    return emails


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
    skipped_ineligible = 0
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
        if not is_eligible_employee(email, emp_status):
            skipped_ineligible += 1
            continue
        eligible.append({
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "employment_status": emp_status,
        })
    print(f"  {len(eligible)} eligible (skipped: {skipped_intern} interns/contractors, {skipped_svc} service accounts, {skipped_ineligible} board/advisor/external, {skipped_no_email} no email)")

    print("Fetching all Greenhouse users (paginated)...")
    gh_emails = greenhouse_list_all_user_emails()
    print(f"  {len(gh_emails)} unique emails in Greenhouse")

    created = 0
    skipped_existing = 0
    errors = 0
    missing = []

    for u in eligible:
        email = u["email"]
        if email in gh_emails:
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
            greenhouse.request("POST", "users", {
                "first_name": u["first_name"],
                "last_name": u["last_name"],
                "primary_email": email,
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
