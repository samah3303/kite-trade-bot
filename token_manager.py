"""
Token Manager — Kite Access Token Health Check & Expiry Alert

Detects expired/invalid tokens, sends Telegram alerts with login URL,
and provides token status for the dashboard.
"""

import os
import logging
import time as _time
from datetime import datetime
from dotenv import load_dotenv
from kiteconnect import KiteConnect

load_dotenv()

# Shared state
_token_status = {
    "valid": None,       # True/False/None (unknown)
    "last_check": None,
    "last_error": None,
    "alert_sent_today": False,
    "alert_date": None,
}


def check_token_health(kite=None):
    """
    Quick token health check by calling kite.profile().
    Returns True if token is valid, False if expired/invalid.
    """
    global _token_status

    if kite is None:
        kite = KiteConnect(api_key=os.getenv("KITE_API_KEY"))
        kite.set_access_token(os.getenv("KITE_ACCESS_TOKEN"))

    try:
        kite.profile()
        _token_status["valid"] = True
        _token_status["last_check"] = datetime.now().isoformat()
        _token_status["last_error"] = None
        return True
    except Exception as e:
        error_str = str(e).lower()
        is_auth_error = any(word in error_str for word in [
            "token", "access", "403", "unauthorized", "invalid",
            "expired", "session", "login", "incorrect"
        ])

        _token_status["valid"] = False
        _token_status["last_check"] = datetime.now().isoformat()
        _token_status["last_error"] = str(e)

        if is_auth_error:
            _send_token_alert(str(e))

        return False


def _send_token_alert(error_msg):
    """Send Telegram alert with login URL (once per day max)."""
    global _token_status

    today = datetime.now().strftime("%Y-%m-%d")

    # Don't spam — only send once per day
    if _token_status["alert_sent_today"] and _token_status["alert_date"] == today:
        return

    try:
        from telegram_alerts import send_message as send_telegram_message

        api_key = os.getenv("KITE_API_KEY")
        dashboard_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:5000")
        login_url = f"{dashboard_url}/login"

        send_telegram_message(
            f"🔑 <b>TOKEN EXPIRED — ACTION REQUIRED</b>\n\n"
            f"Kite access token is invalid or expired.\n"
            f"Error: <code>{error_msg[:100]}</code>\n\n"
            f"⚡ <b>Quick Fix:</b>\n"
            f"1. Click: {login_url}\n"
            f"2. Login to Zerodha\n"
            f"3. Token auto-saves\n"
            f"4. Restart the bot\n\n"
            f"⏸ Both RIJIN and MODE_DON are paused until token is refreshed."
        )

        _token_status["alert_sent_today"] = True
        _token_status["alert_date"] = today

        logging.warning("🔑 TOKEN EXPIRED — Telegram alert sent with login URL")

    except Exception as e:
        logging.error(f"Failed to send token alert: {e}")


def is_token_error(exception):
    """Check if an exception is a token/auth error."""
    error_str = str(exception).lower()
    return any(word in error_str for word in [
        "token", "access", "403", "unauthorized", "invalid",
        "expired", "session", "login", "incorrect", "api_key"
    ])


def handle_api_error(exception, context=""):
    """
    Call this from any engine's except block.
    If it's a token error → sends Telegram alert + returns True.
    If it's a different error → returns False (handle normally).
    """
    if is_token_error(exception):
        logging.error(f"🔑 TOKEN ERROR in {context}: {exception}")
        _token_status["valid"] = False
        _token_status["last_error"] = str(exception)
        _token_status["last_check"] = datetime.now().isoformat()
        _send_token_alert(str(exception))
        return True
    return False


def get_token_status():
    """Get current token status for dashboard."""
    return {
        "valid": _token_status["valid"],
        "last_check": _token_status["last_check"],
        "last_error": _token_status["last_error"],
        "alert_sent": _token_status["alert_sent_today"],
    }


def reset_daily_alert():
    """Reset the daily alert flag (call on new day)."""
    _token_status["alert_sent_today"] = False
    _token_status["alert_date"] = None
