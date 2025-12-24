import os
from flask import Flask, render_template, jsonify, Response, request, redirect, session, url_for
import sys
import time
import io
import threading
from dotenv import load_dotenv, set_key
from kiteconnect import KiteConnect
import unified_engine as bot

load_dotenv()

app = Flask(__name__)
app.secret_key = 'some_random_secret_key' # Needed for session

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

if __name__ == "__main__":
    print("starting web server on port 5000")
    app.run(host='0.0.0.0', port=5000)
