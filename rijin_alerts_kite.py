
import os
import time
import json
import logging
import argparse
import requests
import traceback
import numpy as np
from datetime import datetime, timedelta
from enum import Enum
from kiteconnect import KiteConnect
from dotenv import load_dotenv

# -------------------------------------------------------------------
# Configuration & Constants
# -------------------------------------------------------------------
load_dotenv()

API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TG_BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

INSTRUMENT = "MCX:GOLDGUINEA26MARFUT" 

TIMEFRAME_TREND = "30minute" 
TIMEFRAME_ENTRY = "5minute"

# -------------------------------------------------------------------
# Data Models
# -------------------------------------------------------------------
class TrendState(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

class LegState(Enum):
    INITIAL = "INITIAL"
    NEW = "NEW"                 
    CONFIRMED = "CONFIRMED"     
    EXHAUSTED = "EXHAUSTED"     

# -------------------------------------------------------------------
# Indicators & Utils
# -------------------------------------------------------------------
def simple_ema(data, period):
    if len(data) == 0: return []
    ema = np.zeros(len(data))
    ema[0] = data[0]
    alpha = 2 / (period + 1)
    for i in range(1, len(data)):
        ema[i] = (data[i] * alpha) + (ema[i-1] * (1 - alpha))
    return ema

def calculate_rsi(data, period=14):
    if len(data) < period + 1: return np.zeros(len(data))
    data = np.array(data)
    deltas = np.diff(data)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    if down == 0: return np.zeros(len(data))
    rs = up / down
    rsi = np.zeros(len(data))
    rsi[:period] = 100. - 100. / (1. + rs)
    
    avg_up = up
    avg_down = down
    for i in range(period, len(data)):
        delta = data[i] - data[i-1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta
        avg_up = (avg_up * (period - 1) + upval) / period
        avg_down = (avg_down * (period - 1) + downval) / period
        rs = avg_up / avg_down if avg_down != 0 else 0
        rsi[i] = 100. - 100. / (1. + rs)
    return rsi

def calculate_atr(highs, lows, closes, period=14):
    if len(closes) < period: return np.zeros(len(closes))
    tr_values = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        h = highs[i]
        l = lows[i]
        pc = closes[i-1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_values.append(tr)
    return simple_ema(tr_values, period)

def get_slope(series, lookback=3):
    if len(series) < lookback + 1: return 0.0
    val = series[-1] - series[-lookback-1]
    return float(val)

def detect_patterns(candles, ema20, atr):
    # Returns list of strings: ["Inside Bar", "Impulse", "EMA Touch", "Consolidation"]
    patterns = []
    if len(candles) < 3: return patterns
    
    c = candles[-1]
    prev = candles[-2]
    
    c_h, c_l = float(c['high']), float(c['low'])
    p_h, p_l = float(prev['high']), float(prev['low'])
    e20 = float(ema20[-1])
    cur_atr = float(atr[-1])
    
    # 1. Inside Bar
    if c_h < p_h and c_l > p_l:
        patterns.append("Inside Bar")
        
    # 2. Impulse (Large Body)
    body = abs(float(c['close']) - float(c['open']))
    if body > (0.6 * cur_atr):
        patterns.append("Impulse")
        
    # 3. EMA Touch
    if c_l <= e20 <= c_h:
        patterns.append("EMA Touch")
        
    # 4. Consolidation (Last 3 candles small bodies)
    try:
        bodies = [abs(float(x['close'])-float(x['open'])) for x in candles[-3:]]
        if all(b < (0.4 * cur_atr) for b in bodies):
            patterns.append("Consolidation")
    except: pass
    
    return patterns

# -------------------------------------------------------------------
# Telegram Utils
# -------------------------------------------------------------------
def send_telegram_message(message):
    try:
        url = f"{TG_BASE_URL}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"E: Telegram Send Failed: {e}")

def format_telegram_msg(res):
    # EXIT Message
    if res.get('signal') == "EXIT":
        msg = f"""
<b>🚫 TRADE CLOSED</b>
RESULT: {res['exit_type']}
EXIT PRICE: {res['price']}
ENTRY PRICE: {res['entry_price']}
POINTS: {res['price'] - res['entry_price']:.1f}
DATE: {res['date']}
"""
        return msg.strip()

    # ENTRY Message
    msg = f"""
<b>MODE: {res['mode']}</b>
TYPE: {res['signal']}
SYMBOL: GOLD GUINEA
ENTRY: {res['price']}
SL: {res['sl']:.1f}
TARGET: {res['target']:.1f}
TIMEFRAME: 5m
RSI: {res['rsi']:.1f}
ATR: {res['atr']:.1f}
PATTERN: {res['pattern']}
"""
    return msg.strip()

# -------------------------------------------------------------------
# Market Engine
# -------------------------------------------------------------------
class MarketAnalyzer:
    def __init__(self):
        self.leg_state = LegState.INITIAL
        self.current_trend = TrendState.NEUTRAL
        self.last_trade_index = -999 
        self.trend_duration = 0 
        self.avg_30m_slope = 0
        
        # Risk / Kill Switch
        self.daily_pnl_r = 0.0
        self.consecutive_losses = 0
        self.last_trade_day = None

    def update_trend_30m(self, c30):
        try:
            if len(c30) < 55: return TrendState.NEUTRAL
            
            closes = [float(x['close']) for x in c30]
            ema20 = simple_ema(closes, 20)
            ema50 = simple_ema(closes, 50)
            
            e20_slope = get_slope(ema20)
            e50_slope = get_slope(ema50)
            
            # Slope Avg for Mode C
            slopes_hist = [abs(float(ema20[-(i+1)] - ema20[-(i+4)])) for i in range(20)]
            self.avg_30m_slope = sum(slopes_hist)/len(slopes_hist) if slopes_hist else 1.0

            P = closes[-1]
            E20 = float(ema20[-1])
            E50 = float(ema50[-1])
            
            new_trend = TrendState.NEUTRAL
            
            if P > E20 > E50 and e20_slope > 0:
                new_trend = TrendState.BULLISH
            elif P < E20 < E50 and e20_slope < 0:
                new_trend = TrendState.BEARISH
            
            # State Transitions
            if new_trend != self.current_trend:
                # Full Reset
                self.current_trend = new_trend
                # If Trend defined -> NEW, else INITIAL
                self.leg_state = LegState.NEW if new_trend != TrendState.NEUTRAL else LegState.INITIAL
                self.trend_duration = 0
            else:
                self.trend_duration += 1
                # Auto-confirm after duration
                if self.leg_state == LegState.NEW and self.trend_duration > 10:
                    self.leg_state = LegState.CONFIRMED
                    
            return new_trend
        except Exception:
            return TrendState.NEUTRAL

    def analyze_5m(self, c5, c30_trend, i_idx):
        try:
            if not c5 or len(c5) < 30: return None
            
            c = c5[-1]
            P = float(c['close'])
            h_curr = float(c['high'])
            l_curr = float(c['low'])
            curr_date = c['date']
            
            # Daily Reset for Kill Switch
            current_day = curr_date.date()
            if self.last_trade_day != current_day:
                self.daily_pnl_r = 0.0
                self.consecutive_losses = 0
                self.last_trade_day = current_day
            
            # ---------------------------------------------------
            # 1. MANAGE ACTIVE TRADE (Exit Detection)
            # ---------------------------------------------------
            if hasattr(self, 'active_trade') and self.active_trade:
                trade = self.active_trade
                
                # Check Exit
                exit_type = None
                exit_price = 0.0
                pnl_r = 0.0
                
                if trade['signal'] == "BUY":
                    if l_curr <= trade['sl']:
                        exit_type = "SL HIT"
                        exit_price = trade['sl']
                        pnl_r = -1.0 # Approx
                    elif h_curr >= trade['target']:
                        exit_type = "TARGET HIT"
                        exit_price = trade['target']
                        pnl_r = 1.0 # Approx
                        
                elif trade['signal'] == "SELL":
                    if h_curr >= trade['sl']:
                        exit_type = "SL HIT"
                        exit_price = trade['sl']
                        pnl_r = -1.0
                    elif l_curr <= trade['target']:
                        exit_type = "TARGET HIT"
                        exit_price = trade['target']
                        pnl_r = 1.0

                if exit_type:
                    # Update Stats for Kill Switch using simplistic R
                    self.daily_pnl_r += pnl_r
                    if pnl_r < 0:
                        self.consecutive_losses += 1
                    else:
                        self.consecutive_losses = 0 # Reset on win? Or strict? 
                        # Usually strict consecutive losses refers to losing streak. Win breaks it.
                    
                    self.active_trade = None # Clear trade
                    
                    return {
                        "signal": "EXIT",
                        "mode": trade['mode'],
                        "exit_type": exit_type,
                        "price": exit_price,
                        "entry_price": trade['price'],
                        "date": curr_date,
                        "pattern": "N/A",
                        "rsi": 0, "atr": 0, "sl": 0, "target": 0 # Fillers
                    }
                    
                return None # Trade active, no new signals

            # ---------------------------------------------------
            # 2. SCAN FOR NEW ENTRIES
            # ---------------------------------------------------
            
            closes = [float(x['close']) for x in c5]
            highs = [float(x['high']) for x in c5]
            lows = [float(x['low']) for x in c5]
            vols = [float(x['volume']) for x in c5]
            
            ema20 = simple_ema(closes, 20)
            ema50 = simple_ema(closes, 50)
            atr = calculate_atr(highs, lows, closes, 14)
            atr_ma = simple_ema(atr, 20)
            rsi = calculate_rsi(closes, 14)
            vol_ma = simple_ema(vols, 20)
            
            O = float(c['open'])
            E20 = float(ema20[-1])
            E50 = float(ema50[-1])
            ATR = float(atr[-1])
            RSI = float(rsi[-1])
            
            # Kill Switch Check
            kill_switch = False
            if self.daily_pnl_r <= -2.0 or self.consecutive_losses >= 3:
                kill_switch = True # Mode C disabled
            
            # Cooldown
            if (i_idx - self.last_trade_index) < 3: return None
            
            # Session Filter (14:00 - 23:30)
            h, m = c['date'].hour, c['date'].minute
            t_val = h * 100 + m
            if not (1400 <= t_val <= 2330): return None
            
            # Inputs
            signal = None
            mode = None
            ptrns = detect_patterns(c5, ema20, atr)
            ptrn_str = ", ".join(ptrns) if ptrns else "None"
            
            high_vol = ATR > (1.1 * float(atr_ma[-1]))
            
            # Slope check for Mode C
            local_slope = abs(get_slope(ema20))
            momentum_ok = local_slope > self.avg_30m_slope
            
            # ... (Logic identical to previous, just wrapped) ...
            # To minimize diff complexity, I will copy the logic block but carefully.
            
            # --------------------- BULLISH ---------------------
            if c30_trend == TrendState.BULLISH:
                if self.leg_state == LegState.NEW:
                    recent_closes = closes[-11:-1]
                    recent_emas = ema20[-11:-1]
                    count_above = sum(1 for k in range(len(recent_closes)) if recent_closes[k] > recent_emas[k])
                    
                    if count_above <= 3 and P > E20:
                        if 55 <= RSI <= 68:
                            signal = "BUY"
                            mode = "Mode A"
                            self.leg_state = LegState.CONFIRMED
                            
                elif self.leg_state == LegState.CONFIRMED:
                    mode_b_valid = False
                    dist_ema = P - E20
                    is_pullback = (0.25 * ATR) <= abs(dist_ema) <= (0.8 * ATR)
                    
                    if (is_pullback and P > E20) or \
                       ("EMA Touch" in ptrns and P > E20) or \
                       ("Consolidation" in ptrn_str and P > max([float(x['high']) for x in c5[-4:-1]])):
                        mode_b_valid = True
                        
                    if mode_b_valid and 45 <= RSI <= 62:
                        signal = "BUY"
                        mode = "Mode B"
                    
                    if not signal and high_vol and momentum_ok and not kill_switch:
                        mode_c_valid = False
                        if "Inside Bar" in ptrns and P > float(c5[-2]['high']): mode_c_valid = True
                        if "Impulse" in ptrns and P > E20: mode_c_valid = True
                        if "Consolidation" in ptrns and P > E20: mode_c_valid = True
                        
                        if mode_c_valid and 40 <= RSI <= 60:
                            signal = "BUY"
                            mode = "Mode C"
                            
            # --------------------- BEARISH ---------------------
            elif c30_trend == TrendState.BEARISH:
                if self.leg_state == LegState.NEW:
                    recent_closes = closes[-11:-1]
                    recent_emas = ema20[-11:-1]
                    count_below = sum(1 for k in range(len(recent_closes)) if recent_closes[k] < recent_emas[k])
                    
                    if count_below <= 3 and P < E20:
                        if 32 <= RSI <= 45:
                            signal = "SELL"
                            mode = "Mode A"
                            self.leg_state = LegState.CONFIRMED
                            
                elif self.leg_state == LegState.CONFIRMED:
                    mode_b_valid = False
                    dist_ema = E20 - P
                    is_pullback = (0.25 * ATR) <= abs(dist_ema) <= (0.8 * ATR)
                    
                    if (is_pullback and P < E20) or \
                       ("EMA Touch" in ptrns and P < E20) or \
                       ("Consolidation" in ptrn_str and P < min([float(x['low']) for x in c5[-4:-1]])):
                        mode_b_valid = True
                        
                    if mode_b_valid and 38 <= RSI <= 55:
                        signal = "SELL"
                        mode = "Mode B"
                        
                    if not signal and high_vol and momentum_ok and not kill_switch:
                        mode_c_valid = False
                        if "Inside Bar" in ptrns and P < float(c5[-2]['low']): mode_c_valid = True
                        if "Impulse" in ptrns and P < E20: mode_c_valid = True
                        if "Consolidation" in ptrns and P < E20: mode_c_valid = True
                        
                        if mode_c_valid and 40 <= RSI <= 60:
                            signal = "SELL"
                            mode = "Mode C"
            
            if signal:
                self.last_trade_index = i_idx
                sl = 0.0
                tp = 0.0
                
                if mode == "Mode C":
                    risk = 0.6 * ATR
                    if signal == "BUY":
                        sl = P - risk
                        tp = P + (1.0 * risk)
                    else:
                        sl = P + risk
                        tp = P - (1.0 * risk)
                else:
                    risk = 2.0 * ATR
                    if signal == "BUY":
                         sl = P - risk
                         tp = P + (2.0 * risk)
                    else:
                         sl = P + risk
                         tp = P - (2.0 * risk)
                         
                # Save Active Trade
                self.active_trade = {
                    "signal": signal,
                    "mode": mode,
                    "price": P,
                    "sl": sl,
                    "target": tp,
                    "rsi": RSI,
                    "atr": ATR,
                    "pattern": ptrn_str,
                    "date": c['date']
                }
                
                return {
                    "signal": signal, # BUY/SELL
                    "mode": mode,
                    "price": P,
                    "high": float(c['high']),
                    "low": float(c['low']),
                    "sl": sl,
                    "target": tp,
                    "rsi": RSI,
                    "atr": ATR,
                    "pattern": ptrn_str,
                    "date": c['date']
                }
            return None
        except Exception:
            traceback.print_exc()
            return None

# -------------------------------------------------------------------
# Control & Globals
# -------------------------------------------------------------------
import threading
STOP_EVENT = threading.Event()
BOT_THREAD = None

def start_bot_thread():
    global BOT_THREAD
    if BOT_THREAD and BOT_THREAD.is_alive():
        return False # Already running
    
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_live_mode)
    BOT_THREAD.daemon = True
    BOT_THREAD.start()
    return True

def stop_bot_thread():
    STOP_EVENT.set()
    if BOT_THREAD:
        BOT_THREAD.join(timeout=2)
    return True

# -------------------------------------------------------------------
# Live Trading Loop
# -------------------------------------------------------------------
def run_live_mode():
    print(f"🚀 STARTING LIVE ALGO FOR {INSTRUMENT}")
    
    if not API_KEY or not ACCESS_TOKEN:
        print("❌ Error: Credentials missing in .env")
        return
        
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)
    
    analyzer = MarketAnalyzer()
    last_processed_time = None
    
    # Initial Data Fetch
    try:
        tok = kite.quote([INSTRUMENT])[INSTRUMENT]['instrument_token']
        print(f"Instrument Token: {tok}")
    except Exception as e:
        print(f"❌ Error getting token: {e}")
        return

    while not STOP_EVENT.is_set():
        try:
            # UTC Fix: Render/Cloud runs on UTC. Force IST time (UTC+5:30)
            now_utc = datetime.utcnow()
            now_ist = now_utc + timedelta(hours=5, minutes=30)
            
            # Using now_ist ensures we request data up to current India time
            now = now_ist 
            start = now - timedelta(days=5)
            end = now
            
            c5 = kite.historical_data(tok, start, end, interval="5minute")
            
            if not c5:
                print("No data received.")
                time.sleep(10)
                continue
                
            last_candle = c5[-1]
            last_candle_time = last_candle['date']
            
            if last_processed_time != last_candle_time:
                print(f"⚡ Analyzing Candle: {last_candle_time}")
                
                c30_acc = []
                curr_30 = None
                
                # ... Build 30m ...
                for c in c5:
                    dt = c['date']
                    if dt.minute % 30 == 0 and dt.second == 0:
                        if curr_30: c30_acc.append(curr_30)
                        curr_30 = {'date':dt, 'open':c['open'], 'high':c['high'], 'low':c['low'], 'close':c['close'], 'volume':c['volume']}
                    else:
                        if curr_30:
                            curr_30['high'] = max(curr_30['high'], c['high'])
                            curr_30['low'] = min(curr_30['low'], c['low'])
                            curr_30['close'] = c['close']
                            curr_30['volume'] += c['volume']
                        else: curr_30 = c.copy()
                            
                trend = analyzer.update_trend_30m(c30_acc)
                res = analyzer.analyze_5m(c5, trend, len(c5))
                
                if res:
                    msg = format_telegram_msg(res)
                    print(f"\n🔔 SIGNAL GENERATED: {res['signal']} {res.get('mode', '')}")
                    print(msg)
                    send_telegram_message(msg)
                
                last_processed_time = last_candle_time
            else:
                pass # Heartbeat silent to avoid spamming logs in UI
                
            time.sleep(5) 
            
        except Exception as e:
            print(f"❌ Loop Error: {e}")
            time.sleep(10)
    
    print("🛑 Bot Stopped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--backtest', action='store_true')
    args = parser.parse_args()
    
    if args.backtest:
        run_backtest()
    else:
        # If run directly without args, default to live mode
        run_live_mode()
