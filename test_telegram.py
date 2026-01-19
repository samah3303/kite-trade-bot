
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TG_BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_test_message():
    print(f"Testing Telegram Notifications...")
    print(f"Bot Token: {BOT_TOKEN[:5]}...{BOT_TOKEN[-5:] if BOT_TOKEN else 'None'}")
    print(f"Chat ID: {CHAT_ID}")
    
    url = f"{TG_BASE_URL}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": "🔔 <b>Telegram Diagnostic Test</b>\nIf you see this, your credentials are correct!", "parse_mode": "HTML"}
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            print("✅ SUCCESS: Telegram message sent!")
            print(f"Response: {response.text}")
        else:
            print(f"❌ FAILED: Status Code {response.status_code}")
            print(f"Error Detail: {response.text}")
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")

if __name__ == "__main__":
    send_test_message()
