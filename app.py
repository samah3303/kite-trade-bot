"""
KiteAlerts V6.0 — Flask Application
Tri-Core: MODE_DON v2.2 · RIJIN v3.2 · MODE_VORTEX v1.0
"""

import os
import sys
import io
import threading
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify, Response, request, redirect, session, url_for
from dotenv import load_dotenv, set_key
from kiteconnect import KiteConnect

import token_manager

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "kitealerts_v6_secret")

# Kite for login flow
API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
kite = KiteConnect(api_key=API_KEY)

# Log capture
log_capture_string = io.StringIO()


class LogCatcher:
    def write(self, data):
        log_capture_string.write(data)
        sys.__stdout__.write(data)

    def flush(self):
        pass


sys.stdout = LogCatcher()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# ===================================================================
# ENGINE THREAD
# ===================================================================

engine = None
engine_thread = None


def start_engine():
    """Start the tri-core engine in a background thread."""
    global engine, engine_thread
    from engine_runner import TriCoreRunner

    if engine and engine.running:
        logging.info("Engine already running")
        return

    stop_event = threading.Event()
    engine = TriCoreRunner(stop_event=stop_event)
    engine_thread = threading.Thread(target=engine.run, daemon=True, name="TriCoreEngine")
    engine_thread.start()
    logging.info("🚀 Tri-Core Engine thread started")


def stop_engine():
    """Stop the engine."""
    global engine
    if engine:
        engine.stop()
        logging.info("🛑 Engine stop requested")


# ===================================================================
# ROUTES
# ===================================================================

@app.route("/")
def dashboard():
    stats = engine.get_stats() if engine else {"version": "V6.0", "running": False, "instruments": {}}
    token_status = token_manager.get_token_status()
    return render_template("dashboard.html", stats=stats, token_status=token_status)


@app.route("/status")
def status():
    stats = engine.get_stats() if engine else {"running": False}
    stats["token"] = token_manager.get_token_status()
    return jsonify(stats)


@app.route("/login")
def login():
    return redirect(kite.login_url())


@app.route("/callback")
def callback():
    """Zerodha OAuth callback — save token and refresh engine."""
    request_token = request.args.get("request_token")
    if not request_token:
        return "Missing request_token", 400

    try:
        data = kite.generate_session(request_token, api_secret=API_SECRET)
        access_token = data["access_token"]

        # Save to .env
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        set_key(env_path, "KITE_ACCESS_TOKEN", access_token)
        os.environ["KITE_ACCESS_TOKEN"] = access_token

        # Refresh engine
        kite.set_access_token(access_token)
        if engine:
            engine.refresh_token(access_token)

        logging.info(f"✅ Token refreshed: {access_token[:8]}...")
        return redirect("/")

    except Exception as e:
        logging.error(f"Callback error: {e}")
        return f"Login failed: {e}", 500


@app.route("/auth-status")
def auth_status():
    valid = token_manager.check_token_health(kite)
    return jsonify({"valid": valid, **token_manager.get_token_status()})


@app.route("/start-engine", methods=["POST"])
def start_engine_route():
    start_engine()
    return jsonify({"status": "started"})


@app.route("/stop-engine", methods=["POST"])
def stop_engine_route():
    stop_engine()
    return jsonify({"status": "stopped"})


@app.route("/logs")
def logs():
    log_content = log_capture_string.getvalue()
    lines = log_content.split("\n")[-200:]
    return Response("\n".join(lines), mimetype="text/plain")


# ===================================================================
# STARTUP
# ===================================================================

# Auto-start engine on boot
start_engine()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
