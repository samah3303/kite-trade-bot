import os
from flask import Flask, render_template, jsonify, Response, request, redirect, session, url_for
import sys
import time
import io
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv, set_key
from kiteconnect import KiteConnect
import unified_engine as bot

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback_dev_secret_key")

# Globals
API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
USE_RIJIN = os.getenv("USE_RIJIN_SYSTEM", "false").lower() == "true"
MODE_DON_ENABLED = os.getenv("MODE_DON_ENABLED", "true").lower() == "true"

# Kite for login flow
kite = KiteConnect(api_key=API_KEY)

# Bot Selection
if USE_RIJIN:
    print("[RIJIN] Loading RIJIN SYSTEM v3.0.1...")
    # Import the new RIJIN v3.0.1 live engine
    try:
        import rijin_live_runner  # We'll create this wrapper
        active_bot = rijin_live_runner
        bot_mode = "RIJIN v3.0.1"
    except ImportError:
        print("[WARN] rijin_live_runner not found, falling back to unified engine")
        active_bot = bot.runner
        bot_mode = "UNIFIED"
else:
    print("[ENGINE] Loading Unified Engine...")
    active_bot = bot.runner
    bot_mode = "UNIFIED"

# Log Capture Setup
log_capture_string = io.StringIO()
class LogCatcher(object):
    def write(self, data):
        log_capture_string.write(data)
        sys.__stdout__.write(data)
    def flush(self):
        log_capture_string.flush()
        sys.__stdout__.flush()

sys.stdout = LogCatcher()

# Capture logging.* output (RIJIN engine uses logging, not print)
import logging as _logging
_log_handler = _logging.StreamHandler(log_capture_string)
_log_handler.setLevel(_logging.DEBUG)
_log_handler.setFormatter(_logging.Formatter('%(asctime)s - %(message)s'))
_logging.root.addHandler(_log_handler)

# Suppress Flask/Werkzeug request logs from dashboard console
_logging.getLogger('werkzeug').propagate = False
_logging.getLogger('werkzeug').handlers = [_logging.StreamHandler(sys.__stdout__)]

@app.route('/')
def home():
    return render_template('dashboard.html')

@app.route('/login')
def login_zerodha():
    if not API_KEY:
        return "API_KEY not set in .env"
    login_url = kite.login_url()
    return redirect(login_url)

@app.route('/callback')
def callback():
    request_token = request.args.get('request_token')
    if not request_token:
        return "Error: No request_token received."
        
    try:
        data = kite.generate_session(request_token, api_secret=API_SECRET)
        access_token = data['access_token']
        
        # Save to .env
        set_key(".env", "KITE_ACCESS_TOKEN", access_token)
        os.environ["KITE_ACCESS_TOKEN"] = access_token
        
        # Update Bot's Token Global
        if not USE_RIJIN:
            bot.ACCESS_TOKEN = access_token
        
        return redirect(url_for('home'))
        
    except Exception as e:
        return f"Error exchanging token: {e}"

@app.route('/start', methods=['POST'])
def start_bot():
    if not USE_RIJIN:
        # Reload credentials for unified engine
        bot.API_KEY = os.getenv("KITE_API_KEY")
        bot.ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")
    
    if active_bot.start():
        return jsonify({"status": "started", "message": f"{bot_mode} Engine started successfully."})
    return jsonify({"status": "error", "message": "Engine already running."})

@app.route('/stop', methods=['POST'])
def stop_bot():
    active_bot.stop()
    return jsonify({"status": "stopped", "message": "Engine stop signal sent."})

@app.route('/status')
def status():
    # Check if bot thread is alive
    if USE_RIJIN:
        is_running = active_bot.thread and active_bot.thread.is_alive()
    else:
        is_running = active_bot.thread and active_bot.thread.is_alive()
    
    return jsonify({
        "running": bool(is_running),
        "mode": bot_mode
    })

@app.route('/logs')
def logs():
    content = log_capture_string.getvalue()
    return jsonify({"logs": content[-5000:]})

# ===== RIJIN AI-FILTERED ENDPOINTS =====
@app.route('/rijin/stats')
def rijin_stats():
    """Get RIJIN AI-filtered stats"""
    if not USE_RIJIN:
        return jsonify({"error": "RIJIN not enabled"}), 400
    try:
        import rijin_live_runner
        stats = rijin_live_runner.get_live_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== RIJIN v3.0.1 SPECIFIC ENDPOINTS =====
@app.route('/rijin/v3/live-stats')
def rijin_v3_live_stats():
    """Get RIJIN v3.0.1 real-time statistics"""
    if not USE_RIJIN:
        return jsonify({"error": "RIJIN not enabled"}), 400
    
    try:
        import rijin_live_runner
        stats = rijin_live_runner.get_live_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Mode F Integration
from mode_f_engine import ModeFEngine
try:
    from global_market_analyzer import GlobalMarketAnalyzer
except ImportError:
    GlobalMarketAnalyzer = None

# ===== MODE_DON ENDPOINTS =====
if MODE_DON_ENABLED:
    try:
        import mode_don_runner
        print("[MODE_DON] Loaded MODE_DON Engine")
    except ImportError:
        print("[WARN] mode_don_runner not found. MODE_DON disabled.")
        MODE_DON_ENABLED = False

@app.route('/mode-don/start', methods=['POST'])
def start_mode_don():
    if not MODE_DON_ENABLED:
        return jsonify({"status": "error", "message": "MODE_DON not enabled"}), 400
    if mode_don_runner.start():
        return jsonify({"status": "started", "message": "MODE_DON engine started."})
    return jsonify({"status": "error", "message": "MODE_DON already running."})

@app.route('/mode-don/stop', methods=['POST'])
def stop_mode_don():
    if not MODE_DON_ENABLED:
        return jsonify({"status": "error", "message": "MODE_DON not enabled"}), 400
    mode_don_runner.stop()
    return jsonify({"status": "stopped", "message": "MODE_DON stop signal sent."})

@app.route('/mode-don/stats')
def mode_don_stats():
    if not MODE_DON_ENABLED:
        return jsonify({"running": False, "instruments": {}})
    return jsonify(mode_don_runner.get_live_stats())

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"Starting Flask Dashboard")
    print(f"Mode: {bot_mode}")
    if USE_RIJIN:
        print(f"RIJIN v3.0.1 — AI-Filtered Architecture")
    if MODE_DON_ENABLED:
        print(f"MODE_DON — Regime-Gated Breakout Engine")
    print(f"{'='*60}\n")
    
    app.run(host='0.0.0.0', port=5000)
