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

## II. GLOBAL MARKET ANALYSIS MODULE (GMAM)

**Purpose:** Daily context & directional bias.
**Triggers:** Login, 12:30 IST, 12:45 IST.

| Context      | Criteria   | Impact                                      |
| :----------- | :--------- | :------------------------------------------ |
| **RISK-ON**  | Score ≥ +2 | MODE D: BUY Only<br>MODE C: BUY Preferred   |
| **RISK-OFF** | Score ≤ -2 | MODE D: SELL Only<br>MODE C: SELL Preferred |
| **NEUTRAL**  | Others     | All Normal                                  |

---

## III. DAY TYPE CLASSIFICATION

**Purpose:** Detect CHOP early.
**CHOP Criteria:** ATR Flat/Falling AND EMA20 Range < 0.3% AND Mixed Opening.
**Impact:** If CHOP → **MODE D BLOCKED**.

---

## IV. NIFTY 50 STRATEGY (PRIMARY)

**Execution Order:**

1. Global Analysis
2. Day Type
3. **MODE D (09:20-10:30)**
4. **MODE C** (Core)
5. **MODE A/B** (Aux)

### 🅳 MODE D — OPENING DRIVE (Institutional)

- **Time:** 09:20 – 10:30 IST.
- **Goal:** Capture institutional opening momentum.
- **Entry:** Option B (Conservative) - Pullback to EMA20 & Rejection.
- **Risk:** SL: 1.0 ATR (or Structure) | Target: **1.5R Fixed**.
- **Limit:** **MAX 1 TRADE/DAY**.

### 🅲 MODE C — MOMENTUM (Core Engine)

- **Goal:** Trend Continuation / Breakouts.
- **Eligibility:** Trend Aligned, Volatility Expanding.
- **Logic:** Range Breakouts, EMA Touches.
- **Risk:** SL: ~0.8 ATR | Target: Trail or 1.2R.

### 🅰️ MODE A — FRESH TREND

- **Goal:** Reversal catch.
- **Logic:** 30m Trend Change + 5m Reclaim.

### 🅱️ MODE B — PULLBACK

- **Goal:** Deep value in trend.
- **Logic:** Deep pullback to EMA20 with rejection.

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
