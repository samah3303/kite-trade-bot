"""
RIJIN v3.0.1 - LIVE TRADING ENGINE (AI-FILTERED)
Architecture: Signal Engine (MODE_F) → AI Validator (Gemini) → Telegram Alert

NO gate logic. NO regime downgrades. NO system stops.
AI layer acts as constrained quality filter — ACCEPT or RESTRICT only.

Deploy: python rijin_live.py
"""

import os
import time
import logging
import threading
from datetime import datetime, timedelta, time as dtime
import pytz
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# === IST TIMEZONE (CRITICAL FOR RENDER/UTC SERVERS) ===
IST = pytz.timezone('Asia/Kolkata')

def now_ist():
    """Single source of truth for current IST time."""
    return datetime.now(IST)

# Signal Engine
from mode_f_engine import ModeFEngine

# AI Validator
from gemini_helper import gemini

# Utilities
from unified_engine import (
    simple_ema,
    calculate_rsi,
    calculate_atr,
    send_telegram_message,
)

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# ===================================================================
# CONFIGURATION
# ===================================================================
API_KEY = os.getenv("KITE_API_KEY")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")
NIFTY_INSTRUMENT = os.getenv("NIFTY_INSTRUMENT", "NSE:NIFTY 50")

INITIAL_CAPITAL = 100000  # Rs.1,00,000
RISK_PER_TRADE = 0.01     # 1% = 1R = Rs.1,000

# AI Filter Settings
USE_AI_FILTER = True       # Set False to skip Gemini (all signals ACCEPT)
AI_CALL_DELAY = 2        # Seconds between Groq calls


# ===================================================================
# RIJIN LIVE TRADING ENGINE (AI-FILTERED)
# ===================================================================
class RijinLiveEngine:
    """
    RIJIN v3.0.1 Live Trading Engine — AI-Filtered Architecture
    
    Clean layered flow:
      1. Feature Extraction (EMA, ATR, RSI, VWAP, Slope)
      2. Signal Engine (MODE_F — 3-Gear)
      3. AI Validator (Gemini — ACCEPT/RESTRICT)
      4. Telegram Alert Delivery
    
    No gates. No regime blocks. No mid-session reclassification.
    """
    
    def __init__(self, stop_event=None):
        # Stop event for graceful shutdown
        self._stop_event = stop_event or threading.Event()
        
        # Kite Connection
        self.kite = KiteConnect(api_key=API_KEY)
        self.kite.set_access_token(ACCESS_TOKEN)
        
        # Resolve instrument token ONCE at startup
        self.instrument_token = None
        self._resolve_instrument_token()
        
        # Signal Engine
        self.mode_f_engine = ModeFEngine()
        
        # State
        self.active_trade = None
        self.last_check_time = None
        
        # Error tracking (avoid spamming Telegram)
        self._last_error_msg = None
        self._error_count = 0
        
        # Daily tracking
        self.today = None
        self.daily_trades = 0
        self.daily_pnl_r = 0.0
        
        # AI Stats (daily)
        self.ai_total_calls = 0
        self.ai_accepts = 0
        self.ai_restricts = 0
        self.ai_failures = 0
        
        logging.info("="*60)
        logging.info("RIJIN v3.0.1 - AI-FILTERED LIVE ENGINE")
        logging.info("Signal Engine → AI Validator → Telegram Alert")
        logging.info("="*60)
        logging.info(f"Instrument: {NIFTY_INSTRUMENT}")
        logging.info(f"Instrument Token: {self.instrument_token}")
        logging.info(f"AI Filter: {'ENABLED' if USE_AI_FILTER else 'DISABLED'}")
        logging.info(f"Capital: Rs.{INITIAL_CAPITAL:,}")
        logging.info(f"Risk per trade: {RISK_PER_TRADE*100}% = Rs.{int(INITIAL_CAPITAL*RISK_PER_TRADE):,}")
        logging.info("="*60)
    
    def _resolve_instrument_token(self):
        """Resolve instrument token ONCE at startup"""
        try:
            ltp_data = self.kite.ltp(NIFTY_INSTRUMENT)
            self.instrument_token = ltp_data[NIFTY_INSTRUMENT]['instrument_token']
            logging.info(f"✅ Resolved {NIFTY_INSTRUMENT} → token {self.instrument_token}")
        except Exception as e:
            error_msg = f"❌ Failed to resolve instrument '{NIFTY_INSTRUMENT}': {e}"
            logging.error(error_msg)
            send_telegram_message(
                f"🚨 <b>RIJIN STARTUP ERROR</b>\n\n"
                f"Could not resolve instrument: <code>{NIFTY_INSTRUMENT}</code>\n"
                f"Error: {e}\n\n"
                f"⚠️ The engine will NOT generate signals until this is fixed.\n"
                f"Check NIFTY_INSTRUMENT in .env"
            )
            self.instrument_token = None
    
    def _send_error_telegram(self, error_msg):
        """Send error to Telegram, with dedup to avoid spam"""
        if error_msg == self._last_error_msg:
            self._error_count += 1
            if self._error_count % 10 != 0:
                return
        else:
            self._last_error_msg = error_msg
            self._error_count = 1
        
        send_telegram_message(
            f"⚠️ <b>RIJIN ERROR</b>\n\n"
            f"{error_msg}\n"
            f"{'(repeated ' + str(self._error_count) + ' times)' if self._error_count > 1 else ''}\n"
            f"⏰ {now_ist().strftime('%H:%M:%S')}"
        )
    
    def reset_daily_state(self):
        """Reset state for new trading day"""
        self.today = now_ist().date()
        self.daily_trades = 0
        self.daily_pnl_r = 0.0
        self.ai_total_calls = 0
        self.ai_accepts = 0
        self.ai_restricts = 0
        self.ai_failures = 0
        
        logging.info(f"\n{'='*60}")
        logging.info(f"NEW TRADING DAY: {self.today}")
        logging.info(f"{'='*60}\n")
        
        send_telegram_message(
            f"🟢 <b>RIJIN v3.0.1 AI-FILTERED - NEW DAY</b>\n\n"
            f"📅 Date: {self.today}\n"
            f"💰 Capital: Rs.{INITIAL_CAPITAL:,}\n"
            f"🎯 Risk: Rs.{int(INITIAL_CAPITAL*RISK_PER_TRADE):,} per trade\n"
            f"🤖 AI Filter: {'ENABLED' if USE_AI_FILTER else 'DISABLED'}\n\n"
            f"System active. Monitoring for signals..."
        )
    
    # ---------------------------------------------------------------
    # DATA FETCHING
    # ---------------------------------------------------------------
    
    def fetch_candles_5m(self, limit=100):
        """Fetch latest 5-minute candles from Kite"""
        if not self.instrument_token:
            self._resolve_instrument_token()
            if not self.instrument_token:
                return []
        
        try:
            from_date = now_ist().replace(hour=9, minute=0, second=0, microsecond=0)
            to_date = now_ist()
            
            data = self.kite.historical_data(
                instrument_token=self.instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval="5minute"
            )
            
            if not data:
                logging.warning(f"No candle data returned for {NIFTY_INSTRUMENT}")
            
            return data
        except Exception as e:
            error_msg = f"Candle fetch failed: {e}"
            logging.error(error_msg)
            self._send_error_telegram(error_msg)
            return []
    
    # ---------------------------------------------------------------
    # FEATURE EXTRACTION
    # ---------------------------------------------------------------
    
    def calculate_indicators(self, candles):
        """Calculate EMA, ATR, RSI, Slope"""
        if len(candles) < 30:
            return None
        
        closes = [float(c['close']) for c in candles]
        highs = [float(c['high']) for c in candles]
        lows = [float(c['low']) for c in candles]
        
        ema20 = simple_ema(closes, 20)
        atr = calculate_atr(highs, lows, closes, 14)
        rsi = calculate_rsi(closes, 14)
        
        if len(ema20) == 0 or len(atr) == 0 or len(rsi) == 0:
            return None
        
        slope = 0.0
        if len(ema20) >= 4:
            slope = float(ema20[-1]) - float(ema20[-4])
        
        return {
            'ema20': float(ema20[-1]),
            'atr': float(atr[-1]),
            'rsi': float(rsi[-1]),
            'slope': slope,
        }
    
    def calculate_vwap(self, candles):
        """Volume-weighted average price for the session"""
        try:
            total_vol = sum(c.get('volume', 1) for c in candles)
            if total_vol == 0:
                return float(candles[-1]['close'])
            vwap = sum(
                ((float(c['high']) + float(c['low']) + float(c['close'])) / 3) * c.get('volume', 1)
                for c in candles
            ) / total_vol
            return vwap
        except:
            return float(candles[-1]['close'])
    
    def build_market_context(self, candles, indicators):
        """Build market context JSON for AI evaluation"""
        now = now_ist()
        price = float(candles[-1]['close'])
        vwap = self.calculate_vwap(candles)

        # Session extremes
        session_high = max(float(c['high']) for c in candles)
        session_low = min(float(c['low']) for c in candles)

        # Time context
        time_str = now.strftime('%H:%M')
        market_open = now.replace(hour=9, minute=15, second=0)
        minutes_since_open = int((now - market_open).total_seconds() / 60)

        # Session phase
        if minutes_since_open < 30:
            session_phase = "Opening"
        elif minutes_since_open < 90:
            session_phase = "Morning"
        elif minutes_since_open < 210:
            session_phase = "Midday"
        elif minutes_since_open < 300:
            session_phase = "Afternoon"
        else:
            session_phase = "Closing"

        # Trend detection
        slope = indicators['slope']
        if slope > 5:
            trend = "Bullish"
        elif slope < -5:
            trend = "Bearish"
        else:
            trend = "Sideways"

        # Day type
        session_range = session_high - session_low
        atr = indicators['atr']
        range_vs_atr = session_range / atr if atr > 0 else 0

        if range_vs_atr > 2.0 and trend == "Bullish":
            day_type = "Bullish Expansion"
        elif range_vs_atr > 2.0 and trend == "Bearish":
            day_type = "Bearish Expansion"
        elif range_vs_atr > 1.5:
            day_type = "Trending"
        elif range_vs_atr > 0.8:
            day_type = "Normal Range"
        else:
            day_type = "Narrow Range"

        # VWAP distance %
        price_vs_vwap_pct = ((price - vwap) / vwap * 100) if vwap > 0 else 0

        # Distance from session extremes
        distance_from_low_pct = ((price - session_low) / session_low * 100) if session_low > 0 else 0
        distance_from_high_pct = ((session_high - price) / session_high * 100) if session_high > 0 else 0

        # RSI slope
        rsi = indicators['rsi']
        if len(candles) >= 4:
            closes_3ago = [float(c['close']) for c in candles[:-3]]
            rsi_3ago_list = calculate_rsi(closes_3ago, 14)
            rsi_3ago = float(rsi_3ago_list[-1]) if len(rsi_3ago_list) > 0 else rsi
            rsi_diff = rsi - rsi_3ago
            if rsi_diff > 3:
                rsi_slope = "Rising"
            elif rsi_diff < -3:
                rsi_slope = "Falling"
            else:
                rsi_slope = "Flat"
        else:
            rsi_slope = "Flat"

        # Expansion legs
        expansion_legs = self._count_expansion_legs(candles)
        avg_leg_size = self._avg_leg_size(candles)
        current_leg = self._current_leg_size(candles)
        current_leg_vs_avg = round(current_leg / avg_leg_size, 1) if avg_leg_size > 0 else 1.0

        # Volatility state
        atr_pct = (atr / price * 100) if price > 0 else 0
        if atr_pct < 0.10:
            volatility_state = "Contracting"
        elif atr_pct < 0.25:
            volatility_state = "Normal"
        else:
            volatility_state = "Expanding"

        # Structure
        structure_last_5 = self._detect_structure(candles[-5:] if len(candles) >= 5 else candles)

        # Pullback depth
        pullback_depth_pct = self._calculate_pullback_depth(candles)

        # Volume vs average
        if len(candles) >= 20:
            recent_vol = sum(c.get('volume', 0) for c in candles[-3:]) / 3
            avg_vol = sum(c.get('volume', 0) for c in candles[-20:]) / 20
            volume_vs_avg = round(recent_vol / avg_vol, 1) if avg_vol > 0 else 1.0
        else:
            volume_vs_avg = 1.0

        return {
            "time": time_str,
            "minutes_since_open": minutes_since_open,
            "session_phase": session_phase,
            "day_type": day_type,
            "trend": trend,
            "price_vs_vwap_pct": round(price_vs_vwap_pct, 2),
            "distance_from_session_low_pct": round(distance_from_low_pct, 2),
            "distance_from_session_high_pct": round(distance_from_high_pct, 2),
            "rsi": round(rsi, 0),
            "rsi_slope": rsi_slope,
            "expansion_legs": expansion_legs,
            "current_leg_vs_avg": current_leg_vs_avg,
            "volatility_state": volatility_state,
            "structure_last_5": structure_last_5,
            "pullback_depth_pct": pullback_depth_pct,
            "volume_vs_avg": volume_vs_avg,
        }

    # ---------------------------------------------------------------
    # MARKET STRUCTURE HELPERS
    # ---------------------------------------------------------------

    def _count_expansion_legs(self, candles):
        """Count directional expansion legs"""
        if len(candles) < 3:
            return 0
        legs = 0
        prev_dir = None
        for i in range(1, len(candles)):
            c = float(candles[i]['close'])
            o = float(candles[i]['open'])
            curr_dir = "UP" if c > o else "DOWN"
            if curr_dir != prev_dir and prev_dir is not None:
                legs += 1
            prev_dir = curr_dir
        return max(1, legs)

    def _avg_leg_size(self, candles):
        """Average leg size in points"""
        if len(candles) < 3:
            return 1.0
        legs = []
        leg_start = float(candles[0]['close'])
        prev_dir = None
        for i in range(1, len(candles)):
            c = float(candles[i]['close'])
            o = float(candles[i]['open'])
            curr_dir = "UP" if c > o else "DOWN"
            if curr_dir != prev_dir and prev_dir is not None:
                legs.append(abs(c - leg_start))
                leg_start = c
            prev_dir = curr_dir
        if legs:
            return sum(legs) / len(legs)
        return abs(float(candles[-1]['close']) - float(candles[0]['close'])) or 1.0

    def _current_leg_size(self, candles):
        """Size of the current directional leg"""
        if len(candles) < 3:
            return 0.0
        last_dir = "UP" if float(candles[-1]['close']) > float(candles[-1]['open']) else "DOWN"
        leg_start_price = float(candles[-1]['close'])
        for i in range(len(candles) - 2, -1, -1):
            c = float(candles[i]['close'])
            o = float(candles[i]['open'])
            curr_dir = "UP" if c > o else "DOWN"
            if curr_dir != last_dir:
                break
            leg_start_price = c
        return abs(float(candles[-1]['close']) - leg_start_price)

    def _detect_structure(self, candles):
        """Detect price structure from last N candles"""
        if len(candles) < 3:
            return "Insufficient data"
        highs = [float(c['high']) for c in candles]
        lows = [float(c['low']) for c in candles]

        hh = all(highs[i] >= highs[i-1] for i in range(1, len(highs)))
        hl = all(lows[i] >= lows[i-1] for i in range(1, len(lows)))
        lh = all(highs[i] <= highs[i-1] for i in range(1, len(highs)))
        ll = all(lows[i] <= lows[i-1] for i in range(1, len(lows)))

        if hh and hl:
            return "HH-HL continuation"
        elif lh and ll:
            return "LH-LL continuation"
        elif hh and ll:
            return "Expanding range"
        elif lh and hl:
            return "Contracting range"
        elif hh:
            return "Higher highs"
        elif ll:
            return "Lower lows"
        else:
            return "Choppy / No structure"

    def _calculate_pullback_depth(self, candles):
        """Pullback depth as % of last swing"""
        if len(candles) < 10:
            return 0
        recent = candles[-20:] if len(candles) >= 20 else candles
        swing_high = max(float(c['high']) for c in recent)
        swing_low = min(float(c['low']) for c in recent)
        swing_range = swing_high - swing_low
        if swing_range == 0:
            return 0
        current_price = float(candles[-1]['close'])
        if current_price > (swing_high + swing_low) / 2:
            pullback = swing_high - current_price
        else:
            pullback = current_price - swing_low
        return round((pullback / swing_range) * 100)

    # ---------------------------------------------------------------
    # SIGNAL ENGINE
    # ---------------------------------------------------------------
    
    def generate_signal(self, candles, indicators):
        """Generate MODE_F signal"""
        try:
            res = self.mode_f_engine.predict(candles, global_bias="NEUTRAL")
            
            if res.valid:
                return {
                    'mode': 'MODE_F',
                    'direction': res.direction,
                    'entry': res.entry,
                    'sl': res.sl,
                    'target': res.target,
                    'gear': res.gear.name,
                    'rsi': indicators['rsi'],
                    'atr': indicators['atr'],
                }
            
            return None
        except Exception as e:
            logging.error(f"Signal generation error: {e}")
            return None
    
    # ---------------------------------------------------------------
    # AI VALIDATION LAYER
    # ---------------------------------------------------------------
    
    def validate_signal_with_ai(self, market_context, signal):
        """
        Send signal to Gemini AI for ACCEPT/RESTRICT decision.
        Falls back to ACCEPT on any failure.
        """
        if not USE_AI_FILTER:
            return {"decision": "ACCEPT", "confidence": 100, "reasons": ["AI filter disabled"]}

        # Build signal in standard format
        risk = abs(signal['entry'] - signal['sl'])
        reward = abs(signal['target'] - signal['entry'])
        rr_ratio = f"1:{reward / risk:.0f}" if risk > 0 else "1:0"

        signal_data = {
            "direction": "SHORT" if signal['direction'] == 'SELL' else "LONG",
            "entry": signal['entry'],
            "sl": signal['sl'],
            "rr": rr_ratio,
        }

        self.ai_total_calls += 1

        result = gemini.evaluate_trade_quality(market_context, signal_data)

        if result is None:
            self.ai_failures += 1
            return {"decision": "ACCEPT", "confidence": 50, "reasons": ["AI unavailable — defaulting to ACCEPT"]}

        if result['decision'] == 'ACCEPT':
            self.ai_accepts += 1
        else:
            self.ai_restricts += 1

        time.sleep(AI_CALL_DELAY)
        return result
    
    # ---------------------------------------------------------------
    # TRADE MANAGEMENT
    # ---------------------------------------------------------------
    
    def execute_trade(self, signal, ai_result):
        """Send trade alert to Telegram (no broker execution)"""
        risk = abs(signal['entry'] - signal['sl'])
        quantity = int((INITIAL_CAPITAL * RISK_PER_TRADE) / risk) if risk > 0 else 0
        direction_label = "SHORT" if signal['direction'] == 'SELL' else "LONG"
        
        reward = abs(signal['target'] - signal['entry'])
        rr_ratio = f"1:{reward / risk:.0f}" if risk > 0 else "1:0"
        
        logging.info(f"\n{'='*60}")
        logging.info(f"📊 SIGNAL ACCEPTED BY AI")
        logging.info(f"{'='*60}")
        logging.info(f"Direction: {direction_label}")
        logging.info(f"Entry: {signal['entry']}  SL: {signal['sl']}  RR: {rr_ratio}")
        logging.info(f"AI: {ai_result['decision']} ({ai_result['confidence']}%)")
        logging.info(f"{'='*60}\n")
        
        # Send Telegram alert
        reasons_text = ''.join('• ' + r + '\n' for r in ai_result['reasons'][:3])
        send_telegram_message(
            f"🎯 <b>RIJIN SIGNAL — AI ACCEPTED</b>\n\n"
            f"📅 {now_ist().strftime('%d %b %Y')} | ⏰ {now_ist().strftime('%H:%M:%S')}\n\n"
            f"📍 Direction: <b>{direction_label}</b>\n"
            f"💵 Entry: {signal['entry']}\n"
            f"🛑 SL: {signal['sl']}\n"
            f"🎯 Target: {signal['target']}\n"
            f"📊 RR: {rr_ratio}\n"
            f"📦 Qty: {quantity}\n"
            f"💰 Risk: Rs.{int(INITIAL_CAPITAL * RISK_PER_TRADE):,}\n\n"
            f"🤖 <b>AI: {ai_result['decision']}</b> ({ai_result['confidence']}%)\n"
            f"{reasons_text}\n"
            f"📈 RSI: {signal['rsi']:.1f} | ATR: {signal['atr']:.1f}"
        )
        
        # Store active trade for monitoring
        self.active_trade = {
            **signal,
            'entry_time': now_ist(),
            'quantity': quantity,
            'ai_decision': ai_result['decision'],
            'ai_confidence': ai_result['confidence'],
        }
        
        self.daily_trades += 1
    
    def check_active_trade_exit(self, current_price):
        """Monitor active trade for exit"""
        if not self.active_trade:
            return
        
        trade = self.active_trade
        direction = trade['direction']
        sl = trade['sl']
        target = trade['target']
        
        exit_type = None
        exit_price = None
        
        if direction == 'BUY':
            if current_price >= target:
                exit_type = 'TARGET'
                exit_price = target
            elif current_price <= sl:
                exit_type = 'SL'
                exit_price = sl
        else:
            if current_price <= target:
                exit_type = 'TARGET'
                exit_price = target
            elif current_price >= sl:
                exit_type = 'SL'
                exit_price = sl
        
        if exit_type:
            self.close_trade(exit_type, exit_price)
    
    def close_trade(self, exit_type, exit_price):
        """Close active trade and send Telegram alert"""
        trade = self.active_trade
        entry = trade['entry']
        sl = trade['sl']
        direction = trade['direction']
        
        # Calculate P&L
        risk = abs(entry - sl)
        pnl = (exit_price - entry) if direction == 'BUY' else (entry - exit_price)
        pnl_r = pnl / risk if risk > 0 else 0
        
        self.daily_pnl_r += pnl_r
        
        direction_label = "SHORT" if direction == 'SELL' else "LONG"
        
        logging.info(f"\n{'='*60}")
        logging.info(f"TRADE CLOSED: {exit_type}")
        logging.info(f"{'='*60}")
        logging.info(f"Entry: {entry}  Exit: {exit_price}")
        logging.info(f"P&L: {pnl_r:+.2f}R  Daily: {self.daily_pnl_r:+.2f}R")
        logging.info(f"{'='*60}\n")
        
        # Send Telegram
        emoji = "✅" if exit_type == 'TARGET' else "❌"
        send_telegram_message(
            f"{emoji} <b>TRADE CLOSED: {exit_type}</b>\n\n"
            f"📅 {now_ist().strftime('%d %b %Y')} | ⏰ {now_ist().strftime('%H:%M:%S')}\n\n"
            f"📍 {direction_label}\n"
            f"💵 Entry: {entry} → Exit: {exit_price}\n"
            f"💰 P&L: <b>{pnl_r:+.2f}R</b>\n"
            f"📊 Daily P&L: {self.daily_pnl_r:+.2f}R\n"
            f"🔢 Daily Trades: {self.daily_trades}\n\n"
            f"🤖 AI was: {trade.get('ai_decision', 'N/A')} ({trade.get('ai_confidence', 'N/A')}%)"
        )
        
        self.active_trade = None
    
    def stop(self):
        """Signal the engine to stop gracefully"""
        self._stop_event.set()
    
    # ---------------------------------------------------------------
    # MAIN TRADING LOOP
    # ---------------------------------------------------------------
    
    def run(self):
        """Main trading loop — clean layered architecture"""
        logging.info("Starting RIJIN v3.0.1 AI-Filtered Live Engine...\n")
        
        # Startup health check
        if not self.instrument_token:
            send_telegram_message(
                "🚨 <b>RIJIN v3.0.1 FAILED TO START</b>\n\n"
                f"Instrument token could not be resolved for: <code>{NIFTY_INSTRUMENT}</code>\n"
                f"Check .env KITE_ACCESS_TOKEN and NIFTY_INSTRUMENT"
            )
            return
        
        send_telegram_message(
            f"🚀 <b>RIJIN v3.0.1 AI-FILTERED STARTED</b>\n\n"
            f"📊 Instrument: <code>{NIFTY_INSTRUMENT}</code>\n"
            f"🔑 Token: {self.instrument_token}\n"
            f"🤖 AI Filter: <b>{'ENABLED' if USE_AI_FILTER else 'DISABLED'}</b>\n"
            f"💰 Capital: Rs.{INITIAL_CAPITAL:,}\n\n"
            f"Signal Engine → AI Validator → Telegram Alert"
        )
        
        while not self._stop_event.is_set():
            try:
                now = now_ist()
                current_time = now.time()
                
                # Reset daily state if new day
                if self.today != now.date():
                    self.reset_daily_state()
                
                # Trading hours check
                if not (dtime(9, 15) <= current_time <= dtime(15, 30)):
                    self._stop_event.wait(60)
                    continue
                
                # Fetch candles
                candles = self.fetch_candles_5m()
                if len(candles) < 30:
                    self._stop_event.wait(30)
                    continue
                
                # === STALE DATA REJECTION ===
                try:
                    last_candle_time = candles[-1]['date']
                    if isinstance(last_candle_time, datetime):
                        if last_candle_time.tzinfo is None:
                            last_candle_time = IST.localize(last_candle_time)
                        candle_age_seconds = (now - last_candle_time).total_seconds()
                        if candle_age_seconds > 420:  # 7 minutes
                            logging.warning(
                                f"Stale data: last candle {candle_age_seconds/60:.1f}m old. Skipping."
                            )
                            self._stop_event.wait(60)
                            continue
                except Exception as e:
                    logging.warning(f"Stale data check failed: {e}")
                
                # ===== LAYER 1: FEATURE EXTRACTION =====
                indicators = self.calculate_indicators(candles)
                if not indicators:
                    self._stop_event.wait(30)
                    continue
                
                # Check active trade exit
                if self.active_trade:
                    current_price = float(candles[-1]['close'])
                    self.check_active_trade_exit(current_price)
                    self._stop_event.wait(10)
                    continue
                
                # ===== LAYER 2: SIGNAL ENGINE =====
                # Only check every 5 minutes (one per candle)
                if not self.last_check_time or (now - self.last_check_time).total_seconds() >= 300:
                    signal = self.generate_signal(candles, indicators)
                    
                    if signal:
                        # Build market context
                        market_context = self.build_market_context(candles, indicators)
                        
                        # ===== LAYER 3: AI VALIDATOR =====
                        ai_result = self.validate_signal_with_ai(market_context, signal)
                        
                        if ai_result['decision'] == 'ACCEPT':
                            # ===== LAYER 4: TELEGRAM ALERT =====
                            logging.info(f"✅ AI ACCEPTED: {ai_result['confidence']}% confidence")
                            self.execute_trade(signal, ai_result)
                        else:
                            # AI RESTRICTED — send alert
                            direction_label = "SHORT" if signal['direction'] == 'SELL' else "LONG"
                            logging.info(
                                f"⚠️ AI RESTRICTED: {direction_label} | "
                                f"Confidence: {ai_result['confidence']}% | "
                                f"{'; '.join(ai_result['reasons'][:2])}"
                            )
                            
                            reasons_text = ''.join('• ' + r + '\n' for r in ai_result['reasons'][:3])
                            send_telegram_message(
                                f"⚠️ <b>SIGNAL RESTRICTED BY AI</b>\n\n"
                                f"📅 {now.strftime('%d %b %Y')} | ⏰ {now.strftime('%H:%M:%S')}\n\n"
                                f"📍 {direction_label} ({signal.get('gear', 'N/A')})\n"
                                f"💵 Entry: {signal['entry']} | SL: {signal['sl']}\n\n"
                                f"🤖 <b>AI: RESTRICT</b> ({ai_result['confidence']}%)\n"
                                f"{reasons_text}"
                            )
                    
                    self.last_check_time = now
                
                # Sleep before next iteration
                self._stop_event.wait(30)
            
            except KeyboardInterrupt:
                logging.info("\nShutting down RIJIN engine...")
                send_telegram_message("🛑 <b>RIJIN STOPPED</b>\n\nEngine shut down by user.")
                break
            
            except Exception as e:
                error_msg = f"Main loop error: {e}"
                logging.error(error_msg)
                self._send_error_telegram(error_msg)
                self._stop_event.wait(60)
        
        # End of day summary
        if self.daily_trades > 0:
            send_telegram_message(
                f"📊 <b>RIJIN END OF DAY</b>\n\n"
                f"📅 {self.today}\n"
                f"🔢 Trades: {self.daily_trades}\n"
                f"💰 P&L: <b>{self.daily_pnl_r:+.2f}R</b>\n\n"
                f"🤖 AI Stats:\n"
                f"• Accepted: {self.ai_accepts}\n"
                f"• Restricted: {self.ai_restricts}\n"
                f"• Failures: {self.ai_failures}"
            )
        
        logging.info("RIJIN engine stopped.")
        send_telegram_message("🛑 <b>RIJIN STOPPED</b>\n\nEngine shut down.")


# ===================================================================
# MAIN
# ===================================================================
if __name__ == "__main__":
    engine = RijinLiveEngine()
    engine.run()
