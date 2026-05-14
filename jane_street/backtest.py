"""
2-Year Backtester
─────────────────────────────────────────────────────────────────────────────
Runs BEFORE any live recommendation.
If win rate < 80% → agent does NOT trade today.
Strategies backtested: ORB, VWAP, MOMENTUM
Saves reports/backtest_TICKER_STRATEGY_DATE.csv
"""
import os, json, warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
from datetime import datetime
from jane_street.data_fetcher import fetch_historical
from jane_street.config import (
    BACKTEST_PERIOD_YEARS, MIN_WIN_RATE_THRESHOLD,
    COMMISSION_PER_TRADE, SLIPPAGE_PERCENT,
    MIN_REWARD_RISK, ONLY_BUY, BT_CACHE_PATH, REPORTS_DIR
)


def run_backtest(ticker: str, strategy: str = "ORB") -> dict:
    """
    2-year daily backtest.
    Returns dict with win_rate, sharpe, drawdown, passed (bool).
    """
    try:
        df = fetch_historical(ticker, years=BACKTEST_PERIOD_YEARS)
    except Exception as e:
        return {"ticker": ticker, "strategy": strategy, "win_rate": 0,
                "total_trades": 0, "passed": False, "error": str(e)}

    trades      = []
    equity      = 1.0
    equity_curve = [1.0]

    for i in range(30, len(df) - 1):
        prev  = df.iloc[i - 1]
        today = df.iloc[i]

        pdc = float(prev["Close"])
        pdh = float(prev["High"])
        pdl = float(prev["Low"])

        open_p  = float(today["Open"])
        high_p  = float(today["High"])
        low_p   = float(today["Low"])
        close_p = float(today["Close"])

        orb_high = open_p * 1.002
        orb_low  = open_p * 0.998

        entry = stop = target = direction = None

        if strategy == "ORB":
            if high_p > orb_high * 1.001:
                entry     = orb_high * (1 + SLIPPAGE_PERCENT)
                direction = "LONG"
                stop      = orb_low
                risk      = entry - stop
                target    = entry + risk * MIN_REWARD_RISK
            elif not ONLY_BUY and low_p < orb_low * 0.999:
                entry     = orb_low * (1 - SLIPPAGE_PERCENT)
                direction = "SHORT"
                stop      = orb_high
                risk      = stop - entry
                target    = entry - risk * MIN_REWARD_RISK

        elif strategy == "VWAP":
            vwap_approx = (high_p + low_p + close_p) / 3
            dev = (open_p - vwap_approx) / vwap_approx
            if dev < -0.005:
                entry     = open_p * (1 + SLIPPAGE_PERCENT)
                direction = "LONG"
                stop      = low_p * 0.998
                risk      = entry - stop
                target    = vwap_approx
                if risk <= 0 or (target - entry) / risk < MIN_REWARD_RISK:
                    entry = None
            elif not ONLY_BUY and dev > 0.005:
                entry     = open_p * (1 - SLIPPAGE_PERCENT)
                direction = "SHORT"
                stop      = high_p * 1.002
                risk      = stop - entry
                target    = vwap_approx
                if risk <= 0 or (entry - target) / risk < MIN_REWARD_RISK:
                    entry = None

        elif strategy == "MOMENTUM":
            window = df.iloc[:i]
            ema9   = float(window["Close"].ewm(span=9).mean().iloc[-1])
            t5     = float(df.iloc[i - 5]["Close"])
            trend  = (pdc - t5) / t5 if t5 > 0 else 0
            if trend > 0.01 and open_p > ema9:
                entry     = open_p * (1 + SLIPPAGE_PERCENT)
                direction = "LONG"
                stop      = ema9 * 0.997
                risk      = entry - stop
                target    = entry + risk * MIN_REWARD_RISK

        if entry is None or direction is None or stop is None or target is None:
            continue
        if entry <= 0 or stop <= 0 or target <= 0:
            continue

        comm = COMMISSION_PER_TRADE * 2 / entry

        if direction == "LONG":
            if high_p >= target:
                pnl_pct = (target - entry) / entry - comm
                outcome = "WIN"
            elif low_p <= stop:
                pnl_pct = (stop - entry) / entry - comm
                outcome = "LOSS"
            else:
                pnl_pct = (close_p - entry) / entry - comm
                outcome = "PARTIAL"
        else:
            if low_p <= target:
                pnl_pct = (entry - target) / entry - comm
                outcome = "WIN"
            elif high_p >= stop:
                pnl_pct = (entry - stop) / entry - comm
                outcome = "LOSS"
            else:
                pnl_pct = (entry - close_p) / entry - comm
                outcome = "PARTIAL"

        trades.append({
            "date":      str(today.name.date()) if hasattr(today.name, 'date') else str(today.name),
            "ticker":    ticker,
            "strategy":  strategy,
            "direction": direction,
            "entry":     round(entry, 2),
            "target":    round(target, 2),
            "stop":      round(stop, 2),
            "outcome":   outcome,
            "pnl_pct":   round(pnl_pct * 100, 3),
        })
        equity *= (1 + pnl_pct)
        equity_curve.append(equity)

    if not trades:
        return {"ticker": ticker, "strategy": strategy, "win_rate": 0,
                "total_trades": 0, "passed": False}

    df_t    = pd.DataFrame(trades)
    wins    = df_t[df_t["outcome"] == "WIN"]
    losses  = df_t[df_t["outcome"] == "LOSS"]

    win_rate = len(wins) / len(df_t)
    avg_win  = float(wins["pnl_pct"].mean())   if len(wins)   > 0 else 0
    avg_loss = float(abs(losses["pnl_pct"].mean())) if len(losses) > 0 else 1
    pf       = (avg_win * len(wins)) / (avg_loss * max(len(losses), 1))

    eq_s         = pd.Series(equity_curve)
    drawdown     = (eq_s - eq_s.cummax()) / eq_s.cummax()
    max_dd       = float(drawdown.min()) * 100
    daily_ret    = eq_s.pct_change().dropna()
    sharpe       = float(daily_ret.mean() / daily_ret.std() * (252 ** 0.5)) if daily_ret.std() > 0 else 0

    result = {
        "ticker":               ticker,
        "strategy":             strategy,
        "win_rate":             round(win_rate, 4),
        "total_trades":         len(df_t),
        "wins":                 len(wins),
        "losses":               len(losses),
        "avg_return_pct":       round(float(df_t["pnl_pct"].mean()), 3),
        "max_drawdown_pct":     round(max_dd, 2),
        "sharpe_ratio":         round(sharpe, 3),
        "profit_factor":        round(pf, 2),
        "final_equity_x":       round(equity, 3),
        "passed":               win_rate >= MIN_WIN_RATE_THRESHOLD,
    }

    # Save CSV report
    os.makedirs(REPORTS_DIR, exist_ok=True)
    csv_path = f"{REPORTS_DIR}/bt_{ticker.replace('.NS','')}_{strategy}_{datetime.today().strftime('%Y%m%d')}.csv"
    df_t.to_csv(csv_path, index=False)

    return result


def run_all_backtests(tickers: list, strategies: list = ["ORB", "VWAP", "MOMENTUM"]) -> pd.DataFrame:
    """Run all combos. Return only those that passed ≥80% win rate, sorted by Sharpe."""
    results = []
    for ticker in tickers:
        for strat in strategies:
            try:
                r = run_backtest(ticker, strat)
                results.append({k: v for k, v in r.items()})
            except Exception as e:
                pass

    if not results:
        return pd.DataFrame()

    df_r = pd.DataFrame(results)
    df_r = df_r[df_r["passed"] == True].sort_values("sharpe_ratio", ascending=False)
    return df_r


def load_or_run_backtest(tickers: list, force_fresh: bool = False) -> pd.DataFrame:
    """
    Load cached Sunday backtest if available and recent (<7 days).
    Otherwise re-run.
    """
    from datetime import date, timedelta

    if not force_fresh and os.path.exists(BT_CACHE_PATH):
        try:
            with open(BT_CACHE_PATH) as f:
                cached = json.load(f)
            cache_date = datetime.fromisoformat(cached.get("run_date", "2000-01-01"))
            age_days   = (datetime.now() - cache_date).days
            if age_days < 7:
                df = pd.DataFrame(cached["results"])
                df = df[df["passed"] == True].sort_values("sharpe_ratio", ascending=False)
                print(f"  [BACKTEST] Using cached results from {cache_date.strftime('%d %b')} ({age_days}d old) — {len(df)} strategies passed")
                return df
        except:
            pass

    print(f"  [BACKTEST] Running fresh 2-year backtest on {len(tickers)} stocks × 3 strategies...")
    df = run_all_backtests(tickers, ["ORB", "VWAP", "MOMENTUM"])

    # Cache results
    os.makedirs("results", exist_ok=True)
    with open(BT_CACHE_PATH, "w") as f:
        json.dump({
            "run_date": datetime.now().isoformat(),
            "results":  df.to_dict("records") if not df.empty else [],
        }, f, indent=2, default=str)

    return df
