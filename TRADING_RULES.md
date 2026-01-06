# 📜 Algorithm Trading Rules (v5.0 - NIFTY-CENTRIC)

This is the **production constitution** for the Unified Trading Engine.

---

## 0️⃣ INSTRUMENT SCOPE

| Instrument      | Status       | Role               |
| --------------- | ------------ | ------------------ |
| **NIFTY 50**    | ✅ PRIMARY   | Core profit engine |
| **GOLD GUINEA** | ⚠️ SECONDARY | Regime-dependent   |
| **BANK NIFTY**  | ❌ REMOVED   | No edge, high risk |

---

## 1️⃣ NIFTY 50 Strategy (The Engine)

**Philosophy:** Momentum First, Patience Second.

### 🅰️ MODE A — FRESH TREND (Rare)

- **Goal:** Catch the birth of a new trend.
- **Logic:** 30m Trend Reversal + 5m Reclaim.
- **RSI:** 56–72 (Buy) / 28–44 (Sell).
- **Risk:** SL ~1.2 ATR | Target ~2.0 ATR.

### 🅱️ MODE B — PULLBACK (Strict Gate)

- **Goal:** Buy the dip in a mature trend (Safely).
- **Strict Gate (ALL Must Pass):**
  1.  EMA Separation ≥ 0.25%
  2.  ATR Flat/Falling (Last 3 candles)
  3.  Price NOT making new High/Low
- **Entry:** Rejection candle at EMA20.
- **Risk:** SL: Rejection Low/High | Target: 1.2 R.
- **Cool-off:** 1 loss → Skip next setup.

### 🅲 MODE C — MOMENTUM (Primary)

- **Goal:** Exploit fast intraday expansion. **(Main Profit Driver)**
- **Eligibility:**
  - 30m Trend Aligned.
  - EMA Separation exists.
  - ATR Rising (Expansion).
- **Entry:** Breakout of recent structure (High/Low).
- **Filters:** RSI > 55 (Buy) / < 45 (Sell). MACD Confirm.
- **Loss Brake:** 3 consecutive losses → Pause Mode C for day.

---

## 2️⃣ GOLD GUINEA Strategy (Auxiliary)

**Philosophy:** Mean Reversion only.

### 🅲 MODE C — MOMENTUM ONLY

- **Goal:** Catch volatility spikes.
- **Logic:** 30m Trend + 5m EMA Separation + **ATR Rising**.
- **Risk:** SL: 0.5-1.0 ATR | Target: 2.0 R.
- **Modes A & B:** **DISABLED**.

---

## 3️⃣ GLOBAL SAFETY RULES

1.  **Time Filter:** 09:30 – 14:30 (Nifty) / 14:00 – 23:30 (Gold).
2.  **Kill Switch:**
    - Daily Loss ≥ **-1.5 R**
    - Max Trades = 7 (Nifty)
3.  **Engine Logic:**
    - **Live Watch:** Alerts ONLY. No execution.
    - **Decision:** Closed Candle ONLY.

---
