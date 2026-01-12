
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import os
import sys

# Import Engine Components
sys.path.insert(0, os.path.dirname(__file__))
from unified_engine import NiftyStrategy, TrendState, GlobalBias

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
INITIAL_CAPITAL = 100000.0
RISK_PER_TRADE_PCT = 0.02  # 2% Risk per trade
DATA_FILE = "nifty50_3months_data.csv" # Contains 1 year data actually

# -----------------------------------------------------------------------------
# Helper: Global Data Simulator
# -----------------------------------------------------------------------------
class GlobalContextSimulator:
    def __init__(self, start_date, end_date):
        self.bias_map = {} # date_str -> bias_value
        self.fetch_data(start_date, end_date)
        
    def fetch_data(self, start, end):
        print(f"🌍 Fetching Global Data (VIX, S&P 500) for context: {start.date()} - {end.date()}")
        try:
            # Fetch India VIX and S&P 500
            vix = yf.download("^INDIAVIX", start=start, end=end, progress=False)
            spx = yf.download("^GSPC", start=start, end=end, progress=False)
            
            # Simple Logic Simulation:
            # RISK_ON: VIX < 18 or Decreasing, SPX > SMA20
            # RISK_OFF: VIX > 20 or Spiking, SPX < SMA20
            
            # Resample to daily
            if not vix.empty and not spx.empty:
                # Calculate indicators
                spx['SMA20'] = spx['Close'].rolling(20).mean()
                
                # Align indices
                common_dates = vix.index.intersection(spx.index)
                
                for date in common_dates:
                    d_str = str(date.date())
                    
                    v_val = vix.loc[date]['Close']
                    # Handle multi-level column if yfinance returns dataframe
                    if isinstance(v_val, pd.Series): v_val = v_val.iloc[0]
                    
                    s_val = spx.loc[date]['Close']
                    if isinstance(s_val, pd.Series): s_val = s_val.iloc[0]
                    
                    s_sma = spx.loc[date]['SMA20']
                    if isinstance(s_sma, pd.Series): s_sma = s_sma.iloc[0]
                    
                    # Logic
                    score = 0
                    if v_val < 15: score += 1
                    if v_val > 22: score -= 1
                    
                    if s_val > s_sma: score += 1
                    else: score -= 1
                    
                    bias = "NEUTRAL"
                    if score >= 1: bias = "RISK_ON"
                    elif score <= -1: bias = "RISK_OFF"
                    
                    self.bias_map[d_str] = bias
                    
            print(f"✅ Global Context Loaded ({len(self.bias_map)} days)")
            
        except Exception as e:
            print(f"⚠️ Global Data Fetch Warning: {e}")
            
    def get_bias(self, date_obj):
        return self.bias_map.get(str(date_obj.date()), "NEUTRAL")

# -----------------------------------------------------------------------------
# Backtester
# -----------------------------------------------------------------------------
class SystemBacktester:
    def __init__(self):
        self.capital = INITIAL_CAPITAL
        self.equity_curve = []
        self.trades = []
        self.strat = NiftyStrategy()
        
    def run(self):
        print(f"🚀 STARTING FULL SYSTEM BACKTEST (Starting Equity: ₹{self.capital:,.2f})")
        print(f"📊 Dynamic Position Sizing: {RISK_PER_TRADE_PCT*100}% Risk per trade")
        
        # 1. Load Nifty Data
        if not os.path.exists(DATA_FILE):
             print(f"❌ Data file {DATA_FILE} not found.")
             return
             
        df = pd.read_csv(DATA_FILE)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        print(f"✅ Loaded {len(df)} Nifty 5-min candles")
        
        # 2. Setup Global Context
        start_date = df.index[0]
        end_date = df.index[-1]
        gmam = GlobalContextSimulator(start_date, end_date)
        
        # 3. Resample 30m for Trend
        df_30m = df.resample('30min').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
        
        # Convert to list structures
        candles_5m = [{'date': i, 'open': r.open, 'high': r.high, 'low': r.low, 'close': r.close} for i, r in df.iterrows()]
        candles_30m = [{'date': i, 'open': r.open, 'high': r.high, 'low': r.low, 'close': r.close} for i, r in df_30m.iterrows()]
        
        active_trade = None
        
        # Metrics
        max_capital = self.capital
        max_drawdown = 0.0
        
        print("\n⏳ Simulating...")
        
        # Simulation Loop
        for i, c in enumerate(candles_5m):
            if i < 100: continue
            
            curr_time = c['date']
            curr_price = c['close']
            
            # --- GLOBAL BIAS ---
            global_bias = gmam.get_bias(curr_time)
            
            # --- 30M TREND ---
            # Get closed 30m candles before this time
            c30_subset = [x for x in candles_30m if x['date'] < curr_time]
            if len(c30_subset) < 60: continue
            
            trend_state, slope = self.strat.update_trend_30m(c30_subset[-60:])
            
            # Add day type classification logic 
            # (Need to inject Todays candles to Strat?)
            day_candles = [x for x in candles_5m[max(0, i-75):i+1] if x['date'].date() == curr_time.date()]
            if day_candles:
                 self.strat.day_type = self.strat.classify_day_type(c30_subset, day_candles)
            
            # --- EXECUTION STATE ---
            if active_trade:
                # Check for Exit
                res = self.check_exit(active_trade, c)
                if res:
                    # Close Trade
                    pnl = res['pnl']
                    self.capital += pnl
                    self.trades.append(res)
                    active_trade = None
                    
                    # Update High Watermark
                    max_capital = max(max_capital, self.capital)
                    drawdown = (max_capital - self.capital) / max_capital * 100
                    max_drawdown = max(max_drawdown, drawdown)
                    
            else:
                # Check for Entry
                # Prepare c5 history (last 50)
                c5_hist = candles_5m[i-50:i+1]
                
                signal = self.strat.analyze_5m(c5_hist, trend_state, slope, "NIFTY", global_bias)
                
                if signal:
                    # POSITION SIZING
                    entry = signal['entry']
                    sl = signal['sl']
                    risk_per_share = abs(entry - sl)
                    
                    if risk_per_share > 0:
                        risk_capital = self.capital * RISK_PER_TRADE_PCT
                        qty = int(risk_capital / risk_per_share)
                        qty = max(1, qty) # Min 1
                        
                        # Margin Check (Indices require margin, but assuming pure PnL simulation here)
                        # or assuming Futures logic (Lot size = 1 for simulation granularity)
                        
                        active_trade = {
                            "entry": entry,
                            "sl": sl,
                            "target": float(signal['target']),
                            "direction": signal['direction'],
                            "mode": signal['mode'],
                            "qty": qty,
                            "entry_time": curr_time
                        }
        
        self.generate_report(max_drawdown)

    def check_exit(self, trade, c):
        # OHLC check
        sl_hit = False
        tgt_hit = False
        price = 0
        
        if trade['direction'] == "BUY":
            if c['low'] <= trade['sl']:
                sl_hit = True; price = trade['sl']
            elif c['high'] >= trade['target']:
                tgt_hit = True; price = trade['target']
        else:
            if c['high'] >= trade['sl']:
                sl_hit = True; price = trade['sl']
            elif c['low'] <= trade['target']:
                tgt_hit = True; price = trade['target']
                
        if sl_hit or tgt_hit:
            pnl_per_share = (price - trade['entry']) if trade['direction'] == "BUY" else (trade['entry'] - price)
            total_pnl = pnl_per_share * trade['qty']
            return {
                "entry_time": trade['entry_time'],
                "exit_time": c['date'],
                "mode": trade['mode'],
                "pnl": total_pnl,
                "exit_type": "SL" if sl_hit else "TARGET",
                "capital_after": self.capital + total_pnl
            }
        
        # EOD Exit (15:25)
        if c['date'].time() >= datetime.strptime("15:25", "%H:%M").time():
             price = c['close']
             pnl_per_share = (price - trade['entry']) if trade['direction'] == "BUY" else (trade['entry'] - price)
             total_pnl = pnl_per_share * trade['qty']
             return {
                "entry_time": trade['entry_time'],
                "exit_time": c['date'],
                "mode": trade['mode'],
                "pnl": total_pnl,
                "exit_type": "EOD",
                "capital_after": self.capital + total_pnl
            }
            
        return None

    def generate_report(self, max_dd):
        print(f"\n📊 BACKTEST RESULTS (Last 1 Year)")
        print(f"=================================")
        print(f"Initial Capital:  ₹{INITIAL_CAPITAL:,.2f}")
        print(f"Final Capital:    ₹{self.capital:,.2f}")
        total_ret = ((self.capital - INITIAL_CAPITAL)/INITIAL_CAPITAL)*100
        print(f"Net Return:       {total_ret:.2f}%")
        print(f"Max Drawdown:     {max_dd:.2f}%")
        
        if not self.trades:
            print("No trades executed.")
            return

        df = pd.DataFrame(self.trades)
        total_trades = len(df)
        winners = df[df['pnl'] > 0]
        losers = df[df['pnl'] <= 0]
        
        win_rate = len(winners)/total_trades * 100
        
        print(f"Total Trades:     {total_trades}")
        print(f"Win Rate:         {win_rate:.2f}%")
        print(f"Avg Win:          ₹{winners['pnl'].mean():,.2f}")
        print(f"Avg Loss:         ₹{losers['pnl'].mean():,.2f}")
        
        print("\nStrategy Performance:")
        print(df.groupby('mode')['pnl'].agg(['count', 'sum', 'mean']))
        
        # Save
        df.to_csv("full_system_backtest_results.csv", index=False)
        print(f"\n📄 Validated output saved to full_system_backtest_results.csv")

if __name__ == "__main__":
    bt = SystemBacktester()
    bt.run()
