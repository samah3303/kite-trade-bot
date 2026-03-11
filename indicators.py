"""
KiteAlerts V6.0 — Indicator Library
Pure functions. No state. No side effects.
"""

import numpy as np


def ema(data, period):
    """Exponential Moving Average."""
    if len(data) < period:
        return [data[0]] * len(data)
    result = [float(data[0])]
    k = 2.0 / (period + 1)
    for i in range(1, len(data)):
        result.append(float(data[i]) * k + result[-1] * (1 - k))
    return result


def sma(data, period):
    """Simple Moving Average."""
    result = []
    for i in range(len(data)):
        if i < period - 1:
            result.append(sum(data[:i+1]) / (i + 1))
        else:
            result.append(sum(data[i-period+1:i+1]) / period)
    return result


def rsi(closes, period=14):
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return [50.0] * len(closes)

    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    result = [50.0] * (period + 1)
    if avg_loss == 0:
        result[-1] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[-1] = 100 - (100 / (1 + rs))

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - (100 / (1 + rs)))

    return result


def atr(highs, lows, closes, period=14):
    """Average True Range."""
    if len(highs) < 2:
        return [0.0]

    trs = [highs[0] - lows[0]]
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        trs.append(tr)

    # Wilder's smoothed ATR
    result = [sum(trs[:period]) / period if len(trs) >= period else trs[0]]
    for i in range(period, len(trs)):
        result.append((result[-1] * (period - 1) + trs[i]) / period)

    # Pad front
    return [result[0]] * (len(highs) - len(result)) + result


def adx(highs, lows, closes, period=14):
    """
    Average Directional Index.
    Returns: (adx_values, plus_di, minus_di) — all same length as input.
    """
    n = len(highs)
    if n < period + 1:
        return [0.0] * n, [0.0] * n, [0.0] * n

    # Directional movement
    plus_dm = []
    minus_dm = []
    tr_list = []

    for i in range(1, n):
        up = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]

        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)

        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)

    # Wilder smoothing
    def wilder_smooth(data, p):
        result = [sum(data[:p])]
        for i in range(p, len(data)):
            result.append(result[-1] - result[-1] / p + data[i])
        return result

    sm_tr = wilder_smooth(tr_list, period)
    sm_plus = wilder_smooth(plus_dm, period)
    sm_minus = wilder_smooth(minus_dm, period)

    # +DI / -DI
    plus_di_vals = []
    minus_di_vals = []
    dx_vals = []

    for i in range(len(sm_tr)):
        pdi = (sm_plus[i] / sm_tr[i] * 100) if sm_tr[i] > 0 else 0
        mdi = (sm_minus[i] / sm_tr[i] * 100) if sm_tr[i] > 0 else 0
        plus_di_vals.append(pdi)
        minus_di_vals.append(mdi)

        di_sum = pdi + mdi
        dx = (abs(pdi - mdi) / di_sum * 100) if di_sum > 0 else 0
        dx_vals.append(dx)

    # ADX = smoothed DX
    adx_vals = []
    if len(dx_vals) >= period:
        adx_vals = [sum(dx_vals[:period]) / period]
        for i in range(period, len(dx_vals)):
            adx_vals.append((adx_vals[-1] * (period - 1) + dx_vals[i]) / period)

    # Pad to match input length
    pad_adx = n - len(adx_vals)
    pad_di = n - len(plus_di_vals)

    return (
        [0.0] * pad_adx + adx_vals,
        [0.0] * pad_di + plus_di_vals,
        [0.0] * pad_di + minus_di_vals,
    )


def bollinger_bands(closes, period=20, std_dev=2.0):
    """Returns (upper, middle, lower) bands."""
    middle = sma(closes, period)
    upper = []
    lower = []

    for i in range(len(closes)):
        if i < period - 1:
            std = np.std(closes[:i+1]) if i > 0 else 0
        else:
            std = np.std(closes[i-period+1:i+1])
        upper.append(middle[i] + std_dev * std)
        lower.append(middle[i] - std_dev * std)

    return upper, middle, lower


def vwap(candles):
    """Volume-Weighted Average Price from candle list."""
    cum_vol = 0
    cum_pv = 0
    result = []

    for c in candles:
        typical = (float(c['high']) + float(c['low']) + float(c['close'])) / 3
        vol = float(c.get('volume', 1) or 1)
        cum_vol += vol
        cum_pv += typical * vol
        result.append(cum_pv / cum_vol if cum_vol > 0 else typical)

    return result


def donchian(highs, lows, period):
    """
    Donchian Channel.
    Returns (upper, lower) — upper = highest high, lower = lowest low
    of the previous N candles (excluding current).
    """
    if len(highs) <= period:
        return None, None

    upper = max(highs[-(period+1):-1])
    lower = min(lows[-(period+1):-1])
    return upper, lower


def donchian_series(highs, lows, period):
    """Full Donchian channel series for trailing stops."""
    uppers = []
    lowers = []
    for i in range(len(highs)):
        if i < period:
            uppers.append(max(highs[:i+1]))
            lowers.append(min(lows[:i+1]))
        else:
            uppers.append(max(highs[i-period:i]))
            lowers.append(min(lows[i-period:i]))
    return uppers, lowers


def volume_sma(volumes, period=20):
    """Simple moving average of volume."""
    return sma(volumes, period)


def slope(series, lookback=3):
    """Linear slope over last N values."""
    if len(series) < lookback:
        return 0.0
    segment = series[-lookback:]
    return (segment[-1] - segment[0]) / lookback


def opening_range(candles, market_open_hour=9, market_open_min=15, or_minutes=30):
    """
    Opening Range High/Low from first N minutes of session.
    Returns (or_high, or_low) or (None, None).
    """
    or_candles = []
    for c in candles:
        dt = c['date']
        if hasattr(dt, 'hour'):
            # Within first 30 mins from 9:15
            mins_since_open = (dt.hour - market_open_hour) * 60 + (dt.minute - market_open_min)
            if 0 <= mins_since_open < or_minutes:
                or_candles.append(c)

    if not or_candles:
        return None, None

    or_high = max(float(c['high']) for c in or_candles)
    or_low = min(float(c['low']) for c in or_candles)
    return or_high, or_low
