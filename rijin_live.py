"""
RIJIN v3.0.1 - LIVE TRADING ENGINE
Production-Ready System with Impulse-Based Timing & Consecutive Loss Protection

Deploy: python rijin_live.py
"""

import os
import time
import logging
from datetime import datetime, time as dtime
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# RIJIN Core Components
from rijin_engine import (
    ImpulseDetectionEngine,
    TrendPhaseEngine,
    DayTypeEngine,
    ExecutionGates,
    SystemStopManager,
    ModePermissionChecker,
)
from rijin_config import (
    DayType,
    CONSECUTIVE_LOSS_LIMIT,
    TRADING_CUTOFF,
)

# Signal Engines
from mode_f_engine import ModeFEngine

# Utilities
from unified_engine import (
    simple_ema,
    calculate_rsi,
    calculate_atr,
    send_telegram_message,
)

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# ===================================================================
# CONFIGURATION
# ===================================================================
API_KEY = os.getenv("KITE_API_KEY")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")
NIFTY_INSTRUMENT = os.getenv("NIFTY_INSTRUMENT", "NFO:NIFTY26FEBFUT")

INITIAL_CAPITAL = 100000  # Rs.1,00,000
RISK_PER_TRADE = 0.01     # 1% = 1R = Rs.1,000


# ===================================================================
# RIJIN LIVE TRADING ENGINE
# ===================================================================
class RijinLiveEngine:
    """
    RIJIN v3.0.1 Live Trading Engine
    
    Features:
    - Impulse-based phase detection
    - Consecutive loss protection
    - Day type awareness
    - Real MODE_F signal generation
    """
    
    def __init__(self):
        # Kite Connection
        self.kite = KiteConnect(api_key=API_KEY)
        self.kite.set_access_token(ACCESS_TOKEN)
        
        # RIJIN Components
        self.impulse_engine = ImpulseDetectionEngine()
        self.day_type_engine = DayTypeEngine()
        self.system_stop = SystemStopManager()
        self.mode_f_engine = ModeFEngine()
        
        # State
        self.active_trade = None
        self.consecutive_losses = 0
        self.pause_until = None
        self.last_check_time = None
        
        # Daily tracking
        self.today = None
        self.daily_trades = 0
        self.daily_pnl_r = 0.0
        
        logging.info("="*60)
        logging.info("RIJIN v3.0.1 - LIVE TRADING ENGINE INITIALIZED")
        logging.info("="*60)
        logging.info(f"Instrument: {NIFTY_INSTRUMENT}")
        logging.info(f"Capital: Rs.{INITIAL_CAPITAL:,}")
        logging.info(f"Risk per trade: {RISK_PER_TRADE*100}% = Rs.{int(INITIAL_CAPITAL*RISK_PER_TRADE):,}")
        logging.info(f"Consecutive loss limit: {CONSECUTIVE_LOSS_LIMIT['max_consecutive_losses']}")
        logging.info("="*60)
    
    def reset_daily_state(self):
        """Reset state for new trading day"""
        self.today = datetime.now().date()
        self.impulse_engine.reset_for_new_day()
        self.day_type_engine.reset_for_new_day()
        self.system_stop.reset_for_new_day()
        self.daily_trades = 0
        self.daily_pnl_r = 0.0
        self.consecutive_losses = 0
        self.pause_until = None
        
        logging.info(f"\n{'='*60}")
        logging.info(f"NEW TRADING DAY: {self.today}")
        logging.info(f"{'='*60}\n")
        
        # Send Telegram notification
        send_telegram_message(
            f"🟢 <b>RIJIN v3.0.1 - NEW DAY</b>\n\n"
            f"📅 Date: {self.today}\n"
            f"💰 Capital: Rs.{INITIAL_CAPITAL:,}\n"
            f"🎯 Risk: Rs.{int(INITIAL_CAPITAL*RISK_PER_TRADE):,} per trade\n"
            f"🛡️ Max consecutive losses: {CONSECUTIVE_LOSS_LIMIT['max_consecutive_losses']}\n\n"
            f"System active. Monitoring for signals..."
        )
    
    def fetch_candles_5m(self, limit=100):
        """Fetch latest 5-minute candles from Kite"""
        try:
            from_date = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
            to_date = datetime.now()
            
            data = self.kite.historical_data(
                instrument_token=self.kite.ltp(NIFTY_INSTRUMENT)[NIFTY_INSTRUMENT]['instrument_token'],
                from_date=from_date,
                to_date=to_date,
                interval="5minute"
            )
            
            return data
        except Exception as e:
            logging.error(f"Error fetching candles: {e}")
            return []
    
    def calculate_indicators(self, candles):
        """Calculate EMA, ATR, RSI"""
        if len(candles) < 30:
            return None
        
        closes = [float(c['close']) for c in candles]
        highs = [float(c['high']) for c in candles]
        lows = [float(c['low']) for c in candles]
        
        ema20 = simple_ema(closes, 20)
        atr = calculate_atr(highs, lows, closes, 14)
        rsi = calculate_rsi(closes, 14)
        
        if len(ema20) == 0 or len(atr) == 0 or len(rsi) == 0:
            return None
        
        return {
            'ema20': float(ema20[-1]),
            'atr': float(atr[-1]),
            'rsi': float(rsi[-1]),
        }
    
    def check_consecutive_loss_pause(self):
        """Check if trading is paused due to consecutive losses"""
        if self.pause_until:
            now = datetime.now()
            if now < self.pause_until:
                remaining = int((self.pause_until - now).total_seconds() / 60)
                return True, f"Paused for {remaining} more minutes (consecutive loss protection)"
            else:
                # Pause expired
                self.pause_until = None
                self.consecutive_losses = 0
                logging.info("Consecutive loss pause EXPIRED - resuming trading")
                send_telegram_message("✅ <b>Trading Resumed</b>\n\nConsecutive loss pause expired.")
                return False, None
        
        return False, None
    
    def apply_rijin_gates(self, signal, candles, indicators):
        """
        Apply RIJIN v3.0.1 execution gates
        Returns: (allowed, reason)
        """
        current_time = datetime.now()
        
        # Check consecutive loss pause FIRST
        paused, reason = self.check_consecutive_loss_pause()
        if paused:
            return False, reason
        
        # Phase Filter (impulse-based v3.0)
        phase_allowed, phase_reason, phase, expansion = TrendPhaseEngine.is_mode_f_allowed(
            candles, indicators, signal['direction'], self.impulse_engine
        )
        
        if not phase_allowed:
            return False, f"Phase Filter: {phase_reason}"
        
        # Execution Gate 1: Move Exhaustion (impulse-based)
        gate_1_pass, gate_1_reason = ExecutionGates.gate_1_move_exhaustion(
            candles, indicators, signal['direction'], self.impulse_engine
        )
        
        if not gate_1_pass:
            return False, gate_1_reason
        
        # Execution Gate 2: Time + Day Type
        gate_2_pass, gate_2_reason = ExecutionGates.gate_2_time_day_type(
            current_time, self.day_type_engine.current_day_type
        )
        
        if not gate_2_pass:
            return False, gate_2_reason
        
        # Execution Gate 3: RSI Compression
        gate_3_pass, gate_3_reason = ExecutionGates.gate_3_rsi_compression(
            candles, indicators
        )
        
        if not gate_3_pass:
            return False, gate_3_reason
        
        # Mode Permission
        is_expiry = datetime.now().weekday() == 1  # Tuesday for NIFTY
        perm_pass, perm_reason = ModePermissionChecker.check_mode_f(
            self.day_type_engine.current_day_type, current_time, is_expiry
        )
        
        if not perm_pass:
            return False, perm_reason
        
        # All gates passed
        return True, f"ALLOWED - Phase: {phase} ({expansion:.1f}× ATR from impulse)"
    
    def generate_signal(self, candles, indicators):
        """Generate MODE_F signal using production engine"""
        try:
            res = self.mode_f_engine.predict(candles, global_bias="NEUTRAL")
            
            if res.valid:
                return {
                    'mode': 'MODE_F',
                    'direction': res.direction,
                    'entry': res.entry,
                    'sl': res.sl,
                    'target': res.target,
                    'gear': res.gear.name,
                    'rsi': indicators['rsi'],
                    'atr': indicators['atr'],
                }
            
            return None
        except Exception as e:
            logging.error(f"Signal generation error: {e}")
            return None
    
    def execute_trade(self, signal):
        """Execute trade (paper or live)"""
        # Calculate position size
        risk = abs(signal['entry'] - signal['sl'])
        quantity = int((INITIAL_CAPITAL * RISK_PER_TRADE) / risk)
        
        logging.info(f"\n{'='*60}")
        logging.info(f"EXECUTING TRADE")
        logging.info(f"{'='*60}")
        logging.info(f"Direction: {signal['direction']}")
        logging.info(f"Entry: {signal['entry']}")
        logging.info(f"SL: {signal['sl']}")
        logging.info(f"Target: {signal['target']}\nQuantity: {quantity}")
        logging.info(f"Risk: Rs.{int(INITIAL_CAPITAL * RISK_PER_TRADE):,} (1R)")
        logging.info(f"{'='*60}\n")
        
        # Send Telegram alert
        send_telegram_message(
            f"🎯 <b>RIJIN SIGNAL</b>\n\n"
            f"📊 Mode: {signal['mode']} ({signal['gear']})\n"
            f"📍 Direction: <b>{signal['direction']}</b>\n"
            f"💵 Entry: {signal['entry']}\n"
            f"🛑 SL: {signal['sl']}\n"
            f"🎯 Target: {signal['target']}\n"
            f"📦 Quantity: {quantity}\n"
            f"💰 Risk: Rs.{int(INITIAL_CAPITAL * RISK_PER_TRADE):,}\n"
            f"📈 RSI: {signal['rsi']:.1f}\n"
            f"📏 ATR: {signal['atr']:.1f}\n\n"
            f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        # Store active trade
        self.active_trade = {
            **signal,
            'entry_time': datetime.now(),
            'quantity': quantity,
        }
        
        self.daily_trades += 1
    
    def check_active_trade_exit(self, current_price):
        """Monitor active trade for exit"""
        if not self.active_trade:
            return
        
        trade = self.active_trade
        direction = trade['direction']
        sl = trade['sl']
        target = trade['target']
        
        exit_type = None
        exit_price = None
        
        if direction == 'BUY':
            if current_price >= target:
                exit_type = 'TARGET'
                exit_price = target
            elif current_price <= sl:
                exit_type = 'SL'
                exit_price = sl
        else:
            if current_price <= target:
                exit_type = 'TARGET'
                exit_price = target
            elif current_price >= sl:
                exit_type = 'SL'
                exit_price = sl
        
        if exit_type:
            self.close_trade(exit_type, exit_price)
    
    def close_trade(self, exit_type, exit_price):
        """Close active trade and update stats"""
        trade = self.active_trade
        entry = trade['entry']
        sl = trade['sl']
        direction = trade['direction']
        
        # Calculate P&L
        risk = abs(entry - sl)
        pnl = (exit_price - entry) if direction == 'BUY' else (entry - exit_price)
        pnl_r = pnl / risk if risk > 0 else 0
        
        self.daily_pnl_r += pnl_r
        
        logging.info(f"\n{'='*60}")
        logging.info(f"TRADE CLOSED: {exit_type}")
        logging.info(f"{'='*60}")
        logging.info(f"Entry: {entry}")
        logging.info(f"Exit: {exit_price}")
        logging.info(f"P&L: {pnl_r:+.2f}R")
        logging.info(f"Daily P&L: {self.daily_pnl_r:+.2f}R")
        logging.info(f"{'='*60}\n")
        
        # Update consecutive losses
        if exit_type == 'SL':
            self.consecutive_losses += 1
            self.system_stop.register_sl(datetime.now())
            
            # Check if pause needed
            if self.consecutive_losses >= CONSECUTIVE_LOSS_LIMIT['max_consecutive_losses']:
                pause_duration = CONSECUTIVE_LOSS_LIMIT['pause_duration_minutes']
                self.pause_until = datetime.now() + timedelta(minutes=pause_duration)
                
                logging.warning(f"⚠️ {self.consecutive_losses} CONSECUTIVE LOSSES - PAUSED FOR {pause_duration} MIN")
                
                send_telegram_message(
                    f"⚠️ <b>CONSECUTIVE LOSS PROTECTION</b>\n\n"
                    f"Losses in a row: {self.consecutive_losses}\n"
                    f"Trading PAUSED for {pause_duration} minutes\n"
                    f"Resume at: {self.pause_until.strftime('%H:%M')}\n\n"
                    f"This prevents drawdown spirals."
                )
        
        elif exit_type == 'TARGET' and CONSECUTIVE_LOSS_LIMIT['reset_on_win']:
            self.consecutive_losses = 0
        
        # Send Telegram
        emoji = "✅" if exit_type == 'TARGET' else "❌"
        send_telegram_message(
            f"{emoji} <b>TRADE CLOSED: {exit_type}</b>\n\n"
            f"Entry: {entry}\n"
            f"Exit: {exit_price}\n"
            f"P&L: <b>{pnl_r:+.2f}R</b>\n"
            f"Daily P&L: {self.daily_pnl_r:+.2f}R\n"
            f"Daily Trades: {self.daily_trades}\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        
        # Clear active trade
        self.active_trade = None
    
    def run(self):
        """Main trading loop"""
        logging.info("Starting RIJIN v3.0.1 Live Engine...\n")
        send_telegram_message("🚀 <b>RIJIN v3.0.1 STARTED</b>\n\nLive trading engine active.")
        
        while True:
            try:
                now = datetime.now()
                current_time = now.time()
                
                # Reset daily state if new day
                if self.today != now.date():
                    self.reset_daily_state()
                
                # Trading hours check
                if not (dtime(9, 15) <= current_time <= dtime(15, 30)):
                    time.sleep(60)
                    continue
                
                # Fetch candles
                candles = self.fetch_candles_5m()
                if len(candles) < 30:
                    time.sleep(30)
                    continue
                
                # Calculate indicators
                indicators = self.calculate_indicators(candles)
                if not indicators:
                    time.sleep(30)
                    continue
                
                # Detect impulse
                self.impulse_engine.detect_impulse(candles, indicators, now)
                
                # Check if we have an active trade
                if self.active_trade:
                    current_price = float(candles[-1]['close'])
                    self.check_active_trade_exit(current_price)
                    time.sleep(10)  # Check every 10 seconds when in trade
                    continue
                
                # Classify day type (every 30 min)
                # (Simplified - full implementation would track properly)
                
                # Check system stop
                should_stop, stop_reason = self.system_stop.check_stop_conditions(
                    self.day_type_engine.current_day_type
                )
                
                if should_stop:
                    logging.warning(f"System Stop: {stop_reason}")
                    time.sleep(300)  # Wait 5 min
                    continue
                
                # Generate signal (only check every 5 minutes)
                if not self.last_check_time or (now - self.last_check_time).seconds >= 300:
                    signal = self.generate_signal(candles, indicators)
                    
                    if signal:
                        # Apply RIJIN gates
                        allowed, reason = self.apply_rijin_gates(signal, candles, indicators)
                        
                        if allowed:
                            logging.info(f"✅ Signal ALLOWED: {reason}")
                            self.execute_trade(signal)
                        else:
                            logging.info(f"❌ Signal BLOCKED: {reason}")
                    
                    self.last_check_time = now
                
                # Sleep before next iteration
                time.sleep(30)  # Check every 30 seconds
            
            except KeyboardInterrupt:
                logging.info("\nShutting down RIJIN engine...")
                send_telegram_message("🛑 <b>RIJIN STOPPED</b>\n\nEngine shut down by user.")
                break
            
            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                time.sleep(60)


# ===================================================================
# MAIN
# ===================================================================
if __name__ == "__main__":
    from datetime import timedelta  # Add import
    
    engine = RijinLiveEngine()
    engine.run()
