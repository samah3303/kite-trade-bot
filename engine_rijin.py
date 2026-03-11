"""
KiteAlerts V6.0 — RIJIN v3.2
The Tactical Adapter

3 Gears:
  Gear 1: Trend Pullback (VWAP + HH + EMA20 bounce)
  Gear 2: Mean Reversion (Bollinger + RSI extreme + ADX lock)
  Gear 3: Momentum Impulse (single candle > 1.5× ATR)
"""

import logging
import indicators as ind
from config import RIJIN_CONFIG


def scan(candles, instrument_config):
    """
    Scan for RIJIN signal across all 3 gears.

    Args:
        candles: list of candle dicts (5-min)
        instrument_config: dict from config.INSTRUMENTS[name]

    Returns:
        dict signal (with gear info) or None
    """
    cfg = RIJIN_CONFIG

    if len(candles) < 50:
        return None

    highs = [float(c['high']) for c in candles]
    lows = [float(c['low']) for c in candles]
    closes = [float(c['close']) for c in candles]
    opens = [float(c['open']) for c in candles]

    price = closes[-1]
    candle_open = opens[-1]
    candle_high = highs[-1]
    candle_low = lows[-1]

    # Indicators
    ema20 = ind.ema(closes, cfg["ema_trend_period"])
    e20 = ema20[-1]
    atr_vals = ind.atr(highs, lows, closes)
    current_atr = atr_vals[-1]
    vwap_vals = ind.vwap(candles)
    current_vwap = vwap_vals[-1]
    rsi_vals = ind.rsi(closes, cfg["rsi_period"])
    current_rsi = rsi_vals[-1]
    adx_vals, plus_di, minus_di = ind.adx(highs, lows, closes, cfg["adx_period"])
    current_adx = adx_vals[-1]
    bb_upper, bb_mid, bb_lower = ind.bollinger_bands(closes, cfg["bollinger_period"], cfg["bollinger_std"])

    # Structure check: Higher Highs / Lower Lows
    recent_highs = highs[-10:]
    recent_lows = lows[-10:]
    making_hh = len(recent_highs) >= 5 and recent_highs[-1] > max(recent_highs[-5:-1])
    making_ll = len(recent_lows) >= 5 and recent_lows[-1] < min(recent_lows[-5:-1])

    # Is candle green/red?
    is_green = price > candle_open
    is_red = price < candle_open

    # ─────────────────────────────────────────────────────
    # GEAR 3: MOMENTUM IMPULSE (check first — speed matters)
    # Single candle body > 1.5× ATR
    # ─────────────────────────────────────────────────────
    body = abs(price - candle_open)
    if current_atr > 0 and body > cfg["impulse_atr_multiplier"] * current_atr:
        if is_green:
            sl = price - 1.0 * current_atr
            target = price + 1.5 * current_atr
            return _signal("RIJIN Gear 3 (Impulse)", "LONG", price, sl, target,
                           current_atr, current_rsi, current_adx)
        elif is_red:
            sl = price + 1.0 * current_atr
            target = price - 1.5 * current_atr
            return _signal("RIJIN Gear 3 (Impulse)", "SHORT", price, sl, target,
                           current_atr, current_rsi, current_adx)

    # ─────────────────────────────────────────────────────
    # GEAR 1: TREND PULLBACK
    # Price > VWAP, making HH, pulls back to EMA20, closes green
    # ─────────────────────────────────────────────────────
    tolerance = e20 * cfg["gear1_pullback_tolerance"]

    # Long
    if price > current_vwap and making_hh:
        if candle_low <= e20 + tolerance and is_green:
            sl = min(candle_low, e20 - current_atr)
            target = price + 2.0 * current_atr
            return _signal("RIJIN Gear 1 (Trend)", "LONG", price, sl, target,
                           current_atr, current_rsi, current_adx)

    # Short
    if price < current_vwap and making_ll:
        if candle_high >= e20 - tolerance and is_red:
            sl = max(candle_high, e20 + current_atr)
            target = price - 2.0 * current_atr
            return _signal("RIJIN Gear 1 (Trend)", "SHORT", price, sl, target,
                           current_atr, current_rsi, current_adx)

    # ─────────────────────────────────────────────────────
    # GEAR 2: MEAN REVERSION
    # Price breaks Bollinger, RSI extreme, closes BACK inside band
    # ADX Lock: disabled if ADX > 25
    # ─────────────────────────────────────────────────────
    if current_adx <= cfg["adx_trend_threshold"]:
        # Long: price was below lower BB, RSI oversold, closes back inside
        prev_close = closes[-2] if len(closes) > 1 else price
        if prev_close < bb_lower[-2] and price > bb_lower[-1] and current_rsi < cfg["rsi_oversold"]:
            sl = candle_low - 0.3 * current_atr
            target = bb_mid[-1]  # Target: mid-band
            return _signal("RIJIN Gear 2 (Reversion)", "LONG", price, sl, target,
                           current_atr, current_rsi, current_adx)

        # Short: price was above upper BB, RSI overbought, closes back inside
        if prev_close > bb_upper[-2] and price < bb_upper[-1] and current_rsi > cfg["rsi_overbought"]:
            sl = candle_high + 0.3 * current_atr
            target = bb_mid[-1]
            return _signal("RIJIN Gear 2 (Reversion)", "SHORT", price, sl, target,
                           current_atr, current_rsi, current_adx)

    return None


def _signal(engine, direction, entry, sl, target, atr_val, rsi_val, adx_val):
    """Build standardized signal dict."""
    return {
        "engine": engine,
        "direction": direction,
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "target": round(target, 2),
        "atr": round(atr_val, 2),
        "rsi": round(rsi_val, 1),
        "adx": round(adx_val, 1),
    }
