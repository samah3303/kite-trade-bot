# 🧠 RIJIN Trading System — Project Overview

> **RIJIN v3.0.1** — An AI-filtered, automated intraday trading alert system for Indian markets, built on Zerodha's Kite Connect API.

---

## Table of Contents

- [Why?](#-why)
- [What?](#-what)
- [How?](#-how)
- [Architecture](#-architecture)
- [File Map](#-file-map)
- [Deployment](#-deployment)

---

## 💡 WHY?

### The Problem

Intraday trading in Indian equity markets (Nifty 50, Sensex) is brutally unforgiving. Retail traders face:

1. **Emotional Decision-Making** — Fear and greed override logic. A trader might hold a losing position too long or exit a winning one too early.
2. **Signal Overload** — Technical indicators generate dozens of signals daily. Most are noise. Without a filtering mechanism, traders overtrade and bleed capital.
3. **No Capital Protection** — Markets change character mid-session. A trending morning can turn choppy by noon. Traders who keep firing signals get chopped up.
4. **Late-Cycle Exhaustion Traps** — The most dangerous mistake: entering a trend after it has already moved 2–3× ATR. The move looks "obvious" but is already exhausted — instant SL hit.
5. **Manual Monitoring is Impractical** — Watching 5-minute candles across multiple timeframes, calculating RSI/EMA/ATR in real time, and making split-second decisions is humanly unsustainable.

### The Philosophy

> _"Signals generate opportunity. Context decides permission. Capital protection is the alpha."_

The system was built with one core belief: **the best trade is the one you don't take**. Rather than maximizing signals, RIJIN maximizes _quality_ — using a layered filter architecture that only allows trades when the market structure, session timing, and AI validation all agree.

### Why AI Filtering?

Traditional rule-based gates (v1–v2) worked but were rigid. Markets evolve. The v3.0.1 architecture introduces an **AI validator layer** (via Groq/Llama 3.3 70B) that evaluates trade quality based on 17+ market context parameters — effectively adding an institutional-grade risk manager that never sleeps, never panics, and never revenge-trades.

---

## 📦 WHAT?

### System Identity

| Attribute          | Value                                            |
| ------------------ | ------------------------------------------------ |
| **Name**           | RIJIN System v3.0.1                              |
| **Type**           | Automated Intraday Trading Alert Bot             |
| **Market**         | Indian Equities (NSE/BSE)                        |
| **Instruments**    | Nifty 50 (primary), Sensex (secondary)           |
| **Timeframe**      | 5-minute candles, 30-minute trend confirmation   |
| **Broker**         | Zerodha (via Kite Connect API)                   |
| **AI Provider**    | Groq (Llama 3.3 70B) for trade quality filtering |
| **Alert Delivery** | Telegram Bot                                     |
| **Dashboard**      | Flask Web UI                                     |
| **Deployment**     | Render.com (cloud) / Oracle Cloud (self-hosted)  |

### What Does It Do?

```
Market Data  →  Indicator Calculation  →  Signal Engine  →  AI Validator  →  Telegram Alert
  (Kite)         (EMA, RSI, ATR,          (MODE_F          (Groq LLM        (BUY/SELL
                  VWAP, Slope)             3-Gear)          ACCEPT/RESTRICT)   with Entry/SL/Target)
```

1. **Fetches live 5-minute candlestick data** from Zerodha Kite every 30 seconds.
2. **Calculates technical indicators**: EMA(20), EMA(50), ATR(14), RSI(14), VWAP, EMA Slope.
3. **Runs the MODE_F 3-Gear Signal Engine** to detect potential trade setups.
4. **Passes signals through the AI Validator** with full market context (17+ parameters).
5. **Sends Telegram alerts** for accepted signals, including Entry, SL, Target, RR ratio, AI confidence, and reasons.
6. **Monitors active trades** for SL/Target exits and sends close alerts.

### What It Does NOT Do

- ❌ **Does NOT execute trades automatically** — It sends alerts only. The trader places orders manually.
- ❌ **Does NOT predict market direction** — The AI only evaluates trade _quality_, not direction.
- ❌ **Does NOT modify entry/SL/target** — The AI cannot change signal parameters. It can only ACCEPT or RESTRICT.

### Trading Modes

#### MODE_F — Primary Signal Engine (3-Gear)

| Gear       | Name                | Condition               | Strategy                                                   |
| ---------- | ------------------- | ----------------------- | ---------------------------------------------------------- |
| **Gear 1** | Structure Trend     | Low/Normal volatility   | Trend-following pullback entries near EMA20                |
| **Gear 2** | Structure Rotation  | Normal/High volatility  | Mean-reversion at Bollinger-like bands (±2 ATR from EMA20) |
| **Gear 3** | Volatility Momentum | High/Extreme volatility | Impulse breakout scalps on large-body candles (>1.5× ATR)  |

#### MODE_S — Sensex Engine

A separate Sensex-specific engine with 3 trade buckets:

- **CORE** — High-conviction trend pullbacks (always active)
- **STABILITY** — VWAP mean-reversion (activates after 1:30 PM if under 3 trades)
- **LIQUIDITY** — Day-high/low breakout/breakdown (activates after 2:45 PM if under 5 trades)

#### Legacy Modes (Unified Engine)

The `unified_engine.py` contains earlier strategies (MODE_A through MODE_D) for Nifty, Bank Nifty, and Gold — superseded by RIJIN v3.0.1 but retained for reference.

### Safety & Capital Protection Systems

| System                       | Purpose                                                                                                    |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------- |
| **Day Type Classification**  | Classifies market into 9 types (Clean Trend → Liquidity Sweep Trap). Only allows trades on favorable days. |
| **Session Trend Phase**      | Tracks expansion from impulse origin. Blocks "late" entries (>2× ATR expansion).                           |
| **Execution Gates (3-Gate)** | Gate 1: Move exhaustion. Gate 2: Time + day type. Gate 3: RSI compression.                                 |
| **Consecutive Loss Pause**   | 2 losses in a row → 60-minute pause.                                                                       |
| **Correlation Brake**        | 2 SLs on Nifty → blocks Sensex for 60 min (and vice versa).                                                |
| **System Stop**              | Halts all trading if: choppy day detected, 3 consecutive blocks, or 2 SLs after 11:30 AM.                  |
| **Expiry Intelligence**      | Reduces signals 30% on expiry days, no new entries after 2:45 PM.                                          |
| **Stale Data Rejection**     | Skips processing if last candle is >7 minutes old.                                                         |

### Day Type Classification (9 Types)

| #   | Day Type                 | Severity  | Trading Allowed?           |
| --- | ------------------------ | --------- | -------------------------- |
| 1   | Clean Trend Day          | Lowest    | ✅ Full trading            |
| 2   | Normal Trend Day         | Low       | ✅ Full trading            |
| 3   | Early Impulse → Sideways | Medium    | ⚠️ Max 1 trade             |
| 4   | Fast Regime Flip         | Medium    | ⚠️ Max 1 trade             |
| 5   | Rotational Expansion     | High      | ⚠️ Max 1 trade             |
| 6   | Range / Choppy           | High      | ❌ All blocked             |
| 7   | Liquidity Sweep Trap     | Very High | ❌ All blocked, day locked |
| 8   | Expiry Distortion        | Highest   | ❌ All blocked             |
| 8   | Volatility Spike         | Highest   | ❌ All blocked             |

> **Degradation is one-way only** — a day can only get _worse_, never better. Once classified as "Range/Choppy", the day is locked.

---

## ⚙️ HOW?

### Tech Stack

| Layer             | Technology                                   |
| ----------------- | -------------------------------------------- |
| **Language**      | Python 3.13                                  |
| **Web Framework** | Flask + Gunicorn                             |
| **Broker API**    | Zerodha Kite Connect (`kiteconnect`)         |
| **AI/LLM**        | Groq API (Llama 3.3 70B Versatile) via REST  |
| **Indicators**    | NumPy (custom EMA, ATR, RSI implementations) |
| **Global Data**   | Yahoo Finance (`yfinance`)                   |
| **Notifications** | Telegram Bot API                             |
| **Config**        | python-dotenv (`.env` file)                  |
| **Timezone**      | IST (Asia/Kolkata) via `pytz`                |
| **Deployment**    | Render.com (Starter plan, always-on)         |

### Authentication Flow

```
User  →  /login  →  Zerodha Login Page  →  /callback  →  Access Token saved to .env
                                                            ↓
                                              Bot starts with token
```

1. User opens the Flask dashboard and clicks **Login**.
2. Flask redirects to Zerodha's OAuth login page.
3. User authenticates; Zerodha redirects back to `/callback` with a `request_token`.
4. Flask exchanges the `request_token` for an `access_token` and saves it in `.env`.
5. The bot uses this token for all Kite API calls (historical data, LTP).

> **Note:** Access tokens expire daily. A utility script `get_access_token.py` can also generate tokens manually via CLI.

### Main Trading Loop (Simplified)

```python
while not stop_event:
    # 1. Check trading hours (09:15 - 15:30 IST)
    # 2. Fetch 5-minute candles from Kite
    # 3. Reject stale data (>7 min old)

    # LAYER 1: Feature Extraction
    indicators = calculate_indicators(candles)  # EMA20, ATR14, RSI14, Slope

    # LAYER 2: Signal Engine (MODE_F)
    signal = mode_f_engine.predict(candles, global_bias)

    if signal:
        # Build 17-parameter market context
        market_context = build_market_context(candles, indicators)

        # LAYER 3: AI Validator
        ai_result = gemini.evaluate_trade_quality(market_context, signal)

        if ai_result['decision'] == 'ACCEPT':
            # LAYER 4: Telegram Alert
            send_telegram_alert(signal, ai_result)
        else:
            send_telegram_restricted_alert(signal, ai_result)

    sleep(30)
```

### AI Validation — How It Works

The AI receives a structured JSON payload with:

**Market Context (17 parameters):**
| Parameter | Example | Purpose |
|---|---|---|
| `time` | `"11:30"` | Session timing |
| `session_phase` | `"Midday"` | Opening/Morning/Midday/Afternoon/Closing |
| `day_type` | `"Trending"` | Narrow Range / Normal Range / Trending / Expansion |
| `trend` | `"Bullish"` | Bullish / Bearish / Sideways |
| `price_vs_vwap_pct` | `0.15` | Premium/discount to VWAP |
| `rsi` | `58` | RSI(14) |
| `rsi_slope` | `"Rising"` | Rising / Flat / Falling |
| `expansion_legs` | `3` | Number of directional legs |
| `current_leg_vs_avg` | `1.2` | Current leg size vs average |
| `volatility_state` | `"Normal"` | Contracting / Normal / Expanding |
| `structure_last_5` | `"HH-HL continuation"` | Price structure |
| `pullback_depth_pct` | `25` | Pullback as % of swing |
| `volume_vs_avg` | `1.3` | Volume relative to average |

**Signal Data:**

```json
{
  "direction": "LONG",
  "entry": 24150,
  "sl": 24120,
  "rr": "1:2"
}
```

**AI Response:**

```json
{
  "decision": "ACCEPT",
  "confidence": 78,
  "reasons": [
    "Trade aligned with primary bullish trend",
    "Momentum supportive with rising RSI",
    "Price near VWAP — not overextended"
  ]
}
```

> On AI failure, the system **defaults to ACCEPT** (fail-open design) — the signal engine's own filters are trusted as the primary safeguard.

### Environment Variables

| Variable             | Required | Description                                       |
| -------------------- | -------- | ------------------------------------------------- |
| `KITE_API_KEY`       | ✅       | Zerodha API key                                   |
| `KITE_API_SECRET`    | ✅       | Zerodha API secret                                |
| `KITE_ACCESS_TOKEN`  | ✅       | Daily access token (auto-updated)                 |
| `TELEGRAM_BOT_TOKEN` | ✅       | Telegram bot token                                |
| `TELEGRAM_CHAT_ID`   | ✅       | Telegram chat ID for alerts                       |
| `GROQ_API_KEY`       | ✅       | Groq API key for AI filtering                     |
| `NIFTY_INSTRUMENT`   | ❌       | Instrument string (default: `NSE:NIFTY 50`)       |
| `USE_RIJIN_SYSTEM`   | ❌       | Set `true` to use RIJIN v3.0.1 (default: `false`) |
| `FLASK_SECRET_KEY`   | ❌       | Flask session secret                              |

### Running Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure .env (copy from .env.example)
cp .env.example .env
# Edit .env with your API keys

# 3. Generate access token
python get_access_token.py

# 4. Start the dashboard
python app.py
# → Opens at http://localhost:5000

# 5. Start/stop bot from dashboard or hit:
# POST /start  → starts the engine
# POST /stop   → stops the engine
```

### Deploying to Render

The `render.yaml` blueprint handles everything:

```yaml
services:
  - type: web
    name: kite-alerts
    runtime: python
    plan: starter # $7/mo, always-on
    healthCheckPath: /status
    startCommand: gunicorn app:app --workers 1 --threads 4 --timeout 120
```

1. Push code to GitHub.
2. Connect repo on [Render.com](https://render.com).
3. Add environment variables in the Render dashboard.
4. Deploy — the bot starts automatically.

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    FLASK DASHBOARD (app.py)                   │
│  /login  /callback  /start  /stop  /status  /logs            │
│  /rijin/stats  /rijin/v3/live-stats  /rijin/v3/backtest      │
└──────────────────┬───────────────────────────────────────────┘
                   │ starts/stops
                   ▼
┌──────────────────────────────────────────────────────────────┐
│              rijin_live_runner.py (Thread Wrapper)            │
│  start() → spawns background thread                          │
│  stop()  → sets stop_event                                   │
│  get_live_stats() → dashboard JSON                           │
└──────────────────┬───────────────────────────────────────────┘
                   │ creates
                   ▼
┌──────────────────────────────────────────────────────────────┐
│              rijin_live.py (RijinLiveEngine)                  │
│                                                              │
│  ┌──────────┐   ┌──────────────┐   ┌─────────────────┐      │
│  │ Kite API │──▶│ Indicator    │──▶│ MODE_F Engine    │      │
│  │ (candles)│   │ Calculation  │   │ (3-Gear Signal)  │      │
│  └──────────┘   └──────────────┘   └────────┬────────┘      │
│                                              │               │
│                                  ┌───────────▼──────────┐    │
│                                  │  Market Context JSON  │    │
│                                  │  (17 parameters)      │    │
│                                  └───────────┬──────────┘    │
│                                              │               │
│                                  ┌───────────▼──────────┐    │
│                                  │  AI Validator (Groq)  │    │
│                                  │  ACCEPT / RESTRICT    │    │
│                                  └───────────┬──────────┘    │
│                                              │               │
│                                  ┌───────────▼──────────┐    │
│                                  │  Telegram Alert       │    │
│                                  │  (Signal + AI result) │    │
│                                  └──────────────────────┘    │
└──────────────────────────────────────────────────────────────┘

Supporting Engines (rijin_engine.py — used by legacy path):
  ├── DayTypeEngine        — 9-type market classification
  ├── ImpulseDetectionEngine — Impulse origin tracking
  ├── TrendPhaseEngine     — EARLY/MID/LATE phase filtering
  ├── ExecutionGates       — 3-gate pre-trade validation
  ├── OpeningImpulseTracker — 09:15-10:00 early trades
  ├── CorrelationBrake     — Cross-instrument loss protection
  ├── SystemStopManager    — Hard market halt
  └── ModePermissionChecker — Mode/day-type permission matrix
```

---

## 📁 File Map

| File                            | Lines | Purpose                                                                                                |
| ------------------------------- | ----- | ------------------------------------------------------------------------------------------------------ |
| **`app.py`**                    | 182   | Flask web server — dashboard, OAuth login, bot control endpoints                                       |
| **`rijin_live.py`**             | 813   | **Core live engine** — main trading loop, indicator calc, AI validation, Telegram alerts               |
| **`rijin_engine.py`**           | 1316  | **Trading rule engine** — Day type classification, impulse detection, execution gates, phase filtering |
| **`rijin_config.py`**           | 369   | **All configuration** — thresholds, timings, day type hierarchy, Telegram templates                    |
| **`rijin_live_runner.py`**      | 115   | Thread wrapper — bridges Flask dashboard to the live engine                                            |
| **`mode_f_engine.py`**          | 232   | **MODE_F 3-Gear signal engine** — Gear 1 (Trend), Gear 2 (Rotation), Gear 3 (Momentum)                 |
| **`mode_s_engine.py`**          | 215   | **MODE_S Sensex engine** — Core/Stability/Liquidity buckets                                            |
| **`gemini_helper.py`**          | 278   | **AI helper** — Groq/Gemini API calls for trade quality evaluation                                     |
| **`unified_engine.py`**         | 1397  | Legacy unified engine — Nifty/BankNifty/Gold strategies, utility functions (EMA, RSI, ATR)             |
| **`global_market_analyzer.py`** | 309   | Global market context — fetches S&P500, Nasdaq, VIX, DXY via yfinance                                  |
| **`mode_d_helpers.py`**         | 205   | MODE_D (Opening Drive) helper methods                                                                  |
| **`get_access_token.py`**       | 41    | CLI utility to generate daily Kite access token                                                        |
| **`example_daily_limit.py`**    | 33    | Example: daily signal cap implementation                                                               |
| **`render.yaml`**               | 28    | Render.com deployment blueprint                                                                        |
| **`requirements.txt`**          | 10    | Python dependencies                                                                                    |
| **`.env.example`**              | 15    | Environment variable template                                                                          |
| **`.gitignore`**                | —     | Git ignore rules                                                                                       |
| **`Procfile`**                  | —     | Gunicorn process definition                                                                            |
| **`templates/dashboard.html`**  | —     | Flask dashboard HTML template                                                                          |

---

## 🔑 Key Design Decisions

1. **Alert-Only (No Auto-Execution)** — Keeps the human in the loop. The bot tells you _what_ to do, not does it for you. This is a conscious safety decision.

2. **Fail-Open AI** — If the AI API fails, the signal is ACCEPTED. The signal engine's own filters are the primary safeguard; AI is an additional quality layer.

3. **One-Way Degradation** — Day types can only worsen. This prevents the system from "re-upgrading" a choppy day as trending and generating dangerous late signals.

4. **Impulse-Based Expansion (v3.0 Core Fix)** — Earlier versions measured expansion from day extremes, which was architecturally flawed. v3.0 measures from the _impulse origin_ — where the actual directional move started.

5. **IST-First Design** — All time logic uses IST via `pytz`, critical because Render servers run on UTC. A single `now_ist()` function is the sole source of truth.

6. **Groq over Gemini for AI Filter** — Despite the filename `gemini_helper.py`, the trade quality filter uses Groq's Llama 3.3 70B (faster, cheaper, more reliable for the structured JSON output required). Gemini is retained for market sentiment and exit analysis.

---

_Built with discipline. Deployed with conviction. Protecting capital above all else._
