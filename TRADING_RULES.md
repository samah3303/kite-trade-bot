# 📜 Algorithm Trading Rules (v2.0)

This document serves as the "Constitution" for the Unified Trading Engine. It defines the logic for **Nifty 50**, **Bank Nifty**, and **Gold Guinea**.

---

## 🌍 General System Rules

- **Platform:** Kite Connect (Zerodha) + Telegram Alerts.
- **Timeframes:**
  - **Trend:** 30-Minute Candles (Trend Direction & Slope).
  - **Entry:** 5-Minute Candles (Closed Candle Only).
- **AI Integration:** Gemini Flash 2.0 analyzes every Entry/Exit for risk context.
- **Safety**:
  - **Blackout Periods:** No new trades after 14:30 (Indices) / 23:00 (Gold).
  - **Kill Switch:** Algorithm stops if Daily PnL hits **-1.5R** or Max Trades **10**.

---

## 1️⃣ NIFTY 50 Strategy (Strict Trend)

**Philosophy:** "Patient Sniper". Only takes high-quality setups with structure alignment.

| Rule           | Mode A (Fresh)                   | Mode B (Pullback)                | Mode C (Mom/Breakout)           |
| :------------- | :------------------------------- | :------------------------------- | :------------------------------ |
| **Concept**    | Catch start of new trend.        | Buy dips in strong trend.        | Fast scalp on expansion.        |
| **Logic**      | 30m Trend Reversal + 5m Reclaim. | Price touches EMA20 + Rejection. | Volatility Expansion + Pattern. |
| **RSI (Buy)**  | 56 – 72                          | 52 – 65                          | 45 – 68                         |
| **RSI (Sell)** | 28 – 44                          | 35 – 48                          | 32 – 55                         |
| **Stop Loss**  | 1.2 ATR                          | 1.0 ATR                          | 0.8 ATR                         |
| **Target**     | Trailing                         | 1.5 R                            | 1.2 R                           |
| **Special**    | Must be "Fresh" (New Leg).       | Max 0.5 ATR Pullback Depth.      | Blocked if consolidated.        |

---

## 2️⃣ BANK NIFTY Strategy (High Volatility)

**Philosophy:** "Aggressive Hunter". Wide stops to survive whipsaws; capitalized on big moves.

| Rule           | Mode A (Fresh)                    | Mode B (Pullback)                | Mode C (Scalp)                         |
| :------------- | :-------------------------------- | :------------------------------- | :------------------------------------- |
| **Concept**    | Survive initial volatility.       | Deep value entries.              | Quick hit in chaos.                    |
| **Logic**      | 30m Trend Change + Thrust Candle. | **Deep** Pullback (0.2-0.6 ATR). | High Volatility (ATR>MA) + Inside Bar. |
| **RSI (Buy)**  | 55 – 70                           | 50 – 62                          | 45 – 60                                |
| **RSI (Sell)** | 30 – 45                           | 38 – 50                          | 40 – 55                                |
| **Stop Loss**  | **1.4 ATR** (Wide)                | **1.2 ATR**                      | **0.9 ATR** (Fixed)                    |
| **Target**     | Trailing (Aggressive)             | 2.0 R                            | **1.0 R Fixed** (No Trail)             |
| **Special**    | Wick % Check (Body > 65%).        | Time-based Entry allowed.        | **Disabled** if ATR low.               |

---

## 3️⃣ GOLD GUINEA Strategy (Mean Reversion)

**Philosophy:** "Rhythmic Swinger". Exploits Gold's tendency to respect EMA20.

| Rule           | Mode A (Reversal)          | Mode B (Touch)             | Mode C (Structure)    |
| :------------- | :------------------------- | :------------------------- | :-------------------- |
| **Concept**    | Trend Change Confirmation. | The "Standard" Gold trade. | Structure Breakouts.  |
| **Logic**      | Price Crosses EMA20.       | EMA20 Touch + Rejection.   | Impulse / Inside Bar. |
| **RSI (Buy)**  | 55 – 68                    | 45 – 62                    | 40 – 60               |
| **RSI (Sell)** | 32 – 45                    | 38 – 55                    | 40 – 60               |
| **Stop Loss**  | 2.0 ATR                    | 2.0 ATR                    | 0.6 ATR               |
| **Target**     | 2.0 R                      | 2.0 R                      | 1.0 R                 |
| **Special**    | Evening Session (14:00+).  | -                          | -                     |

---

## 🤖 AI Logic (The "Risk Manager")

The AI does NOT generate signals. It **grades** them.

1.  **Confidence Score (⚡):**

    - **High (8-10):** Perfect alignment of Trend, Slope, and RSI.
    - **Med (5-7):** Valid setup but mixed signals (e.g., lower timeframe divergence).
    - **Low (1-4):** Counter-trend or dangerous volatility.

2.  **Risk Verdict (🟢/🟡/🔴):**

    - Based on ATR (Choppiness) and RSI Extremes.
    - **Actionable Advice:** "Proceed", "Caution", or "Skip".

3.  **Exit Analysis:**
    - After a trade, AI reviews the outcome.
    - **Reason:** Was it bad luck (news spike) or technical failure?
    - **Lesson:** One line tip for future improvement.
