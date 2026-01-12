# 🤖 KiteAlerts - Multi-Strategy Trading Bot

A sophisticated algorithmic trading system for **Indian markets (Nifty 50, Gold Guinea)** using the Zerodha Kite Connect API. This system features a multi-mode strategy engine (Reversal, Pullback, Momentum), Gemini AI integration, real-time Telegram alerts, and a Web Dashboard for management.

---

## ✨ Features

- **Nifty-Centric Multi-Strategy Engine**:
  - **Mode A (Fresh Trend)**: Catches early trend reversals (Rare, high-confidence setups)
  - **Mode B (Pullback)**: Strict-gate pullback entries with ATR-based filters
  - **Mode C (Momentum)**: Primary profit driver - breakouts, ORB, micro-range expansion
  - Gold Guinea: Mode C only (Mean reversion disabled)
- **Gemini AI Integration**:
  - Entry analysis: Confidence scoring (1-10) + Risk assessment
  - Exit analysis: Post-trade review with lessons learned
- **Hybrid Timeframe Analysis**: 30-minute trend context filters 5-minute entry signals
- **Smart Risk Management**:
  - Dynamic Stop Loss & Target based on ATR (Volatility)
  - **Daily Kill Switch**: Max 7 trades or -1.5R drawdown limit
  - Mode C Loss Brake: Pause after 2 consecutive losses
- **Live Dashboard**:
  - Web UI to Start/Stop the bot
  - Manual "Login with Zerodha" integrated flow to handle daily token expiry
  - Live Log Viewer
- **Telegram Integration**: Instant HTML-formatted alerts with AI analysis

---

## 🛠️ Installation (Local)

1.  **Clone/Download** this repository.
2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configure Environment**:
    - Create a `.env` file (see `.env.example` or below).
    - Add your Kite API Keys and Telegram Tokens.
    ```ini
    KITE_API_KEY=your_key
    KITE_API_SECRET=your_secret
    TELEGRAM_BOT_TOKEN=your_token
    TELEGRAM_CHAT_ID=your_chat_id
    ```

---

## 🚀 Usage

### Running the Dashboard

1.  Start the Application:
    ```bash
    python app.py
    ```
2.  Open your browser: [http://localhost:5000](http://localhost:5000)
3.  **Login**: Click "KEY LOGIN ZERODHA" to authenticate daily.
4.  **Start**: Click "PLAY START BOT" to begin analyzing.

### Running Headless (Server)

You can run the bot script directly without the UI if desired:

```bash
python unified_engine.py
```

### Backtesting

Multiple backtest scripts are available for different strategies:

```bash
python backtest_unified.py        # Test unified multi-strategy engine
python backtest_hybrid.py         # Test hybrid EMA + RSI strategy
python backtest_bullish_candle.py # Test bullish pattern strategy
```

Results are saved as CSV files with detailed trade logs.

---

## ☁️ Deployment (Free Cloud)

**Recommended Stack: Render + UptimeRobot**

1.  **Render**: Create a Web Service connected to this Repo.
    - Build: `pip install -r requirements.txt`
    - Start: `python app.py`
    - Env Vars: Add all values from `.env`.
2.  **UptimeRobot**:
    - Create a monitor to ping your Render URL every 5 minutes.
    - This prevents the free tier server from sleeping.
3.  **Zerodha Redirect**:
    - Update your Zerodha App **Redirect URL** to `https://your-app-name.onrender.com/callback`.

---

## 📂 Project Structure

- `app.py`: Flask Web Server & UI Backend
- `unified_engine.py`: Core Multi-Strategy Trading Engine
- `gemini_helper.py`: Gemini AI Integration for Trade Analysis
- `backtest_*.py`: Backtesting Scripts for Strategy Validation
- `templates/dashboard.html`: Frontend UI
- `requirements.txt`: Python Dependencies
- `Procfile`: Render/Heroku Startup Config
- `TRADING_RULES.md`: Strategy Constitution & Rules
- `DETAILED_LOGIC.md`: Complete Code-Level Documentation

---

## ⚠️ Disclaimer

This software is for educational purposes. Algorithmic trading involves significant risk. The authors are not responsible for any financial losses incurred.
