# KiteAlerts Trading Logic - Complete Code-Level Documentation

## 🎯 NIFTY STRATEGY - FULL DETAILED LOGIC

### 📊 STEP 1: 30-Minute Trend Detection

#### 1.1 Data Requirements

- **Minimum candles**: 55 completed 30-minute candles
- **If < 55 candles**: Return `NEUTRAL`, exit

#### 1.2 Indicator Calculations

**EMA20 Calculation:**

```
closes = [close_price for each 30m candle]
ema20[0] = closes[0]
alpha = 2 / (20 + 1) = 0.0952

for i in 1 to length:
    ema20[i] = (closes[i] * alpha) + (ema20[i-1] * (1 - alpha))
```

**EMA50 Calculation:**

```
alpha50 = 2 / (50 + 1) = 0.0392
Same logic as EMA20
```

**ATR14 Calculation:**

```
TR[0] = high[0] - low[0]

for i in 1 to length:
    TR[i] = MAX(
        high[i] - low[i],
        ABS(high[i] - close[i-1]),
        ABS(low[i] - close[i-1])
    )

ATR = EMA(TR, period=14)
```

**ATR_MA20 Calculation:**

```
ATR_MA20 = EMA(ATR values, period=20)
```

**Slope Calculation:**

```
lookback = 3
slope = ema20[-1] - ema20[-4]
```

**Average 30m Slope (for filters):**

```
slopes_hist = []
for i in 0 to 19:
    slope_i = ABS(ema20[-(i+1)] - ema20[-(i+4)])
    slopes_hist.append(slope_i)

avg_30m_slope = SUM(slopes_hist) / 20
```

#### 1.3 Trend Definition Logic

```
P = closes[-1]  (Latest close)
E20 = ema20[-1]
E50 = ema50[-1]
ATR = atr[-1]
ATR_MA = atr_ma20[-1]

BULLISH CONDITIONS (ALL must be true):
    1. P > E20
    2. E20 > E50
    3. slope > 0
    4. ATR > ATR_MA

BEARISH CONDITIONS (ALL must be true):
    1. P < E20
    2. E20 < E50
    3. slope < 0
    4. ATR > ATR_MA

Otherwise: NEUTRAL
```

#### 1.4 State Machine Transitions

```
IF new_trend != current_trend:
    current_trend = new_trend

    IF new_trend == NEUTRAL:
        leg_state = INITIAL
    ELSE:
        leg_state = NEW

    candles_since_new = 0
    mode_a_fired = False
    mode_b_fired = False

ELSE (trend unchanged):
    IF leg_state == NEW:
        candles_since_new += 1

        IF candles_since_new >= 10:
            leg_state = CONFIRMED
```

---

### ⚡ STEP 2: 5-Minute Analysis - Entry Logic

#### 2.1 Data Requirements

- **Minimum candles**: 30 completed 5-minute candles
- **If < 30 candles**: Return None, exit

#### 2.2 Indicator Calculations (5-Minute)

**EMA20 (5m):** Same formula as 30m, applied to 5m closes

**ATR14 (5m):** Same formula as 30m, applied to 5m H/L/C

**ATR_MA20 (5m):**

```
ATR_MA = EMA(atr values, period=20)
```

**RSI14 Calculation:**

```
period = 14
deltas = DIFF(closes)  # closes[i] - closes[i-1]

seed = deltas[0:15]
up = SUM(seed where seed >= 0) / period
down = -SUM(seed where seed < 0) / period

rs = up / down
rsi[0:14] = 100 - (100 / (1 + rs))

avg_up = up
avg_down = down

for i in period to length:
    delta = closes[i] - closes[i-1]

    IF delta > 0:
        upval = delta
        downval = 0
    ELSE:
        upval = 0
        downval = -delta

    avg_up = (avg_up * (period - 1) + upval) / period
    avg_down = (avg_down * (period - 1) + downval) / period

    rs = avg_up / avg_down
    rsi[i] = 100 - (100 / (1 + rs))
```

**Slope (5m):**

```
slope_5m = ema20[-1] - ema20[-4]
```

**Average 5m Slope:**

```
slopes_hist = []
for i in 0 to 19:
    slope_i = ABS(ema20[-(i+1)] - ema20[-(i+4)])
    slopes_hist.append(slope_i)

avg_5m_slope = SUM(slopes_hist) / 20
```

**Current Values:**

```
P = close[-1]     # Latest close
H = high[-1]      # Latest high
L = low[-1]       # Latest low
O = open[-1]      # Latest open
E20 = ema20[-1]
ATR = atr[-1]
RSI = rsi[-1]
CURR_DATE = date[-1]
```

#### 2.3 Daily Reset Check

```
IF last_trade_day != CURR_DATE.date():
    daily_trades = 0
    daily_pnl_r = 0.0
    mode_c_losses = 0
    last_trade_day = CURR_DATE.date()
    mode_a_fired = False
    mode_b_fired = False
    leg_state = INITIAL

    PRINT "🔄 NIFTY DAILY RESET: {date}"
```

#### 2.4 Global Filters (ALL must pass)

```
1. TRADING HOURS CHECK:
   t_now = CURR_DATE.time()
   IF NOT (09:30 <= t_now <= 15:15):
       RETURN None

2. DAILY TRADE LIMIT:
   IF daily_trades >= 7:
       RETURN None

3. DAILY PNL LIMIT:
   IF daily_pnl_r <= -1.5:
       RETURN None

4. MINIMUM ATR:
   IF ATR < 5.0:
       RETURN None

IF any filter fails: RETURN None, exit analysis
```

#### 2.5 Direction Flags

```
is_bullish = (c30_trend == BULLISH)
is_bearish = (c30_trend == BEARISH)

LOCAL OVERRIDE (if 30m = NEUTRAL):
    IF slope_5m > 0 AND P > E20:
        is_bullish = True

    ELIF slope_5m < 0 AND P < E20:
        is_bearish = True
```

---

### 🚀 MODE A: FRESH TREND ENTRY

#### Conditions to Check Mode A:

```
1. leg_state == NEW
2. mode_a_fired == False
3. signal == None (no prior mode triggered)
```

#### Mode A Logic - BULLISH

```
check_range = 10
valid_freshness = False

STEP 1: Count candles above/below EMA20 in last 10 candles
    count_above = 0
    count_below = 0

    for i in range(len(closes[-11:-1])):
        index = -11 + i
        IF closes[index] > ema20[index]:
            count_above += 1
        ELSE:
            count_below += 1

STEP 2: Freshness Check
    IF count_above <= 3 AND count_below >= 1:
        valid_freshness = True

STEP 3: Bullish Candle Check
    body_ratio = ABS(P - O) / (H - L) if (H - L) > 0 else 0

    IF valid_freshness AND P > E20 AND body_ratio >= 0.60 AND 56 <= RSI <= 72:
        signal = "BUY"
        mode = "MODE_A"
        pattern = "Fresh Trend Reclaim"
        sl_val = P - (1.2 * ATR)
        tp_val = P + (2.0 * ATR)

        mode_a_fired = True
        leg_state = CONFIRMED
```

#### Mode A Logic - BEARISH

```
STEP 1: Count candles
    count_below = 0
    count_above = 0

    for i in range(len(closes[-11:-1])):
        index = -11 + i
        IF closes[index] < ema20[index]:
            count_below += 1
        ELSE:
            count_above += 1

STEP 2: Freshness Check
    IF count_below <= 3 AND count_above >= 1:
        valid_freshness = True

STEP 3: Bearish Candle Check
    body_ratio = ABS(P - O) / (H - L) if (H - L) > 0 else 0

    IF valid_freshness AND P < E20 AND body_ratio >= 0.60 AND 28 <= RSI <= 44:
        signal = "SELL"
        mode = "MODE_A"
        pattern = "Fresh Trend Reclaim"
        sl_val = P + (1.2 * ATR)
        tp_val = P - (2.0 * ATR)

        mode_a_fired = True
        leg_state = CONFIRMED
```

---

### 🔄 MODE B: PULLBACK ENTRY

#### Conditions to Check Mode B:

```
1. signal == None (Mode A didn't trigger)
2. leg_state == CONFIRMED
3. (current_index - last_mode_b_idx) >= 2
```

#### Mode B Re-entry Tracking:

```
IF NOT hasattr(self, 'last_mode_b_idx'):
    last_mode_b_idx = -999

curr_idx = len(c5)

IF (curr_idx - last_mode_b_idx) >= 2:
    can_fire_b = True
ELSE:
    can_fire_b = False
```

#### Mode B Logic - BULLISH

```
IF signal == None AND can_fire_b AND is_bullish:

    pb_depth_ok = False
    time_pb_ok = False
    hold_bo_ok = False

    # Must be above EMA20
    IF P > E20:

        # CHECK 1: DEPTH-BASED PULLBACK
        dist = MAX(highs[-20:-1]) - MIN(lows[-5:])

        IF (0.05 * ATR) <= dist <= (0.5 * ATR):
            pb_depth_ok = True

        # CHECK 2: TIME-BASED PULLBACK
        # Last 4 candles within 0.3 ATR of EMA20
        devs = []
        for i in 1 to 4:
            dev = ABS(closes[-i] - ema20[-i])
            devs.append(dev)

        IF ALL(d < (0.3 * ATR) for d in devs):
            time_pb_ok = True

        # CHECK 3: EMA20 HOLD BREAKOUT
        # All last 5 closes above EMA20
        IF ALL(closes[-i] > ema20[-i] for i in 1 to 5):
            # Current breaks last 3 highs
            IF P > MAX(highs[-4:-1]):
                hold_bo_ok = True

        # REJECTION PATTERN CHECK
        is_rejection = (
            ((P - L) > (H - P) * 2) OR              # Long lower wick
            (P > highs[-2] AND closes[-2] < ema20[-2]) OR  # Previous rejection
            hold_bo_ok OR
            time_pb_ok
        )

        # FINAL ENTRY CONDITION
        IF (pb_depth_ok OR time_pb_ok OR hold_bo_ok) AND is_rejection AND 52 <= RSI <= 65:
            signal = "BUY"
            mode = "MODE_B"
            pattern = "Pullback Rejection"
            sl_val = P - (1.0 * ATR)
            tp_val = P + (1.5 * (P - sl_val))

            last_mode_b_idx = len(c5)
```

#### Mode B Logic - BEARISH

```
IF signal == None AND can_fire_b AND is_bearish:

    pb_depth_ok = False
    time_pb_ok = False
    hold_bo_ok = False

    # Must be below EMA20
    IF P < E20:

        # CHECK 1: DEPTH-BASED PULLBACK
        dist = MAX(highs[-5:]) - MIN(lows[-20:-1])

        IF (0.05 * ATR) <= dist <= (0.5 * ATR):
            pb_depth_ok = True

        # CHECK 2: TIME-BASED PULLBACK
        devs = []
        for i in 1 to 4:
            dev = ABS(closes[-i] - ema20[-i])
            devs.append(dev)

        IF ALL(d < (0.3 * ATR) for d in devs):
            time_pb_ok = True

        # CHECK 3: EMA20 HOLD BREAKDOWN
        IF ALL(closes[-i] < ema20[-i] for i in 1 to 5):
            IF P < MIN(lows[-4:-1]):
                hold_bo_ok = True

        # REJECTION PATTERN CHECK
        is_rejection = (
            ((H - P) > (P - L) * 2) OR              # Long upper wick
            (P < lows[-2] AND closes[-2] > ema20[-2]) OR
            hold_bo_ok OR
            time_pb_ok
        )

        # FINAL ENTRY CONDITION
        IF (pb_depth_ok OR time_pb_ok OR hold_bo_ok) AND is_rejection AND 35 <= RSI <= 48:
            signal = "SELL"
            mode = "MODE_B"
            pattern = "Pullback Rejection"
            sl_val = P + (1.0 * ATR)
            tp_val = P - (1.5 * (sl_val - P))

            last_mode_b_idx = len(c5)
```

---

### 🎯 MODE C: BREAKOUT/MOMENTUM ENTRY

#### Conditions to Check Mode C:

```
1. signal == None (Mode A & B didn't trigger)
2. mode_c_losses < 2
```

#### Early Mode C Enablement:

```
mode_c_allowed = (leg_state == CONFIRMED)

IF NOT mode_c_allowed AND leg_state == NEW:
    # Early enable if 3 consecutive candles on right side of EMA20
    IF is_bullish AND ALL(closes[-i] > ema20[-i] for i in 1 to 3):
        mode_c_allowed = True

    ELIF is_bearish AND ALL(closes[-i] < ema20[-i] for i in 1 to 3):
        mode_c_allowed = True
```

#### Special Window: Opening Range Breakout (ORB)

```
TIME WINDOW: 09:30 <= t_now <= 10:30

STEP 1: Get today's candles
    todays_candles = [candle for candle in c5 if candle.date.date() == CURR_DATE.date()]

STEP 2: Check we have at least 4 candles (3 closed + 1 current)
    IF len(todays_candles) >= 4:

        # Opening Range = First 3 candles (9:15, 9:20, 9:25)
        or_high = MAX(candle.high for candle in todays_candles[0:3])
        or_low = MIN(candle.low for candle in todays_candles[0:3])

        # BULLISH ORB BREAKOUT
        IF is_bullish AND P > or_high AND P > O:
            signal = "BUY"
            mode = "MODE_C"
            pattern = "ORB Breakout"
            sl_val = P - (0.5 * ATR)
            tp_val = P + (1.5 * (P - sl_val))

        # BEARISH ORB BREAKDOWN
        ELIF is_bearish AND P < or_low AND P < O:
            signal = "SELL"
            mode = "MODE_C"
            pattern = "ORB Breakdown"
            sl_val = P + (0.5 * ATR)
            tp_val = P - (1.2 * (sl_val - P))
```

#### Standard Mode C Logic:

```
IF signal == None AND mode_c_allowed AND mode_c_losses < 2:

    # RANGE CALCULATIONS
    rng_last_5 = MAX(highs[-5:]) - MIN(lows[-5:])

    micro_range_ok = (rng_last_5 < (0.6 * ATR))

    # MIDDAY WINDOW (12:00 - 13:30)
    midday_time = (12:00 <= t_now <= 13:30)
    midday_range_ok = (rng_last_5 < (0.7 * ATR))
    midday_ok = (midday_time AND midday_range_ok)

    # VOLATILITY CHECK
    vol_ok = (ATR > (0.95 * atr_ma[-1]) AND ABS(slope_5m) > (avg_5m_slope * 1.2))

    # AT LEAST ONE TRIGGER CONDITION MUST BE TRUE
    IF vol_ok OR micro_range_ok OR midday_ok:

        c_valid = False
        c_pattern = ""

        # ============ BULLISH MODE C ============
        IF is_bullish:

            # PATTERN 1: EMA TOUCH
            IF L <= E20 <= H AND P > E20 AND P > O:
                c_valid = True
                c_pattern = "EMA Touch"

            # PATTERN 2: INSIDE BAR BREAK
            IF highs[-2] < highs[-3] AND lows[-2] > lows[-3] AND P > highs[-2]:
                c_valid = True
                c_pattern = "Inside Bar Break"

            # PATTERN 3: MICRO RANGE BREAK
            IF micro_range_ok AND P > MAX(highs[-5:-1]):
                c_valid = True
                c_pattern = "Micro Range Break"

            # RSI CHECK
            IF c_valid AND 45 <= RSI <= 68:
                signal = "BUY"
                mode = "MODE_C"
                pattern = c_pattern
                sl_val = P - (0.8 * ATR)
                tp_val = P + (1.2 * (P - sl_val))

        # ============ BEARISH MODE C ============
        ELIF is_bearish:

            # PATTERN 1: EMA TOUCH
            IF L <= E20 <= H AND P < E20 AND P < O:
                c_valid = True
                c_pattern = "EMA Touch"

            # PATTERN 2: INSIDE BAR BREAK
            IF highs[-2] < highs[-3] AND lows[-2] > lows[-3] AND P < lows[-2]:
                c_valid = True
                c_pattern = "Inside Bar Break"

            # PATTERN 3: MICRO RANGE BREAK
            IF micro_range_ok AND P < MIN(lows[-5:-1]):
                c_valid = True
                c_pattern = "Micro Range Break"

            # RSI CHECK
            IF c_valid AND 32 <= RSI <= 55:
                signal = "SELL"
                mode = "MODE_C"
                pattern = c_pattern
                sl_val = P + (0.8 * ATR)
                tp_val = P - (1.2 * (sl_val - P))
```

---

### 📤 Signal Output

```
IF signal is not None:
    daily_trades += 1

    RETURN {
        "instrument": instrument_name,
        "mode": mode,
        "direction": signal,
        "entry": P,
        "sl": sl_val,
        "target": tp_val,
        "pattern": pattern,
        "rsi": RSI,
        "atr": ATR,
        "trend_state": c30_trend.name,
        "time": str(CURR_DATE)
    }

ELSE:
    RETURN None
```

---

## 🥇 GOLD STRATEGY - FULL DETAILED LOGIC

### 📊 30-Minute Trend Detection

#### Data Requirements

- **Minimum candles**: 55 completed 30-minute candles
- **If < 55 candles**: Return `NEUTRAL`

#### Trend Definition (SIMPLIFIED)

```
P = closes[-1]
E20 = ema20[-1]
E50 = ema50[-1]
slope = ema20[-1] - ema20[-4]

BULLISH: P > E20 > E50 AND slope > 0
BEARISH: P < E20 < E50 AND slope < 0
Otherwise: NEUTRAL
```

#### State Machine

```
IF new_trend != current_trend:
    current_trend = new_trend
    leg_state = NEW if new_trend != NEUTRAL else INITIAL
    trend_duration = 0
ELSE:
    trend_duration += 1
    IF leg_state == NEW AND trend_duration > 10:
        leg_state = CONFIRMED
```

---

### ⚡ 5-Minute Analysis - MODE C ONLY

#### Global Filters

```
1. TRADING HOURS: 14:00 <= t_now <= 23:30
2. 30M TREND: Must be BULLISH or BEARISH (not NEUTRAL)
3. EMA SEPARATION: ABS(P - E20) / P >= 0.0020 (0.20%)
4. ATR RISING: atr[-1] > EMA(atr, 5)[-1]
5. MOMENTUM: ABS(ema20[-1] - ema20[-4]) > 0.5
```

#### Entry Logic - BULLISH

```
recent_high = MAX(highs[-6:-1])

IF P > recent_high AND P > E20:
    signal = "BUY"
    mode = "MODE_C"
    pattern = "Expansion Breakout"

    sl_structural = MIN(lows[-2:])
    sl_val = MAX(sl_structural, P - (0.5 * ATR))  # Farther stop

    tp_val = P + (2.0 * (P - sl_val))
```

#### Entry Logic - BEARISH

```
recent_low = MIN(lows[-6:-1])

IF P < recent_low AND P < E20:
    signal = "SELL"
    mode = "MODE_C"
    pattern = "Expansion Breakdown"

    sl_structural = MAX(highs[-2:])
    sl_val = MIN(sl_structural, P + (0.5 * ATR))

    tp_val = P - (2.0 * (sl_val - P))
```

---

## 🤖 AI INTEGRATION

### Entry Analysis (Async)

```
Analyzes: Trend + RSI + ATR + Pattern
Returns: Confidence (1-10), Risk Level, Action, Reason
Telegram: "🤖 AI Risk Check" message
```

### Exit Analysis (Async)

```
Analyzes: Entry, Exit, Exit Type, Pattern
Returns: Reason, Lesson, Verdict
Telegram: "🤖 Post-Trade Review" message
```

---

## 📊 RISK MANAGEMENT

| Parameter         | Nifty     | Gold |
| ----------------- | --------- | ---- |
| Max Daily Trades  | 7         | N/A  |
| Max Daily Loss    | -1.5R     | N/A  |
| Min ATR           | 5.0       | N/A  |
| Mode C Max Losses | 2         | N/A  |
| Mode B Cooldown   | 2 candles | N/A  |

---

## 🎯 STOP LOSS & TARGET FORMULAS

### Nifty

| Mode | Stop Loss       | Target          |
| ---- | --------------- | --------------- |
| A    | Entry ± 1.2×ATR | Entry ± 2.0×ATR |
| B    | Entry ± 1.0×ATR | Entry ± 1.5R    |
| C    | Entry ± 0.8×ATR | Entry ± 1.2R    |
| ORB  | Entry ± 0.5×ATR | Entry ± 1.5R    |

### Gold

| Mode | Stop Loss                | Target       |
| ---- | ------------------------ | ------------ |
| C    | MIN/MAX(Recent, 0.5×ATR) | Entry ± 2.0R |

**Risk = |Entry - Stop_Loss|**
