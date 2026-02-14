"""
RIJIN SYSTEM - Configuration
Version: 3.0 (IMPULSE-BASED TIMING MODEL)
Philosophy: Signals generate opportunity. Context decides permission.
v3.0: Expansion measured from impulse origin, not day extremes.
      This fixes the core timing architecture flaw.
"""

from enum import Enum
from datetime import time as dtime

# ===================================================================
# DAY TYPES (Human-Readable, Telegram-Visible)
# ===================================================================
class DayType(Enum):
    CLEAN_TREND = "Clean Trend Day"
    NORMAL_TREND = "Normal Trend Day"
    EARLY_IMPULSE_SIDEWAYS = "Early Impulse → Sideways Day"
    RANGE_CHOPPY = "Range / Choppy Day"
    VOLATILITY_SPIKE = "Volatility Spike / News Shock"
    EXPIRY_DISTORTION = "Expiry Distortion Day"
    UNKNOWN = "Unknown (Early Data)"


# ===================================================================
# INSTRUMENT EXPIRY MEMORY (HARD-CODED FACTS)
# ===================================================================
EXPIRY_DAYS = {
    "NIFTY": 1,      # Tuesday (0=Mon, 1=Tue, ...)
    "SENSEX": 3,     # Thursday
}

# v2.4: Expiry Intelligence Layer
EXPIRY_INTELLIGENCE_CONFIG = {
    "signal_reduction_pct": 0.30,      # Reduce allowed signals by 30%
    "no_entry_after": dtime(14, 45),   # No new entries after 2:45 PM
}



# ===================================================================
# DAY TYPE ENGINE SCHEDULE
# ===================================================================
DAY_TYPE_CHECK_TIMES = [
    dtime(10, 0),
    dtime(10, 30),
    dtime(11, 0),
    dtime(11, 30),
    dtime(12, 0),
    dtime(12, 30),
    dtime(13, 0),
    dtime(13, 30),
    dtime(14, 0),
    dtime(14, 30),
]

# After this time, NO new trades (only manage existing)
TRADING_CUTOFF = dtime(14, 30)


# ===================================================================
# DAY TYPE CLASSIFICATION THRESHOLDS (v2.4 CALIBRATED)
# ===================================================================
DAY_TYPE_THRESHOLDS = {
    "clean_trend": {
        "atr_expansion_ratio": 1.05,     # v2.4: CALIBRATED (was 1.1)
        "min_slope": 0.15,               # EMA20 slope strength
        "rsi_bull_min": 60,              # RSI holding above
        "rsi_bear_max": 40,              # RSI holding below
    },
    "normal_trend": {
        "atr_expansion_ratio": 0.8,      # Moderate expansion
        "min_slope": 0.08,
    },
    "range_choppy": {
        "max_atr_ratio": 0.6,            # Contraction threshold
        "rsi_oscillation_range": (40, 60),
        "max_slope": 0.05,
    },
    "volatility_spike": {
        "single_candle_atr": 0.7,        # Single candle > 0.7× ATR
        "reversal_pct": 0.60,            # 60% reversal within 15min
        "pause_duration_min": 30,        # Pause trading for 30min
    },
}



# ===================================================================
# DAY TYPE DEGRADATION PATH (ONLY WORSE, NEVER BETTER)
# ===================================================================
DAY_TYPE_HIERARCHY = {
    DayType.CLEAN_TREND: 1,
    DayType.NORMAL_TREND: 2,
    DayType.EARLY_IMPULSE_SIDEWAYS: 3,
    DayType.RANGE_CHOPPY: 4,
    DayType.EXPIRY_DISTORTION: 4,  # Same severity as choppy
    DayType.VOLATILITY_SPIKE: 5,    # v2.4: Most hostile
}

# Immediate downgrade (no confirmation needed)
IMMEDIATE_DOWNGRADE = [
    DayType.RANGE_CHOPPY,
    DayType.EXPIRY_DISTORTION,
    DayType.VOLATILITY_SPIKE,  # v2.4: Added
]


# ===================================================================
# IMPULSE DETECTION CONFIG (v3.0 FOUNDATION)
# ===================================================================
# Detects where directional move actually STARTS
IMPULSE_DETECTION = {
    "min_candles_for_impulse": 2,       # 2 strong candles
    "min_range_atr_multiple": 0.6,      # Each candle > 0.6× ATR
    "require_swing_break": True,        # Must break prior swing
    "min_ema_slope_pct": 0.03,          # EMA20 slope threshold
}


# ===================================================================
# SESSION TREND PHASE ENGINE (v3.0 IMPULSE-BASED MODEL - REFINED)
# ===================================================================
# Expansion measured from IMPULSE ORIGIN, not day extremes
# v3.0.1: Tightened after real MODE_F backtest showed too many late signals
SESSION_TREND_PHASE = {
    "early": {
        "max_expansion_atr": 1.2,     # v3.0.1: 0-1.2× ATR (was 1.5) - stricter
        "policy": "FULLY_ALLOWED",     # MODE_F unrestricted
    },
    "mid": {
        "min_expansion_atr": 1.2,      # v3.0.1: 1.2-2.0× ATR (was 1.5-3.0)
        "max_expansion_atr": 2.0,      # Tighter to prevent late entries
        "policy": "CONDITIONAL",        # MODE_F with strict conditions
        "conditions": {
            "max_pullback_atr": 0.5,    # v3.0.1: Tighter (was 0.8)
            "min_rsi": 50,               # v3.0.1: Raised to 50 (was 48)
            "require_structure": True,   # HH-HL or LH-LL structure intact
        }
    },
    "late": {
        "min_expansion_atr": 2.0,      # v3.0.1: > 2.0× ATR (was 3.0) - tighter
        "policy": "DISABLED",           # MODE_F completely blocked
        "reason": "Late-cycle exhaustion - move > 2× ATR from impulse"
    },
    
    # v3.0: Hard cutoffs
    "absolute_max_expansion": 2.5,      # No trades beyond this (was 3.5)
}



# ===================================================================
# OPENING IMPULSE MODULE (v2.4 CALIBRATED)
# ===================================================================
OPENING_IMPULSE_CONFIG = {
    "time_start": dtime(9, 20),      # v2.4: Slightly delayed for stability
    "time_end": dtime(10, 0),        # Extended window
    "min_move_atr_multiple": 0.4,    # v2.4: Relaxed from 0.6
    "max_trades_per_index": 1,
    "risk_r": 0.5,
}


# ===================================================================
# CONSECUTIVE LOSS PROTECTION (v3.0.1)
# ===================================================================
# Prevents drawdown spirals by pausing after consecutive losses
CONSECUTIVE_LOSS_LIMIT = {
    "max_consecutive_losses": 2,      # Stop after 2 losses in a row
    "pause_duration_minutes": 60,     # Pause for 1 hour
    "reset_on_win": True,              # Reset counter on any win
}


# ===================================================================
# EXECUTION GATES THRESHOLDS (v2.4 STRUCTURAL FIX)
# ===================================================================
EXECUTION_GATES = {
    # Gate 1: Move Exhaustion (v2.4: Back to 1.5× after adding Phase Filter)
    # Phase filter prevents late signals, so Gate 1 maintains proper threshold
    "exhaustion_atr_multiple": 1.5,     # Reverted from 1.2×
    "exhaustion_day_range_pct": 0.70,
    
    # Gate 2: Time + Day Type cutoff
    "late_cutoff_time": dtime(12, 30),
    
    # Gate 3: RSI Compression + Signal Clustering
    "rsi_compression_min": 48,
    "rsi_compression_max": 62,
    "rsi_compression_candles": 10,
    
    # v2.4: Signal Clustering Protection
    "cluster_sl_count": 2,               # 2 SLs within window
    "cluster_time_window_min": 45,        # Within 45 minutes
}


# ===================================================================
# MODE PERMISSION MATRIX
# ===================================================================
MODE_F_ALLOWED_DAY_TYPES = [
    DayType.CLEAN_TREND,
    DayType.NORMAL_TREND,
]

MODE_S_CORE_STABILITY_ALLOWED = [
    DayType.CLEAN_TREND,
    DayType.NORMAL_TREND,
]

MODE_S_LIQUIDITY_ALLOWED = [
    DayType.CLEAN_TREND,
    DayType.NORMAL_TREND,
]

MODE_S_LIQUIDITY_CUTOFF = dtime(13, 0)
MODE_S_CORE_CUTOFF = dtime(13, 30)


# ===================================================================
# CORRELATION BRAKE
# ===================================================================
CORRELATION_BRAKE_CONFIG = {
    "sl_count_trigger": 2,          # 2 SLs within window
    "time_window_minutes": 60,      # Within 60 minutes
    "block_duration_minutes": 60,   # Block other index for 60 min
}


# ===================================================================
# SYSTEM STOP STATE TRIGGERS
# ===================================================================
SYSTEM_STOP_TRIGGERS = {
    "day_type_range_choppy": True,
    "consecutive_blocks": 3,
    "sl_count_after_time": 2,
    "sl_after_time": dtime(11, 30),
}


# ===================================================================
# EXPECTED TRADE COUNTS (v2.4 CALIBRATED - Realistic Targets)
# ===================================================================
EXPECTED_TRADE_COUNT = {
    DayType.CLEAN_TREND: (3, 5),           # v2.4: More realistic
    DayType.NORMAL_TREND: (2, 3),          # v2.4: Balanced
    DayType.EARLY_IMPULSE_SIDEWAYS: (0, 1),
    DayType.RANGE_CHOPPY: (0, 0),
    DayType.VOLATILITY_SPIKE: (0, 0),       # v2.4: Added
    DayType.EXPIRY_DISTORTION: (0, 1),
}


# ===================================================================
# TELEGRAM MESSAGE TEMPLATES
# ===================================================================
TELEGRAM_TEMPLATES = {
    "trade_allowed": """
🔔 <b>CONFIRMED SIGNAL</b>
INSTRUMENT: {instrument}
TYPE: {direction}
MODE: {mode}

📊 <b>MARKET CONTEXT</b>
DAY TYPE: {day_type}
DAY TYPE CHECK: {check_time} IST
EXPIRY CONTEXT: {expiry_context}

💰 <b>TRADE DETAILS</b>
ENTRY: {entry}
SL: {sl} | TGT: {target}
PATTERN: {pattern}

EXECUTION STATUS: ✅ <b>ALLOWED</b>
""",
    
    "trade_blocked": """
⚠️ <b>SIGNAL DETECTED (BLOCKED)</b>
INSTRUMENT: {instrument}
TYPE: {direction}
MODE: {mode}

📊 <b>MARKET CONTEXT</b>
DAY TYPE: {day_type}
DAY TYPE CHECK: {check_time} IST

EXECUTION STATUS: ❌ <b>BLOCKED</b>
Reason:
• {reason}
""",
    
    "day_type_downgrade": """
🚨 <b>MARKET STATUS UPDATE</b>

DAY TYPE: {day_type}
TIME: {time} IST

ACTION:
❌ Directional trades blocked
🛡 Capital Protection Mode ON

{additional_context}
""",
    
    "system_stop": """
🛑 <b>SYSTEM STATUS: STOPPED</b>

Reason:
• Market conditions hostile
• Capital protection active

Next review: Next trading day

{context}
""",
    
    "opening_impulse": """
⚡ <b>OPENING IMPULSE SIGNAL</b>
INSTRUMENT: {instrument}
TYPE: {direction}
MOVE: {move_atr}× ATR

RISK: 0.5R (Limited)
TIME: {time} IST

EXPIRY CONTEXT: {expiry_context}
STATUS: {status}
""",
}
