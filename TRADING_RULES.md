# 📊 Trading Strategy Rules (Gold Guinea)

This document details the exact logic used by the bot for Mode A, Mode B, and Mode C.

## 🌍 Global Context

- **Trend Timeframe**: 30 Minutes (EMA 20/50 Slope).
- **Entry Timeframe**: 5 Minutes.
- **Session Filter**: 14:00 to 23:30 (IST).
- **Risk Management**:
  - **Stop Loss**: Dynamic based on ATR (Volatility).
  - **Targets**: Risk:Reward Ratio (1:2 for Trend, 1:1 for Scalp).

---

## 🟢 Mode A: Trend Reversal (Early Entry)

_Captures the start of a new trend when price reclaims the EMA._

### Logic

1.  **30m Trend**: Checks for a fresh trend shift (e.g., Neutral -> Bullish).
2.  **5m Setups**:
    - **Buy**: Price closes ABOVE EMA 20 after being below it for at least 3 candles.
    - **Sell**: Price closes BELOW EMA 20 after being above it.
3.  **Validation**:
    - **RSI Filter**: Must be "Neutral" (Bullish: 55-68, Bearish: 32-45) to avoid exhaustion.
    - **Freshness**: The cross must be a _fresh_ reclaim, not an old chopping market.

---

## 🔵 Mode B: Trend Continuation (Pullback)

_Enters an established trend on a dip or support test._

### Logic

1.  **30m Trend**: Must be clearly established (Bullish/Bearish confirmed > 10 candles).
2.  **5m Setups**:
    - **Pullback**: Price retraces to the EMA 20 zone.
    - **Patterns**: "EMA Touch" or "Consolidation" near Support.
3.  **Validation**:
    - **RSI Filter**: Mid-range (Bullish: 45-62, Bearish: 38-55).
    - **Structure**: Price must not have broken major swing points.

---

## 🟣 Mode C: Momentum Breakout (Scalp)

_High-probability momentum bursts, usually after consolidation._

### Logic

1.  **30m Trend**: Trend must be strong (Steep Slope).
2.  **5m Setups**:
    - **Breakout**: "Inside Bar Breakout", "Impulse Candle", or "Consolidation Breakout".
    - **Volume**: Must be higher than Average Volume (20 period).
3.  **Validation**:
    - **RSI Filter**: Specific narrow range (40-60) to catch expansion before it becomes overbought/oversold.
    - **Risk**: Tighter Stop Loss (0.6 \* ATR) and Target (1:1 RR).

---

## 🛡️ Risk Management (The "Kill Switch")

To protect capital, the bot enters a **STOP STATE** for the day if:

1.  **Consecutive Losses**: 3 losses in a row.
2.  **Drawdown**: Net PnL drops below -2.0 R (Risk Units).

Once triggered, no new trades are taken until the next trading day.

---

## 📉 Indicators Used

- **EMA 20 & 50**: For Trend Direction and Support/Resistance.
- **ATR (14)**: For Volatility-based Stop Loss/Target.
- **RSI (14)**: For Momentum and Overbought/Oversold filtering.
- **Volume**: For breakout confirmation.
