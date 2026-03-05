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
    "vwap_hold_candles": 3,         # v2.1: Reduced from 5 to 3 for faster activation
    "atr_gate_multiplier": 1.1,     # ATR ≥ 1.1 × ATR at 9:45
}


# ===================================================================
# EARLY SESSION DONCHIAN (Before 11:00 AM)
# ===================================================================

EARLY_SESSION_DONCHIAN = {
    "period": 12,                    # 12-period lookback for early breakouts
    "cutoff_time": dtime(11, 0),     # Switch to standard after 11:00
    "earliest_breakout": dtime(10, 15),  # 12 * 5min from 9:15 = ~10:15
}


# ===================================================================
# CORRELATION PROTECTION
# ===================================================================

CORRELATION_PROTECTION = {
    "blocked_pairs": [("NIFTY", "SENSEX")],   # Block same-direction trades
    "allowed_pairs": [("NIFTY", "BANKNIFTY")], # Financial sector divergence OK
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

        # v2.1: Early session uses 12-period, after 11:00 uses standard
        "earliest_breakout_time": dtime(10, 15),  # Updated for early Donchian

        # Gates
        "atr_gate_multiplier": 1.2,
        "exhaustion_multiplier": 2.5,

        # v2.1: Breakout buffer
        "breakout_buffer_pct": 0.02,     # 0.02% (~5 pts)

        # Risk
        "risk_r": 1.0,
        "daily_loss_cap_r": -2.5,

        # v2.1: Trading hours start at 9:45
        "time_windows": [
            (dtime(9, 45), dtime(12, 45)),
            (dtime(13, 30), dtime(14, 45)),
        ],
    },

    "SENSEX": {
        "kite_symbol": os.getenv("SENSEX_INSTRUMENT", "BSE:SENSEX"),
        "display_name": "SENSEX",
        "emoji": "🟩",

        "donchian_entry_period": 18,
        "donchian_stop_period": 10,

        "earliest_breakout_time": dtime(10, 15),

        "atr_gate_multiplier": 1.2,
        "exhaustion_multiplier": 2.3,

        "breakout_buffer_pct": 0.02,     # 0.02% (~16 pts)

        "risk_r": 1.0,
        "daily_loss_cap_r": -2.5,

        "time_windows": [
            (dtime(9, 45), dtime(12, 45)),
            (dtime(13, 30), dtime(14, 45)),
        ],
    },

    "BANKNIFTY": {
        "kite_symbol": os.getenv("BANKNIFTY_INSTRUMENT", "NSE:NIFTY BANK"),
        "display_name": "BANK NIFTY",
        "emoji": "🟥",

        "donchian_entry_period": 15,
        "donchian_stop_period": 10,

        "earliest_breakout_time": dtime(10, 15),

        "atr_gate_multiplier": 1.3,
        "exhaustion_multiplier": 2.0,

        "breakout_buffer_pct": 0.03,     # 0.03% (~15 pts) — tighter for volatile instrument

        "risk_r": 0.75,
        "daily_loss_cap_r": -2.0,

        "time_windows": [
            (dtime(9, 45), dtime(11, 45)),
            (dtime(13, 45), dtime(14, 30)),
        ],
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
