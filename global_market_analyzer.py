"""
Global Market Analysis Module (GMAM)
Provides daily market context by analyzing global indices, volatility, and macro factors.
Runs at: Login, 12:30 IST, 12:45 IST
"""

import os
import pytz
from datetime import datetime, time
from enum import Enum

try:
    import yfinance as yf
except ImportError:
    print("⚠️ yfinance not installed. Global market analysis disabled.")
    yf = None


class GlobalBias(Enum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    NEUTRAL = "NEUTRAL"


class GlobalMarketAnalyzer:
    """
    Analyzes global market conditions to provide directional bias.
    """
    
    def __init__(self):
        self.bias = GlobalBias.NEUTRAL
        self.last_update = None
        self.score = 0
        self.factors = {}
        self.data = {}
        self.ist = pytz.timezone('Asia/Kolkata')
        
    def should_run_analysis(self, current_time=None):
        """
        Check if global analysis should run.
        Triggers: First call (login), 12:30 IST, 12:45 IST
        """
        if self.last_update is None:
            return True  # First run (login)
        
        if current_time is None:
            current_time = datetime.now(self.ist).time()
        
        # Check if it's 9:15, 12:30 or 12:45 IST
        trigger_times = [time(9, 15), time(12, 30), time(12, 45)]
        
        for trigger_time in trigger_times:
            # Allow 5-minute window for each trigger
            if (trigger_time <= current_time <= time(trigger_time.hour, trigger_time.minute + 5)):
                # Check if we haven't updated in the last 10 minutes
                if self.last_update:
                    now = datetime.now(self.ist)
                    delta = (now - self.last_update).total_seconds() / 60
                    if delta < 10:
                        return False  # Already updated recently
                return True
        
        return False
    
    def fetch_global_data(self):
        """
        Fetch global market data with graceful degradation.
        If any source fails, continue with available data.
        """
        if yf is None:
            print("⚠️ yfinance not available. Skipping global analysis.")
            return False
        
        symbols = {
            'sp500': '^GSPC',      # S&P 500
            'nasdaq': '^IXIC',     # Nasdaq
            'nikkei': '^N225',     # Nikkei
            'hangseng': '^HSI',    # Hang Seng
            'vix': '^VIX',         # VIX
            'dxy': 'DX-Y.NYB',     # Dollar Index
            'us10y': '^TNX',       # US 10Y Treasury Yield
            'crude': 'CL=F',       # Crude Oil
        }
        
        self.data = {}
        
        for name, symbol in symbols.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d")
                
                if len(hist) >= 2:
                    # Calculate EMA20 if enough data
                    closes = hist['Close'].values[-20:] if len(hist) >= 20 else hist['Close'].values
                    ema20 = self._simple_ema(closes, min(20, len(closes)))
                    
                    self.data[name] = {
                        'current': hist['Close'].iloc[-1],
                        'previous': hist['Close'].iloc[-2],
                        'ema20': ema20[-1] if len(ema20) > 0 else hist['Close'].iloc[-1],
                        'change_pct': ((hist['Close'].iloc[-1] / hist['Close'].iloc[-2]) - 1) * 100
                    }
                    print(f"✅ Fetched {name}: {self.data[name]['current']:.2f} ({self.data[name]['change_pct']:+.2f}%)")
            except Exception as e:
                print(f"⚠️ Failed to fetch {name}: {e}")
                continue
        
        # Fetch GIFT Nifty if available (placeholder - would need NSE API)
        try:
            # For now, skip GIFT Nifty or use a proxy
            pass
        except Exception as e:
            print(f"⚠️ Failed to fetch GIFT Nifty: {e}")
        
        self.last_update = datetime.now(self.ist)
        return len(self.data) > 0
    
    def _simple_ema(self, data, period):
        """Calculate EMA using simple exponential smoothing"""
        import numpy as np
        alpha = 2 / (period + 1)
        ema = [data[0]]
        for price in data[1:]:
            ema.append(alpha * price + (1 - alpha) * ema[-1])
        return np.array(ema)
    
    def calculate_bias(self):
        """
        Calculate global bias based on scoring rules.
        Each factor: +1 / 0 / -1
        Final: ≥+2 = RISK-ON, ≤-2 = RISK-OFF, else NEUTRAL
        """
        self.score = 0
        self.factors = {}
        
        if not self.data:
            print("⚠️ No global data available. Setting bias to NEUTRAL.")
            self.bias = GlobalBias.NEUTRAL
            return
        
        # Rule 1: US indices above/below EMA20
        if 'sp500' in self.data:
            if self.data['sp500']['current'] > self.data['sp500']['ema20']:
                self.score += 1
                self.factors['sp500'] = '+1 (Above EMA20)'
            else:
                self.score -= 1
                self.factors['sp500'] = '-1 (Below EMA20)'
        
        if 'nasdaq' in self.data:
            if self.data['nasdaq']['current'] > self.data['nasdaq']['ema20']:
                self.score += 1
                self.factors['nasdaq'] = '+1 (Above EMA20)'
            else:
                self.score -= 1
                self.factors['nasdaq'] = '-1 (Below EMA20)'
        
        # Rule 2: VIX rising > 5%
        if 'vix' in self.data:
            if self.data['vix']['change_pct'] > 5:
                self.score -= 1
                self.factors['vix'] = '-1 (Rising >5%)'
            elif self.data['vix']['change_pct'] < -5:
                self.score += 1
                self.factors['vix'] = '+1 (Falling >5%)'
            else:
                self.factors['vix'] = '0 (Stable)'
        
        # Rule 3: DXY rising strongly
        if 'dxy' in self.data:
            if self.data['dxy']['change_pct'] > 0.5:
                self.score -= 1
                self.factors['dxy'] = '-1 (Strong rise)'
            elif self.data['dxy']['change_pct'] < -0.5:
                self.score += 1
                self.factors['dxy'] = '+1 (Weak)'
            else:
                self.factors['dxy'] = '0 (Stable)'
        
        # Rule 4: US 10Y Yield rising
        if 'us10y' in self.data:
            if self.data['us10y']['change_pct'] > 2:
                self.score -= 1
                self.factors['us10y'] = '-1 (Rising)'
            elif self.data['us10y']['change_pct'] < -2:
                self.score += 1
                self.factors['us10y'] = '+1 (Falling)'
            else:
                self.factors['us10y'] = '0 (Stable)'
        
        # Rule 5: Asian markets sentiment
        asian_score = 0
        asian_count = 0
        for market in ['nikkei', 'hangseng']:
            if market in self.data:
                asian_count += 1
                if self.data[market]['change_pct'] > 0.5:
                    asian_score += 1
                elif self.data[market]['change_pct'] < -0.5:
                    asian_score -= 1
        
        if asian_count > 0:
            if asian_score > 0:
                self.score += 1
                self.factors['asia'] = '+1 (Positive)'
            elif asian_score < 0:
                self.score -= 1
                self.factors['asia'] = '-1 (Negative)'
            else:
                self.factors['asia'] = '0 (Mixed)'
        
        # Determine final bias
        if self.score >= 2:
            self.bias = GlobalBias.RISK_ON
        elif self.score <= -2:
            self.bias = GlobalBias.RISK_OFF
        else:
            self.bias = GlobalBias.NEUTRAL
        
        print(f"📊 Global Bias Score: {self.score} → {self.bias.value}")
    
    def format_telegram_alert(self):
        """
        Format global market context for Telegram notification.
        """
        # Status symbols
        def get_status(name):
            if name not in self.data:
                return "⚠️ N/A"
            pct = self.data[name]['change_pct']
            if pct > 0.3:
                return f"✅ +{pct:.2f}%"
            elif pct < -0.3:
                return f"🔴 {pct:.2f}%"
            else:
                return f"⚠️ {pct:+.2f}%"
        
        # Bias emoji
        bias_emoji = {
            GlobalBias.RISK_ON: "🟢",
            GlobalBias.RISK_OFF: "🔴",
            GlobalBias.NEUTRAL: "🟡"
        }
        
        message = f"""🌍 GLOBAL MARKET CONTEXT

<b>US Markets:</b>
• S&P 500: {get_status('sp500')}
• Nasdaq: {get_status('nasdaq')}

<b>Asia:</b>
• Nikkei: {get_status('nikkei')}
• Hang Seng: {get_status('hangseng')}

<b>Volatility & Macro:</b>
• VIX: {get_status('vix')}
• DXY: {get_status('dxy')}
• US 10Y: {get_status('us10y')}
• Crude: {get_status('crude')}

📊 <b>Score:</b> {self.score:+d}
<b>Global Bias:</b> {bias_emoji.get(self.bias, '⚪')} <b>{self.bias.value}</b>

<b>Impact:</b>
• MODE D: {'BUY preferred' if self.bias == GlobalBias.RISK_ON else 'SELL preferred' if self.bias == GlobalBias.RISK_OFF else 'Both directions allowed'}
• MODE C: {'BUY confidence ↑' if self.bias == GlobalBias.RISK_ON else 'SELL confidence ↑' if self.bias == GlobalBias.RISK_OFF else 'Neutral stance'}
"""
        return message
    
    def is_bias_opposing(self, trade_direction):
        """
        Check if global bias opposes the trade direction.
        Used for MODE D filtering.
        
        Args:
            trade_direction: "BUY" or "SELL"
        
        Returns:
            True if bias opposes direction, False otherwise
        """
        if self.bias == GlobalBias.NEUTRAL:
            return False  # Neutral doesn't oppose anything
        
        if trade_direction == "BUY" and self.bias == GlobalBias.RISK_OFF:
            return True
        
        if trade_direction == "SELL" and self.bias == GlobalBias.RISK_ON:
            return True
        
        return False


# Test function
if __name__ == "__main__":
    print("Testing Global Market Analyzer...")
    gmam = GlobalMarketAnalyzer()
    
    print("\n1. Fetching global data...")
    success = gmam.fetch_global_data()
    
    if success:
        print("\n2. Calculating bias...")
        gmam.calculate_bias()
        
        print("\n3. Generating Telegram alert...")
        print(gmam.format_telegram_alert())
    else:
        print("❌ Failed to fetch global data")
