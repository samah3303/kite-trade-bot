"""
RUN MODE F — PRODUCTION PREDICTOR
Manual Trigger for Nifty Mode F Logic.

Usage:
    python run_mode_f.py

Behavior:
    1. Connects to Kite Connect.
    2. Fetches Global Market Data.
    3. Fetches recent Nifty 5m Data.
    4. Runs Mode F strict analysis.
    5. Outputs Decision (BUY / SELL / CALL NOT VALID).
"""

import os
import sys
import time
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Import Mode F Engine
from mode_f_engine import ModeFEngine, VolatilityState, StructuralState, DominanceState

# Import Global Analyzer
try:
    from global_market_analyzer import GlobalMarketAnalyzer, GlobalBias
except ImportError:
    print("⚠️ Global Market Analyzer not found.")
    sys.exit(1)

# Load Env
load_dotenv()
API_KEY = os.getenv("KITE_API_KEY")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")
NIFTY_INSTRUMENT = os.getenv("NIFTY_INSTRUMENT", "NSE:NIFTY 50") # Default to Spot 

def get_kite_session():
    if not API_KEY or not ACCESS_TOKEN:
        print("❌ CRITICAL: Credentials missing in .env")
        sys.exit(1)
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)
    return kite

def fetch_nifty_data(kite, instrument_token):
    # Fetch last 5-7 days of 5minute data to ensure enough history for 30m structure calculation
    to_date = datetime.now()
    from_date = to_date - timedelta(days=7) 
    
    interval = "5minute"
    try:
        data = kite.historical_data(instrument_token, from_date, to_date, interval)
        return data
    except Exception as e:
        print(f"❌ Error fetching Nifty data: {e}")
        return []

def print_report(response, global_bias, symbol):
    print("\n" + "="*60)
    print(f"🔒 MODE F — PRODUCTION CALL | {symbol}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    print(f"\n🌍 GLOBAL CONTEXT")
    print(f"   Bias: {global_bias} (Risk State)")
    
    print(f"\n📊 MARKET STATE")
    print(f"   Volatility: {response.vol_state.name} {'(⚠️ RESTRICTED)' if response.vol_state.name == 'EXTREME' else ''}")
    print(f"   Structure:  {response.struct_state.name}")
    
    print("\n" + "-"*60)
    if response.valid:
        print(f"📢 DECISION:  {response.direction} {symbol}")
        print("-" * 60)
        print(f"   Entry:      {response.entry}")
        print(f"   Stoploss:   {response.sl}")
        print(f"   Target:     {response.target}")
        print(f"   Reason:     {response.narrative}")
    else:
        print(f"🚫 DECISION:  CALL NOT VALID")
        print("-" * 60)
        print(f"   Reason:     {response.reason}")
    print("="*60 + "\n")

def main():
    print("🚀 INIT MODE F PREDICTOR...")
    
    # 1. Connect
    kite = get_kite_session()
    print("✅ Kite Connected")
    
    # 2. Global Analysis
    print("🌍 Analyzing Global Markets...")
    gmam = GlobalMarketAnalyzer()
    gmam.fetch_global_data()
    gmam.calculate_bias()
    global_bias_str = gmam.bias.value # RISK_ON / RISK_OFF / NEUTRAL
    print(f"   Result: {global_bias_str}")
    
    # 3. Nifty Data
    print(f"📈 Fetching Nifty Data ({NIFTY_INSTRUMENT})...")
    try:
        q = kite.quote(NIFTY_INSTRUMENT)
        token = q[NIFTY_INSTRUMENT]['instrument_token']
        candles = fetch_nifty_data(kite, token)
        
        if len(candles) < 50:
            print("❌ Insufficient Nifty data fetched < 50 candles.")
            return
            
        print(f"   ✅ Fetched {len(candles)} candles.")
        
        # 4. Mode F Prediction
        engine = ModeFEngine()
        print("🧠 Running Mode F Logic Engine...")
        
        # Pass data to engine
        start_t = time.time()
        response = engine.predict(candles, global_bias=global_bias_str)
        end_t = time.time()
        print(f"   Analysis complete in {(end_t-start_t)*1000:.2f}ms")
        
        # 5. Output
        print_report(response, global_bias_str, NIFTY_INSTRUMENT)
        
    except Exception as e:
        print(f"❌ Execution Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
