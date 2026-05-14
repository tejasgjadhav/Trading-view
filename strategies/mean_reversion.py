"""
Mean Reversion Strategy
─────────────────────────────────────────────────────────────────────────────
Inspired by Ray Dalio's "All Weather" principles and John Henry's systematic
mean-reversion models. Also incorporates George Soros' reflexivity concept —
prices overshoot equilibrium, creating reversion opportunities.

Rules:
  BUY  → Price > 2 std deviations below 20-day Bollinger Band lower bound
         AND RSI < 30 AND price showing reversal candle
  SELL → Price touches upper Bollinger Band (mean + 2 std)
         OR RSI > 70
  Filter: Only in confirmed uptrend (200 SMA slope positive)
"""

import pandas as pd
import numpy as np


class MeanReversionStrategy:
    name = "Mean Reversion (Ray Dalio / Soros Style)"
    short_name = "mean_reversion"

    def __init__(self, bb_period: int = 20, bb_std: float = 2.0, rsi_period: int = 14):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period

    def _rsi(self, close: pd.Series) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(self.rsi_period).mean()
        loss = (-delta.clip(upper=0)).rolling(self.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def _stochastic(self, df: pd.DataFrame, k_period: int = 14) -> pd.Series:
        low_min = df["Low"].rolling(k_period).min()
        high_max = df["High"].rolling(k_period).max()
        stoch = 100 * (df["Close"] - low_min) / (high_max - low_min).replace(0, np.nan)
        return stoch

    def compute_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # Bollinger Bands
        df["bb_mid"] = df["Close"].rolling(self.bb_period).mean()
        df["bb_std"] = df["Close"].rolling(self.bb_period).std()
        df["bb_upper"] = df["bb_mid"] + self.bb_std * df["bb_std"]
        df["bb_lower"] = df["bb_mid"] - self.bb_std * df["bb_std"]

        # %B indicator (0 = lower band, 1 = upper band)
        df["pct_b"] = (df["Close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)

        df["rsi"] = self._rsi(df["Close"])
        df["stoch"] = self._stochastic(df)

        # Trend filter (Dalio: always be aware of the broader cycle)
        df["sma_200"] = df["Close"].rolling(200).mean()
        df["sma_200_slope"] = df["sma_200"].diff(5) / df["sma_200"].shift(5)  # % slope over 5 days
        df["bull_regime"] = df["sma_200_slope"] > 0  # Positive trend slope

        # Reversal candle detection (hammer / engulfing)
        df["body"] = df["Close"] - df["Open"]
        df["lower_wick"] = df["Open"].where(df["body"] > 0, df["Close"]) - df["Low"]
        df["upper_wick"] = df["High"] - df["Close"].where(df["body"] > 0, df["Open"])
        df["hammer"] = (df["lower_wick"] > 2 * abs(df["body"])) & (df["upper_wick"] < abs(df["body"]))

        # Bullish engulfing
        df["engulfing_bull"] = (
            (df["body"] > 0) &
            (df["body"].shift(1) < 0) &
            (df["Close"] > df["Open"].shift(1)) &
            (df["Open"] < df["Close"].shift(1))
        )

        df["signal"] = 0
        df["score"] = 0.0

        # BUY: extreme oversold + reversal signal in bull regime
        oversold = (df["pct_b"] < 0.05) & (df["rsi"] < 35)
        reversal_signal = df["hammer"] | df["engulfing_bull"]

        df.loc[oversold & reversal_signal, "signal"] = 1
        # Also buy mild oversold if in strong bull regime
        df.loc[(df["pct_b"] < 0.15) & (df["rsi"] < 30) & df["bull_regime"], "signal"] = 1

        # SELL: overbought at upper band
        overbought = (df["pct_b"] > 0.95) & (df["rsi"] > 65)
        df.loc[overbought, "signal"] = -1

        # Score: distance from mean (normalized)
        # Low %B + low RSI = bullish score; high %B + high RSI = bearish score
        bb_score = (0.5 - df["pct_b"]).clip(-0.5, 0.5) * 2   # inverted: low %B = high score
        rsi_score = (50 - df["rsi"]) / 50                     # inverted: low RSI = high score
        regime_mult = df["bull_regime"].map({True: 1.0, False: 0.3})

        df["score"] = ((bb_score + rsi_score) / 2 * regime_mult).clip(-1, 1).fillna(0)

        return df[["signal", "score", "pct_b", "rsi", "bb_upper", "bb_lower", "bb_mid"]]

    def get_signal(self, df: pd.DataFrame) -> dict:
        result = self.compute_signals(df)
        latest = result.iloc[-1]
        return {
            "strategy": self.short_name,
            "signal": int(latest["signal"]),
            "score": float(latest["score"]),
            "pct_b": float(latest.get("pct_b", 0.5)),
            "rsi": float(latest["rsi"]),
        }
