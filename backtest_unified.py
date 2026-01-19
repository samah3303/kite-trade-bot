import os
import time
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from kiteconnect import KiteConnect
from unified_engine import NiftyStrategy, BankNiftyStrategy, GoldStrategy, TrendState, LegState, simple_ema, calculate_atr, calculate_rsi, get_slope, send_telegram_message

# Load Environment
load_dotenv()
api_key = os.getenv("KITE_API_KEY")
access_token = os.getenv("KITE_ACCESS_TOKEN")

if not api_key or not access_token:
    print("❌ Critical: KITE_API_KEY or KITE_ACCESS_TOKEN missing in .env")
    exit()

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Configuration
CAPITAL = 1000000.0
RISK_PER_TRADE_PCT = 0.02 # 2% per trade
START_DATE = datetime(2026, 1, 1)
END_DATE = datetime(2026, 1, 20)

# Instruments to Test
# Using SPOT INDICES for 1-Year Backtest (Futures contract history is too short)
# Global Config
# START_DATE handled above

def fetch_data(token, from_date, to_date, interval):
    """Fetch history with loop for limits if needed"""
    try:
        # Kite allows ~30-60 days per call for minute data usually.
        # We will loop month by month.
        data = []
        curr = from_date
        while curr < to_date:
            next_month = curr + timedelta(days=30)
            if next_month > to_date: next_month = to_date
            
            # Fetch
            d = kite.historical_data(token, curr, next_month, interval)
            data.extend(d)
            
            curr = next_month
            time.sleep(0.2) # Rate limit nice
            
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Error fetching data for {token}: {e}")
        return pd.DataFrame()

def run_backtest():
    print(f"STARTING BACKTEST (Capital: Rs.{CAPITAL:,.0f})")
    print(f"Period: {START_DATE.date()} to {END_DATE.date()}\n")
    
    all_trades = []
    
    # Mode F Wrapper
    class ModeFWrapper:
        def __init__(self):
            from mode_f_engine import ModeFEngine
            self.engine = ModeFEngine()
            
        def update_trend_30m(self, c30):
             return "MODE_F", 0
             
        def analyze_5m(self, c5, t_state, slope, name, global_bias="NEUTRAL"):
            try:
                res = self.engine.predict(c5, global_bias=global_bias)
                if res.valid:
                    return {
                        "direction": res.direction,
                        "mode": "MODE_F",
                        "gear": res.gear.name,
                        "regime": res.regime.name,
                        "entry": res.entry,
                        "sl": res.sl,
                        "target": res.target,
                        "pattern": f"{res.gear.name} | {res.reason}"
                    }
            except: pass
            return None

    # Full System Backtest Configuration
    INSTRUMENTS = [
        {"name": "NIFTY_UNIFIED", "symbol": "NSE:NIFTY 50", "strat_cls": NiftyStrategy},
        {"name": "NIFTY_MODE_F_3GEAR",  "symbol": "NSE:NIFTY 50", "strat_cls": ModeFWrapper}
    ]

    for inst in INSTRUMENTS:
        name = inst['name']
        symbol = inst['symbol']
        strat = inst['strat_cls']()
        
        print(f"Processing {name} ({symbol})...")
        
        # 1. Get Token
        try:
            q = kite.quote(symbol)
            token = q[symbol]['instrument_token']
        except:
            print(f"   Could not fetch token for {symbol}. Skipping.")
            continue
            
        # 2. Fetch Data
        # We need 30m for Trend, 5m for Entry
        # Fetching 5m data is enough? No, we need 30m candle logic.
        # We can resample 5m to 30m or fetch separate 30m. 
        # Strategy expects "c30" (list of dicts).
        # To be precise, we should fetch 5minute data and *construct* 30m candles on the fly 
        # to prevent look-ahead bias, or fetch both and align timestamps.
        # Simplest consistent way: Fetch 5min, resample to 30min.
        
        print("   Fetching historical data...")
        df_5m = fetch_data(token, START_DATE, END_DATE, "5minute")
        if df_5m.empty:
            print("   No data found.")
            continue
        print(f"   Fetched {len(df_5m)} candles.")
            
        df_5m['date'] = pd.to_datetime(df_5m['date'])
        df_5m.set_index('date', inplace=True)
        # Resample block removed - using fetched data below
        
        # Reset index so 'date' is a column again for to_dicts
        df_5m.reset_index(inplace=True)
        
        # Convert to list of dicts for Strategy
        def to_dicts(df):
            return [{'date': r['date'] if 'date' in r else i, 'open': r.open, 'high': r.high, 'low': r.low, 'close': r.close} for i, r in df.iterrows()]
            
        candles_5m = to_dicts(df_5m)
        
        # Need 30m context for Unified
        df_30m = fetch_data(token, START_DATE, END_DATE, "30minute")
        if df_30m.empty:
            print("   30m data missing, checking Unified validity...")
            
        df_30m['date'] = pd.to_datetime(df_30m['date'])
        df_30m.set_index('date', inplace=True)
        
        # Resample to 30m for Trend
        # df_30m = df_5m.resample('30min').agg({
        #     'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        # }).dropna()
        
        # Simulation Loop
        active_trade = None
        trend_state = ("NEUTRAL", 0) # Format: (State, Slope) or just State
        
        for i, c in enumerate(candles_5m):
            if i < 60: continue # Warmup
            
            curr_time = c['date']
            
            # Update Strategy State
            c5r = candles_5m[i-50:i+1] 
            
            # Optimization: 30m Context
            if "MODE_F" not in name:
                past_30m = df_30m[df_30m.index < curr_time]
                if len(past_30m) < 55: continue
                c30_input = to_dicts(past_30m.tail(60))
                if isinstance(strat, GoldStrategy):
                    trend_state = strat.update_trend_30m(c30_input)
                    slope_val = 0
                else:
                    trend_state, slope_val = strat.update_trend_30m(c30_input)
            else:
                 trend_state = ("MODE_F", 0)
                 slope_val = 0

            # Check Active Trade Exit
            if active_trade:
                sl_hit = False
                tgt_hit = False
                exit_price = 0.0
                exit_reason = ""
                
                if active_trade['direction'] == "BUY":
                    if c['low'] <= active_trade['sl']:
                        sl_hit = True
                        exit_price = active_trade['sl']
                        exit_reason = "SL HIT"
                    elif c['high'] >= float(active_trade['target']):
                        tgt_hit = True
                        exit_price = float(active_trade['target'])
                        exit_reason = "TARGET HIT"
                        
                elif active_trade['direction'] == "SELL":
                    if c['high'] >= active_trade['sl']:
                        sl_hit = True
                        exit_price = active_trade['sl']
                        exit_reason = "SL HIT"
                    elif c['low'] <= float(active_trade['target']):
                        tgt_hit = True
                        exit_price = float(active_trade['target'])
                        exit_reason = "TARGET HIT"
                
                if sl_hit or tgt_hit:
                    pnl = 0.0
                    if active_trade['direction'] == "BUY":
                        pnl = (exit_price - active_trade['entry']) * active_trade['qty']
                    else:
                        pnl = (active_trade['entry'] - exit_price) * active_trade['qty']
                    
                    trade_res = {
                        "instrument": name,
                        "date": curr_time, # Exit Time
                        "entry_time": active_trade['entry_time'],
                        "mode": active_trade['mode'],
                        "gear": active_trade.get('gear', 'N/A'),
                        "direction": active_trade['direction'],
                        "entry": active_trade['entry'],
                        "exit": exit_price,
                        "sl": active_trade['sl'],
                        "pnl": pnl,
                        "reason": exit_reason
                    }
                    all_trades.append(trade_res)
                    active_trade = None
                    
            # Check New Entry
            if not active_trade:
                t_state = trend_state[0] if isinstance(trend_state, tuple) else trend_state
                s_val = slope_val if isinstance(trend_state, tuple) else 0
                
                sig = strat.analyze_5m(c5r, t_state, s_val, name)
                
                if sig and sig['direction'] in ["BUY", "SELL"]:
                    entry = sig['entry']
                    sl = sig['sl']
                    risk = abs(entry - sl)
                    if risk > 0:
                        risk_amount = CAPITAL * RISK_PER_TRADE_PCT
                        qty = int(risk_amount / risk)
                        if qty < 1: qty = 1
                        
                        active_trade = {
                            "direction": sig['direction'],
                            "mode": sig['mode'],
                            "gear": sig.get('gear', 'N/A'),
                            "regime": sig.get('regime', 'N/A'),
                            "entry": entry,
                            "sl": sl,
                            "target": sig['target'],
                            "qty": qty,
                            "entry_time": curr_time
                        }

    # ----------------------------------------------
    # REPORT GENERATION
    # ----------------------------------------------
    print("\nRAW SIGNAL GENERATION COMPLETE.")

    if not all_trades:
        print("No trades generated.")
        return

    # Convert to DataFrame
    df_res = pd.DataFrame(all_trades)
    df_res['entry_time'] = pd.to_datetime(df_res['entry_time'])
    df_res['date'] = pd.to_datetime(df_res['date']) # Exit time
    
    # ----------------------------------------------
    # DEFINE SIMULATION FUNCTION
    # ----------------------------------------------
    def run_simulation(trades_subset, title):
        if len(trades_subset) == 0:
            print(f"\n--- {title} ---")
            print("No trades found.")
            return None

        print(f"\n" + "="*50)
        print(f"SIMULATION: {title} (1 Trade at a Time)")
        print("="*50)
        
        curr_cap = CAPITAL
        sim_trades = []
        
        # Sort by Entry Time
        df_sim = trades_subset.sort_values(by='entry_time').copy()
        
        for idx, row in df_sim.iterrows():
            entry = row['entry']
            sl = row['sl']
            risk = abs(entry - sl)
            
            if risk <= 0: continue
            
            risk_amt = curr_cap * RISK_PER_TRADE_PCT
            new_qty = int(risk_amt / risk)
            if new_qty < 1: new_qty = 1
            
            if row['direction'] == "BUY":
                unit_pnl = row['exit'] - row['entry']
            else:
                unit_pnl = row['entry'] - row['exit']
                
            real_pnl = unit_pnl * new_qty
            curr_cap += real_pnl
            
            sim_trades.append({
                "entry": row['entry_time'],
                "exit": row['date'],
                "pnl": real_pnl,
                "cap": curr_cap,
                "mode": row['mode'],
                "gear": row.get('gear', 'N/A')
            })
            
        final_cap = curr_cap
        net_pnl = final_cap - CAPITAL
        ret = (net_pnl / CAPITAL) * 100
        
        print(f"Starting Capital: Rs.{CAPITAL:,.2f}")
        print(f"Ending Capital:   Rs.{final_cap:,.2f}")
        print(f"Net PnL:          Rs.{net_pnl:,.2f} ({ret:.1f}%)")
        print(f"Trades Taken:     {len(sim_trades)}")
        
        return pd.DataFrame(sim_trades)

    # ----------------------------------------------
    # RUN COMBINED SIMULATION (Start Fresh logic)
    # ----------------------------------------------
    
    # 1. Use All trades
    df_filtered = df_res.copy()
    
    print(f" - Total trades for simulation: {len(df_filtered)}")
    
    # 2. Run Combined Portfolio Simulation
    sim_df = run_simulation(df_filtered, "COMBINED PORTFOLIO (No Gear 2/3)")
    
    # 3. Detailed Reporting
    if sim_df is not None and not sim_df.empty:
        sim_df['month'] = sim_df['entry'].dt.to_period('M')

        # A. Month-by-Month
        print("\nMONTHLY PERFORMANCE (Dynamic)")
        monthly_sim = sim_df.groupby('month').agg(
            trades=('pnl', 'count'),
            wins=('pnl', lambda x: (x > 0).sum()),
            losses=('pnl', lambda x: (x <= 0).sum()),
            pnl=('pnl', 'sum')
        )
        monthly_sim['win_rate'] = (monthly_sim['wins'] / monthly_sim['trades'] * 100).round(1)
        print(monthly_sim)
        
        # B. Mode-by-Mode
        print("\nMODE PERFORMANCE (Dynamic)")
        mode_sim = sim_df.groupby('mode').agg(
            trades=('pnl', 'count'),
            wins=('pnl', lambda x: (x > 0).sum()),
            losses=('pnl', lambda x: (x <= 0).sum()),
            pnl=('pnl', 'sum')
        )
        mode_sim['win_rate'] = (mode_sim['wins'] / mode_sim['trades'] * 100).round(1)
        print(mode_sim)

        # C. Daily Breakdown
        print("\nDAILY PERFORMANCE (Dynamic)")
        sim_df['day'] = sim_df['entry'].dt.date
        daily_sim = sim_df.groupby('day').agg(
            trades=('pnl', 'count'),
            wins=('pnl', lambda x: (x > 0).sum()),
            losses=('pnl', lambda x: (x <= 0).sum()),
            pnl=('pnl', 'sum'),
            ending_cap=('cap', 'last')
        )
        daily_sim['win_rate'] = (daily_sim['wins'] / daily_sim['trades'] * 100).round(1)
        print(daily_sim)

    # Save Sim Report
    if sim_df is not None:
        sim_df.to_csv("portfolio_sim_results.csv", index=False)
    print("\nSimulation Complete.")

if __name__ == "__main__":
    run_backtest()
