"""
🧠 RIJIN SYSTEM — Trading Engine v3.0 (IMPULSE-BASED TIMING MODEL)

Philosophy:
    Signals generate opportunity.
    Context decides permission.
    Capital protection is the alpha.

v3.0: Expansion measured from IMPULSE ORIGIN, not day extremes.
      This fixes the core timing architecture flaw.
"""

import os
import time
import numpy as np
from datetime import datetime, timedelta, time as dtime
from enum import Enum
from collections import deque
import traceback

from rijin_config import *


# ===================================================================
# DAY TYPE ENGINE (THE BRAIN)
# ===================================================================
class DayTypeEngine:
    """
    Classifies market days into 9 human-readable types
    Direction: ONLY WORSE (never upgrades)
    v3.1: Added ROTATIONAL_EXPANSION, LIQUIDITY_SWEEP_TRAP, FAST_REGIME_FLIP
    """
    
    def __init__(self):
        self.current_day_type = DayType.UNKNOWN
        self.last_check_time = None
        self.pending_downgrade = None
        self.pending_downgrade_since = None
        self.day_locked = False
        self.day_stats = {
            'open_time': None,
            'first_atr': None,
            'day_high': None,
            'day_low': None,
            'vwap': None,
        }
    
    def reset_for_new_day(self):
        """Reset at market open"""
        self.current_day_type = DayType.UNKNOWN
        self.last_check_time = None
        self.pending_downgrade = None
        self.pending_downgrade_since = None
        self.day_locked = False
        self.day_stats = {
            'open_time': None,
            'first_atr': None,
            'day_high': None,
            'day_low': None,
            'vwap': None,
        }
    
    def should_run_check(self, current_time):
        """Check if we should run day type analysis"""
        current_time_only = current_time.time()
        
        # Check if current time matches any scheduled time (within 5 min window)
        for check_time in DAY_TYPE_CHECK_TIMES:
            time_diff = abs(
                (current_time_only.hour * 60 + current_time_only.minute) -
                (check_time.hour * 60 + check_time.minute)
            )
            if time_diff <= 5:
                # Avoid duplicate checks
                if self.last_check_time:
                    last_diff = (current_time - self.last_check_time).total_seconds() / 60
                    if last_diff < 25:  # Less than 25 minutes since last check
                        return False
                return True
        
        return False
    
    def classify_day(self, candles_5m, candles_30m, indicators, is_expiry_day=False):
        """
        Main classification logic (v3.1 PRIORITY ORDER)
        Higher priority = more dangerous. Once degraded, cannot upgrade.
        
        Priority:
        1. EXPIRY_DISTORTION
        2. LIQUIDITY_SWEEP_TRAP
        3. RANGE_CHOPPY
        4. ROTATIONAL_EXPANSION
        5. FAST_REGIME_FLIP
        6. CLEAN_TREND
        7. NORMAL_TREND
        8. EARLY_IMPULSE_SIDEWAYS
        
        Returns: (DayType, reason)
        """
        try:
            if len(candles_5m) < 30:
                return DayType.UNKNOWN, "Insufficient data"
            
            # Update day stats
            self._update_day_stats(candles_5m, indicators)
            
            # === DANGEROUS TYPES FIRST (highest severity) ===
            
            # 1. EXPIRY_DISTORTION (severity 8)
            if is_expiry_day and datetime.now().time() > dtime(12, 0):
                return DayType.EXPIRY_DISTORTION, "Expiry day post-noon"
            
            # 2. LIQUIDITY_SWEEP_TRAP (severity 7)
            if self._is_liquidity_sweep_trap(candles_5m, indicators):
                return DayType.LIQUIDITY_SWEEP_TRAP, "Stop-hunt pattern detected (expansion + reversal)"
            
            # 3. RANGE_CHOPPY (severity 6)
            if self._is_range_choppy(candles_5m, candles_30m, indicators):
                return DayType.RANGE_CHOPPY, "Choppy price action"
            
            # 4. ROTATIONAL_EXPANSION (severity 5)
            if self._is_rotational_expansion(candles_5m, indicators):
                return DayType.ROTATIONAL_EXPANSION, "ATR expanding but structure unstable"
            
            # 5. FAST_REGIME_FLIP (severity 4)
            if self._is_fast_regime_flip(candles_5m, indicators):
                return DayType.FAST_REGIME_FLIP, "Morning trend reversed violently"
            
            # === SAFE TYPES (lower severity) ===
            
            # 6. CLEAN_TREND (severity 1)
            if self._is_clean_trend(candles_5m, candles_30m, indicators):
                return DayType.CLEAN_TREND, "Clean expansion & pullbacks"
            
            # 7. NORMAL_TREND (severity 2)
            if self._is_normal_trend(candles_5m, candles_30m, indicators):
                return DayType.NORMAL_TREND, "Directional with slower expansion"
            
            # 8. EARLY_IMPULSE_SIDEWAYS (severity 3)
            if self._is_early_impulse_sideways(candles_5m, indicators):
                return DayType.EARLY_IMPULSE_SIDEWAYS, "Early move, then compression"
            
            # Default
            return DayType.NORMAL_TREND, "Default classification"
        
        except Exception as e:
            print(f"Error Day classification error: {e}")
            traceback.print_exc()
            return self.current_day_type, "Error in classification"
    
    def _update_day_stats(self, candles_5m, indicators):
        """Track day-level statistics"""
        if not self.day_stats['open_time']:
            self.day_stats['open_time'] = candles_5m[0]['date']
        
        # Track day range
        highs = [float(c['high']) for c in candles_5m]
        lows = [float(c['low']) for c in candles_5m]
        self.day_stats['day_high'] = max(highs)
        self.day_stats['day_low'] = min(lows)
        
        # Store first ATR for comparison
        if not self.day_stats['first_atr']:
            self.day_stats['first_atr'] = indicators['atr']
        
        # Calculate VWAP
        self.day_stats['vwap'] = self._calculate_vwap(candles_5m)
    
    def _calculate_vwap(self, candles):
        """Volume-weighted average price"""
        try:
            total_vol = sum(c['volume'] for c in candles)
            if total_vol == 0:
                return float(candles[-1]['close'])
            
            vwap = sum(
                ((c['high'] + c['low'] + c['close']) / 3) * c['volume']
                for c in candles
            ) / total_vol
            
            return vwap
        except:
            return float(candles[-1]['close'])
    
    def _is_clean_trend(self, c5, c30, ind):
        """
        Clean Trend Day (v2.4 CALIBRATED):
        - Expansion continues (1.05× ATR, was 1.1×)
        - Pullbacks respected
        - RSI directional (>55 or <45)
        - No overlap candles
        """
        try:
            rsi = ind['rsi']
            atr = ind['atr']
            ema20 = ind['ema20']
            price = float(c5[-1]['close'])
            
            # ATR expanding (v2.4: CALIBRATED 1.1 → 1.05)
            if self.day_stats['first_atr']:
                atr_ratio = atr / self.day_stats['first_atr']
                threshold = DAY_TYPE_THRESHOLDS['clean_trend']['atr_expansion_ratio']
                if atr_ratio < threshold:  # More lenient
                    return False
            
            # RSI directional
            if not (rsi > 55 or rsi < 45):
                return False
            
            # Check for overlapping candles (sign of chop)
            last_10 = c5[-10:]
            overlap_count = 0
            for i in range(1, len(last_10)):
                curr = last_10[i]
                prev = last_10[i-1]
                
                curr_h, curr_l = float(curr['high']), float(curr['low'])
                prev_h, prev_l = float(prev['high']), float(prev['low'])
                
                # Check if candles overlap but don't extend range
                if (curr_h < prev_h and curr_l > prev_l) or (prev_h < curr_h and prev_l > curr_l):
                    overlap_count += 1
            
            if overlap_count > 3:  # Too much overlap
                return False
            
            # Price respecting EMA20 (pullbacks)
            if len(c5) >= 20:
                recent_prices = [float(c['close']) for c in c5[-20:]]
                ema_touches = sum(1 for p in recent_prices if abs(p - ema20) / ema20 < 0.002)
                if ema_touches < 2:  # No pullbacks to EMA
                    return False
            
            return True
        
        except:
            return False
    
    def _is_normal_trend(self, c5, c30, ind):
        """
        Normal Trend Day:
        - Direction exists
        - Expansion slower
        - RSI between 50–60 / 40–50
        - Some overlap
        """
        try:
            rsi = ind['rsi']
            slope = ind['slope']
            
            # Directional (slope exists)
            if abs(slope) < 0.5:
                return False
            
            # RSI in range
            if not ((50 <= rsi <= 60) or (40 <= rsi <= 50)):
                return False
            
            # Some expansion present
            if self.day_stats['first_atr']:
                atr_ratio = ind['atr'] / self.day_stats['first_atr']
                if atr_ratio < 0.9:  # Contracting
                    return False
            
            return True
        
        except:
            return False
    
    def _is_early_impulse_sideways(self, c5, ind):
        """
        Early Impulse → Sideways:
        - Big early move (>1.5× ATR)
        - After ~11:00 → compression
        - RSI stuck 48–62
        - Breakouts fail
        """
        try:
            current_time = c5[-1]['date'].time()
            
            # Check if we're past 11:00
            if current_time < dtime(11, 0):
                return False
            
            # Get opening candles (first 10)
            opening_candles = c5[:min(10, len(c5))]
            opening_range = max(c['high'] for c in opening_candles) - min(c['low'] for c in opening_candles)
            
            # Big early move
            if self.day_stats['first_atr']:
                if opening_range < 1.5 * self.day_stats['first_atr']:
                    return False
            
            # Current RSI stuck
            if not (48 <= ind['rsi'] <= 62):
                return False
            
            # Check compression (last 20 candles)
            recent = c5[-20:]
            recent_range = max(c['high'] for c in recent) - min(c['low'] for c in recent)
            recent_atr = ind['atr']
            
            if recent_range > 1.2 * recent_atr:  # Still moving
                return False
            
            return True
        
        except:
            return False
    
    def _is_range_choppy(self, c5, c30, ind):
        """
        Range / Choppy Day:
        - VWAP magnet
        - EMA flat / crossed
        - RSI whipsaws 40–60
        - Fake moves
        """
        try:
            vwap = self.day_stats['vwap']
            price = float(c5[-1]['close'])
            ema20 = ind['ema20']
            rsi = ind['rsi']
            slope = ind['slope']
            
            # VWAP magnet (price oscillates around VWAP)
            vwap_distance = abs(price - vwap) / vwap
            if vwap_distance > 0.005:  # More than 0.5% away
                # Not a strong magnet, check other factors
                pass
            
            # EMA flat
            if abs(slope) > 1.0:  # Trending
                return False
            
            # RSI whipsaws (check last 10 candles)
            if len(c5) >= 10:
                rsi_values = []
                for c in c5[-10:]:
                    closes = [float(x['close']) for x in c5[:c5.index(c)+1]]
                    if len(closes) >= 14:
                        from unified_engine import calculate_rsi
                        rsi_vals = calculate_rsi(closes, 14)
                        if len(rsi_vals) > 0:
                            rsi_values.append(rsi_vals[-1])
                
                if rsi_values:
                    # Count crosses of 50
                    crosses = sum(1 for i in range(1, len(rsi_values)) 
                                 if (rsi_values[i-1] < 50 and rsi_values[i] > 50) or 
                                    (rsi_values[i-1] > 50 and rsi_values[i] < 50))
                    
                    if crosses >= 3:  # Multiple whipsaws
                        return True
            
            # ATR contracting
            if self.day_stats['first_atr']:
                atr_ratio = ind['atr'] / self.day_stats['first_atr']
                if atr_ratio < 0.7:  # Significant contraction
                    return True
            
            return False
        
        except:
            return False
    
    def _is_liquidity_sweep_trap(self, c5, ind):
        """
        LIQUIDITY SWEEP TRAP (v3.1):
        Catch stop-hunt days early.
        - Large expansion candle (> 1.2x ATR)
        - Immediate reversal (> 0.8x ATR)
        - Opposite direction candle
        """
        try:
            if len(c5) < 4:
                return False
            
            cfg = REGIME_THRESHOLDS['liquidity_sweep_trap']
            atr = ind['atr']
            
            c1 = c5[-3]  # Context candle
            c2 = c5[-2]  # Expansion candle
            c3 = c5[-1]  # Reversal candle
            
            # Large expansion candle
            expansion = (float(c2['high']) - float(c2['low'])) > cfg['expansion_atr_multiple'] * atr
            
            # Immediate reversal
            reversal = abs(float(c3['close']) - float(c2['close'])) > cfg['reversal_atr_multiple'] * atr
            
            # Opposite direction
            c2_bull = float(c2['close']) > float(c2['open'])
            c3_bull = float(c3['close']) > float(c3['open'])
            direction_flip = (c2_bull and not c3_bull) or (not c2_bull and c3_bull)
            
            return expansion and reversal and direction_flip
        
        except:
            return False
    
    def _is_rotational_expansion(self, c5, ind):
        """
        ROTATIONAL EXPANSION (v3.1):
        ATR expanding but structure unstable.
        - ATR expanding (> 1.05x first ATR)
        - RSI crossing 50 at least 3 times in last 10 candles
        - VWAP crossovers >= 3
        - At least 1 failed breakout
        """
        try:
            if len(c5) < 12:
                return False
            
            cfg = REGIME_THRESHOLDS['rotational_expansion']
            atr = ind['atr']
            
            # ATR expanding
            if self.day_stats['first_atr']:
                atr_expanding = atr > cfg['atr_expansion_ratio'] * self.day_stats['first_atr']
            else:
                return False
            
            if not atr_expanding:
                return False
            
            # RSI crossing 50 multiple times (simplified: use close vs EMA as proxy)
            closes = [float(c['close']) for c in c5[-12:]]
            ema20 = ind['ema20']
            
            # Count times close crosses EMA20 (proxy for RSI 50 cross)
            cross_count = 0
            for i in range(1, len(closes)):
                above_now = closes[i] > ema20
                above_prev = closes[i-1] > ema20
                if above_now != above_prev:
                    cross_count += 1
            
            if cross_count < cfg['rsi_cross_50_min']:
                return False
            
            # VWAP crossovers
            vwap = self.day_stats.get('vwap')
            if vwap:
                vwap_cross = 0
                for i in range(1, len(closes)):
                    above_now = closes[i] > vwap
                    above_prev = closes[i-1] > vwap
                    if above_now != above_prev:
                        vwap_cross += 1
                
                if vwap_cross < cfg['vwap_cross_min']:
                    return False
            
            # Failed breakouts (candle makes new high but next candle closes below)
            failed_breaks = 0
            recent = c5[-8:]
            for i in range(2, len(recent) - 1):
                prev_highs = [float(c['high']) for c in recent[:i]]
                if float(recent[i]['high']) > max(prev_highs):
                    if float(recent[i+1]['close']) < float(recent[i]['close']):
                        failed_breaks += 1
            
            if failed_breaks < cfg['failed_breakout_min']:
                return False
            
            return True
        
        except:
            return False
    
    def _is_fast_regime_flip(self, c5, ind):
        """
        FAST REGIME FLIP (v3.1):
        Morning trend followed by violent opposite impulse.
        - Morning range > 1.5x ATR  (first 12 candles)
        - Recent reversal range > 1.2x ATR (last 6 candles)
        - Direction changed (morning bull -> recent bear or vice versa)
        """
        try:
            cfg = REGIME_THRESHOLDS['fast_regime_flip']
            atr = ind['atr']
            
            morning_count = cfg['lookback_morning']
            recent_count = cfg['lookback_recent']
            
            if len(c5) < morning_count + recent_count:
                return False
            
            # Morning range
            morning_candles = c5[:morning_count]
            morning_high = max(float(c['high']) for c in morning_candles)
            morning_low = min(float(c['low']) for c in morning_candles)
            morning_range = morning_high - morning_low
            
            # Recent range
            recent_candles = c5[-recent_count:]
            recent_high = max(float(c['high']) for c in recent_candles)
            recent_low = min(float(c['low']) for c in recent_candles)
            recent_range = recent_high - recent_low
            
            # Size checks
            if morning_range < cfg['morning_move_atr'] * atr:
                return False
            if recent_range < cfg['recent_range_atr'] * atr:
                return False
            
            # Direction change: compare 4th morning candle vs latest candle
            morning_bull = float(morning_candles[3]['close']) > float(morning_candles[3]['open'])
            recent_bull = float(c5[-1]['close']) > float(c5[-1]['open'])
            direction_change = morning_bull != recent_bull
            
            return direction_change
        
        except:
            return False
    
    def update_day_type(self, new_type, reason, current_time):
        """
        Apply degradation rules with confirmation
        Returns: (updated, message)
        """
        # If day is locked (reached RANGE_CHOPPY), no changes
        if self.day_locked:
            return False, None
        
        # If unknown, accept any classification
        if self.current_day_type == DayType.UNKNOWN:
            self.current_day_type = new_type
            self.last_check_time = current_time
            return True, f"Initial classification: {new_type.value}"
        
        # Get hierarchy levels
        current_level = DAY_TYPE_HIERARCHY.get(self.current_day_type, 0)
        new_level = DAY_TYPE_HIERARCHY.get(new_type, 0)
        
        # Can only degrade (move to higher number = worse)
        if new_level <= current_level:
            # Reset pending downgrade if trying to upgrade or stay same
            self.pending_downgrade = None
            self.pending_downgrade_since = None
            return False, None
        
        # Immediate downgrades (no confirmation needed)
        if new_type in IMMEDIATE_DOWNGRADE:
            self.current_day_type = new_type
            self.last_check_time = current_time
            
            # Lock day if terminal regime
            if new_type in [DayType.RANGE_CHOPPY, DayType.LIQUIDITY_SWEEP_TRAP]:
                self.day_locked = True
            
            message = f"🚨 DAY TYPE DOWNGRADE: {new_type.value} (Immediate)"
            return True, message
        
        # Confirmation-based downgrade (need 2 consecutive checks = 60 min)
        if self.pending_downgrade == new_type:
            # Check if 60 min passed
            time_since = (current_time - self.pending_downgrade_since).total_seconds() / 60
            
            if time_since >= 50:  # Allow some margin (50-70 min)
                # Downgrade confirmed
                self.current_day_type = new_type
                self.last_check_time = current_time
                self.pending_downgrade = None
                self.pending_downgrade_since = None
                
                message = f"🚨 DAY TYPE DOWNGRADE: {new_type.value} (Confirmed)"
                return True, message
        else:
            # Start confirmation timer
            self.pending_downgrade = new_type
            self.pending_downgrade_since = current_time
        
        return False, None


# ===================================================================
# IMPULSE DETECTION ENGINE (v3.0 FOUNDATION)
# ===================================================================
class ImpulseDetectionEngine:
    """
    Detects where directional move actually STARTS
    
    v3.0 Core Fix: Expansion measured from impulse origin, not day extremes
    
    Impulse = The candle where significant directional move begins
    """
    
    def __init__(self):
        self.impulse_origin = None      # Price where impulse started
        self.impulse_atr = None          # ATR at impulse time
        self.impulse_direction = None    # "BUY" or "SELL"
        self.impulse_time = None         # When detected
        self.swing_high = None           # Prior swing high
        self.swing_low = None            # Prior swing low
    
    def reset_for_new_day(self):
        """Reset impulse tracking for new trading day"""
        self.impulse_origin = None
        self.impulse_atr = None
        self.impulse_direction = None
        self.impulse_time = None
        self.swing_high = None
        self.swing_low = None
    
    def detect_impulse(self, candles_5m, indicators, current_time):
        """
        Detect bullish or bearish impulse
        
        Bullish Impulse:
        - 2 strong bullish candles
        - Close > previous swing high
        - Range > 0.6× ATR
        - EMA20 slope positive
        
        Returns: (impulse_detected, direction, origin_price)
        """
        try:
            if len(candles_5m) < 10:
                return False, None, None
            
            config = IMPULSE_DETECTION
            atr = indicators.get('atr', 10.0)
            
            # Calculate EMA20 slope (last 3 candles)
            closes = [float(c['close']) for c in candles_5m[-5:]]
            if len(closes) >= 4:
                ema_slope_pct = (closes[-1] - closes[-4]) / closes[-4] * 100
            else:
                ema_slope_pct = 0
            
            # Update swing levels (last 10 candles)
            recent_candles = candles_5m[-10:]
            self.swing_high = max(float(c['high']) for c in recent_candles[:-2])
            self.swing_low = min(float(c['low']) for c in recent_candles[:-2])
            
            # Get last 2 candles
            candle_1 = candles_5m[-2]
            candle_2 = candles_5m[-1]
            
            # Check for bullish impulse
            bullish_1 = float(candle_1['close']) > float(candle_1['open'])
            bullish_2 = float(candle_2['close']) > float(candle_2['open'])
            range_1 = float(candle_1['high']) - float(candle_1['low'])
            range_2 = float(candle_2['high']) - float(candle_2['low'])
            
            if (bullish_1 and bullish_2 and 
                range_1 > config['min_range_atr_multiple'] * atr and
                range_2 > config['min_range_atr_multiple'] * atr and
                ema_slope_pct > config['min_ema_slope_pct']):
                
                # Check swing break
                if config['require_swing_break']:
                    if float(candle_2['close']) > self.swing_high:
                        # Bullish impulse detected!
                        self.impulse_origin = float(candle_1['low'])  # Start from impulse base
                        self.impulse_atr = atr
                        self.impulse_direction = "BUY"
                        self.impulse_time = current_time
                        return True, "BUY", self.impulse_origin
            
            # Check for bearish impulse
            bearish_1 = float(candle_1['close']) < float(candle_1['open'])
            bearish_2 = float(candle_2['close']) < float(candle_2['open'])
            
            if (bearish_1 and bearish_2 and 
                range_1 > config['min_range_atr_multiple'] * atr and
                range_2 > config['min_range_atr_multiple'] * atr and
                ema_slope_pct < -config['min_ema_slope_pct']):
                
                # Check swing break
                if config['require_swing_break']:
                    if float(candle_2['close']) < self.swing_low:
                        # Bearish impulse detected!
                        self.impulse_origin = float(candle_1['high'])  # Start from impulse top
                        self.impulse_atr = atr
                        self.impulse_direction = "SELL"
                        self.impulse_time = current_time
                        return True, "SELL", self.impulse_origin
            
            return False, None, None
        
        except Exception as e:
            print(f"⚠️ Impulse detection error: {e}")
            return False, None, None
    
    def get_expansion_from_impulse(self, current_price):
        """
        Calculate expansion from impulse origin (v3.0 CORE FIX)
        
        Returns: expansion_multiple (float)
        """
        if self.impulse_origin is None or self.impulse_atr is None:
            return 0.0
        
        try:
            expansion = abs(current_price - self.impulse_origin) / self.impulse_atr
            return expansion
        except:
            return 0.0
    
    def is_impulse_active(self):
        """Check if an impulse is currently being tracked"""
        return self.impulse_origin is not None


# ===================================================================
# SESSION TREND PHASE ENGINE (v3.0 IMPULSE-BASED)
# ===================================================================
class TrendPhaseEngine:
    """
    Prevents MODE_F from firing on exhausted moves
    Filters BEFORE signal generation, not at gate level
    
    Philosophy: Don't try to make late signals pass gates.
                Prevent late signals from existing.
    """
    
    @staticmethod
    def calculate_expansion(candles_5m, direction, atr):
        """
        Calculate session expansion multiple
        Returns: expansion_multiple (float)
        """
        try:
            price = float(candles_5m[-1]['close'])
            
            # Get session extremes
            session_high = max(float(c['high']) for c in candles_5m)
            session_low = min(float(c['low']) for c in candles_5m)
            
            # Calculate move from extreme
            if direction == "BUY":
                session_move = price - session_low
            else:  # SELL
                session_move = session_high - price
            
            # Expansion multiple
            if atr > 0:
                expansion_multiple = session_move / atr
            else:
                expansion_multiple = 0
            
            return expansion_multiple
        
        except Exception as e:
            print(f"⚠️ Expansion calculation error: {e}")
            return 0
    
    @staticmethod
    def get_phase(expansion_multiple):
        """
        Determine current session phase
        Returns: ("EARLY"|"MID"|"LATE")
        """
        if expansion_multiple < SESSION_TREND_PHASE['early']['max_expansion_atr']:
            return "EARLY"
        elif expansion_multiple <= SESSION_TREND_PHASE['mid']['max_expansion_atr']:
            return "MID"
        else:
            return "LATE"
    
    @staticmethod
    def check_mid_phase_conditions(candles_5m, indicators, direction):
        """
        Check if MID phase conditions are met
        Returns: (allowed, reason)
        """
        try:
            conditions = SESSION_TREND_PHASE['mid']['conditions']
            
            # Check pullback depth
            price = float(candles_5m[-1]['close'])
            
            # Get recent high/low (last 5 candles)
            recent = candles_5m[-5:]
            recent_high = max(float(c['high']) for c in recent)
            recent_low = min(float(c['low']) for c in recent)
            
            if direction == "BUY":
                pullback_depth = recent_high - price
            else:
                pullback_depth = price - recent_low
            
            max_pullback = conditions['max_pullback_atr'] * indicators['atr']
            
            if pullback_depth > max_pullback:
                return False, f"MID phase: Pullback too deep ({pullback_depth:.1f} > {max_pullback:.1f})"
            
            # Check RSI continuation
            rsi = indicators['rsi']
            if direction == "BUY" and rsi < conditions['min_rsi']:
                return False, f"MID phase: RSI not confirming ({rsi:.1f} < {conditions['min_rsi']})"
            elif direction == "SELL" and rsi > (100 - conditions['min_rsi']):
                return False, f"MID phase: RSI not confirming ({rsi:.1f} > {100 - conditions['min_rsi']})"
            
            # Structure check (simplified: check last 3 candles)
            if conditions['require_structure']:
                last_3 = candles_5m[-3:]
                closes = [float(c['close']) for c in last_3]
                
                if direction == "BUY":
                    # Should have higher lows
                    lows = [float(c['low']) for c in last_3]
                    if not (lows[1] >= lows[0] and lows[2] >= lows[1]):
                        return False, "MID phase: Structure broken (no HH-HL)"
                else:
                    # Should have lower highs
                    highs = [float(c['high']) for c in last_3]
                    if not (highs[1] <= highs[0] and highs[2] <= highs[1]):
                        return False, "MID phase: Structure broken (no LH-LL)"
            
            return True, None
        
        except Exception as e:
            print(f"⚠️ MID phase check error: {e}")
            return False, "MID phase: Check error"
    
    @staticmethod
    def is_mode_f_allowed(candles_5m, indicators, direction, impulse_engine=None):
        """
        Main phase filter for MODE_F (v3.0 IMPULSE-BASED)
        
        v3.0: Uses expansion from impulse origin, not day extremes
        
        Returns: (allowed, reason, phase, expansion)
        """
        try:
            # v3.0: Get expansion from impulse, not session extremes
            if impulse_engine and impulse_engine.is_impulse_active():
                price = float(candles_5m[-1]['close'])
                expansion = impulse_engine.get_expansion_from_impulse(price)
            else:
                # Fallback: No impulse detected yet, allow (will be caught later)
                return True, None, "NO_IMPULSE", 0.0
            
            # Get phase
            phase = TrendPhaseEngine.get_phase(expansion)
            
            # EARLY: Fully allowed
            if phase == "EARLY":
                return True, None, phase, expansion
            
            # MID: Conditional
            elif phase == "MID":
                allowed, reason = TrendPhaseEngine.check_mid_phase_conditions(
                    candles_5m, indicators, direction
                )
                if not allowed:
                    return False, reason, phase, expansion
                
                return True, None, phase, expansion
            
            # LATE: Disabled
            else:  # phase == "LATE"
                reason = SESSION_TREND_PHASE['late']['reason']
                return False, f"LATE phase ({expansion:.1f}× ATR from impulse): {reason}", phase, expansion
        
        except Exception as e:
            print(f"⚠️ Phase filter error: {e}")
            # Allow on error (fail-safe)
            return True, None, "UNKNOWN", 0.0


# ===================================================================
# EXECUTION GATES (ALL MUST PASS)
# ===================================================================
class ExecutionGates:
    """
    Triple gate system that runs before EVERY trade
    """
    
    @staticmethod
    def gate_1_move_exhaustion(candles_5m, indicators, direction, impulse_engine=None):
        """
        Gate 1: Move Exhaustion (v3.0 IMPULSE-BASED)
        Block if price too far from impulse origin (not day extremes)
        
        v3.0: Now uses impulse-based expansion like Phase Filter
        """
        try:
            price = float(candles_5m[-1]['close'])
            atr = indicators['atr']
            
            # v3.0: Use impulse-based expansion if available
            if impulse_engine and impulse_engine.is_impulse_active():
                expansion = impulse_engine.get_expansion_from_impulse(price)
                threshold_multiple = EXECUTION_GATES['exhaustion_atr_multiple']
                
                # v3.1: Regime-aware exhaustion threshold
                if hasattr(self, '_day_type_override'):
                    pass  # Will be handled by caller
                
                if expansion > threshold_multiple:
                    return False, f"Move exhausted (Expansion {expansion:.1f}× ATR from impulse, threshold {threshold_multiple}×)"
                
                return True, None
            
            else:
                # Fallback: No impulse detected yet, use day extremes
                day_high = max(float(c['high']) for c in candles_5m)
                day_low = min(float(c['low']) for c in candles_5m)
                day_range = day_high - day_low
                
                atr_threshold = EXECUTION_GATES['exhaustion_atr_multiple'] * atr
                range_threshold = EXECUTION_GATES['exhaustion_day_range_pct'] * day_range
                
                # Calculate distance from extreme
                if direction == "BUY":
                    distance_from_low = price - day_low
                    threshold = min(atr_threshold, range_threshold)
                    
                    if distance_from_low > threshold:
                        return False, f"Move exhausted (Price {distance_from_low:.1f} from low, threshold {threshold:.1f})"
                
                elif direction == "SELL":
                    distance_from_high = day_high - price
                    threshold = min(atr_threshold, range_threshold)
                    
                    if distance_from_high > threshold:
                        return False, f"Move exhausted (Price {distance_from_high:.1f} from high, threshold {threshold:.1f})"
                
                return True, None
        
        except Exception as e:
            print(f"Gate 1 error: {e}")
            return True, None  # Allow on error
    
    @staticmethod
    def gate_2_time_day_type(current_time, day_type):
        """
        Gate 2: Time + Day Type
        Block after 12:30 if day type is bad
        """
        time_only = current_time.time()
        
        if time_only > EXECUTION_GATES['late_cutoff_time']:
            bad_day_types = [
                DayType.EARLY_IMPULSE_SIDEWAYS,
                DayType.RANGE_CHOPPY,
                DayType.EXPIRY_DISTORTION,
                DayType.ROTATIONAL_EXPANSION,
                DayType.FAST_REGIME_FLIP,
            ]
            
            if day_type in bad_day_types:
                return False, f"Post 12:30 + Day Type = {day_type.value}"
        
        return True, None
    
    @staticmethod
    def gate_3_rsi_compression(candles_5m, indicators):
        """
        Gate 3: RSI Compression
        Block if RSI stuck in 48-62 for >10 candles with overlap
        """
        try:
            from unified_engine import calculate_rsi
            
            if len(candles_5m) < 15:
                return True, None
            
            # Calculate RSI for last 15 candles
            rsi_values = []
            for i in range(-15, 0):
                closes = [float(c['close']) for c in candles_5m[:len(candles_5m)+i+1]]
                if len(closes) >= 14:
                    rsi_arr = calculate_rsi(closes, 14)
                    if len(rsi_arr) > 0:
                        rsi_values.append(rsi_arr[-1])
            
            if len(rsi_values) < 10:
                return True, None
            
            # Check if stuck in compression zone
            compression_count = sum(
                1 for rsi in rsi_values[-10:]
                if EXECUTION_GATES['rsi_compression_min'] <= rsi <= EXECUTION_GATES['rsi_compression_max']
            )
            
            if compression_count >= 10:
                # Also check for candle overlap
                last_10 = candles_5m[-10:]
                overlap_count = 0
                
                for i in range(1, len(last_10)):
                    curr_h = float(last_10[i]['high'])
                    curr_l = float(last_10[i]['low'])
                    prev_h = float(last_10[i-1]['high'])
                    prev_l = float(last_10[i-1]['low'])
                    
                    # Inside bar or overlap
                    if (curr_h <= prev_h and curr_l >= prev_l) or \
                       (prev_h <= curr_h and prev_l >= curr_l):
                        overlap_count += 1
                
                if overlap_count >= 5:
                    return False, "RSI compression + candle overlap (No momentum)"
            
            return True, None
        
        except Exception as e:
            print(f"Gate 3 error: {e}")
            return True, None


# ===================================================================
# OPENING IMPULSE MODULE
# ===================================================================
class OpeningImpulseTracker:
    """
    Limited early morning trading (09:15-09:40)
    Max 1 trade per index OR 1 total if correlated
    """
    
    def __init__(self):
        self.impulse_fired = {}  # {instrument: True/False}
        self.total_impulse_count = 0
        self.last_reset_date = None
    
    def reset_for_new_day(self, date):
        """Reset daily counters"""
        if self.last_reset_date != date:
            self.impulse_fired = {}
            self.total_impulse_count = 0
            self.last_reset_date = date
    
    def is_allowed(self, instrument, current_time, is_expiry_day, indices_correlated=False):
        """
        Check if opening impulse is allowed
        """
        time_only = current_time.time()
        
        # Time window check
        if not (OPENING_IMPULSE_CONFIG['time_start'] <= time_only <= OPENING_IMPULSE_CONFIG['time_end']):
            return False, "Outside opening impulse window"
        
        # Max 1 per instrument
        if self.impulse_fired.get(instrument, False):
            return False, "Impulse already fired for this instrument"
        
        # If correlated, max 1 total
        if indices_correlated and self.total_impulse_count >= 1:
            return False, "Impulse already fired (correlated indices)"
        
        # Expiry rule: Only non-expiry index
        if is_expiry_day:
            return False, "Expiry day - impulse not allowed"
        
        return True, None
    
    def check_impulse_conditions(self, candles_5m, indicators):
        """
        Check if impulse conditions are met
        Returns: (valid, move_atr_multiple)
        """
        try:
            if len(candles_5m) < 5:
                return False, 0
            
            # Get opening candles
            opening_candles = candles_5m[:min(5, len(candles_5m))]
            
            # Opening move magnitude
            opening_high = max(float(c['high']) for c in opening_candles)
            opening_low = min(float(c['low']) for c in opening_candles)
            opening_range = opening_high - opening_low
            
            atr = indicators['atr']
            move_atr_multiple = opening_range / atr if atr > 0 else 0
            
            # Must be >= 0.6 ATR
            if move_atr_multiple < OPENING_IMPULSE_CONFIG['min_move_atr_multiple']:
                return False, move_atr_multiple
            
            # Check last candle quality
            last_candle = candles_5m[-1]
            body = abs(float(last_candle['close']) - float(last_candle['open']))
            candle_range = float(last_candle['high']) - float(last_candle['low'])
            
            if candle_range > 0:
                body_pct = body / candle_range
                # Strong body, minimal wick
                if body_pct < 0.65:
                    return False, move_atr_multiple
            
            # RSI slope accelerating
            rsi = indicators['rsi']
            if not (rsi > 60 or rsi < 40):  # Strong directional
                return False, move_atr_multiple
            
            return True, move_atr_multiple
        
        except Exception as e:
            print(f"Impulse check error: {e}")
            return False, 0
    
    def register_impulse(self, instrument):
        """Mark impulse as fired"""
        self.impulse_fired[instrument] = True
        self.total_impulse_count += 1


# ===================================================================
# CORRELATION BRAKE
# ===================================================================
class CorrelationBrake:
    """
    Prevents stacked drawdowns across correlated indices
    """
    
    def __init__(self):
        self.sl_history = {}  # {instrument: [(timestamp, direction, day_type), ...]}
        self.blocked_instruments = {}  # {instrument: block_until_time}
    
    def register_sl(self, instrument, direction, day_type, timestamp):
        """Record a stop loss hit"""
        if instrument not in self.sl_history:
            self.sl_history[instrument] = deque(maxlen=10)
        
        self.sl_history[instrument].append((timestamp, direction, day_type))
    
    def check_and_block(self, instrument_a, instrument_b, current_time, indices_correlated=False):
        """
        Check if instrument_b should be blocked due to instrument_a losses
        Returns: (blocked, reason)
        """
        # Clear expired blocks
        self._clear_expired_blocks(current_time)
        
        # Check if already blocked
        if instrument_b in self.blocked_instruments:
            block_until = self.blocked_instruments[instrument_b]
            if current_time < block_until:
                time_left = (block_until - current_time).total_seconds() / 60
                return True, f"Correlation brake active ({time_left:.0f} min remaining)"
        
        # Get recent SLs for instrument A
        if instrument_a not in self.sl_history:
            return False, None
        
        recent_sls = [
            sl for sl in self.sl_history[instrument_a]
            if (current_time - sl[0]).total_seconds() <= CORRELATION_BRAKE_CONFIG['time_window_minutes'] * 60
        ]
        
        if len(recent_sls) < CORRELATION_BRAKE_CONFIG['sl_count_trigger']:
            return False, None
        
        # Check if same day type and direction
        if len(recent_sls) >= 2:
            last_two = recent_sls[-2:]
            same_direction = last_two[0][1] == last_two[1][1]
            same_day_type = last_two[0][2] == last_two[1][2]
            
            if same_direction and same_day_type and indices_correlated:
                # Block instrument B
                block_until = current_time + timedelta(minutes=CORRELATION_BRAKE_CONFIG['block_duration_minutes'])
                self.blocked_instruments[instrument_b] = block_until
                
                return True, f"2 SLs on {instrument_a} within 60min (Same direction & day type)"
        
        return False, None
    
    def _clear_expired_blocks(self, current_time):
        """Remove expired blocks"""
        expired = [
            inst for inst, block_until in self.blocked_instruments.items()
            if current_time >= block_until
        ]
        for inst in expired:
            del self.blocked_instruments[inst]


# ===================================================================
# SYSTEM STOP STATE
# ===================================================================
class SystemStopManager:
    """
    Hard stop when market conditions are hostile
    """
    
    def __init__(self):
        self.stopped = False
        self.stop_reason = None
        self.consecutive_blocks = 0
        self.sl_count_after_cutoff = 0
    
    def reset_for_new_day(self):
        """Reset at market open"""
        self.stopped = False
        self.stop_reason = None
        self.consecutive_blocks = 0
        self.sl_count_after_cutoff = 0
    
    def register_block(self):
        """Count consecutive execution blocks"""
        self.consecutive_blocks += 1
    
    def reset_consecutive_blocks(self):
        """Reset on successful execution"""
        self.consecutive_blocks = 0
    
    def register_sl(self, timestamp):
        """Count SLs after cutoff time"""
        if timestamp.time() > SYSTEM_STOP_TRIGGERS['sl_after_time']:
            self.sl_count_after_cutoff += 1
    
    def check_stop_conditions(self, day_type):
        """
        Check if system should stop
        Returns: (should_stop, reason)
        """
        # Already stopped
        if self.stopped:
            return True, self.stop_reason
        
        # Condition 1: Range/Choppy or Liquidity Sweep Trap
        if day_type in [DayType.RANGE_CHOPPY, DayType.LIQUIDITY_SWEEP_TRAP]:
            self.stopped = True
            self.stop_reason = f"Market conditions hostile ({day_type.value})"
            return True, self.stop_reason
        
        # Condition 2: 3 consecutive blocks
        if self.consecutive_blocks >= SYSTEM_STOP_TRIGGERS['consecutive_blocks']:
            self.stopped = True
            self.stop_reason = "3 consecutive execution blocks"
            return True, self.stop_reason
        
        # Condition 3: 2 SLs after 11:30
        if self.sl_count_after_cutoff >= SYSTEM_STOP_TRIGGERS['sl_count_after_time']:
            self.stopped = True
            self.stop_reason = "2 stop losses after 11:30 IST"
            return True, self.stop_reason
        
        return False, None
    
    def force_stop(self, reason):
        """Manual stop"""
        self.stopped = True
        self.stop_reason = reason


# ===================================================================
# MODE PERMISSION CHECKER
# ===================================================================
class ModePermissionChecker:
    """
    Validates if a mode is allowed to trade given current context
    """
    
    @staticmethod
    def check_mode_f(day_type, current_time, is_expiry_day):
        """Check if MODE_F is allowed"""
        # Day type check (v3.1: ROTATIONAL_EXPANSION allows 1 conditional trade)
        if day_type not in MODE_F_ALLOWED_DAY_TYPES:
            # v3.1: ROTATIONAL_EXPANSION = conditional allow (max 1)
            if day_type == DayType.ROTATIONAL_EXPANSION:
                return True, "MODE_F conditional (ROTATIONAL_EXPANSION: max 1 trade)"
            # v3.1: FAST_REGIME_FLIP = conditional allow (max 1, stricter RSI)
            if day_type == DayType.FAST_REGIME_FLIP:
                return True, "MODE_F conditional (FAST_REGIME_FLIP: max 1 continuation)"
            return False, f"MODE_F blocked (Day Type: {day_type.value})"
        
        # Not in late expiry phase
        if is_expiry_day and current_time.time() > dtime(14, 0):
            return False, "MODE_F blocked (Late expiry phase)"
        
        return True, None
    
    @staticmethod
    def check_mode_s_core(day_type, current_time):
        """Check if MODE_S CORE/STABILITY is allowed"""
        # Day type check
        if day_type not in MODE_S_CORE_STABILITY_ALLOWED:
            return False, f"MODE_S CORE blocked (Day Type: {day_type.value})"
        
        # Time check
        if current_time.time() > MODE_S_CORE_CUTOFF:
            return False, "MODE_S CORE blocked (After 13:30)"
        
        return True, None
    
    @staticmethod
    def check_mode_s_liquidity(day_type, current_time):
        """Check if MODE_S LIQUIDITY is allowed"""
        # Day type check
        if day_type not in MODE_S_LIQUIDITY_ALLOWED:
            return False, f"MODE_S LIQUIDITY blocked (Day Type: {day_type.value})"
        
        # Time check
        if current_time.time() > MODE_S_LIQUIDITY_CUTOFF:
            return False, "MODE_S LIQUIDITY blocked (After 13:00)"
        
        # No forced trades on bad days
        if day_type in [DayType.EXPIRY_DISTORTION, DayType.RANGE_CHOPPY,
                        DayType.LIQUIDITY_SWEEP_TRAP, DayType.ROTATIONAL_EXPANSION,
                        DayType.FAST_REGIME_FLIP]:
            return False, "No forced trades on hostile days"
        
        return True, None


# Export main classes
__all__ = [
    'DayTypeEngine',
    'ImpulseDetectionEngine',
    'TrendPhaseEngine',
    'ExecutionGates',
    'OpeningImpulseTracker',
    'CorrelationBrake',
    'SystemStopManager',
    'ModePermissionChecker',
]
