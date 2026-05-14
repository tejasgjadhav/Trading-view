"""
Risk Manager — Kelly sizing, daily loss limits.
Core principle: position SIZING is the strategy.
"""
import math
from engine.config import (
    CAPITAL, MAX_RISK_PER_TRADE, DAILY_LOSS_LIMIT,
    KELLY_FRACTION, MIN_REWARD_RISK
)


class RiskManager:
    def __init__(self, capital: float = CAPITAL):
        self.capital    = capital
        self.daily_pnl  = 0.0
        self.trades_today = 0

    def can_trade(self) -> tuple:
        """Returns (allowed: bool, reason: str)."""
        loss_pct = self.daily_pnl / self.capital
        if loss_pct <= -DAILY_LOSS_LIMIT:
            return False, f"Daily loss limit hit ({loss_pct:.1%}). No more trades today."
        return True, "OK"

    def kelly_position(self, win_rate: float, entry: float, stop: float) -> dict:
        """
        25% fractional Kelly position sizing.
        Kelly: f* = (p*b - q) / b   where b = reward/risk ratio
        """
        p = win_rate
        q = 1 - p
        b = MIN_REWARD_RISK  # 2:1

        full_kelly = (p * b - q) / b
        frac_kelly = max(0.0, min(full_kelly * KELLY_FRACTION, 0.20))  # cap 20%

        risk_per_share  = abs(entry - stop)
        max_risk_amount = self.capital * MAX_RISK_PER_TRADE
        kelly_amount    = self.capital * frac_kelly

        position_amount = min(max_risk_amount, kelly_amount)
        shares = math.floor(position_amount / risk_per_share) if risk_per_share > 0 else 0
        shares = max(shares, 1)

        return {
            "shares":          shares,
            "position_value":  round(shares * entry, 2),
            "risk_amount":     round(shares * risk_per_share, 2),
            "risk_pct":        round((shares * risk_per_share / self.capital) * 100, 2),
            "kelly_pct":       round(frac_kelly * 100, 2),
            "full_kelly_pct":  round(full_kelly * 100, 2),
        }

    def update(self, pnl: float):
        self.daily_pnl    += pnl
        self.trades_today += 1

    def reset(self):
        self.daily_pnl    = 0.0
        self.trades_today = 0
