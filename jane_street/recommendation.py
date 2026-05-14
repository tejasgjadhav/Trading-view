"""
Quant Signal Engine — Recommendation Generator
─────────────────────────────────────────────────────────────────────────────
Outputs UP TO TWO calls per day with capital allocation commentary.
Primary call = highest max-1-day-return setup.
Secondary call = second-best setup (if strong enough).

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
        "calls":     [],
        "allocation": None,
    }


def _build_call(sig: dict, now_ist: datetime) -> dict | None:
    """Build a single BUY call dict from a signal result. Returns None if levels fail."""
    ticker   = sig["ticker"]
    entry    = sig["current_price"]
    orb_low  = sig["orb_low"]
    orb_high = sig["orb_high"]
    vwap     = sig["vwap"]

    stop  = round(orb_low * 0.998, 2)
    risk  = entry - stop
    if risk <= 0:
        return None

    target = round(entry + risk * MIN_REWARD_RISK, 2)
    exp_return_pct = (target / entry - 1) * 100
    rr = (target - entry) / (entry - stop)

    if exp_return_pct < MIN_RETURN_PCT:
        return None
    if rr < MIN_REWARD_RISK:
        return None

    sizing = RiskManager().kelly_position(
        win_rate=sig["bt_win_rate"],
        entry=entry,
        stop=stop
    )

    return {
        "action":           "BUY",
        "type":             "EQUITY",
        "ticker":           ticker,
        "exchange":         "NSE",
        "entry":            round(entry, 2),
        "target":           round(target, 2),
        "stop_loss":        stop,
        "expected_return":  round(exp_return_pct, 2),
        "reward_risk":      round(rr, 2),
        "shares":           sizing["shares"],
        "position_value":   sizing["position_value"],
        "risk_amount":      sizing["risk_amount"],
        "risk_pct":         sizing["risk_pct"],
        "kelly_pct":        sizing["kelly_pct"],
        "signals_aligned":  sig["signals_aligned"],
        "signals_detail":   sig["signals_detail"],
        "confidence":       sig["confidence"],
        "regime":           sig["regime"],
        "vwap":             vwap,
        "orb_high":         orb_high,
        "orb_low":          orb_low,
        "rsi":              sig["rsi"],
        "vol_ratio":        sig.get("vol_ratio", 0),
        "bt_win_rate":      round(sig["bt_win_rate"], 4),
        "bt_sharpe":        round(sig["bt_sharpe"], 3),
        "bt_strategy":      sig["bt_strategy"],
        "bt_max_1day":      round(sig.get("bt_max_1day_return", 0), 2),
        "exit_rule":        f"Sell at ₹{round(target,2):,.2f} if hit. Close ALL by {KILL_SWITCH_TIME} IST.",
        "kill_switch":      f"FORCE CLOSE at {KILL_SWITCH_TIME} IST regardless of P&L.",
        "timestamp":        now_ist.isoformat(),
    }


def _allocation_commentary(calls: list, capital: float = CAPITAL) -> dict:
    """
    Compute how much to invest in each call.
    Total position value must not exceed 85% of capital.
    If 2 calls, scale down proportionally if needed.
    """
    if not calls:
        return {}

    if len(calls) == 1:
        c = calls[0]
        invest = min(c["position_value"], capital * 0.85)
        shares = int(invest / c["entry"])
        pct    = round(invest / capital * 100, 1)
        cash_reserve = capital - invest
        lines = [
            f"Single signal today. Invest ₹{invest:,.0f} ({pct}% of capital) in {c['ticker']}.",
            f"Buy {shares} shares @ ₹{c['entry']:,.2f}.",
            f"Keep ₹{cash_reserve:,.0f} as cash reserve.",
            f"Expected gain if target hit: +{c['expected_return']:.1f}% → ₹{shares*(c['target']-c['entry']):,.0f}.",
            f"Max loss if stop hit: -₹{shares*(c['entry']-c['stop_loss']):,.0f}.",
        ]
        return {
            "primary":      {"ticker": c["ticker"], "invest_inr": round(invest), "invest_pct": pct, "shares": shares},
            "secondary":    None,
            "cash_reserve": round(cash_reserve),
            "commentary":   " ".join(lines),
        }

    # 2 calls — split proportionally by confidence × max_1day_return
    c1, c2 = calls[0], calls[1]
    score1  = c1["confidence"] * c1.get("bt_max_1day", 1)
    score2  = c2["confidence"] * c2.get("bt_max_1day", 1)
    total_score = score1 + score2 if (score1 + score2) > 0 else 1

    # Proportional split, capped at 85% total
    alloc1 = min(c1["position_value"], capital * 0.85 * score1 / total_score)
    alloc2 = min(c2["position_value"], capital * 0.85 * score2 / total_score)
    total_alloc = alloc1 + alloc2

    if total_alloc > capital * 0.85:
        scale = (capital * 0.85) / total_alloc
        alloc1 *= scale
        alloc2 *= scale

    shares1 = max(1, int(alloc1 / c1["entry"]))
    shares2 = max(1, int(alloc2 / c2["entry"]))
    pct1    = round(alloc1 / capital * 100, 1)
    pct2    = round(alloc2 / capital * 100, 1)
    reserve = capital - alloc1 - alloc2

    lines = [
        f"Two signals today — split ₹1L as follows:",
        f"► {c1['ticker']}: ₹{alloc1:,.0f} ({pct1}% of capital) — {shares1} shares @ ₹{c1['entry']:,.2f}. "
        f"Target +{c1['expected_return']:.1f}%, Stop -{round((c1['entry']-c1['stop_loss'])/c1['entry']*100,1)}%.",
        f"► {c2['ticker']}: ₹{alloc2:,.0f} ({pct2}% of capital) — {shares2} shares @ ₹{c2['entry']:,.2f}. "
        f"Target +{c2['expected_return']:.1f}%, Stop -{round((c2['entry']-c2['stop_loss'])/c2['entry']*100,1)}%.",
        f"► Cash reserve: ₹{reserve:,.0f} (buffer for intraday slippage).",
        f"Allocation weighted by confidence × max 1-day return. {c1['ticker']} is primary ({pct1}%), {c2['ticker']} secondary ({pct2}%).",
    ]
    return {
        "primary":      {"ticker": c1["ticker"], "invest_inr": round(alloc1), "invest_pct": pct1, "shares": shares1},
        "secondary":    {"ticker": c2["ticker"], "invest_inr": round(alloc2), "invest_pct": pct2, "shares": shares2},
        "cash_reserve": round(reserve),
        "commentary":   " ".join(lines),
    }


def generate_recommendation(force_fresh_backtest: bool = False) -> dict:
    """
    MAIN FUNCTION — call at 9:45 AM every trading day.
    Returns recommendation dict with up to 2 calls and allocation commentary.
    """
    now_ist = datetime.now(IST)
    risk    = RiskManager(capital=CAPITAL)

    print(f"\n{'='*65}")
    print(f"  QUANT SIGNAL ENGINE — {now_ist.strftime('%d %b %Y  %I:%M %p IST')}")
    print(f"  Capital: ₹{CAPITAL:,.0f}  |  Rules: BUY only, >=80% WR, >=3/7 signals, 2:1 R:R")
    print(f"  Ranking: Max 1-day return (best single intraday gain in backtest)")
    print(f"{'='*65}\n")

    # -- STEP 1: Backtest gate ---------------------------------------------
    print(f"[1/4] Loading backtest results (2-year, >=80% win rate gate)...")
    bt_df = load_or_run_backtest(CASH_EQUITIES, force_fresh=force_fresh_backtest)

    if bt_df.empty:
        return _no_trade(f"Zero strategies passed {MIN_WIN_RATE_THRESHOLD:.0%} win rate. No trade today.")

    print(f"  {len(bt_df)} strategy-ticker combos passed backtest")
    for _, row in bt_df.head(5).iterrows():
        max1d = row.get("max_1day_return", 0)
        print(f"    {row['ticker']:<18} {row['strategy']:<12} WR={row['win_rate']:.1%}  "
              f"MaxDay={max1d:+.2f}%  Sharpe={row['sharpe_ratio']:.2f}")

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
                best_bt = bt_rows.sort_values("max_1day_return", ascending=False).iloc[0]
                sig["bt_win_rate"]         = float(best_bt["win_rate"])
                sig["bt_sharpe"]           = float(best_bt["sharpe_ratio"])
                sig["bt_strategy"]         = best_bt["strategy"]
                sig["bt_max_1day_return"]  = float(best_bt.get("max_1day_return", 0))
            else:
                sig["bt_win_rate"]         = 0
                sig["bt_sharpe"]           = 0
                sig["bt_strategy"]         = "ORB"
                sig["bt_max_1day_return"]  = 0

            signal_results.append(sig)

            aligned = sig["signals_aligned"]
            icon = "OK" if sig["direction"] == "LONG" and aligned >= MIN_SIGNALS_REQUIRED else "-"
            print(f"  [{icon}] {ticker:<18} {sig['direction']:<8} signals={aligned}/7  "
                  f"conf={sig['confidence']:.0%}  RSI={sig['rsi']:.0f}  "
                  f"vol={sig['vol_ratio']:.1f}x  maxDay={sig['bt_max_1day_return']:+.1f}%")

        except Exception as e:
            print(f"  ! {ticker:<18} {e}")

    # -- STEP 3: Select best 2 setups -------------------------------------
    print(f"\n[3/4] Selecting top BUY setups (ranked by max 1-day return)...")

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

    # Score = max_1day_return × confidence × win_rate (prioritises max 1-day gain)
    for s in actionable:
        s["_score"] = s["bt_max_1day_return"] * s["confidence"] * s["bt_win_rate"]

    actionable.sort(key=lambda x: x["_score"], reverse=True)
    top2 = actionable[:2]

    # -- STEP 4: Build calls + allocation ---------------------------------
    print(f"\n[4/4] Building recommendation(s) for {[s['ticker'] for s in top2]}...")

    built_calls = []
    for s in top2:
        c = _build_call(s, now_ist)
        if c:
            built_calls.append(c)

    if not built_calls:
        return _no_trade("Signals passed gate but levels/risk checks failed for all candidates.")

    allocation = _allocation_commentary(built_calls, capital=CAPITAL)

    return {
        "action":     "BUY",
        "calls":      built_calls,
        "allocation": allocation,
        "timestamp":  now_ist.isoformat(),
        # Flatten first call fields for backward-compat
        **built_calls[0],
    }
