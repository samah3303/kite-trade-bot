"""
KiteAlerts V6.0 — Tri-Core Engine Runner
Orchestrates 4 instruments × 3 engines.
Fires dual-profiler alerts to Telegram.
"""

import os
import logging
import threading
import time as _time
from datetime import datetime, timedelta, time as dtime
import pytz
from dotenv import load_dotenv
from kiteconnect import KiteConnect

import config
import indicators as ind
import engine_mode_don
import engine_rijin
import engine_vortex
import day_profiler
import ai_profiler
import telegram_alerts
import token_manager

load_dotenv()

IST = pytz.timezone('Asia/Kolkata')


def now_ist():
    return datetime.now(IST)


class InstrumentState:
    """Per-instrument runtime state."""

    def __init__(self, name, cfg):
        self.name = name
        self.config = cfg
        self.instrument_token = None
        self.active_trade = None
        self.daily_trades = 0
        self.daily_pnl_r = 0.0
        self.consecutive_losses = 0
        self.disabled = False
        self.last_signal_candle = None  # Prevent double-fire on same candle

    def reset_daily(self):
        self.active_trade = None
        self.daily_trades = 0
        self.daily_pnl_r = 0.0
        self.consecutive_losses = 0
        self.disabled = False
        self.last_signal_candle = None


class TriCoreRunner:
    """Main engine loop. Scans all instruments with all 3 engines."""

    def __init__(self, stop_event=None):
        self._stop_event = stop_event or threading.Event()

        # Kite
        self.kite = KiteConnect(api_key=os.getenv("KITE_API_KEY"))
        self.kite.set_access_token(os.getenv("KITE_ACCESS_TOKEN"))

        # Instruments
        self.instruments = {}
        for name, cfg in config.INSTRUMENTS.items():
            self.instruments[name] = InstrumentState(name, cfg)

        # System state
        self.system_pnl_r = 0.0
        self.system_stopped = False
        self.today = None
        self.running = False

    def stop(self):
        self._stop_event.set()

    def _resolve_tokens(self):
        """Resolve Kite instrument tokens for all instruments."""
        try:
            all_instruments = self.kite.instruments()
            for name, inst in self.instruments.items():
                kite_symbol = inst.config["kite_symbol"]
                parts = kite_symbol.split(":")
                if len(parts) != 2:
                    continue
                exchange, tradingsymbol = parts[0], parts[1]
                for ki in all_instruments:
                    if ki["exchange"] == exchange and ki["tradingsymbol"] == tradingsymbol:
                        inst.instrument_token = ki["instrument_token"]
                        logging.info(f"✅ [{name}] Token resolved: {inst.instrument_token}")
                        break
                else:
                    logging.error(f"❌ [{name}] Could not resolve: {kite_symbol}")
        except Exception as e:
            logging.error(f"Token resolution failed: {e}")
            token_manager.handle_api_error(e, "resolve_tokens")

    def _fetch_candles(self, instrument_token, from_time=None):
        """Fetch 5-min candles."""
        try:
            now = now_ist()
            if from_time is None:
                from_time = now.replace(hour=9, minute=0, second=0, microsecond=0)

            data = self.kite.historical_data(
                instrument_token,
                from_time,
                now,
                config.CANDLE_INTERVAL,
            )
            return data
        except Exception as e:
            token_manager.handle_api_error(e, "fetch_candles")
            logging.error(f"Candle fetch error: {e}")
            return []

    def _is_in_window(self, inst, now_time):
        """Check if current time is within instrument's active window."""
        start, end = inst.config["active_window"]
        return start <= now_time <= end

    def _is_inventory_blackout(self, inst, now):
        """Check Crude Oil inventory blackout (Wed 7:45-8:45 PM)."""
        if inst.name != "CRUDEOIL":
            return False
        blackout_day = inst.config.get("inventory_blackout_day")
        if blackout_day is None or now.weekday() != blackout_day:
            return False
        t = now.time()
        return inst.config["inventory_blackout_start"] <= t <= inst.config["inventory_blackout_end"]

    def _get_expiry_warning(self, inst, now):
        """Check if expiry warning should be appended."""
        expiry_day = inst.config.get("expiry_day")
        if expiry_day is None or now.weekday() != expiry_day:
            return None
        warning_after = inst.config.get("expiry_warning_after")
        if warning_after and now.time() >= warning_after:
            return "⚠️ EXPIRY WARNING — Gamma spike risk elevated. Reduce size."
        return None

    def _build_market_snapshot(self, candles, highs, lows, closes, volumes, atr_val, rsi_val, adx_val, vwap_val):
        """Build the JSON snapshot fed to both profilers."""
        price = closes[-1]
        vwap_dist = (price - vwap_val) / vwap_val * 100 if vwap_val > 0 else 0
        session_range = max(highs) - min(lows)

        return {
            "price": round(price, 2),
            "rsi": round(rsi_val, 1),
            "atr": round(atr_val, 2),
            "adx": round(adx_val, 1),
            "vwap": round(vwap_val, 2),
            "vwap_distance_pct": round(vwap_dist, 3),
            "session_range": round(session_range, 2),
            "session_high": round(max(highs), 2),
            "session_low": round(min(lows), 2),
            "candle_count": len(candles),
        }

    def _process_signal(self, inst, signal, candles, highs, lows, closes, volumes, now):
        """Process a signal: run dual profiler → fire Telegram alert."""
        # Indicators for snapshot
        atr_val = ind.atr(highs, lows, closes)[-1]
        rsi_val = ind.rsi(closes)[-1]
        adx_vals = ind.adx(highs, lows, closes)[0]
        adx_val = adx_vals[-1]
        vwap_val = ind.vwap(candles)[-1]

        snapshot = self._build_market_snapshot(
            candles, highs, lows, closes, volumes,
            atr_val, rsi_val, adx_val, vwap_val
        )

        # Math Profiler
        math_profile = day_profiler.classify_day(candles, highs, lows, closes, volumes, now)

        # AI Profiler (async-safe, fail-open)
        ai_profile = ai_profiler.profile_market(snapshot, signal)

        # Expiry warning
        extra = self._get_expiry_warning(inst, now)

        # Fire Telegram
        telegram_alerts.send_signal_alert(
            instrument=inst.config["display_name"],
            engine=signal["engine"],
            direction=signal["direction"],
            entry=signal["entry"],
            sl=signal["sl"],
            target=signal["target"],
            math_profile=math_profile,
            ai_profile=ai_profile,
            extra_info=extra,
        )

        logging.info(
            f"🚨 SIGNAL FIRED: {inst.name} | {signal['engine']} | {signal['direction']} | "
            f"Entry: {signal['entry']} | Math: {math_profile['tag']} | AI: {ai_profile['tag']}"
        )

        # Track (no position management — manual execution)
        inst.daily_trades += 1
        inst.last_signal_candle = candles[-1]['date'] if candles else None

    def run(self):
        """Main engine loop."""
        self.running = True
        logging.info("🚀 KiteAlerts V6.0 Tri-Core Engine starting...")

        # Resolve instrument tokens
        self._resolve_tokens()
        resolved = sum(1 for i in self.instruments.values() if i.instrument_token)
        logging.info(f"📊 Resolved {resolved}/{len(self.instruments)} instruments")

        if resolved == 0:
            logging.error("❌ No instruments resolved. Check token and .env")
            telegram_alerts.send_system_alert(
                "❌ V6.0 FAILED TO START",
                "No instrument tokens could be resolved.\nCheck KITE_ACCESS_TOKEN."
            )
            self.running = False
            return

        telegram_alerts.send_system_alert(
            "🚀 KiteAlerts V6.0 ONLINE",
            f"Tri-Core: MODE_DON · RIJIN · VORTEX\n"
            f"Instruments: {', '.join(n for n, i in self.instruments.items() if i.instrument_token)}\n"
            f"Mode: Manual Execution"
        )

        while not self._stop_event.is_set():
            try:
                now = now_ist()
                current_date = now.date()
                current_time = now.time()

                # Daily reset
                if self.today != current_date:
                    self.today = current_date
                    self.system_pnl_r = 0.0
                    self.system_stopped = False
                    for inst in self.instruments.values():
                        inst.reset_daily()
                    token_manager.reset_daily_alert()
                    logging.info(f"📅 New day: {current_date}")

                # System-level stop
                if self.system_stopped:
                    self._stop_event.wait(60)
                    continue

                # Scan each instrument
                for name, inst in self.instruments.items():
                    if not inst.instrument_token or inst.disabled:
                        continue

                    # Time gate
                    if not self._is_in_window(inst, current_time):
                        continue

                    # Crude oil inventory blackout
                    if self._is_inventory_blackout(inst, now):
                        continue

                    # Fetch candles
                    candles = self._fetch_candles(inst.instrument_token)
                    if len(candles) < config.MIN_CANDLES_REQUIRED:
                        continue

                    # Prevent double-fire on same candle
                    candle_time = candles[-1]['date']
                    if inst.last_signal_candle == candle_time:
                        continue

                    # Extract arrays
                    highs = [float(c['high']) for c in candles]
                    lows = [float(c['low']) for c in candles]
                    closes = [float(c['close']) for c in candles]
                    volumes = [float(c.get('volume', 0) or 0) for c in candles]

                    # Run all 3 engines — first signal wins
                    signal = None

                    # Engine A: MODE_DON
                    signal = engine_mode_don.scan(candles, inst.config)

                    # Engine B: RIJIN
                    if not signal:
                        signal = engine_rijin.scan(candles, inst.config)

                    # Engine C: VORTEX
                    if not signal:
                        signal = engine_vortex.scan(candles, inst.config)

                    # Process signal
                    if signal:
                        self._process_signal(inst, signal, candles, highs, lows, closes, volumes, now)

                # Sleep between scans
                self._stop_event.wait(config.SCAN_INTERVAL_SECONDS)

            except KeyboardInterrupt:
                logging.info("Shutting down...")
                break
            except Exception as e:
                logging.error(f"Main loop error: {e}")
                import traceback
                traceback.print_exc()
                self._stop_event.wait(60)

        self.running = False
        logging.info("🛑 Tri-Core Engine stopped")
        telegram_alerts.send_system_alert("🛑 V6.0 STOPPED", "Engine shut down.")

    def get_stats(self):
        """Dashboard stats."""
        stats = {
            "version": "V6.0",
            "running": self.running,
            "system_pnl_r": self.system_pnl_r,
            "system_stopped": self.system_stopped,
            "instruments": {},
        }
        for name, inst in self.instruments.items():
            stats["instruments"][name] = {
                "display_name": inst.config["display_name"],
                "emoji": inst.config["emoji"],
                "token_resolved": inst.instrument_token is not None,
                "daily_trades": inst.daily_trades,
                "daily_pnl_r": inst.daily_pnl_r,
                "disabled": inst.disabled,
                "active_trade": inst.active_trade is not None,
            }
        return stats

    def refresh_token(self, new_token):
        """Update access token for all Kite connections."""
        self.kite.set_access_token(new_token)
        self._resolve_tokens()
        logging.info("🔑 Token refreshed for all instruments")
