"""
3:35 PM Close — Record End-of-Day P&L
─────────────────────────────────────────────────────────────────────────────
Runs at 3:35 PM IST via GitHub Actions.
Fetches closing price for today's trade, calculates P&L,
updates the equity tracker (₹1 lakh becomes X).
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date
import pytz
import yfinance as yf
import pandas as pd

IST = pytz.timezone("Asia/Kolkata")
CALLS_PATH = "data/daily_calls.json"
CAPITAL    = 100_000
POSITION_PCT = 0.80  # Use 80% of equity per trade


def get_closing_price(ticker: str) -> float:
    try:
        df = yf.download(ticker, period="1d", interval="1m", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty:
            return 0.0
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)
        # Use last available price (3:25-3:30 bar)
        close_bars = df.between_time("15:10", "15:31")
        if not close_bars.empty:
            return float(close_bars.iloc[-1]["Close"])
        return float(df.iloc[-1]["Close"])
    except:
        return 0.0


def check_intraday_exits(ticker: str, entry: float, direction: str,
                          target: float, stoploss: float) -> dict:
    """
    Check today's 1-min data to see if SL or Target was hit before close.
    Returns exit price and reason.
    """
    try:
        df = yf.download(ticker, period="1d", interval="1m", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty:
            return {"exit": entry, "reason": "no_data"}
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)

        # Only look at bars after 9:45
        post_signal = df.between_time("09:45", "15:30")

        for _, bar in post_signal.iterrows():
            if direction == "BUY":
                if bar["Low"] <= stoploss:
                    return {"exit": stoploss, "reason": "stoploss"}
                if bar["High"] >= target:
                    return {"exit": target, "reason": "target"}
            else:  # SELL
                if bar["High"] >= stoploss:
                    return {"exit": stoploss, "reason": "stoploss"}
                if bar["Low"] <= target:
                    return {"exit": target, "reason": "target"}

        # EOD exit at closing price
        eod_price = get_closing_price(ticker)
        return {"exit": eod_price if eod_price > 0 else entry, "reason": "eod_close"}

    except Exception as e:
        return {"exit": entry, "reason": f"error: {e}"}


def record_eod_pnl():
    today = str(date.today())
    now   = datetime.now(IST).strftime("%H:%M IST")

    if not os.path.exists(CALLS_PATH):
        print("[CLOSE] No calls file found.")
        return

    with open(CALLS_PATH) as f:
        log = json.load(f)

    # Find today's open call
    today_call = None
    for call in log["calls"]:
        if call["date"] == today and call["status"] == "open":
            today_call = call
            break

    if not today_call:
        print(f"[CLOSE] No open call for {today} — nothing to record.")
        return

    ticker    = today_call["ticker"]
    direction = today_call["action"]
    entry     = today_call.get("entry", 0)
    target    = today_call.get("target", 0)
    stoploss  = today_call.get("stoploss", 0)
    equity    = today_call.get("equity_start", CAPITAL)

    print(f"\n[CLOSE] Recording P&L for {ticker} {direction} @ ₹{entry:,.2f}")

    # Get exit price
    exit_info = check_intraday_exits(ticker, entry, direction, target, stoploss)
    exit_price  = exit_info["exit"]
    exit_reason = exit_info["reason"]

    # Calculate P&L
    position_size = equity * POSITION_PCT
    shares = position_size / entry if entry > 0 else 0

    if direction == "BUY":
        raw_pnl = (exit_price - entry) * shares
    else:
        raw_pnl = (entry - exit_price) * shares

    brokerage = position_size * 0.0006  # 0.06% round trip (Zerodha intraday ~₹20 each side)
    net_pnl   = raw_pnl - brokerage
    pnl_pct   = (net_pnl / equity) * 100
    equity_end = equity + net_pnl

    # Update call
    today_call["exit"]        = round(exit_price, 2)
    today_call["exit_time"]   = now
    today_call["exit_reason"] = exit_reason
    today_call["pnl_pct"]     = round(pnl_pct, 2)
    today_call["pnl_inr"]     = round(net_pnl, 0)
    today_call["equity_end"]  = round(equity_end, 0)
    today_call["status"]      = "closed"

    # Update running equity
    log["equity"] = round(equity_end, 0)

    # Update call in log
    log["calls"] = [c if c["date"] != today else today_call for c in log["calls"]]

    with open(CALLS_PATH, "w") as f:
        json.dump(log, f, indent=2, default=str)

    # Summary
    direction_word = "▲ BUY" if direction == "BUY" else "▼ SELL"
    result_emoji   = "✅" if net_pnl >= 0 else "❌"

    print(f"\n{'='*60}")
    print(f"  {result_emoji} EOD RESULT: {direction_word} {ticker}")
    print(f"  Entry:  ₹{entry:,.2f}  →  Exit: ₹{exit_price:,.2f}  [{exit_reason}]")
    print(f"  P&L:    {pnl_pct:+.2f}%  =  ₹{net_pnl:+,.0f}")
    print(f"  Equity: ₹{equity:,.0f}  →  ₹{equity_end:,.0f}")
    print(f"{'='*60}\n")

    # GitHub Actions summary
    with open(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null"), "a") as f:
        icon = "✅" if net_pnl >= 0 else "❌"
        f.write(f"## {icon} EOD Result: {direction} {ticker}\n")
        f.write(f"| | |\n|---|---|\n")
        f.write(f"| Entry | ₹{entry:,.2f} |\n")
        f.write(f"| Exit | ₹{exit_price:,.2f} ({exit_reason}) |\n")
        f.write(f"| P&L | **{pnl_pct:+.2f}% = ₹{net_pnl:+,.0f}** |\n")
        f.write(f"| Running Capital | ₹{equity_end:,.0f} |\n")


if __name__ == "__main__":
    record_eod_pnl()
