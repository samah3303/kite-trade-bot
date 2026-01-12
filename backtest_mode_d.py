"""
MODE D - Opening Drive Backtest Script
Tests the Opening Drive strategy on historical Nifty data

Strategy:
- Time Window: 09:20-10:30 IST
- Entry: Conservative pullback after strong opening (3 candles)
- Risk: Tight (1.0 ATR max), Target: 1.5R
- Max 1 trade per day
"""

import pandas as pd
import numpy as np
from datetime import datetime, time as dtime
import sys
import os

# Import functions from unified_engine
sys.path.insert(0, os.path.dirname(__file__))
from unified_engine import simple_ema, calculate_rsi, calculate_atr, get_slope


class ModeDBacktester:
    def __init__(self):
        self.trades = []
        self.mode_d_fired_days = set()
        
    def classify_day_type(self, df_day):
        """Simple CHOP detection"""
        if len(df_day) < 10:
            return "UNKNOWN"
        
        # Calculate ATR
        atr = calculate_atr(df_day['high'].values, df_day['low'].values, df_day['close'].values, 14)
        
        # Check if ATR is flat/falling
        if len(atr) >= 3:
            atr_falling = atr[-1] <= atr[-2] <= atr[-3]
        else:
            atr_falling = False
        
        # Check if range is small
        price_range = (df_day['high'].max() - df_day['low'].min()) / df_day['close'].iloc[0]
        small_range = price_range < 0.005  # < 0.5%
        
        # Check mixed candles
        first_6 = df_day.head(6)
        bullish = (first_6['close'] > first_6['open']).sum()
        bearish = (first_6['close'] < first_6['open']).sum()
        mixed = abs(bullish - bearish) <= 2
        
        if atr_falling and small_range and mixed:
            return "CHOP"
        elif not small_range and not atr_falling:
            return "TREND"
        else:
            return "RANGE"
    
    def check_mode_d_eligibility(self, df_day, global_bias="NEUTRAL"):
        """
        Check MODE D eligibility using first 3 candles (09:15-09:30)
        """
        if len(df_day) < 4:
            return False, None, None, None
        
        first_3 = df_day.head(3)
        
        #Calculate ATR for the day
        atr = calculate_atr(df_day['high'].values, df_day['low'].values, df_day['close'].values, 14)
        if len(atr) == 0:
            return False, None, None, None
        ATR = atr[-1]
        
        # Condition 1: Day type not CHOP
        day_type = self.classify_day_type(df_day)
        if day_type == "CHOP":
            return False, None, None, None
        
        # Condition 2: Opening range ≥ 0.50 × ATR
        or_high = first_3['high'].max()
        or_low = first_3['low'].min()
        or_range = or_high - or_low
        
        if or_range < (0.50 * ATR):
            return False, None, None, None
        
        # Condition 3: ≥2 candles same direction
        bullish_count = (first_3['close'] > first_3['open']).sum()
        bearish_count = (first_3['close'] < first_3['open']).sum()
        
        if bullish_count >= 2:
            direction = "BUY"
        elif bearish_count >= 2:
            direction = "SELL"
        else:
            return False, None, None, None
        
        # Condition 4: Body ≥ 60%, Wicks ≤ 40%
        for idx, row in first_3.iterrows():
            candle_range = row['high'] - row['low']
            if candle_range > 0:
                body = abs(row['close'] - row['open'])
                body_pct = body / candle_range
                if body_pct < 0.60:
                    return False, None, None, None
        
        # Condition 5: EMA20 slope aligns (calculated on available data)
        closes = df_day['close'].values
        if len(closes) >= 20:
            ema20 = simple_ema(closes, 20)
            slope = get_slope(ema20)
            
            if direction == "BUY" and slope <= 0:
                return False, None, None, None
            if direction == "SELL" and slope >= 0:
                return False, None, None, None
        
        # Condition 6: RSI
        if len(closes) >= 15:
            rsi = calculate_rsi(closes, 14)
            RSI = rsi[-1]
            
            if direction == "SELL" and RSI > 45:
                return False, None, None, None
            if direction == "BUY" and RSI < 55:
                return False, None, None, None
        
        # All conditions passed!
        return True, direction, or_high, or_low
    
    def find_mode_d_entry(self, df_day, direction, or_high, or_low):
        """
        Find MODE D entry using Option B (Conservative Pullback)
        Time window: 09:20-10:30
        """
        #Filter candles in MODE D time window (after first 3 candles)
        if len(df_day) <= 3:
            return None
        
        mode_d_window = df_day.iloc[3:].copy()  # Skip first 3 candles
        
        closes = mode_d_window['close'].values
        if len(closes) < 20:
            return None
        
        ema20 = simple_ema(closes, 20)
        atr = calculate_atr(mode_d_window['high'].values, mode_d_window['low'].values, closes, 14)
        
        if len(atr) == 0:
            return None
        
        # Look for pullback and rejection
        for i in range(len(mode_d_window)):
            if i >= len(ema20):
                break
                
            row = mode_d_window.iloc[i]
            P = row['close']
            O = row['open']
            H = row['high']
            L = row['low']
            E20 = ema20[i]
            ATR = atr[min(i, len(atr)-1)]
            
            entry_found = False
            
            if direction == "BUY":
                # Pullback: touched/went below EMA20
                # Rejection: closed back above with bullish candle
                pullback = L <= E20
                rejection = P > E20 and P > O
                
                if pullback and rejection:
                    entry_found = True
                    sl_or = or_low
                    sl_atr = P - (1.0 * ATR)
                    sl_val = max(sl_or, sl_atr)
                    tp_val = P + (1.5 * (P - sl_val))
                    
            elif direction == "SELL":
                pullback = H >= E20
                rejection = P < E20 and P < O
                
                if pullback and rejection:
                    entry_found = True
                    sl_or = or_high
                    sl_atr = P + (1.0 * ATR)
                    sl_val = min(sl_or, sl_atr)
                    tp_val = P - (1.5 * (sl_val - P))
            
            if entry_found:
                return {
                    'entry_time': row.name,
                    'entry_price': P,
                    'sl': sl_val,
                    'target': tp_val,
                    'direction': direction,
                    'atr': ATR
                }
        
        return None
    
    def simulate_trade(self, trade, df_remaining):
        """Simulate trade outcome"""
        if trade is None:
            return None
        
        entry = trade['entry_price']
        sl = trade['sl']
        target = trade['target']
        direction = trade['direction']
        
        for idx, row in df_remaining.iterrows():
            if direction == "BUY":
                if row['low'] <= sl:
                    return {**trade, 'exit_type': 'SL', 'exit_price': sl, 'exit_time': idx, 'pnl_r': -1.0}
                if row['high'] >= target:
                    return {**trade, 'exit_type': 'TARGET', 'exit_price': target, 'exit_time': idx, 'pnl_r': 1.5}
            else:  # SELL
                if row['high'] >= sl:
                    return {**trade, 'exit_type': 'SL', 'exit_price': sl, 'exit_time': idx, 'pnl_r': -1.0}
                if row['low'] <= target:
                    return {**trade, 'exit_type': 'TARGET', 'exit_price': target, 'exit_time': idx, 'pnl_r': 1.5}
        
        # End of day - close at market
        last_price = df_remaining.iloc[-1]['close']
        if direction == "BUY":
            pnl_r = (last_price - entry) / (entry - sl) if (entry - sl) > 0 else 0
        else:
            pnl_r = (entry - last_price) / (sl - entry) if (sl - entry) > 0 else 0
        
        return {**trade, 'exit_type': 'EOD', 'exit_price': last_price, 'exit_time': df_remaining.index[-1], 'pnl_r': pnl_r}
    
    def backtest(self, df):
        """Run backtest on DataFrame"""
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        
        # Group by day
        for date, df_day in df.groupby(df.index.date):
            # Convert date to string for set membership check
            date_key = str(date)
            
            if date_key in self.mode_d_fired_days:
                continue  # Max 1 trade per day
            
            # Check eligibility
            eligible, direction, or_high, or_low = self.check_mode_d_eligibility(df_day)
            
            if not eligible:
                continue
            
            # Find entry
            entry_signal = self.find_mode_d_entry(df_day, direction, or_high, or_low)
            
            if entry_signal is None:
                continue
            
            # Get remaining candles after entry
            entry_idx = df_day.index.get_loc(entry_signal['entry_time'])
            df_remaining = df_day.iloc[entry_idx+1:]
            
            # Simulate trade
            trade_result = self.simulate_trade(entry_signal, df_remaining)
            
            if trade_result:
                self.trades.append(trade_result)
                self.mode_d_fired_days.add(date_key)
                print(f"✅ MODE D {direction}: Entry={trade_result['entry_price']:.2f} | SL={trade_result['sl']:.2f} | Target={trade_result['target']:.2f} | Exit={trade_result['exit_type']} | PnL={trade_result['pnl_r']:.2f}R")
    
    def generate_report(self):
        """Generate backtest report"""
        if len(self.trades) == 0:
            print("\n❌ No MODE D trades found in backtest period")
            return
        
        df_trades = pd.DataFrame(self.trades)
        
        total_trades = len(df_trades)
        winners = (df_trades['pnl_r'] > 0).sum()
        losers = (df_trades['pnl_r'] <= 0).sum()
        win_rate = (winners / total_trades * 100) if total_trades > 0 else 0
        
        total_pnl_r = df_trades['pnl_r'].sum()
        avg_winner = df_trades[df_trades['pnl_r'] > 0]['pnl_r'].mean() if winners > 0 else 0
        avg_loser = df_trades[df_trades['pnl_r'] <= 0]['pnl_r'].mean() if losers > 0 else 0
        
        targets_hit = (df_trades['exit_type'] == 'TARGET').sum()
        sls_hit = (df_trades['exit_type'] == 'SL').sum()
        eod_exits = (df_trades['exit_type'] == 'EOD').sum()
        
        print(f"\n📊 MODE D BACKTEST RESULTS")
        print(f"=" * 60)
        print(f"Total Trades: {total_trades}")
        print(f"Winners: {winners} | Losers: {losers}")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Total PnL: {total_pnl_r:+.2f}R")
        print(f"Avg Winner: {avg_winner:+.2f}R | Avg Loser: {avg_loser:+.2f}R")
        print(f"\nExit Types: TARGET={targets_hit} | SL={sls_hit} | EOD={eod_exits}")
        print(f"=" * 60)
        
        # Save to CSV
        csv_filename = f"mode_d_backtest_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df_trades.to_csv(csv_filename, index=False)
        print(f"\n✅ Results saved to: {csv_filename}")


if __name__ == "__main__":
    print("🚀 MODE D - Opening Drive Backtest")
    print("=" * 60)
    
    # Load data
    data_file = "nifty50_3months_data.csv"
    if not os.path.exists(data_file):
        print(f"❌ Data file not found: {data_file}")
        print("Please run export_nifty_data.py first to generate historical data")
        sys.exit(1)
    
    print(f"Loading data from {data_file}...")
    df = pd.read_csv(data_file)
    print(f"✅ Loaded {len(df)} candles")
    
    # Run backtest
    backtester = ModeDBacktester()
    backtester.backtest(df)
    
    # Generate report
    backtester.generate_report()
