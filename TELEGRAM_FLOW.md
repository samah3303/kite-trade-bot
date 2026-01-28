# Telegram Notification Flow (Active Strategies)

The system delivers **Zero Latency Rules-Based Alerts** followed immediately by **Async AI Analysis**.

## 1. AI Integration

- **Entry:** AI checks Trend, RSI, and Volatility to assign a **Confidence Score (1-10)** and **Risk Level**.
- **Exit:** AI analyzes the result (SL/Target) to explain **WHY** it happened.

---

## 2. Notification Samples

### 🌍 GLOBAL MARKET ANALYSIS (Context)

_Trigger: Login / 12:30 / 12:45 IST_

```html
🌍 GLOBAL MARKET CONTEXT US Markets: • S&P 500: ✅ +0.45% Asia: • Nikkei: ✅
+0.80% 📊 Score: +3 Global Bias: 🟢 RISK_ON Impact: • MODE D: BUY preferred •
MODE C: BUY confidence ↑
```

### 👁️ LIVE WATCH (Forming Setup)

_Trigger: Valid setup conditions on a live (unclosed) candle._

```html
👀 LIVE WATCH (NFO:NIFTY26JANFUT) Potential MODE_A | BUY Price: 24155.0 Candle
forming...
```

---

### A. NIFTY 50 (Strategies: Mode A/B/C/D + Mode F)

#### 1. Mode A: Fresh Trend Reclaim

_Fresh trend confirmation after a reversal._

```html
🔔 CONFIRMED SIGNAL: MODE_A INSTRUMENT: NFO:NIFTY26JANFUT TYPE: BUY ENTRY:
24150.0 SL: 24100.0 | TGT: 24225.0 PATTERN: Fresh Trend Reclaim TIME: 2025-01-02
10:15:00
```

#### 2. Mode B: Pullback Rejection

_Buying dips in a confirmed trend._

```html
🔔 CONFIRMED SIGNAL: MODE_B INSTRUMENT: NFO:NIFTY26JANFUT TYPE: BUY ENTRY:
24200.0 SL: 24180.0 | TGT: 24250.0 PATTERN: Pullback Rejection TIME: 2025-01-02
11:30:00
```

#### 3. Mode C: Breakout / Momentum

_Impulse moves and inside bar breaks._

```html
🔔 CONFIRMED SIGNAL: MODE_C INSTRUMENT: NFO:NIFTY26JANFUT TYPE: BUY ENTRY:
24300.0 SL: 24285.0 | TGT: 24325.0 PATTERN: Inside Bar Break TIME: 2025-01-02
13:45:00
```

#### 4. Mode D: Opening Drive

_First 15 minutes aggressive entry (09:15-09:30)._

```html
🔔 CONFIRMED SIGNAL: MODE_D INSTRUMENT: NFO:NIFTY26JANFUT TYPE: SELL ENTRY:
24100.0 SL: 24140.0 | TGT: 24000.0 PATTERN: Opening Drive Pullback TIME:
2025-01-02 09:20:00
```

#### 5. Mode F: Automated 3-Gear Engine

_High-Frequency automated scalp logic._

```html
🔔 CONFIRMED SIGNAL: MODE_F INSTRUMENT: NFO:NIFTY26JANFUT TYPE: BUY ENTRY:
24160.0 SL: 24140.0 | TGT: 24200.0 PATTERN: GEAR_1_TREND | Trend Pullback GEAR:
GEAR_1_TREND (NORMAL) TIME: 2025-01-02 10:05:00
```

---

### B. SENSEX (Strategy: Mode S)

#### Mode S: Core / Stability / Liquidity

_Specialized Sensex Strategy._

```html
🔔 CONFIRMED SIGNAL: MODE S INSTRUMENT: BSE:SENSEX TYPE: BUY BUCKET: CORE ENTRY:
72500.0 SL: 72400.0 | TGT: 72700.0 REASON: Trend Pullback TIME: 2025-01-02
11:30:00
```

---

## 3. Exit Notifications

When a trade is closed, you receive an **Immediate Alert** followed by an **AI Review**.

### Exit Alerts (Standard)

**Stop Loss Hit:**

```html
🔔 EXIT SIGNAL: NFO:NIFTY26JANFUT TYPE: SL HIT ENTRY: 24150.0 | EXIT: 24100.0
PNL: -2500.0
```

**Target Hit:**

```html
🔔 EXIT SIGNAL: NFO:NIFTY26JANFUT TYPE: TARGET HIT ENTRY: 24150.0 | EXIT:
24225.0 PNL: +3750.0
```

---

## 4. AI Analysis Messages

### AI Entry Logic (Async)

_Sent ~5 seconds after Entry Signal_

```html
🤖 AI Risk Check (NFO:NIFTY26JANFUT) Confidence: ⚡⚡⚡⚡⚡⚡⚡⚡ (8/10) Risk:
🟢 Low | Action: Proceed "Strong trend structure with RSI reset; low volatility
breakout supports continuation."
```

### AI Post-Trade Review (Async)

_Sent ~5 seconds after Exit Signal_

**Scenario 1: Loss (Lesson)**

```html
🤖 AI Post-Trade Review Result: SL HIT | Verdict: ⚠️ Bad Luck Reason: Sudden
volatility spike against trend direction. Lesson: Use wider stops during
high-impact news events.
```

**Scenario 2: Win (Reinforcement)**

```html
🤖 AI Post-Trade Review Result: TARGET HIT | Verdict: OK Good Exit Reason: Trend
continued as expected with volume support. Lesson: Great patience waiting for
the pullback.
```
