"""
KiteAlerts V6.0 — MODE_DON v2.2
The Breakout Sniper

Catches massive structural trend days at ignition.
Donchian(20) breakout with volume confirmation,
squeeze gate, and rubber band protection.
"""

import logging
import indicators as ind
from config import MODE_DON_CONFIG


def scan(candles, instrument_config):
    """
    Scan for MODE_DON breakout signal.

    Args:
        candles: list of candle dicts (5-min)
        instrument_config: dict from config.INSTRUMENTS[name]

    Returns:
        dict signal or None
    """
    cfg = MODE_DON_CONFIG
    period = instrument_config.get("donchian_period", cfg["donchian_period"])
    min_candles = period + cfg["squeeze_candles"] + 2

    if len(candles) < min_candles:
        return None

    highs = [float(c['high']) for c in candles]
    lows = [float(c['low']) for c in candles]
    closes = [float(c['close']) for c in candles]
    volumes = [float(c.get('volume', 0) or 0) for c in candles]

    # Current candle
    price = closes[-1]
    current_vol = volumes[-1]

    # 1. Donchian Channel
    upper, lower = ind.donchian(highs, lows, period)
    if upper is None:
        return None

    # 2. Volume confirmation: current volume > 1.2× SMA(20)
    vol_sma = ind.volume_sma(volumes, cfg["volume_sma_period"])
    vol_threshold = vol_sma[-1] * cfg["volume_breakout_multiplier"]

    # For instruments with no volume data (indices), skip volume check
    has_volume = any(v > 0 for v in volumes[-5:])
    if has_volume and current_vol <= vol_threshold:
        return None

    # 3. Breakout buffer
    buffer_pct = instrument_config.get("breakout_buffer_pct")
    buffer_abs = instrument_config.get("breakout_buffer_abs", 0)

    if buffer_pct is not None:
        buffer = price * buffer_pct / 100
    else:
        buffer = buffer_abs

    # Determine direction
    direction = None
    if price > upper + buffer:
        direction = "LONG"
    elif price < lower - buffer:
        direction = "SHORT"
    else:
        return None

    # 4. Squeeze Gate: 3 preceding candles must have contracting ATR or be inside bars
    if not _check_squeeze(candles, cfg["squeeze_candles"]):
        return None

    # 5. Rubber Band Rule: void if close > 0.5% from VWAP
    vwap_vals = ind.vwap(candles)
    vwap_now = vwap_vals[-1]
    vwap_distance_pct = abs(price - vwap_now) / vwap_now * 100 if vwap_now > 0 else 0

    if vwap_distance_pct > cfg["rubber_band_max_vwap_pct"]:
        return None

    # 6. Exhaustion check
    atr_vals = ind.atr(highs, lows, closes)
    current_atr = atr_vals[-1]
    exhaust_mult = instrument_config.get("exhaustion_multiplier", 2.5)

    # Directional move from session
    session_high = max(highs)
    session_low = min(lows)
    if direction == "LONG":
        move = price - session_low
    else:
        move = session_high - price

    if current_atr > 0 and move > exhaust_mult * current_atr:
        return None

    # Build signal
    # Stop: opposite Donchian(10) or 1.2× ATR — whichever is tighter
    stop_period = instrument_config.get("donchian_stop_period", 10)
    stop_upper, stop_lower = ind.donchian(highs, lows, stop_period)

    if direction == "LONG":
        donchian_stop = stop_lower if stop_lower else price - 1.2 * current_atr
        atr_stop = price - 1.2 * current_atr
        sl = max(donchian_stop, atr_stop)  # Tighter stop
        target = price + 2.0 * current_atr
    else:
        donchian_stop = stop_upper if stop_upper else price + 1.2 * current_atr
        atr_stop = price + 1.2 * current_atr
        sl = min(donchian_stop, atr_stop)
        target = price - 2.0 * current_atr

    return {
        "engine": "MODE_DON v2.2",
        "direction": direction,
        "entry": round(price, 2),
        "sl": round(sl, 2),
        "target": round(target, 2),
        "donchian_upper": round(upper, 2),
        "donchian_lower": round(lower, 2),
        "volume_ratio": round(current_vol / vol_sma[-1], 2) if vol_sma[-1] > 0 else 0,
        "vwap_distance_pct": round(vwap_distance_pct, 3),
    }


def _check_squeeze(candles, lookback=3):
    """
    Squeeze Gate: preceding candles must have contracting ATR or be inside bars.
    Returns True if squeeze is detected (valid breakout compression).
    """
    if len(candles) < lookback + 2:
        return True  # Not enough data, skip check

    # Check ATR contraction: each candle range smaller than previous
    ranges = []
    for i in range(len(candles) - lookback - 1, len(candles) - 1):
        ranges.append(float(candles[i]['high']) - float(candles[i]['low']))

    if len(ranges) < 2:
        return True

    # Contracting: at least 2 of 3 candles are smaller than the one before
    contracting = sum(1 for i in range(1, len(ranges)) if ranges[i] <= ranges[i-1])

    # Inside bar check: high lower, low higher than previous
    inside_bars = 0
    for i in range(len(candles) - lookback - 1, len(candles) - 1):
        if i > 0:
            h = float(candles[i]['high'])
            l = float(candles[i]['low'])
            ph = float(candles[i-1]['high'])
            pl = float(candles[i-1]['low'])
            if h <= ph and l >= pl:
                inside_bars += 1

    return contracting >= 1 or inside_bars >= 1
