# Telegram Notification Flow (All Strategies)

The system delivers **Zero Latency Rules-Based Alerts** followed immediately by **Async AI Analysis**. This ensures you get the raw signal instantly, while AI provides the "Second Opinion" and "Post-Trade Review".

## 1. AI Integration

- **Entry:** AI checks Trend, RSI, and Volatility to assign a **Confidence Score (1-10)** and **Risk Level**.
- **Exit:** AI analyzes the result (SL/Target) to explain **WHY** it happened and provide a **Lesson**.

---

## 2. Notification Samples (By Instrument)

### 🌍 GLOBAL MARKET ANALYSIS (Context)

**Trigger:** Login / 12:30 / 12:45 IST.

```html
🌍 GLOBAL MARKET CONTEXT US Markets: • S&P 500: ✅ +0.45% • Nasdaq: ⚠️ -0.12%
Asia: • Nikkei: ✅ +0.80% Volatility & Macro: • VIX: 🔴 -6.20% • DXY: 0 (Stable)
📊 Score: +3 Global Bias: 🟢 RISK_ON Impact: • MODE D: BUY preferred • MODE C:
BUY confidence ↑
```

### 👁️ LIVE WATCH (Forming Setup)

_Trigger: Valid setup conditions on a live (unclosed) candle._

```html
👀 LIVE WATCH (NFO:NIFTY25JANFUT) Potential MODE_A | BUY Price: 24155.0 Candle
forming...
```

---

### A. NIFTY 50 (Trend Strategy)

**Logic:** Strict Mode A/B/C. High structure focus.

**Message 1: Signal (Immediate)**

```html
🔔 NFO:NIFTY25JANFUT SIGNAL MODE: MODE_A | TYPE: BUY ENTRY: 24150.0 SL: 24100.0
| TGT: 24225.0 PATTERN: Fresh Trend Reclaim TIME: 2025-01-02 10:15:00
```

**Message 2: AI Entry Logic (Async)**

```html
🤖 AI Risk Check (NFO:NIFTY25JANFUT) Confidence: ⚡⚡⚡⚡⚡⚡⚡⚡ (8/10) Risk:
🟢 Low | Action: Proceed "Strong trend structure with RSI reset; low volatility
breakout supports continuation."
```

---

### B. BANK NIFTY (Volatility Strategy)

**Logic:** Aggressive. Wide stops. Captures big moves.

**Message 1: Signal (Immediate)**

```html
🔔 NFO:BANKNIFTY25JANFUT SIGNAL MODE: MODE_C | TYPE: SELL ENTRY: 48050.0 SL:
48150.0 | TGT: 47950.0 PATTERN: EMA Touch TIME: 2025-01-02 13:45:00
```

**Message 2: AI Entry Logic (Async)**

```html
🤖 AI Risk Check (NFO:BANKNIFTY25JANFUT) Confidence: ⚡⚡⚡⚡⚡ (5/10) Risk: 🟡
Medium | Action: Caution "High volatility regime; valid setup but beware of
midday choppy wicks."
```

---

### C. GOLD GUINEA (Mean Reversion)

**Logic:** Pullbacks to Mean (EMA).

**Message 1: Signal (Immediate)**

```html
🔔 MCX:GOLDGUINEA26MARFUT SIGNAL MODE: Mode B | TYPE: BUY ENTRY: 62500.0 SL:
62450.0 | TGT: 62650.0 PATTERN: Pullback Rejection TIME: 2025-01-02 20:30:00
```

**Message 2: AI Entry Logic (Async)**

```html
🤖 AI Risk Check (MCX:GOLDGUINEA26MARFUT) Confidence: ⚡⚡⚡⚡⚡⚡ (6/10) Risk:
� Low | Action: Proceed "Mean reversion supported by oversold RSI; risk-reward
is favorable."
```

---

## 3. Exit Notifications (Analysis)

When a trade is closed (Target or SL), the AI performs a **Post-Trade Review**.

**Message 1: Exit Alert (Immediate)**

```html
🔔 NFO:BANKNIFTY25JANFUT SIGNAL MODE: MODE_C | TYPE: EXIT ENTRY: 48050.0 EXIT
TYPE: SL HIT TIME: 2025-01-02 14:05:00
```

**Message 2: AI Post-Trade Review (Async)**

```html
🤖 AI Post-Trade Review Result: SL HIT | Verdict: ⚠️ Bad Luck Reason: Sudden
volatility spike against trend direction. Lesson: Use wider stops during
high-impact news events.
```
