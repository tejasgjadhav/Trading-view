"""
Signal Engine — 7 signals, need ≥ MIN_SIGNALS_REQUIRED aligned.

Signals:
  1. PDC Position    — is price above/below prev day close?
  2. ORB Breakout    — broke above/below 9:15–9:45 range?
  3. VWAP Position   — above VWAP = bullish, with deviation check
  4. RSI             — oversold → long, overbought → short
  5. EMA Trend       — fast EMA vs slow EMA
  6. Volume Spike    — is volume 1.5x+ above avg? (confirmation)
  7. Key Level Test  — near PDH (resistance) or PDL (support)?
"""
import pandas as pd
import numpy as np
from engine.config import (
    RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT,
    EMA_FAST, EMA_SLOW, VWAP_DEVIATION_THRESHOLD,
    VOLUME_SURGE_MULTIPLIER, MIN_SIGNALS_REQUIRED, ONLY_BUY
)


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Anchored VWAP from market open each day."""
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    return (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()


def compute_rsi(close: pd.Series, period: int = RSI_PERIOD) -> float:
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0


def compute_signals(df_daily: pd.DataFrame, df_intraday: pd.DataFrame,
                    pdh: float, pdl: float, pdc: float,
                    entry_bar_idx: int = 5) -> dict:
    """
    Returns:
    {
        direction: "LONG" | "NEUTRAL"  (only LONG since ONLY_BUY=True)
        signals_aligned: int
        confidence: float 0–1
        signals_detail: dict
        regime: str
        current_price, vwap, orb_high, orb_low, rsi, ema_fast, ema_slow
    }
    """
    signals = {}

    min_bars = entry_bar_idx + 1
    if df_intraday.empty or len(df_intraday) < 6:
        return {"direction": "NEUTRAL", "signals_aligned": 0,
                "confidence": 0, "signals_detail": {}, "regime": "UNKNOWN"}

    # ── ORB window: bars 0-5 (9:15–9:44 AM opening range) ───────────────────
    # entry_bar_idx=-1 → use latest available bar (continuous/dynamic mode).
    # entry_bar_idx=N  → anchor to specific bar (backcompat for fixed-time runs).
    orb_idx   = min(5, len(df_intraday) - 1)
    entry_idx = (len(df_intraday) - 1) if entry_bar_idx < 0 else min(entry_bar_idx, len(df_intraday) - 1)
    current_price = float(df_intraday.iloc[entry_idx]["Close"])

    # 1. PDC Position
    signals["above_pdc"] = 1 if current_price > pdc else -1

    # 2. ORB Breakout (first 6 bars of 5-min = 30 min = 9:15–9:45)
    or_bars  = df_intraday.iloc[:orb_idx + 1]
    orb_high = float(or_bars["High"].max())
    orb_low  = float(or_bars["Low"].min())
    if current_price > orb_high:
        signals["orb"] = 1
    elif current_price < orb_low:
        signals["orb"] = -1
    else:
        signals["orb"] = 0

    # 3. VWAP — anchored to the entry window (9:45 AM = bars 0-5; 11 AM = bars 0-20)
    vwap_window  = df_intraday.iloc[:entry_idx + 1]
    vwap         = compute_vwap(vwap_window)
    current_vwap = float(vwap.iloc[-1])
    deviation    = (current_price - current_vwap) / current_vwap
    signals["vwap"] = 1 if current_price > current_vwap else -1

    # 4. RSI — computed up to entry bar
    rsi_val = compute_rsi(df_intraday["Close"].iloc[:entry_idx + 1])
    if rsi_val < RSI_OVERSOLD:
        signals["rsi"] = 1
    elif rsi_val > RSI_OVERBOUGHT:
        signals["rsi"] = -1
    else:
        signals["rsi"] = 0

    # 5. EMA Trend — computed up to entry bar
    entry_close  = df_intraday["Close"].iloc[:entry_idx + 1]
    ema_fast_s   = entry_close.ewm(span=EMA_FAST, adjust=False).mean()
    ema_slow_s   = entry_close.ewm(span=EMA_SLOW, adjust=False).mean()
    ema_fast_v   = float(ema_fast_s.iloc[-1])
    ema_slow_v   = float(ema_slow_s.iloc[-1])
    signals["ema_trend"] = 1 if ema_fast_v > ema_slow_v else -1

    # 6. Volume Spike — compare entry bar volume against average of prior bars
    avg_vol = df_intraday["Volume"].iloc[:entry_idx].rolling(10, min_periods=3).mean()
    cur_vol = float(df_intraday["Volume"].iloc[entry_idx])
    avg_v   = float(avg_vol.iloc[-1]) if not avg_vol.empty and not pd.isna(avg_vol.iloc[-1]) and avg_vol.iloc[-1] > 0 else 1
    signals["volume_spike"] = 1 if cur_vol > VOLUME_SURGE_MULTIPLIER * avg_v else 0

    # 7. Key Level
    tol = 0.002
    near_pdh = abs(current_price - pdh) / pdh < tol
    near_pdl = abs(current_price - pdl) / pdl < tol
    if near_pdh:
        signals["key_level"] = -1   # resistance
    elif near_pdl:
        signals["key_level"] = 1    # support bounce
    else:
        signals["key_level"] = 0

    # Aggregate
    long_count  = sum(1 for v in signals.values() if v == 1)
    short_count = sum(1 for v in signals.values() if v == -1)

    # ONLY_BUY: never go short
    if ONLY_BUY:
        if long_count >= MIN_SIGNALS_REQUIRED:
            direction = "LONG"
            aligned   = long_count
        else:
            direction = "NEUTRAL"
            aligned   = long_count
    else:
        if long_count >= MIN_SIGNALS_REQUIRED and long_count > short_count:
            direction = "LONG"
            aligned   = long_count
        elif short_count >= MIN_SIGNALS_REQUIRED and short_count > long_count:
            direction = "SHORT"
            aligned   = short_count
        else:
            direction = "NEUTRAL"
            aligned   = 0

    # Regime from daily ATR
    regime = "RANGE"
    if len(df_daily) > 30:
        hi, lo, cl = df_daily["High"], df_daily["Low"], df_daily["Close"]
        tr  = pd.concat([hi - lo, abs(hi - cl.shift(1)), abs(lo - cl.shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        if not atr.empty and not pd.isna(atr.iloc[-1]):
            cur_atr = float(atr.iloc[-1])
            avg_atr = float(atr.rolling(30).mean().iloc[-1])
            if not pd.isna(avg_atr) and avg_atr > 0:
                if cur_atr > 1.5 * avg_atr:
                    regime = "VOLATILE"
                elif abs(current_price - pdc) / pdc > 0.005:
                    regime = "TRENDING"

    vol_ratio = round(cur_vol / avg_v, 2)

    return {
        "direction":        direction,
        "signals_aligned":  aligned,
        "long_signals":     long_count,
        "short_signals":    short_count,
        "confidence":       round(aligned / 7.0, 2),
        "signals_detail":   signals,
        "regime":           regime,
        "current_price":    current_price,   # always 9:45 AM price
        "vwap":             round(current_vwap, 2),
        "orb_high":         round(orb_high, 2),
        "orb_low":          round(orb_low, 2),
        "rsi":              round(rsi_val, 1),
        "ema_fast":         round(ema_fast_v, 2),
        "ema_slow":         round(ema_slow_v, 2),
        "vol_ratio":        vol_ratio,
    }
