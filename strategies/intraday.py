"""
Intraday Strategy — Opening Range Breakout + VWAP
─────────────────────────────────────────────────────────────────────────────
The most battle-tested intraday strategy for NSE India.

Logic (signal at 9:45 AM after market settles):
  1. Opening Range = 9:15–9:30 (first 15 min) High and Low
  2. BUY  → Price breaks ABOVE the opening range high at 9:30–9:45
             AND price is above VWAP (institutional trend)
             AND volume on breakout bar is 1.5x+ 5-bar average
  3. SELL → Price breaks BELOW the opening range low at 9:30–9:45
             AND price is below VWAP
             AND volume confirmation
  4. HOLD → No clean breakout or conflicting signals

Risk Management (intraday):
  Stop Loss   = Opposite side of Opening Range
  Target      = Entry + 1.5 × Opening Range size
  Hard exit   = 3:15 PM regardless (never hold overnight)

Stock picker:
  Scans top 10 liquid Nifty stocks, returns ONE best call ranked by:
  breakout strength × volume surge × VWAP alignment
"""

import pandas as pd
import numpy as np
from datetime import datetime, time
import pytz

IST = pytz.timezone("Asia/Kolkata")


def calc_vwap(df: pd.DataFrame) -> pd.Series:
    """Volume Weighted Average Price — resets each day."""
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    return (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()


def calc_orb_signal(df_1min: pd.DataFrame) -> dict:
    """
    Given 1-minute intraday bars for today, compute ORB signal at 9:45.
    df_1min must have DatetimeIndex in IST with columns: Open High Low Close Volume
    """
    if df_1min.empty or len(df_1min) < 5:
        return {"action": "HOLD", "reason": "insufficient data", "score": 0}

    # Ensure index is IST
    if df_1min.index.tz is None:
        df_1min.index = df_1min.index.tz_localize(IST)
    elif str(df_1min.index.tz) != "Asia/Kolkata":
        df_1min.index = df_1min.index.tz_convert(IST)

    today = df_1min.index[-1].date()

    # Opening Range: 9:15 AM – 9:30 AM
    t_open  = pd.Timestamp(today).tz_localize(IST).replace(hour=9, minute=15)
    t_range_end = pd.Timestamp(today).tz_localize(IST).replace(hour=9, minute=30)
    t_signal    = pd.Timestamp(today).tz_localize(IST).replace(hour=9, minute=44)

    or_bars = df_1min[t_open:t_range_end]
    if len(or_bars) < 3:
        return {"action": "HOLD", "reason": "opening range not formed", "score": 0}

    or_high = float(or_bars["High"].max())
    or_low  = float(or_bars["Low"].min())
    or_size = or_high - or_low

    if or_size <= 0:
        return {"action": "HOLD", "reason": "zero opening range", "score": 0}

    # Signal bar: latest bar up to 9:45
    signal_bars = df_1min[t_range_end:]
    if signal_bars.empty:
        return {"action": "HOLD", "reason": "no data after 9:30", "score": 0}

    latest = signal_bars.iloc[-1]
    current_price = float(latest["Close"])

    # VWAP for today
    vwap = float(calc_vwap(df_1min).iloc[-1])

    # Volume surge: compare signal bar to opening range avg
    or_avg_vol = float(or_bars["Volume"].mean()) if len(or_bars) > 0 else 1
    signal_vol = float(latest["Volume"])
    vol_ratio  = signal_vol / or_avg_vol if or_avg_vol > 0 else 1.0

    # Breakout detection
    broke_above = current_price > or_high
    broke_below = current_price < or_low
    above_vwap  = current_price > vwap
    below_vwap  = current_price < vwap

    # --- BUY signal ---
    if broke_above and above_vwap and vol_ratio >= 1.2:
        breakout_strength = (current_price - or_high) / or_size
        score = min(breakout_strength * vol_ratio, 1.0)
        target   = or_high + 1.5 * or_size
        stoploss = or_low
        return {
            "action":    "BUY",
            "score":     round(score, 4),
            "entry":     round(current_price, 2),
            "target":    round(target, 2),
            "stoploss":  round(stoploss, 2),
            "or_high":   round(or_high, 2),
            "or_low":    round(or_low, 2),
            "or_size":   round(or_size, 2),
            "vwap":      round(vwap, 2),
            "vol_ratio": round(vol_ratio, 2),
            "reason":    f"ORB breakout above ₹{or_high:.1f}, VWAP={vwap:.1f}, vol {vol_ratio:.1f}x",
        }

    # --- SELL signal ---
    if broke_below and below_vwap and vol_ratio >= 1.2:
        breakout_strength = (or_low - current_price) / or_size
        score = -min(breakout_strength * vol_ratio, 1.0)
        target   = or_low - 1.5 * or_size
        stoploss = or_high
        return {
            "action":    "SELL",
            "score":     round(score, 4),
            "entry":     round(current_price, 2),
            "target":    round(target, 2),
            "stoploss":  round(stoploss, 2),
            "or_high":   round(or_high, 2),
            "or_low":    round(or_low, 2),
            "or_size":   round(or_size, 2),
            "vwap":      round(vwap, 2),
            "vol_ratio": round(vol_ratio, 2),
            "reason":    f"ORB breakdown below ₹{or_low:.1f}, VWAP={vwap:.1f}, vol {vol_ratio:.1f}x",
        }

    return {
        "action":  "HOLD",
        "score":   0,
        "entry":   round(current_price, 2),
        "or_high": round(or_high, 2),
        "or_low":  round(or_low, 2),
        "vwap":    round(vwap, 2),
        "reason":  "no clean breakout",
    }


def backtest_orb_intraday(df_5min: pd.DataFrame, capital: float = 100_000) -> dict:
    """
    Backtest ORB on 5-minute historical data (up to 60 days available from yfinance).
    Groups by date, simulates signal at 9:45, exit at 3:15.
    Returns daily P&L records.
    """
    if df_5min.empty:
        return {"trades": [], "final_equity": capital, "total_return_pct": 0}

    if df_5min.index.tz is None:
        df_5min.index = df_5min.index.tz_localize(IST)
    elif str(df_5min.index.tz) != "Asia/Kolkata":
        df_5min.index = df_5min.index.tz_convert(IST)

    dates   = sorted(set(df_5min.index.date))
    equity  = capital
    trades  = []

    for day in dates:
        day_ts  = pd.Timestamp(day).tz_localize(IST)
        day_df  = df_5min[df_5min.index.date == day].copy()
        if len(day_df) < 6:
            continue

        # Opening range: 9:15–9:30
        or_bars = day_df.between_time("09:15", "09:30")
        if len(or_bars) < 2:
            continue
        or_high = float(or_bars["High"].max())
        or_low  = float(or_bars["Low"].min())
        or_size = or_high - or_low
        if or_size <= 0:
            continue

        # Signal: first bar at or after 9:45
        signal_bars = day_df.between_time("09:45", "09:50")
        if signal_bars.empty:
            signal_bars = day_df.between_time("09:30", "10:00").iloc[2:]
        if signal_bars.empty:
            continue

        sig_bar = signal_bars.iloc[0]
        entry_price = float(sig_bar["Close"])
        vwap = float(calc_vwap(day_df.loc[:sig_bar.name]).iloc[-1])

        # Volume check
        or_avg_vol = float(or_bars["Volume"].mean()) if len(or_bars) > 0 else 1
        sig_vol    = float(sig_bar["Volume"])
        vol_ratio  = sig_vol / or_avg_vol if or_avg_vol > 0 else 1.0

        broke_above = entry_price > or_high
        broke_below = entry_price < or_low

        direction = None
        stoploss  = 0.0
        target    = 0.0

        if broke_above and entry_price > vwap and vol_ratio >= 1.2:
            direction = "BUY"
            stoploss  = or_low
            target    = or_high + 1.5 * or_size
        elif broke_below and entry_price < vwap and vol_ratio >= 1.2:
            direction = "SELL"
            stoploss  = or_high
            target    = or_low - 1.5 * or_size
        else:
            trades.append({
                "date":     str(day),
                "action":   "HOLD",
                "pnl_pct":  0.0,
                "pnl_inr":  0.0,
                "equity":   round(equity, 0),
                "reason":   "no signal",
            })
            continue

        # Simulate intraday: check each bar after entry for SL/target/EOD exit
        post_entry = day_df.between_time("09:45", "15:15")
        exit_price  = float(day_df.between_time("15:10", "15:30").iloc[-1]["Close"]) if not day_df.between_time("15:10", "15:30").empty else entry_price
        exit_reason = "eod"

        for _, bar in post_entry.iterrows():
            if direction == "BUY":
                if bar["Low"] <= stoploss:
                    exit_price  = stoploss
                    exit_reason = "stoploss"
                    break
                if bar["High"] >= target:
                    exit_price  = target
                    exit_reason = "target"
                    break
            else:  # SELL
                if bar["High"] >= stoploss:
                    exit_price  = stoploss
                    exit_reason = "stoploss"
                    break
                if bar["Low"] <= target:
                    exit_price  = target
                    exit_reason = "target"
                    break

        # P&L calculation (use 80% of equity as position)
        position_size = equity * 0.80
        shares = position_size / entry_price
        if direction == "BUY":
            raw_pnl = (exit_price - entry_price) * shares
        else:
            raw_pnl = (entry_price - exit_price) * shares

        brokerage = position_size * 0.0006  # 0.06% round trip (Zerodha intraday)
        net_pnl   = raw_pnl - brokerage
        pnl_pct   = net_pnl / equity * 100
        equity   += net_pnl

        trades.append({
            "date":        str(day),
            "action":      direction,
            "entry":       round(entry_price, 2),
            "exit":        round(exit_price, 2),
            "exit_reason": exit_reason,
            "or_high":     round(or_high, 2),
            "or_low":      round(or_low, 2),
            "stoploss":    round(stoploss, 2),
            "target":      round(target, 2),
            "pnl_pct":     round(pnl_pct, 2),
            "pnl_inr":     round(net_pnl, 0),
            "equity":      round(equity, 0),
        })

    total_return = (equity / capital - 1) * 100
    return {
        "trades":           trades,
        "final_equity":     round(equity, 0),
        "total_return_pct": round(total_return, 2),
        "capital":          capital,
    }
