"""
MODE_DON Runner — Thread wrapper for dashboard integration.
Same pattern as rijin_live_runner.py.
"""

import threading
import logging
from datetime import datetime
from mode_don_engine import ModeDonEngine
from unified_engine import send_telegram_message

# Global state
_engine = None
thread = None
_running = False
_stop_event = threading.Event()


def _run_engine():
    """Internal thread function."""
    global _running, _engine
    try:
        _engine = ModeDonEngine(stop_event=_stop_event)
        _running = True
        _engine.run()
    except Exception as e:
        error_msg = f"MODE_DON crashed: {e}"
        logging.error(error_msg)
        try:
            send_telegram_message(
                f"🚨 <b>MODE_DON ENGINE CRASHED</b>\n\n"
                f"Error: {error_msg}\n\n"
                f"Please restart from the dashboard."
            )
        except:
            pass
    finally:
        _running = False


def start():
    """Start MODE_DON engine in background thread."""
    global thread, _running, _stop_event

    if thread and thread.is_alive():
        return False  # Already running

    _stop_event = threading.Event()
    thread = threading.Thread(target=_run_engine, daemon=True)
    thread.start()

    import time
    time.sleep(2)

    logging.info("MODE_DON engine started via dashboard")
    return True


def stop():
    """Stop MODE_DON engine gracefully."""
    global _running, _engine

    _stop_event.set()
    if _engine:
        _engine.stop()

    _running = False
    logging.info("MODE_DON engine stop signal sent")


def get_live_stats():
    """Get current stats for dashboard."""
    if _engine and _running:
        try:
            stats = _engine.get_stats()
            stats['running'] = _running
            return stats
        except Exception as e:
            logging.error(f"MODE_DON stats error: {e}")

    return {
        'running': _running,
        'system_pnl_r': 0.0,
        'system_stopped': False,
        'regime_computed': False,
        'instruments': {},
        'active_trades': 0,
    }
