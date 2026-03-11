"""
KiteAlerts V6.0 — Telegram Alert System
Dual-Profiler payload format: Math + AI context in every signal.
"""

import os
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send_message(text):
    """Send raw HTML message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("[TELEGRAM] Bot token or chat ID not configured")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        logging.error(f"[TELEGRAM] Send failed: {e}")
        return False


def send_signal_alert(instrument, engine, direction, entry, sl, target,
                      math_profile, ai_profile, extra_info=None):
    """
    V6.0 Dual-Profiler Signal Alert.

    Args:
        instrument: str (display name)
        engine: str (e.g. "MODE_DON v2.2", "RIJIN Gear 1")
        direction: str ("LONG" or "SHORT")
        entry: float
        sl: float
        target: float
        math_profile: dict {"tag": "...", "reasons": ["...", "..."]}
        ai_profile: dict {"tag": "...", "bullets": ["...", "...", "..."]}
        extra_info: optional str (e.g. "⚠️ EXPIRY WARNING")
    """
    # Math section
    math_reasons = ""
    for r in math_profile.get("reasons", [])[:2]:
        math_reasons += f"• {r}\n"

    # AI section
    ai_bullets = ""
    for b in ai_profile.get("bullets", [])[:3]:
        ai_bullets += f"• {b}\n"

    # Extra warning line
    extra_line = f"\n{extra_info}" if extra_info else ""

    msg = (
        f"🚨 <b>KITEALERTS SIGNAL — MANUAL EXECUTION</b>\n\n"
        f"📍 Instrument: <b>{instrument}</b>\n"
        f"⚙️ Strategy: <b>{engine}</b>\n"
        f"🧭 Direction: <b>{direction}</b>\n\n"
        f"💵 Entry: {entry}\n"
        f"🛑 SL: {sl}\n"
        f"🎯 Target: {target}\n\n"
        f"────────────────────────\n"
        f"⚙️ <b>MATH ENGINE PROFILE:</b>\n"
        f"Tag: {math_profile.get('tag', 'Unknown')}\n"
        f"{math_reasons}\n"
        f"🤖 <b>AI ENGINE PROFILE:</b>\n"
        f"Tag: {ai_profile.get('tag', 'Processing...')}\n"
        f"{ai_bullets}"
        f"────────────────────────\n"
        f"👉 <b>Trader Decision Required.</b>"
        f"{extra_line}"
    )

    return send_message(msg)


def send_exit_alert(instrument, engine, direction, entry, exit_price, pnl_r):
    """Trade exit notification."""
    emoji = "✅" if pnl_r > 0 else "❌"
    exit_type = "PROFIT" if pnl_r > 0 else "STOP HIT" if pnl_r < 0 else "BREAKEVEN"

    msg = (
        f"{emoji} <b>EXIT — {instrument}</b>\n\n"
        f"⚙️ {engine} | {direction}\n"
        f"💵 Entry: {entry} → Exit: {exit_price}\n"
        f"📊 P&L: <b>{pnl_r:+.2f}R</b> ({exit_type})\n"
    )
    return send_message(msg)


def send_system_alert(title, body):
    """Generic system alert (startup, shutdown, errors)."""
    msg = f"📢 <b>{title}</b>\n\n{body}"
    return send_message(msg)
