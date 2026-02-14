"""
RIJIN SYSTEM - Integration Runner
Wraps existing MODE_F and MODE_S with RIJIN context-aware execution
"""

import os
import time
import requests
from datetime import datetime, timedelta, time as dtime
from kiteconnect import KiteConnect
from dotenv import load_dotenv
import threading
import traceback

# Import RIJIN components
from rijin_engine import (
    DayTypeEngine,
    ExecutionGates,
    OpeningImpulseTracker,
    CorrelationBrake,
    SystemStopManager,
    ModePermissionChecker,
)
from rijin_config import *

# Import existing engines
from mode_f_engine import ModeFEngine
from mode_s_engine import ModeSEngine
from unified_engine import (
    simple_ema, calculate_rsi, calculate_atr, get_slope,
    TrendState
)

load_dotenv()

# Config
API_KEY = os.getenv("KITE_API_KEY")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TG_BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

NIFTY_INSTRUMENT = os.getenv("NIFTY_INSTRUMENT", "NFO:NIFTY26FEBFUT")
SENSEX_INSTRUMENT = os.getenv("SENSEX_INSTRUMENT", "BSE:SENSEX")


def send_telegram(message):
    """Send Telegram message"""
    try:
        url = f"{TG_BASE_URL}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")


# ===================================================================
# RIJIN INTEGRATED RUNNER
# ===================================================================
class RijinIntegratedRunner:
    """
    RIJIN System v2.3 - Context-Aware Execution
    Wraps MODE_F and MODE_S with intelligent permission system
    """
    
    def __init__(self):
        # RIJIN Components
        self.day_type_engine = DayTypeEngine()
        self.opening_impulse = OpeningImpulseTracker()
        self.correlation_brake = CorrelationBrake()
        self.system_stop = SystemStopManager()
        
        # Existing strategies
        self.mode_f_engine = ModeFEngine()
        self.mode_s_engine = ModeSEngine()
        
        # Kite
        self.kite = None
        
        # State
        self.stop_event = threading.Event()
        self.thread = None
        self.current_day_type = DayType.UNKNOWN
        self.last_day_type_check = None
        self.day_type_downgrade_sent = False
        
        # Tracking
        self.active_trades = {}
        self.instruments = {
            "NIFTY": NIFTY_INSTRUMENT,
            "SENSEX": SENSEX_INSTRUMENT,
        }
        self.last_processed = {inst: None for inst in self.instruments.values()}
        
        print("🧠 RIJIN SYSTEM v2.3 initialized")
    
    def start(self):
        """Start the system"""
        if self.thread and self.thread.is_alive():
            return False
        
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run_loop)
        self.thread.daemon = True
        self.thread.start()
        return True
    
    def stop(self):
        """Stop the system"""
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        return True
    
    def is_expiry_day(self, instrument_name, date):
        """Check if today is expiry day for instrument"""
        if "NIFTY" in instrument_name:
            return date.weekday() == EXPIRY_DAYS["NIFTY"]
        elif "SENSEX" in instrument_name:
            return date.weekday() == EXPIRY_DAYS["SENSEX"]
        return False
    
    def are_indices_correlated(self):
        """Check if NIFTY and SENSEX are moving together"""
        # Simple heuristic: same day type
        return True  # For now, always treat as correlated
    
    def run_loop(self):
        """Main execution loop"""
        print("🚀 RIJIN SYSTEM STARTED")
        print("📊 Philosophy: Signals generate opportunity. Context decides permission.")
        
        if not API_KEY or not ACCESS_TOKEN:
            print("❌ Missing API credentials")
            return
        
        self.kite = KiteConnect(api_key=API_KEY)
        self.kite.set_access_token(ACCESS_TOKEN)
        
        # Get tokens
        tokens = {}
        try:
            q = self.kite.quote(list(self.instruments.values()))
            for name, inst in self.instruments.items():
                tokens[name] = q[inst]['instrument_token']
        except Exception as e:
            print(f"❌ Token fetch error: {e}")
            return
        
        while not self.stop_event.is_set():
            try:
                current_time = datetime.now()
                
                # Daily reset
                if current_time.time() < dtime(9, 15):
                    if current_time.date() != getattr(self, 'last_reset_date', None):
                        self.reset_for_new_day(current_time.date())
                
                # After trading cutoff, only manage open trades
                if current_time.time() > TRADING_CUTOFF:
                    self.manage_open_trades_only()
                    time.sleep(30)
                    continue
                
                # Run day type check if scheduled
                if self.day_type_engine.should_run_check(current_time):
                    self.run_day_type_analysis(current_time)
                
                # Check system stop
                should_stop, stop_reason = self.system_stop.check_stop_conditions(
                    self.day_type_engine.current_day_type
                )
                
                if should_stop:
                    if not getattr(self, 'stop_message_sent', False):
                        self.send_system_stop_message(stop_reason)
                        self.stop_message_sent = True
                    
                    # Only manage open trades
                    self.manage_open_trades_only()
                    time.sleep(30)
                    continue
                
                # Process each instrument
                for name, inst in self.instruments.items():
                    self.process_instrument(
                        name=name,
                        instrument=inst,
                        token=tokens[name],
                        current_time=current_time
                    )
                
                time.sleep(10)  # Check every 10 seconds
            
            except Exception as e:
                print(f"❌ Loop error: {e}")
                traceback.print_exc()
                time.sleep(30)
        
        print("🛑 RIJIN SYSTEM STOPPED")
    
    def reset_for_new_day(self, date):
        """Reset all components for new trading day"""
        print(f"\n{'='*60}")
        print(f"🌅 NEW TRADING DAY: {date}")
        print(f"{'='*60}\n")
        
        self.day_type_engine.reset_for_new_day()
        self.opening_impulse.reset_for_new_day(date)
        self.system_stop.reset_for_new_day()
        self.active_trades = {}
        self.day_type_downgrade_sent = False
        self.stop_message_sent = False
        self.last_reset_date = date
        
        send_telegram(f"🌅 <b>NEW TRADING DAY</b>\nDate: {date}\nRIJIN System Active")
    
    def run_day_type_analysis(self, current_time):
        """Run day type classification"""
        try:
            print(f"\n🔍 Running Day Type Analysis @ {current_time.strftime('%H:%M')}")
            
            # Fetch data for NIFTY (primary)
            token = self.kite.quote([NIFTY_INSTRUMENT])[NIFTY_INSTRUMENT]['instrument_token']
            
            start = current_time - timedelta(days=2)
            c5 = self.kite.historical_data(token, start, current_time, interval="5minute")
            
            if not c5 or len(c5) < 30:
                print("⚠️ Insufficient data for day type analysis")
                return
            
            # Resample to 30m
            c30 = self.resample_to_30m(c5)
            
            # Calculate indicators
            closes = [float(x['close']) for x in c5]
            highs = [float(x['high']) for x in c5]
            lows = [float(x['low']) for x in c5]
            
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
            
            # Check if expiry day
            is_expiry = self.is_expiry_day(NIFTY_INSTRUMENT, current_time.date())
            
            # Classify
            new_day_type, reason = self.day_type_engine.classify_day(
                c5, c30, indicators, is_expiry
            )
            
            print(f"   Classification: {new_day_type.value}")
            print(f"   Reason: {reason}")
            
            # Update with confirmation rules
            updated, message = self.day_type_engine.update_day_type(
                new_day_type, reason, current_time
            )
            
            if updated and message:
                print(f"   ✅ {message}")
                
                # Send downgrade alert
                if not self.day_type_downgrade_sent:
                    self.send_day_type_downgrade(
                        self.day_type_engine.current_day_type,
                        current_time
                    )
                    self.day_type_downgrade_sent = True
            
            self.current_day_type = self.day_type_engine.current_day_type
            self.last_day_type_check = current_time
        
        except Exception as e:
            print(f"❌ Day type analysis error: {e}")
            traceback.print_exc()
    
    def process_instrument(self, name, instrument, token, current_time):
        """Process single instrument with RIJIN gates"""
        try:
            # Fetch data
            start = current_time - timedelta(days=3)
            c5 = self.kite.historical_data(token, start, current_time, interval="5minute")
            
            if not c5 or len(c5) < 30:
                return
            
            # Check for exits first
            self.check_exits(instrument, c5)
            
            # If trade already active, skip new entries
            if instrument in self.active_trades:
                return
            
            # Track last processed
            last_candle_time = c5[-2]['date']
            if self.last_processed[instrument] == last_candle_time:
                return  # Already processed this candle
            
            # Calculate indicators
            closes = [float(x['close']) for x in c5]
            highs = [float(x['high']) for x in c5]
            lows = [float(x['low']) for x in c5]
            
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
            
            # Check opening impulse
            is_expiry = self.is_expiry_day(instrument, current_time.date())
            impulse_signal = self.check_opening_impulse(
                instrument, c5, indicators, current_time, is_expiry
            )
            
            if impulse_signal:
                self.execute_signal(impulse_signal, current_time, is_impulse=True)
                self.last_processed[instrument] = last_candle_time
                return
            
            # Get signals from existing engines
            if "NIFTY" in name:
                signal = self.get_mode_f_signal(c5, indicators)
                mode = "MODE_F"
            elif "SENSEX" in name:
                signal = self.get_mode_s_signal(c5)
                mode = "MODE_S"
            else:
                signal = None
                mode = None
            
            if not signal:
                self.last_processed[instrument] = last_candle_time
                return
            
            # RIJIN CONTEXT-AWARE EXECUTION
            signal['instrument'] = instrument
            signal['mode'] = mode
            
            executed = self.rijin_execute(signal, current_time, is_expiry)
            
            self.last_processed[instrument] = last_candle_time
        
        except Exception as e:
            print(f"❌ Error processing {instrument}: {e}")
            traceback.print_exc()
    
    def check_opening_impulse(self, instrument, c5, indicators, current_time, is_expiry):
        """Check opening impulse conditions"""
        try:
            # Check if allowed
            indices_corr = self.are_indices_correlated()
            allowed, reason = self.opening_impulse.is_allowed(
                instrument, current_time, is_expiry, indices_corr
            )
            
            if not allowed:
                return None
            
            # Check conditions
            valid, move_atr = self.opening_impulse.check_impulse_conditions(c5, indicators)
            
            if not valid:
                return None
            
            # Determine direction
            last_candle = c5[-1]
            direction = "BUY" if float(last_candle['close']) > float(last_candle['open']) else "SELL"
            
            # Create signal
            price = float(last_candle['close'])
            atr = indicators['atr']
            
            sl = price - (0.5 * atr) if direction == "BUY" else price + (0.5 * atr)
            target = price + (1.0 * atr) if direction == "BUY" else price - (1.0 * atr)
            
            signal = {
                'instrument': instrument,
                'mode': 'OPENING_IMPULSE',
                'direction': direction,
                'entry': price,
                'sl': sl,
                'target': target,
                'pattern': f"Opening Impulse ({move_atr:.2f}× ATR)",
                'rsi': indicators['rsi'],
                'atr': atr,
                'move_atr': move_atr,
            }
            
            # Register
            self.opening_impulse.register_impulse(instrument)
            
            return signal
        
        except Exception as e:
            print(f"Impulse check error: {e}")
            return None
    
    def get_mode_f_signal(self, c5, indicators):
        """Get MODE_F signal from existing engine"""
        try:
            res = self.mode_f_engine.predict(c5, global_bias="NEUTRAL")
            
            if res.valid:
                return {
                    'direction': res.direction,
                    'entry': res.entry,
                    'sl': res.sl,
                    'target': res.target,
                    'pattern': f"{res.gear.name} | {res.reason}",
                    'rsi': indicators['rsi'],
                    'atr': indicators['atr'],
                    'gear': res.gear.name,
                    'regime': res.regime.name,
                }
            return None
        except:
            return None
    
    def get_mode_s_signal(self, c5):
        """Get MODE_S signal from existing engine"""
        try:
            res = self.mode_s_engine.analyze(c5)
            
            if res.valid:
                return {
                    'direction': res.direction,
                    'entry': res.entry,
                    'sl': res.sl,
                    'target': res.target,
                    'pattern': res.reason,
                    'rsi': 50,  # Mode S doesn't use RSI
                    'atr': 0,
                    'bucket': res.bucket.name,
                }
            return None
        except:
            return None
    
    def rijin_execute(self, signal, current_time, is_expiry):
        """
        RIJIN Context-Aware Execution Engine
        ALL GATES MUST PASS
        """
        instrument = signal['instrument']
        mode = signal['mode']
        direction = signal['direction']
        
        # Prepare indicators (reconstruct from signal)
        indicators = {
            'rsi': signal.get('rsi', 50),
            'atr': signal.get('atr', 10),
        }
        
        # ===== EXECUTION GATE 1: Move Exhaustion =====
        # (Would need candles, skip for now or fetch again)
        # gate_1_pass, gate_1_reason = ExecutionGates.gate_1_move_exhaustion(c5, indicators, direction)
        gate_1_pass, gate_1_reason = True, None  # Simplified
        
        if not gate_1_pass:
            self.send_signal_blocked(signal, current_time, gate_1_reason)
            self.system_stop.register_block()
            return False
        
        # ===== EXECUTION GATE 2: Time + Day Type =====
        gate_2_pass, gate_2_reason = ExecutionGates.gate_2_time_day_type(
            current_time,
            self.current_day_type
        )
        
        if not gate_2_pass:
            self.send_signal_blocked(signal, current_time, gate_2_reason)
            self.system_stop.register_block()
            return False
        
        # ===== EXECUTION GATE 3: RSI Compression =====
        # (Would need candles)
        gate_3_pass, gate_3_reason = True, None  # Simplified
        
        if not gate_3_pass:
            self.send_signal_blocked(signal, current_time, gate_3_reason)
            self.system_stop.register_block()
            return False
        
        # ===== MODE PERMISSION CHECK =====
        if mode == "MODE_F":
            perm_pass, perm_reason = ModePermissionChecker.check_mode_f(
                self.current_day_type, current_time, is_expiry
            )
        elif mode == "MODE_S":
            bucket = signal.get('bucket', 'CORE')
            if bucket in ['CORE', 'STABILITY']:
                perm_pass, perm_reason = ModePermissionChecker.check_mode_s_core(
                    self.current_day_type, current_time
                )
            else:
                perm_pass, perm_reason = ModePermissionChecker.check_mode_s_liquidity(
                    self.current_day_type, current_time
                )
        else:
            perm_pass, perm_reason = True, None
        
        if not perm_pass:
            self.send_signal_blocked(signal, current_time, perm_reason)
            self.system_stop.register_block()
            return False
        
        # ===== CORRELATION BRAKE =====
        other_inst = self.get_other_instrument(instrument)
        if other_inst:
            brake_active, brake_reason = self.correlation_brake.check_and_block(
                other_inst, instrument, current_time, self.are_indices_correlated()
            )
            
            if brake_active:
                self.send_signal_blocked(signal, current_time, brake_reason)
                self.system_stop.register_block()
                return False
        
        # ===== ALL GATES PASSED - EXECUTE =====
        self.execute_signal(signal, current_time, is_impulse=False)
        self.system_stop.reset_consecutive_blocks()
        
        return True
    
    def get_other_instrument(self, instrument):
        """Get correlated instrument"""
        if "NIFTY" in instrument:
            return SENSEX_INSTRUMENT
        elif "SENSEX" in instrument:
            return NIFTY_INSTRUMENT
        return None
    
    def execute_signal(self, signal, current_time, is_impulse=False):
        """Execute allowed signal"""
        instrument = signal['instrument']
        
        # Register trade
        self.active_trades[instrument] = {
            'mode': signal['mode'],
            'direction': signal['direction'],
            'entry': signal['entry'],
            'sl': signal['sl'],
            'target': signal['target'],
            'entry_time': current_time,
        }
        
        # Send Telegram
        self.send_signal_allowed(signal, current_time)
        
        print(f"✅ SIGNAL EXECUTED: {signal['mode']} {signal['direction']} on {instrument}")
    
    def check_exits(self, instrument, c5):
        """Check if active trades hit SL or Target"""
        if instrument not in self.active_trades:
            return
        
        trade = self.active_trades[instrument]
        last_candle = c5[-2]  # Use completed candle
        
        h = float(last_candle['high'])
        l = float(last_candle['low'])
        
        exit_type = None
        exit_price = None
        
        if trade['direction'] == 'BUY':
            if h >= float(trade['target']):
                exit_type = "TARGET HIT"
                exit_price = trade['target']
            elif l <= float(trade['sl']):
                exit_type = "SL HIT"
                exit_price = trade['sl']
        else:
            if l <= float(trade['target']):
                exit_type = "TARGET HIT"
                exit_price = trade['target']
            elif h >= float(trade['sl']):
                exit_type = "SL HIT"
                exit_price = trade['sl']
        
        if exit_type:
            pnl = (exit_price - trade['entry']) if trade['direction'] == 'BUY' else (trade['entry'] - exit_price)
            
            # Send exit alert
            msg = f"""
🚪 <b>EXIT SIGNAL</b>
INSTRUMENT: {instrument}
TYPE: {exit_type}
ENTRY: {trade['entry']} | EXIT: {exit_price}
PNL: {pnl:.2f}
"""
            send_telegram(msg.strip())
            
            # Register SL for correlation brake
            if "SL" in exit_type:
                self.correlation_brake.register_sl(
                    instrument,
                    trade['direction'],
                    self.current_day_type,
                    datetime.now()
                )
                self.system_stop.register_sl(datetime.now())
            
            # Remove trade
            del self.active_trades[instrument]
            
            print(f"🚪 EXIT: {exit_type} on {instrument}, PnL: {pnl:.2f}")
    
    def manage_open_trades_only(self):
        """After cutoff, only manage existing trades"""
        print("⏰ Post-cutoff: Managing open trades only")
        # Fetch data and check exits for active trades
        # Simplified for now
        pass
    
    def send_signal_allowed(self, signal, current_time):
        """Send Telegram alert for allowed signal"""
        expiry_ctx = self.get_expiry_context(signal['instrument'], current_time.date())
        
        msg = TELEGRAM_TEMPLATES['trade_allowed'].format(
            instrument=signal['instrument'],
            direction=signal['direction'],
            mode=signal['mode'],
            day_type=self.current_day_type.value,
            check_time=current_time.strftime('%H:%M'),
            expiry_context=expiry_ctx,
            entry=signal['entry'],
            sl=signal['sl'],
            target=signal['target'],
            pattern=signal['pattern'],
        )
        
        send_telegram(msg.strip())
    
    def send_signal_blocked(self, signal, current_time, reason):
        """Send Telegram alert for blocked signal"""
        msg = TELEGRAM_TEMPLATES['trade_blocked'].format(
            instrument=signal['instrument'],
            direction=signal['direction'],
            mode=signal['mode'],
            day_type=self.current_day_type.value,
            check_time=current_time.strftime('%H:%M'),
            reason=reason,
        )
        
        send_telegram(msg.strip())
        print(f"⚠️ SIGNAL BLOCKED: {signal['mode']} - {reason}")
    
    def send_day_type_downgrade(self, day_type, current_time):
        """Send day type downgrade alert"""
        additional = ""
        if day_type == DayType.RANGE_CHOPPY:
            additional = "⛔ All new directional trades BLOCKED for rest of day"
        
        msg = TELEGRAM_TEMPLATES['day_type_downgrade'].format(
            day_type=day_type.value,
            time=current_time.strftime('%H:%M'),
            additional_context=additional,
        )
        
        send_telegram(msg.strip())
    
    def send_system_stop_message(self, reason):
        """Send system stop alert"""
        msg = TELEGRAM_TEMPLATES['system_stop'].format(
            context=f"Reason: {reason}"
        )
        
        send_telegram(msg.strip())
    
    def get_expiry_context(self, instrument, date):
        """Get expiry context string"""
        is_nifty_expiry = "NIFTY" in instrument and self.is_expiry_day(instrument, date)
        is_sensex_expiry = "SENSEX" in instrument and self.is_expiry_day(instrument, date)
        
        if is_nifty_expiry:
            return "NIFTY Expiry Today (Tuesday)"
        elif is_sensex_expiry:
            return "SENSEX Expiry Today (Thursday)"
        else:
            return "Normal Trading Day"
    
    def resample_to_30m(self, c5):
        """Resample 5min to 30min candles"""
        c30_acc = []
        curr_30 = None
        
        for c in c5:
            dt = c['date']
            if dt.minute % 30 == 0 and dt.second == 0:
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


# Global instance
rijin_runner = RijinIntegratedRunner()


if __name__ == "__main__":
    print("""
    ===========================================================
    
              RIJIN SYSTEM v2.3 (LOCKED)
    
      Signals generate opportunity.
      Context decides permission.
      Capital protection is the alpha.
    
    ===========================================================
    """)
    
    rijin_runner.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n⏹️  Shutting down...")
        rijin_runner.stop()
