"""
RIJIN v3.0.1 Live Runner - Dashboard Integration Wrapper
AI-Filtered Architecture: Signal Engine → AI Validator → Telegram Alert
"""

import threading
import logging
from datetime import datetime
from rijin_live import RijinLiveEngine, send_telegram_message

# Global engine instance
_engine = None
thread = None  # Exposed for app.py: active_bot.thread.is_alive()
_running = False
_stop_event = threading.Event()

# Expose stats for dashboard
active_trades = {}
daily_pnl_r = 0.0
daily_trades = 0

# AI Stats
ai_total_calls = 0
ai_accepts = 0
ai_restricts = 0

def update_dashboard_stats():
    """Update global stats from engine for dashboard"""
    global active_trades, daily_pnl_r, daily_trades
    global ai_total_calls, ai_accepts, ai_restricts
    
    if _engine:
        try:
            active_trades = {'active': _engine.active_trade} if _engine.active_trade else {}
            daily_pnl_r = _engine.daily_pnl_r
            daily_trades = _engine.daily_trades
            ai_total_calls = _engine.ai_total_calls
            ai_accepts = _engine.ai_accepts
            ai_restricts = _engine.ai_restricts
        except Exception as e:
            logging.error(f"Error updating dashboard stats: {e}")

def _run_engine():
    """Internal thread function"""
    global _running, _engine
    try:
        _engine = RijinLiveEngine(stop_event=_stop_event)
        _running = True
        _engine.run()
    except Exception as e:
        error_msg = f"Engine crashed: {e}"
        logging.error(error_msg)
        try:
            send_telegram_message(
                f"🚨 <b>RIJIN ENGINE CRASHED</b>\n\n"
                f"Error: {error_msg}\n\n"
                f"The engine has stopped. Please restart from the dashboard."
            )
        except:
            pass
    finally:
        _running = False

def start():
    """Start the RIJIN v3.0.1 engine in background thread"""
    global thread, _running, _stop_event
    
    if thread and thread.is_alive():
        return False  # Already running
    
    # Reset stop event for new run
    _stop_event = threading.Event()
    
    thread = threading.Thread(target=_run_engine, daemon=True)
    thread.start()
    
    import time
    time.sleep(2)
    
    logging.info("RIJIN v3.0.1 AI-Filtered Live Engine started via dashboard")
    return True

def stop():
    """Stop the RIJIN v3.0.1 engine gracefully"""
    global _running, _engine
    
    _stop_event.set()
    
    if _engine:
        _engine.stop()
    
    _running = False
    logging.info("RIJIN v3.0.1 Live Engine stop signal sent")

# Update stats periodically
def get_live_stats():
    """Get current live stats for dashboard"""
    update_dashboard_stats()
    
    return {
        'running': _running,
        'day_type': "AI-Filtered",
        'phase': "Active" if _running else "Offline",
        'active_trades': len(active_trades),
        'active_trade': active_trades.get('active'),
        'daily_pnl_r': round(daily_pnl_r, 2),
        'daily_trades': daily_trades,
        'consecutive_losses': 0,
        'paused': False,
        'pause_until': None,
        'ai_total_calls': ai_total_calls,
        'ai_accepts': ai_accepts,
        'ai_restricts': ai_restricts,
    }
