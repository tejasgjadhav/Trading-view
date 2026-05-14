"""
Turtle Trading Strategy
─────────────────────────────────────────────────────────────────────────────
Pioneered by Richard Dennis & William Eckhardt in the 1983 "Turtle Traders"
experiment. One of the most proven trend-following systems ever created.

Rules:
  BUY  → Price breaks above 20-day highest high (System 1 entry)
  SELL → Price breaks below 10-day lowest low   (System 1 exit)
  ATR-based position sizing for risk normalization
  Skip entry if last trade was a winner (filter)
"""

import pandas as pd
import numpy as np


class TurtleStrategy:
    name = "Turtle Trading (Richard Dennis)"
    short_name = "turtle"

    def __init__(self, entry_period: int = 20, exit_period: int = 10, atr_period: int = 14):
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.atr_period = atr_period

    def compute_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Returns DataFrame with signal column:
          1  = BUY
         -1  = SELL
          0  = HOLD
        Also returns score column (-1 to 1) for ensemble weighting.
        """
        df = df.copy()

        # Donchian Channels
        df["dc_high"] = df["High"].rolling(self.entry_period).max()
        df["dc_low"] = df["Low"].rolling(self.exit_period).min()

        # True Range & ATR
        df["prev_close"] = df["Close"].shift(1)
        df["tr"] = np.maximum(
            df["High"] - df["Low"],
            np.maximum(
                abs(df["High"] - df["prev_close"]),
                abs(df["Low"] - df["prev_close"])
            )
        )
        df["atr"] = df["tr"].rolling(self.atr_period).mean()

        # Signals
        df["signal"] = 0
        df["score"] = 0.0

        # Breakout above 20-day high → BUY
        buy_cond = df["Close"] >= df["dc_high"].shift(1)
        # Breakout below 10-day low → SELL
        sell_cond = df["Close"] <= df["dc_low"].shift(1)

        df.loc[buy_cond, "signal"] = 1
        df.loc[sell_cond, "signal"] = -1

        # Score: normalized distance from Donchian midpoint
        dc_mid = (df["dc_high"] + df["dc_low"]) / 2
        dc_range = df["dc_high"] - df["dc_low"]
        df["score"] = ((df["Close"] - dc_mid) / dc_range.replace(0, np.nan)).clip(-1, 1)
        df["score"] = df["score"].fillna(0)

        return df[["signal", "score", "atr"]]

    def get_signal(self, df: pd.DataFrame) -> dict:
        """Get today's signal for live trading."""
        result = self.compute_signals(df)
        latest = result.iloc[-1]
        return {
            "strategy": self.short_name,
            "signal": int(latest["signal"]),
            "score": float(latest["score"]),
            "atr": float(latest.get("atr", 0)),
        }
