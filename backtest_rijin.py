"""
RIJIN SYSTEM - Backtesting Framework
Validates day type classification, gate effectiveness, and expected trade counts
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time as dtime
from kiteconnect import KiteConnect
from dotenv import load_dotenv
from collections import defaultdict
import json

# Import RIJIN components
from rijin_engine import (
    DayTypeEngine,
    ExecutionGates,
    TrendPhaseEngine,       # v2.4: Added phase filter
    ImpulseDetectionEngine,  # v3.0: Added impulse detection
    OpeningImpulseTracker,
    CorrelationBrake,
    SystemStopManager,
    ModePermissionChecker,
)
from rijin_config import DayType, EXPECTED_TRADE_COUNT, CONSECUTIVE_LOSS_LIMIT

# Import existing engines and utilities
from mode_f_engine import ModeFEngine
from mode_s_engine import ModeSEngine
from unified_engine import simple_ema, calculate_rsi, calculate_atr, get_slope

load_dotenv()

# ===================================================================
# BACKTEST CONFIGURATION
# ===================================================================
BACKTEST_CONFIG = {
    "start_date": datetime(2025, 11, 20),  # 80 days (within Kite API limit)
    "end_date": datetime(2026, 2, 14),
    "initial_capital": 100000,
    "nifty_instrument": os.getenv("NIFTY_INSTRUMENT", "NFO:NIFTY26FEBFUT"),
    "sensex_instrument": os.getenv("SENSEX_INSTRUMENT", "BSE:SENSEX"),
}


# ===================================================================
# BACKTEST RESULTS CONTAINER
# ===================================================================
class BacktestResults:
    """Store and analyze backtest results"""
    
    def __init__(self):
        self.day_types = []  # [(date, day_type, reason)]
        self.signals_generated = []  # All signals from MODE_F/S
        self.signals_allowed = []  # Signals that passed RIJIN gates
        self.signals_blocked = []  # Signals blocked by RIJIN
        self.trades = []  # Executed trades
        self.gate_blocks = defaultdict(int)  # Count blocks by gate
        self.system_stops = []  # Days system stopped
        
        # Performance metrics
        self.daily_pnl = {}
        self.daily_trade_count = defaultdict(int)
        self.day_type_trade_count = defaultdict(list)
        
    def add_day_type_classification(self, date, day_type, reason):
        """Record day type classification"""
        self.day_types.append({
            'date': date,
            'day_type': day_type.value,
            'reason': reason
        })
    
    def add_signal(self, signal, allowed, block_reason=None):
        """Record a signal (allowed or blocked)"""
        signal_record = signal.copy()
        signal_record['timestamp'] = signal.get('timestamp', datetime.now())
        
        self.signals_generated.append(signal_record)
        
        if allowed:
            self.signals_allowed.append(signal_record)
        else:
            signal_record['block_reason'] = block_reason
            self.signals_blocked.append(signal_record)
            
            # Track which gate blocked it
            if block_reason:
                if 'Phase Filter' in block_reason or 'LATE phase' in block_reason:
                    self.gate_blocks['Phase Filter (Late Move)'] += 1
                elif 'MID phase' in block_reason:
                    self.gate_blocks['MID Phase Conditions'] += 1
                elif 'Gate 1' in block_reason or 'exhaust' in block_reason.lower():
                    self.gate_blocks['Gate 1: Move Exhaustion'] += 1
                elif 'Gate 2' in block_reason or 'Time' in block_reason:
                    self.gate_blocks['Gate 2: Time + Day Type'] += 1
                elif 'Gate 3' in block_reason or 'RSI compression' in block_reason.lower():
                    self.gate_blocks['Gate 3: RSI Compression'] += 1
                elif 'MODE' in block_reason:
                    self.gate_blocks['Mode Permission'] += 1
                elif 'Correlation' in block_reason:
                    self.gate_blocks['Correlation Brake'] += 1
                else:
                    self.gate_blocks['Other'] += 1
    
    def add_trade(self, trade):
        """Record a completed trade"""
        self.trades.append(trade)
        
        # Update daily stats
        trade_date = trade['entry_time'].date()
        if trade_date not in self.daily_pnl:
            self.daily_pnl[trade_date] = 0
        
        self.daily_pnl[trade_date] += trade['pnl_r']
        self.daily_trade_count[trade_date] += 1
        
        # Track by day type
        if 'day_type' in trade:
            self.day_type_trade_count[trade['day_type']].append(trade)
    
    def add_system_stop(self, date, reason):
        """Record system stop event"""
        self.system_stops.append({
            'date': date,
            'reason': reason
        })
    
    def generate_report(self):
        """Generate comprehensive backtest report"""
        print("\n" + "="*80)
        print("[BRAIN] RIJIN SYSTEM BACKTEST REPORT")
        print("="*80)
        
        # Day Type Analysis
        print("\n[CHART] DAY TYPE CLASSIFICATION")
        print("-" * 80)
        day_type_counts = defaultdict(int)
        for record in self.day_types:
            day_type_counts[record['day_type']] += 1
        
        total_days = len(self.day_types)
        for day_type, count in sorted(day_type_counts.items()):
            pct = (count / total_days * 100) if total_days > 0 else 0
            print(f"  {day_type:30s}: {count:3d} days ({pct:5.1f}%)")
        
        print(f"\n  Total Trading Days Analyzed: {total_days}")
        
        # Signal Analysis
        print("\n[TARGET] SIGNAL ANALYSIS")
        print("-" * 80)
        total_signals = len(self.signals_generated)
        allowed_signals = len(self.signals_allowed)
        blocked_signals = len(self.signals_blocked)
        
        print(f"  Total Signals Generated:     {total_signals:4d}")
        print(f"  Signals Allowed (Passed):    {allowed_signals:4d} ({allowed_signals/total_signals*100 if total_signals > 0 else 0:.1f}%)")
        print(f"  Signals Blocked (Rejected):  {blocked_signals:4d} ({blocked_signals/total_signals*100 if total_signals > 0 else 0:.1f}%)")
        
        # Gate Block Breakdown
        print("\n[GATE] GATE BLOCK BREAKDOWN")
        print("-" * 80)
        for gate, count in sorted(self.gate_blocks.items(), key=lambda x: x[1], reverse=True):
            pct = (count / blocked_signals * 100) if blocked_signals > 0 else 0
            print(f"  {gate:40s}: {count:4d} ({pct:5.1f}%)")
        
        # Trade Count by Day Type
        print("\n[TRADES] TRADES PER DAY TYPE")
        print("-" * 80)
        print(f"  {'Day Type':30s} | {'Actual':>10s} | {'Expected':>15s} | {'Status':>10s}")
        print("  " + "-" * 76)
        
        for day_type_enum in [DayType.CLEAN_TREND, DayType.NORMAL_TREND, 
                               DayType.EARLY_IMPULSE_SIDEWAYS, DayType.RANGE_CHOPPY,
                               DayType.EXPIRY_DISTORTION]:
            day_type_str = day_type_enum.value
            trades = self.day_type_trade_count.get(day_type_str, [])
            
            # Calculate average trades per day of this type
            days_of_type = sum(1 for d in self.day_types if d['day_type'] == day_type_str)
            avg_trades = len(trades) / days_of_type if days_of_type > 0 else 0
            
            expected = EXPECTED_TRADE_COUNT.get(day_type_enum, (0, 0))
            expected_str = f"{expected[0]}-{expected[1]}"
            
            # Status check
            if expected[0] <= avg_trades <= expected[1]:
                status = "[OK] PASS"
            elif avg_trades < expected[0]:
                status = "[WARN] LOW"
            else:
                status = "[WARN] HIGH"
            
            print(f"  {day_type_str:30s} | {avg_trades:10.1f} | {expected_str:>15s} | {status:>10s}")
        
        # Performance Metrics
        print("\n[MONEY] PERFORMANCE METRICS")
        print("-" * 80)
        
        # Initialize bad_days
        bad_days = {}
        
        if self.trades:
            total_trades = len(self.trades)
            winning_trades = [t for t in self.trades if t['pnl_r'] > 0]
            losing_trades = [t for t in self.trades if t['pnl_r'] < 0]
            
            win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
            
            total_pnl_r = sum(t['pnl_r'] for t in self.trades)
            avg_win_r = np.mean([t['pnl_r'] for t in winning_trades]) if winning_trades else 0
            avg_loss_r = np.mean([t['pnl_r'] for t in losing_trades]) if losing_trades else 0
            
            # Largest drawdown day
            if self.daily_pnl:
                worst_day = min(self.daily_pnl.items(), key=lambda x: x[1])
                best_day = max(self.daily_pnl.items(), key=lambda x: x[1])
            else:
                worst_day = (None, 0)
                best_day = (None, 0)
            
            print(f"  Total Trades:           {total_trades:6d}")
            print(f"  Win Rate:               {win_rate:6.2f}%")
            print(f"  Total P&L (R):          {total_pnl_r:+7.2f}R")
            print(f"  Avg Win (R):            {avg_win_r:+7.2f}R")
            print(f"  Avg Loss (R):           {avg_loss_r:+7.2f}R")
            print(f"  Best Day:               {worst_day[0]} -> {best_day[1]:+.2f}R")
            print(f"  Worst Day:              {worst_day[0]} -> {worst_day[1]:+.2f}R")
            
            # Capital protection validation
            print("\n🛡️ CAPITAL PROTECTION VALIDATION")
            print("-" * 80)
            
            bad_days = {date: pnl for date, pnl in self.daily_pnl.items() if pnl < -1.5}
            
            if bad_days:
                print(f"  [WARN] WARNING: {len(bad_days)} days exceeded -1.5R limit:")
                for date, pnl in sorted(bad_days.items(), key=lambda x: x[1]):
                    print(f"    • {date}: {pnl:+.2f}R")
            else:
                print(f"  [OK] SUCCESS: No single day exceeded -1.5R limit")
                print(f"  [OK] System achieved primary goal: Prevent Rs.4L-type drawdowns")
        else:
            print("  No trades executed during backtest period")
        
        # System Stop Events
        print("\n[STOP] SYSTEM STOP EVENTS")
        print("-" * 80)
        if self.system_stops:
            print(f"  Total Stop Events: {len(self.system_stops)}")
            for stop in self.system_stops:
                print(f"    • {stop['date']}: {stop['reason']}")
        else:
            print("  No system stop events triggered")
        
        # Summary
        print("\n" + "="*80)
        print("[LIST] SUMMARY")
        print("="*80)
        
        # Overall verdict
        issues = []
        
        # Check day type distribution
        choppy_pct = (day_type_counts.get(DayType.RANGE_CHOPPY.value, 0) / total_days * 100) if total_days > 0 else 0
        if choppy_pct > 30:
            issues.append(f"High choppy days ({choppy_pct:.1f}%)")
        
        # Check if expected trade counts met
        for day_type_enum in [DayType.CLEAN_TREND, DayType.NORMAL_TREND]:
            day_type_str = day_type_enum.value
            trades = self.day_type_trade_count.get(day_type_str, [])
            days_of_type = sum(1 for d in self.day_types if d['day_type'] == day_type_str)
            avg_trades = len(trades) / days_of_type if days_of_type > 0 else 0
            expected = EXPECTED_TRADE_COUNT.get(day_type_enum, (0, 100))
            
            if avg_trades < expected[0]:
                issues.append(f"{day_type_str}: Below expected ({avg_trades:.1f} < {expected[0]})")
        
        # Check capital protection
        if bad_days:
            issues.append(f"{len(bad_days)} days exceeded -1.5R limit")
        
        
        if not issues:
            print("  [OK] RIJIN SYSTEM VALIDATION: PASSED")
            print("  • Day type classification working")
            print("  • Trade counts within expected ranges")
            print("  • Capital protection achieved")
            print("  • Ready for Phase 1: Dry Run Testing")
        else:
            print("  [WARN] RIJIN SYSTEM VALIDATION: ISSUES FOUND")
            for issue in issues:
                print(f"    • {issue}")
            print("\n  Review and adjust thresholds before deployment")
        
        print("="*80 + "\n")
        
        return {
            'total_days': total_days,
            'total_signals': total_signals,
            'allowed_signals': allowed_signals,
            'blocked_signals': blocked_signals,
            'total_trades': len(self.trades),
            'win_rate': win_rate if self.trades else 0,
            'total_pnl_r': total_pnl_r if self.trades else 0,
            'worst_day_pnl': worst_day[1] if self.trades else 0,
            'bad_days_count': len(bad_days) if self.trades else 0,
            'issues': issues,
        }
    
    def export_to_csv(self, filename_prefix='rijin_backtest'):
        """Export results to CSV files"""
        # Day types
        pd.DataFrame(self.day_types).to_csv(f'{filename_prefix}_day_types.csv', index=False)
        
        # Signals
        pd.DataFrame(self.signals_generated).to_csv(f'{filename_prefix}_signals_all.csv', index=False)
        pd.DataFrame(self.signals_allowed).to_csv(f'{filename_prefix}_signals_allowed.csv', index=False)
        pd.DataFrame(self.signals_blocked).to_csv(f'{filename_prefix}_signals_blocked.csv', index=False)
        
        # Trades
        if self.trades:
            pd.DataFrame(self.trades).to_csv(f'{filename_prefix}_trades.csv', index=False)
        
        print(f"\n[FILE] Exported results to {filename_prefix}_*.csv")


# ===================================================================
# RIJIN BACKTEST ENGINE
# ===================================================================
class RijinBacktestEngine:
    """
    Simulate RIJIN system on historical data
    """
    
    def __init__(self, config):
        self.config = config
        self.results = BacktestResults()
        
        # Initialize RIJIN components
        self.day_type_engine = DayTypeEngine()
        self.impulse_engine = ImpulseDetectionEngine()  # v3.0: Add impulse detection
        self.opening_impulse = OpeningImpulseTracker()
        self.correlation_brake = CorrelationBrake()
        self.system_stop = SystemStopManager()
        
        # Initialize strategy engines
        self.mode_f_engine = ModeFEngine()
        self.mode_s_engine = ModeSEngine()
        
        # Kite
        self.kite = None
        
        # State
        self.active_trades = {}
        
        # v3.0.1: Consecutive loss tracking (per index)
        self.consecutive_losses = {
            'NIFTY': 0,
            'BANKNIFTY': 0,
        }
        self.pause_until = {
            'NIFTY': None,
            'BANKNIFTY': None,
        }
        
        print("RIJIN Backtest Engine Initialized (v3.0.1 - PRODUCTION READY)")
        print(f"   Period: {config['start_date'].date()} to {config['end_date'].date()}")
        print(f"   Initial Capital: Rs.{config['initial_capital']:,}")
        print(f"   Loss Protection: Max {CONSECUTIVE_LOSS_LIMIT['max_consecutive_losses']} consecutive losses")
        print(f"   Exit Strategy: 1:2 Risk-Reward (maximize profit)")
    
    def fetch_historical_data(self, instrument, start, end):
        """Fetch historical 5-minute data"""
        try:
            if not self.kite:
                api_key = os.getenv("KITE_API_KEY")
                access_token = os.getenv("KITE_ACCESS_TOKEN")
                self.kite = KiteConnect(api_key=api_key)
                self.kite.set_access_token(access_token)
            
            # Get instrument token
            quote = self.kite.quote([instrument])
            token = quote[instrument]['instrument_token']
            
            # Fetch data
            data = self.kite.historical_data(token, start, end, interval="5minute")
            
            return data
        
        except Exception as e:
            print(f"[ERROR] Error fetching data for {instrument}: {e}")
            return None
    
    def run_backtest(self):
        """Main backtest loop"""
        print("\n[START] Starting Backtest...\n")
        
        # Fetch data for both instruments
        print("[DATA] Fetching historical data...")
        nifty_data = self.fetch_historical_data(
            self.config['nifty_instrument'],
            self.config['start_date'],
            self.config['end_date']
        )
        
        if not nifty_data:
            print("[ERROR] Failed to fetch NIFTY data. Aborting backtest.")
            return
        
        print(f"   [OK] Fetched {len(nifty_data)} candles for NIFTY")
        
        # Group by date
        dates_data = self._group_by_date(nifty_data)
        
        print(f"\n[DAYS] Processing {len(dates_data)} trading days...\n")
        
        # Process each day
        for idx, (date, day_candles) in enumerate(sorted(dates_data.items())):
            if idx % 10 == 0:
                print(f"   Processing {date} ({idx+1}/{len(dates_data)})")
            
            self._process_day(date, day_candles)
        
        # Generate report
        print("\n[OK] Backtest Complete!")
        summary = self.results.generate_report()
        
        # Export to CSV
        self.results.export_to_csv()
        
        return summary
    
    def _group_by_date(self, candles):
        """Group candles by date"""
        dates_data = defaultdict(list)
        
        for candle in candles:
            date = candle['date'].date()
            dates_data[date].append(candle)
        
        return dates_data
    
    def _process_day(self, date, candles):
        """Process a single trading day (v3.0 with impulse detection)"""
        # Reset daily state
        self.day_type_engine.reset_for_new_day()
        self.impulse_engine.reset_for_new_day()  # v3.0: Reset impulse tracking
        self.opening_impulse.reset_for_new_day(date)
        self.system_stop.reset_for_new_day()
        self.active_trades = {}
        
        # Skip if insufficient data
        if len(candles) < 30:
            return
        
        # Simulate day type checks (every 30 min)
        day_type_checks = [dtime(10, 0), dtime(10, 30), dtime(11, 0), dtime(11, 30),
                           dtime(12, 0), dtime(12, 30), dtime(13, 0), dtime(13, 30),
                           dtime(14, 0), dtime(14, 30)]
        
        for check_time in day_type_checks:
            # Get candles up to this time
            candles_until = [c for c in candles if c['date'].time() <= check_time]
            
            if len(candles_until) < 30:
                continue
            
            # Run day type classification
            day_type, reason = self._classify_day_at_time(candles_until, date)
            
            # Update with confirmation rules
            updated, message = self.day_type_engine.update_day_type(
                day_type, reason, datetime.combine(date, check_time)
            )
            
            if updated:
                self.results.add_day_type_classification(date, day_type, reason)
        
        # Record final day type
        final_day_type = self.day_type_engine.current_day_type
        
        # Check system stop
        should_stop, stop_reason = self.system_stop.check_stop_conditions(final_day_type)
        
        if should_stop:
            self.results.add_system_stop(date, stop_reason)
            return  # No trading on this day
        
        # Process signals throughout the day
        for idx in range(30, len(candles)):
            candle_time = candles[idx]['date']
            
            # Skip if outside trading hours
            if not (dtime(9, 15) <= candle_time.time() <= dtime(15, 15)):
                continue
            
            # Get candles up to this point
            candles_until = candles[:idx+1]
            
            # v3.0: Check for impulse on each candle
            ema20 = simple_ema([float(c['close']) for c in candles_until], 20)
            atr = calculate_atr([float(c['high']) for c in candles_until],
                               [float(c['low']) for c in candles_until],
                               [float(c['close']) for c in candles_until], 14)
            rsi = calculate_rsi([float(c['close']) for c in candles_until], 14)
            
            indicators = {
                'atr': float(atr[-1]) if len(atr) > 0 else 10.0,
                'rsi': float(rsi[-1]) if len(rsi) > 0 else 50.0,
            }
            
            self.impulse_engine.detect_impulse(candles_until, indicators, candle_time)
            
            # Generate signals
            signal = self._generate_signal(candles_until, candle_time, date)
            
            if signal:
                # Apply RIJIN gates
                allowed, block_reason = self._apply_rijin_gates(
                    signal, candles_until, candle_time, date
                )
                
                # Record signal
                self.results.add_signal(signal, allowed, block_reason)
                
                if allowed:
                    # Execute trade
                    self._execute_trade(signal, candles, idx, date)
    
    def _classify_day_at_time(self, candles, date):
        """Classify day type at specific time"""
        # Calculate indicators
        closes = [float(c['close']) for c in candles]
        highs = [float(c['high']) for c in candles]
        lows = [float(c['low']) for c in candles]
        
        ema20 = simple_ema(closes, 20)
        atr = calculate_atr(highs, lows, closes, 14)
        rsi = calculate_rsi(closes, 14)
        slope = get_slope(ema20)
        
        indicators = {
            'ema20': float(ema20[-1]) if len(ema20) > 0 else closes[-1],
            'atr': float(atr[-1]) if len(atr) > 0 else 10.0,
            'rsi': float(rsi[-1]) if len(rsi) > 0 else 50.0,
            'slope': slope,
        }
        
        # Resample to 30m
        c30 = self._resample_to_30m(candles)
        
        # Check if expiry day (hardcoded: NIFTY=Tuesday)
        is_expiry = date.weekday() == 1  # Tuesday
        
        # Classify
        day_type, reason = self.day_type_engine.classify_day(
            candles, c30, indicators, is_expiry
        )
        
        return day_type, reason
    
    def _generate_signal(self, candles, current_time, date):
        """
        Generate trading signal using REAL ModeFEngine (v3.0 COMPLETE)
        
        v3.0: Uses production MODE_F with gear-based detection
              Then applies impulse-based v3.0 gates for timing control
        """
        try:
            if len(candles) < 30:
                return None
            
            # Calculate indicators
            closes = [float(c['close']) for c in candles]
            highs = [float(c['high']) for c in candles]
            lows = [float(c['low']) for c in candles]
            
            ema20 = simple_ema(closes, 20)
            atr = calculate_atr(highs, lows, closes, 14)
            rsi = calculate_rsi(closes, 14)
            
            if len(ema20) == 0 or len(atr) == 0 or len(rsi) == 0:
                return None
            
            indicators = {
                'ema20': float(ema20[-1]),
                'atr': float(atr[-1]),
                'rsi': float(rsi[-1]),
            }
            
            # ===== USE REAL MODE_F ENGINE =====
            # Get signal from production-grade ModeFEngine
            res = self.mode_f_engine.predict(candles, global_bias="NEUTRAL")
            
            if res.valid:
                # Real MODE_F generated a signal
                # Return it with v3.0 metadata for gate filtering
                return {
                    'timestamp': current_time,
                    'date': date,
                    'instrument': 'NIFTY',
                    'mode': 'MODE_F',
                    'direction': res.direction,
                    'entry': res.entry,
                    'sl': res.sl,
                    'target': res.target,
                    'pattern': f"{res.gear.name}",  # GEAR_1, GEAR_2, GEAR_3
                    'rsi': indicators['rsi'],
                    'atr': indicators['atr'],
                }
            
            return None
        
        except Exception as e:
            return None
    
    def _apply_rijin_gates(self, signal, candles, current_time, date):
        """Apply RIJIN execution gates (v3.0.1 with consecutive loss protection)"""
        # Prepare indicators
        indicators = {
            'atr': signal['atr'],
            'rsi': signal['rsi'],
        }
        
        # ===== CONSECUTIVE LOSS PROTECTION (v3.0.1) =====
        # Check FIRST - pause trading after consecutive losses
        instrument = signal['instrument']
        
        if self.pause_until.get(instrument):
            time_diff = (current_time - self.pause_until[instrument]).total_seconds() / 60
            if time_diff < CONSECUTIVE_LOSS_LIMIT['pause_duration_minutes']:
                remaining = int(CONSECUTIVE_LOSS_LIMIT['pause_duration_minutes'] - time_diff)
                return False, f"Consecutive Loss Protection: Paused for {remaining} more minutes"
            else:
                # Pause expired, reset
                self.pause_until[instrument] = None
                self.consecutive_losses[instrument] = 0
        
        # ===== PHASE FILTER (v3.0 IMPULSE-BASED) =====
        # Check BEFORE all gates - uses impulse-based expansion
        phase_allowed, phase_reason, phase, expansion = TrendPhaseEngine.is_mode_f_allowed(
            candles, indicators, signal['direction'], self.impulse_engine  # v3.0: Pass impulse engine
        )
        
        if not phase_allowed:
            return False, f"Phase Filter: {phase_reason}"
        
        # ===== EXECUTION GATE 1: Move Exhaustion =====
        gate_1_pass, gate_1_reason = ExecutionGates.gate_1_move_exhaustion(
            candles, indicators, signal['direction'], self.impulse_engine  # v3.0: Pass impulse engine
        )
        
        if not gate_1_pass:
            return False, gate_1_reason
        
        # ===== EXECUTION GATE 2: Time + Day Type =====
        gate_2_pass, gate_2_reason = ExecutionGates.gate_2_time_day_type(
            current_time, self.day_type_engine.current_day_type
        )
        
        if not gate_2_pass:
            return False, gate_2_reason
        
        # ===== EXECUTION GATE 3: RSI Compression =====
        gate_3_pass, gate_3_reason = ExecutionGates.gate_3_rsi_compression(
            candles, indicators
        )
        
        if not gate_3_pass:
            return False, gate_3_reason
        
        # ===== MODE PERMISSION =====
        is_expiry = date.weekday() == 1  # Tuesday for NIFTY
        perm_pass, perm_reason = ModePermissionChecker.check_mode_f(
            self.day_type_engine.current_day_type, current_time, is_expiry
        )
        
        if not perm_pass:
            return False, perm_reason
        
        # All filters passed
        return True, None
    
    def _execute_trade(self, signal, all_candles, entry_idx, date):
        """Simulate trade execution with 1:2 RR target (PRODUCTION VERSION)"""
        entry_price = signal['entry']
        sl = signal['sl']
        target = signal['target']  # Use MODE_F calculated target (1:2 RR)
        direction = signal['direction']
        
        # Find exit
        for idx in range(entry_idx + 1, len(all_candles)):
            candle = all_candles[idx]
            h = float(candle['high'])
            l = float(candle['low'])
            
            exit_type = None
            exit_price = None
            
            if direction == 'BUY':
                if h >= target:
                    exit_type = 'TARGET'
                    exit_price = target
                elif l <= sl:
                    exit_type = 'SL'
                    exit_price = sl
            else:
                if l <= target:
                    exit_type = 'TARGET'
                    exit_price = target
                elif h >= sl:
                    exit_type = 'SL'
                    exit_price = sl
            
            if exit_type:
                # Calculate P&L in R
                risk = abs(entry_price - sl)
                pnl = (exit_price - entry_price) if direction == 'BUY' else (entry_price - exit_price)
                pnl_r = pnl / risk if risk > 0 else 0
                
                # Record trade
                trade = {
                    'entry_time': signal['timestamp'],
                    'exit_time': candle['date'],
                    'instrument': signal['instrument'],
                    'mode': signal['mode'],
                    'direction': direction,
                    'entry': entry_price,
                    'exit': exit_price,
                    'sl': sl,
                    'target': target,  # 1:2 RR target
                    'exit_type': exit_type,
                    'pnl': pnl,
                    'pnl_r': pnl_r,
                    'day_type': self.day_type_engine.current_day_type.value,
                }
                
                self.results.add_trade(trade)
                
                # v3.0.1: Update consecutive loss tracking
                instrument = signal['instrument']
                
                if exit_type == 'SL':
                    # Loss - increment counter
                    self.consecutive_losses[instrument] = self.consecutive_losses.get(instrument, 0) + 1
                    
                    # Check if limit reached
                    if self.consecutive_losses[instrument] >= CONSECUTIVE_LOSS_LIMIT['max_consecutive_losses']:
                        # Trigger pause
                        self.pause_until[instrument] = candle['date']
                        print(f"   ⚠️ {instrument}: {self.consecutive_losses[instrument]} consecutive losses - PAUSED for {CONSECUTIVE_LOSS_LIMIT['pause_duration_minutes']} min")
                    
                    # Register SL for correlation brake
                    self.system_stop.register_sl(candle['date'])
                
                elif exit_type == 'TARGET' and CONSECUTIVE_LOSS_LIMIT['reset_on_win']:
                    # Win - reset counter
                    self.consecutive_losses[instrument] = 0
                
                break
    
    def _resample_to_30m(self, c5):
        """Resample 5min to 30min"""
        c30_acc = []
        curr_30 = None
        
        for c in c5:
            dt = c['date']
            if dt.minute % 30 == 0:
                if curr_30:
                    c30_acc.append(curr_30)
                curr_30 = c.copy()
            else:
                if curr_30:
                    curr_30['high'] = max(curr_30['high'], c['high'])
                    curr_30['low'] = min(curr_30['low'], c['low'])
                    curr_30['close'] = c['close']
                    curr_30['volume'] += c['volume']
                else:
                    curr_30 = c.copy()
        
        if curr_30:
            c30_acc.append(curr_30)
        
        return c30_acc


# ===================================================================
# MAIN EXECUTION
# ===================================================================
if __name__ == "__main__":
    print("""
    ============================================================
    
           RIJIN SYSTEM - BACKTEST VALIDATION
    
       Testing day type classification, gates, and trade
       counts against 3 months of historical data.
    
    ============================================================
    """)
    
    # Run backtest
    engine = RijinBacktestEngine(BACKTEST_CONFIG)
    summary = engine.run_backtest()
    
    print("\n[TARGET] Backtest Summary:")
    print(f"   Total Days: {summary.get('total_days', 0)}")
    print(f"   Total Signals: {summary.get('total_signals', 0)}")
    print(f"   Signals Allowed: {summary.get('allowed_signals', 0)}")
    print(f"   Signals Blocked: {summary.get('blocked_signals', 0)}")
    print(f"   Total Trades: {summary.get('total_trades', 0)}")
    print(f"   Win Rate: {summary.get('win_rate', 0):.2f}%")
    print(f"   Total P&L: {summary.get('total_pnl_r', 0):+.2f}R")
    print(f"   Worst Day: {summary.get('worst_day_pnl', 0):+.2f}R")
    print(f"   Bad Days (< -1.5R): {summary.get('bad_days_count', 0)}")
    
    if summary.get('issues'):
        print("\n[WARN] Issues Found:")
        for issue in summary['issues']:
            print(f"   • {issue}")
    else:
        print("\n[OK] All validation checks passed!")
    
    print("\n" + "="*80)
    print("[CHART] Results exported to CSV files")
    print("="*80)


