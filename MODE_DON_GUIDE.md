# MODE_DON — How It Works (Simple Guide)

> _"Wait for the strong days. Strike on breakouts. Trail the winners. Die fast on losers."_

---

## What Is MODE_DON?

MODE_DON is a **breakout trading system** that watches 3 instruments — **Nifty 50**, **Sensex**, and **Bank Nifty** — and sends you Telegram alerts when price breaks out of a range during strong trending days.

**Key difference from RIJIN/MODE_F:** There is **no AI involved**. Every decision is rule-based and predictable. Same input = same output, every time.

---

## The Daily Routine

### ⚡ 9:45 AM: Provisional Mode (Early Gate)

MODE_DON **doesn't wait until noon** anymore. Starting at 9:45, it checks 3 strict conditions every candle:

| Condition     | What It Means                             | Threshold                      |
| ------------- | ----------------------------------------- | ------------------------------ |
| **Expansion** | Market has moved beyond the opening range | ≥ 1.5× opening 30-min range    |
| **VWAP Hold** | Price is committed to one direction       | 5 candles on same side of VWAP |
| **ATR Gate**  | Volatility is growing                     | ≥ 1.1× morning ATR             |

**All 3 must pass simultaneously.** If any one fails → no trading.

> This catches strong opening impulses (like 9:45–10:30 trend days) while blocking fake spikes and chop.

When the early gate passes, the dashboard shows the instrument as **⚡ Provisional** and breakout scanning begins.

---

### ⏱ Lookback Formation Rule

Even if the early gate passes, MODE_DON **won't fire a breakout until enough candles exist** to form the Donchian channel:

| Instrument | Lookback   | Earliest Valid Breakout |
| ---------- | ---------- | ----------------------- |
| NIFTY 50   | 20 candles | ~10:55 AM               |
| SENSEX     | 18 candles | ~10:45 AM               |
| BANK NIFTY | 15 candles | ~10:30 AM               |

> This prevents triggering on a "breakout" of just a handful of candles — the box needs to be fully drawn first.

---

### 📊 12:00 PM: The Full Verdict

At exactly **12:00 PM**, MODE_DON runs the **full 4-metric scoring**:

| What It Measures    | What It Means                                                    | Score |
| ------------------- | ---------------------------------------------------------------- | ----- |
| **Expansion Ratio** | Has the market moved well beyond the opening range?              | 0–2   |
| **VWAP Stability**  | Is price staying consistently on one side of VWAP?               | 0–2   |
| **Structure**       | Are there clean directional legs (like stairs), or is it choppy? | 0–2   |
| **ATR Expansion**   | Is volatility growing compared to the morning?                   | 0–2   |

**Total score: 0 to 8**

| Score   | Day Type        | What Happens                |
| ------- | --------------- | --------------------------- |
| **7–8** | 🟢 Clean Trend  | Full trading allowed        |
| **5–6** | 🟡 Normal Trend | Full trading allowed        |
| **3–4** | 🟠 Rotation     | ❌ NO trading — too messy   |
| **0–2** | 🔴 Range        | ❌ NO trading — flat market |

After 12 PM, the **provisional gate is replaced** by the locked regime score. If the score comes in as Rotation or Range, MODE_DON shuts off — even if it was trading during the morning.

---

### 🎯 Breakout Entry (Same Before and After 12 PM)

When allowed (either by early gate or full regime), MODE_DON watches for **Donchian breakouts**:

Imagine drawing a box around the **highest high** and **lowest low** of the last 20 candles.

- If price **closes above the top of the box** → LONG signal
- If price **closes below the bottom of the box** → SHORT signal

That's it. No indicators, no oscillators, no AI opinion. Just: "Did price break the box?"

**Why only on close?** Because wicks lie. A momentary spike might reverse instantly. MODE_DON waits for the candle to **close** above/below — that's stronger confirmation.

---

### 🛡 Safety Checks Before Every Entry

Even on a trending day, MODE_DON won't enter unless:

1. ✅ ATR (volatility) is **still expanding** — not fading
2. ✅ The move hasn't already gone too far (exhaustion check)
3. ✅ The instrument hasn't hit its daily loss limit
4. ✅ No more than 3 trades are open across all instruments
5. ✅ The system hasn't hit the overall -3R daily loss cap

---

### 📏 Managing the Trade: Trailing Stop

Once in a trade, there is **no fixed profit target**. MODE_DON lets winners run.

The stop follows a **trailing Donchian** — the lowest low of the last 10 candles. As the market moves in your favor, the stop moves up (for longs) or down (for shorts). It can **never move against you**.

If the market reverses and hits the trailing stop → exit. If it keeps running → the stop keeps following.

> This is how breakout traders capture 2R, 3R, even 4R moves — by not having a fixed target.

---

## One-Way Degradation

After 12 PM, the day type can only **get worse**, never better.

If the market was scored as "Normal Trend" at 12 PM but then:

- VWAP flips and price stays on the opposite side for 45 minutes
- Volatility contracts below morning levels
- Structure breaks down (starts zigzagging)

...the day gets **downgraded** to Rotation or Range, and MODE_DON **shuts off for the rest of the day**.

> This prevents the trap of "it was trending earlier, maybe it'll come back." It won't. The system accepts reality.

---

## Per-Instrument Rules

|                       | Nifty 50              | Sensex     | Bank Nifty          |
| --------------------- | --------------------- | ---------- | ------------------- |
| **Breakout lookback** | 20 candles            | 18 candles | 15 candles          |
| **Risk per trade**    | 1R                    | 1R         | 0.75R               |
| **Daily loss cap**    | -2.5R                 | -2.5R      | -2.0R               |
| **Trading hours**     | 9:30–12:45, 1:30–2:45 | Same       | 9:30–11:45          |
| **Afternoon session** | Always                | Always     | Only if Clean Trend |

Bank Nifty has **tighter rules** because it's the most volatile instrument — bigger moves but also bigger traps.

---

## System-Level Protection

| Rule                        | What It Does                                                              |
| --------------------------- | ------------------------------------------------------------------------- |
| **Max 3 concurrent trades** | Can hold Nifty + Sensex + BankNifty at most                               |
| **-3R daily system stop**   | If combined losses hit -3R across all instruments → done for the day      |
| **3 consecutive losses**    | 3 stops in a row on one instrument → that instrument disabled for the day |
| **No double entries**       | Can't have two positions on the same instrument                           |

---

## What to Expect

|                          | Realistic Range                                            |
| ------------------------ | ---------------------------------------------------------- |
| **Trades per week**      | 8–18 across all instruments                                |
| **Active days per week** | 2–3 (including provisional morning triggers)               |
| **Win rate**             | 35–48% (most breakouts fail)                               |
| **Average winner**       | 2R–4R (trailing stop lets winners run)                     |
| **Average loser**        | -1R (stopped out quickly)                                  |
| **Edge**                 | Low win rate × big winners > high frequency × small losses |

> **The math:** If you win 40% of trades at +3R and lose 60% at -1R:
> Expected value = (0.40 × 3R) + (0.60 × -1R) = **+0.60R per trade**

---

## Telegram Alerts

When MODE_DON fires, you'll get a message like:

```
🟦 MODE_DON | NIFTY 50 | LONG

Time: 13:15 IST
Day Type: Clean Trend (Score 7/8)
Donchian(20) Breakout Confirmed

Entry: 24250
Stop: 24180
Risk: 1R

ATR Ratio: 1.35×
Session Expansion: 2.8×

AI Layer: NOT USED
```

The "AI Layer: NOT USED" line is intentional — so you always know this signal came from rules, not a model.

---

## In One Sentence

> MODE_DON checks the market from 9:45 with a provisional gate, locks the regime at noon, and trades breakouts on genuinely strong days — then lets the move run with a trailing stop and no fixed target.

That's it. No AI. No indicators. No opinions. Just structure, expansion, and breakout.
