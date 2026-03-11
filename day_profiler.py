"""
KiteAlerts V6.0 — Math Day Profiler
9-Type market classifier. Runs locally, no API calls.
Does NOT block trades — only provides context.
"""

import logging
from datetime import datetime, time as dtime
import indicators as ind


def classify_day(candles, highs, lows, closes, volumes, now=None):
    """
    Classify current market into one of 9 day types.

    Args:
        candles: list of candle dicts
        highs, lows, closes, volumes: parallel float lists
        now: datetime (IST)

    Returns:
        dict: {"tag": "...", "reasons": ["...", "..."]}
    """
    if len(closes) < 30:
        return {"tag": "Insufficient Data", "reasons": ["Need at least 30 candles"]}

    try:
        # Compute all needed indicators
        adx_vals, plus_di, minus_di = ind.adx(highs, lows, closes)
        current_adx = adx_vals[-1]
        rsi_vals = ind.rsi(closes)
        current_rsi = rsi_vals[-1]
        atr_vals = ind.atr(highs, lows, closes)
        current_atr = atr_vals[-1]
        vwap_vals = ind.vwap(candles)
        current_vwap = vwap_vals[-1]
        bb_upper, bb_mid, bb_lower = ind.bollinger_bands(closes)
        or_high, or_low = ind.opening_range(candles)
        price = closes[-1]

        # Session range
        session_high = max(highs)
        session_low = min(lows)
        session_range = session_high - session_low

        # VWAP crossing analysis
        vwap_crosses = 0
        candles_above_vwap = 0
        candles_below_vwap = 0
        for i in range(max(12, len(closes) - 60), len(closes)):
            if closes[i] > vwap_vals[i]:
                candles_above_vwap += 1
            else:
                candles_below_vwap += 1
            if i > 0 and ((closes[i] > vwap_vals[i]) != (closes[i-1] > vwap_vals[i-1])):
                vwap_crosses += 1

        vwap_one_side_pct = max(candles_above_vwap, candles_below_vwap) / max(candles_above_vwap + candles_below_vwap, 1) * 100

        # ATR analysis: first 9 candles (45 min opening)
        opening_atr_total = sum(highs[i] - lows[i] for i in range(min(9, len(highs))))
        daily_range_pct_in_opening = (opening_atr_total / session_range * 100) if session_range > 0 else 0

        # Structure: HH + LL in same hour
        recent_highs = highs[-12:]  # last hour
        recent_lows = lows[-12:]
        made_hh = len(recent_highs) > 6 and max(recent_highs[-6:]) > max(recent_highs[:6])
        made_ll = len(recent_lows) > 6 and min(recent_lows[-6:]) < min(recent_lows[:6])
        rotational = made_hh and made_ll

        # Expiry check
        is_expiry_afternoon = False
        if now:
            weekday = now.weekday()
            is_expiry_afternoon = weekday in [1, 3] and now.hour >= 13 and now.minute >= 30

        # ATR expansion (compare current to first hour)
        first_hour_atr = ind.atr(highs[:12], lows[:12], closes[:12])[-1] if len(closes) >= 12 else current_atr
        atr_expansion = current_atr / first_hour_atr if first_hour_atr > 0 else 1.0

        # Opening Range breakout + failure check (Liquidity Sweep)
        or_break_fail = False
        if or_high and or_low:
            broke_or_high = any(h > or_high for h in highs[-6:])
            broke_or_low = any(l < or_low for l in lows[-6:])
            if broke_or_high and price < or_high:
                or_break_fail = True
            if broke_or_low and price > or_low:
                or_break_fail = True

        # ============================================================
        # CLASSIFICATION CASCADE (priority order)
        # ============================================================

        # 9. Volatility Spike — ATR explosion
        if atr_expansion > 2.0:
            return {
                "tag": "Volatility Spike",
                "reasons": [
                    f"ATR expanded {atr_expansion:.1f}× vs morning",
                    "Possible macro news event — approach with caution",
                ],
            }

        # 8. Expiry Distortion
        if is_expiry_afternoon and current_adx < 20:
            return {
                "tag": "Expiry Distortion",
                "reasons": [
                    f"Expiry afternoon — ADX only {current_adx:.0f}",
                    "Price likely pinned to round-number strike",
                ],
            }

        # 1. Clean Trend Day — ADX > 30, price never meaningfully crosses VWAP
        if current_adx > 30 and vwap_crosses <= 2 and vwap_one_side_pct > 80:
            side = "above" if candles_above_vwap > candles_below_vwap else "below"
            return {
                "tag": "Clean Trend Day",
                "reasons": [
                    f"ADX {current_adx:.0f} — strong directional conviction",
                    f"Price held {side} VWAP for {vwap_one_side_pct:.0f}% of session",
                ],
            }

        # 5. Rotational Expansion
        if rotational:
            return {
                "tag": "Rotational Expansion",
                "reasons": [
                    "New HH AND new LL in the same hour — chaotic",
                    "Extremely dangerous: both sides getting stopped out",
                ],
            }

        # 7. Liquidity Sweep Trap
        if or_break_fail:
            return {
                "tag": "Liquidity Sweep Trap",
                "reasons": [
                    "Opening Range breakout failed and reversed",
                    "Retail breakout traders are trapped",
                ],
            }

        # 4. Fast Regime Flip — VWAP cross with heavy volume
        if vwap_crosses >= 3 and len(closes) > 20:
            # Check if latest cross was sustained 3+ candles
            last_side = closes[-1] > vwap_vals[-1]
            sustained = all((closes[-i-1] > vwap_vals[-i-1]) == last_side for i in range(min(3, len(closes)-1)))
            if sustained:
                return {
                    "tag": "Fast Regime Flip",
                    "reasons": [
                        f"VWAP crossed {vwap_crosses} times — regime shifting",
                        "Latest cross sustained for 3+ candles",
                    ],
                }

        # 3. Early Impulse → Sideways
        if daily_range_pct_in_opening > 75 and current_adx < 20 and len(closes) > 20:
            return {
                "tag": "Early Impulse → Sideways",
                "reasons": [
                    f"Opening 45 min accounts for {daily_range_pct_in_opening:.0f}% of daily range",
                    f"ADX collapsed to {current_adx:.0f} — momentum exhausted",
                ],
            }

        # 2. Normal Trend Day — ADX > 20, trending but bouncing off EMA
        if current_adx > 20 and vwap_one_side_pct > 60:
            return {
                "tag": "Normal Trend Day",
                "reasons": [
                    f"ADX {current_adx:.0f} — moderate trend strength",
                    f"Price on one side of VWAP {vwap_one_side_pct:.0f}% of time",
                ],
            }

        # 6. Range / Choppy — ADX < 15, flat VWAP
        if current_adx < 15:
            return {
                "tag": "Range / Choppy",
                "reasons": [
                    f"ADX {current_adx:.0f} — no directional conviction",
                    "VWAP flat — expect price to ping-pong between bands",
                ],
            }

        # Default: Normal Trend
        return {
            "tag": "Normal Trend Day",
            "reasons": [
                f"ADX {current_adx:.0f} | RSI {current_rsi:.0f}",
                f"Session range: {session_range:.1f} pts",
            ],
        }

    except Exception as e:
        logging.error(f"Day profiler error: {e}")
        return {"tag": "Classification Error", "reasons": [str(e)]}
