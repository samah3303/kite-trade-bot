"""
KiteAlerts V6.0 — MODE_VORTEX v1.0
The Order Flow Trap

Hunts retail liquidity traps using volume profile,
OI approximation, and CVD divergence.
Trades AGAINST retail breakouts at key levels.

NOTE: CVD is approximated from candle buy/sell volume imbalance.
      Full tick-level CVD would require a dedicated KiteTicker WebSocket.
"""

import logging
import indicators as ind
from config import VORTEX_CONFIG


def scan(candles, instrument_config):
    """
    Scan for MODE_VORTEX order flow trap signal.

    Args:
        candles: list of candle dicts (5-min)
        instrument_config: dict from config.INSTRUMENTS[name]

    Returns:
        dict signal or None
    """
    cfg = VORTEX_CONFIG

    if len(candles) < cfg["volume_profile_lookback"] + 5:
        return None

    highs = [float(c['high']) for c in candles]
    lows = [float(c['low']) for c in candles]
    closes = [float(c['close']) for c in candles]
    volumes = [float(c.get('volume', 0) or 0) for c in candles]

    price = closes[-1]
    current_atr = ind.atr(highs, lows, closes)[-1]

    # Skip if no volume data available
    if not any(v > 0 for v in volumes[-10:]):
        return None

    # ─────────────────────────────────────────────────────
    # STEP 1: LOCATION — Price at VAH / VAL / POC
    # ─────────────────────────────────────────────────────
    poc, vah, val = _compute_volume_profile(candles, cfg["volume_profile_lookback"])

    if poc is None:
        return None

    proximity = price * cfg["poc_proximity_pct"] / 100

    at_vah = abs(price - vah) <= proximity
    at_val = abs(price - val) <= proximity
    at_poc = abs(price - poc) <= proximity

    if not (at_vah or at_val or at_poc):
        return None

    location = "VAH" if at_vah else ("VAL" if at_val else "POC")

    # ─────────────────────────────────────────────────────
    # STEP 2: CONTEXT — Volume anomaly at the level
    # Heavy volume + rejection = institutional defense
    # ─────────────────────────────────────────────────────
    vol_sma = ind.volume_sma(volumes, 20)
    recent_vol = volumes[-1]
    vol_ratio = recent_vol / vol_sma[-1] if vol_sma[-1] > 0 else 0

    # Need at least moderate volume anomaly
    if vol_ratio < 1.3:
        return None

    # ─────────────────────────────────────────────────────
    # STEP 3: ACTION — CVD Divergence
    # Price makes new high but CVD drops (or vice versa)
    # ─────────────────────────────────────────────────────
    cvd = _approximate_cvd(candles, cfg["cvd_divergence_candles"])
    if cvd is None:
        return None

    divergence, div_direction = cvd

    if not divergence:
        return None

    # ─────────────────────────────────────────────────────
    # BUILD SIGNAL — Trade AGAINST the retail trap
    # ─────────────────────────────────────────────────────
    if div_direction == "BEARISH_DIV":
        # Price up but CVD down → retail buyers being absorbed → SHORT
        direction = "SHORT"
        sl = price + 0.8 * current_atr
        target = price - 1.5 * current_atr
    else:
        # Price down but CVD up → retail sellers being absorbed → LONG
        direction = "LONG"
        sl = price - 0.8 * current_atr
        target = price + 1.5 * current_atr

    return {
        "engine": "MODE_VORTEX v1.0",
        "direction": direction,
        "entry": round(price, 2),
        "sl": round(sl, 2),
        "target": round(target, 2),
        "location": location,
        "volume_ratio": round(vol_ratio, 2),
        "divergence": div_direction,
    }


def _compute_volume_profile(candles, lookback):
    """
    Compute simplified volume profile.
    Returns (POC, VAH, VAL) or (None, None, None).

    POC = price level with highest volume
    VAH/VAL = 70% value area boundaries
    """
    recent = candles[-lookback:]
    volumes = [float(c.get('volume', 0) or 0) for c in recent]

    if not any(v > 0 for v in volumes):
        return None, None, None

    # Build price-volume histogram with 20 bins
    all_highs = [float(c['high']) for c in recent]
    all_lows = [float(c['low']) for c in recent]
    range_high = max(all_highs)
    range_low = min(all_lows)
    range_size = range_high - range_low

    if range_size <= 0:
        return None, None, None

    num_bins = 20
    bin_size = range_size / num_bins
    bins = [0.0] * num_bins

    for c in recent:
        typical = (float(c['high']) + float(c['low']) + float(c['close'])) / 3
        vol = float(c.get('volume', 1) or 1)
        bin_idx = min(int((typical - range_low) / bin_size), num_bins - 1)
        bins[bin_idx] += vol

    # POC = bin with max volume
    poc_idx = bins.index(max(bins))
    poc = range_low + (poc_idx + 0.5) * bin_size

    # Value Area = 70% of total volume, expanding from POC
    total_vol = sum(bins)
    target_vol = total_vol * 0.7
    va_vol = bins[poc_idx]
    va_low_idx = poc_idx
    va_high_idx = poc_idx

    while va_vol < target_vol and (va_low_idx > 0 or va_high_idx < num_bins - 1):
        expand_up = bins[va_high_idx + 1] if va_high_idx < num_bins - 1 else 0
        expand_down = bins[va_low_idx - 1] if va_low_idx > 0 else 0

        if expand_up >= expand_down and va_high_idx < num_bins - 1:
            va_high_idx += 1
            va_vol += expand_up
        elif va_low_idx > 0:
            va_low_idx -= 1
            va_vol += expand_down
        else:
            break

    vah = range_low + (va_high_idx + 1) * bin_size
    val = range_low + va_low_idx * bin_size

    return poc, vah, val


def _approximate_cvd(candles, lookback=5):
    """
    Approximate CVD (Cumulative Volume Delta) from candle data.
    
    Buy volume ≈ volume × (close - low) / (high - low)
    Sell volume ≈ volume × (high - close) / (high - low)
    
    Returns: (divergence_detected, direction) or (None, None)
    """
    recent = candles[-lookback:]
    if len(recent) < lookback:
        return None

    # Build CVD
    cvd_values = []
    cumulative = 0
    for c in recent:
        h = float(c['high'])
        l = float(c['low'])
        cl = float(c['close'])
        vol = float(c.get('volume', 1) or 1)
        rng = h - l

        if rng > 0:
            buy_vol = vol * (cl - l) / rng
            sell_vol = vol * (h - cl) / rng
            delta = buy_vol - sell_vol
        else:
            delta = 0

        cumulative += delta
        cvd_values.append(cumulative)

    if len(cvd_values) < 3:
        return None

    # Check divergence
    prices = [float(c['close']) for c in recent]
    price_up = prices[-1] > prices[0]
    cvd_down = cvd_values[-1] < cvd_values[0]

    price_down = prices[-1] < prices[0]
    cvd_up = cvd_values[-1] > cvd_values[0]

    if price_up and cvd_down:
        return (True, "BEARISH_DIV")
    elif price_down and cvd_up:
        return (True, "BULLISH_DIV")

    return (False, None)
