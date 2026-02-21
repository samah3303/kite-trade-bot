# KiteAlerts — Server Deployment Flow

> How the system works from `app.py` startup to live Telegram signals

---

## 1. Startup Sequence

```
gunicorn app:app --workers 1 --threads 4 --timeout 120
          │
          ▼
     ┌─────────┐
     │ app.py   │  (Flask app created)
     └────┬─────┘
          │
          ▼
   Load .env variables
   (API keys, tokens, USE_RIJIN_SYSTEM)
          │
          ▼
   USE_RIJIN_SYSTEM = "true" ?
          │
     ┌────┴────┐
     YES       NO
     │         │
     ▼         ▼
  import     use unified_engine.runner
  rijin_live_runner
     │
     ▼
  active_bot = rijin_live_runner
  bot_mode = "RIJIN v3.0.1"
          │
          ▼
   Flask server listening on port (Render assigns)
   Dashboard available at /
   ⚠️ Bot is NOT running yet — waiting for /start
```

> **Key**: The bot does NOT auto-start on deploy. You must hit `/start` from the dashboard or API.

---

## 2. Login Flow (One-Time Daily)

Kite access tokens expire every day. You must re-login each morning.

```
User clicks "Login" on Dashboard
          │
          ▼
   GET /login
   → Redirect to Zerodha Kite login page
          │
          ▼
   User logs in on Zerodha
          │
          ▼
   Zerodha redirects to /callback?request_token=xxx
          │
          ▼
   GET /callback
   → kite.generate_session(request_token)
   → Gets new access_token
   → Saves to .env (set_key)
   → Updates os.environ
   → Redirect to dashboard /
          │
          ▼
   ✅ Access token is now valid for today
```

---

## 3. Starting the Bot

```
User clicks "Start" on Dashboard
          │
          ▼
   POST /start
          │
          ▼
   rijin_live_runner.start()
          │
          ▼
   Creates background daemon thread
          │
          ▼
   Thread runs _run_engine():
     1. Creates RijinLiveEngine(stop_event)
     2. Resolves NIFTY instrument token from Kite
        - ✅ Success → logs token
        - ❌ Failure → sends 🚨 Telegram alert, engine won't start
     3. Calls engine.run()
          │
          ▼
   🚀 Telegram: "RIJIN v3.0.1 STARTED"
   (shows instrument, token, capital)
```

---

## 4. Main Trading Loop (Inside engine.run())

Runs continuously in the background thread:

```
┌──────────────────────────────────────────┐
│              MAIN LOOP (every 30 sec)     │
│                                          │
│  1. Is it a new day?                     │
│     YES → reset_daily_state()            │
│           📱 Telegram: "NEW DAY"          │
│                                          │
│  2. Is it trading hours (09:15–15:30)?   │
│     NO → sleep 60 sec, continue          │
│                                          │
│  3. Fetch 5min candles from Kite         │
│     FAIL → ⚠️ Telegram error alert       │
│     < 30 candles → sleep 30 sec          │
│                                          │
│  4. Calculate indicators (EMA20/ATR/RSI) │
│                                          │
│  5. Detect impulse                       │
│                                          │
│  6. Active trade? → check exit (SL/TP)   │
│     ✅ TARGET → 📱 Telegram "TRADE CLOSED"│
│     ❌ SL → 📱 Telegram + loss tracking   │
│                                          │
│  7. System stopped? → sleep 5 min        │
│                                          │
│  8. Every 5 min → Generate MODE_F signal │
│     │                                    │
│     ▼                                    │
│     Signal found?                        │
|     YES → Apply RIJIN gates (7 checks)   |
|       │                                  |
│       ├─ ✅ ALLOWED → Execute trade       │
│       │  📱 Telegram: "RIJIN SIGNAL"      │
│       │                                  │
│       └─ ❌ BLOCKED → Log + reason        │
│          📱 Telegram: "SIGNAL BLOCKED"    │
│                                          │
│  9. Sleep 30 sec → loop again            │
└──────────────────────────────────────────┘
```

---

## 5. Stopping the Bot

```
User clicks "Stop" on Dashboard
          │
          ▼
   POST /stop
          │
          ▼
   rijin_live_runner.stop()
   → Sets stop_event (threading.Event)
   → Engine's while loop checks stop_event
   → Loop exits on next iteration
          │
          ▼
   🛑 Telegram: "RIJIN STOPPED"
```

---

## 6. Dashboard API Endpoints

| Endpoint                     | Method | What It Does                                    |
| ---------------------------- | ------ | ----------------------------------------------- |
| `/`                          | GET    | Dashboard HTML page                             |
| `/login`                     | GET    | Redirect to Zerodha login                       |
| `/callback`                  | GET    | Handle login callback, save token               |
| `/start`                     | POST   | Start bot engine in background thread           |
| `/stop`                      | POST   | Stop bot engine gracefully                      |
| `/status`                    | GET    | `{ running: true/false, mode: "RIJIN v3.0.1" }` |
| `/logs`                      | GET    | Last 5000 chars of console output               |
| `/rijin/day-type`            | GET    | Current day type (CLEAN_TREND, CHOP, etc.)      |
| `/rijin/stats`               | GET    | System stop state, trades, blocks               |
| `/rijin/v3/live-stats`       | GET    | Full live stats (P&L, trades, paused, etc.)     |
| `/rijin/v3/backtest-results` | GET    | Hardcoded backtest summary                      |
| `/rijin/config`              | GET    | Gate thresholds, impulse config                 |

---

## 7. Telegram Notifications You'll See

| Message                           | Trigger                            |
| --------------------------------- | ---------------------------------- |
| RIJIN v3.0.1 STARTED              | Bot starts successfully            |
| STARTUP ERROR                     | Instrument/token resolution failed |
| NEW DAY                           | Daily reset at market open         |
| RIJIN SIGNAL (BUY/SELL)           | Trade allowed through all gates    |
| SIGNAL BLOCKED + reason           | Gates rejected a signal            |
| HARD BLOCK (Liquidity Sweep Trap) | Stop-hunt detected, all trades off |
| ROTATIONAL_EXPANSION capped       | Max 1 trade in unstable expansion  |
| FAST_REGIME_FLIP RSI blocked      | RSI too weak for regime flip trade |
| DAY TYPE DOWNGRADE                | Regime degraded (never upgrades)   |
| TRADE CLOSED: TARGET              | Profit target hit                  |
| TRADE CLOSED: SL                  | Stop loss hit                      |
| CONSECUTIVE LOSS PROTECTION       | 2 losses -> 60 min pause           |
| Trading Resumed                   | Pause expired                      |
| RIJIN ERROR                       | Candle fetch or loop error         |
| ENGINE CRASHED                    | Engine thread died                 |
| RIJIN STOPPED                     | Engine shut down                   |

---

## 8. Deployment on Render

### Procfile

```
web: gunicorn app:app --workers 1 --threads 4 --timeout 120
```

> **Important**: Must use `--workers 1` — the bot engine runs in a thread inside the Flask process. Multiple workers = multiple duplicate engines.

### Required Environment Variables (Render Dashboard)

| Variable             | Value                         |
| -------------------- | ----------------------------- |
| `KITE_API_KEY`       | Your Zerodha API key          |
| `KITE_API_SECRET`    | Your Zerodha API secret       |
| `KITE_ACCESS_TOKEN`  | Updated daily via /login flow |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token       |
| `TELEGRAM_CHAT_ID`   | Your Telegram chat/group ID   |
| `NIFTY_INSTRUMENT`   | `NSE:NIFTY 50`                |
| `USE_RIJIN_SYSTEM`   | `true`                        |

### Daily Routine

```
1. Open dashboard URL (Render gives you the URL)
2. Click "Login" → complete Zerodha login
3. Click "Start" → bot begins monitoring
4. Signals appear in Telegram automatically
5. At 15:30 IST → bot goes idle until next day
6. Next morning → repeat from step 2 (new access token needed)
```

---

## 9. Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│                    RENDER                        │
│                                                 │
│  ┌────────────────────────────────────────────┐ │
│  │              GUNICORN (1 worker)            │ │
│  │                                            │ │
│  │  ┌──────────────────┐  ┌────────────────┐  │ │
│  │  │   Flask App      │  │ Background     │  │ │
│  │  │   (app.py)       │  │ Thread         │  │ │
│  │  │                  │  │                │  │ │
│  │  │  /login          │  │ RijinLive      │  │ │
│  │  │  /callback       │  │ Engine         │  │ │
│  │  │  /start ────────────▶ .run()         │  │ │
│  │  │  /stop  ────────────▶ .stop()        │  │ │
│  │  │  /status         │  │                │  │ │
│  │  │  /logs           │  │  ┌──────────┐  │  │ │
│  │  └──────────────────┘  │  │ MODE_F   │  │  │ │
│  │                        │  │ Engine   │  │  │ │
│  │                        │  └────┬─────┘  │  │ │
│  │                        │       │signal  │  │ │
│  │                        │       ▼        │  │ │
│  │                        │  ┌──────────┐  │  │ │
│  │                        │  │ RIJIN    │  │  │ │
│  │                        │  │ Gates    │  │  │ │
│  │                        │  └────┬─────┘  │  │ │
│  │                        └───────┼────────┘  │ │
│  └────────────────────────────────┼───────────┘ │
│                                   │             │
└───────────────────────────────────┼─────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              ┌──────────┐   ┌──────────┐   ┌──────────┐
              │ Zerodha  │   │ Telegram │   │ Gemini   │
              │ Kite API │   │ Bot API  │   │ AI API   │
              └──────────┘   └──────────┘   └──────────┘
```
