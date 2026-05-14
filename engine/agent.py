"""
Quant Signal Engine — Main Orchestrator
Run at 9:45 AM IST via GitHub Actions.

Usage:
    python -m engine.agent              # run once
    python -m engine.agent --backtest   # backtest only
    python -m engine.agent --fresh      # force fresh backtest
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date
import pytz

from engine.recommendation import generate_recommendation
from engine.config import CAPITAL, CALLS_PATH, REPORTS_DIR, IST


def print_recommendation(rec: dict):
    print(f"\n{'='*65}")
    print(f"  QUANT SIGNAL ENGINE — FINAL CALL")
    print(f"{'='*65}")

    if rec["action"] == "NO_TRADE":
        print(f"\n  NO TRADE TODAY")
        print(f"  Reason: {rec['reason']}")
        print(f"{'='*65}")
        return

    calls = rec.get("calls", [rec])
    alloc = rec.get("allocation", {})

    for i, call in enumerate(calls):
        label = "PRIMARY" if i == 0 else "SECONDARY"
        exp   = call["expected_return"]
        print(f"\n  [{label}] BUY {call['ticker']}")
        print(f"")
        print(f"  Entry Price  : ₹{call['entry']:,.2f}   (9:45 AM price)")
        print(f"  Target       : ₹{call['target']:,.2f}   (+{exp:.1f}%)")
        print(f"  Stop Loss    : ₹{call['stop_loss']:,.2f}   ({((call['stop_loss']/call['entry'])-1)*100:.1f}%)")
        print(f"  VWAP         : ₹{call['vwap']:,.2f}")
        print(f"  ORB Range    : ₹{call['orb_low']:,.2f} – ₹{call['orb_high']:,.2f}")
        print(f"  R:R Ratio    : {call['reward_risk']:.1f}:1")
        print(f"  Max 1-Day BT : +{call.get('bt_max_1day',0):.2f}%  (best single day in 2yr backtest)")
        print(f"  Backtest WR  : {call['bt_win_rate']:.1%}  |  Sharpe {call['bt_sharpe']:.2f}  |  {call['bt_strategy']}")
        print(f"  Signals      : {call['signals_aligned']}/7 aligned  |  Confidence {int(call['confidence']*100)}%")
        print(f"  Regime       : {call['regime']}")
        print(f"")

        # Signal breakdown
        labels_map = {
            "above_pdc":    "Above Prev Close",
            "orb":          "ORB Breakout",
            "vwap":         "Above VWAP",
            "rsi":          "RSI Momentum",
            "ema_trend":    "EMA Trend",
            "volume_spike": "Volume Spike",
            "key_level":    "Key Level",
        }
        for k, v in call.get("signals_detail", {}).items():
            icon = "[Y]" if v == 1 else ("[N]" if v == -1 else "[-]")
            print(f"    {icon}  {labels_map.get(k, k)}")

    print(f"\n{'─'*65}")
    print(f"  ALLOCATION COMMENTARY")
    print(f"{'─'*65}")
    print(f"\n  {alloc.get('commentary', '')}")

    if alloc.get("primary"):
        p = alloc["primary"]
        print(f"\n  PRIMARY   {p['ticker']:<18} ₹{p['invest_inr']:>9,.0f}  ({p['invest_pct']}%)  {p['shares']} shares")
    if alloc.get("secondary"):
        s = alloc["secondary"]
        print(f"  SECONDARY {s['ticker']:<18} ₹{s['invest_inr']:>9,.0f}  ({s['invest_pct']}%)  {s['shares']} shares")
    print(f"  CASH RESERVE            ₹{alloc.get('cash_reserve',0):>9,.0f}")

    print(f"\n  EXIT RULE  : Close at target, else force-close at 2:00 PM IST (no overnight)")
    print(f"{'='*65}\n")


def save_to_calls_log(rec: dict):
    """Merge into existing daily_calls.json for dashboard."""
    today = str(date.today())

    if os.path.exists(CALLS_PATH):
        with open(CALLS_PATH) as f:
            log = json.load(f)
    else:
        log = {"calls": [], "equity": CAPITAL}

    equity = log.get("equity", CAPITAL)

    if rec["action"] == "NO_TRADE":
        call = {
            "date":         today,
            "action":       "HOLD",
            "ticker":       "-",
            "reason":       rec["reason"],
            "status":       "hold",
            "equity_start": equity,
        }
        log["calls"] = [c for c in log["calls"] if c["date"] != today]
        log["calls"].append(call)
    else:
        calls  = rec.get("calls", [rec])
        alloc  = rec.get("allocation", {})
        log["calls"] = [c for c in log["calls"] if c["date"] != today]

        for i, r in enumerate(calls):
            a_key = "primary" if i == 0 else "secondary"
            a_info = alloc.get(a_key, {})
            call = {
                "date":             today,
                "signal_time":      datetime.now(IST).strftime("%I:%M %p IST"),
                "call_rank":        "primary" if i == 0 else "secondary",
                "ticker":           r["ticker"],
                "action":           "BUY",
                "entry":            r["entry"],
                "target":           r["target"],
                "stoploss":         r["stop_loss"],
                "expected_return":  r["expected_return"],
                "reward_risk":      r["reward_risk"],
                "shares":           a_info.get("shares", r["shares"]),
                "invest_inr":       a_info.get("invest_inr", r["position_value"]),
                "invest_pct":       a_info.get("invest_pct", r["kelly_pct"]),
                "position_value":   r["position_value"],
                "risk_amount":      r["risk_amount"],
                "vwap":             r["vwap"],
                "orb_high":         r["orb_high"],
                "orb_low":          r["orb_low"],
                "rsi":              r["rsi"],
                "vol_ratio":        r.get("vol_ratio"),
                "signals_aligned":  r["signals_aligned"],
                "confidence":       r["confidence"],
                "regime":           r["regime"],
                "bt_win_rate":      r["bt_win_rate"],
                "bt_sharpe":        r["bt_sharpe"],
                "bt_strategy":      r["bt_strategy"],
                "bt_max_1day":      r.get("bt_max_1day", 0),
                "signals_detail":   r.get("signals_detail", {}),
                "allocation_note":  alloc.get("commentary", ""),
                "equity_start":     equity,
                "exit":             None,
                "exit_time":        None,
                "exit_reason":      None,
                "pnl_pct":          None,
                "pnl_inr":          None,
                "equity_end":       None,
                "status":           "open",
            }
            log["calls"].append(call)

    os.makedirs(os.path.dirname(CALLS_PATH), exist_ok=True)
    with open(CALLS_PATH, "w") as f:
        json.dump(log, f, indent=2, default=str)

    # Save full rec JSON
    os.makedirs(REPORTS_DIR, exist_ok=True)
    fname = f"{REPORTS_DIR}/rec_{today}.json"
    with open(fname, "w") as f:
        json.dump(rec, f, indent=2, default=str)

    # GitHub Actions step summary
    alloc  = rec.get("allocation", {})
    summary = os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null")
    with open(summary, "a") as f:
        if rec["action"] == "NO_TRADE":
            f.write(f"## ⏸️ NO TRADE — {today}\n{rec['reason']}\n")
        else:
            calls = rec.get("calls", [rec])
            for i, r in enumerate(calls):
                label = "📈 PRIMARY" if i == 0 else "📊 SECONDARY"
                a_key = "primary" if i == 0 else "secondary"
                a_info = alloc.get(a_key, {})
                f.write(f"## {label}: **{r['ticker']}** @ ₹{r['entry']:,.2f}\n\n")
                f.write(f"| | |\n|---|---|\n")
                f.write(f"| **Entry** | ₹{r['entry']:,.2f} |\n")
                f.write(f"| **Target** | ₹{r['target']:,.2f} (+{r['expected_return']:.1f}%) |\n")
                f.write(f"| **Stop Loss** | ₹{r['stop_loss']:,.2f} |\n")
                f.write(f"| **Max 1-Day Return (BT)** | +{r.get('bt_max_1day',0):.2f}% |\n")
                f.write(f"| **Backtest WR** | {r['bt_win_rate']:.1%} |\n")
                f.write(f"| **Signals** | {r['signals_aligned']}/7 |\n")
                f.write(f"| **Invest** | ₹{a_info.get('invest_inr',0):,.0f} ({a_info.get('invest_pct',0)}%) — {a_info.get('shares',0)} shares |\n")
                f.write(f"\n")
            f.write(f"---\n### 💰 Allocation\n{alloc.get('commentary','')}\n")
            f.write(f"\n**Running Capital:** ₹{equity:,.0f}\n")


def run_agent(force_fresh: bool = False):
    rec = generate_recommendation(force_fresh_backtest=force_fresh)
    print_recommendation(rec)
    save_to_calls_log(rec)
    return rec


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtest", action="store_true", help="Backtest only")
    parser.add_argument("--fresh",    action="store_true", help="Force fresh backtest")
    args = parser.parse_args()

    if args.backtest:
        from engine.backtest import run_all_backtests
        from engine.config import CASH_EQUITIES
        print("Running 2-year backtest on all stocks (ranking by max 1-day return)...")
        df = run_all_backtests(CASH_EQUITIES, ["ORB", "VWAP", "MOMENTUM"])
        if df.empty:
            print("No strategies passed 80% win rate threshold.")
        else:
            print(f"\n{len(df)} strategies passed:\n")
            cols = ["ticker","strategy","win_rate","max_1day_return","avg_win_return","total_trades","sharpe_ratio","max_drawdown_pct","profit_factor"]
            print(df[[c for c in cols if c in df.columns]].to_string(index=False))
    else:
        run_agent(force_fresh=args.fresh)
