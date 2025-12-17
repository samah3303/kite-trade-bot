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
print("ACCESS_TOKEN:", data["access_token"])
