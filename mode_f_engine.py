"""
MODE F (FINAL) — HIGH-FREQUENCY 3-GEAR ENGINE
NIFTY 50 EXCLUSIVE | AUTOMATED | SURVIVABLE

GEAR 1: STRUCTURE TREND (Trend Following)
GEAR 2: STRUCTURE ROTATION (Range/Reversals)
GEAR 3: VOLATILITY MOMENTUM (Scalps)
"""

import numpy as np
import traceback
from enum import Enum

# -------------------------------------------------------------------
# ENUMS
# -------------------------------------------------------------------

class VolatilityRegime(Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"
    
class Gear(Enum):
    GEAR_1_TREND = "GEAR_1_TREND"
    GEAR_2_ROTATION = "GEAR_2_ROTATION"
    GEAR_3_MOMENTUM = "GEAR_3_MOMENTUM"
    NEUTRAL = "NEUTRAL"

class DominanceState(Enum):
    BUYERS = "BUYERS"
    SELLERS = "SELLERS"

class GlobalRiskState(Enum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    MIXED = "MIXED"

class ModeFResponse:
    def __init__(self, valid, direction="NONE", gear=Gear.NEUTRAL, reason="", 
                 entry=0.0, sl=0.0, target=0.0, regime=VolatilityRegime.NORMAL):
        self.valid = valid
        self.direction = direction
        self.gear = gear
        self.reason = reason
        self.entry = entry
        self.sl = sl
        self.target = target
        self.regime = regime

    def __repr__(self):
        if not self.valid:
            return f"❌ {self.reason}"
        return f"✅ {self.direction} | Gear: {self.gear.name} | Regime: {self.regime.name}"

# -------------------------------------------------------------------
# ENGINE
# -------------------------------------------------------------------

class ModeFEngine:
    def __init__(self):
        self.last_signal_time = None
        
    # --- UTILS ---
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
        if not tr_values: return 0.0
        return float(np.mean(tr_values[-period:]))

    def _slope(self, series, lookback=3):
        if len(series) < lookback + 1: return 0.0
        return float(series[-1] - series[-lookback-1])

    # --- CORE ---
    
    def get_volatility_regime(self, candles):
        # Using ATR and Range to define regime
        if len(candles) < 20: return VolatilityRegime.NORMAL
        
        closes = [c['close'] for c in candles]
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        
        current_atr = self._atr(highs, lows, closes, 14)
        
        # Calculate Average True Range of last 5 days (approx 375 candles) for baseline?
        # Simpler: Relative to price.
        # Nifty ~24000. 
        # Low: ATR < 30
        # Normal: 30 < ATR < 60
        # High: 60 < ATR < 100
        # Extreme: ATR > 100
        # This needs dynamic baseline, but let's use recent history comparison.
        
        # Better Strategy: Current ATR vs MA(ATR, 50)
        # Note: We don't have enough history for 50-period ATR on 5m usually in short snippets.
        # Let's use absolute percentage of price.
        price = closes[-1]
        atr_pct = (current_atr / price) * 100
        
        # Tuned thresholds for Nifty Intraday 5m
        if atr_pct < 0.10: return VolatilityRegime.LOW        # < 24 pts
        if atr_pct < 0.25: return VolatilityRegime.NORMAL     # < 60 pts
        if atr_pct < 0.40: return VolatilityRegime.HIGH       # < 96 pts
        return VolatilityRegime.EXTREME                       # > 96 pts

    def get_dominance(self, candles):
        # Last 3 candles structure
        if len(candles) < 3: return DominanceState.BUYERS # Fallback
        
        bulls = 0
        bears = 0
        for c in candles[-3:]:
            if c['close'] > c['open']: bulls += 1
            else: bears += 1
            
        if bulls > bears: return DominanceState.BUYERS
        return DominanceState.SELLERS

    def predict(self, candles, global_bias="NEUTRAL"):
        try:
            if len(candles) < 50: return ModeFResponse(False, reason="Need Data")
            
            c = candles[-1]
            P = c['close']
            O = c['open']
            H = c['high']
            L = c['low']
            
            closes = [x['close'] for x in candles]
            ema20 = self._ema(closes, 20)
            ema50 = self._ema(closes, 50)
            atr = self._atr([x['high'] for x in candles], [x['low'] for x in candles], closes)
            E20 = ema20[-1]
            E50 = ema50[-1]
            
            # 1. GET CONTEXT
            regime = self.get_volatility_regime(candles)
            dominance = self.get_dominance(candles)
            
            # Map Global Bias
            is_risk_on = global_bias == "RISK_ON"
            is_risk_off = global_bias == "RISK_OFF"
            
            # 2. SELECT GEAR
            # Determine active logic based on Regime
            
            # ---------------------------------------------------------
            # 🔵 GEAR 1: TREND (Low/Normal Vol)
            # ---------------------------------------------------------
            if regime in [VolatilityRegime.LOW, VolatilityRegime.NORMAL]:
                # Long Trend Check
                if P > E20 and E20 > E50:
                    if dominance == DominanceState.BUYERS:
                        # Pullback Entry?
                        if L <= (E20 * 1.0005): # Near EMA20
                            if not is_risk_off:
                                return ModeFResponse(True, "BUY", Gear.GEAR_1_TREND, "Trend Pullback", 
                                                     entry=P, sl=min(L, E20-(atr)), target=P+(2*atr), regime=regime)
                
                # Short Trend Check
                if P < E20 and E20 < E50:
                    if dominance == DominanceState.SELLERS:
                        if H >= (E20 * 0.9995):
                            if not is_risk_on:
                                return ModeFResponse(True, "SELL", Gear.GEAR_1_TREND, "Trend Pullback", 
                                                     entry=P, sl=max(H, E20+(atr)), target=P-(2*atr), regime=regime)

            # ---------------------------------------------------------
            # 🟡 GEAR 2: ROTATION (Normal/High Vol)
            # ---------------------------------------------------------
            if regime in [VolatilityRegime.NORMAL, VolatilityRegime.HIGH]:
                # Range / Mean Reversion Logic
                # Identifying Range: Flat E20 slope roughly?
                slope = abs(E20 - ema20[-5])
                is_flat = slope < (atr * 0.5)
                
                if is_flat:
                    # Bollinger Band logic proxy (2 std dev approx 2*ATR from E20)
                    upper = E20 + (2 * atr)
                    lower = E20 - (2 * atr)
                    
                    # Rejection from Low (Long)
                    if L < lower and P > lower and dominance == DominanceState.BUYERS:
                         return ModeFResponse(True, "BUY", Gear.GEAR_2_ROTATION, "Range Rotation Low", 
                                              entry=P, sl=L-(0.2*atr), target=E20, regime=regime) # Target Mid
                                              
                    # Rejection from High (Short)
                    if H > upper and P < upper and dominance == DominanceState.SELLERS:
                         return ModeFResponse(True, "SELL", Gear.GEAR_2_ROTATION, "Range Rotation High", 
                                              entry=P, sl=H+(0.2*atr), target=E20, regime=regime)

            # ---------------------------------------------------------
            # 🔴 GEAR 3: MOMENTUM (High/Extreme Vol)
            # ---------------------------------------------------------
            if regime in [VolatilityRegime.HIGH, VolatilityRegime.EXTREME]:
                # Momentum Impulse
                # Big Candle + Breakout
                body = abs(P - O)
                is_impulse = body > (1.5 * atr)
                
                if is_impulse:
                    if P > O and dominance == DominanceState.BUYERS: # Green Impulse
                        return ModeFResponse(True, "BUY", Gear.GEAR_3_MOMENTUM, "Volatility Impulse", 
                                             entry=P, sl=P-(1*atr), target=P+(1.5*atr), regime=regime) # Scalp
                                             
                    if P < O and dominance == DominanceState.SELLERS: # Red Impulse
                         return ModeFResponse(True, "SELL", Gear.GEAR_3_MOMENTUM, "Volatility Impulse", 
                                             entry=P, sl=P+(1*atr), target=P-(1.5*atr), regime=regime)

            return ModeFResponse(False, reason="No Setup", regime=regime)
            
        except Exception as e:
            traceback.print_exc()
            return ModeFResponse(False, reason=f"Error: {e}")
