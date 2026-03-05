"""
MODE_DON Engine — Regime-Gated Donchian Breakout Expansion Engine
Fully deterministic. No AI. No EMA. No RSI.

Architecture:
  Phase 1: 12 PM Regime Classification (4-metric scoring)
  Phase 2: Activation Rules (regime + time + ATR gate + exhaustion)
  Phase 3: Donchian Breakout Entry (close confirmation only)
  Phase 4: Trailing Stop (opposite 10-period Donchian)
  Phase 5: Risk Governance (per-instrument + system-level)
"""

import os
import logging
import threading
from datetime import datetime, timedelta, time as dtime
from collections import defaultdict

import pytz
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Shared utilities
from unified_engine import simple_ema, calculate_atr, send_telegram_message

# Token health
import token_manager

# Config
from mode_don_config import (
    DayRegime, TradeDirection,
    REGIME_THRESHOLDS, REGIME_CLASSIFICATION, ALLOWED_REGIMES,
    REGIME_HIERARCHY, DEGRADATION_RULES, EARLY_REGIME_GATE,
    INSTRUMENTS, SYSTEM_RISK,
    REGIME_COMPUTE_TIME, REGIME_DATA_START, REGIME_EARLY_ATR_TIME,
    TELEGRAM_ENTRY_TEMPLATE, TELEGRAM_EXIT_TEMPLATE,
    TELEGRAM_REGIME_TEMPLATE, TELEGRAM_INSTRUMENT_REGIME,
)

load_dotenv()

IST = pytz.timezone('Asia/Kolkata')

def now_ist():
    return datetime.now(IST)


# ===================================================================
# REGIME ENGINE — Phase 1
# ===================================================================

class RegimeEngine:
    """
    Scores 4 metrics at 12:00 PM to classify the day.
    Score 0-8 → Clean Trend / Normal Trend / Rotation / Range.
    """

    def _score_expansion_ratio(self, ratio):
        t = REGIME_THRESHOLDS["expansion_ratio"]
        if ratio >= t["high"]:
            return 2
        elif ratio >= t["medium"]:
            return 1
        return 0

    def _score_vwap_stability(self, pct_same_side):
        t = REGIME_THRESHOLDS["vwap_stability"]
        if pct_same_side >= t["high"]:
            return 2
        elif pct_same_side >= t["medium"]:
            return 1
        return 0

    def _score_structure_continuity(self, leg_count):
        t = REGIME_THRESHOLDS["structure_legs"]
        if leg_count >= t["high"]:
            return 2
        elif leg_count >= t["medium"]:
            return 1
        return 0

    def _score_atr_expansion(self, atr_ratio):
        t = REGIME_THRESHOLDS["atr_expansion"]
        if atr_ratio >= t["high"]:
            return 2
        elif atr_ratio >= t["medium"]:
            return 1
        return 0

    def compute_regime(self, candles):
        """
        Compute regime from 9:15-12:00 candle data.
        Returns: (DayRegime, total_score, metric_details)
        """
        if len(candles) < 10:
            return DayRegime.UNKNOWN, 0, {}

        try:
            closes = [float(c['close']) for c in candles]
            highs = [float(c['high']) for c in candles]
            lows = [float(c['low']) for c in candles]
            volumes = [float(c.get('volume', 0)) for c in candles]

            # --- Metric 1: Expansion Ratio ---
            # Opening 30-min range (first 6 five-minute candles)
            opening_candles = candles[:min(6, len(candles))]
            opening_high = max(float(c['high']) for c in opening_candles)
            opening_low = min(float(c['low']) for c in opening_candles)
            opening_range = opening_high - opening_low

            session_high = max(highs)
            session_low = min(lows)
            session_range = session_high - session_low

            expansion_ratio = session_range / opening_range if opening_range > 0 else 0
            s1 = self._score_expansion_ratio(expansion_ratio)

            # --- Metric 2: VWAP Stability ---
            # Calculate VWAP
            cumulative_vp = 0
            cumulative_v = 0
            vwap_values = []
            for i, c in enumerate(candles):
                typical = (float(c['high']) + float(c['low']) + float(c['close'])) / 3
                vol = float(c.get('volume', 1))  # avoid div by zero
                cumulative_vp += typical * vol
                cumulative_v += vol
                vwap_values.append(cumulative_vp / cumulative_v if cumulative_v > 0 else typical)

            # % of closes on same side of VWAP since ~10:00 (skip first ~9 candles)
            post_10am_start = min(9, len(candles) - 1)
            if len(candles) > post_10am_start + 1:
                first_side = closes[post_10am_start] > vwap_values[post_10am_start]
                same_side_count = 0
                total_post_10 = 0
                for i in range(post_10am_start, len(candles)):
                    total_post_10 += 1
                    is_above = closes[i] > vwap_values[i]
                    if is_above == first_side:
                        same_side_count += 1
                vwap_pct = same_side_count / total_post_10 if total_post_10 > 0 else 0
            else:
                vwap_pct = 0
            s2 = self._score_vwap_stability(vwap_pct)

            # --- Metric 3: Structure Continuity ---
            legs = self._count_directional_legs(candles)
            s3 = self._score_structure_continuity(legs)

            # --- Metric 4: ATR Expansion ---
            atr_all = calculate_atr(highs, lows, closes, 14)
            atr_current = float(atr_all[-1]) if len(atr_all) > 0 else 0
            # Morning ATR (at ~9:45, index ~6)
            atr_morning_idx = min(6, len(atr_all) - 1)
            atr_morning = float(atr_all[atr_morning_idx]) if atr_morning_idx >= 0 else atr_current
            atr_ratio = atr_current / atr_morning if atr_morning > 0 else 1.0
            s4 = self._score_atr_expansion(atr_ratio)

            total_score = s1 + s2 + s3 + s4

            # Classify
            regime = DayRegime.RANGE  # default
            for (lo, hi), reg in REGIME_CLASSIFICATION.items():
                if lo <= total_score <= hi:
                    regime = reg
                    break

            details = {
                "expansion_ratio": round(expansion_ratio, 2),
                "expansion_score": s1,
                "vwap_pct": round(vwap_pct * 100, 1),
                "vwap_score": s2,
                "structure_legs": legs,
                "structure_score": s3,
                "atr_ratio": round(atr_ratio, 2),
                "atr_score": s4,
                "atr_morning": round(atr_morning, 2),
            }

            return regime, total_score, details

        except Exception as e:
            logging.error(f"MODE_DON regime computation error: {e}")
            return DayRegime.UNKNOWN, 0, {}

    def _count_directional_legs(self, candles):
        """
        Count directional legs: HH-HL (bullish) or LH-LL (bearish).
        A leg = 3+ consecutive candles making higher highs/lows or lower highs/lows.
        """
        if len(candles) < 5:
            return 0

        legs = 0
        leg_direction = None  # 'up' or 'down'
        leg_length = 0

        for i in range(1, len(candles)):
            c = candles[i]
            p = candles[i - 1]
            ch, cl = float(c['high']), float(c['low'])
            ph, pl = float(p['high']), float(p['low'])

            if ch > ph and cl > pl:
                # Higher high, higher low
                if leg_direction == 'up':
                    leg_length += 1
                else:
                    if leg_length >= 3:
                        legs += 1
                    leg_direction = 'up'
                    leg_length = 1
            elif ch < ph and cl < pl:
                # Lower high, lower low
                if leg_direction == 'down':
                    leg_length += 1
                else:
                    if leg_length >= 3:
                        legs += 1
                    leg_direction = 'down'
                    leg_length = 1
            else:
                # Alternating/sideways — break leg
                if leg_length >= 3:
                    legs += 1
                leg_direction = None
                leg_length = 0

        # Count final leg
        if leg_length >= 3:
            legs += 1

        return legs

    def check_degradation(self, candles, current_regime, morning_atr, vwap_values):
        """
        Post-12 PM degradation check.
        Returns new regime if degraded, else current regime.
        """
        if len(candles) < 10:
            return current_regime

        try:
            closes = [float(c['close']) for c in candles]
            highs = [float(c['high']) for c in candles]
            lows = [float(c['low']) for c in candles]

            # Check 1: VWAP flip held for 45 minutes (9 five-min candles)
            if len(vwap_values) >= 9 and len(closes) >= 9:
                last_9_sides = [closes[-(i+1)] > vwap_values[-(i+1)] for i in range(9)]
                # All on opposite side from original = flip held
                if all(s == last_9_sides[0] for s in last_9_sides):
                    # Check if this is opposite from the dominant morning side
                    morning_side = closes[0] > vwap_values[0] if len(vwap_values) > 0 else True
                    if last_9_sides[0] != morning_side:
                        return self._degrade_regime(current_regime)

            # Check 2: ATR contraction below morning ATR
            atr_all = calculate_atr(highs, lows, closes, 14)
            if len(atr_all) > 0 and morning_atr > 0:
                current_atr = float(atr_all[-1])
                if current_atr < morning_atr:
                    return self._degrade_regime(current_regime)

            # Check 3: Two alternating structure breaks
            recent = candles[-10:]
            legs = self._count_directional_legs(recent)
            if legs == 0:
                # No clean legs in recent candles = alternating
                return self._degrade_regime(current_regime)

        except Exception as e:
            logging.error(f"MODE_DON degradation check error: {e}")

        return current_regime

    def _degrade_regime(self, current):
        """One-step degradation. Can only get worse."""
        order = [DayRegime.CLEAN_TREND, DayRegime.NORMAL_TREND,
                 DayRegime.ROTATION, DayRegime.RANGE]
        current_idx = order.index(current) if current in order else len(order) - 1
        if current_idx < len(order) - 1:
            return order[current_idx + 1]
        return current


# ===================================================================
# DONCHIAN SIGNAL ENGINE — Phase 3 & 5
# ===================================================================

class DonchianSignalEngine:
    """Pure Donchian channel breakout with trailing stop."""

    def calculate_donchian(self, candles, period):
        """
        Returns (upper, lower) for the Donchian channel.
        Upper = highest high of previous N candles (excluding current).
        Lower = lowest low of previous N candles (excluding current).
        """
        if len(candles) < period + 1:
            return None, None

        lookback = candles[-(period + 1):-1]  # N candles before current
        upper = max(float(c['high']) for c in lookback)
        lower = min(float(c['low']) for c in lookback)
        return upper, lower

    def check_entry(self, candles, instrument_config):
        """
        Entry: close above upper Donchian + buffer (LONG) or below lower - buffer (SHORT).
        CLOSE confirmation only. No wick triggers.
        v2.1: Uses 12-period Donchian before 11:00, standard period after.
        v2.1: Breakout must exceed Donchian by buffer to clear algo-hunting wicks.
        """
        from mode_don_config import EARLY_SESSION_DONCHIAN
        
        now = now_ist().time()
        
        # v2.1: Early session uses shorter Donchian period
        if now < EARLY_SESSION_DONCHIAN['cutoff_time']:
            period = EARLY_SESSION_DONCHIAN['period']
        else:
            period = instrument_config['donchian_entry_period']
        
        upper, lower = self.calculate_donchian(candles, period)

        if upper is None:
            return None

        current_close = float(candles[-1]['close'])
        
        # v2.1: Breakout buffer — must clear level by a micro-margin
        buffer_pct = instrument_config.get('breakout_buffer_pct', 0.0)
        buffer_up = current_close * buffer_pct / 100
        buffer_dn = current_close * buffer_pct / 100

        if current_close > upper + buffer_up:
            return {
                'direction': TradeDirection.LONG,
                'entry': current_close,
                'donchian_upper': upper,
                'donchian_lower': lower,
            }
        elif current_close < lower - buffer_dn:
            return {
                'direction': TradeDirection.SHORT,
                'entry': current_close,
                'donchian_upper': upper,
                'donchian_lower': lower,
            }

        return None

    def calculate_stop(self, candles, atr, instrument_config):
        """
        Initial stop = tighter of:
          1. Opposite 10-period Donchian
          2. 1.2× ATR from entry
        """
        stop_period = instrument_config['donchian_stop_period']
        _, lower = self.calculate_donchian(candles, stop_period)
        upper, _ = self.calculate_donchian(candles, stop_period)

        entry = float(candles[-1]['close'])
        atr_stop_dist = 1.2 * atr

        return {
            'long_stop': max(lower, entry - atr_stop_dist) if lower else entry - atr_stop_dist,
            'short_stop': min(upper, entry + atr_stop_dist) if upper else entry + atr_stop_dist,
        }

    def update_trailing_stop(self, candles, direction, current_stop, stop_period=10):
        """
        Trail using opposite 10-period Donchian.
        Stop can only move in trade direction (never widen).
        """
        if direction == TradeDirection.LONG:
            _, new_stop = self.calculate_donchian(candles, stop_period)
            if new_stop and new_stop > current_stop:
                return new_stop
        elif direction == TradeDirection.SHORT:
            new_stop, _ = self.calculate_donchian(candles, stop_period)
            if new_stop and new_stop < current_stop:
                return new_stop

        return current_stop


# ===================================================================
# PER-INSTRUMENT STATE
# ===================================================================

class ModeDonInstrument:
    """Per-instrument state and checks."""

    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.instrument_token = None

        # Regime
        self.regime = DayRegime.UNKNOWN
        self.regime_score = 0
        self.regime_details = {}
        self.regime_locked = False  # Set True after 12 PM classification

        # Provisional early regime gate
        self.early_gate_passed = False

        # Trade state
        self.active_trade = None
        self.daily_pnl_r = 0.0
        self.daily_trades = 0
        self.consecutive_losses = 0
        self.disabled = False  # Disabled for the day

        # Morning ATR baseline
        self.morning_atr = None
        self.morning_atr_recorded = False

        # VWAP tracking for degradation
        self.vwap_values = []

        # Leg size tracking for exhaustion
        self.avg_leg_size = None

    def reset_daily(self):
        self.regime = DayRegime.UNKNOWN
        self.regime_score = 0
        self.regime_details = {}
        self.regime_locked = False
        self.early_gate_passed = False
        self.active_trade = None
        self.daily_pnl_r = 0.0
        self.daily_trades = 0
        self.consecutive_losses = 0
        self.disabled = False
        self.morning_atr = None
        self.morning_atr_recorded = False
        self.vwap_values = []
        self.avg_leg_size = None

    def is_in_time_window(self, current_time):
        """Check if current time falls in allowed trading windows."""
        for start, end in self.config['time_windows']:
            # Special: BankNifty afternoon requires Clean Trend
            if self.config.get('afternoon_requires_clean_trend'):
                # Check if this is the afternoon window
                if start.hour >= 13:
                    if self.regime != DayRegime.CLEAN_TREND:
                        continue
            if start <= current_time <= end:
                return True
        return False

    def check_atr_gate(self, current_atr):
        """ATR must be ≥ multiplier × morning ATR."""
        if self.morning_atr is None or self.morning_atr == 0:
            return False
        ratio = current_atr / self.morning_atr
        return ratio >= self.config['atr_gate_multiplier']

    def check_exhaustion(self, candles):
        """Block if current expansion ≥ exhaustion_multiplier × avg leg size."""
        if self.avg_leg_size is None or self.avg_leg_size == 0:
            return False  # Not exhausted (no data)

        closes = [float(c['close']) for c in candles]
        if len(closes) < 10:
            return False

        # Current move size from session low/high
        session_high = max(float(c['high']) for c in candles)
        session_low = min(float(c['low']) for c in candles)
        current_move = session_high - session_low

        threshold = self.config['exhaustion_multiplier'] * self.avg_leg_size
        return current_move >= threshold

    def can_trade(self, current_time, current_atr, candles, pre_12_mode=False):
        """Full activation check. pre_12_mode=True uses early gate instead of full regime."""
        if self.disabled:
            return False, "Instrument disabled for day"

        # Pre-12: require early gate passed. Post-12: require full regime.
        if pre_12_mode:
            if not self.early_gate_passed:
                return False, "Early regime gate not met"
        else:
            if self.regime not in ALLOWED_REGIMES:
                return False, f"Regime {self.regime.value} not allowed"

        # Donchian lookback formation rule (Section 3):
        # No breakout allowed before full lookback period has formed
        earliest = self.config.get('earliest_breakout_time')
        if earliest and current_time < earliest:
            return False, f"Lookback not formed (before {earliest.strftime('%H:%M')})"

        if not self.is_in_time_window(current_time):
            return False, "Outside time window"
        if self.daily_pnl_r <= self.config['daily_loss_cap_r']:
            return False, f"Daily cap hit: {self.daily_pnl_r:.2f}R"
        if not self.check_atr_gate(current_atr):
            return False, "ATR gate not met"
        if self.check_exhaustion(candles):
            return False, "Move exhausted"
        if self.active_trade is not None:
            return False, "Active trade exists"
        return True, "OK"

    def check_early_regime_gate(self, candles, current_atr):
        """
        Provisional Early Regime Gate for pre-12 PM trading.
        Must pass ALL 3 conditions:
          1. Current Range ≥ 1.5 × Opening 30-min Range
          2. Price holds one side of VWAP for 5 consecutive candles
          3. ATR ≥ 1.1 × morning ATR
        """
        if len(candles) < 10 or self.morning_atr is None:
            self.early_gate_passed = False
            return False

        try:
            closes = [float(c['close']) for c in candles]
            highs = [float(c['high']) for c in candles]
            lows = [float(c['low']) for c in candles]

            # Condition 1: Expansion ≥ 1.5×
            opening_candles = candles[:min(6, len(candles))]
            opening_high = max(float(c['high']) for c in opening_candles)
            opening_low = min(float(c['low']) for c in opening_candles)
            opening_range = opening_high - opening_low
            if opening_range <= 0:
                self.early_gate_passed = False
                return False

            session_range = max(highs) - min(lows)
            expansion = session_range / opening_range
            if expansion < EARLY_REGIME_GATE['expansion_min']:
                self.early_gate_passed = False
                return False

            # Condition 2: VWAP hold for 5 consecutive candles
            cumulative_vp = 0
            cumulative_v = 0
            vwap_values = []
            for c in candles:
                typical = (float(c['high']) + float(c['low']) + float(c['close'])) / 3
                vol = float(c.get('volume', 1))
                cumulative_vp += typical * vol
                cumulative_v += vol
                vwap_values.append(cumulative_vp / cumulative_v if cumulative_v > 0 else typical)

            hold_count = EARLY_REGIME_GATE['vwap_hold_candles']
            if len(closes) >= hold_count:
                last_n = closes[-hold_count:]
                last_n_vwap = vwap_values[-hold_count:]
                all_above = all(c > v for c, v in zip(last_n, last_n_vwap))
                all_below = all(c < v for c, v in zip(last_n, last_n_vwap))
                if not (all_above or all_below):
                    self.early_gate_passed = False
                    return False
            else:
                self.early_gate_passed = False
                return False

            # Condition 3: ATR ≥ 1.1× morning ATR
            if self.morning_atr > 0:
                atr_ratio = current_atr / self.morning_atr
                if atr_ratio < EARLY_REGIME_GATE['atr_gate_multiplier']:
                    self.early_gate_passed = False
                    return False
            else:
                self.early_gate_passed = False
                return False

            # All 3 conditions passed
            if not self.early_gate_passed:
                logging.info(
                    f"✅ MODE_DON [{self.name}] EARLY GATE PASSED | "
                    f"Expansion: {expansion:.1f}× | VWAP held {hold_count} candles | "
                    f"ATR ratio: {atr_ratio:.2f}×"
                )
            self.early_gate_passed = True
            return True

        except Exception as e:
            logging.error(f"MODE_DON [{self.name}] early gate error: {e}")
            self.early_gate_passed = False
            return False

    def record_morning_atr(self, candles):
        """Record ATR at ~9:45 (first 6 candles) as baseline."""
        if self.morning_atr_recorded:
            return
        if len(candles) >= 6:
            closes = [float(c['close']) for c in candles[:6]]
            highs = [float(c['high']) for c in candles[:6]]
            lows = [float(c['low']) for c in candles[:6]]
            atr = calculate_atr(highs, lows, closes, min(6, len(closes)))
            if len(atr) > 0:
                self.morning_atr = float(atr[-1])
                self.morning_atr_recorded = True
                logging.info(f"MODE_DON [{self.name}] Morning ATR: {self.morning_atr:.2f}")

    def compute_avg_leg_size(self, candles):
        """Compute average directional leg size for exhaustion check."""
        if len(candles) < 10:
            return

        leg_sizes = []
        leg_start = float(candles[0]['close'])
        leg_direction = None

        for i in range(1, len(candles)):
            p = float(candles[i - 1]['close'])
            c = float(candles[i]['close'])

            if c > p:
                if leg_direction == 'down':
                    leg_sizes.append(abs(p - leg_start))
                    leg_start = p
                leg_direction = 'up'
            elif c < p:
                if leg_direction == 'up':
                    leg_sizes.append(abs(p - leg_start))
                    leg_start = p
                leg_direction = 'down'

        if leg_sizes:
            self.avg_leg_size = sum(leg_sizes) / len(leg_sizes)


# ===================================================================
# MODE_DON ORCHESTRATOR
# ===================================================================

class ModeDonEngine:
    """
    Main MODE_DON engine. Orchestrates 3 instruments.
    Fully deterministic — no AI.
    """

    def __init__(self, stop_event=None):
        self._stop_event = stop_event or threading.Event()

        # Kite connection
        self.kite = KiteConnect(api_key=os.getenv("KITE_API_KEY"))
        self.kite.set_access_token(os.getenv("KITE_ACCESS_TOKEN"))

        # Engines
        self.regime_engine = RegimeEngine()
        self.signal_engine = DonchianSignalEngine()

        # Per-instrument state
        self.instruments = {}
        for name, config in INSTRUMENTS.items():
            self.instruments[name] = ModeDonInstrument(name, config)

        # System-level state
        self.system_pnl_r = 0.0
        self.system_stopped = False
        self.today = None

        # Regime computed flag
        self.regime_computed_today = False

        # Resolve tokens
        self._resolve_tokens()

        # Logging
        logging.info("=" * 60)
        logging.info("MODE_DON — Regime-Gated Breakout Engine")
        logging.info("Instruments: NIFTY | SENSEX | BANK NIFTY")
        logging.info("AI Layer: NOT USED")
        logging.info("=" * 60)

    def _resolve_tokens(self):
        """Resolve instrument tokens at startup."""
        symbols = [inst.config['kite_symbol'] for inst in self.instruments.values()]
        try:
            quotes = self.kite.ltp(symbols)
            for name, inst in self.instruments.items():
                sym = inst.config['kite_symbol']
                if sym in quotes:
                    inst.instrument_token = quotes[sym]['instrument_token']
                    logging.info(f"✅ MODE_DON [{name}] → token {inst.instrument_token}")
                else:
                    logging.warning(f"⚠️ MODE_DON [{name}] → {sym} not found in quotes")
        except Exception as e:
            if token_manager.handle_api_error(e, context="MODE_DON startup"):
                logging.error("🔑 MODE_DON cannot start — Kite token expired. Check Telegram for login link.")
            else:
                logging.error(f"MODE_DON token resolution failed: {e}")
                send_telegram_message(
                    f"🚨 <b>MODE_DON STARTUP ERROR</b>\n\n"
                    f"Failed to resolve instrument tokens: {e}\n"
                    f"Engine will retry on next cycle."
                )

    def reset_daily_state(self):
        """Reset all state for new day."""
        self.today = now_ist().date()
        self.system_pnl_r = 0.0
        self.system_stopped = False
        self.regime_computed_today = False

        for inst in self.instruments.values():
            inst.reset_daily()

        logging.info(f"\n{'=' * 60}")
        logging.info(f"MODE_DON — NEW TRADING DAY: {self.today}")
        logging.info(f"{'=' * 60}")

        send_telegram_message(
            f"🟢 <b>MODE_DON — NEW DAY</b>\n\n"
            f"📅 Date: {self.today}\n"
            f"📊 Instruments: NIFTY | SENSEX | BANK NIFTY\n"
            f"⏰ Regime scan at 12:00 PM\n"
            f"🤖 AI Layer: <b>NOT USED</b>\n\n"
            f"Waiting for regime classification..."
        )

    def stop(self):
        self._stop_event.set()

    # ---------------------------------------------------------------
    # DATA FETCHING
    # ---------------------------------------------------------------

    def fetch_candles(self, instrument_token, from_time=None):
        """Fetch 5-min candles for an instrument."""
        try:
            now = now_ist()
            if from_time is None:
                from_time = now.replace(hour=9, minute=0, second=0, microsecond=0)

            data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_time,
                to_date=now,
                interval="5minute"
            )
            return data if data else []
        except Exception as e:
            if not token_manager.handle_api_error(e, context="MODE_DON fetch_candles"):
                logging.error(f"MODE_DON fetch error (token {instrument_token}): {e}")
            return []

    # ---------------------------------------------------------------
    # REGIME CLASSIFICATION — Phase 1
    # ---------------------------------------------------------------

    def compute_all_regimes(self):
        """Compute regime for all instruments at 12:00 PM."""
        logging.info("📊 MODE_DON: Computing 12 PM regime for all instruments...")

        reports = []

        for name, inst in self.instruments.items():
            if not inst.instrument_token:
                inst.regime = DayRegime.UNKNOWN
                inst.regime_score = 0
                reports.append(f"{inst.config['emoji']} {name}: Token unavailable")
                continue

            candles = self.fetch_candles(inst.instrument_token)
            if len(candles) < 10:
                inst.regime = DayRegime.UNKNOWN
                inst.regime_score = 0
                reports.append(f"{inst.config['emoji']} {name}: Insufficient data")
                continue

            # Compute regime
            regime, score, details = self.regime_engine.compute_regime(candles)
            inst.regime = regime
            inst.regime_score = score
            inst.regime_details = details
            inst.regime_locked = True

            # Record morning ATR and avg leg size
            inst.record_morning_atr(candles)
            inst.compute_avg_leg_size(candles)

            # Build VWAP for degradation tracking
            self._update_vwap(inst, candles)

            status = "✅ ACTIVE" if regime in ALLOWED_REGIMES else "❌ DISABLED"
            if inst.disabled:
                status = "❌ DISABLED (loss cap)"

            logging.info(
                f"📊 MODE_DON [{name}]: {regime.value} "
                f"(Score {score}/8) → {status}"
            )

            report = TELEGRAM_INSTRUMENT_REGIME.format(
                emoji=inst.config['emoji'],
                instrument=inst.config['display_name'],
                regime=regime.value,
                score=score,
                expansion=details.get('expansion_ratio', 0),
                vwap_pct=details.get('vwap_pct', 0),
                legs=details.get('structure_legs', 0),
                atr_ratio=details.get('atr_ratio', 0),
                status=status,
            )
            reports.append(report)

        # Send Telegram regime report
        system_status = "🟢 Active" if not self.system_stopped else "🔴 Stopped"
        send_telegram_message(
            TELEGRAM_REGIME_TEMPLATE.format(
                instrument_reports="\n\n".join(reports),
                system_status=system_status,
            )
        )

        self.regime_computed_today = True

    def _update_vwap(self, inst, candles):
        """Compute running VWAP for degradation checks."""
        inst.vwap_values = []
        cumulative_vp = 0
        cumulative_v = 0
        for c in candles:
            typical = (float(c['high']) + float(c['low']) + float(c['close'])) / 3
            vol = float(c.get('volume', 1))
            cumulative_vp += typical * vol
            cumulative_v += vol
            inst.vwap_values.append(cumulative_vp / cumulative_v if cumulative_v > 0 else typical)

    # ---------------------------------------------------------------
    # DEGRADATION CHECK — Phase 7
    # ---------------------------------------------------------------

    def check_degradation_all(self):
        """Post-12 PM degradation check for all instruments."""
        for name, inst in self.instruments.items():
            if not inst.regime_locked or inst.disabled:
                continue
            if inst.regime not in ALLOWED_REGIMES:
                continue
            if not inst.instrument_token:
                continue

            candles = self.fetch_candles(inst.instrument_token)
            if len(candles) < 10:
                continue

            self._update_vwap(inst, candles)

            old_regime = inst.regime
            new_regime = self.regime_engine.check_degradation(
                candles, inst.regime, inst.morning_atr or 0, inst.vwap_values
            )

            # One-way degradation enforcement
            if REGIME_HIERARCHY.get(new_regime, 99) > REGIME_HIERARCHY.get(old_regime, 0):
                inst.regime = new_regime
                logging.info(
                    f"⚠️ MODE_DON [{name}] DEGRADED: "
                    f"{old_regime.value} → {new_regime.value}"
                )

                if new_regime not in ALLOWED_REGIMES:
                    send_telegram_message(
                        f"⚠️ <b>MODE_DON [{inst.config['display_name']}] DISABLED</b>\n\n"
                        f"Regime degraded: {old_regime.value} → {new_regime.value}\n"
                        f"No further entries allowed today."
                    )

    # ---------------------------------------------------------------
    # EARLY REGIME GATE — Pre-12 PM
    # ---------------------------------------------------------------

    def _update_early_gates(self):
        """Check early regime gate for all instruments (pre-12 PM)."""
        for name, inst in self.instruments.items():
            if not inst.instrument_token or inst.regime_locked:
                continue

            candles = self.fetch_candles(inst.instrument_token)
            if len(candles) < 10:
                continue

            closes = [float(c['close']) for c in candles]
            highs = [float(c['high']) for c in candles]
            lows = [float(c['low']) for c in candles]
            atr_all = calculate_atr(highs, lows, closes, 14)
            current_atr = float(atr_all[-1]) if len(atr_all) > 0 else 0

            inst.check_early_regime_gate(candles, current_atr)

    # ---------------------------------------------------------------
    # ENTRY CHECK — Phase 3 & 4
    # ---------------------------------------------------------------

    def check_entries(self, pre_12_mode=False):
        """Scan all instruments for Donchian breakout entries."""
        if self.system_stopped:
            return

        # System concurrent trade check
        active_count = sum(1 for inst in self.instruments.values() if inst.active_trade)
        if active_count >= SYSTEM_RISK['max_concurrent_trades']:
            return

        now = now_ist()
        current_time = now.time()

        for name, inst in self.instruments.items():
            if not inst.instrument_token:
                continue

            # Full activation check
            candles = self.fetch_candles(inst.instrument_token)
            if len(candles) < inst.config['donchian_entry_period'] + 1:
                continue

            # Calculate current ATR
            closes = [float(c['close']) for c in candles]
            highs = [float(c['high']) for c in candles]
            lows = [float(c['low']) for c in candles]
            atr_all = calculate_atr(highs, lows, closes, 14)
            current_atr = float(atr_all[-1]) if len(atr_all) > 0 else 0

            can, reason = inst.can_trade(current_time, current_atr, candles, pre_12_mode=pre_12_mode)
            if not can:
                continue

            # Check Donchian breakout
            signal = self.signal_engine.check_entry(candles, inst.config)
            if not signal:
                continue

            # v2.1: Correlation protection — block same-direction trades on correlated pairs
            from mode_don_config import CORRELATION_PROTECTION
            correlation_blocked = False
            for pair in CORRELATION_PROTECTION.get('blocked_pairs', []):
                if name in pair:
                    other_name = pair[0] if pair[1] == name else pair[1]
                    other_inst = self.instruments.get(other_name)
                    if other_inst and other_inst.active_trade:
                        if other_inst.active_trade['direction'] == signal['direction']:
                            logging.info(
                                f"🚫 MODE_DON [{name}] BLOCKED: Correlation with {other_name} "
                                f"({signal['direction'].value})"
                            )
                            correlation_blocked = True
                            break
            if correlation_blocked:
                continue

            # No same-direction double entry check
            if SYSTEM_RISK['no_same_direction_double']:
                for other_name, other_inst in self.instruments.items():
                    if other_inst.active_trade and other_inst.active_trade['direction'] == signal['direction']:
                        if other_name == name:
                            continue  # same instrument already blocked by active_trade check

            # Calculate stop
            stops = self.signal_engine.calculate_stop(candles, current_atr, inst.config)
            if signal['direction'] == TradeDirection.LONG:
                stop = stops['long_stop']
            else:
                stop = stops['short_stop']

            # Execute entry
            entry_price = signal['entry']
            risk_points = abs(entry_price - stop)

            # ATR ratio for telegram
            atr_ratio = current_atr / inst.morning_atr if inst.morning_atr and inst.morning_atr > 0 else 0
            expansion = inst.regime_details.get('expansion_ratio', 0)

            inst.active_trade = {
                'direction': signal['direction'],
                'entry': entry_price,
                'stop': stop,
                'trailing_stop': stop,
                'risk_points': risk_points,
                'time': now.strftime('%H:%M'),
            }
            inst.daily_trades += 1

            logging.info(
                f"🔔 MODE_DON [{name}] ENTRY: {signal['direction'].value} @ {entry_price:.1f} | "
                f"Stop: {stop:.1f} | Risk: {risk_points:.1f}pts | "
                f"Regime: {inst.regime.value} ({inst.regime_score}/8)"
            )

            send_telegram_message(
                TELEGRAM_ENTRY_TEMPLATE.format(
                    emoji=inst.config['emoji'],
                    instrument=inst.config['display_name'],
                    direction=signal['direction'].value,
                    time=now.strftime('%H:%M'),
                    regime=inst.regime.value,
                    score=inst.regime_score,
                    period=inst.config['donchian_entry_period'],
                    entry=f"{entry_price:.1f}",
                    stop=f"{stop:.1f}",
                    risk_r=inst.config['risk_r'],
                    atr_ratio=atr_ratio,
                    expansion=expansion,
                )
            )

    # ---------------------------------------------------------------
    # TRADE MONITORING — Phase 5
    # ---------------------------------------------------------------

    def monitor_trades(self):
        """Monitor all active trades — trailing stops and exits."""
        for name, inst in self.instruments.items():
            if not inst.active_trade or not inst.instrument_token:
                continue

            candles = self.fetch_candles(inst.instrument_token)
            if len(candles) < 5:
                continue

            trade = inst.active_trade
            current_close = float(candles[-1]['close'])
            current_high = float(candles[-1]['high'])
            current_low = float(candles[-1]['low'])

            # Update trailing stop
            old_stop = trade['trailing_stop']
            new_stop = self.signal_engine.update_trailing_stop(
                candles, trade['direction'], old_stop,
                inst.config['donchian_stop_period']
            )
            trade['trailing_stop'] = new_stop

            if new_stop != old_stop:
                logging.info(
                    f"📏 MODE_DON [{name}] Trail updated: {old_stop:.1f} → {new_stop:.1f}"
                )

            # Check exit
            hit_stop = False
            if trade['direction'] == TradeDirection.LONG:
                if current_low <= trade['trailing_stop']:
                    hit_stop = True
                    exit_price = trade['trailing_stop']
            else:
                if current_high >= trade['trailing_stop']:
                    hit_stop = True
                    exit_price = trade['trailing_stop']

            if hit_stop:
                # Calculate P&L
                if trade['direction'] == TradeDirection.LONG:
                    pnl_points = exit_price - trade['entry']
                else:
                    pnl_points = trade['entry'] - exit_price

                pnl_r = (pnl_points / trade['risk_points']) * inst.config['risk_r'] if trade['risk_points'] > 0 else 0

                # Update stats
                inst.daily_pnl_r += pnl_r
                self.system_pnl_r += pnl_r

                exit_type = "TARGET (Trail)" if pnl_r > 0 else "STOP HIT"

                if pnl_r <= 0:
                    inst.consecutive_losses += 1
                    if inst.consecutive_losses >= SYSTEM_RISK['consecutive_loss_disable']:
                        inst.disabled = True
                        logging.info(f"❌ MODE_DON [{name}] disabled: {inst.consecutive_losses} consecutive losses")
                else:
                    inst.consecutive_losses = 0

                logging.info(
                    f"{'✅' if pnl_r > 0 else '❌'} MODE_DON [{name}] EXIT: {exit_type} | "
                    f"P&L: {pnl_r:+.2f}R | Daily: {inst.daily_pnl_r:+.2f}R"
                )

                send_telegram_message(
                    TELEGRAM_EXIT_TEMPLATE.format(
                        emoji=inst.config['emoji'],
                        instrument=inst.config['display_name'],
                        time=now_ist().strftime('%H:%M'),
                        direction=trade['direction'].value,
                        exit_type=exit_type,
                        entry=f"{trade['entry']:.1f}",
                        exit_price=f"{exit_price:.1f}",
                        pnl_r=pnl_r,
                    )
                )

                inst.active_trade = None

                # v2.1: Trend re-entries — re-arm after profitable/breakeven close
                if pnl_r >= 0 and not inst.disabled and inst.regime_score >= 5:
                    logging.info(
                        f"♻️ MODE_DON [{name}] RE-ARMED for new breakout "
                        f"(Regime: {inst.regime_score}/8)"
                    )
                    # inst stays enabled — can take another trade
                elif inst.disabled:
                    logging.info(f"❌ MODE_DON [{name}] permanently disabled for today")

                # System loss cap check
                if self.system_pnl_r <= SYSTEM_RISK['system_daily_loss_cap_r']:
                    self.system_stopped = True
                    logging.info(f"🛑 MODE_DON SYSTEM STOP: Daily loss {self.system_pnl_r:.2f}R")
                    send_telegram_message(
                        f"🛑 <b>MODE_DON SYSTEM STOPPED</b>\n\n"
                        f"Daily loss cap hit: {self.system_pnl_r:+.2f}R\n"
                        f"No further entries today."
                    )

    # ---------------------------------------------------------------
    # MAIN LOOP
    # ---------------------------------------------------------------

    def run(self):
        """Main engine loop."""
        logging.info("🚀 MODE_DON engine started")

        last_candle_times = {}

        while not self._stop_event.is_set():
            try:
                now = now_ist()
                current_time = now.time()

                # Daily reset
                if self.today != now.date():
                    self.reset_daily_state()

                # Trading hours check (9:15 - 15:30)
                if not (dtime(9, 15) <= current_time <= dtime(15, 30)):
                    self._stop_event.wait(60)
                    continue

                # Record morning ATR for all instruments (~9:45)
                if current_time >= dtime(9, 45):
                    for name, inst in self.instruments.items():
                        if not inst.morning_atr_recorded and inst.instrument_token:
                            candles = self.fetch_candles(inst.instrument_token)
                            inst.record_morning_atr(candles)
                            inst.compute_avg_leg_size(candles)

                # Phase 1: Regime classification at 12:00 PM
                if not self.regime_computed_today and current_time >= dtime(12, 0):
                    self.compute_all_regimes()

                # Per-candle console output
                for name, inst in self.instruments.items():
                    if not inst.instrument_token:
                        continue

                    candles = self.fetch_candles(inst.instrument_token)
                    if not candles:
                        continue

                    candle_time = candles[-1].get('date')
                    last_time = last_candle_times.get(name)

                    if candle_time != last_time:
                        last_candle_times[name] = candle_time
                        price = float(candles[-1]['close'])

                        closes = [float(c['close']) for c in candles]
                        highs = [float(c['high']) for c in candles]
                        lows = [float(c['low']) for c in candles]
                        atr_all = calculate_atr(highs, lows, closes, 14)
                        current_atr = float(atr_all[-1]) if len(atr_all) > 0 else 0

                        if inst.regime_locked:
                            regime_str = inst.regime.value
                        elif inst.early_gate_passed:
                            regime_str = "⚡ Provisional"
                        else:
                            regime_str = "Awaiting 12PM"
                        trade_str = ""
                        if inst.active_trade:
                            t = inst.active_trade
                            direction = t['direction'].value
                            unrealized = (price - t['entry']) if t['direction'] == TradeDirection.LONG else (t['entry'] - price)
                            unrealized_r = (unrealized / t['risk_points']) * inst.config['risk_r'] if t['risk_points'] > 0 else 0
                            trade_str = f" | 👁️ {direction} {unrealized_r:+.2f}R"

                        ct = candle_time.strftime('%H:%M') if hasattr(candle_time, 'strftime') else str(candle_time)
                        logging.info(
                            f"📊 DON [{ct}] {name} | "
                            f"₹{price:.1f} | ATR: {current_atr:.1f} | "
                            f"Regime: {regime_str} | "
                            f"PnL: {inst.daily_pnl_r:+.2f}R{trade_str}"
                        )

                # Monitor active trades (every cycle)
                self.monitor_trades()

                # Check for new entries
                if not self.system_stopped:
                    if self.regime_computed_today:
                        # Post-12 PM: full regime mode
                        self.check_entries(pre_12_mode=False)

                        # Post-12 PM degradation check (every cycle)
                        if current_time > dtime(12, 5):
                            self.check_degradation_all()
                    elif current_time >= dtime(9, 45):
                        # Pre-12 PM: provisional early regime gate
                        self._update_early_gates()
                        self.check_entries(pre_12_mode=True)

                # Sleep
                self._stop_event.wait(30)

            except KeyboardInterrupt:
                logging.info("MODE_DON shutting down...")
                send_telegram_message("🛑 <b>MODE_DON STOPPED</b>\n\nEngine shut down by user.")
                break
            except Exception as e:
                logging.error(f"MODE_DON loop error: {e}")
                self._stop_event.wait(60)

        logging.info("MODE_DON engine stopped.")

    # ---------------------------------------------------------------
    # STATS FOR DASHBOARD
    # ---------------------------------------------------------------

    def get_stats(self):
        """Return stats dict for dashboard."""
        instruments_stats = {}
        for name, inst in self.instruments.items():
            instruments_stats[name] = {
                'regime': inst.regime.value,
                'regime_score': inst.regime_score,
                'daily_pnl_r': round(inst.daily_pnl_r, 2),
                'daily_trades': inst.daily_trades,
                'active_trade': None,
                'disabled': inst.disabled,
                'consecutive_losses': inst.consecutive_losses,
            }
            if inst.active_trade:
                instruments_stats[name]['active_trade'] = {
                    'direction': inst.active_trade['direction'].value,
                    'entry': inst.active_trade['entry'],
                    'stop': inst.active_trade['trailing_stop'],
                    'time': inst.active_trade['time'],
                }

        return {
            'running': True,
            'system_pnl_r': round(self.system_pnl_r, 2),
            'system_stopped': self.system_stopped,
            'regime_computed': self.regime_computed_today,
            'instruments': instruments_stats,
            'active_trades': sum(1 for i in self.instruments.values() if i.active_trade),
        }
