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

# ===== RIJIN-SPECIFIC ENDPOINTS =====
@app.route('/rijin/day-type')
def rijin_day_type():
    """Get current day type (RIJIN only)"""
    if not USE_RIJIN:
        return jsonify({"error": "RIJIN not enabled"}), 400
    
    return jsonify({
        "day_type": active_bot.current_day_type.value if hasattr(active_bot, 'current_day_type') else "Unknown",
        "last_check": active_bot.last_day_type_check.isoformat() if hasattr(active_bot, 'last_day_type_check') and active_bot.last_day_type_check else None,
        "locked": active_bot.day_type_engine.day_locked if hasattr(active_bot, 'day_type_engine') else False,
    })

@app.route('/rijin/stats')
def rijin_stats():
    """Get RIJIN system statistics"""
    if not USE_RIJIN:
        return jsonify({"error": "RIJIN not enabled"}), 400
    
    stats = {
        "system_stopped": active_bot.system_stop.stopped if hasattr(active_bot, 'system_stop') else False,
        "stop_reason": active_bot.system_stop.stop_reason if hasattr(active_bot, 'system_stop') else None,
        "consecutive_blocks": active_bot.system_stop.consecutive_blocks if hasattr(active_bot, 'system_stop') else 0,
        "active_trades": len(active_bot.active_trades) if hasattr(active_bot, 'active_trades') else 0,
        "opening_impulse_fired": active_bot.opening_impulse.total_impulse_count if hasattr(active_bot, 'opening_impulse') else 0,
    }
    
    return jsonify(stats)

@app.route('/rijin/config')
def rijin_config():
    """Get RIJIN configuration"""
    if not USE_RIJIN:
        return jsonify({"error": "RIJIN not enabled"}), 400
    
    from rijin_config import (
        EXECUTION_GATES,
        OPENING_IMPULSE_CONFIG,
        CORRELATION_BRAKE_CONFIG,
        SYSTEM_STOP_TRIGGERS,
    )
    
    return jsonify({
        "execution_gates": EXECUTION_GATES,
        "opening_impulse": {
            "time_start": str(OPENING_IMPULSE_CONFIG['time_start']),
            "time_end": str(OPENING_IMPULSE_CONFIG['time_end']),
            "min_move_atr": OPENING_IMPULSE_CONFIG['min_move_atr_multiple'],
            "max_trades": OPENING_IMPULSE_CONFIG['max_trades_per_index'],
        },
        "correlation_brake": CORRELATION_BRAKE_CONFIG,
        "system_stop": SYSTEM_STOP_TRIGGERS,
    })

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

@app.route('/rijin/v3/backtest-results')
def rijin_v3_backtest():
    """Get RIJIN v3.0.1 backtest results summary"""
    return jsonify({
        "period": "67 days (Nov 20, 2025 - Feb 14, 2026)",
        "total_trades": 67,
        "win_rate": 56.72,
        "total_pnl_r": 17.98,
        "avg_win_r": 1.24,
        "avg_loss_r": -1.00,
        "worst_day_r": -2.00,
        "best_day_r": 5.96,
        "bad_days": 9,
        "consecutive_loss_pauses": 15,
        "status": "PRODUCTION READY"
    })

# Mode F Integration
from mode_f_engine import ModeFEngine
try:
    from global_market_analyzer import GlobalMarketAnalyzer
except ImportError:
    GlobalMarketAnalyzer = None

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"Starting Flask Dashboard")
    print(f"Mode: {bot_mode}")
    if USE_RIJIN:
        print(f"RIJIN SYSTEM v3.0.1 - Impulse-Based Timing")
    print(f"{'='*60}\n")
    
    app.run(host='0.0.0.0', port=5000)
