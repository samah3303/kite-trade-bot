"""
RIJIN v3.0.1 — 3-MONTH BACKTEST ENGINE (AI-FILTERED)
Architecture: Signal Engine (MODE_F) → AI Validator (Gemini) → Telegram Alert

NO gate logic. NO regime downgrades. NO system stops.
AI layer acts as constrained quality filter — ACCEPT or RESTRICT only.

Usage: python backtest_3month.py
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta, time as dtime, date
from collections import defaultdict

import pytz
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# === Signal Engine ===
from mode_f_engine import ModeFEngine

# === AI Validator ===
from gemini_helper import gemini

# === Utilities (from unified_engine) ===
from unified_engine import (
    simple_ema,
    calculate_rsi,
    calculate_atr,
    send_telegram_message,
)

# === Setup ===
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

IST = pytz.timezone('Asia/Kolkata')

# === Configuration ===
API_KEY = os.getenv("KITE_API_KEY")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")
NIFTY_INSTRUMENT = os.getenv("NIFTY_INSTRUMENT", "NSE:NIFTY 50")

INITIAL_CAPITAL = 100000   # Rs.1,00,000
RISK_PER_TRADE = 0.01      # 1% = 1R

# AI Filter Settings
USE_AI_FILTER = True        # Set False to skip Gemini (all signals ACCEPT)
AI_CALL_DELAY = 2        # Seconds between Groq calls (30 RPM free = 2s min)

# Backtest period
BACKTEST_MONTHS = 3


# ===================================================================
# BACKTEST ENGINE — AI-FILTERED ARCHITECTURE
# ===================================================================
class RijinBacktester:
    """
    Clean layered architecture:
      1. Feature Extraction (EMA, ATR, RSI, VWAP, Slope)
      2. Signal Engine (MODE_F — 3-Gear)
      3. AI Validator (Gemini — ACCEPT/RESTRICT)
      4. Telegram Alert Delivery
    """

    def __init__(self):
        self.kite = KiteConnect(api_key=API_KEY)
        self.kite.set_access_token(ACCESS_TOKEN)

        self.instrument_token = None
        self._resolve_instrument_token()

        self.mode_f = ModeFEngine()

        self.all_trades = []
        self.daily_summaries = []
        self.all_signals = []

        self.ai_total_calls = 0
        self.ai_accepts = 0
        self.ai_restricts = 0
        self.ai_failures = 0
        self.ai_confidence_sum = 0.0

    def _resolve_instrument_token(self):
        try:
            ltp_data = self.kite.ltp(NIFTY_INSTRUMENT)
            self.instrument_token = ltp_data[NIFTY_INSTRUMENT]['instrument_token']
            logging.info(f"✅ Resolved {NIFTY_INSTRUMENT} → token {self.instrument_token}")
        except Exception as e:
            logging.error(f"❌ Failed to resolve instrument: {e}")
            sys.exit(1)

    def fetch_historical_candles(self, from_date, to_date):
        all_candles = []
        chunk_start = from_date

        while chunk_start < to_date:
            chunk_end = min(chunk_start + timedelta(days=55), to_date)
            try:
                candles = self.kite.historical_data(
                    instrument_token=self.instrument_token,
                    from_date=chunk_start,
                    to_date=chunk_end,
                    interval="5minute"
                )
                if candles:
                    all_candles.extend(candles)
                    logging.info(
                        f"  📥 {len(candles)} candles: "
                        f"{chunk_start.strftime('%Y-%m-%d')} → {chunk_end.strftime('%Y-%m-%d')}"
                    )
                time.sleep(0.5)
            except Exception as e:
                logging.error(f"  ❌ Fetch error ({chunk_start} → {chunk_end}): {e}")
                time.sleep(1)
            chunk_start = chunk_end + timedelta(days=1)

        logging.info(f"📊 Total candles: {len(all_candles)}")
        return all_candles

    # ---------------------------------------------------------------
    # FEATURE EXTRACTION
    # ---------------------------------------------------------------

    def calculate_indicators(self, candles):
        if len(candles) < 30:
            return None
        closes = [float(c['close']) for c in candles]
        highs = [float(c['high']) for c in candles]
        lows = [float(c['low']) for c in candles]

        ema20 = simple_ema(closes, 20)
        atr = calculate_atr(highs, lows, closes, 14)
        rsi = calculate_rsi(closes, 14)

        if len(ema20) == 0 or len(atr) == 0 or len(rsi) == 0:
            return None

        slope = 0.0
        if len(ema20) >= 4:
            slope = float(ema20[-1]) - float(ema20[-4])

        return {
            'ema20': float(ema20[-1]),
            'atr': float(atr[-1]),
            'rsi': float(rsi[-1]),
            'slope': slope,
        }

    def calculate_vwap(self, candles):
        try:
            total_vol = sum(c.get('volume', 1) for c in candles)
            if total_vol == 0:
                return float(candles[-1]['close'])
            vwap = sum(
                ((float(c['high']) + float(c['low']) + float(c['close'])) / 3) * c.get('volume', 1)
                for c in candles
            ) / total_vol
            return vwap
        except:
            return float(candles[-1]['close'])

    def build_market_context(self, candles, indicators, candle_time):
        price = float(candles[-1]['close'])
        vwap = self.calculate_vwap(candles)

        session_high = max(float(c['high']) for c in candles)
        session_low = min(float(c['low']) for c in candles)

        if isinstance(candle_time, datetime):
            time_str = candle_time.strftime('%H:%M')
            market_open = candle_time.replace(hour=9, minute=15, second=0)
            minutes_since_open = int((candle_time - market_open).total_seconds() / 60)
        else:
            time_str = str(candle_time)
            minutes_since_open = 0

        if minutes_since_open < 30:
            session_phase = "Opening"
        elif minutes_since_open < 90:
            session_phase = "Morning"
        elif minutes_since_open < 210:
            session_phase = "Midday"
        elif minutes_since_open < 300:
            session_phase = "Afternoon"
        else:
            session_phase = "Closing"

        slope = indicators['slope']
        trend = "Bullish" if slope > 5 else "Bearish" if slope < -5 else "Sideways"

        session_range = session_high - session_low
        atr = indicators['atr']
        range_vs_atr = session_range / atr if atr > 0 else 0

        if range_vs_atr > 2.0 and trend == "Bullish":
            day_type = "Bullish Expansion"
        elif range_vs_atr > 2.0 and trend == "Bearish":
            day_type = "Bearish Expansion"
        elif range_vs_atr > 1.5:
            day_type = "Trending"
        elif range_vs_atr > 0.8:
            day_type = "Normal Range"
        else:
            day_type = "Narrow Range"

        price_vs_vwap_pct = ((price - vwap) / vwap * 100) if vwap > 0 else 0
        distance_from_low_pct = ((price - session_low) / session_low * 100) if session_low > 0 else 0
        distance_from_high_pct = ((session_high - price) / session_high * 100) if session_high > 0 else 0

        rsi = indicators['rsi']
        if len(candles) >= 4:
            closes_3ago = [float(c['close']) for c in candles[:-3]]
            rsi_3ago_list = calculate_rsi(closes_3ago, 14)
            rsi_3ago = float(rsi_3ago_list[-1]) if len(rsi_3ago_list) > 0 else rsi
            rsi_diff = rsi - rsi_3ago
            rsi_slope = "Rising" if rsi_diff > 3 else "Falling" if rsi_diff < -3 else "Flat"
        else:
            rsi_slope = "Flat"

        expansion_legs = self._count_expansion_legs(candles)
        avg_leg = self._avg_leg_size(candles)
        current_leg = self._current_leg_size(candles)
        current_leg_vs_avg = round(current_leg / avg_leg, 1) if avg_leg > 0 else 1.0

        atr_pct = (atr / price * 100) if price > 0 else 0
        volatility_state = "Contracting" if atr_pct < 0.10 else "Normal" if atr_pct < 0.25 else "Expanding"

        structure_last_5 = self._detect_structure(candles[-5:] if len(candles) >= 5 else candles)
        pullback_depth_pct = self._calculate_pullback_depth(candles)

        if len(candles) >= 20:
            recent_vol = sum(c.get('volume', 0) for c in candles[-3:]) / 3
            avg_vol = sum(c.get('volume', 0) for c in candles[-20:]) / 20
            volume_vs_avg = round(recent_vol / avg_vol, 1) if avg_vol > 0 else 1.0
        else:
            volume_vs_avg = 1.0

        return {
            "time": time_str,
            "minutes_since_open": minutes_since_open,
            "session_phase": session_phase,
            "day_type": day_type,
            "trend": trend,
            "price_vs_vwap_pct": round(price_vs_vwap_pct, 2),
            "distance_from_session_low_pct": round(distance_from_low_pct, 2),
            "distance_from_session_high_pct": round(distance_from_high_pct, 2),
            "rsi": round(rsi, 0),
            "rsi_slope": rsi_slope,
            "expansion_legs": expansion_legs,
            "current_leg_vs_avg": current_leg_vs_avg,
            "volatility_state": volatility_state,
            "structure_last_5": structure_last_5,
            "pullback_depth_pct": pullback_depth_pct,
            "volume_vs_avg": volume_vs_avg,
        }

    # ---------------------------------------------------------------
    # STRUCTURE HELPERS
    # ---------------------------------------------------------------

    def _count_expansion_legs(self, candles):
        if len(candles) < 3:
            return 0
        legs = 0
        prev_dir = None
        for i in range(1, len(candles)):
            curr_dir = "UP" if float(candles[i]['close']) > float(candles[i]['open']) else "DOWN"
            if curr_dir != prev_dir and prev_dir is not None:
                legs += 1
            prev_dir = curr_dir
        return max(1, legs)

    def _avg_leg_size(self, candles):
        if len(candles) < 3:
            return 1.0
        legs = []
        leg_start = float(candles[0]['close'])
        prev_dir = None
        for i in range(1, len(candles)):
            c = float(candles[i]['close'])
            o = float(candles[i]['open'])
            curr_dir = "UP" if c > o else "DOWN"
            if curr_dir != prev_dir and prev_dir is not None:
                legs.append(abs(c - leg_start))
                leg_start = c
            prev_dir = curr_dir
        return (sum(legs) / len(legs)) if legs else (abs(float(candles[-1]['close']) - float(candles[0]['close'])) or 1.0)

    def _current_leg_size(self, candles):
        if len(candles) < 3:
            return 0.0
        last_dir = "UP" if float(candles[-1]['close']) > float(candles[-1]['open']) else "DOWN"
        leg_start_price = float(candles[-1]['close'])
        for i in range(len(candles) - 2, -1, -1):
            curr_dir = "UP" if float(candles[i]['close']) > float(candles[i]['open']) else "DOWN"
            if curr_dir != last_dir:
                break
            leg_start_price = float(candles[i]['close'])
        return abs(float(candles[-1]['close']) - leg_start_price)

    def _detect_structure(self, candles):
        if len(candles) < 3:
            return "Insufficient data"
        highs = [float(c['high']) for c in candles]
        lows = [float(c['low']) for c in candles]
        hh = all(highs[i] >= highs[i-1] for i in range(1, len(highs)))
        hl = all(lows[i] >= lows[i-1] for i in range(1, len(lows)))
        lh = all(highs[i] <= highs[i-1] for i in range(1, len(highs)))
        ll = all(lows[i] <= lows[i-1] for i in range(1, len(lows)))
        if hh and hl: return "HH-HL continuation"
        elif lh and ll: return "LH-LL continuation"
        elif hh and ll: return "Expanding range"
        elif lh and hl: return "Contracting range"
        elif hh: return "Higher highs"
        elif ll: return "Lower lows"
        else: return "Choppy / No structure"

    def _calculate_pullback_depth(self, candles):
        if len(candles) < 10:
            return 0
        recent = candles[-20:] if len(candles) >= 20 else candles
        swing_high = max(float(c['high']) for c in recent)
        swing_low = min(float(c['low']) for c in recent)
        swing_range = swing_high - swing_low
        if swing_range == 0:
            return 0
        current_price = float(candles[-1]['close'])
        pullback = (swing_high - current_price) if current_price > (swing_high + swing_low) / 2 else (current_price - swing_low)
        return round((pullback / swing_range) * 100)

    # ---------------------------------------------------------------
    # AI VALIDATION LAYER
    # ---------------------------------------------------------------

    def validate_signal_with_ai(self, market_context, signal):
        if not USE_AI_FILTER:
            return {"decision": "ACCEPT", "confidence": 100, "reasons": ["AI filter disabled"]}

        risk = abs(signal['entry'] - signal['sl'])
        reward = abs(signal['target'] - signal['entry'])
        rr_ratio = f"1:{reward / risk:.0f}" if risk > 0 else "1:0"

        signal_data = {
            "direction": "SHORT" if signal['direction'] == 'SELL' else "LONG",
            "entry": signal['entry'],
            "sl": signal['sl'],
            "rr": rr_ratio,
        }

        self.ai_total_calls += 1
        result = gemini.evaluate_trade_quality(market_context, signal_data)

        if result is None:
            self.ai_failures += 1
            return {"decision": "ACCEPT", "confidence": 50, "reasons": ["AI unavailable — defaulting to ACCEPT"]}

        if result['decision'] == 'ACCEPT':
            self.ai_accepts += 1
        else:
            self.ai_restricts += 1
        self.ai_confidence_sum += result['confidence']

        time.sleep(AI_CALL_DELAY)
        return result

    # ---------------------------------------------------------------
    # TRADE SIMULATION
    # ---------------------------------------------------------------

    def simulate_trade_exit(self, trade, future_candles):
        for i, candle in enumerate(future_candles):
            h = float(candle['high'])
            l = float(candle['low'])
            if trade['direction'] == 'BUY':
                if l <= trade['sl']: return 'SL', trade['sl'], candle['date'], i
                if h >= trade['target']: return 'TARGET', trade['target'], candle['date'], i
            else:
                if h >= trade['sl']: return 'SL', trade['sl'], candle['date'], i
                if l <= trade['target']: return 'TARGET', trade['target'], candle['date'], i
        if future_candles:
            last = future_candles[-1]
            return 'EOD', float(last['close']), last['date'], len(future_candles) - 1
        return 'NO_DATA', trade['entry'], None, 0

    # ---------------------------------------------------------------
    # MAIN BACKTEST LOOP
    # ---------------------------------------------------------------

    def run_backtest(self):
        end_date = datetime.now(IST).replace(hour=15, minute=30, second=0, microsecond=0)
        start_date = end_date - timedelta(days=BACKTEST_MONTHS * 30)

        logging.info("=" * 60)
        logging.info("RIJIN v3.0.1 — 3-MONTH BACKTEST (AI-FILTERED)")
        logging.info("=" * 60)
        logging.info(f"Period: {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")
        logging.info(f"AI Filter: {'ENABLED' if USE_AI_FILTER else 'DISABLED'}")

        send_telegram_message(
            f"📊 <b>RIJIN v3.0.1 BACKTEST STARTED</b>\n\n"
            f"📅 Period: {start_date.strftime('%d %b %Y')} → {end_date.strftime('%d %b %Y')}\n"
            f"📈 Instrument: <code>{NIFTY_INSTRUMENT}</code>\n"
            f"🤖 AI Filter: <b>{'ENABLED' if USE_AI_FILTER else 'DISABLED'}</b>\n"
            f"💰 Capital: Rs.{INITIAL_CAPITAL:,}\n"
            f"🎯 Risk: Rs.{int(INITIAL_CAPITAL * RISK_PER_TRADE):,}/trade\n\n"
            f"⏳ Processing..."
        )

        logging.info("\n📥 Fetching historical data...")
        all_candles = self.fetch_historical_candles(start_date, end_date)

        if len(all_candles) < 100:
            msg = "❌ Insufficient data for backtest"
            logging.error(msg)
            send_telegram_message(msg)
            return

        days = self._group_by_day(all_candles)
        logging.info(f"\n📅 Trading days: {len(days)}")

        total_trades = 0
        total_wins = 0
        total_pnl_r = 0.0
        capital = INITIAL_CAPITAL
        max_capital = capital
        max_drawdown = 0.0
        best_day_pnl = 0.0
        worst_day_pnl = 0.0
        trade_number = 0

        for day_date, day_candles in sorted(days.items()):
            daily_trades = 0
            daily_pnl_r = 0.0

            i = 50
            while i < len(day_candles):
                candle = day_candles[i]
                candle_time = candle['date']

                if isinstance(candle_time, datetime) and candle_time.tzinfo is None:
                    candle_time = IST.localize(candle_time)

                current_time = candle_time.time()
                if not (dtime(9, 20) <= current_time <= dtime(15, 15)):
                    i += 1
                    continue

                window = day_candles[:i + 1]
                indicators = self.calculate_indicators(window)
                if not indicators:
                    i += 1
                    continue

                # ===== LAYER 1: SIGNAL ENGINE =====
                signal_result = self.mode_f.predict(window, global_bias="NEUTRAL")

                if signal_result.valid:
                    signal = {
                        'direction': signal_result.direction,
                        'entry': signal_result.entry,
                        'sl': signal_result.sl,
                        'target': signal_result.target,
                        'gear': signal_result.gear.name,
                    }

                    market_context = self.build_market_context(window, indicators, candle_time)

                    # ===== LAYER 2: AI VALIDATOR =====
                    ai_result = self.validate_signal_with_ai(market_context, signal)
                    ai_decision = ai_result['decision']
                    ai_confidence = ai_result['confidence']
                    ai_reasons = ai_result['reasons']

                    entry_time_str = candle_time.strftime('%H:%M')
                    self.all_signals.append({
                        'date': day_date.strftime('%Y-%m-%d'),
                        'time': entry_time_str,
                        'direction': signal['direction'],
                        'gear': signal['gear'],
                        'ai_decision': ai_decision,
                        'ai_confidence': ai_confidence,
                    })

                    if ai_decision == 'ACCEPT':
                        # ===== LAYER 3: SIMULATE TRADE =====
                        future_candles = day_candles[i + 1:]
                        exit_type, exit_price, exit_time, exit_idx = self.simulate_trade_exit(signal, future_candles)

                        risk = abs(signal['entry'] - signal['sl'])
                        if risk > 0:
                            pnl_pts = (exit_price - signal['entry']) if signal['direction'] == 'BUY' else (signal['entry'] - exit_price)
                            pnl_r = pnl_pts / risk
                        else:
                            pnl_r = 0.0

                        pnl_money = pnl_r * (INITIAL_CAPITAL * RISK_PER_TRADE)
                        capital += pnl_money

                        trade_number += 1
                        total_trades += 1
                        daily_trades += 1
                        total_pnl_r += pnl_r
                        daily_pnl_r += pnl_r

                        if exit_type == 'TARGET':
                            total_wins += 1

                        if capital > max_capital:
                            max_capital = capital
                        dd = (max_capital - capital) / max_capital * 100
                        if dd > max_drawdown:
                            max_drawdown = dd

                        exit_time_str = exit_time.strftime('%H:%M') if exit_time else 'N/A'

                        self.all_trades.append({
                            'trade_no': trade_number,
                            'date': day_date.strftime('%Y-%m-%d'),
                            'entry_time': entry_time_str,
                            'exit_time': exit_time_str,
                            'direction': signal['direction'],
                            'gear': signal['gear'],
                            'entry': round(signal['entry'], 2),
                            'sl': round(signal['sl'], 2),
                            'target': round(signal['target'], 2),
                            'ai_decision': ai_decision,
                            'ai_confidence': ai_confidence,
                            'ai_reasons': ai_reasons,
                            'exit_type': exit_type,
                            'exit_price': round(exit_price, 2),
                            'pnl_r': round(pnl_r, 2),
                            'pnl_money': round(pnl_money, 2),
                            'capital': round(capital, 2),
                        })

                        # ===== LAYER 4: TELEGRAM ALERT =====
                        emoji = "✅" if exit_type == 'TARGET' else "❌" if exit_type == 'SL' else "⏹"
                        send_telegram_message(
                            f"{emoji} <b>BACKTEST TRADE #{trade_number}</b>\n\n"
                            f"📅 {day_date} | {entry_time_str} → {exit_time_str}\n"
                            f"📍 {signal['direction']} ({signal['gear']})\n"
                            f"💵 Entry: {signal['entry']:.1f} | SL: {signal['sl']:.1f} | TGT: {signal['target']:.1f}\n"
                            f"📊 Exit: {exit_price:.1f} ({exit_type})\n"
                            f"💰 P&L: <b>{pnl_r:+.2f}R</b> (Rs.{pnl_money:+,.0f})\n\n"
                            f"🤖 <b>AI: {ai_decision}</b> ({ai_confidence}%)\n"
                            f"{''.join('• ' + r + chr(10) for r in ai_reasons[:3])}"
                        )

                        logging.info(
                            f"  {emoji} #{trade_number} | {day_date} {entry_time_str} "
                            f"| {signal['direction']} ({signal['gear']}) "
                            f"| {signal['entry']:.1f} → {exit_price:.1f} ({exit_type}) "
                            f"| {pnl_r:+.2f}R | AI: {ai_decision} ({ai_confidence}%)"
                        )

                        i += exit_idx + 1
                        continue

                    else:
                        logging.info(
                            f"  ⚠️ RESTRICTED | {day_date} {entry_time_str} "
                            f"| {signal['direction']} ({signal['gear']}) "
                            f"| AI: {ai_confidence}% | {'; '.join(ai_reasons[:2])}"
                        )
                        send_telegram_message(
                            f"⚠️ <b>SIGNAL RESTRICTED BY AI</b>\n\n"
                            f"📅 {day_date} | {entry_time_str}\n"
                            f"📍 {signal['direction']} ({signal['gear']})\n"
                            f"💵 Entry: {signal['entry']:.1f} | SL: {signal['sl']:.1f}\n\n"
                            f"🤖 <b>AI: RESTRICT</b> ({ai_confidence}%)\n"
                            f"{''.join('• ' + r + chr(10) for r in ai_reasons[:3])}"
                        )

                i += 1

            if daily_trades > 0:
                if daily_pnl_r > best_day_pnl: best_day_pnl = daily_pnl_r
                if daily_pnl_r < worst_day_pnl: worst_day_pnl = daily_pnl_r
                self.daily_summaries.append({
                    'date': day_date.strftime('%Y-%m-%d'),
                    'trades': daily_trades,
                    'pnl_r': round(daily_pnl_r, 2),
                })
                logging.info(f"  📅 {day_date} | {daily_trades} trades | P&L: {daily_pnl_r:+.2f}R")

        self._send_final_report(
            start_date, end_date, len(days),
            total_trades, total_wins, total_pnl_r,
            capital, max_drawdown, best_day_pnl, worst_day_pnl
        )

    # ---------------------------------------------------------------
    # REPORTS
    # ---------------------------------------------------------------

    def _group_by_day(self, candles):
        days = defaultdict(list)
        for c in candles:
            trade_date = c['date'].date() if isinstance(c['date'], datetime) else c['date']
            days[trade_date].append(c)
        return days

    def _send_final_report(self, start_date, end_date, total_days,
                           total_trades, total_wins, total_pnl_r,
                           final_capital, max_drawdown, best_day, worst_day):

        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        total_losses = total_trades - total_wins
        avg_pnl_per_day = total_pnl_r / total_days if total_days > 0 else 0

        wins = [t for t in self.all_trades if t['exit_type'] == 'TARGET']
        losses = [t for t in self.all_trades if t['exit_type'] == 'SL']
        eod_trades = [t for t in self.all_trades if t['exit_type'] == 'EOD']

        avg_win_r = sum(t['pnl_r'] for t in wins) / len(wins) if wins else 0
        avg_loss_r = sum(t['pnl_r'] for t in losses) / len(losses) if losses else 0

        pnl_money = final_capital - INITIAL_CAPITAL
        return_pct = (pnl_money / INITIAL_CAPITAL) * 100

        avg_confidence = (self.ai_confidence_sum / self.ai_total_calls) if self.ai_total_calls > 0 else 0
        total_signals = len(self.all_signals)

        report = (
            f"📊 <b>RIJIN v3.0.1 — 3-MONTH BACKTEST REPORT</b>\n"
            f"{'=' * 40}\n\n"
            f"📅 <b>Period:</b> {start_date.strftime('%d %b %Y')} → {end_date.strftime('%d %b %Y')}\n"
            f"📈 <b>Instrument:</b> {NIFTY_INSTRUMENT}\n"
            f"📆 <b>Trading Days:</b> {total_days}\n\n"
            f"{'─' * 40}\n"
            f"💰 <b>PERFORMANCE</b>\n"
            f"{'─' * 40}\n"
            f"🔢 Total Trades: <b>{total_trades}</b>\n"
            f"✅ Wins: {total_wins} | ❌ Losses: {total_losses} | ⏹ EOD: {len(eod_trades)}\n"
            f"🎯 Win Rate: <b>{win_rate:.1f}%</b>\n\n"
            f"📈 Total P&L: <b>{total_pnl_r:+.2f}R</b>\n"
            f"💵 P&L: <b>Rs.{pnl_money:+,.0f}</b>\n"
            f"📊 Return: <b>{return_pct:+.1f}%</b>\n\n"
            f"💰 Starting: Rs.{INITIAL_CAPITAL:,}\n"
            f"💰 Final: <b>Rs.{final_capital:,.0f}</b>\n\n"
            f"{'─' * 40}\n"
            f"📉 <b>RISK METRICS</b>\n"
            f"{'─' * 40}\n"
            f"📈 Avg Win: {avg_win_r:+.2f}R\n"
            f"📉 Avg Loss: {avg_loss_r:+.2f}R\n"
            f"📊 Avg P&L/Day: {avg_pnl_per_day:+.2f}R\n"
            f"🏆 Best Day: {best_day:+.2f}R\n"
            f"💀 Worst Day: {worst_day:+.2f}R\n"
            f"📉 Max Drawdown: {max_drawdown:.1f}%\n\n"
        )

        if total_signals > 0:
            report += (
                f"{'─' * 40}\n"
                f"🤖 <b>AI FILTER STATS</b>\n"
                f"{'─' * 40}\n"
                f"📡 Total Signals: {total_signals}\n"
                f"✅ Accepted: {self.ai_accepts} ({self.ai_accepts / total_signals * 100:.0f}%)\n"
                f"⚠️ Restricted: {self.ai_restricts} ({self.ai_restricts / total_signals * 100:.0f}%)\n"
                f"❓ Failures: {self.ai_failures}\n"
                f"📊 Avg Confidence: {avg_confidence:.0f}%\n\n"
            )

        report += f"⏰ {datetime.now(IST).strftime('%d %b %Y %H:%M IST')}"

        send_telegram_message(report)
        logging.info("\n" + report.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))

        if self.all_trades:
            self._send_trade_log()
        if self.daily_summaries:
            self._send_daily_breakdown()

    def _send_trade_log(self):
        batch_size = 12
        for batch_start in range(0, len(self.all_trades), batch_size):
            batch = self.all_trades[batch_start:batch_start + batch_size]
            lines = [f"📋 <b>TRADE LOG ({batch_start + 1}-{batch_start + len(batch)} of {len(self.all_trades)})</b>\n"]
            for t in batch:
                emoji = "✅" if t['exit_type'] == 'TARGET' else "❌" if t['exit_type'] == 'SL' else "⏹"
                lines.append(
                    f"{emoji} #{t['trade_no']} | {t['date']} {t['entry_time']}"
                    f" | {t['direction']} ({t['gear']})"
                    f" | {t['entry']} → {t['exit_price']} ({t['exit_type']})"
                    f" | <b>{t['pnl_r']:+.2f}R</b>"
                    f" | 🤖 {t['ai_decision']} {t['ai_confidence']}%"
                )
            send_telegram_message("\n".join(lines))
            time.sleep(0.5)

    def _send_daily_breakdown(self):
        batch_size = 20
        for batch_start in range(0, len(self.daily_summaries), batch_size):
            batch = self.daily_summaries[batch_start:batch_start + batch_size]
            lines = [f"📅 <b>DAILY BREAKDOWN ({batch_start + 1}-{batch_start + len(batch)})</b>\n"]
            for d in batch:
                emoji = "🟢" if d['pnl_r'] >= 0 else "🔴"
                lines.append(f"{emoji} {d['date']} | {d['trades']} trades | <b>{d['pnl_r']:+.2f}R</b>")
            send_telegram_message("\n".join(lines))
            time.sleep(0.5)


# ===================================================================
# MAIN
# ===================================================================
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("RIJIN v3.0.1 — 3-MONTH BACKTEST (AI-FILTERED)")
    print("Signal Engine → AI Validator → Telegram Alert")
    print("=" * 60 + "\n")

    backtester = RijinBacktester()
    backtester.run_backtest()

    print("\n✅ Backtest complete. Check Telegram for full report.")
