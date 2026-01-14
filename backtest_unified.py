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
CAPITAL = 100000.0
RISK_PER_TRADE_PCT = 0.02 # 2% per trade
START_DATE = datetime.now() - timedelta(days=365)
END_DATE = datetime.now()

# Instruments to Test
# Using SPOT INDICES for 1-Year Backtest (Futures contract history is too short)
# Global Config
START_DATE = datetime.now() - timedelta(days=365) # 1 Year Backtest

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
    print(f"🚀 STARTING BACKTEST (Capital: ₹{CAPITAL:,.0f})")
    print(f"📅 Period: {START_DATE.date()} to {END_DATE.date()}\n")
    
    all_trades = []
    
    # Mode F Wrapper
    class ModeFWrapper:
        def __init__(self):
            from mode_f_engine import ModeFEngine
            self.engine = ModeFEngine()
            
        def update_trend_30m(self, c30):
             return "MODE_F_TREND", 0
             
        def analyze_5m(self, c5, t_state, slope, name, global_bias="NEUTRAL"):
            res = self.engine.predict(c5, global_bias=global_bias)
            if res.valid:
                return {
                    "direction": res.direction,
                    "mode": "MODE_F",
                    "entry": res.entry,
                    "sl": res.sl,
                    "target": res.target,
                    "pattern": f"{res.struct_state.name} | {res.vol_state.name}"
                }
            return None

    # Full System Backtest Configuration
    INSTRUMENTS = [
        {"name": "NIFTY_UNIFIED", "symbol": "NSE:NIFTY 50", "strat_cls": NiftyStrategy},
        {"name": "GOLD_GUINEA", "symbol": "MCX:GOLDGUINEA26MARFUT", "strat_cls": GoldStrategy},
        {"name": "NIFTY_MODE_F",  "symbol": "NSE:NIFTY 50", "strat_cls": ModeFWrapper}
    ]

    for inst in INSTRUMENTS:
        name = inst['name']
        symbol = inst['symbol']
        strat = inst['strat_cls']()
        
        print(f"🔄 Processing {name} ({symbol})...")
        
        # 1. Get Token
        try:
            q = kite.quote(symbol)
            token = q[symbol]['instrument_token']
        except:
            print(f"   ⚠️ Could not fetch token for {symbol}. Skipping.")
            continue
            
        # 2. Fetch Data
        # We need 30m for Trend, 5m for Entry
        # Fetching 5m data is enough? No, we need 30m candle logic.
        # We can resample 5m to 30m or fetch separate 30m. 
        # Strategy expects "c30" (list of dicts).
        # To be precise, we should fetch 5minute data and *construct* 30m candles on the fly 
        # to prevent look-ahead bias, or fetch both and align timestamps.
        # Simplest consistent way: Fetch 5min, resample to 30min.
        
        print("   ⏳ Fetching historical data...")
        df_5m = fetch_data(token, START_DATE, END_DATE, "5minute")
        if df_5m.empty:
            print("   ⚠️ No data found.")
            continue
        print(f"   ✅ Fetched {len(df_5m)} candles.")
            
        df_5m['date'] = pd.to_datetime(df_5m['date'])
        df_5m.set_index('date', inplace=True)
        
        # Resample to 30m for Trend
        df_30m = df_5m.resample('30min').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
        
        # Convert to list of dicts for Strategy
        def to_dicts(df):
            return [{'date': i, 'open': r.open, 'high': r.high, 'low': r.low, 'close': r.close} for i, r in df.iterrows()]
            
        candles_5m = to_dicts(df_5m)
        
        # 3. Simulation Loop
        # We simulate candle by candle.
        # Optimization: We check 30m trend only when a new 30m candle closes.
        
        # Mapping 5m buffer
        buffer_5m = [] # Rolling buffer
        
        active_trade = None
        
        # Pre-calculate 30m trends? 
        # Better: iterate through 5m candles.
        # If timestamp aligns with 30m close, update strat trend.
        
        for i, c in enumerate(candles_5m):
            if i < 60: continue # Warmup
            
            curr_time = c['date']
            
            # Update Strategy State
            # Provide last 30 5m candles
            c5r = candles_5m[i-50:i+1] # Pass last 50 candles
            
            # Find relevant 30m data (all 30m candles completed BEFORE current time)
            # Efficient way: df_30m[df_30m.index < curr_time] 
            # Note: Strategy.update_trend_30m expects a list of candles
            
            # Performance Optimization: Only update 30m trend if we just crossed a 30m boundary?
            # UnifiedEngine creates c30 every 5 seconds.
            # Strategy.analyze_5m takes "c30_trend, c30_slope".
            
            # Let's get the latest 30m candle closed before current time
            past_30m = df_30m[df_30m.index < curr_time]
            if len(past_30m) < 55: continue
            
            c30_input = to_dicts(past_30m.tail(60)) # Pass last 60
            
            # Handle different return signatures
            if isinstance(strat, GoldStrategy):
                trend_state = strat.update_trend_30m(c30_input)
                slope_val = 0 # Gold doesn't return slope here
            else:
                trend_state, slope_val = strat.update_trend_30m(c30_input)
            
            # Check Active Trade Exit
            if active_trade:
                # Check High/Low of current candle vs SL/Target
                # Logic: SL Hit? Target Hit?
                # Assume intra-candle hit: Worst case SL first if both listed? 
                # Or just standard: Low < SL -> Exit.
                
                # Check SL
                sl_hit = False
                tgt_hit = False
                exit_price = 0.0
                exit_reason = ""
                
                if active_trade['direction'] == "BUY":
                    if c['low'] <= active_trade['sl']:
                        sl_hit = True
                        exit_price = active_trade['sl'] # slippage ignored
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
                
                # Close Trade
                if sl_hit or tgt_hit:
                    pnl = 0.0
                    r_acquired = 0.0
                    
                    if active_trade['direction'] == "BUY":
                        pnl = (exit_price - active_trade['entry']) * active_trade['qty']
                    else:
                        pnl = (active_trade['entry'] - exit_price) * active_trade['qty']
                    
                    # Store Result
                    trade_res = {
                        "instrument": name,
                        "date": curr_time, # Exit Time
                        "entry_time": active_trade['entry_time'], # Added for Portfolio Sim
                        "mode": active_trade['mode'],
                        "direction": active_trade['direction'],
                        "entry": active_trade['entry'],
                        "exit": exit_price,
                        "sl": active_trade['sl'], # Added for Risk Calc
                        "pnl": pnl,
                        "reason": exit_reason
                    }
                    all_trades.append(trade_res)
                    
                    # NOTIFY EXIT
                    # msg_exit = f"🧪 <b>BACKTEST EXIT [{name}]</b>\n" \
                    #            f"Result: {exit_reason} (PnL: {pnl:.2f})\n" \
                    #            f"Exit Price: {exit_price}\n" \
                    #            f"Time: {curr_time}"
                    # try:
                    #     send_telegram_message(msg_exit)
                    #     time.sleep(0.5)
                    # except: pass
                    
                    active_trade = None # Reset
                    
            # Check New Entry (If no active trade)
            if not active_trade:
                # Run Strategy
                # Note: GoldStrategy signature is update_trend_30m -> return trend only (no slope?)
                # Check Unified code... GoldStrategy.update_trend_30m returns "new_trend".
                # Nifty/BankNifty return "new_trend, slope".
                # Wrapper needed.
                
                t_state = trend_state
                s_val = 0
                if isinstance(trend_state, tuple):
                    t_state = trend_state[0]
                    s_val = trend_state[1]
                
                # Pass instrument name
                sig = strat.analyze_5m(c5r, t_state, s_val, name)
                
                if sig and sig['direction'] in ["BUY", "SELL"]:
                    # Create Trade
                    # Calculate Qty based on Risk
                    entry = sig['entry']
                    sl = sig['sl']
                    risk = abs(entry - sl)
                    if risk > 0:
                        risk_amount = CAPITAL * RISK_PER_TRADE_PCT
                        qty = int(risk_amount / risk)
                        if qty < 1: qty = 1 # Min 1
                        
                        active_trade = {
                            "direction": sig['direction'],
                            "mode": sig['mode'],
                            "entry": entry,
                            "sl": sl,
                            "target": sig['target'],
                            "qty": qty,
                            "entry_time": curr_time
                        }
                        
                        # NOTIFY ENTRY
                        # msg = f"🧪 <b>BACKTEST ENTRY [{name}]</b>\n" \
                        #       f"Direction: {sig['direction']}\n" \
                        #       f"Mode: {sig['mode']}\n" \
                        #       f"Entry: {entry}\nSL: {sl}\nTarget: {sig['target']}\n" \
                        #       f"Time: {curr_time}"
                        # try:
                        #     # send_telegram_message(msg) 
                        #     # To prevent blocking and 429s, we might want to just print or use a rate-limited sender.
                        #     # User requested ACTUAL notifications.
                        #     # send_telegram_message(msg)
                        #     # time.sleep(0.5) # Rate limit
                        #     pass
                        # except Exception as e: print(f"TG Error: {e}")
                        
    # ----------------------------------------------
    # Generate Report
    # ----------------------------------------------
    print("\n✅ BACKTEST COMPLETE. Generating Report...\n")
    
    if not all_trades:
        print("No trades generated.")
        return

    df_res = pd.DataFrame(all_trades)
    df_res.to_csv(f"backtest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", index=False)
    print(f"📄 Report saved to CSV.")
    df_res['month'] = df_res['date'].dt.to_period('M')
    
    # 1. Month-by-Month
    print("📅 MONTHLY BREAKDOWN")
    monthly = df_res.groupby(['month', 'instrument']).agg(
        trades=('pnl', 'count'),
        pnl=('pnl', 'sum'),
        wins=('pnl', lambda x: (x > 0).sum())
    )
    monthly['win_rate'] = (monthly['wins'] / monthly['trades'] * 100).round(1)
    pd.set_option('display.max_rows', None)
    print(monthly)
    print("\n" + "="*50 + "\n")
    
    # 2. Instrument-wise
    print("📊 INSTRUMENT PERFORMANCE")
    instr_grp = df_res.groupby('instrument').agg(
        total_trades=('pnl', 'count'),
        net_profit=('pnl', 'sum'),
        avg_trade=('pnl', 'mean'),
        max_profit=('pnl', 'max'),
        max_loss=('pnl', 'min')
    )
    print(instr_grp)
    print("\n" + "="*50 + "\n")
    
    # 3. Mode Breakdown
    print("🎯 STRATEGY MODE STATS")
    mode_grp = df_res.groupby('mode').agg(
        trades=('pnl', 'count'),
        net_pnl=('pnl', 'sum'),
        win_rate=('pnl', lambda x: ((x > 0).sum() / x.count() * 100))
    )
    print(mode_grp)
    
    # 4. Total
    total_pnl = df_res['pnl'].sum()
    final_cap = CAPITAL + total_pnl
    ret_pct = (total_pnl / CAPITAL) * 100
    
    print("\n💰 FINAL SUMMARY")
    print(f"Starting Capital: ₹{CAPITAL:,.2f}")
    print(f"Ending Capital:   ₹{final_cap:,.2f}")
    print(f"Total Net PnL:    ₹{total_pnl:,.2f} ({ret_pct:.1f}%)")
    print(f"Total Trades:     {len(df_res)}")

if __name__ == "__main__":
    run_backtest()
