"""
MODE_DON Configuration — Regime-Gated Breakout Expansion Engine
Fully deterministic. No AI. No oscillators.

Instruments: NIFTY 50, SENSEX, BANK NIFTY
"""

import os
from datetime import time as dtime
from enum import Enum


# ===================================================================
# ENUMS
# ===================================================================

class DayRegime(Enum):
    CLEAN_TREND = "Clean Trend"
    NORMAL_TREND = "Normal Trend"
    ROTATION = "Rotation"
    RANGE = "Range"
    UNKNOWN = "Unknown"


class TradeDirection(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


# ===================================================================
# REGIME SCORING THRESHOLDS
# ===================================================================

REGIME_THRESHOLDS = {
    # Metric 1: Expansion Ratio (Session Range / Opening 30-min Range)
    "expansion_ratio": {
        "high": 2.5,    # score 2
        "medium": 1.8,  # score 1
    },

    # Metric 2: VWAP Stability (% closes same side since 10:00)
    "vwap_stability": {
        "high": 0.75,   # score 2
        "medium": 0.60, # score 1
    },

    # Metric 3: Structure Continuity (directional legs count)
    "structure_legs": {
        "high": 3,      # score 2 (3+ clean legs)
        "medium": 2,    # score 1
    },

    # Metric 4: ATR Expansion (ATR at 12:00 / ATR at 9:45)
    "atr_expansion": {
        "high": 1.2,    # score 2
        "medium": 1.0,  # score 1
    },
}

# Score → Regime mapping
REGIME_CLASSIFICATION = {
    # score_range: DayRegime
    (7, 8): DayRegime.CLEAN_TREND,
    (5, 6): DayRegime.NORMAL_TREND,
    (3, 4): DayRegime.ROTATION,
    (0, 2): DayRegime.RANGE,
}

# Regimes that allow MODE_DON trading
ALLOWED_REGIMES = {DayRegime.CLEAN_TREND, DayRegime.NORMAL_TREND}

# Regime hierarchy for one-way degradation (higher = worse)
REGIME_HIERARCHY = {
    DayRegime.CLEAN_TREND: 1,
    DayRegime.NORMAL_TREND: 2,
    DayRegime.ROTATION: 3,
    DayRegime.RANGE: 4,
    DayRegime.UNKNOWN: 5,
}


# ===================================================================
# DEGRADATION THRESHOLDS (Post 12 PM)
# ===================================================================

DEGRADATION_RULES = {
    "vwap_flip_hold_minutes": 45,   # VWAP flips and holds opposite side 45 min
    "atr_contraction_vs_morning": 1.0,  # ATR contracts below morning ATR
    "structure_break_count": 2,     # Two alternating structure breaks
}


# ===================================================================
# PROVISIONAL EARLY REGIME GATE (Pre-12 PM Trading)
# ===================================================================

EARLY_REGIME_GATE = {
    "expansion_min": 1.5,           # Current Range ≥ 1.5 × Opening 30-min Range
    "vwap_hold_candles": 5,         # Price must hold one side of VWAP for 5 consecutive candles
    "atr_gate_multiplier": 1.1,     # ATR ≥ 1.1 × ATR at 9:45
}


# ===================================================================
# INSTRUMENT CONFIGURATIONS
# ===================================================================

INSTRUMENTS = {
    "NIFTY": {
        "kite_symbol": os.getenv("NIFTY_INSTRUMENT", "NSE:NIFTY 50"),
        "display_name": "NIFTY 50",
        "emoji": "🟦",

        # Donchian parameters
        "donchian_entry_period": 20,     # 20-period for entry breakout
        "donchian_stop_period": 10,      # 10-period for trailing stop

        # Lookback formation: 20 × 5min = 100min from 9:15 → earliest ≈ 10:55
        "earliest_breakout_time": dtime(10, 55),

        # Gates
        "atr_gate_multiplier": 1.2,      # ATR must be ≥ 1.2× morning ATR
        "exhaustion_multiplier": 2.5,    # Block if move ≥ 2.5× avg leg

        # Risk
        "risk_r": 1.0,                   # 1R per trade
        "daily_loss_cap_r": -2.5,        # Stop this instrument at -2.5R

        # Time windows: (start, end)
        "time_windows": [
            (dtime(9, 30), dtime(12, 45)),
            (dtime(13, 30), dtime(14, 45)),
        ],
    },

    "SENSEX": {
        "kite_symbol": os.getenv("SENSEX_INSTRUMENT", "BSE:SENSEX"),
        "display_name": "SENSEX",
        "emoji": "🟩",

        "donchian_entry_period": 18,
        "donchian_stop_period": 10,

        # Lookback formation: 18 × 5min = 90min from 9:15 → earliest ≈ 10:45
        "earliest_breakout_time": dtime(10, 45),

        "atr_gate_multiplier": 1.2,
        "exhaustion_multiplier": 2.3,

        "risk_r": 1.0,
        "daily_loss_cap_r": -2.5,

        "time_windows": [
            (dtime(9, 30), dtime(12, 45)),
            (dtime(13, 30), dtime(14, 45)),
        ],
    },

    "BANKNIFTY": {
        "kite_symbol": os.getenv("BANKNIFTY_INSTRUMENT", "NSE:NIFTY BANK"),
        "display_name": "BANK NIFTY",
        "emoji": "🟥",

        "donchian_entry_period": 15,
        "donchian_stop_period": 10,

        # Lookback formation: 15 × 5min = 75min from 9:15 → earliest ≈ 10:30
        "earliest_breakout_time": dtime(10, 30),

        "atr_gate_multiplier": 1.3,      # Tighter gate for aggressive instrument
        "exhaustion_multiplier": 2.0,

        "risk_r": 0.75,                   # Reduced risk
        "daily_loss_cap_r": -2.0,         # Tighter daily cap

        "time_windows": [
            (dtime(9, 30), dtime(11, 45)),         # Morning only by default
            (dtime(13, 45), dtime(14, 30)),         # Afternoon only if Clean Trend
        ],
        # Special: afternoon window only allowed for Clean Trend
        "afternoon_requires_clean_trend": True,
    },
}


# ===================================================================
# SYSTEM-LEVEL RISK GOVERNANCE
# ===================================================================

SYSTEM_RISK = {
    "max_concurrent_trades": 3,
    "system_daily_loss_cap_r": -3.0,
    "consecutive_loss_disable": 3,       # 3 consecutive losses → disable instrument for day
    "no_same_direction_double": True,    # No same-direction double entries on same instrument
}


# ===================================================================
# REGIME COMPUTATION TIMING
# ===================================================================

REGIME_COMPUTE_TIME = dtime(12, 0)       # Compute regime at exactly 12:00 IST
REGIME_DATA_START = dtime(9, 15)         # Use data from 9:15
REGIME_EARLY_ATR_TIME = dtime(9, 45)     # Morning ATR baseline


# ===================================================================
# TELEGRAM TEMPLATES
# ===================================================================

TELEGRAM_ENTRY_TEMPLATE = """
{emoji} <b>MODE_DON | {instrument} | {direction}</b>

⏰ Time: {time} IST
📊 Day Type: {regime} (Score {score}/8)
📈 Donchian({period}) Breakout Confirmed

💰 Entry: {entry}
🛑 Stop: {stop}
⚖️ Risk: {risk_r}R

📏 ATR Ratio: {atr_ratio:.2f}×
📐 Session Expansion: {expansion:.1f}×

🤖 AI Layer: <b>NOT USED</b>
""".strip()

TELEGRAM_EXIT_TEMPLATE = """
{emoji} <b>MODE_DON EXIT | {instrument}</b>

⏰ Time: {time} IST
📍 {direction} → {exit_type}

💰 Entry: {entry} → Exit: {exit_price}
📊 P&L: {pnl_r:+.2f}R

🤖 AI Layer: <b>NOT USED</b>
""".strip()

TELEGRAM_REGIME_TEMPLATE = """
📊 <b>MODE_DON | 12 PM REGIME REPORT</b>

{instrument_reports}

🔒 System Status: {system_status}
""".strip()

TELEGRAM_INSTRUMENT_REGIME = """
{emoji} <b>{instrument}</b>: {regime} (Score {score}/8)
  • Expansion: {expansion:.1f}× | VWAP: {vwap_pct:.0f}%
  • Legs: {legs} | ATR: {atr_ratio:.2f}×
  • Status: {status}
""".strip()
