"""Greenhouse Harvest v3 API client (OAuth client-credentials).

Centralizes token fetch/caching/refresh so main.py, reconcile.py,
create_user.py, and lookup_user.py share one auth implementation.
"""
import json
import time
import urllib.parse
import urllib.request
import urllib.error
from base64 import b64encode

import config

_TOKEN = {"value": None, "expires_at": 0}


def _fetch_token():
    if not config.GREENHOUSE_CLIENT_ID or not config.GREENHOUSE_CLIENT_SECRET:
        raise Exception("GREENHOUSE_CLIENT_ID / GREENHOUSE_CLIENT_SECRET not set")
    creds = b64encode(
        f"{config.GREENHOUSE_CLIENT_ID}:{config.GREENHOUSE_CLIENT_SECRET}".encode()
    ).decode()
    form = {"grant_type": "client_credentials"}
    if config.GREENHOUSE_SUB_USER_ID:
        form["sub"] = config.GREENHOUSE_SUB_USER_ID
    req = urllib.request.Request(
        "https://auth.greenhouse.io/token",
        data=urllib.parse.urlencode(form).encode(),
        method="POST",
    )
    req.add_header("Authorization", f"Basic {creds}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise Exception(f"Greenhouse token error {e.code}: {e.read().decode()}")
    token = payload.get("access_token")
    if not token:
        raise Exception(f"No access_token in token response: {payload}")
    _TOKEN["value"] = token
    # refresh a minute early to avoid edge-of-expiry 401s
    _TOKEN["expires_at"] = time.time() + int(payload.get("expires_in", 3600)) - 60
    return token


def _token(force=False):
    if force or not _TOKEN["value"] or time.time() >= _TOKEN["expires_at"]:
        return _fetch_token()
    return _TOKEN["value"]


def request(method, path, body=None, return_response=False):
    """Call Harvest v3. `path` may be a relative path or a full URL (for pagination)."""
    url = path if path.startswith("http") else f"https://harvest.greenhouse.io/v3/{path}"
    data = json.dumps(body).encode() if body is not None else None

    def _do(token):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        return urllib.request.urlopen(req)

    resp = None
    for attempt in (1, 2):
        try:
            resp = _do(_token(force=(attempt == 2)))
            break
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 1:
                continue  # token stale — refresh once and retry
            raise Exception(f"Greenhouse API error {e.code}: {e.read().decode()}")

    raw = resp.read()
    parsed = json.loads(raw) if raw else None  # 204 (e.g. deactivate) → empty body
    if return_response:
        return parsed, resp
    return parsed
