import os
import time
import json
import logging
import argparse
from datetime import datetime, timedelta
# No pandas import
from kiteconnect import KiteConnect
from dotenv import load_dotenv
from unified_engine import NiftyStrategy, GoldStrategy, TrendState, LegState

# Load Env
load_dotenv()
API_KEY = os.getenv("KITE_API_KEY")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")
NIFTY_INSTRUMENT = "NSE:NIFTY 50"
GOLD_INSTRUMENT = "MCX:GOLDGUINEA26MARFUT"

def fetch_historical_data(kite, token, days=30):
    print(f"Fetching {days} days of data for token {token}...")
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)
    
    try:
        data = kite.historical_data(token, from_date, to_date, interval="5minute")
        print(f"Fetched {len(data)} candles.")
        return data
    except Exception as e:
        print(f"Error fetching data: {e}")
        return []

def run_backtest_strategy(strategy, data, instrument_name):
    print(f"\n--- Backtesting {instrument_name} ---")
    trades = []
    
    c30_acc = []
    curr_30 = None
    
    active_trade = None 
    
    # Lot Size
    lot_size = 25 if "NIFTY" in instrument_name else 1
    if "GOLD" in instrument_name: lot_size = 1 # Gold Guinea=1
    
    for i in range(len(data)):
        c = data[i]
        c_time = c['date']
        
        # 30m Construction
        dt = c['date']
        if dt.minute % 30 == 0:
             if curr_30: c30_acc.append(curr_30)
             curr_30 = c.copy()
        else:
            if curr_30:
                curr_30['high'] = max(curr_30['high'], c['high'])
                curr_30['low'] = min(curr_30['low'], c['low'])
                curr_30['close'] = c['close']
                curr_30['volume'] += c['volume']
            else: curr_30 = c.copy()
            
        if len(c30_acc) < 55: continue 
        
        c5_subset = data[:i+1] 
        
        # ------------------------
        # NIFTY LOGIC
        # ------------------------
        if isinstance(strategy, NiftyStrategy):
            if active_trade:
                res_exit = None
                points = 0
                if active_trade['direction'] == "BUY":
                    if c['low'] <= active_trade['sl']: res_exit = "SL HIT"; points = active_trade['sl'] - active_trade['entry']
                    elif c['high'] >= float(active_trade['target_val']): res_exit = "TARGET HIT"; points = float(active_trade['target_val']) - active_trade['entry']
                elif active_trade['direction'] == "SELL":
                    if c['high'] >= active_trade['sl']: res_exit = "SL HIT"; points = active_trade['entry'] - active_trade['sl']
                    elif c['low'] <= float(active_trade['target_val']): res_exit = "TARGET HIT"; points = active_trade['entry'] - float(active_trade['target_val'])
                
                if res_exit:
                    pnl_amt = points * lot_size
                    trade_record = {
                        "Instrument": instrument_name,
                        "Entry Time": str(active_trade['time']),
                        "Exit Time": str(c_time),
                        "Signal": active_trade['direction'],
                        "Mode": active_trade['mode'],
                        "Entry": active_trade['entry'],
                        "Exit": active_trade['sl'] if "SL" in res_exit else active_trade['target_val'],
                        "Result": res_exit,
                        "Points": points,
                        "PnL": pnl_amt
                    }
                    trades.append(trade_record)
                    
                    risk = abs(active_trade['entry'] - active_trade['sl'])
                    r_mult = points / risk if risk > 0 else 0
                    strategy.daily_pnl_r += r_mult
                    if r_mult < 0 and active_trade['mode'] == "MODE_C": strategy.mode_c_losses += 1
                    
                    active_trade = None
                continue 
            
            trend, slope = strategy.update_trend_30m(c30_acc)
            res = strategy.analyze_5m(c5_subset, trend, slope, instrument_name)
            
            if res:
                t_val = res['target']
                if "TRAIL" in str(t_val):
                     # Fix numeric target for backtest
                     t_val = str(res['entry']*1.01)

                active_trade = {
                    "direction": res['direction'],
                    "mode": res['mode'],
                    "entry": res['entry'],
                    "sl": res['sl'],
                    "target_val": t_val,
                    "time": c_time
                }
                
                if "TRAIL" in str(res['target']):
                     # Default 1:2 Risk Reward handling for TRAIL placeholders
                    risk = abs(res['entry'] - res['sl'])
                    if res['direction'] == "BUY": active_trade['target_val'] = res['entry'] + (2*risk)
                    else: active_trade['target_val'] = res['entry'] - (2*risk)

        # ------------------------
        # GOLD LOGIC
        # ------------------------
        elif isinstance(strategy, GoldStrategy):
            trend = strategy.update_trend_30m(c30_acc)
            res = strategy.analyze_5m(c5_subset, trend, instrument_name, i)
            
            if res and res['direction'] == "EXIT":
                points = 0
                # Primitive Gold PnL approximation
                if res['exit_type'] == "TARGET HIT": points = 150 # Approx 150 INR profit per trade per lot
                elif res['exit_type'] == "SL HIT": points = -150
                
                trade_record = {
                    "Instrument": instrument_name,
                    "Entry Time": "N/A",
                    "Exit Time": str(c_time),
                    "Signal": res.get('mode', 'Unk'),
                    "Result": res['exit_type'],
                    "Points": points,
                    "PnL": points * lot_size
                }
                trades.append(trade_record)
                
    return trades

def print_trades_table(trades):
    if not trades:
        print("No trades generated.")
        return

    # Columns
    headers = ["Instrument", "Signal", "Result", "PnL"]
    col_width = 20
    
    # Print Header
    header_str = "".join(h.ljust(col_width) for h in headers)
    print("-" * len(header_str))
    print(header_str)
    print("-" * len(header_str))
    
    # Print Rows (Last 15)
    for t in trades[-15:]:
        row = [
            str(t.get("Instrument", ""))[:18],
            str(t.get("Signal", ""))[:18],
            str(t.get("Result", ""))[:18],
            f"{t.get('PnL', 0):.2f}"
        ]
        print("".join(c.ljust(col_width) for c in row))
    print("-" * len(header_str))


def main():
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)
    
    CAPITAL = 100000
    DAYS = 30 # Updated to 30 days
    
    print(f"--- STARTING SIMULATION: {DAYS} Days, INR {CAPITAL} Capital ---")
    
    # 1. Fetch Data
    tokens = kite.quote([NIFTY_INSTRUMENT, GOLD_INSTRUMENT])
    tok_nifty = tokens[NIFTY_INSTRUMENT]['instrument_token']
    tok_gold = tokens[GOLD_INSTRUMENT]['instrument_token']
    
    data_nifty = fetch_historical_data(kite, tok_nifty, days=DAYS)
    data_gold = fetch_historical_data(kite, tok_gold, days=DAYS)
    
    # 2. Run Backtests
    nifty_strat = NiftyStrategy()
    nifty_trades = run_backtest_strategy(nifty_strat, data_nifty, NIFTY_INSTRUMENT)
    
    gold_strat = GoldStrategy()
    gold_trades = run_backtest_strategy(gold_strat, data_gold, GOLD_INSTRUMENT)
    
    # 3. Process
    all_trades = nifty_trades + gold_trades
    
    total_pnl = sum(t['PnL'] for t in all_trades)
    final_cap = CAPITAL + total_pnl
    roi = (total_pnl / CAPITAL) * 100
    
    print("\n=== BACKTEST REPORT ===")
    print(f"Start Capital: INR {CAPITAL}")
    print(f"End Capital:   INR {final_cap:.2f}")
    print(f"Net PnL:       INR {total_pnl:.2f} ({roi:.2f}%)")
    print(f"Total Trades:  {len(all_trades)}")
    print(f"(NIFTY: {len(nifty_trades)}, GOLD: {len(gold_trades)})")
    
    print("\n--- Recent Trades Log ---")
    print_trades_table(all_trades)

if __name__ == "__main__":
    main()
