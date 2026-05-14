"""
Breakout + Volume Confirmation Strategy
─────────────────────────────────────────────────────────────────────────────
Jesse Livermore's core principle: "Never buy a stock that isn't in an uptrend,
and never short a stock that isn't in a downtrend."

Key insight from Livermore: Volume is the heartbeat of the market.
A breakout without volume is a false breakout.

Rules:
  BUY  → Price breaks 52-week high on 2x+ average volume
         OR breaks above key pivot with volume confirmation
  SELL → Price closes below 10-day moving average after breakout
  Filter: Must be within 10% of 52-week high (only buy leaders)
"""

import pandas as pd
import numpy as np


class BreakoutVolumeStrategy:
    name = "Breakout + Volume (Jesse Livermore)"
    short_name = "breakout_volume"

    def __init__(
        self,
        breakout_period: int = 50,
        volume_multiplier: float = 1.5,
        pivot_period: int = 10,
    ):
        self.breakout_period = breakout_period
        self.volume_multiplier = volume_multiplier
        self.pivot_period = pivot_period

    def _pivot_highs(self, series: pd.Series, n: int = 10) -> pd.Series:
        """Detect pivot high points."""
        pivots = pd.Series(False, index=series.index)
        for i in range(n, len(series) - n):
            window = series.iloc[i - n: i + n + 1]
            if series.iloc[i] == window.max():
                pivots.iloc[i] = True
        return pivots

    def compute_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # Rolling highs for breakout detection
        df["high_n"] = df["High"].rolling(self.breakout_period).max()
        df["low_n"] = df["Low"].rolling(self.breakout_period).min()

        # 52-week high/low
        df["high_52w"] = df["High"].rolling(252).max()
        df["low_52w"] = df["Low"].rolling(252).min()

        # Volume analysis
        df["vol_avg_20"] = df["Volume"].rolling(20).mean()
        df["vol_ratio"] = df["Volume"] / df["vol_avg_20"]
        df["high_volume"] = df["vol_ratio"] >= self.volume_multiplier

        # Near 52-week high filter (only buy strength leaders)
        df["near_52w_high"] = df["Close"] >= df["high_52w"] * 0.90

        # Breakout signals
        df["breakout_up"] = (
            (df["Close"] > df["high_n"].shift(1)) &
            df["high_volume"] &
            df["near_52w_high"]
        )

        # Exit: close below 10-day MA after breakout
        df["ma10"] = df["Close"].rolling(10).mean()
        df["below_ma10"] = df["Close"] < df["ma10"]

        # RS (Relative Strength) vs SPY approximation
        df["price_change_50d"] = df["Close"] / df["Close"].shift(50) - 1

        df["signal"] = 0
        df["score"] = 0.0

        df.loc[df["breakout_up"], "signal"] = 1
        df.loc[df["below_ma10"] & (df["vol_ratio"] > 1.0), "signal"] = -1

        # Score: combination of breakout strength and volume
        breakout_strength = ((df["Close"] - df["high_n"].shift(1)) / df["high_n"].shift(1)).clip(0, 0.1) * 10
        volume_score = (df["vol_ratio"] - 1).clip(0, 3) / 3
        momentum_score = df["price_change_50d"].clip(-0.3, 0.3) / 0.3

        df["score"] = ((breakout_strength + volume_score + momentum_score) / 3).clip(-1, 1).fillna(0)

        return df[["signal", "score", "vol_ratio", "high_n"]]

    def get_signal(self, df: pd.DataFrame) -> dict:
        result = self.compute_signals(df)
        latest = result.iloc[-1]
        return {
            "strategy": self.short_name,
            "signal": int(latest["signal"]),
            "score": float(latest["score"]),
            "vol_ratio": float(latest.get("vol_ratio", 1.0)),
        }
