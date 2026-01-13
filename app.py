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
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback_dev_secret_key") # Needed for session

# Globals
API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
# We use the bot's globals usually, but let's re-init kite here for login flow
kite = KiteConnect(api_key=API_KEY)

# Log Capture Setup
log_capture_string = io.StringIO()
class LogCatcher(object):
    def write(self, data):
        log_capture_string.write(data)
        sys.__stdout__.write(data) # Mirror to terminal
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

@app.route('/callback') # Ensure Zerodha App Dashboard has this as Redirect URI
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
        bot.ACCESS_TOKEN = access_token
        
        return redirect(url_for('home'))
        
    except Exception as e:
        return f"Error exchanging token: {e}"

@app.route('/start', methods=['POST'])
def start_bot():
    # Reload credentials just in case
    bot.API_KEY = os.getenv("KITE_API_KEY")
    bot.ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")
    
    if bot.runner.start():
        return jsonify({"status": "started", "message": "Unified Engine started successfully."})
    return jsonify({"status": "error", "message": "Engine already running."})

@app.route('/stop', methods=['POST'])
def stop_bot():
    bot.runner.stop()
    return jsonify({"status": "stopped", "message": "Engine stop signal sent."})

@app.route('/status')
def status():
    # Check if bot thread is alive
    is_running = bot.runner.thread and bot.runner.thread.is_alive()
    return jsonify({"running": bool(is_running)})

@app.route('/logs')
def logs():
    # Return last 2000 chars of logs
    content = log_capture_string.getvalue()
    return jsonify({"logs": content[-5000:]})

# Mode F Integration
from mode_f_engine import ModeFEngine
try:
    from global_market_analyzer import GlobalMarketAnalyzer
except ImportError:
    GlobalMarketAnalyzer = None

@app.route('/predict', methods=['POST'])
def predict_mode_f():
    # 1. Check Credentials
    API_KEY = os.getenv("KITE_API_KEY")
    ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN") # Use updated token
    
    if not API_KEY or not ACCESS_TOKEN:
        return jsonify({"valid": False, "message": "Credentials missing. Login first."})
        
    try:
        # 2. Connect
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(ACCESS_TOKEN)
        
        # 3. Global Context
        global_bias = "NEUTRAL"
        if GlobalMarketAnalyzer:
            gmam = GlobalMarketAnalyzer()
            # Fast check? or Full Fetch? Full fetch might take 2-3s
            gmam.fetch_global_data() 
            gmam.calculate_bias()
            global_bias = gmam.bias.value
            
        # 4. Nifty Data
        NIFTY_INSTRUMENT = os.getenv("NIFTY_INSTRUMENT", "NSE:NIFTY 50")
        q = kite.quote(NIFTY_INSTRUMENT)
        token = q[NIFTY_INSTRUMENT]['instrument_token']
        
        to_date = datetime.now()
        from_date = to_date - timedelta(days=7)
        candles = kite.historical_data(token, from_date, to_date, "5minute")
        
        # 5. Run Mode F
        engine = ModeFEngine()
        res = engine.predict(candles, global_bias=global_bias)
        
        return jsonify({
            "valid": True,
            "decision": "VALID" if res.valid else "INVALID",
            "direction": res.direction,
            "reason": res.reason if not res.valid else res.narrative,
            "details": {
                "volatility": res.vol_state.name,
                "structure": res.struct_state.name,
                "entry": res.entry,
                "sl": res.sl,
                "target": res.target,
                "global_bias": global_bias
            }
        })
        
    except Exception as e:
        return jsonify({"valid": False, "message": f"Error: {str(e)}"})

if __name__ == "__main__":
    print("starting web server on port 5000")
    app.run(host='0.0.0.0', port=5000)
