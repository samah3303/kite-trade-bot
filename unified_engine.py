import os
import time
import json
import logging
import argparse
import requests
import traceback
import threading
import numpy as np
from datetime import datetime, timedelta, time as dtime
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

# Default Instruments
NIFTY_INSTRUMENT = os.getenv("NIFTY_INSTRUMENT", "NFO:NIFTY25JANFUT")
GOLD_INSTRUMENT = "MCX:GOLDGUINEA26MARFUT"

# -------------------------------------------------------------------
# Data Models and Utils
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
    if c_h < p_h and c_l > p_l: patterns.append("Inside Bar")
        
    # 2. Impulse (Large Body)
    body = abs(float(c['close']) - float(c['open']))
    if body > (0.6 * cur_atr): patterns.append("Impulse")
        
    # 3. EMA Touch
    if c_l <= e20 <= c_h: patterns.append("EMA Touch")
        
    # 4. Consolidation (Last 3 candles small bodies)
    try:
        bodies = [abs(float(x['close'])-float(x['open'])) for x in candles[-3:]]
        if all(b < (0.4 * cur_atr) for b in bodies): patterns.append("Consolidation")
    except: pass
    
    return patterns

def send_telegram_message(message):
    try:
        url = f"{TG_BASE_URL}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"E: Telegram Send Failed: {e}")

# -------------------------------------------------------------------
# STRATEGY 1: NIFTY (Strict Mode A/B/C)
# -------------------------------------------------------------------
class NiftyStrategy:
    def __init__(self):
        self.leg_state = LegState.INITIAL
        self.current_trend = TrendState.NEUTRAL
        self.candles_since_new = 0
        self.daily_trades = 0
        self.daily_pnl_r = 0.0
        self.mode_c_losses = 0
        self.last_trade_day = None
        self.mode_a_fired = False
        self.mode_b_fired = False
        self.avg_30m_slope = 0.0
        self.avg_5m_slope = 0.0

    def reset_daily_stats_if_new_day(self, current_date):
        if self.last_trade_day != current_date.date():
            self.daily_trades = 0
            self.daily_pnl_r = 0.0
            self.mode_c_losses = 0
            self.last_trade_day = current_date.date()
            self.mode_a_fired = False
            self.mode_b_fired = False
            self.leg_state = LegState.INITIAL
            print(f"🔄 NIFTY DAILY RESET: {self.last_trade_day}")

    def update_trend_30m(self, c30):
        try:
            # print("DEBUG: Patched update_trend_30m running") 
            if len(c30) < 55: return TrendState.NEUTRAL, 0
            
            closes = [float(x['close']) for x in c30]
            ema20 = simple_ema(closes, 20)
            ema50 = simple_ema(closes, 50)
            atr = calculate_atr([float(x['high']) for x in c30], [float(x['low']) for x in c30], closes, 14)
            atr_ma20 = simple_ema(atr, 20)
            slope = get_slope(ema20)
            
            slopes_hist = [abs(float(ema20[-(i+1)] - ema20[-(i+4)])) for i in range(20)]
            self.avg_30m_slope = sum(slopes_hist)/len(slopes_hist) if slopes_hist else 1.0

            P = closes[-1]
            E20 = float(ema20[-1])
            E50 = float(ema50[-1])
            ATR = float(atr[-1])
            ATR_MA = float(atr_ma20[-1])
            
            new_trend = TrendState.NEUTRAL
            if (P > E20 > E50) and (slope > 0) and (ATR > ATR_MA): new_trend = TrendState.BULLISH
            elif (P < E20 < E50) and (slope < 0) and (ATR > ATR_MA): new_trend = TrendState.BEARISH
            
            if new_trend != self.current_trend:
                self.current_trend = new_trend
                self.leg_state = LegState.NEW if new_trend != TrendState.NEUTRAL else LegState.INITIAL
                self.candles_since_new = 0
                self.mode_a_fired = False
                self.mode_b_fired = False
            else:
                if self.leg_state == LegState.NEW:
                    self.candles_since_new += 1
                    if self.candles_since_new >= 10: self.leg_state = LegState.CONFIRMED
            
            return new_trend, slope
        except: 
            return TrendState.NEUTRAL, 0

    def analyze_5m(self, c5, c30_trend, c30_ema20_slope, instrument_name):
        try:
            if not c5 or len(c5) < 30: return None
            c = c5[-1]
            closes = [float(x['close']) for x in c5]
            highs = [float(x['high']) for x in c5]
            lows = [float(x['low']) for x in c5]
            ema20 = simple_ema(closes, 20)
            atr = calculate_atr(highs, lows, closes, 14)
            atr_ma = simple_ema(atr, 20)
            rsi = calculate_rsi(closes, 14)
            slope_5m = get_slope(ema20)
            
            slopes_hist = [abs(float(ema20[-(i+1)] - ema20[-(i+4)])) for i in range(20)]
            self.avg_5m_slope = sum(slopes_hist)/len(slopes_hist) if slopes_hist else 1.0

            P, H, L, O = float(c['close']), float(c['high']), float(c['low']), float(c['open'])
            E20, ATR, RSI = float(ema20[-1]), float(atr[-1]), float(rsi[-1])
            CURR_DATE = c['date']
            
            self.reset_daily_stats_if_new_day(CURR_DATE)
            
            # Global Filters
            t_now = CURR_DATE.time()
            if not (dtime(9, 30) <= t_now <= dtime(15, 15)): return None
            # Fix 5: Early Mode C enablement - reduce slope strictness or rely on logic below?
            # User said "Enable Mode C as soon as Slope > 0 and Price > EMA20 for 3 candles". 
            # This implies we might skip "avg_30m_slope * 0.8" check? No, user said "EMA slope filters... keeping you alive". 
            # "Enable Mode C as soon as..." likely means don't wait for "CONFIRMED" state if slope is good?
            # Let's keep global slope check but relax LegState inside Mode C block.
            
            if abs(c30_ema20_slope) < (self.avg_30m_slope * 0.8): return None
            
            # Fix 7: Daily Limit 7
            if self.daily_trades >= 7 or self.daily_pnl_r <= -1.5 or ATR < 5.0: return None

            signal, mode, pattern, sl_val, tp_val = None, None, None, 0.0, "TRAIL"
            is_bullish = c30_trend == TrendState.BULLISH
            is_bearish = c30_trend == TrendState.BEARISH
            
            # Helper for Early Mode C (Fix 6)
            # If 30m Trend is Neutral, but local structure is waking up
            if c30_trend == TrendState.NEUTRAL:
                 if slope_5m > 0 and P > E20: is_bullish = True # Local Bullish Override
                 elif slope_5m < 0 and P < E20: is_bearish = True # Local Bearish Override
            
            # --------------------------
            # Fix 6: Opening Range Break (ORB)
            # --------------------------
            # 09:30 - 10:30 only
            if dtime(9, 30) <= t_now <= dtime(10, 30):
                # Calc OR (First 3 candles: 9:15, 9:20, 9:25)
                # Ensure we have data for today
                todays_candles = [x for x in c5 if x['date'].date() == CURR_DATE.date()]
                if len(todays_candles) >= 4: # Need at least 3 closed candles (idx 0,1,2) + current (idx 3)
                    or_high = max(x['high'] for x in todays_candles[:3])
                    or_low = min(x['low'] for x in todays_candles[:3])
                    
                    if is_bullish and P > or_high and P > O: # Breakout
                         # Retest? User said "Break + retest OR clean break".
                         # Let's assume clean break for now to ensure calls.
                         signal, mode, pattern, sl_val = "BUY", "MODE_C", "ORB Breakout", P - (0.5*ATR) # Tight SL for ORB?
                         tp_val = str(round(P + (1.5*(P-sl_val)), 2))
                    elif is_bearish and P < or_low and P < O:
                         signal, mode, pattern, sl_val = "SELL", "MODE_C", "ORB Breakdown", P + (0.5*ATR)
                         tp_val = str(round(P - (1.2*(sl_val-P)), 2))

            # --------------------------
            # Mode A (Fresh Trend)
            # --------------------------
            # Keep Fix 1.0 logic as base, but ensure it doesn't conflict
            if not signal and self.leg_state == LegState.NEW and not self.mode_a_fired:
                check_range = 10; valid_freshness = False
                if is_bullish:
                    count_above = sum(1 for i in range(len(closes[-check_range-1:-1])) if closes[-check_range-1+i] > ema20[-check_range-1+i])
                    count_below = sum(1 for i in range(len(closes[-check_range-1:-1])) if closes[-check_range-1+i] < ema20[-check_range-1+i])
                    if count_above <= 3 and count_below >= 1: valid_freshness = True
                    if valid_freshness and P > E20 and (abs(P-O)/(H-L) if (H-L)>0 else 0) >= 0.60 and 56 <= RSI <= 72:
                        signal, mode, pattern, sl_val = "BUY", "MODE_A", "Fresh Trend Reclaim", P - (1.2 * ATR)
                        self.mode_a_fired = True; self.leg_state = LegState.CONFIRMED
                elif is_bearish:
                    count_below = sum(1 for i in range(len(closes[-check_range-1:-1])) if closes[-check_range-1+i] < ema20[-check_range-1+i])
                    count_above = sum(1 for i in range(len(closes[-check_range-1:-1])) if closes[-check_range-1+i] > ema20[-check_range-1+i])
                    if count_below <= 3 and count_above >= 1: valid_freshness = True
                    if valid_freshness and P < E20 and (abs(P-O)/(H-L) if (H-L)>0 else 0) >= 0.60 and 28 <= RSI <= 44:
                        signal, mode, pattern, sl_val = "SELL", "MODE_A", "Fresh Trend Reclaim", P + (1.2 * ATR)
                        self.mode_a_fired = True; self.leg_state = LegState.CONFIRMED

            # --------------------------
            # Mode B (Pullback) - Fix 1, 2, 3
            # --------------------------
            # Fix 1: Re-entry allowed if 5 candles passed since last Mode B?
            # Or just remove single-fire check? "Allow Mode B re-entry every 5 candles"
            # We need a last_mode_b_time check.
            can_fire_b = False
            if self.leg_state == LegState.CONFIRMED:
                 if not hasattr(self, 'last_mode_b_idx'): self.last_mode_b_idx = -999
                 # Current index? analyze_5m doesn't receive 'i' in Nifty call usually, checking signature...
                 # It receives 'c5'. We can rely on len(c5) or just trust time?
                 # unified_engine.py passes c5_subset.
                 curr_idx = len(c5)
                 if (curr_idx - self.last_mode_b_idx) >= 2: can_fire_b = True

            if not signal and can_fire_b:
                pb_depth_ok = False
                time_pb_ok = False
                hold_bo_ok = False
                
                if is_bullish:
                    if P > E20:
                        dist = max(highs[-20:-1]) - min(lows[-5:])
                        # Fix 3: Lower Depth 0.05 ATR
                        if (0.05 * ATR) <= dist <= (0.5 * ATR): pb_depth_ok = True
                        
                        # Fix 2: Time-Based (+/- 0.3 ATR for 3-6 candles)
                        # Check last 4 candles deviation < 0.3 ATR
                        devs = [abs(closes[-i] - ema20[-i]) for i in range(1, 5)]
                        if all(d < (0.3 * ATR) for d in devs): time_pb_ok = True
                        
                        # EMA20 Hold BO (Keep existing)
                        if all(closes[-i] > ema20[-i] for i in range(1, 6)):
                            if P > max(highs[-4:-1]): hold_bo_ok = True

                        is_rejection = ((P - L) > (H - P) * 2) or (P > highs[-2] and closes[-2] < float(ema20[-2])) or hold_bo_ok or time_pb_ok
                        
                        if (pb_depth_ok or time_pb_ok or hold_bo_ok) and is_rejection and 52 <= RSI <= 65:
                            signal, mode, pattern, sl_val = "BUY", "MODE_B", "Pullback Rejection", P - (1.0 * ATR)
                            tp_val = str(round(P + (1.5*(P-sl_val)), 2))
                            # Removed "EXHAUSTED" transition
                            self.last_mode_b_idx = len(c5)
                            
                elif is_bearish:
                    if P < E20:
                        dist = max(highs[-5:]) - min(lows[-20:-1])
                        # Fix 3: Lower Depth
                        if (0.05 * ATR) <= dist <= (0.5 * ATR): pb_depth_ok = True
                        
                        # Fix 2: Time-Based
                        devs = [abs(closes[-i] - ema20[-i]) for i in range(1, 5)]
                        if all(d < (0.3 * ATR) for d in devs): time_pb_ok = True
                        
                        # EMA20 Hold BO
                        if all(closes[-i] < ema20[-i] for i in range(1, 6)):
                             if P < min(lows[-4:-1]): hold_bo_ok = True

                        is_rejection = ((H - P) > (P - L) * 2) or (P < lows[-2] and closes[-2] > float(ema20[-2])) or hold_bo_ok or time_pb_ok
                        
                        if (pb_depth_ok or time_pb_ok or hold_bo_ok) and is_rejection and 35 <= RSI <= 48:
                            signal, mode, pattern, sl_val = "SELL", "MODE_B", "Pullback Rejection", P + (1.0 * ATR)
                            tp_val = str(round(P - (1.5*(sl_val-P)), 2))
                            self.last_mode_b_idx = len(c5)

            # --------------------------
            # Mode C (Breakout/Mom) - Fix 4, 5, 8
            # --------------------------
            # Fix 6: Early Mode C (Slope + 3 candles)
            mode_c_allowed = (self.leg_state == LegState.CONFIRMED)
            # Early enable logic:
            if not mode_c_allowed and self.leg_state == LegState.NEW:
                 if is_bullish and all(closes[-i] > ema20[-i] for i in range(1, 4)): mode_c_allowed = True
                 elif is_bearish and all(closes[-i] < ema20[-i] for i in range(1, 4)): mode_c_allowed = True

            if not signal and mode_c_allowed and self.mode_c_losses < 2:
                # Fix 5: Micro Range Breakout (Range < 0.6 ATR for last 5)
                # Check range
                rng_last_5 = max(highs[-5:]) - min(lows[-5:])
                micro_range_ok = (rng_last_5 < (0.6 * ATR))
                
                # Fix 8: Midday Compression (12:00-13:30)
                # Relaxed logic: If Midday, allow 0.7 ATR range.
                midday_time = (dtime(12, 0) <= t_now <= dtime(13, 30))
                midday_range_ok = (rng_last_5 < (0.7 * ATR))
                midday_ok = midday_time and midday_range_ok
                
                # Standard Mode C Volatility check trigger OR Micro Range trigger
                vol_ok = (ATR > (0.95 * float(atr_ma[-1])) and abs(slope_5m) > (self.avg_5m_slope * 1.2))
                
                if vol_ok or micro_range_ok or midday_ok:
                    c_valid = False; c_pattern = ""
                    if is_bullish:
                        if L <= E20 <= H and P > E20 and P > O: c_valid, c_pattern = True, "EMA Touch"
                        if highs[-2] < highs[-3] and lows[-2] > lows[-3] and P > highs[-2]: c_valid, c_pattern = True, "Inside Bar Break"
                        if micro_range_ok and P > max(highs[-5:-1]): c_valid, c_pattern = True, "Micro Range Break"
                        
                        # Fix 4: RSI 45-68
                        if c_valid and 45 <= RSI <= 68:
                            signal, mode, pattern, sl_val = "BUY", "MODE_C", c_pattern, P - (0.8 * ATR)
                            tp_val = str(round(P + (1.2 * (P-sl_val)), 2))
                    elif is_bearish:
                        if L <= E20 <= H and P < E20 and P < O: c_valid, c_pattern = True, "EMA Touch"
                        if highs[-2] < highs[-3] and lows[-2] > lows[-3] and P < lows[-2]: c_valid, c_pattern = True, "Inside Bar Break"
                        if micro_range_ok and P < min(lows[-5:-1]): c_valid, c_pattern = True, "Micro Range Break"
                        
                        # Fix 4: RSI Inv
                        if c_valid and 32 <= RSI <= 55:
                            signal, mode, pattern, sl_val = "SELL", "MODE_C", c_pattern, P + (0.8 * ATR)
                            tp_val = str(round(P - (1.2 * (sl_val-P)), 2))

            if signal:
                self.daily_trades += 1
                return {
                    "instrument": instrument_name,
                    "mode": mode,
                    "direction": signal,
                    "entry": P, "sl": sl_val, "target": tp_val,
                    "pattern": pattern, "rsi": RSI, "atr": ATR,
                    "trend_state": c30_trend.name, "time": str(CURR_DATE)
                }
            return None
        except: traceback.print_exc(); return None

# -------------------------------------------------------------------
# STRATEGY 2: GOLD GUINEA (Original Logic)
# -------------------------------------------------------------------
class GoldStrategy:
    def __init__(self):
        self.leg_state = LegState.INITIAL
        self.current_trend = TrendState.NEUTRAL
        self.last_trade_index = -999 
        self.trend_duration = 0 
        self.avg_30m_slope = 0
        self.active_trade = None

    def update_trend_30m(self, c30):
        try:
            if len(c30) < 55: return TrendState.NEUTRAL
            closes = [float(x['close']) for x in c30]
            ema20 = simple_ema(closes, 20)
            ema50 = simple_ema(closes, 50)
            
            slope = get_slope(ema20)
            slopes_hist = [abs(float(ema20[-(i+1)] - ema20[-(i+4)])) for i in range(20)]
            self.avg_30m_slope = sum(slopes_hist)/len(slopes_hist) if slopes_hist else 1.0

            P, E20, E50 = closes[-1], float(ema20[-1]), float(ema50[-1])
            new_trend = TrendState.NEUTRAL
            if P > E20 > E50 and slope > 0: new_trend = TrendState.BULLISH
            elif P < E20 < E50 and slope < 0: new_trend = TrendState.BEARISH
            
            if new_trend != self.current_trend:
                self.current_trend = new_trend
                self.leg_state = LegState.NEW if new_trend != TrendState.NEUTRAL else LegState.INITIAL
                self.trend_duration = 0
            else:
                self.trend_duration += 1
                if self.leg_state == LegState.NEW and self.trend_duration > 10: self.leg_state = LegState.CONFIRMED
            return new_trend
        except: return TrendState.NEUTRAL

    def analyze_5m(self, c5, c30_trend, instrument_name, i_idx):
        try:
            if not c5 or len(c5) < 30: return None
            c = c5[-1]
            closes = [float(x['close']) for x in c5]
            highs = [float(x['high']) for x in c5]
            lows = [float(x['low']) for x in c5]
            
            ema20 = simple_ema(closes, 20)
            atr = calculate_atr(highs, lows, closes, 14)
            atr_ma = simple_ema(atr, 20)
            rsi = calculate_rsi(closes, 14)
            
            P, E20, ATR, RSI = float(c['close']), float(ema20[-1]), float(atr[-1]), float(rsi[-1])
            curr_date = c['date']
            
            # 1. Exit Logic
            if self.active_trade:
                trade = self.active_trade
                exit_type = None
                if trade['direction'] == "BUY":
                    if float(c['low']) <= trade['sl']: exit_type = "SL HIT"
                    elif float(c['high']) >= trade['target']: exit_type = "TARGET HIT"
                elif trade['direction'] == "SELL":
                    if float(c['high']) >= trade['sl']: exit_type = "SL HIT"
                    elif float(c['low']) <= trade['target']: exit_type = "TARGET HIT"
                
                if exit_type:
                    self.active_trade = None
                    return {
                        "instrument": instrument_name, "mode": trade['mode'],
                        "direction": "EXIT", "entry": trade['entry'], "exit_type": exit_type,
                        "time": str(curr_date), "sl": 0, "target": 0, "rsi": 0, "atr": 0, "pattern": "N/A" # Filler
                    }
                return None

            # 2. Entry Logic
            if (i_idx - self.last_trade_index) < 3: return None
            h, m = c['date'].hour, c['date'].minute
            if not (1400 <= (h*100+m) <= 2330): return None
            
            signal, mode = None, None
            ptrns = detect_patterns(c5, ema20, atr)
            local_slope = abs(get_slope(ema20))
            momentum_ok = local_slope > self.avg_30m_slope
            
            # Simple Original Logic Ported
            is_pullback = (0.25 * ATR) <= abs(P - E20) <= (0.8 * ATR)
            
            if c30_trend == TrendState.BULLISH:
                if self.leg_state == LegState.NEW:
                     if P > E20 and 55 <= RSI <= 68: # Simplified
                         signal, mode = "BUY", "Mode A"
                         self.leg_state = LegState.CONFIRMED
                elif self.leg_state == LegState.CONFIRMED:
                    if (is_pullback and P > E20) or ("EMA Touch" in ptrns and P > E20):
                        if 45 <= RSI <= 62: signal, mode = "BUY", "Mode B"
                    if not signal and momentum_ok and 40 <= RSI <= 60 and ("Inside Bar" in ptrns or "Impulse" in ptrns):
                         signal, mode = "BUY", "Mode C"
            
            elif c30_trend == TrendState.BEARISH:
                 if self.leg_state == LegState.NEW:
                     if P < E20 and 32 <= RSI <= 45:
                         signal, mode = "SELL", "Mode A"
                         self.leg_state = LegState.CONFIRMED
                 elif self.leg_state == LegState.CONFIRMED:
                    if (is_pullback and P < E20) or ("EMA Touch" in ptrns and P < E20):
                        if 38 <= RSI <= 55: signal, mode = "SELL", "Mode B"
                    if not signal and momentum_ok and 40 <= RSI <= 60 and ("Inside Bar" in ptrns or "Impulse" in ptrns):
                         signal, mode = "SELL", "Mode C"
                         
            if signal:
                self.last_trade_index = i_idx
                risk = (0.6 * ATR) if mode == "Mode C" else (2.0 * ATR)
                sl = P - risk if signal == "BUY" else P + risk
                tp = P + (risk * (1.0 if mode == "Mode C" else 2.0)) if signal == "BUY" else P - (risk * (1.0 if mode == "Mode C" else 2.0))
                
                self.active_trade = {"direction": signal, "mode": mode, "entry": P, "sl": sl, "target": tp}
                
                return {
                    "instrument": instrument_name,
                    "mode": mode, "direction": signal,
                    "entry": P, "sl": sl, "target": tp,
                    "pattern": ", ".join(ptrns), "rsi": RSI, "atr": ATR,
                    "trend_state": c30_trend.name, "time": str(curr_date)
                }
            return None
        except: traceback.print_exc(); return None

# -------------------------------------------------------------------
# Unified Runner
# -------------------------------------------------------------------
class UnifiedRunner:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None
        self.nifty_strat = NiftyStrategy()
        self.gold_strat = GoldStrategy()
        self.kite = None
        
    def start(self):
        if self.thread and self.thread.is_alive(): return False
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run_loop)
        self.thread.daemon = True
        self.thread.start()
        return True
        
    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=2)
        return True

    def process_instrument(self, token, instrument, strategy, last_processed):
        try:
             # UTC Fix: India Time
            now = datetime.utcnow() + timedelta(hours=5, minutes=30)
            start = now - timedelta(days=5)
            
            c5 = self.kite.historical_data(token, start, now, interval="5minute")
            if not c5: return last_processed
            
            last_candle_time = c5[-1]['date']
            if last_processed == last_candle_time: return last_processed
            
            print(f"⚡ [{instrument}] Analyzing: {last_candle_time}")
            
            # Resample 30m
            c30_acc = []
            curr_30 = None
            for c in c5:
                dt = c['date']
                if dt.minute % 30 == 0 and dt.second == 0:
                    if curr_30: c30_acc.append(curr_30)
                    curr_30 = c.copy()
                else:
                    if curr_30:
                        curr_30['high'] = max(curr_30['high'], c['high'])
                        curr_30['low'] = min(curr_30['low'], c['low'])
                        curr_30['close'] = c['close']
                        curr_30['volume'] += c['volume']
                    else: curr_30 = c.copy()
            
            # Strategy Specific Calls
            if isinstance(strategy, NiftyStrategy):
                trend, slope = strategy.update_trend_30m(c30_acc)
                res = strategy.analyze_5m(c5, trend, slope, instrument)
            else:
                trend = strategy.update_trend_30m(c30_acc)
                res = strategy.analyze_5m(c5, trend, instrument, len(c5))
                
            if res:
                msg = f"""
<b>🔔 {instrument} SIGNAL</b>
MODE: {res.get('mode')} | TYPE: {res.get('direction')}
ENTRY: {res.get('entry')}
SL: {res.get('sl'):.1f} | TGT: {res.get('target')}
PATTERN: {res.get('pattern')}
TIME: {res.get('time')}
"""
                print(f"SIGNAL: {json.dumps(res, default=str)}")
                send_telegram_message(msg.strip())
                
            return last_candle_time
        except Exception as e:
            print(f"❌ Error processing {instrument}: {e}")
            return last_processed

    def run_loop(self):
        print("🚀 UNIFIED ENGINE STARTED")
        if not API_KEY or not ACCESS_TOKEN:
             print("❌ Error: Missing API_KEY/ACCESS_TOKEN"); return

        self.kite = KiteConnect(api_key=API_KEY)
        self.kite.set_access_token(ACCESS_TOKEN)
        
        # Get Tokens
        inst_list = [NIFTY_INSTRUMENT, GOLD_INSTRUMENT]
        tokens = {}
        try:
            q = self.kite.quote(inst_list)
            for i in inst_list:
                tokens[i] = q[i]['instrument_token']
        except Exception as e:
            print(f"❌ Token Fetch Error: {e}"); return
            
        last_times = {i: None for i in inst_list}

        while not self.stop_event.is_set():
            for inst in inst_list:
                strat = self.nifty_strat if inst == NIFTY_INSTRUMENT else self.gold_strat
                last_times[inst] = self.process_instrument(tokens[inst], inst, strat, last_times[inst])
            
            time.sleep(5)
        print("🛑 Engine Stopped")

# Global Instance
runner = UnifiedRunner()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true') # Not fully implemented in this unified runner entry point
    runner.start()
    while True: time.sleep(1)
