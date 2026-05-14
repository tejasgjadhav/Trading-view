"""
Jane Street Daily Trading Agent — Main Orchestrator
Run at 9:45 AM IST via GitHub Actions.

Usage:
    python -m jane_street.agent              # run once
    python -m jane_street.agent --backtest   # backtest only
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date
import pytz

from jane_street.recommendation import generate_recommendation
from jane_street.config import CAPITAL, CALLS_PATH, REPORTS_DIR, IST


def print_recommendation(rec: dict):
    print(f"\n{'='*65}")
    print(f"  JANE STREET FINAL CALL")
    print(f"{'='*65}")

    if rec["action"] == "NO_TRADE":
        print(f"\n  NO TRADE TODAY")
        print(f"  Reason: {rec['reason']}")
        print(f"{'='*65}")
        return

    exp  = rec["expected_return"]

    print(f"\n  ACTION     : {rec['action']}")
    print(f"  STOCK      : NSE:{rec['ticker']}")
    print(f"")
    print(f"  BUY AT     : Rs.{rec['entry']:,.2f}   (9:45 AM price)")
    print(f"  TARGET     : Rs.{rec['target']:,.2f}   (+{exp:.1f}%)")
    print(f"  STOP LOSS  : Rs.{rec['stop_loss']:,.2f}   ({((rec['stop_loss']/rec['entry'])-1)*100:.1f}%)")
    print(f"  VWAP       : Rs.{rec['vwap']:,.2f}")
    print(f"  ORB Range  : Rs.{rec['orb_low']:,.2f} - Rs.{rec['orb_high']:,.2f}")
    print(f"")
    print(f"  QUANTITY   : {rec['shares']} shares")
    print(f"  POSITION   : Rs.{rec['position_value']:,.0f}")
    print(f"  RISK       : Rs.{rec['risk_amount']:,.0f}  ({rec['risk_pct']:.1f}% of capital)")
    print(f"  KELLY SIZE : {rec['kelly_pct']:.1f}% of capital (25% fractional)")
    print(f"  R:R RATIO  : {rec['reward_risk']:.1f}:1")
    print(f"")
    print(f"  SIGNALS    : {rec['signals_aligned']}/7 aligned")
    print(f"  CONFIDENCE : {int(rec['confidence']*100)}%")
    print(f"  REGIME     : {rec['regime']}")
    print(f"  RSI        : {rec['rsi']:.1f}")
    print(f"  VOLUME     : {rec.get('vol_ratio',0):.1f}x average")
    print(f"")
    print(f"  BACKTEST   : {rec['bt_win_rate']:.1%} win rate | Sharpe {rec['bt_sharpe']:.2f} | {rec['bt_strategy']}")
    print(f"")
    print(f"  EXIT       : {rec['exit_rule']}")
    print(f"  KILL       : {rec['kill_switch']}")
    print(f"{'='*65}\n")

    # Signal breakdown
    print("  Signal breakdown:")
    labels = {
        "above_pdc":    "Above Prev Close",
        "orb":          "ORB Breakout",
        "vwap":         "Above VWAP",
        "rsi":          "RSI",
        "ema_trend":    "EMA Trend",
        "volume_spike": "Volume Spike",
        "key_level":    "Key Level",
    }
    for k, v in rec.get("signals_detail", {}).items():
        icon2 = "[Y]" if v == 1 else ("[N]" if v == -1 else "[-]")
        print(f"    {icon2}  {labels.get(k, k)}")
    print()


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
            "date":   today, "action": "HOLD",
            "ticker": "-",   "reason": rec["reason"],
            "status": "hold", "equity_start": equity,
        }
    else:
        call = {
            "date":             today,
            "signal_time":      datetime.now(IST).strftime("%I:%M %p IST"),
            "ticker":           rec["ticker"],
            "action":           "BUY",
            "entry":            rec["entry"],
            "target":           rec["target"],
            "stoploss":         rec["stop_loss"],
            "expected_return":  rec["expected_return"],
            "reward_risk":      rec["reward_risk"],
            "shares":           rec["shares"],
            "position_value":   rec["position_value"],
            "risk_amount":      rec["risk_amount"],
            "vwap":             rec["vwap"],
            "orb_high":         rec["orb_high"],
            "orb_low":          rec["orb_low"],
            "rsi":              rec["rsi"],
            "vol_ratio":        rec.get("vol_ratio"),
            "signals_aligned":  rec["signals_aligned"],
            "confidence":       rec["confidence"],
            "regime":           rec["regime"],
            "bt_win_rate":      rec["bt_win_rate"],
            "bt_sharpe":        rec["bt_sharpe"],
            "bt_strategy":      rec["bt_strategy"],
            "signals_detail":   rec.get("signals_detail", {}),
            "equity_start":     equity,
            "exit":             None,
            "exit_time":        None,
            "exit_reason":      None,
            "pnl_pct":          None,
            "pnl_inr":          None,
            "equity_end":       None,
            "status":           "open",
        }

    log["calls"] = [c for c in log["calls"] if c["date"] != today]
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
    summary = os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null")
    with open(summary, "a") as f:
        if rec["action"] == "NO_TRADE":
            f.write(f"## NO TRADE - {today}\n{rec['reason']}\n")
        else:
            f.write(f"## BUY: **{rec['ticker']}** @ Rs.{rec['entry']:,.2f}\n\n")
            f.write(f"| | |\n|---|---|\n")
            f.write(f"| **Entry** | Rs.{rec['entry']:,.2f} |\n")
            f.write(f"| **Target** | Rs.{rec['target']:,.2f} (+{rec['expected_return']:.1f}%) |\n")
            f.write(f"| **Stop Loss** | Rs.{rec['stop_loss']:,.2f} |\n")
            f.write(f"| **Shares** | {rec['shares']} @ Kelly {rec['kelly_pct']:.1f}% |\n")
            f.write(f"| **Signals** | {rec['signals_aligned']}/7 aligned |\n")
            f.write(f"| **Confidence** | {int(rec['confidence']*100)}% |\n")
            f.write(f"| **Backtest WR** | {rec['bt_win_rate']:.1%} |\n")
            f.write(f"| **Sharpe** | {rec['bt_sharpe']:.2f} |\n")
            f.write(f"\n> Exit at Rs.{rec['target']:,.2f} or force-close at 2:00 PM IST\n")
            f.write(f"\n**Running Capital:** Rs.{equity:,.0f}\n")


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
        from jane_street.backtest import run_all_backtests
        from jane_street.config import CASH_EQUITIES
        print("Running 2-year backtest on all stocks...")
        df = run_all_backtests(CASH_EQUITIES, ["ORB", "VWAP", "MOMENTUM"])
        if df.empty:
            print("No strategies passed 80% win rate threshold.")
        else:
            print(f"\n{len(df)} strategies passed:\n")
            print(df[["ticker","strategy","win_rate","total_trades","sharpe_ratio","max_drawdown_pct","profit_factor"]].to_string(index=False))
    else:
        run_agent(force_fresh=args.fresh)
