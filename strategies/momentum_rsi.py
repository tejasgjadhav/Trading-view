"""
Momentum + RSI Strategy
─────────────────────────────────────────────────────────────────────────────
Combines Jesse Livermore's price momentum principles with modern RSI and MACD.
Livermore: "The big money is made in the big swings of the market."

Rules:
  BUY  → RSI recovering from oversold (<35), MACD bullish cross, price momentum +
  SELL → RSI entering overbought (>70), MACD bearish cross, momentum stalls
  Filter: 12-month price momentum > 0 (only trade stocks going up over the year)
"""

import pandas as pd
import numpy as np


class MomentumRSIStrategy:
    name = "Momentum + RSI (Jesse Livermore Style)"
    short_name = "momentum_rsi"

    def __init__(self, rsi_period: int = 14, rsi_oversold: int = 35, rsi_overbought: int = 70):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought

    def _rsi(self, close: pd.Series) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(self.rsi_period).mean()
        loss = (-delta.clip(upper=0)).rolling(self.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def _macd(self, close: pd.Series):
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal
        return macd, signal, histogram

    def compute_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df["rsi"] = self._rsi(df["Close"])
        df["macd"], df["macd_sig"], df["macd_hist"] = self._macd(df["Close"])

        # 12-month momentum filter (Livermore only trades with the trend)
        df["momentum_12m"] = df["Close"] / df["Close"].shift(252) - 1
        df["momentum_3m"] = df["Close"] / df["Close"].shift(63) - 1
        df["momentum_1m"] = df["Close"] / df["Close"].shift(21) - 1

        # MACD bullish/bearish crossovers
        df["macd_bull_cross"] = (df["macd"] > df["macd_sig"]) & (df["macd"].shift(1) <= df["macd_sig"].shift(1))
        df["macd_bear_cross"] = (df["macd"] < df["macd_sig"]) & (df["macd"].shift(1) >= df["macd_sig"].shift(1))

        # RSI recovery from oversold
        df["rsi_recovery"] = (df["rsi"] > self.rsi_oversold) & (df["rsi"].shift(1) <= self.rsi_oversold)
        df["rsi_overbought_hit"] = df["rsi"] > self.rsi_overbought

        # Composite score
        df["signal"] = 0
        df["score"] = 0.0

        long_term_bull = df["momentum_12m"] > 0
        medium_bull = df["momentum_3m"] > 0

        # BUY conditions
        buy_rsi = df["rsi_recovery"] & df["macd_bull_cross"]
        buy_momentum = df["macd_bull_cross"] & (df["rsi"] < 60) & long_term_bull & medium_bull

        df.loc[buy_rsi | buy_momentum, "signal"] = 1

        # SELL conditions
        sell_cond = df["rsi_overbought_hit"] | df["macd_bear_cross"]
        df.loc[sell_cond, "signal"] = -1

        # Score: normalized RSI contribution + MACD histogram
        rsi_score = (df["rsi"] - 50) / 50  # -1 to 1 from overbought to oversold (inverted)
        rsi_score = -rsi_score  # flip: low RSI = bullish opportunity
        macd_score = np.sign(df["macd_hist"]) * np.minimum(abs(df["macd_hist"]) / (df["Close"] * 0.01), 1)
        momentum_score = df["momentum_3m"].clip(-0.5, 0.5) * 2

        df["score"] = ((rsi_score + macd_score + momentum_score) / 3).clip(-1, 1).fillna(0)

        return df[["signal", "score", "rsi", "macd", "macd_sig"]]

    def get_signal(self, df: pd.DataFrame) -> dict:
        result = self.compute_signals(df)
        latest = result.iloc[-1]
        return {
            "strategy": self.short_name,
            "signal": int(latest["signal"]),
            "score": float(latest["score"]),
            "rsi": float(latest["rsi"]),
            "macd": float(latest["macd"]),
        }
