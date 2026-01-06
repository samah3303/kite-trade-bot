import os
import time
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Load Environment
load_dotenv()
api_key = os.getenv("KITE_API_KEY")
access_token = os.getenv("KITE_ACCESS_TOKEN")
nifty_symbol = os.getenv("NIFTY_INSTRUMENT", "NFO:NIFTY26JANFUT")

if not api_key or not access_token:
    print("❌ Critical: KITE_API_KEY or KITE_ACCESS_TOKEN missing in .env")
    exit()

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

def fetch_data(token, from_date, to_date, interval):
    """Fetch history with loop for limits"""
    try:
        data = []
        curr = from_date
        while curr < to_date:
            next_month = curr + timedelta(days=30)
            if next_month > to_date: next_month = to_date
            
            print(f"   ⏳ Fetching {curr.date()} to {next_month.date()}...")
            d = kite.historical_data(token, curr, next_month, interval)
            data.extend(d)
            
            curr = next_month
            time.sleep(0.5) # Rate limit
            
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Error fetching data: {e}")
        return pd.DataFrame()

def main():
    print("🚀 STARTING NIFTY 50 DATA EXPORT")
    
    # 1. Get Token
    try:
        q = kite.quote(nifty_symbol)
        token = q[nifty_symbol]['instrument_token']
        print(f"✅ Found Token for {nifty_symbol}: {token}")
    except Exception as e:
        print(f"❌ Failed to fetch token: {e}")
        return

    # 2. Fetch Data (Last 90 Days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    print(f"📅 Exporting Data from {start_date.date()} to {end_date.date()}")
    
    df = fetch_data(token, start_date, end_date, "5minute")
    
    if not df.empty:
        filename = "nifty50_3months_data.csv"
        df.to_csv(filename, index=False)
        print(f"✅ Data saved to {filename} ({len(df)} rows)")
    else:
        print("⚠️ No data fetched.")

if __name__ == "__main__":
    main()
