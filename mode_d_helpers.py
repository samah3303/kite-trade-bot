# MODE D Helper Methods for NiftyStrategy
# Add these methods to the NiftyStrategy class

def check_mode_d_eligibility(self, c5, c30, global_bias):
    """
    Check if MODE D (Opening Drive) is eligible for the day.
    
    Returns: (eligible: bool, direction: str or None)
    
    ALL conditions must pass:
    1. Day Type ≠ CHOP
    2. Global Bias NOT opposing
    3. First 3 candles (09:15-09:30):
       - Range ≥ 0.50 × ATR
       - ≥2 candles same direction  
       - Body ≥ 60% of range
       - Wicks ≤ 40%
    4. EMA20 slope aligns by 3rd candle
    5. RSI: SELL ≤45 / BUY ≥55
    """
    try:
        # Get today's candles
        current_date = c5[-1]['date'].date()
        todays_candles = [x for x in c5 if x['date'].date() == current_date]
        
        if len(todays_candles) < 4:  # Need at least 3 completed + 1 current
            return False, None
        
        # Store first 3 candles for opening range calculation
        self.first_three_candles = todays_candles[:3]
        
        # Calculate ATR for comparison
        closes = [float(x['close']) for x in c5]
        highs = [float(x['high']) for x in c5]
        lows = [float(x['low']) for x in c5]
        atr = calculate_atr(highs, lows, closes, 14)
        ATR = float(atr[-1])
        
        # Calculate EMA20 and RSI on 5m
        ema20 = simple_ema(closes, 20)
        rsi = calculate_rsi(closes, 14)
        slope_5m = get_slope(ema20)
        RSI = float(rsi[-1])
        
        # Condition 1: Day Type ≠ CHOP
        if self.day_type == "CHOP":
            return False, None
        
        # Condition 3: First 3 candles analysis
        first_3_highs = [float(c['high']) for c in self.first_three_candles]
        first_3_lows = [float(c['low']) for c in self.first_three_candles]
        or_range = max(first_3_highs) - min(first_3_lows)
        
        # Range must be ≥ 0.50 × ATR
        if or_range < (0.50 * ATR):
            return False, None
        
        # Check direction consistency (≥2 candles same direction)
        bullish_candles = sum(1 for c in self.first_three_candles if float(c['close']) > float(c['open']))
        bearish_candles = sum(1 for c in self.first_three_candles if float(c['close']) < float(c['open']))
        
        if bullish_candles >= 2:
            direction = "BUY"
        elif bearish_candles >= 2:
            direction = "SELL"
        else:
            return False, None  # Mixed direction
        
        # Check body ≥ 60% and wicks ≤ 40%
        for c in self.first_three_candles:
            h, l, o, cl = float(c['high']), float(c['low']), float(c['open']), float(c['close'])
            candle_range = h - l
            if candle_range > 0:
                body = abs(cl - o)
                body_pct = body / candle_range
                wick_pct = 1 - body_pct
                
                if body_pct < 0.60 or wick_pct > 0.40:
                    return False, None
        
        # Condition 2: Global Bias NOT opposing (using global_market_analyzer)
        # Parse global_bias string to check opposition
        if global_bias == "RISK_OFF" and direction == "BUY":
            return False, None
        if global_bias == "RISK_ON" and direction == "SELL":
            return False, None
        
        # Condition 4: EMA20 slope aligns
        if direction == "BUY" and slope_5m <= 0:
            return False, None
        if direction == "SELL" and slope_5m >= 0:
            return False, None
        
        # Condition 5: RSI conditions
        if direction == "SELL" and RSI > 45:
            return False, None
        if direction == "BUY" and RSI < 55:
            return False, None
        
        # All conditions passed!
        self.opening_range_high = max(first_3_highs)
        self.opening_range_low = min(first_3_lows)
        
        return True, direction
        
    except Exception as e:
        print(f"❌ MODE D eligibility check error: {e}")
        return False, None


def analyze_mode_d(self, c5, global_bias):
    """
    MODE D Entry Logic (Option B - Conservative Pullback)
    
    Entry: Wait for first pullback candle that FAILS to reclaim EMA20
    Time Window: 09:20-10:30 IST ONLY
    SL: min(High/Low of first 3, 1.0 ATR)
    Target: 1.5R fixed
    """
    try:
        # Get current candle data
        c = c5[-1]
        closes = [float(x['close']) for x in c5]
        highs = [float(x['high']) for x in c5]
        lows = [float(x['low']) for x in c5]
        
        ema20 = simple_ema(closes, 20)
        atr = calculate_atr(highs, lows, closes, 14)
        
        P = float(c['close'])
        H = float(c['high'])
        L = float(c['low'])
        O = float(c['open'])
        E20 = float(ema20[-1])
        ATR = float(atr[-1])
        
        # Check eligibility (sets opening range as side effect)
        eligible, direction = self.check_mode_d_eligibility(c5, None, global_bias)
        
        if not eligible:
            return None
        
        signal = None
        mode = "MODE_D"
        pattern = "Opening Drive"
        
        # Option B: Conservative - Wait for pullback that fails to reclaim EMA20
        if direction == "BUY":
            # Wait for a pullback (price tested below EMA or near it)
            # Then rejection back above
            #
pullback_occurred = L <= E20  # Touched or went below EMA
            rejection = P > E20 and P > O  # Closed back above with bullish candle
            
            if pullback_occurred and rejection:
                signal = "BUY"
                pattern = "Opening Drive Pullback"
                
                # SL: min(OR low, Entry - 1.0 ATR)
                sl_or = self.opening_range_low
                sl_atr = P - (1.0 * ATR)
                sl_val = max(sl_or, sl_atr)  # Use tighter stop
                
                # Target: 1.5R
                tp_val = str(round(P + (1.5 * (P - sl_val)), 2))
                
        elif direction == "SELL":
            # Wait for pullback upward, then failure
            pullback_occurred = H >= E20
            rejection = P < E20 and P < O
            
            if pullback_occurred and rejection:
                signal = "SELL"
                pattern = "Opening Drive Breakdown"
                
                # SL: max(OR high, Entry + 1.0 ATR)
                sl_or = self.opening_range_high
                sl_atr = P + (1.0 * ATR)
                sl_val = min(sl_or, sl_atr)
                
                # Target: 1.5R
                tp_val = str(round(P - (1.5 * (sl_val - P)), 2))
        
        if signal:
            return {
                "instrument": "NFO:NIFTY26JANFUT",  # Will be overridden
                "mode": mode,
                "direction": signal,
                "entry": P,
                "sl": sl_val,
                "target": tp_val,
                "pattern": pattern,
                "rsi": 0,  # Will be filled
                "atr": ATR,
                "trend_state": "MODE_D",
                "time": str(c['date'])
            }
        
        return None
        
    except Exception as e:
        print(f"❌ MODE D analysis error: {e}")
        traceback.print_exc()
        return None
