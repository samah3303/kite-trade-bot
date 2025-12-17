# 🤖 Gold Guinea AI Trading Bot & Dashboard

A sophisticated algorithmic trading system for **Gold Guinea Futures (MCX)** using the Zerodha Kite Connect API. This system features a multi-mode strategy engine (Reversal, Pullback, Breakout), real-time Telegram alerts, and a Web Dashboard for management.

---

## ✨ Features

- **Multi-Mode Strategy**:
  - **Mode A (Reversal)**: Catches early trend changes using EMA crossovers.
  - **Mode B (Pullback)**: Enters established trends on pullbacks/support tests.
  - **Mode C (Breakout)**: Identifying high-momentum breakouts (with strict specific RSI conditions).
- **Hybrid Timeframe Analysis**: Uses 30-minute trend context to filter 5-minute entry signals.
- **Smart Risk Management**:
  - Dynamic Stop Loss & Target based on ATR (Volatility).
  - **Daily Kill Switch**: Stops trading after 3 consecutive losses or -2R drawdown.
- **Live Dashboard**:
  - Web UI to Start/Stop the bot.
  - Manual "Login with Zerodha" integrated flow to handle daily token expiry.
  - Live Log Viewer.
- **Telegram Integration**: Instant HTML-formatted alerts for Entries and Exits.

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
python rijin_alerts_kite.py
```

### Backtesting

To test the strategy on historical data:

```bash
python rijin_alerts_kite.py --backtest
```

Check `backtest_log.txt` for detailed results.

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

- `app.py`: Flask Web Server & UI Backend.
- `rijin_alerts_kite.py`: Core Trading Engine & Strategy Logic.
- `templates/dashboard.html`: Frontend UI.
- `requirements.txt`: Python Dependencies.
- `Procfile`: Render/Heroku Startup config.

---

## ⚠️ Disclaimer

This software is for educational purposes. Algorithmic trading involves significant risk. The authors are not responsible for any financial losses incurred.
