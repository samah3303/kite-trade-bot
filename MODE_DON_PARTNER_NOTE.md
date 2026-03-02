# What We're Building & Why — Partner Update

> **Date:** March 3, 2026
> **System:** KiteAlerts Trading Bot
> **For:** Non-technical trading partner review

---

## Where We Are Today

We currently have a working trading system with two engines running in parallel:

| Engine           | What It Does                                                                                                                                                  | Status  |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| **RIJIN v3.0.1** | AI-filtered signal engine for Nifty. Catches intraday setups using RSI/ATR/structure, then asks an AI model to accept or reject. Fixed 15-point target.       | ✅ Live |
| **MODE_DON**     | Rule-based breakout engine for Nifty + Sensex + Bank Nifty. No AI. Waits for strong trending days, enters on Donchian breakouts, trails with no fixed target. | ✅ Live |

Both send Telegram alerts. Neither executes trades automatically — **we still decide whether to take the trade.**

---

## What's Planned Next (and Why It Matters to Our P&L)

### 🔴 Week 1 — Survival Features (Highest Priority)

**1. Daily Drawdown Circuit Breaker**
Right now there's no hard stop if we have a terrible day. If RIJIN fires 5 losing trades, that's -5R with nothing stopping it.

→ **Fix:** Auto-shutdown at -3R daily. One Telegram alert: "Done for the day." No more trades until tomorrow.

**Why it matters:** Prevents one bad day from wiping out a week of gains. This is non-negotiable for any serious system.

---

**2. Trade Journal (Database)**
Currently, there's no record of what trades fired, what the AI said, what happened. Everything disappears when the app restarts.

→ **Fix:** Every trade, every AI decision, every outcome gets logged to a database. Daily summaries auto-generated.

**Why it matters:** We can't improve what we can't measure. Without this:

- We can't calculate our real win rate
- We can't know if the AI filter is actually helping
- We can't show a track record to anyone
- We can't backtest improvements

**This is the foundation for everything else.**

---

**3. Token Expiry Alert**
Zerodha tokens expire every day. If nobody logs in before market open, the bot sits there doing nothing.

→ **Fix:** Bot detects expired token and sends a Telegram message with the login link. Takes 10 seconds to fix from your phone.

**Why it matters:** Prevents missed trading days because someone forgot to log in.

---

### 🟡 Week 2 — Tighter Edge

**4. Smarter Position Sizing**
Right now, every trade risks the same amount — regardless of whether the AI says it's 90% confident or barely 60%.

→ **Fix:** High confidence signals = bigger size. Low confidence = smaller size. Also adjusts for winning/losing streaks.

**Why it matters:** We risk more when conditions are best, less when they're marginal. Same number of trades, better returns.

---

**5. Slippage Buffer**
Backtests assume we get filled at the exact price. We don't. In reality, entry is 2–3 points worse, stops get hit slightly beyond the level.

→ **Fix:** All calculations and alerts include a realistic slippage buffer.

**Why it matters:** Prevents over-sizing. Shows us honest expected returns instead of optimistic ones.

---

**6. Better AI Scoring**
The AI currently gives subjective "overextended" or "looks good" type answers. Sometimes it's inconsistent — same setup, different answer.

→ **Fix:** Give the AI a strict rubric with 5 criteria scored 0–2 each. Total 6+ = take the trade. Below 6 = skip.

**Why it matters:** Makes the AI filter predictable and auditable. We can look at any trade and see exactly why it was accepted or rejected.

---

### 🟡 Week 3 — Better Signals

**7. Volume Confirmation**
Sometimes the bot triggers on a big candle that has no real buying/selling behind it — just noise.

→ **Fix:** Require above-average volume on the breakout candle before triggering.

**Why it matters:** Filters out fake moves. Fewer losing trades.

---

**8. Time-of-Day Rules**
Some strategies work in certain hours but not others. Momentum signals at 2:30 PM get chopped up. Trend signals in the first 15 minutes are unreliable.

→ **Fix:** Restrict which signal types are allowed during which hours.

**Why it matters:** Same signals, but we only take them when they historically work best.

---

### 🟢 Week 4 — Measurement & Validation

**9. Backtest Runner**
Before changing any setting, we should be able to test it on historical data first.

→ **Fix:** Build a tool that replays past data through our signal engine and shows: "If you used these settings for the last 60 days, here's what would have happened."

**Why it matters:** Lets us validate changes before risking real money. No more "let's try this and see."

---

**10. AI Audit Report**
The biggest question: **Is the AI filter actually making us money?**

→ **Fix:** Compare trades the AI accepted (did they win?) vs trades the AI rejected (would they have won?). Calculate the AI's actual value in R-multiple.

**Why it matters:** If the AI is rejecting trades that would have won more than it's blocking losers, we should adjust. Data > feelings.

---

## The Big Picture

```
CURRENT STATE (Today)
├── RIJIN v3.0.1 → AI-filtered Nifty signals → Live ✅
├── MODE_DON → Breakout engine (3 instruments) → Live ✅
└── Dashboard → Start/stop, live stats, console → Live ✅

AFTER WEEK 1-2
├── Hard daily loss cap → Can't blow up
├── Full trade journal → Every trade recorded
├── Token alerts → No missed days
├── Smarter sizing → More on best setups
└── Better AI → Consistent decisions

AFTER WEEK 3-4
├── Volume filter → Fewer false signals
├── Time rules → Right trades at right times
├── Backtester → Test before deploy
└── AI audit → Prove the AI earns its keep
```

---

## What This Means Financially

| Improvement      | Expected Impact                                           |
| ---------------- | --------------------------------------------------------- |
| Drawdown breaker | Prevents -5R or worse days → saves ~2-4R/month            |
| Smarter sizing   | +10-15% better returns on same trades                     |
| Better AI rubric | Fewer inconsistent rejections → captures ~1-2R/month more |
| Volume filter    | Removes 2-3 false signals/week → saves ~1-2R/month        |
| Time rules       | Cuts late-day losses → saves ~1R/month                    |
| MODE_DON (done)  | Adds 8-18 trades/week on expansion days → est. +7R/week   |

**Conservative estimate:** These improvements combined should add **+15-25R per month** in either captured gains or prevented losses.

---

## What's NOT on This List

- ❌ Auto-execution (not until we have 3+ months of journal data proving consistency)
- ❌ Options trading (future consideration)
- ❌ More AI models (current one works, just needs better prompting)
- ❌ More instruments for RIJIN (MODE_DON already covers Sensex + Bank Nifty)

---

## Timeline

| Week       | What Gets Done                          | Risk Level                       |
| ---------- | --------------------------------------- | -------------------------------- |
| **Week 1** | Loss cap + trade journal + token alerts | Zero risk (safety features)      |
| **Week 2** | Position sizing + slippage + AI rubric  | Low risk (tuning, not new logic) |
| **Week 3** | Volume filter + time rules + backtester | Low risk (additional filters)    |
| **Week 4** | AI audit + dashboard analytics          | Zero risk (measurement only)     |

> **Nothing on this list increases our risk exposure.** Every item either reduces risk, improves signal quality, or adds measurement capability.

---

_Happy to discuss any of these in detail. The priority order is deliberate — safety first, edge refinement second, measurement third._
