from kiteconnect import KiteConnect
import webbrowser
import urllib.parse
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")

kite = KiteConnect(api_key=API_KEY)

print("Login URL:")
print(kite.login_url())
webbrowser.open(kite.login_url())

request_token = input("Enter request_token from redirected URL: ").strip()

data = kite.generate_session(request_token, api_secret=API_SECRET)
access_token = data["access_token"]
print("ACCESS_TOKEN:", access_token)

# Auto-update .env
env_path = ".env"
with open(env_path, "r") as f:
    lines = f.readlines()

with open(env_path, "w") as f:
    updated = False
    for line in lines:
        if line.startswith("KITE_ACCESS_TOKEN="):
            f.write(f"KITE_ACCESS_TOKEN={access_token}\n")
            updated = True
        else:
            f.write(line)
    if not updated:
        f.write(f"\nKITE_ACCESS_TOKEN={access_token}\n")

print("✅ Updated .env with new Access Token")
