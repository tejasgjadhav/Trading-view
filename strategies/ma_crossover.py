"""
Moving Average Crossover Strategy
─────────────────────────────────────────────────────────────────────────────
Inspired by Paul Tudor Jones & Stanley Druckenmiller macro trend following.
PTJ famously uses the 200-day MA as his primary trend filter —
"I don't want to own anything below its 200-day moving average."

Rules:
  Trend Filter: Price > 200 SMA (bullish regime)
  BUY  → 20 EMA crosses above 50 EMA + price > 200 SMA + volume surge
  SELL → 20 EMA crosses below 50 EMA OR price < 200 SMA
  ADD  → Golden Cross (50 SMA > 200 SMA) — strong confirmation
"""

import pandas as pd
import numpy as np


class MACrossoverStrategy:
    name = "MA Crossover (Paul Tudor Jones / Druckenmiller)"
    short_name = "ma_crossover"

    def __init__(self, fast: int = 20, slow: int = 50, trend: int = 200):
        self.fast = fast
        self.slow = slow
        self.trend = trend

    def compute_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df["ema_fast"] = df["Close"].ewm(span=self.fast, adjust=False).mean()
        df["sma_slow"] = df["Close"].rolling(self.slow).mean()
        df["sma_trend"] = df["Close"].rolling(self.trend).mean()

        # Volume average for confirmation
        df["vol_avg"] = df["Volume"].rolling(20).mean()
        df["vol_surge"] = df["Volume"] > df["vol_avg"] * 1.2

        # Crossover detection
        df["cross_above"] = (df["ema_fast"] > df["sma_slow"]) & (df["ema_fast"].shift(1) <= df["sma_slow"].shift(1))
        df["cross_below"] = (df["ema_fast"] < df["sma_slow"]) & (df["ema_fast"].shift(1) >= df["sma_slow"].shift(1))

        # Golden / Death cross
        df["golden_cross"] = (df["sma_slow"] > df["sma_trend"]) & (df["sma_slow"].shift(1) <= df["sma_trend"].shift(1))
        df["death_cross"] = (df["sma_slow"] < df["sma_trend"]) & (df["sma_slow"].shift(1) >= df["sma_trend"].shift(1))

        df["signal"] = 0
        df["score"] = 0.0

        above_trend = df["Close"] > df["sma_trend"]

        # BUY: fast crosses slow from below, price above 200 SMA
        df.loc[df["cross_above"] & above_trend, "signal"] = 1
        # SELL: fast crosses slow from above OR price drops below 200 SMA
        df.loc[df["cross_below"] | (~above_trend & (df["signal"].shift(1) == 1)), "signal"] = -1

        # Score based on MA alignment
        # +1 when fast >> slow >> trend, -1 when reversed
        fast_slow_gap = (df["ema_fast"] - df["sma_slow"]) / df["sma_slow"]
        slow_trend_gap = (df["sma_slow"] - df["sma_trend"]) / df["sma_trend"]
        df["score"] = (fast_slow_gap + slow_trend_gap).clip(-1, 1) * 5  # amplify
        df["score"] = df["score"].clip(-1, 1).fillna(0)

        return df[["signal", "score"]]

    def get_signal(self, df: pd.DataFrame) -> dict:
        result = self.compute_signals(df)
        latest = result.iloc[-1]
        return {
            "strategy": self.short_name,
            "signal": int(latest["signal"]),
            "score": float(latest["score"]),
        }
