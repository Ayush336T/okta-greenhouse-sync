import json
import os
import urllib.request
from base64 import b64encode

api_key = os.environ.get("GREENHOUSE_API_KEY", "")
email = os.environ.get("LOOKUP_EMAIL", "sheetal.mohan@devrev.ai")

url = f"https://harvest.greenhouse.io/v1/users?email={email}"
credentials = b64encode(f"{api_key}:".encode()).decode()

req = urllib.request.Request(url)
req.add_header("Authorization", f"Basic {credentials}")

with urllib.request.urlopen(req) as resp:
    users = json.loads(resp.read())
    if users:
        user = users[0]
        print(f"Found user: {user.get('first_name', '')} {user.get('last_name', '')}")
        print(f"User ID: {user['id']}")
        print(f"Email: {email}")
    else:
        print(f"No user found for {email}")
