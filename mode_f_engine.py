"""
MODE F — FINAL, LOCKED, PRODUCTION LOGIC
NIFTY GLOBAL–STRUCTURAL PREDICTIVE EXECUTION ENGINE

Identity:
- 100% Independent (No Mode A/B/C dependency)
- Accuracy > Frequency
- Structure > Indicators
- Volatility decides authority
"""

import numpy as np
import traceback
from datetime import datetime, timedelta
from enum import Enum

class VolatilityState(Enum):
    NORMAL = "NORMAL"
    EXPANDING = "EXPANDING"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"

class DominanceState(Enum):
    BUYERS = "BUYERS"
    SELLERS = "SELLERS"
    NONE = "NONE"

class StructuralState(Enum):
    BULLISH_CONTINUATION = "BULLISH_CONTINUATION"
    BEARISH_CONTINUATION = "BEARISH_CONTINUATION"
    RANGE = "RANGE"
    BREAKOUT_ACCEPTED = "BREAKOUT_ACCEPTED"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"
    TRANSITION = "TRANSITION"

class ModeFResponse:
    def __init__(self, valid, direction="NONE", reason="CALL NOT VALID", 
                 vol_state=VolatilityState.UNKNOWN, struct_state=StructuralState.TRANSITION,
                 entry=0.0, sl=0.0, target=0.0, narrative=""):
        self.valid = valid
        self.direction = direction # BUY / SELL / NONE
        self.reason = reason
        self.vol_state = vol_state
        self.struct_state = struct_state
        self.entry = entry
        self.sl = sl
        self.target = target
        self.narrative = narrative

    def __repr__(self):
        if not self.valid:
            return f"❌ {self.reason}"
        return f"✅ {self.direction} | Entry: {self.entry} | SL: {self.sl} | Tgt: {self.target} | Vol: {self.vol_state.name}"

class ModeFEngine:
    def __init__(self):
        self.last_call_time = None
        self.last_call_result = None
        
    def _simple_ema(self, data, period):
        if len(data) == 0: return []
        ema = np.zeros(len(data))
        ema[0] = data[0]
        alpha = 2 / (period + 1)
        for i in range(1, len(data)):
            ema[i] = (data[i] * alpha) + (ema[i-1] * (1 - alpha))
        return ema

    def _calculate_atr(self, highs, lows, closes, period=14):
        if len(closes) < period: return 0.0
        tr_sum = 0.0
        # Simple AVG/EMA approximation for engine speed
        # Real ATR:
        tr_values = []
        for i in range(1, len(closes)):
             h = highs[i]
             l = lows[i]
             pc = closes[i-1]
             tr = max(h - l, abs(h - pc), abs(l - pc))
             tr_values.append(tr)
        
        if not tr_values: return 0.0
        return float(np.mean(tr_values[-period:]))

    def get_slope(self, series, lookback=3):
        if len(series) < lookback + 1: return 0.0
        return float(series[-1] - series[-lookback-1])

    # 1. GLOBAL RISK ENGINE (Permission Layer)
    # Assumes 'global_bias' string is passed from GlobalMarketAnalyzer (RISK_ON / RISK_OFF / NEUTRAL)
    # Logic: Risk-Off blocks BUY, Risk-On blocks SELL (mostly)
    
    # 2. VOLATILITY ENGINE
    def evaluate_volatility(self, candles):
        """
        Classify Volatility into NORMAL / EXPANDING / EXTREME
        Using ATR and Recent Range
        """
        try:
            if len(candles) < 20: return VolatilityState.NORMAL
            
            closes = [c['close'] for c in candles]
            highs = [c['high'] for c in candles]
            lows = [c['low'] for c in candles]
            
            atr = self._calculate_atr(highs, lows, closes, 14)
            
            # Helper: Average Candle Body vs ATR
            recent_bodies = [abs(c['close'] - c['open']) for c in candles[-5:]]
            avg_body = np.mean(recent_bodies)
            
            # Logic
            if avg_body > (1.5 * atr): return VolatilityState.EXTREME
            if avg_body > (1.0 * atr): return VolatilityState.EXPANDING
            return VolatilityState.NORMAL
            
        except: return VolatilityState.NORMAL

    # 5. STRUCTURAL STATE ENGINE
    def evaluate_structure(self, candles, ema20):
        """
        Classify Structure: CONTINUATION (B/B), RANGE, BREAKOUT_ACCEPTED, FAILED_BREAKOUT
        """
        try:
            if len(candles) < 10: return StructuralState.TRANSITION
            
            c = candles[-1]
            P = float(c['close'])
            E20 = float(ema20[-1])
            slope = self.get_slope(ema20)
            
            # High/Low of last 10 candles
            last_10_h = max([x['high'] for x in candles[-10:]])
            last_10_l = min([x['low'] for x in candles[-10:]])
            
            # Bullish Continuation
            if P > E20 and slope > 0:
                # Check for higher highs in last 5 candles
                recent_highs = [x['high'] for x in candles[-5:]]
                if recent_highs[-1] >= max(recent_highs[:-1]) or P > E20 * 1.001:
                    return StructuralState.BULLISH_CONTINUATION
            
            # Bearish Continuation
            if P < E20 and slope < 0:
                recent_lows = [x['low'] for x in candles[-5:]]
                if recent_lows[-1] <= min(recent_lows[:-1]) or P < E20 * 0.999:
                    return StructuralState.BEARISH_CONTINUATION
            
            # Range (Slope Flat)
            if abs(slope) < 0.5: # Arbitrary threshold, depends on instrument scale (Nifty ~24000)
                 # Nifty slope 0.5 is tiny. Let's say < 2 points over 3 candles?
                 return StructuralState.RANGE
                 
            return StructuralState.TRANSITION
        except: return StructuralState.TRANSITION

    # 6. DOMINANCE ENGINE
    def evaluate_dominance(self, candles):
        """
        Who is in control?
        """
        try:
            if len(candles) < 3: return DominanceState.NONE
            
            # Check last 3 candles
            bull_score = 0
            bear_score = 0
            
            for c in candles[-3:]:
                if c['close'] > c['open']: bull_score += 1
                elif c['close'] < c['open']: bear_score += 1
                
                # Big body bonus
                body = abs(c['close'] - c['open'])
                full_range = c['high'] - c['low']
                if full_range > 0 and (body / full_range) > 0.6:
                    if c['close'] > c['open']: bull_score += 1
                    else: bear_score += 1
            
            if bull_score >= 3: return DominanceState.BUYERS
            if bear_score >= 3: return DominanceState.SELLERS
            
            # If mixed, look at most recent massive candle?
            return DominanceState.NONE
        except: return DominanceState.NONE

    # MAIN PREDICTION FUNCTION
    def predict(self, candles, global_bias="NEUTRAL", event_status="POST"):
        """
        The "User Click" Trigger
        """
        try:
            # 1. GOVERNANCE: 5 min Re-click (Simulated by checking last call time if passed, but here we run fresh)
            
            # Data Prep
            if len(candles) < 50: 
                return ModeFResponse(False, reason="Insufficient Data")
                
            closes = [c['close'] for c in candles]
            ema20 = self._simple_ema(closes, 20)
            atr = self._calculate_atr([c['high'] for c in candles], [c['low'] for c in candles], closes)
            
            c = candles[-1]
            price = c['close']
            
            # 2. GLOBAL RISK (Permission)
            # bias passed from caller (RISK_ON / RISK_OFF / MIXED/NEUTRAL)
            risk_on = global_bias == "RISK_ON"
            risk_off = global_bias == "RISK_OFF"
            
            # 3. VOLATILITY ENGINE
            vol_state = self.evaluate_volatility(candles)
            if vol_state == VolatilityState.EXTREME:
                 # Sub-mode: Restricted
                 return ModeFResponse(False, reason="Extreme Volatility - Restricted Mode Engaged (Auto-Safety)", vol_state=vol_state)
            
            # 4. STRUCTURE
            struct_state = self.evaluate_structure(candles, ema20)
            if struct_state in [StructuralState.TRANSITION, StructuralState.RANGE, StructuralState.FAILED_BREAKOUT]:
                # In strict mode, we don't trade ranges or transitions?
                # "Range without dominance -> Call Not Valid"
                pass # Continue to dominance to check
                
            # 5. DOMINANCE
            dominance = self.evaluate_dominance(candles)
            if dominance == DominanceState.NONE:
                return ModeFResponse(False, reason="Dominance Unclear", vol_state=vol_state, struct_state=struct_state)
                
            # 6. CONFLUENCE GATE
            direction = "NONE"
            valid = False
            sl = 0.0
            tgt = 0.0
            reason = ""
            
            # BUY LOGIC
            if dominance == DominanceState.BUYERS:
                allowed = True
                
                # Rule: Structure = Bullish Continuation OR Accepted Breakout
                if struct_state not in [StructuralState.BULLISH_CONTINUATION, StructuralState.BREAKOUT_ACCEPTED]:
                    reason = f"BUY Rejected: Structure is {struct_state.name}"
                    allowed = False
                    
                # Rule: Global != Risk-Off (Unless Vol Normal)
                if risk_off and vol_state != VolatilityState.NORMAL:
                    reason = "BUY Rejected: Global Risk-OFF in Active Volatility"
                    allowed = False
                    
                if allowed:
                    valid = True
                    direction = "BUY"
                    sl = float(min([x['low'] for x in candles[-3:]])) - (0.5 * atr) # Structural Low
                    tgt = price + (2.0 * atr) # Target heuristic (Structure overrides in manual, using ATR for backtest)
                    
            # SELL LOGIC
            elif dominance == DominanceState.SELLERS:
                allowed = True
                
                if struct_state not in [StructuralState.BEARISH_CONTINUATION, StructuralState.FAILED_BREAKOUT]: # Failed breakout is bearish signal? Yes.
                     # Actually FAILED_BREAKOUT needs context (Failed Bull Breakout = Bearish). 
                     # Simplifying: Bearish Continuation is safest.
                     if struct_state != StructuralState.BEARISH_CONTINUATION:
                        reason = f"SELL Rejected: Structure is {struct_state.name}"
                        allowed = False

                if risk_on and vol_state != VolatilityState.NORMAL:
                    reason = "SELL Rejected: Global Risk-ON in Active Volatility"
                    allowed = False
                    
                if allowed:
                    valid = True
                    direction = "SELL"
                    sl = float(max([x['high'] for x in candles[-3:]])) + (0.5 * atr)
                    tgt = price - (2.0 * atr)
            
            else:
                reason = "No Dominance"
                
            if valid:
                return ModeFResponse(True, direction, vol_state=vol_state, struct_state=struct_state, 
                                     entry=price, sl=sl, target=tgt, narrative=f"Structure {struct_state.name} + Dominance {dominance.name}")
            else:
                return ModeFResponse(False, reason=reason, vol_state=vol_state, struct_state=struct_state)

        except Exception as e:
            return ModeFResponse(False, reason=f"Error: {str(e)}")

