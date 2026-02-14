"""
Sample: Add Daily Signal Cap to unified_engine.py
"""

class UnifiedRunner:
    def __init__(self):
        # ... existing code ...
        
        # NEW: Daily limits
        self.daily_signal_count = 0
        self.max_signals_per_day = 25  # Customize this
        self.last_reset_date = None
    
    def process_instrument(self, token, instrument, strategy, last_processed, global_bias="NEUTRAL"):
        # Reset counter at start of day
        from datetime import date
        today = date.today()
        if self.last_reset_date != today:
            self.daily_signal_count = 0
            self.last_reset_date = today
        
        # Check limit before processing
        if self.daily_signal_count >= self.max_signals_per_day:
            print(f"⚠️ Daily limit reached ({self.max_signals_per_day} signals)")
            return last_processed
        
        # ... existing signal detection code ...
        
        # After sending signal, increment counter:
        if signal_sent:
            self.daily_signal_count += 1
            print(f"📊 Signals today: {self.daily_signal_count}/{self.max_signals_per_day}")
