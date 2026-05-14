"""
Performance Metrics Calculator
─────────────────────────────────────────────────────────────────────────────
Industry-standard metrics used by hedge funds and professional traders:
  - Sharpe Ratio (risk-adjusted return)
  - Sortino Ratio (downside risk only)
  - Max Drawdown (worst peak-to-trough)
  - CAGR (compound annual growth)
  - Win Rate, Profit Factor, Expectancy
  - Calmar Ratio (CAGR / Max Drawdown)
"""

import pandas as pd
import numpy as np
from typing import List, Dict


def compute_metrics(result: dict, benchmark_annual_return: float = 0.10) -> dict:
    """
    Compute comprehensive performance metrics from backtest result.

    Args:
        result: Output from BacktestEngine.run()
        benchmark_annual_return: Annual return of benchmark (default: 10% for S&P 500)
    """
    trades = result["trades"]
    equity_curve = result["equity_curve"]
    initial_capital = result["initial_capital"]
    final_equity = result["final_equity"]

    if not trades:
        return _empty_metrics(result)

    # ─── Trade Statistics ────────────────────────────────────────────────────
    pnls = [t["pnl"] for t in trades]
    pnl_pcts = [t["pnl_pct"] for t in trades]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]

    win_rate = len(winners) / len(trades) if trades else 0
    avg_win = np.mean(winners) if winners else 0
    avg_loss = abs(np.mean(losers)) if losers else 0
    profit_factor = (sum(winners) / abs(sum(losers))) if losers and sum(losers) != 0 else float("inf")
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    # ─── Equity Curve Analysis ───────────────────────────────────────────────
    equity_values = pd.Series([e["equity"] for e in equity_curve])
    equity_dates = pd.to_datetime([e["date"] for e in equity_curve])

    # Daily returns
    daily_returns = equity_values.pct_change().dropna()

    # CAGR
    days = (equity_dates[-1] - equity_dates[0]).days
    years = days / 365.25
    cagr = ((final_equity / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0

    # Max Drawdown
    rolling_max = equity_values.cummax()
    drawdown = (equity_values - rolling_max) / rolling_max
    max_drawdown = drawdown.min() * 100  # negative value

    # Sharpe Ratio (annualized, risk-free ≈ 5%)
    risk_free_daily = 0.05 / 252
    excess_returns = daily_returns - risk_free_daily
    sharpe = (excess_returns.mean() / excess_returns.std() * np.sqrt(252)) if excess_returns.std() > 0 else 0

    # Sortino Ratio (uses only downside deviation)
    downside_returns = daily_returns[daily_returns < risk_free_daily]
    downside_std = downside_returns.std() * np.sqrt(252)
    sortino = ((daily_returns.mean() - risk_free_daily) * 252 / downside_std) if downside_std > 0 else 0

    # Calmar Ratio
    calmar = (cagr / abs(max_drawdown)) if max_drawdown != 0 else 0

    # Volatility (annualized)
    volatility = daily_returns.std() * np.sqrt(252) * 100

    # Best / Worst trade
    best_trade = max(pnl_pcts) if pnl_pcts else 0
    worst_trade = min(pnl_pcts) if pnl_pcts else 0

    # Average holding period
    holding_periods = []
    for t in trades:
        try:
            entry = pd.to_datetime(t["entry_date"])
            exit_ = pd.to_datetime(t["exit_date"])
            holding_periods.append((exit_ - entry).days)
        except Exception:
            pass
    avg_holding_days = int(np.mean(holding_periods)) if holding_periods else 0

    # Exit reason breakdown
    exit_reasons = {}
    for t in trades:
        reason = t.get("exit_reason", "unknown")
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

    return {
        "total_return_pct": round(result["total_return_pct"], 2),
        "cagr_pct": round(cagr, 2),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "calmar_ratio": round(calmar, 3),
        "max_drawdown_pct": round(max_drawdown, 2),
        "volatility_pct": round(volatility, 2),
        "total_trades": len(trades),
        "win_rate_pct": round(win_rate * 100, 1),
        "avg_win_pct": round(np.mean(pnl_pcts) if pnl_pcts else 0, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy_usd": round(expectancy, 2),
        "best_trade_pct": round(best_trade, 2),
        "worst_trade_pct": round(worst_trade, 2),
        "avg_holding_days": avg_holding_days,
        "exit_reasons": exit_reasons,
        "initial_capital": initial_capital,
        "final_equity": final_equity,
    }


def _empty_metrics(result: dict) -> dict:
    return {
        "total_return_pct": result.get("total_return_pct", 0),
        "cagr_pct": 0,
        "sharpe_ratio": 0,
        "sortino_ratio": 0,
        "calmar_ratio": 0,
        "max_drawdown_pct": 0,
        "volatility_pct": 0,
        "total_trades": 0,
        "win_rate_pct": 0,
        "avg_win_pct": 0,
        "profit_factor": 0,
        "expectancy_usd": 0,
        "best_trade_pct": 0,
        "worst_trade_pct": 0,
        "avg_holding_days": 0,
        "exit_reasons": {},
        "initial_capital": result.get("initial_capital", 100000),
        "final_equity": result.get("final_equity", 100000),
    }


def format_metrics_table(metrics: dict) -> str:
    """Format metrics as a readable table for reports/README."""
    lines = [
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Return | {metrics['total_return_pct']:+.1f}% |",
        f"| CAGR | {metrics['cagr_pct']:+.1f}% |",
        f"| Sharpe Ratio | {metrics['sharpe_ratio']:.3f} |",
        f"| Sortino Ratio | {metrics['sortino_ratio']:.3f} |",
        f"| Calmar Ratio | {metrics['calmar_ratio']:.3f} |",
        f"| Max Drawdown | {metrics['max_drawdown_pct']:.1f}% |",
        f"| Volatility (Ann.) | {metrics['volatility_pct']:.1f}% |",
        f"| Total Trades | {metrics['total_trades']} |",
        f"| Win Rate | {metrics['win_rate_pct']:.1f}% |",
        f"| Profit Factor | {metrics['profit_factor']:.2f} |",
        f"| Expectancy | ${metrics['expectancy_usd']:.2f} |",
        f"| Best Trade | {metrics['best_trade_pct']:+.1f}% |",
        f"| Worst Trade | {metrics['worst_trade_pct']:+.1f}% |",
        f"| Avg Holding | {metrics['avg_holding_days']} days |",
        f"| Final Equity | ${metrics['final_equity']:,.0f} |",
    ]
    return "\n".join(lines)
