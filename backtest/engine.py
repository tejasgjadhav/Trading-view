"""
Vectorized Backtesting Engine
─────────────────────────────────────────────────────────────────────────────
Simulates trading with realistic costs: commission, slippage, position sizing.
Supports stop-loss, take-profit, and trailing stops.
"""

import pandas as pd
import numpy as np
from typing import Optional
from config import (
    INITIAL_CAPITAL, POSITION_SIZE_PCT, COMMISSION_PCT,
    SLIPPAGE_PCT, STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRAILING_STOP_PCT
)


class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = INITIAL_CAPITAL,
        position_size_pct: float = POSITION_SIZE_PCT,
        commission_pct: float = COMMISSION_PCT,
        slippage_pct: float = SLIPPAGE_PCT,
        stop_loss_pct: float = STOP_LOSS_PCT,
        take_profit_pct: float = TAKE_PROFIT_PCT,
        trailing_stop_pct: float = TRAILING_STOP_PCT,
    ):
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct

    def run(self, df: pd.DataFrame, signals: pd.Series) -> dict:
        """
        Run backtest on a single asset.

        Args:
            df: OHLCV DataFrame with DatetimeIndex
            signals: Series of signals (1=BUY, -1=SELL, 0=HOLD)

        Returns:
            dict with equity curve, trades, and metrics
        """
        capital = self.initial_capital
        position = 0          # shares held
        entry_price = 0.0
        highest_price = 0.0   # for trailing stop
        trades = []
        equity = []

        closes = df["Close"].values
        highs = df["High"].values
        lows = df["Low"].values
        dates = df.index

        for i, (date, close, high, low) in enumerate(zip(dates, closes, highs, lows)):
            signal = signals.iloc[i] if i < len(signals) else 0
            current_equity = capital + position * close
            equity.append({"date": str(date.date()), "equity": round(current_equity, 2)})

            if position > 0:
                # Check stop-loss
                stop_price = entry_price * (1 - self.stop_loss_pct)
                # Trailing stop: follows highest price
                trail_price = highest_price * (1 - self.trailing_stop_pct)
                effective_stop = max(stop_price, trail_price)

                # Check take-profit
                tp_price = entry_price * (1 + self.take_profit_pct)

                # Update highest price
                if high > highest_price:
                    highest_price = high

                # Exits: stop loss, take profit, or sell signal
                if low <= effective_stop or high >= tp_price or signal == -1:
                    if low <= effective_stop:
                        exit_price = effective_stop * (1 - self.slippage_pct)
                        exit_reason = "stop_loss"
                    elif high >= tp_price:
                        exit_price = tp_price * (1 - self.slippage_pct)
                        exit_reason = "take_profit"
                    else:
                        exit_price = close * (1 - self.slippage_pct)
                        exit_reason = "signal"

                    proceeds = position * exit_price * (1 - self.commission_pct)
                    pnl = proceeds - (position * entry_price * (1 + self.commission_pct))
                    pnl_pct = pnl / (position * entry_price) * 100

                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": str(date.date()),
                        "entry_price": round(entry_price, 2),
                        "exit_price": round(exit_price, 2),
                        "shares": position,
                        "pnl": round(pnl, 2),
                        "pnl_pct": round(pnl_pct, 2),
                        "exit_reason": exit_reason,
                    })

                    capital += proceeds
                    position = 0
                    entry_price = 0.0
                    highest_price = 0.0

            elif position == 0 and signal == 1:
                # BUY: enter position
                trade_capital = capital * self.position_size_pct
                buy_price = close * (1 + self.slippage_pct)
                cost_per_share = buy_price * (1 + self.commission_pct)
                shares = int(trade_capital / cost_per_share)

                if shares > 0:
                    cost = shares * cost_per_share
                    if cost <= capital:
                        capital -= cost
                        position = shares
                        entry_price = buy_price
                        entry_date = str(date.date())
                        highest_price = high

        # Close any open position at end
        if position > 0:
            exit_price = closes[-1] * (1 - self.slippage_pct)
            proceeds = position * exit_price * (1 - self.commission_pct)
            pnl = proceeds - (position * entry_price * (1 + self.commission_pct))
            trades.append({
                "entry_date": entry_date,
                "exit_date": str(dates[-1].date()),
                "entry_price": round(entry_price, 2),
                "exit_price": round(exit_price, 2),
                "shares": position,
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl / (position * entry_price) * 100, 2),
                "exit_reason": "end_of_period",
            })
            capital += proceeds

        final_equity = capital
        equity_series = pd.Series(
            [e["equity"] for e in equity],
            index=pd.to_datetime([e["date"] for e in equity])
        )

        return {
            "initial_capital": self.initial_capital,
            "final_equity": round(final_equity, 2),
            "total_return_pct": round((final_equity / self.initial_capital - 1) * 100, 2),
            "trades": trades,
            "equity_curve": equity,
        }
