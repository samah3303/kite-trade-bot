"""
KiteAlerts V6.0 — Unified Configuration
Tri-Core: MODE_DON v2.2 | RIJIN v3.2 | MODE_VORTEX v1.0
4 Instruments: NIFTY · BANKNIFTY · SENSEX · CRUDE OIL
"""

import os
from datetime import time as dtime
from dotenv import load_dotenv

load_dotenv()

# ===================================================================
# INSTRUMENT MATRIX
# ===================================================================

INSTRUMENTS = {
    "NIFTY": {
        "kite_symbol": os.getenv("NIFTY_INSTRUMENT", "NSE:NIFTY 50"),
        "display_name": "NIFTY 50",
        "emoji": "🟦",
        "active_window": (dtime(9, 45), dtime(15, 15)),
        "expiry_day": 3,            # Thursday (0=Mon)
        "expiry_warning_after": dtime(13, 30),

        # MODE_DON params
        "donchian_period": 20,
        "donchian_stop_period": 10,
        "breakout_buffer_pct": 0.02,
        "exhaustion_multiplier": 2.5,

        # Risk
        "risk_r": 1.0,
    },

    "BANKNIFTY": {
        "kite_symbol": os.getenv("BANKNIFTY_INSTRUMENT", "NSE:NIFTY BANK"),
        "display_name": "BANK NIFTY",
        "emoji": "🟥",
        "active_window": (dtime(9, 45), dtime(15, 15)),
        "expiry_day": 2,            # Wednesday
        "expiry_warning_after": dtime(13, 30),

        "donchian_period": 20,
        "donchian_stop_period": 10,
        "breakout_buffer_pct": 0.03,
        "exhaustion_multiplier": 2.0,

        "risk_r": 0.75,
    },

    "SENSEX": {
        "kite_symbol": os.getenv("SENSEX_INSTRUMENT", "BSE:SENSEX"),
        "display_name": "SENSEX",
        "emoji": "🟩",
        "active_window": (dtime(9, 45), dtime(15, 15)),
        "expiry_day": 3,            # Thursday
        "expiry_warning_after": dtime(13, 30),

        "donchian_period": 20,
        "donchian_stop_period": 10,
        "breakout_buffer_pct": 0.02,
        "exhaustion_multiplier": 2.3,

        "risk_r": 1.0,
    },

    "CRUDEOIL": {
        "kite_symbol": os.getenv("CRUDEOIL_INSTRUMENT", "MCX:CRUDEOIL26APRFUT"),
        "display_name": "CRUDE OIL",
        "emoji": "🛢️",
        "active_window": (dtime(9, 0), dtime(23, 30)),
        "prime_time": (dtime(18, 0), dtime(22, 0)),    # US Market Open
        "expiry_day": None,
        "expiry_warning_after": None,

        # Crude uses absolute buffer, not percentage
        "donchian_period": 20,
        "donchian_stop_period": 10,
        "breakout_buffer_abs": 5,   # +5 absolute points
        "breakout_buffer_pct": None,
        "exhaustion_multiplier": 2.0,

        # Inventory blackout: Wednesday 7:45 PM - 8:45 PM IST
        "inventory_blackout_day": 2,    # Wednesday
        "inventory_blackout_start": dtime(19, 45),
        "inventory_blackout_end": dtime(20, 45),

        "risk_r": 1.0,
    },
}


# ===================================================================
# MODE_DON v2.2 — BREAKOUT SNIPER CONFIG
# ===================================================================

MODE_DON_CONFIG = {
    "donchian_period": 20,
    "volume_sma_period": 20,
    "volume_breakout_multiplier": 1.2,      # Volume > 1.2× SMA(20)
    "squeeze_candles": 3,                    # 3 preceding candles must contract
    "rubber_band_max_vwap_pct": 0.5,        # Max 0.5% from VWAP
}


# ===================================================================
# RIJIN v3.2 — TACTICAL ADAPTER CONFIG
# ===================================================================

RIJIN_CONFIG = {
    # Gear 1: Trend Pullback
    "ema_trend_period": 20,
    "gear1_pullback_tolerance": 0.001,       # 0.1% from EMA20

    # Gear 2: Mean Reversion
    "bollinger_period": 20,
    "bollinger_std": 2.0,
    "rsi_period": 14,
    "rsi_overbought": 75,
    "rsi_oversold": 25,
    "adx_period": 14,
    "adx_trend_threshold": 25,               # Gear 2 disabled if ADX > 25

    # Gear 3: Momentum Impulse
    "impulse_atr_multiplier": 1.5,           # Body > 1.5× ATR
}


# ===================================================================
# MODE_VORTEX v1.0 — ORDER FLOW TRAP CONFIG
# ===================================================================

VORTEX_CONFIG = {
    "volume_profile_lookback": 50,           # Candles for volume profile
    "poc_proximity_pct": 0.1,                # Within 0.1% of POC/VAH/VAL
    "oi_change_threshold": 5.0,              # % change in ATM OI to consider significant
    "cvd_divergence_candles": 5,             # CVD divergence lookback
}


# ===================================================================
# SYSTEM RISK GOVERNANCE
# ===================================================================

SYSTEM_RISK = {
    "max_concurrent_trades": 3,
    "system_daily_loss_cap_r": -3.0,
    "consecutive_loss_disable": 3,
}


# ===================================================================
# DAY TYPE LABELS (9 categories)
# ===================================================================

DAY_TYPES = [
    "Clean Trend Day",
    "Normal Trend Day",
    "Early Impulse → Sideways",
    "Fast Regime Flip",
    "Rotational Expansion",
    "Range / Choppy",
    "Liquidity Sweep Trap",
    "Expiry Distortion",
    "Volatility Spike",
]


# ===================================================================
# TIMING
# ===================================================================

CANDLE_INTERVAL = "5minute"
SCAN_INTERVAL_SECONDS = 30
MIN_CANDLES_REQUIRED = 50
MARKET_OPEN = dtime(9, 15)
