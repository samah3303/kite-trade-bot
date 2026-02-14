"""
RIJIN v3.0.1 Live Runner - Dashboard Integration Wrapper
Provides thread-based interface for Flask dashboard
"""

import threading
import logging
from datetime import datetime
from rijin_live import RijinLiveEngine

# Global engine instance
_engine = None
_thread = None
_running = False

# Expose stats for dashboard
current_day_type = None
last_day_type_check = None
system_stopped = False
active_trades = {}
daily_pnl_r = 0.0
daily_trades = 0
consecutive_losses = 0
pause_until = None

def update_dashboard_stats():
    """Update global stats from engine for dashboard"""
    global current_day_type, system_stopped, active_trades
    global daily_pnl_r, daily_trades, consecutive_losses, pause_until
    
    if _engine:
        try:
            current_day_type = _engine.day_type_engine.current_day_type
            system_stopped = _engine.system_stop.stopped
            active_trades = {'active': _engine.active_trade} if _engine.active_trade else {}
            daily_pnl_r = _engine.daily_pnl_r
            daily_trades = _engine.daily_trades
            consecutive_losses = _engine.consecutive_losses
            pause_until = _engine.pause_until
        except Exception as e:
            logging.error(f"Error updating dashboard stats: {e}")

def _run_engine():
    """Internal thread function"""
    global _running, _engine
    try:
        _engine = RijinLiveEngine()
        _running = True
        
        # Override run() to update stats periodically
        while _running:
            try:
                _engine.run()
            except KeyboardInterrupt:
                break
            except Exception as e:
                logging.error(f"Engine error: {e}")
                break
    finally:
        _running = False

def start():
    """Start the RIJIN v3.0.1 engine in background thread"""
    global _thread, _running
    
    if _thread and _thread.is_alive():
        return False  # Already running
    
    _thread = threading.Thread(target=_run_engine, daemon=True)
    _thread.start()
    
    # Give it a moment to initialize
    import time
    time.sleep(2)
    
    logging.info("RIJIN v3.0.1 Live Engine started via dashboard")
    return True

def stop():
    """Stop the RIJIN v3.0.1 engine"""
    global _running, _engine
    
    _running = False
    
    if _engine:
        # Engine will stop on next iteration
        pass
    
    logging.info("RIJIN v3.0.1 Live Engine stop signal sent")

# Expose thread for dashboard status check
@property
def thread():
    return _thread

# Compatibility attributes for dashboard
class DummyObject:
    def __init__(self):
        pass

# Create dummy objects to match old interface
day_type_engine = DummyObject()
day_type_engine.day_locked = False

system_stop = DummyObject()
system_stop.stopped = False
system_stop.stop_reason = None
system_stop.consecutive_blocks = 0

opening_impulse = DummyObject()
opening_impulse.total_impulse_count = 0

# Update stats periodically
def get_live_stats():
    """Get current live stats for dashboard"""
    update_dashboard_stats()
    
    return {
        'running': _running,
        'day_type': str(current_day_type.value) if current_day_type else "Unknown",
        'system_stopped': system_stopped,
        'active_trades': len(active_trades),
        'daily_pnl_r': round(daily_pnl_r, 2),
        'daily_trades': daily_trades,
        'consecutive_losses': consecutive_losses,
        'paused': pause_until is not None,
        'pause_until': pause_until.strftime('%H:%M') if pause_until else None,
    }
