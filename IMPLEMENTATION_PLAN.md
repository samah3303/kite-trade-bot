# 🛠 KiteAlerts — Implementation Plan

> Full system roadmap covering RIJIN v3.0.1 upgrades and MODE_DON expansion.
> Updated: March 2, 2026

---

## ✅ Completed — MODE_DON Engine (Implemented)

> _Regime-gated Donchian breakout expansion engine. Fully deterministic. No AI._

### What Was Built

| File                 | Description                                                                            |
| -------------------- | -------------------------------------------------------------------------------------- |
| `mode_don_config.py` | Instrument configs, regime thresholds, early gate, risk governance, Telegram templates |
| `mode_don_engine.py` | RegimeEngine, DonchianSignalEngine, ModeDonInstrument, ModeDonEngine orchestrator      |
| `mode_don_runner.py` | Thread wrapper for dashboard integration (start/stop/stats)                            |
| `MODE_DON_GUIDE.md`  | Non-technical guide explaining the full system                                         |

### What Was Modified

| File             | Changes                                                                                   |
| ---------------- | ----------------------------------------------------------------------------------------- |
| `app.py`         | Added `/mode-don/start`, `/mode-don/stop`, `/mode-don/stats` endpoints                    |
| `dashboard.html` | Added MODE_DON section — 3 instrument cards, regime/P&L/trade status, start/stop controls |

### Architecture Summary

```
Phase 1 (9:45 AM) — Provisional Early Regime Gate
  ├── Expansion ≥ 1.5× opening range
  ├── VWAP held 5 consecutive candles
  └── ATR ≥ 1.1× morning ATR
  → All 3 pass? Breakout scanning begins (⚡ Provisional)

Lookback Formation Rule
  ├── NIFTY: 20-period → earliest breakout at 10:55
  ├── SENSEX: 18-period → earliest breakout at 10:45
  └── BANKNIFTY: 15-period → earliest breakout at 10:30

Phase 2 (12:00 PM) — Full Regime Scoring (0–8)
  ├── Expansion Ratio (0–2)
  ├── VWAP Stability (0–2)
  ├── Structure Continuity (0–2)
  └── ATR Expansion (0–2)
  → 7-8: Clean Trend | 5-6: Normal Trend | 3-4: Rotation ❌ | 0-2: Range ❌

Entry: Close > Donchian(N) high → LONG | Close < Donchian(N) low → SHORT
Stop: Opposite 10-period Donchian OR 1.2× ATR (tighter wins)
Trail: 10-period Donchian, never widens, no fixed target

Risk: Max 3 concurrent | -3R system cap | 3 consecutive losses disables instrument
```

### Instruments

|           | NIFTY 50              | SENSEX | BANK NIFTY                        |
| --------- | --------------------- | ------ | --------------------------------- |
| Donchian  | 20                    | 18     | 15                                |
| Risk      | 1R                    | 1R     | 0.75R                             |
| Daily Cap | -2.5R                 | -2.5R  | -2.0R                             |
| ATR Gate  | 1.2×                  | 1.2×   | 1.3×                              |
| Hours     | 9:30–12:45, 1:30–2:45 | Same   | 9:30–11:45 (PM: Clean Trend only) |

---

## Phase 1 — Critical Operations (Week 1)

> _Without these, the system can't run reliably day-to-day._

---

### 1.1 Daily Drawdown Circuit Breaker

**Problem:** No daily max loss. Five -1R trades spread across the day = -5R with no hard stop.

**Implementation:**

#### [MODIFY] `rijin_live.py`

- Add `DAILY_MAX_LOSS_R = -3.0` constant (configurable)
- In the main loop, before signal generation, check:
  ```python
  if self.daily_pnl_r <= DAILY_MAX_LOSS_R:
      # Send one-time Telegram alert
      # Skip all signal processing for the rest of the day
  ```
- Add `daily_stopped` flag to `reset_daily_state()` so it resets next morning

#### [MODIFY] `rijin_config.py`

- Add to config:
  ```python
  DAILY_DRAWDOWN_LIMIT = {
      "max_loss_r": -3.0,
      "alert_threshold_r": -2.0,  # Warning at -2R
  }
  ```

**Effort:** ~30 minutes · **Impact:** High (prevents account damage)

---

### 1.2 Trade Journal / SQLite Database

**Problem:** No persistent record of trades, AI decisions, or outcomes. Can't improve what you can't measure.

**Implementation:**

#### [NEW] `trade_journal.py`

- Create `TradeJournal` class with SQLite backend
- Schema:

  ```sql
  CREATE TABLE trades (
      id INTEGER PRIMARY KEY,
      date TEXT,
      time TEXT,
      instrument TEXT,
      direction TEXT,           -- BUY/SELL
      gear TEXT,                 -- GEAR_1/2/3
      entry REAL,
      sl REAL,
      target REAL,
      exit_price REAL,
      exit_type TEXT,            -- TARGET/SL/MANUAL
      pnl_r REAL,
      ai_decision TEXT,          -- ACCEPT/RESTRICT
      ai_confidence INTEGER,
      ai_reasons TEXT,           -- JSON array
      market_context TEXT,       -- Full JSON snapshot
      session_phase TEXT,
      day_type TEXT,
      rsi REAL,
      atr REAL,
      created_at TIMESTAMP
  );

  CREATE TABLE ai_decisions (
      id INTEGER PRIMARY KEY,
      date TEXT,
      time TEXT,
      direction TEXT,
      decision TEXT,
      confidence INTEGER,
      reasons TEXT,
      market_context TEXT,
      created_at TIMESTAMP
  );

  CREATE TABLE daily_summary (
      date TEXT PRIMARY KEY,
      total_trades INTEGER,
      wins INTEGER,
      losses INTEGER,
      pnl_r REAL,
      ai_accepts INTEGER,
      ai_restricts INTEGER,
      ai_failures INTEGER,
      day_stopped_early BOOLEAN,
      stop_reason TEXT
  );
  ```

- Methods: `log_trade()`, `log_ai_decision()`, `save_daily_summary()`, `get_stats()`

#### [MODIFY] `rijin_live.py`

- Import and initialize `TradeJournal`
- Call `journal.log_trade()` in `execute_trade()` and `close_trade()`
- Call `journal.log_ai_decision()` in `validate_signal_with_ai()`
- Call `journal.save_daily_summary()` at end-of-day

#### [NEW] Dashboard endpoint

- Add `/rijin/v3/journal` endpoint in `app.py` to view recent trades

**Effort:** ~2-3 hours · **Impact:** Critical (foundation for all future improvements)

---

### 1.3 Auto Access Token Refresh

**Problem:** Kite tokens expire daily. Someone must manually log in every morning.

**Implementation:**

#### [MODIFY] `rijin_live.py`

- Detect `TokenException` or 403 in `fetch_candles_5m()`
- On auth failure, send Telegram alert with the login URL:
  ```
  🔑 TOKEN EXPIRED
  Click to re-login: {kite.login_url()}
  Engine paused until token refreshed.
  ```
- Add a `/refresh-token` webhook endpoint in `app.py` that Zerodha can callback to

#### [MODIFY] `app.py`

- Add `/auth-status` endpoint that returns token health
- Add auto-redirect: if token is invalid on dashboard load, show login button prominently

**Effort:** ~1 hour · **Impact:** High (operational reliability)

---

## Phase 2 — Risk Management Upgrades (Week 2)

> _Tighten the edge. Reduce variance._

---

### 2.1 Dynamic Position Sizing

**Problem:** Fixed ₹1,000 risk per trade regardless of AI confidence or win streak.

**Implementation:**

#### [NEW] `position_sizer.py`

- **Confidence-based scaling:**
  ```python
  def calculate_risk(base_risk, ai_confidence):
      if ai_confidence >= 80:
          return base_risk * 1.5   # High confidence = 1.5R
      elif ai_confidence >= 60:
          return base_risk * 1.0   # Normal = 1R
      else:
          return base_risk * 0.5   # Low confidence = 0.5R
  ```
- **Kelly Criterion (optional):**
  - Requires trade journal data (win rate + avg win/loss ratio)
  - `kelly_fraction = win_rate - (1 - win_rate) / payoff_ratio`
  - Cap at 50% Kelly for safety
- **Streak adjustment:**
  - After 2 consecutive wins: +0.25R
  - After 2 consecutive losses: -0.25R (on top of the 60-min pause)

#### [MODIFY] `rijin_live.py`

- Replace fixed `RISK_PER_TRADE` with `position_sizer.calculate_risk()`
- Pass AI confidence to the sizer

**Effort:** ~1-2 hours · **Impact:** Medium (increases returns without increasing max risk)

---

### 2.2 Slippage Buffer

**Problem:** Backtest assumes perfect fills. Real execution has slippage.

**Implementation:**

#### [MODIFY] `rijin_config.py`

- Add:
  ```python
  SLIPPAGE_CONFIG = {
      "entry_buffer_points": 2,    # Assume 2 pts worse entry
      "sl_buffer_points": 3,       # SL hit 3 pts worse
      "apply_to_alerts": True,     # Show adjusted levels in Telegram
  }
  ```

#### [MODIFY] `rijin_live.py`

- In `execute_trade()`: adjust entry/SL/target by slippage buffer before calculating quantity
- In Telegram alert: show both "ideal" and "adjusted" levels

**Effort:** ~30 minutes · **Impact:** Medium (realistic expectations, better sizing)

---

### 2.3 Tighter AI Prompt with Scoring Rubric

**Problem:** AI decides "overextended" subjectively. Results vary between calls.

**Implementation:**

#### [MODIFY] `gemini_helper.py` → `evaluate_trade_quality()`

- Replace open-ended prompt with structured scoring rubric:

  ```
  Score each criterion (0-2):
  1. Trend alignment: 0=counter-trend, 1=neutral, 2=aligned
  2. Momentum state: 0=exhausted, 1=stable, 2=accelerating
  3. VWAP position: 0=overextended >0.3%, 1=moderate, 2=near VWAP
  4. Expansion phase: 0=late (>2x ATR), 1=mid, 2=early
  5. Structure quality: 0=choppy, 1=mixed, 2=clean HH-HL or LH-LL

  Total: X/10
  If total >= 6 → ACCEPT
  If total < 6 → RESTRICT
  confidence = total * 10
  ```

- This makes AI decisions **reproducible and auditable**

**Effort:** ~1 hour · **Impact:** High (consistent AI decisions)

---

## Phase 3 — Signal Quality (Week 3)

> _Better entries, fewer false signals._

---

### 3.1 Volume Confirmation for MODE_F

**Problem:** Gear 3 momentum triggers on large candles without checking if volume supports the move.

#### [MODIFY] `mode_f_engine.py`

- Add volume parameter to `predict()`:
  ```python
  volume_ok = candles[-1].get('volume', 0) > avg_volume_20 * 1.3
  if is_impulse and volume_ok:
      # Generate signal
  ```
- Gear 1 (Trend): require volume > average on breakout candle
- Gear 2 (Rotation): no volume requirement

**Effort:** ~1 hour · **Impact:** Medium

---

### 3.2 Time-of-Day Awareness for Gear Selection

**Problem:** Gear 3 at 2:30 PM is dangerous. Gear 1 in first 15 minutes is unreliable.

#### [MODIFY] `mode_f_engine.py`

- Add time-based gear restrictions:
  ```python
  TIME_GEAR_RULES = {
      (9, 15, 9, 30):   [Gear.GEAR_3_MOMENTUM],
      (9, 30, 12, 30):  [Gear.GEAR_1_TREND, Gear.GEAR_2_ROTATION, Gear.GEAR_3_MOMENTUM],
      (12, 30, 14, 0):  [Gear.GEAR_1_TREND, Gear.GEAR_2_ROTATION],
      (14, 0, 15, 30):  [Gear.GEAR_1_TREND],
  }
  ```

**Effort:** ~30 minutes · **Impact:** Medium

---

## Phase 4 — Analytics & Backtesting (Week 4)

> _Measure everything. Let data drive decisions._

---

### 4.1 Lightweight Backtest Runner

#### [NEW] `backtest_runner.py`

- Read historical candle data from Kite (or cached CSV)
- Simulate MODE_F signal engine with configurable thresholds
- Calculate: total PnL (R), win rate, max drawdown, Sharpe ratio
- Use same `rijin_config.py` thresholds

**Effort:** ~4-6 hours · **Impact:** High

---

### 4.2 Performance Dashboard Endpoint

#### [MODIFY] `app.py`

- Add `/rijin/v3/performance` endpoint with 7-day/30-day stats
- Reads from SQLite trade journal (Phase 1.2)

#### [MODIFY] `dashboard.html`

- Add performance charts (win rate, P&L curve, gear breakdown)

**Effort:** ~3-4 hours · **Impact:** Medium

---

### 4.3 AI Decision Audit Trail

#### [NEW] `ai_audit.py`

- Analyze `ai_decisions` table vs `trades` table
- Track: good accepts, bad accepts, over-restricted, good restricts
- Output: AI filter net value in R-multiple

**Effort:** ~2 hours · **Impact:** High

---

## Phase 5 — Advanced Features (Future)

> _Once Phases 1-4 are solid, consider these._

- **5.1** Multi-Timeframe Confirmation (15m + 5m alignment)
- **5.2** Options Chain / PCR Integration
- **5.3** Auto-Execution Mode (Kite order placement, shadow mode first)
- **5.4** ML Model Replacement for MODE_F (requires 500+ labeled trades)
- **5.5** Webhook-Based Token Refresh via Telegram bot
- **5.6** MODE_DON Backtester (validate Donchian breakout stats pre-deployment)

---

## Priority Matrix

| #   | Feature                  | Effort  | Impact      | Priority | Status   |
| --- | ------------------------ | ------- | ----------- | -------- | -------- |
| ✅  | **MODE_DON Engine**      | 6+ hrs  | 🔴 Critical | **P0**   | **Done** |
| 1.1 | Daily Drawdown Breaker   | 30 min  | 🔴 Critical | **P0**   | Pending  |
| 1.2 | Trade Journal (SQLite)   | 2-3 hrs | 🔴 Critical | **P0**   | Pending  |
| 1.3 | Token Expiry Handling    | 1 hr    | 🟡 High     | **P1**   | Pending  |
| 2.1 | Dynamic Position Sizing  | 1-2 hrs | 🟡 Medium   | **P2**   | Pending  |
| 2.2 | Slippage Buffer          | 30 min  | 🟡 Medium   | **P2**   | Pending  |
| 2.3 | AI Prompt Scoring Rubric | 1 hr    | 🟡 High     | **P1**   | Pending  |
| 3.1 | Volume Confirmation      | 1 hr    | 🟡 Medium   | **P2**   | Pending  |
| 3.2 | Time-of-Day Gears        | 30 min  | 🟡 Medium   | **P2**   | Pending  |
| 4.1 | Backtest Runner          | 4-6 hrs | 🟡 High     | **P1**   | Pending  |
| 4.2 | Performance Dashboard    | 3-4 hrs | 🟢 Medium   | **P3**   | Pending  |
| 4.3 | AI Decision Audit        | 2 hrs   | 🟡 High     | **P1**   | Pending  |

---

## Recommended Execution Order

```
Done:    MODE_DON (config + engine + runner + dashboard + guide)
Week 1:  1.1 (drawdown breaker) → 1.2 (trade journal) → 1.3 (token handling)
Week 2:  2.3 (AI rubric) → 2.1 (position sizing) → 2.2 (slippage)
Week 3:  3.1 (volume) → 3.2 (time gears) → 4.1 (backtester)
Week 4:  4.3 (AI audit) → 4.2 (dashboard) → 5.6 (MODE_DON backtester)
```

> **Rule: Never skip Phase 1.** The trade journal is the foundation — everything else depends on having data.

---

_Plan updated: March 2, 2026_
_System: RIJIN v3.0.1 + MODE_DON_
_MODE_DON Status: ✅ Production-ready_
