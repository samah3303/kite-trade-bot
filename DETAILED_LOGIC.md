# KiteAlerts — DETAILED LOGIC DOCUMENT

> **Version**: RIJIN v3.0.1 + Unified Engine  
> **Last Updated**: 2026-02-21  
> **Philosophy**: Signals generate opportunity. Context decides permission. Capital protection is the alpha.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [File Map & Responsibilities](#2-file-map--responsibilities)
3. [app.py — Flask Dashboard & Bot Selector](#3-apppy--flask-dashboard--bot-selector)
4. [unified_engine.py — Multi-Instrument Strategy Engine](#4-unified_enginepy--multi-instrument-strategy-engine)
5. [mode_f_engine.py — MODE F (NIFTY 3-Gear Engine)](#5-mode_f_enginepy--mode-f-nifty-3-gear-engine)
6. [mode_s_engine.py — MODE S (SENSEX)](#6-mode_s_enginepy--mode-s-sensex)
7. [mode_d_helpers.py — MODE D (Opening Drive)](#7-mode_d_helperspy--mode-d-opening-drive)
8. [RIJIN System — Context-Aware Execution Layer](#8-rijin-system--context-aware-execution-layer)
9. [rijin_config.py — Configuration & Thresholds](#9-rijin_configpy--configuration--thresholds)
10. [rijin_engine.py — Core RIJIN Components](#10-rijin_enginepy--core-rijin-components)
11. [rijin_live.py — Live Trading Engine](#11-rijin_livepy--live-trading-engine)
12. [rijin_live_runner.py — Dashboard Integration Wrapper](#12-rijin_live_runnerpy--dashboard-integration-wrapper)
13. [rijin_runner.py — RIJIN Integrated Runner (v2.3)](#13-rijin_runnerpy--rijin-integrated-runner-v23)
14. [Backtesting Framework](#14-backtesting-framework)
15. [Utility Modules](#15-utility-modules)
16. [End-to-End Signal Flow](#16-end-to-end-signal-flow)
17. [Risk Management Summary](#17-risk-management-summary)

---

## 1. Architecture Overview

The system is a **multi-strategy, context-aware Indian market trading bot** that:

- Connects to **Zerodha Kite Connect** for live market data (5m and 30m candles).
- Runs **multiple signal-generation strategies** (Mode A/B/C/D/F/S) across NIFTY, SENSEX, Gold Guinea, and BankNifty.
- Applies the **RIJIN system** as a permission/gate layer that filters signals based on day type, market phase, exhaustion, and correlation.
- Sends trade alerts (allowed/blocked) via **Telegram**.
- Optionally uses **Gemini AI** for sentiment analysis and post-trade review.
- Provides a **Flask web dashboard** for starting/stopping the bot and viewing logs.

### Two Operating Modes

| Mode        | Entry Point                           | Description                                                          |
| ----------- | ------------------------------------- | -------------------------------------------------------------------- |
| **Unified** | `unified_engine.py` → `UnifiedRunner` | Original multi-instrument engine with Mode A/B/C/D + Mode F + Mode S |
| **RIJIN**   | `rijin_live.py` → `RijinLiveEngine`   | v3.0.1 impulse-based engine focused on NIFTY with full gate system   |

The active mode is selected by the `USE_RIJIN_SYSTEM` environment variable in `.env`.

---

## 2. File Map & Responsibilities

| File                        | Role                                                                                                                                                                           |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `app.py`                    | Flask dashboard, login flow, bot start/stop, API endpoints                                                                                                                     |
| `unified_engine.py`         | Main multi-instrument engine: NiftyStrategy, GoldStrategy, BankNiftyStrategy, UnifiedRunner                                                                                    |
| `mode_f_engine.py`          | MODE F: 3-gear NIFTY signal generator (Trend / Rotation / Momentum)                                                                                                            |
| `mode_s_engine.py`          | MODE S: SENSEX strategy with CORE / STABILITY / LIQUIDITY buckets                                                                                                              |
| `mode_d_helpers.py`         | MODE D: Opening Drive helper methods (standalone version)                                                                                                                      |
| `rijin_config.py`           | All RIJIN configuration: day types, thresholds, gate parameters, templates                                                                                                     |
| `rijin_engine.py`           | RIJIN core classes: DayTypeEngine, ImpulseDetectionEngine, TrendPhaseEngine, ExecutionGates, OpeningImpulseTracker, CorrelationBrake, SystemStopManager, ModePermissionChecker |
| `rijin_live.py`             | RIJIN v3.0.1 live trading engine with main loop                                                                                                                                |
| `rijin_live_runner.py`      | Thread-based wrapper for Flask dashboard integration                                                                                                                           |
| `rijin_runner.py`           | RIJIN v2.3 integrated runner wrapping MODE_F + MODE_S                                                                                                                          |
| `backtest_rijin.py`         | RIJIN backtesting framework with results tracking and CSV export                                                                                                               |
| `backtest_unified.py`       | Unified engine backtesting: fetches Kite data, simulates Mode F/S                                                                                                              |
| `gemini_helper.py`          | Google Gemini AI integration for trade analysis and post-trade review                                                                                                          |
| `global_market_analyzer.py` | Global Market Analysis Module (GMAM): fetches S&P500, Nasdaq, VIX, DXY, etc. via yfinance                                                                                      |
| `get_access_token.py`       | CLI utility to obtain and save Kite Connect access token                                                                                                                       |
| `test_telegram.py`          | Diagnostic script to verify Telegram bot credentials                                                                                                                           |
| `example_daily_limit.py`    | Code snippet showing how to add daily signal caps                                                                                                                              |

---

## 3. app.py — Flask Dashboard & Bot Selector

### Bot Selection Logic

```
if USE_RIJIN_SYSTEM == "true":
    → import rijin_live_runner as active_bot
    → bot_mode = "RIJIN v3.0.1"
else:
    → use unified_engine.runner (UnifiedRunner)
    → bot_mode = "UNIFIED"
```

### Routes

| Route                        | Method | Description                                                      |
| ---------------------------- | ------ | ---------------------------------------------------------------- |
| `/`                          | GET    | Dashboard HTML page                                              |
| `/login`                     | GET    | Redirect to Zerodha Kite login URL                               |
| `/callback`                  | GET    | Handle OAuth callback, save `access_token` to `.env`             |
| `/start`                     | POST   | Start the active bot engine in a background thread               |
| `/stop`                      | POST   | Send stop signal to the active bot engine                        |
| `/status`                    | GET    | Return JSON with `running` and `mode`                            |
| `/logs`                      | GET    | Return last 5000 chars of captured stdout                        |
| `/rijin/day-type`            | GET    | Current day type classification (RIJIN only)                     |
| `/rijin/stats`               | GET    | System stop state, consecutive blocks, active trades             |
| `/rijin/config`              | GET    | Return execution gates, impulse config, correlation brake config |
| `/rijin/v3/live-stats`       | GET    | Real-time RIJIN v3.0.1 stats                                     |
| `/rijin/v3/backtest-results` | GET    | Hardcoded summary of latest backtest                             |

### Log Capture

All `print()` output is intercepted by a `LogCatcher` class that writes to both `sys.__stdout__` and a `StringIO` buffer, which is served at `/logs`.

---

## 4. unified_engine.py — Multi-Instrument Strategy Engine

### Technical Indicator Functions

| Function                                        | Purpose                                                     |
| ----------------------------------------------- | ----------------------------------------------------------- |
| `simple_ema(data, period)`                      | Exponential Moving Average calculation                      |
| `calculate_rsi(data, period=14)`                | Wilder's RSI with smoothed averages                         |
| `calculate_atr(highs, lows, closes, period=14)` | Average True Range using EMA smoothing                      |
| `get_slope(series, lookback=3)`                 | Slope as difference between current and N-candles-ago value |
| `detect_patterns(candles, ema20, atr)`          | Detects: Inside Bar, Impulse, EMA Touch, Consolidation      |
| `send_telegram_message(message)`                | POST to Telegram Bot API with HTML parse mode               |

### NiftyStrategy (Lines 163–655)

The primary NIFTY strategy with 4 trading modes:

#### State Machine

- **TrendState**: BULLISH / BEARISH / NEUTRAL (determined from 30m timeframe)
- **LegState**: INITIAL → NEW → CONFIRMED → EXHAUSTED

#### 30m Trend Detection (`update_trend_30m`)

```
BULLISH: Price > EMA20 > EMA50  AND  slope > 0  AND  ATR > ATR_MA20
BEARISH: Price < EMA20 < EMA50  AND  slope < 0  AND  ATR > ATR_MA20
```

On trend change: reset to `LegState.NEW`, clear mode A/B fired flags.  
After 10 candles in NEW: transition to `LegState.CONFIRMED`.

#### Day Type Classification (`classify_day_type`)

Classifies as TREND / RANGE / CHOP based on:

- ATR flat/falling on 30m (last 3 candles)
- EMA20 range < 0.3% on 30m
- Mixed candle directions in first 6 today's candles

**CHOP** days block MODE D.

#### MODE A — Fresh Trend Reclaim (LegState = NEW)

- Fires **once** per trend leg
- Checks freshness: out of last 10 candles, ≤3 above EMA and ≥1 below (for BUY)
- BUY: Price > EMA20, body ≥ 60% of range, RSI 56–72
- SELL: Price < EMA20, body ≥ 60% of range, RSI 28–44
- SL: 1.2× ATR | Target: 2.0× ATR
- Transitions to `LegState.CONFIRMED`

#### MODE B — Pullback Rejection (LegState = CONFIRMED)

- Re-entry allowed every 2 candles (tracked via `last_mode_b_idx`)
- Three pullback types checked (any one can trigger):
  1. **Depth-based**: Distance from extreme to recent low is 0.05–0.5× ATR
  2. **Time-based**: Last 4 candles all within 0.3× ATR of EMA20
  3. **Hold Breakout**: 5 consecutive candles above EMA20, then new high
- Rejection confirmation: Lower wick > 2× upper wick, or close above prior candle high
- BUY RSI: 52–65 | SELL RSI: 35–48
- SL: 1.0× ATR | Target: 1.5R

#### MODE C — Breakout/Momentum (LegState = CONFIRMED or early)

- **Early Enable**: LegState = NEW + 3 consecutive candles on right side of EMA20
- Max 2 consecutive losses before disabling for the day
- Three trigger conditions (any one):
  1. **Volatility expansion**: ATR > 0.95× ATR_MA and slope > 1.2× average
  2. **Micro Range Break**: Last 5 candles range < 0.6× ATR
  3. **Midday Compression** (12:00–13:30): Last 5 candles range < 0.7× ATR
- Patterns: EMA Touch, Inside Bar Break, Micro Range Break
- BUY RSI: 45–68 | SELL RSI: 32–55
- SL: 0.8× ATR | Target: 1.2R

#### MODE D — Opening Drive (09:20–10:30)

- Max 1 trade per day, not on CHOP days
- **Eligibility** (all must pass):
  1. Day Type ≠ CHOP
  2. Opening Range (first 3 candles) ≥ 0.50× ATR
  3. ≥2 of 3 candles same direction
  4. Each candle body ≥ 50% of range
  5. Global bias not opposing
  6. EMA20 slope aligns with direction
  7. RSI: BUY ≥ 52 / SELL ≤ 48
- **Entry**: Conservative pullback — wait for price to touch/cross EMA20 then reject back
- SL: max(Opening Range low, Entry − 1.0× ATR) for BUY
- Target: 1.5R

#### ORB (Opening Range Breakout) — 09:30–10:30

- Integrated into Mode C logic
- BUY when bullish trend + price breaks above Opening Range high
- SL: 0.5× ATR | Target: 1.5R (BUY) / 1.2R (SELL)

#### Daily Limits

- Max 7 trades per day
- Stop if daily P&L ≤ −1.5R
- Stop if ATR < 5.0

### GoldStrategy (Lines 660–766)

- Gold Guinea on MCX
- Trading hours: 14:00–23:30
- Mode A & B disabled; only Mode C (Expansion)
- Requires: Non-neutral 30m trend, EMA separation ≥ 0.20%, ATR rising, slope > 0.5
- BUY: Breakout above last 5 highs + price > EMA20
- SL: Recent low (min 0.5× ATR) | Target: 2.0R

### BankNiftyStrategy (Lines 771–953)

- Higher volatility version of NiftyStrategy
- Same Mode A/B/C structure, tuned for BankNifty volatility
- Mode C disabled after 2 consecutive losses
- Daily limits: 5 trades, P&L ≤ −2.0R

### UnifiedRunner (Lines 960–1334)

The main execution loop that orchestrates everything:

#### Initialization

- Creates strategy instances: `NiftyStrategy`, `BankNiftyStrategy`, `GoldStrategy`
- Creates `ModeFEngine` and `ModeSEngine` instances
- Initializes `GlobalMarketAnalyzer` (if available)
- Sets up Kite Connect with API credentials

#### Main Loop (`run_loop`)

1. Connect to Kite, fetch instrument tokens
2. Run Global Market Analysis at login, 12:30, and 12:45 IST
3. Every 10 seconds:
   - Process NIFTY (NiftyStrategy + ModeFEngine)
   - Process SENSEX (ModeSEngine)
   - Process Gold Guinea (GoldStrategy)

#### `process_instrument` Flow

1. Fetch 5m candles (last 3 days) and 30m candles (last 7 days)
2. Update 30m trend via strategy's `update_trend_30m()`
3. Check if new 5m candle (avoid duplicate processing)
4. Run **Mode F** (NIFTY only): `mode_f_engine.predict(c5, global_bias)`
5. Run **Mode S** (SENSEX only): `mode_s_engine.analyze(c5)`
6. Run strategy's `analyze_5m()` for Mode A/B/C/D signals
7. If signal found:
   - Run **Gemini AI** analysis (if enabled)
   - Format Telegram message with all details
   - Record to signal log

#### Telegram Message Format

Signals include: instrument, direction, mode, pattern, entry, SL, target, RSI, ATR, trend state, AI analysis (if available), and timestamp.

---

## 5. mode_f_engine.py — MODE F (NIFTY 3-Gear Engine)

Standalone NIFTY signal generator with **gear-based architecture** selecting logic based on volatility regime.

### Volatility Regime Classification

| Regime  | ATR as % of Price      | Description         |
| ------- | ---------------------- | ------------------- |
| LOW     | < 0.10% (< 24 pts)     | Very quiet market   |
| NORMAL  | 0.10–0.25% (24–60 pts) | Standard conditions |
| HIGH    | 0.25–0.40% (60–96 pts) | Elevated volatility |
| EXTREME | > 0.40% (> 96 pts)     | Event/shock driven  |

### Dominance Detection

Last 3 candles: if more green → BUYERS, else → SELLERS.

### Gear Selection & Signals

#### 🔵 GEAR 1: Structure Trend (LOW / NORMAL vol)

**Long Setup:**

- Price > EMA20 > EMA50
- Dominance = BUYERS
- Low near EMA20 (within 0.05%)
- Not RISK_OFF bias
- SL: min(Low, EMA20 − ATR) | Target: +2× ATR

**Short Setup:**

- Price < EMA20 < EMA50
- Dominance = SELLERS
- High near EMA20
- Not RISK_ON bias
- SL: max(High, EMA20 + ATR) | Target: −2× ATR

#### 🟡 GEAR 2: Structure Rotation (NORMAL / HIGH vol)

- Flat EMA20 slope (< 0.5× ATR over 5 candles)
- Bollinger-like bands: EMA20 ± 2× ATR
- **BUY**: Low below lower band, close above it, buyers dominant
- **SELL**: High above upper band, close below it, sellers dominant
- Target: EMA20 (mean reversion) | SL: Extreme ± 0.2× ATR

#### 🔴 GEAR 3: Volatility Momentum (HIGH / EXTREME vol)

- Impulse candle: body > 1.5× ATR
- **BUY**: Green impulse + buyers dominant
- **SELL**: Red impulse + sellers dominant
- SL: ±1× ATR | Target: ±1.5× ATR (scalp)

### Response Object (`ModeFResponse`)

Contains: `valid`, `direction`, `gear`, `reason`, `entry`, `sl`, `target`, `regime`.

---

## 6. mode_s_engine.py — MODE S (SENSEX)

SENSEX-specific strategy guaranteeing **≥ 5 calls/day** through a bucket escalation system.

### Bucket Architecture

| Bucket        | Priority          | Activation               | Logic                                |
| ------------- | ----------------- | ------------------------ | ------------------------------------ |
| **CORE**      | 1 (always active) | Always                   | Trend following (EMA20/50 alignment) |
| **STABILITY** | 2                 | After 13:30 if < 3 calls | VWAP mean reversion (0.3% deviation) |
| **LIQUIDITY** | 3                 | After 14:45 if < 5 calls | Day high/low breakout/breakdown      |

### CORE Logic

- **BUY**: Price > EMA20 > EMA50, low touches EMA20, green candle
- **SELL**: Price < EMA20 < EMA50, high touches EMA20, red candle

### STABILITY Logic

- **BUY**: Price < VWAP − 0.3%, price > EMA20, green candle
- **SELL**: Price > VWAP + 0.3%, price < EMA20, red candle
- Risk factor: 0.8× (reduced reward)

### LIQUIDITY Logic

- **BUY**: Price > day high (breakout)
- **SELL**: Price < day low (breakdown)
- Risk factor: 0.6× (further reduced reward)

### SL/Target Calculation

- SL = structure level ± 0.5× ATR (minimum 0.5× ATR risk)
- Target = Entry + Risk × 1.5 × risk_factor

### Noise Control

Rejects signals if same direction and price within 0.5× ATR of last call.

---

## 7. mode_d_helpers.py — MODE D (Opening Drive)

Standalone helper file with MODE D eligibility and entry logic (also integrated into NiftyStrategy).

### Eligibility Conditions (all must pass)

1. Day Type ≠ CHOP
2. Global Bias not opposing
3. First 3 candles (09:15–09:30):
   - Range ≥ 0.50× ATR
   - ≥ 2 candles same direction
   - Body ≥ 60% of range
   - Wicks ≤ 40%
4. EMA20 slope aligns with direction by 3rd candle
5. RSI: SELL ≤ 45 / BUY ≥ 55

### Entry (Option B — Conservative Pullback)

- Time window: 09:20–10:30
- **BUY**: Wait for pullback to EMA20 (Low ≤ EMA20), then rejection (Close > EMA20, green candle)
- **SELL**: Wait for pullback to EMA20 (High ≥ EMA20), then rejection (Close < EMA20, red candle)
- SL: max(Opening Range low, Entry − 1.0× ATR) for BUY
- Target: 1.5R fixed

---

## 8. RIJIN System — Context-Aware Execution Layer

The RIJIN system sits **on top of** signal generators (Mode F/S) and acts as a permission layer.

### Core Principle

```
Signal Generators → Produce opportunity
RIJIN System     → Decides permission to execute
```

### Key Innovation: v3.0 Impulse-Based Timing

**Problem**: Earlier versions measured expansion from day extremes (high/low), which created timing errors — moves measured from first bar of day, not from where the directional move started.

**Solution**: v3.0 measures expansion from the **impulse origin** — the candle where significant directional movement begins.

---

## 9. rijin_config.py — Configuration & Thresholds

### Day Types (Enum)

| Day Type                 | Severity | Description                                             | Trading Allowed?            |
| ------------------------ | -------- | ------------------------------------------------------- | --------------------------- |
| `CLEAN_TREND`            | 1        | ATR expanding, RSI directional, EMA pullbacks respected | Full                        |
| `NORMAL_TREND`           | 2        | Direction exists but slower expansion                   | Full                        |
| `EARLY_IMPULSE_SIDEWAYS` | 3        | Big early move then compression                         | Limited (0-1 trades)        |
| `FAST_REGIME_FLIP`       | 4        | Morning trend reversed violently                        | 1 trade, stricter RSI       |
| `ROTATIONAL_EXPANSION`   | 5        | ATR expanding but structure unstable                    | 1 trade, tighter exhaustion |
| `RANGE_CHOPPY`           | 6        | VWAP magnet, flat EMAs, RSI whipsaws                    | Blocked                     |
| `LIQUIDITY_SWEEP_TRAP`   | 7        | Stop-hunt: expansion + immediate reversal               | HARD BLOCK (day locked)     |
| `VOLATILITY_SPIKE`       | 8        | Single candle > 0.7x ATR, 60% reversal                  | Blocked (30 min pause)      |
| `EXPIRY_DISTORTION`      | 8        | Expiry day after noon                                   | Blocked                     |

### Expiry Days

- NIFTY: Tuesday (weekday = 1)
- SENSEX: Thursday (weekday = 3)

### Day Type Check Schedule

Every 30 minutes from 10:00 to 14:30 IST, with 25-minute dedup window.

### Trading Cutoff

`14:30 IST` — No new trades after this time, only manage existing positions.

### Session Trend Phase (v3.0.1 Impulse-Based)

| Phase            | ATR Expansion  | Policy        | Conditions                                  |
| ---------------- | -------------- | ------------- | ------------------------------------------- |
| **EARLY**        | 0 – 1.2× ATR   | FULLY_ALLOWED | None                                        |
| **MID**          | 1.2 – 2.0× ATR | CONDITIONAL   | Pullback ≤ 0.5× ATR, RSI ≥ 50, HH-HL intact |
| **LATE**         | > 2.0× ATR     | DISABLED      | Move exhausted                              |
| **Absolute Max** | > 2.5× ATR     | HARD BLOCK    | No trades regardless                        |

### Execution Gate Thresholds

| Gate                          | Parameter      | Value                 |
| ----------------------------- | -------------- | --------------------- |
| Gate 1: Exhaustion            | ATR multiple   | 1.5×                  |
| Gate 1: Range %               | Day range      | 70%                   |
| Gate 2: Late cutoff + bad day | Time           | 12:30 IST             |
| Gate 3: RSI compression       | RSI range      | 48–62 for 10+ candles |
| Gate 3: Cluster protection    | Count / Window | 2 SLs within 45 min   |

### Consecutive Loss Protection (v3.0.1)

- Max 2 consecutive losses → **1 hour pause**
- Reset counter on any win

### Opening Impulse Window

- Time: 09:20–10:00 IST
- Min move: 0.4× ATR
- Max 1 trade per index, risk = 0.5R

### Correlation Brake

- Trigger: 2 SLs on Index A within 60 minutes
- Action: Block Index B for 60 minutes (prevents stacked drawdowns)

### System Stop Conditions (hard stop for the day)

1. Day type = RANGE_CHOPPY or LIQUIDITY_SWEEP_TRAP
2. 3 consecutive execution blocks
3. 2 stop losses after 11:30 IST

### Mode Permission Matrix

| Mode                    | Allowed Day Types                      | Time Cutoff          |
| ----------------------- | -------------------------------------- | -------------------- |
| MODE_F                  | Clean Trend, Normal Trend              | 14:00 on expiry days |
| MODE_F (conditional)    | Rotational Expansion (max 1 trade)     | 14:00 on expiry days |
| MODE_F (conditional)    | Fast Regime Flip (max 1, stricter RSI) | 14:00 on expiry days |
| MODE_S (Core/Stability) | Clean Trend, Normal Trend              | 13:30                |
| MODE_S (Liquidity)      | Clean Trend, Normal Trend              | 13:00                |

---

## 10. rijin_engine.py — Core RIJIN Components

### DayTypeEngine

**Purpose**: Classifies market days in real-time using 5m and 30m candle data.

**Classification Logic (v3.1 Priority Order)**:

- Tracks day stats: open time, first ATR, day high/low, VWAP
- Priority (dangerous first): Expiry Distortion -> Liquidity Sweep Trap -> Range/Choppy -> Rotational Expansion -> Fast Regime Flip -> Clean Trend -> Normal Trend -> Early Impulse -> default to Normal Trend

**Degradation Rules** (Day types only get worse, never better):

- Immediate downgrade (no confirmation): RANGE_CHOPPY, EXPIRY_DISTORTION, VOLATILITY_SPIKE, LIQUIDITY_SWEEP_TRAP
- Confirmation-based downgrade: Need 2 consecutive checks (~60 minutes) for gradual transitions
- Once RANGE_CHOPPY or LIQUIDITY_SWEEP_TRAP -> day is **locked** (no further changes)

**New Regime Detections (v3.1)**:

**Liquidity Sweep Trap**: Expansion candle > 1.2x ATR + immediate reversal > 0.8x ATR + opposite direction candle. Hard lock, all trades disabled.

**Rotational Expansion**: ATR expanding > 1.05x first ATR + RSI crossing EMA20 >= 3 times + VWAP crossovers >= 3 + at least 1 failed breakout. Max 1 trade, reduced exhaustion threshold.

**Fast Regime Flip**: Morning range > 1.5x ATR (first 12 candles) + recent range > 1.2x ATR (last 6 candles) + direction changed. Max 1 trade, RSI must be > 55 (buy) or < 45 (sell).

**Clean Trend Detection**:

- ATR expanding ≥ 1.05× of first ATR
- RSI directional (> 55 or < 45)
- ≤ 3 overlapping candles out of last 10
- ≥ 2 EMA20 touches in last 20 candles

**Range/Choppy Detection**:

- EMA20 slope flat (< 1.0)
- RSI crossing 50 level ≥ 3 times in 10 candles
- ATR contracting (< 0.7× of first ATR)

### ImpulseDetectionEngine (v3.0 Foundation)

**Purpose**: Detects where directional move actually STARTS, anchoring all expansion measurements.

**Bullish Impulse**:

1. 2 consecutive strong bullish candles
2. Each candle range > 0.6× ATR
3. Close breaks above prior swing high
4. EMA20 slope positive
5. Impulse origin = Low of first impulse candle

**Bearish Impulse**: Mirror logic, origin = High of first impulse candle.

**Expansion Calculation**: `|current_price - impulse_origin| / impulse_ATR`

### TrendPhaseEngine

**Purpose**: Prevents MODE_F from firing on exhausted moves by filtering BEFORE signal generation.

**Phase Determination**:

1. If impulse active → expansion from impulse origin
2. If no impulse → allow (fail-safe)
3. Map expansion to EARLY / MID / LATE (see config thresholds)

**MID Phase Conditions** (all must pass):

- Pullback ≤ 0.5× ATR from recent extreme
- RSI ≥ 50 (for BUY) or ≤ 50 (for SELL)
- Structure intact: Higher Lows (BUY) or Lower Highs (SELL) in last 3 candles

### ExecutionGates

All 3 gates must pass for every trade:

**Gate 1 — Move Exhaustion**:

- If impulse active: block if expansion > 1.5× ATR from impulse origin
- Fallback (no impulse): block if distance from day extreme > min(1.5× ATR, 70% of day range)

**Gate 2 -- Time + Day Type**:

- Block after 12:30 IST if day type is: Early Impulse Sideways, Range/Choppy, Expiry Distortion, Rotational Expansion, or Fast Regime Flip

**Gate 3 — RSI Compression**:

- Block if RSI stuck in 48–62 for ≥ 10 of last 10 candles AND ≥ 5 overlapping candles (inside bars)

### OpeningImpulseTracker

- Window: 09:20–10:00 IST
- Max 1 trade per instrument, 1 total if correlated
- Not on expiry days
- Conditions: Opening range ≥ 0.4× ATR, last candle body ≥ 65%, RSI > 60 or < 40

### CorrelationBrake

- Tracks SL history per instrument
- Trigger: 2 SLs on instrument A within 60 min, same direction AND day type, indices correlated
- Action: Block instrument B for 60 minutes
- Auto-clears expired blocks

### SystemStopManager

Activates hard stop when:

1. Day type = RANGE_CHOPPY or LIQUIDITY_SWEEP_TRAP
2. 3 consecutive execution blocks
3. 2 SLs after 11:30 IST

Once stopped, stays stopped for rest of day. Can be force-stopped manually.

### ModePermissionChecker

Static checks verifying mode is allowed given current context:

- **MODE_F**: Day type must be Clean/Normal Trend. Conditionally allowed on Rotational Expansion (max 1) and Fast Regime Flip (max 1, stricter RSI). Blocked in late expiry phase (after 14:00).
- **MODE_S Core**: Day type must be Clean/Normal Trend. Cutoff at 13:30.
- **MODE_S Liquidity**: Day type must be Clean/Normal Trend. Cutoff at 13:00. No forced trades on hostile days (including new regimes).

---

## 11. rijin_live.py — Live Trading Engine

### RijinLiveEngine — Complete Live System

**Configuration**:

- Capital: Rs.1,00,000
- Risk per trade: 1% (= Rs.1,000 per R)
- Instrument: NIFTY Future

**Daily Reset** (on new date):

- Reset impulse engine, day type engine, system stop
- Reset trade counters, consecutive losses, pause
- Send Telegram start-of-day notification

**Main Loop** (every 30 seconds):

```
1. Check if new day → reset
2. If outside 09:15–15:30 → sleep
3. Fetch 5m candles from Kite
4. Calculate indicators (EMA20, ATR14, RSI14)
5. Detect impulse
6. If active trade → check exits (every 10 sec)
7. If system stopped → wait 5 min
8. Every 5 minutes → generate MODE_F signal
9. If signal → apply RIJIN gates
10. If allowed → execute trade + Telegram alert
11. If blocked → log reason
```

**Gate Application Order (v3.1)**:

1. Consecutive loss pause check
2. **Regime hard blocks** (LIQUIDITY_SWEEP_TRAP blocks all, ROTATIONAL_EXPANSION / FAST_REGIME_FLIP cap at 1 trade + stricter RSI)
3. Phase Filter (impulse-based)
4. Gate 1: Move Exhaustion
5. Gate 2: Time + Day Type
6. Gate 3: RSI Compression
7. Mode Permission

**Trade Execution**:

- Position size = (Capital × 1%) / Risk
- Track active trade with entry time, quantity, SL, target
- Exit on SL or target hit

**Exit Logic**:

- TARGET → P&L positive, reset consecutive losses
- SL → Increment consecutive losses, register with system stop
- If consecutive losses ≥ 2 → pause for 60 minutes

---

## 12. rijin_live_runner.py — Dashboard Integration Wrapper

Thread-based wrapper for Flask dashboard integration:

- Exposes `start()`, `stop()`, `get_live_stats()` functions
- Creates `RijinLiveEngine` in background daemon thread
- Updates global dashboard stats from engine state
- Provides dummy compatibility objects for `day_type_engine`, `system_stop`, `opening_impulse`

---

## 13. rijin_runner.py — RIJIN Integrated Runner (v2.3)

Earlier version wrapping both MODE_F and MODE_S with RIJIN context:

**Multi-Instrument Processing**:

- NIFTY → Mode F signals
- SENSEX → Mode S signals
- Both processed through RIJIN gates

**RIJIN Execution Flow** (`rijin_execute`):

1. Gate 1: Move Exhaustion (simplified — candles not re-fetched)
2. Gate 2: Time + Day Type
3. Gate 3: RSI Compression (simplified)
4. Mode Permission (F or S with bucket check)
5. Correlation Brake (check other index SLs)
6. All pass → execute signal
7. Any fail → block + register with system stop

**Additional Features**:

- Opening impulse detection (09:20–10:00)
- Day type analysis every 30 min
- Trade exit monitoring (SL/Target on completed candles)
- Correlation brake registration on SL exits

---

## 14. Backtesting Framework

### backtest_rijin.py — RIJIN Backtest

**BacktestResults** class tracks:

- Day type classifications per date
- All signals (generated, allowed, blocked with reasons)
- Completed trades with P&L in R
- System stop events

**RijinBacktestEngine**:

- Fetches historical 5m data from Kite
- Groups by date, processes each day:
  1. Classify day type at 10:00 and 12:00
  2. For each 5m candle (09:20 onwards):
     - Detect impulse
     - Generate MODE_F signal
     - Apply RIJIN gates (v3.0.1 with consecutive loss protection)
     - If allowed → simulate trade (walk forward looking for SL/Target hit)
- Trade execution: 15-point fixed target (v3.0.1), SL from signal
- Exports results to CSV files

### backtest_unified.py — Unified Engine Backtest

- Fetches data from Kite for configurable date range
- Wraps ModeFEngine and ModeSEngine in adapter classes
- Processes each day candle-by-candle
- Records trades with P&L simulation (walk-forward)
- Generates performance summary: total P&L, win rate, max drawdown

---

## 15. Utility Modules

### gemini_helper.py — AI Trade Analysis

- Uses Google Gemini 2.0 Flash via REST API
- `analyze_market_sentiment()`: Evaluates trade setup → returns confidence score (1–10), risk level, action (Proceed/Caution/Skip), insight
- `analyze_exit_reason()`: Post-trade review → returns reason, lesson, verdict (Good Exit/Bad Luck/Premature)
- Exponential backoff retry (3 attempts) on 429 quota errors
- Falls back gracefully if API key missing

### global_market_analyzer.py — Global Market Context

Fetches via yfinance:

- US: S&P 500, Nasdaq
- Asia: Nikkei, Hang Seng
- Macro: VIX, DXY (Dollar Index), US 10Y Treasury, Crude Oil

**Scoring**:
| Factor | +1 | -1 |
|--------|----|----|
| S&P 500 / Nasdaq | Above EMA20 | Below EMA20 |
| VIX | Falling > 5% | Rising > 5% |
| DXY | Weak (< -0.5%) | Strong (> +0.5%) |
| US 10Y | Falling (< -2%) | Rising (> +2%) |
| Asia (avg) | Positive (> 0.5%) | Negative (< -0.5%) |

**Final Bias**: Score ≥ +2 → RISK_ON | Score ≤ −2 → RISK_OFF | else → NEUTRAL

**Usage**: RISK_OFF blocks MODE_D BUYs; RISK_ON blocks MODE_D SELLs.

### get_access_token.py

CLI script:

1. Opens Kite login URL in browser
2. Prompts for `request_token` from redirect URL
3. Generates session → obtains `access_token`
4. Auto-updates `.env` file

### test_telegram.py

Sends a diagnostic message to verify Telegram bot token and chat ID.

### example_daily_limit.py

Code pattern showing how to add daily signal caps (max 25 signals/day) to the UnifiedRunner.

---

## 16. End-to-End Signal Flow

### Unified Engine Flow

```
Market Data (Kite 5m/30m)
    │
    ▼
┌─────────────────────────┐
│   Global Market Analyzer │ ← yfinance (S&P, VIX, etc.)
│   → RISK_ON/OFF/NEUTRAL │
└──────────┬──────────────┘
           │
    ▼──────▼──────────────▼
┌─────────┐ ┌──────────┐ ┌────────────┐
│ NIFTY   │ │ SENSEX   │ │ GOLD       │
│ Strategy│ │ Mode S   │ │ Strategy   │
│ A/B/C/D │ │ Core/    │ │ Mode C     │
│ + Mode F│ │ Stab/Liq │ │            │
└────┬────┘ └────┬─────┘ └─────┬──────┘
     │           │              │
     └───────────┼──────────────┘
                 ▼
         ┌──────────────┐
         │ Gemini AI    │ (optional)
         │ Confidence   │
         └──────┬───────┘
                ▼
         ┌──────────────┐
         │ Telegram     │
         │ Alert        │
         └──────────────┘
```

### RIJIN v3.0.1 Flow

```
Market Data (Kite 5m)
    │
    ▼
┌────────────────────────────┐
│   Impulse Detection Engine │
│   → Detect impulse origin  │
└──────────┬─────────────────┘
           │
           ▼
┌────────────────────────────┐
│   Day Type Engine          │
│   → Classify day every 30m │
│   → Degradation only       │
└──────────┬─────────────────┘
           │
           ▼
┌────────────────────────────┐
│   MODE F Engine            │
│   → Generate signal        │
│   (Gear 1/2/3 based on vol)│
└──────────┬─────────────────┘
           │ Signal
           ▼
┌────────────────────────────────────────────┐
│           RIJIN GATE CHAIN                 │
│                                            │
│   1. Consecutive Loss Pause (60 min)       │
│   2. Phase Filter (Early/Mid/Late)         │
│   3. Gate 1: Move Exhaustion (1.5× ATR)    │
│   4. Gate 2: Time + Day Type               │
│   5. Gate 3: RSI Compression               │
│   6. Mode Permission                       │
│                                            │
│   ALL MUST PASS                            │
└──────────┬─────────────────────────────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
 ✅ ALLOWED   ❌ BLOCKED
     │           │
     ▼           ▼
  Execute     Log reason
  Trade       Telegram alert
  Telegram    Register block
```

---

## 17. Risk Management Summary

| Protection Layer           | Mechanism                                                            | Scope          |
| -------------------------- | -------------------------------------------------------------------- | -------------- |
| **Daily trade limit**      | Max 7 (Nifty), 5 (BankNifty)                                         | Per day        |
| **Daily P&L cap**          | Stop at −1.5R (Nifty), −2.0R (BankNifty)                             | Per day        |
| **Consecutive loss pause** | 2 losses → 60 min pause                                              | Per session    |
| **Day type degradation**   | Only worse, never better; locks at RANGE_CHOPPY/LIQUIDITY_SWEEP_TRAP | Per day        |
| **System stop**            | RANGE_CHOPPY, LIQUIDITY_SWEEP_TRAP, 3 blocks, or 2 SLs after 11:30   | Per day        |
| **Regime hard blocks**     | LIQUIDITY_SWEEP_TRAP=all blocked, ROTATIONAL/FLIP=max 1 trade        | Per day        |
| **Phase filter**           | Block LATE phase (> 2.0× ATR from impulse)                           | Per signal     |
| **Exhaustion gate**        | Block if > 1.5× ATR from impulse                                     | Per signal     |
| **RSI compression gate**   | Block if RSI stuck 48–62 for 10 candles                              | Per signal     |
| **Correlation brake**      | 2 SLs on Index A → block Index B for 60 min                          | Cross-index    |
| **Trading cutoff**         | No new trades after 14:30 IST                                        | Per day        |
| **Expiry intelligence**    | 30% signal reduction, no entries after 14:45                         | Per expiry day |
| **Mode C loss circuit**    | 2 consecutive Mode C losses → disable Mode C                         | Per day        |
| **Noise control**          | Reject duplicate signals within 0.5× ATR                             | Per signal     |
| **ATR minimum**            | No trades if ATR < 5.0                                               | Per signal     |
