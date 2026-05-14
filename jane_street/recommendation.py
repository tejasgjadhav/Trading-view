"""
Jane Street Recommendation Engine
─────────────────────────────────────────────────────────────────────────────
Outputs EXACTLY ONE of:
  BUY CASH — stock, entry, target, stop, shares, kelly sizing
  NO TRADE  — reason stated

Rules enforced:
  • Backtest >= 80% win rate (gate)
  • >= 3 of 7 signals aligned
  • Min 2:1 reward:risk
  • Min 1% expected return
  • LONG only (ONLY_BUY = True)
  • Kill switch at 2:00 PM IST
"""
import os, json
import pandas as pd
from datetime import datetime
import pytz

from jane_street.config import (
    CASH_EQUITIES, MIN_WIN_RATE_THRESHOLD, MIN_SIGNALS_REQUIRED,
    MIN_REWARD_RISK, MIN_RETURN_PCT, CAPITAL, KILL_SWITCH_TIME,
    ONLY_BUY, IST, CALLS_PATH
)
from jane_street.data_fetcher import fetch_historical, fetch_intraday, get_previous_day_levels
from jane_street.signals import compute_signals
from jane_street.backtest import load_or_run_backtest
from jane_street.risk_manager import RiskManager


def _no_trade(reason: str) -> dict:
    return {
        "action":    "NO_TRADE",
        "reason":    reason,
        "timestamp": datetime.now(IST).isoformat(),
    }


def generate_recommendation(force_fresh_backtest: bool = False) -> dict:
    """
    MAIN FUNCTION — call at 9:45 AM every trading day.
    Returns recommendation dict.
    """
    now_ist = datetime.now(IST)
    risk    = RiskManager(capital=CAPITAL)

    print(f"\n{'='*65}")
    print(f"  JANE STREET AGENT — {now_ist.strftime('%d %b %Y  %I:%M %p IST')}")
    print(f"  Capital: Rs.{CAPITAL:,.0f}  |  Rules: BUY only, >=80% WR, >=3/7 signals, 2:1 R:R")
    print(f"{'='*65}\n")

    # -- STEP 1: Backtest gate ---------------------------------------------
    print(f"[1/4] Loading backtest results (2-year, >=80% win rate gate)...")
    bt_df = load_or_run_backtest(CASH_EQUITIES, force_fresh=force_fresh_backtest)

    if bt_df.empty:
        return _no_trade(f"Zero strategies passed {MIN_WIN_RATE_THRESHOLD:.0%} win rate. No trade today.")

    print(f"  {len(bt_df)} strategy-ticker combos passed backtest")
    for _, row in bt_df.head(5).iterrows():
        print(f"    {row['ticker']:<18} {row['strategy']:<12} WR={row['win_rate']:.1%}  Sharpe={row['sharpe_ratio']:.2f}")

    # -- STEP 2: Live signals for top backtest candidates ------------------
    print(f"\n[2/4] Computing live signals for top {min(10,len(bt_df))} candidates...")

    top_tickers = bt_df["ticker"].unique()[:10]
    signal_results = []

    for ticker in top_tickers:
        try:
            df_daily = fetch_historical(ticker, years=0.5)
            df_5min  = fetch_intraday(ticker, interval="5m", period="1d")
            if df_5min.empty or len(df_5min) < 6:
                continue
            levels = get_previous_day_levels(ticker, df_daily)
            sig = compute_signals(df_daily, df_5min,
                                  levels["pdh"], levels["pdl"], levels["pdc"])
            sig["ticker"] = ticker

            # Best matching backtest row for this ticker
            bt_rows = bt_df[bt_df["ticker"] == ticker]
            if not bt_rows.empty:
                best_bt = bt_rows.sort_values("sharpe_ratio", ascending=False).iloc[0]
                sig["bt_win_rate"]  = float(best_bt["win_rate"])
                sig["bt_sharpe"]    = float(best_bt["sharpe_ratio"])
                sig["bt_strategy"]  = best_bt["strategy"]
            else:
                sig["bt_win_rate"]  = 0
                sig["bt_sharpe"]    = 0
                sig["bt_strategy"]  = "ORB"

            signal_results.append(sig)

            aligned = sig["signals_aligned"]
            icon = "OK" if sig["direction"] == "LONG" and aligned >= MIN_SIGNALS_REQUIRED else "-"
            print(f"  [{icon}] {ticker:<18} {sig['direction']:<8} signals={aligned}/7  "
                  f"conf={sig['confidence']:.0%}  RSI={sig['rsi']:.0f}  "
                  f"vol={sig['vol_ratio']:.1f}x  regime={sig['regime']}")

        except Exception as e:
            print(f"  ! {ticker:<18} {e}")

    # -- STEP 3: Select best setup ----------------------------------------
    print(f"\n[3/4] Selecting highest-conviction BUY setup...")

    actionable = [
        s for s in signal_results
        if s["direction"] == "LONG"
        and s["signals_aligned"] >= MIN_SIGNALS_REQUIRED
    ]

    if not actionable:
        return _no_trade(
            f"No stock had >={MIN_SIGNALS_REQUIRED}/7 signals aligned in LONG direction today. "
            f"Checked {len(signal_results)} stocks."
        )

    # Composite score: backtest sharpe x confidence x win_rate
    for s in actionable:
        s["_score"] = s["bt_sharpe"] * s["confidence"] * s["bt_win_rate"]

    best = max(actionable, key=lambda x: x["_score"])
    ticker        = best["ticker"]
    entry         = best["current_price"]
    orb_low       = best["orb_low"]
    orb_high      = best["orb_high"]
    vwap          = best["vwap"]

    # -- STEP 4: Build levels ---------------------------------------------
    print(f"\n[4/4] Building recommendation for {ticker}...")

    stop   = round(orb_low * 0.998, 2)   # Just below ORB low
    risk   = entry - stop
    if risk <= 0:
        return _no_trade(f"Invalid risk calculation for {ticker} (risk={risk:.2f})")

    target = round(entry + risk * MIN_REWARD_RISK, 2)
    exp_return_pct = (target / entry - 1) * 100

    # Min 1% return filter
    if exp_return_pct < MIN_RETURN_PCT:
        return _no_trade(
            f"{ticker} best setup only gives {exp_return_pct:.2f}% return "
            f"(minimum required: {MIN_RETURN_PCT:.0f}%). No trade."
        )

    # Min 2:1 R:R check
    rr = (target - entry) / (entry - stop)
    if rr < MIN_REWARD_RISK:
        return _no_trade(f"{ticker} R:R = {rr:.2f} below minimum {MIN_REWARD_RISK}. No trade.")

    # Kelly sizing
    sizing = RiskManager().kelly_position(
        win_rate=best["bt_win_rate"],
        entry=entry,
        stop=stop
    )

    recommendation = {
        "action":           "BUY CASH",
        "type":             "EQUITY",
        "ticker":           ticker,
        "exchange":         "NSE",

        # Prices
        "entry":            round(entry, 2),
        "target":           round(target, 2),
        "stop_loss":        stop,
        "expected_return":  round(exp_return_pct, 2),
        "reward_risk":      round(rr, 2),

        # Sizing
        "shares":           sizing["shares"],
        "position_value":   sizing["position_value"],
        "risk_amount":      sizing["risk_amount"],
        "risk_pct":         sizing["risk_pct"],
        "kelly_pct":        sizing["kelly_pct"],

        # Signal context
        "signals_aligned":  best["signals_aligned"],
        "signals_detail":   best["signals_detail"],
        "confidence":       best["confidence"],
        "regime":           best["regime"],
        "vwap":             vwap,
        "orb_high":         orb_high,
        "orb_low":          orb_low,
        "rsi":              best["rsi"],
        "vol_ratio":        best.get("vol_ratio", 0),

        # Backtest
        "bt_win_rate":      round(best["bt_win_rate"], 4),
        "bt_sharpe":        round(best["bt_sharpe"], 3),
        "bt_strategy":      best["bt_strategy"],

        # Rules
        "entry_time":       "9:45 AM IST",
        "exit_rule":        f"Sell at Rs.{round(target,2):,.2f} if hit. Close ALL by 2:00 PM IST.",
        "kill_switch":      f"FORCE CLOSE at {KILL_SWITCH_TIME} IST regardless of P&L.",
        "timestamp":        now_ist.isoformat(),
    }

    return recommendation
