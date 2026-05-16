"""
AVCM Signal Engine — Adaptive Volume-Confirmed Momentum
5 factors, ALL must be true simultaneously for a BUY signal.

Factors:
  1. Structural Breakout  — 5-min bar CLOSES above ORB High (close, not wick)
  2. Volume Confirmation  — Signal bar volume ≥ 2× per-bar average of ORB period
  3. VWAP Position        — Price above today's anchored VWAP
  4. RSI Momentum Window  — RSI between 55 and 72 (momentum zone, not overextended)
  5. Market Alignment     — Nifty 50 is positive from its own open

Retest bonus: if price broke ORB High earlier, pulled back to VWAP (within 0.5%),
and is now breaking again with volume — is_retest = True → +25% position size.
"""
import pandas as pd
import numpy as np
from engine.config import (
    RSI_PERIOD, RSI_MOMENTUM_LOW, RSI_MOMENTUM_HIGH,
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
                    entry_bar_idx: int = 5,
                    nifty_pct: float = None) -> dict:
    """
    AVCM 5-factor signal engine.

    Returns:
    {
        direction:        "LONG" | "NEUTRAL"
        signals_aligned:  int  (0–5; must be 5 for LONG)
        confidence:       float (0–1; 1.0 = all 5 fired)
        signals_detail:   dict  (factor → 1 if True, 0 if False)
        is_retest:        bool  (True → retest pattern, +25% size bonus)
        regime:           str
        current_price, vwap, orb_high, orb_low, rsi, ema_fast, ema_slow, vol_ratio
    }

    nifty_pct: % change of Nifty from its open right now.
               If None, Factor 5 (Market Alignment) is not checked
               and defaults to True (conservative: don't block on missing data).
    """
    signals = {}

    if df_intraday.empty or len(df_intraday) < 6:
        return {
            "direction": "NEUTRAL", "signals_aligned": 0,
            "confidence": 0, "signals_detail": {}, "is_retest": False,
            "regime": "UNKNOWN", "current_price": 0, "vwap": 0,
            "orb_high": 0, "orb_low": 0, "rsi": 50,
            "ema_fast": 0, "ema_slow": 0, "vol_ratio": 0,
        }

    # ── ORB window: bars 0–5 (9:15–9:44 AM) ────────────────────────────────
    orb_idx   = min(5, len(df_intraday) - 1)
    entry_idx = (len(df_intraday) - 1) if entry_bar_idx < 0 else min(entry_bar_idx, len(df_intraday) - 1)

    or_bars   = df_intraday.iloc[:orb_idx + 1]
    orb_high  = float(or_bars["High"].max())
    orb_low   = float(or_bars["Low"].min())

    # Entry: LIMIT at ORB High + 0.1% (AVCM execution rule)
    limit_entry   = round(orb_high * 1.001, 2)
    current_price = float(df_intraday.iloc[entry_idx]["Close"])

    # VWAP anchored to entry window
    vwap_window  = df_intraday.iloc[:entry_idx + 1]
    vwap_series  = compute_vwap(vwap_window)
    current_vwap = float(vwap_series.iloc[-1])

    # RSI up to entry bar
    rsi_val = compute_rsi(df_intraday["Close"].iloc[:entry_idx + 1])

    # EMA (for regime context only)
    entry_close = df_intraday["Close"].iloc[:entry_idx + 1]
    ema_fast_v  = float(entry_close.ewm(span=EMA_FAST, adjust=False).mean().iloc[-1])
    ema_slow_v  = float(entry_close.ewm(span=EMA_SLOW, adjust=False).mean().iloc[-1])

    # Per-bar average volume during ORB period (AVCM Volume Confirmation)
    orb_vols     = df_intraday["Volume"].iloc[:orb_idx + 1]
    n_orb_bars   = max(len(orb_vols), 1)
    orb_per_bar_avg = float(orb_vols.sum()) / n_orb_bars
    signal_bar_vol  = float(df_intraday["Volume"].iloc[entry_idx])
    vol_ratio_orb   = round(signal_bar_vol / orb_per_bar_avg, 2) if orb_per_bar_avg > 0 else 0

    # Daily volume ratio (for scoring / quality gates)
    avg_vol_daily = df_intraday["Volume"].rolling(10, min_periods=3).mean()
    avg_v_daily   = float(avg_vol_daily.iloc[max(entry_idx - 1, 0)]) if not avg_vol_daily.empty else 1
    if pd.isna(avg_v_daily) or avg_v_daily <= 0:
        avg_v_daily = max(float(df_intraday["Volume"].iloc[:entry_idx].mean()), 1)
    vol_ratio_daily = round(signal_bar_vol / avg_v_daily, 2) if avg_v_daily > 0 else 0

    # ── Factor 1: Structural Breakout ────────────────────────────────────────
    # Price CLOSES above ORB High (close, not just wick)
    signals["structural_breakout"] = 1 if current_price > orb_high else 0

    # ── Factor 2: Volume Confirmation ────────────────────────────────────────
    # Signal bar volume ≥ 2× per-bar average from ORB period
    signals["volume_confirm"] = 1 if vol_ratio_orb >= VOLUME_SURGE_MULTIPLIER else 0

    # ── Factor 3: VWAP Position ──────────────────────────────────────────────
    signals["vwap_position"] = 1 if current_price > current_vwap else 0

    # ── Factor 4: RSI Momentum Window ────────────────────────────────────────
    # RSI must be 55–72: momentum building, not overbought
    signals["rsi_momentum"] = 1 if RSI_MOMENTUM_LOW <= rsi_val <= RSI_MOMENTUM_HIGH else 0

    # ── Factor 5: Market Alignment ───────────────────────────────────────────
    # Nifty 50 must be positive from its open
    if nifty_pct is None:
        signals["market_align"] = 1  # skip if data unavailable (conservative)
    else:
        signals["market_align"] = 1 if nifty_pct > 0 else 0

    # ── Retest Pattern Detection ─────────────────────────────────────────────
    # Earlier bar broke ORB High → pulled back to VWAP ± 0.5% → now breaking again
    is_retest = False
    if entry_idx >= 8 and orb_high > 0:
        prev_bars = df_intraday.iloc[orb_idx:entry_idx]  # bars after ORB, before signal
        vwap_prev = compute_vwap(df_intraday.iloc[:entry_idx])

        had_prev_breakout = any(float(prev_bars["Close"].iloc[i]) > orb_high
                                for i in range(len(prev_bars)))
        if had_prev_breakout:
            # Check if price touched VWAP (within 0.5%) between breakout and now
            for i in range(len(prev_bars)):
                bar_close = float(prev_bars["Close"].iloc[i])
                vwap_at_bar = float(vwap_prev.iloc[orb_idx + i]) if orb_idx + i < len(vwap_prev) else current_vwap
                near_vwap = abs(bar_close - vwap_at_bar) / vwap_at_bar < 0.005
                if near_vwap:
                    is_retest = True
                    break

    # ── Aggregate ────────────────────────────────────────────────────────────
    long_count = sum(1 for v in signals.values() if v == 1)
    # ALL 5 must fire for LONG (AVCM rule: 4/5 is NOT a signal)
    direction = "LONG" if long_count >= MIN_SIGNALS_REQUIRED else "NEUTRAL"

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

    return {
        "direction":        direction,
        "signals_aligned":  long_count,
        "confidence":       round(long_count / 5.0, 2),   # 5 factors total
        "signals_detail":   signals,
        "is_retest":        is_retest,
        "regime":           regime,
        "current_price":    current_price,
        "limit_entry":      limit_entry,    # AVCM: ORB High + 0.1%
        "vwap":             round(current_vwap, 2),
        "orb_high":         round(orb_high, 2),
        "orb_low":          round(orb_low, 2),
        "rsi":              round(rsi_val, 1),
        "ema_fast":         round(ema_fast_v, 2),
        "ema_slow":         round(ema_slow_v, 2),
        "vol_ratio":        vol_ratio_daily,      # daily avg ratio (for quality gate)
        "vol_ratio_orb":    vol_ratio_orb,        # per-bar ORB ratio (Factor 2)
    }
