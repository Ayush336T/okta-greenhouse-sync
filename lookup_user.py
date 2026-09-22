import json
import os
import urllib.parse

import greenhouse

email = os.environ.get("LOOKUP_EMAIL", "sheetal.mohan@devrev.ai")

data = greenhouse.request("GET", f"users?primary_email={urllib.parse.quote(email)}")
print(f"Raw response: {json.dumps(data, indent=2)[:2000]}")

if isinstance(data, list) and data:
    user = data[0]
    print(f"\nFound user: {user.get('first_name', '')} {user.get('last_name', '')}")
    print(f"User ID: {user.get('id')}")
    print(f"Email: {email}")
elif isinstance(data, dict) and data.get("id"):
    print(f"\nFound user: {data.get('first_name', '')} {data.get('last_name', '')}")
    print(f"User ID: {data['id']}")
    print(f"Email: {email}")
else:
    print(f"No user found for {email}")
