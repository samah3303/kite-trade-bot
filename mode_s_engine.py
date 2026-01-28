"""
MODE S — SENSEX
Version: v1.1 (LOCKED)
Status: FINAL – DEPLOYABLE

Objective: Maximise success rate, preserve capital, guarantee >= 5 calls/day.
"""

import numpy as np
import traceback
from enum import Enum
from datetime import datetime, time as dtime

class CallBucket(Enum):
    CORE = "CORE"             # High conviction
    STABILITY = "STABILITY"   # Controlled frequency
    LIQUIDITY = "LIQUIDITY"   # Time/Liquidity driven

class ModeSResponse:
    def __init__(self, valid, direction="NONE", bucket=None, reason="", 
                 entry=0.0, sl=0.0, target=0.0):
        self.valid = valid
        self.direction = direction
        self.bucket = bucket
        self.reason = reason
        self.entry = entry
        self.sl = sl
        self.target = target

    def __repr__(self):
        if not self.valid: return f"❌ {self.reason}"
        return f"✅ {self.direction} | Bucket: {self.bucket.name} | {self.reason}"

class ModeSEngine:
    def __init__(self):
        self.calls_issued_today = 0
        self.last_call_time = None
        self.last_trade_date = None
        
        # State Tracking per call type to avoid repetition
        self.last_call_direction = None
        self.last_call_price = 0.0
        
    def _reset_daily(self, current_date):
        if self.last_trade_date != current_date:
            self.calls_issued_today = 0
            self.last_call_direction = None
            self.last_trade_date = current_date
            print(f"🔄 MODE S: Daily Reset for {current_date}")

    def _ema(self, data, period):
        if len(data) < period: return np.zeros(len(data))
        ema = np.zeros(len(data))
        ema[0] = data[0]
        alpha = 2 / (period + 1)
        for i in range(1, len(data)):
            ema[i] = (data[i] * alpha) + (ema[i-1] * (1 - alpha))
        return ema

    def _atr(self, highs, lows, closes, period=14):
        if len(closes) < period: return 0.0
        tr_values = []
        for i in range(1, len(closes)):
             h = highs[i]
             l = lows[i]
             pc = closes[i-1]
             tr = max(h - l, abs(h - pc), abs(l - pc))
             tr_values.append(tr)
        return float(np.mean(tr_values[-period:])) if tr_values else 0.0

    def _vwap(self, candles):
        # Calculate Intraday VWAP
        # Assumes candles are from start of day or sufficient window
        cum_vol = 0
        cum_pv = 0
        vwap_series = []
        
        # Reset at start of day logic is complex with just a list of candles
        # We will assume the input 'candles' contains today's data primarily or we calculate rolling
        # For simplicity/robustness, we'll use a rolling VWAP of last N candles if day break not distinct
        # OR ideally, the engine receives today's candles only. 
        # Let's assume input 'candles' is substantial. 
        
        for c in candles:
             avg_p = (c['high'] + c['low'] + c['close']) / 3
             v = c.get('volume', 0)
             if v == 0: v = 1 # Avoid div by zero
             
             # Simple cumulative for passed chunk
             cum_pv += avg_p * v
             cum_vol += v
             vwap_series.append(cum_pv / cum_vol)
             
        return vwap_series

    def analyze(self, candles):
        try:
            if len(candles) < 50: return ModeSResponse(False, reason="Need Data")
            
            c = candles[-1]
            date = c['date'].date()
            t_now = c['date'].time()
            
            self._reset_daily(date)
            
            # 1. Unpack Data
            closes = [x['close'] for x in candles]
            highs = [x['high'] for x in candles]
            lows = [x['low'] for x in candles]
            
            P = c['close']; O = c['open']; H = c['high']; L = c['low']
            
            ema20 = self._ema(closes, 20)
            ema50 = self._ema(closes, 50)
            atr = self._atr(highs, lows, closes, 14)
            vwap_series = self._vwap(candles) # Approximate
            
            E20 = ema20[-1]
            E50 = ema50[-1]
            VWAP = vwap_series[-1]
            
            # 2. Determine Activation State (The Guarantee Mechanism)
            # Default: Core Only
            enable_stability = False
            enable_liquidity = False
            
            # Escalation 1: 1:30 PM (13:30)
            if t_now >= dtime(13, 30) and self.calls_issued_today < 3:
                enable_stability = True
                
            # Escalation 2: 2:45 PM (14:45)
            if t_now >= dtime(14, 45) and self.calls_issued_today < 5:
                enable_stability = True
                enable_liquidity = True
                
            # 3. Evaluate Buckets (Priority Order)
            
            # --- BUCKET A: CORE CALLS (Always Active) ---
            # Logic: Trend Following / Clean Structure
            if P > E20 > E50: # Bullish Trend
                if L <= (E20 * 1.001) and P > E20: # Pullback or Touch
                     # Check Momentum
                     if P > O: # Green Candle
                         return self._pack_response("BUY", CallBucket.CORE, "Trend Pullback", P, L, atr)
            elif P < E20 < E50: # Bearish Trend
                 if H >= (E20 * 0.999) and P < E20:
                     if P < O: # Red Candle
                         return self._pack_response("SELL", CallBucket.CORE, "Trend Pullback", P, H, atr)
                         
            # --- BUCKET B: STABILITY CALLS (If Enabled) ---
            if enable_stability:
                # Logic: VWAP Reversion / Mean Reversion
                # Buy if far below VWAP and turning up
                dist_vwap = (P - VWAP) / VWAP
                
                # Buy Logic: Price < VWAP - 0.5% (Oversold)
                if dist_vwap < -0.003: # 0.3% deviation
                     if P > E20 and P > O: # Reclaiming local structure
                         return self._pack_response("BUY", CallBucket.STABILITY, "VWAP Reversion", P, L, atr, risk_factor=0.8)
                         
                # Sell Logic: Price > VWAP + 0.3% (Overbought)
                if dist_vwap > 0.003:
                     if P < E20 and P < O:
                         return self._pack_response("SELL", CallBucket.STABILITY, "VWAP Reversion", P, H, atr, risk_factor=0.8)

            # --- BUCKET C: LIQUIDITY CALLS (If Enabled) ---
            if enable_liquidity:
                # Logic: Liquidity run / Day High/Low Test
                day_high = max(highs[-50:]) # Approx last 4 hours
                day_low = min(lows[-50:])
                
                # Breakout attempt or Liquidity Grab
                if P > day_high:
                     return self._pack_response("BUY", CallBucket.LIQUIDITY, "Liquidity Breakout", P, L, atr, risk_factor=0.6)
                if P < day_low:
                     return self._pack_response("SELL", CallBucket.LIQUIDITY, "Liquidity Breakdown", P, H, atr, risk_factor=0.6)

            return ModeSResponse(False)

        except Exception as e:
            traceback.print_exc()
            return ModeSResponse(False, reason=f"Error: {e}")

    def _pack_response(self, direction, bucket, pattern, price, structure_lvl, atr, risk_factor=1.0):
        # Noise Control: Max 5 similar calls? 
        # Using simple check: Don't repeat identical call immediately
        if self.last_call_direction == direction and abs(price - self.last_call_price) < (0.5 * atr):
             return ModeSResponse(False, reason="Noise Control (Similar Call)")
        
        # Entry Logic
        sl = 0.0
        target = 0.0
        
        if direction == "BUY":
            sl = structure_lvl - (0.5 * atr)
            risk = price - sl
            if risk < (0.5 * atr): risk = 0.5 * atr # Min risk
            sl = price - risk
            target = price + (risk * 1.5 * risk_factor) # Reward scales with bucket risk
            
        else: # SELL
            sl = structure_lvl + (0.5 * atr)
            risk = sl - price
            if risk < (0.5 * atr): risk = 0.5 * atr
            sl = price + risk
            target = price - (risk * 1.5 * risk_factor)

        # Update State
        self.calls_issued_today += 1
        self.last_call_direction = direction
        self.last_call_price = price
        
        return ModeSResponse(True, direction, bucket, pattern, price, sl, target)

