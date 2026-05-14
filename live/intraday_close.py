"""
3:35 PM — Record EOD P&L
─────────────────────────────────────────────────────────────────────────────
Rules:
  • If target was hit during the day → exit at target price
  • If target NOT hit → exit at 3:30 PM closing price
  • Never hold overnight under any circumstance
  • Uses 80% of current equity as position size
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date
import pytz, warnings
warnings.filterwarnings("ignore")
import yfinance as yf
import pandas as pd

IST          = pytz.timezone("Asia/Kolkata")
CALLS_PATH   = "data/daily_calls.json"
CAPITAL      = 100_000
POSITION_PCT = 0.80   # Use 80% of equity per trade (20% buffer)
BROKERAGE    = 0.0006  # 0.06% round-trip (Zerodha intraday ~₹20/side)


def fetch_full_day(ticker: str) -> pd.DataFrame:
    """Download complete today's 1-minute bars."""
    try:
        df = yf.download(ticker, period="1d", interval="1m",
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty:
            return pd.DataFrame()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)
        return df
    except:
        return pd.DataFrame()


def find_exit(df: pd.DataFrame, direction: str,
              entry: float, target: float, stoploss: float) -> dict:
    """
    Scan every 1-min bar from 9:45 to 15:30.
    Rule 1: If target hit during day → exit at target (best case)
    Rule 2: If stop hit before target → exit at stop
    Rule 3: Otherwise → exit at 15:30 close (mandatory EOD)
    """
    post_signal = df.between_time("09:45", "15:30")
    if post_signal.empty:
        return {"exit": entry, "reason": "no_data_after_signal"}

    for ts, bar in post_signal.iterrows():
        if direction == "BUY":
            # Target hit first → sell there
            if bar["High"] >= target:
                return {"exit": target, "reason": "target_hit",
                        "time": ts.strftime("%I:%M %p")}
            # Stop hit
            if bar["Low"] <= stoploss:
                return {"exit": stoploss, "reason": "stoploss_hit",
                        "time": ts.strftime("%I:%M %p")}
        else:  # SELL / short
            if bar["Low"] <= target:
                return {"exit": target, "reason": "target_hit",
                        "time": ts.strftime("%I:%M %p")}
            if bar["High"] >= stoploss:
                return {"exit": stoploss, "reason": "stoploss_hit",
                        "time": ts.strftime("%I:%M %p")}

    # Neither target nor stop hit → close at end of day (3:30 PM)
    eod_bars = df.between_time("15:25", "15:31")
    eod_price = float(eod_bars.iloc[-1]["Close"]) if not eod_bars.empty else float(df.iloc[-1]["Close"])
    return {"exit": eod_price, "reason": "eod_close_3:30PM",
            "time": "03:30 PM"}


def record_eod_pnl():
    today = str(date.today())
    now   = datetime.now(IST).strftime("%I:%M %p IST")

    if not os.path.exists(CALLS_PATH):
        print("[CLOSE] No calls file found. Nothing to record.")
        return

    with open(CALLS_PATH) as f:
        log = json.load(f)

    # Find today's open call
    today_call = next((c for c in log["calls"]
                       if c["date"] == today and c["status"] == "open"), None)

    if not today_call:
        print(f"[CLOSE] No open position for {today}.")
        return

    ticker    = today_call["ticker"]
    direction = today_call["action"]
    entry     = today_call.get("entry") or 0
    target    = today_call.get("target") or 0
    stoploss  = today_call.get("stoploss") or 0
    equity    = today_call.get("equity_start", CAPITAL)

    if not entry:
        print(f"[CLOSE] No entry price recorded for {ticker}. Skipping.")
        return

    print(f"\n{'='*60}")
    print(f"  CLOSING POSITION: {direction} {ticker}")
    print(f"  Entry: ₹{entry:,.2f}  |  Target: ₹{target:,.2f}  |  SL: ₹{stoploss:,.2f}")
    print(f"{'='*60}")

    # Fetch full day data and find exit
    df = fetch_full_day(ticker)
    if df.empty:
        print(f"  [WARN] No intraday data for {ticker}. Using entry as exit.")
        exit_info = {"exit": entry, "reason": "no_data", "time": now}
    else:
        exit_info = find_exit(df, direction, entry, target, stoploss)

    exit_price  = exit_info["exit"]
    exit_reason = exit_info["reason"]
    exit_time   = exit_info.get("time", now)

    # ─── P&L calculation ─────────────────────────────────────────────────────
    position_size = equity * POSITION_PCT
    shares        = position_size / entry

    if direction == "BUY":
        gross_pnl = (exit_price - entry) * shares
    else:
        gross_pnl = (entry - exit_price) * shares

    brokerage_cost = position_size * BROKERAGE
    net_pnl        = gross_pnl - brokerage_cost
    pnl_pct        = (net_pnl / equity) * 100
    equity_end     = equity + net_pnl

    # ─── Update call record ──────────────────────────────────────────────────
    today_call.update({
        "exit":        round(exit_price, 2),
        "exit_time":   exit_time,
        "exit_reason": exit_reason,
        "pnl_pct":     round(pnl_pct, 2),
        "pnl_inr":     round(net_pnl, 0),
        "equity_end":  round(equity_end, 0),
        "status":      "closed",
    })

    log["calls"]  = [c if c["date"] != today else today_call for c in log["calls"]]
    log["equity"] = round(equity_end, 0)

    with open(CALLS_PATH, "w") as f:
        json.dump(log, f, indent=2, default=str)

    # ─── Print result ────────────────────────────────────────────────────────
    result_icon = "✅ PROFIT" if net_pnl >= 0 else "❌ LOSS"
    reason_label = {
        "target_hit":       "🎯 TARGET HIT",
        "stoploss_hit":     "🛑 STOP HIT",
        "eod_close_3:30PM": "🔔 EOD CLOSE (3:30 PM)",
        "no_data":          "⚠ No data",
    }.get(exit_reason, exit_reason)

    print(f"\n  {result_icon}")
    print(f"  Exit reason: {reason_label}  @ {exit_time}")
    print(f"  Entry ₹{entry:,.2f}  →  Exit ₹{exit_price:,.2f}")
    print(f"  P&L:   {pnl_pct:+.2f}%  =  ₹{net_pnl:+,.0f}")
    print(f"  Equity: ₹{equity:,.0f}  →  ₹{equity_end:,.0f}")
    print(f"{'='*60}\n")

    # GitHub Actions step summary
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null")
    with open(summary_path, "a") as f:
        icon = "✅" if net_pnl >= 0 else "❌"
        f.write(f"## {icon} EOD Result: {direction} {ticker}\n\n")
        f.write(f"| | |\n|---|---|\n")
        f.write(f"| Exit Reason | {reason_label} |\n")
        f.write(f"| Entry | ₹{entry:,.2f} |\n")
        f.write(f"| Exit | ₹{exit_price:,.2f} @ {exit_time} |\n")
        f.write(f"| **P&L** | **{pnl_pct:+.2f}% = ₹{net_pnl:+,.0f}** |\n")
        f.write(f"| Running Capital | ₹{equity_end:,.0f} |\n")


if __name__ == "__main__":
    record_eod_pnl()
