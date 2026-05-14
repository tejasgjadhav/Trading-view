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
    post_signal = df.between_time("09:45", "15:20")
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

    # Neither target nor stop hit → force close at 3:20 PM (10 min before market close)
    eod_bars = df.between_time("15:15", "15:21")
    eod_price = float(eod_bars.iloc[-1]["Close"]) if not eod_bars.empty else float(df.iloc[-1]["Close"])
    return {"exit": eod_price, "reason": "force_close_3:20PM",
            "time": "03:20 PM"}


def record_eod_pnl():
    import math

    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        return obj

    REASON_LABEL = {
        "target_hit":         "🎯 TARGET HIT",
        "stoploss_hit":       "🛑 STOP HIT",
        "force_close_3:20PM": "🔔 FORCE CLOSE (3:20 PM)",
        "no_data":            "⚠ No data",
    }

    today = str(date.today())
    now   = datetime.now(IST).strftime("%I:%M %p IST")

    if not os.path.exists(CALLS_PATH):
        print("[CLOSE] No calls file found. Nothing to record.")
        return

    with open(CALLS_PATH) as f:
        log = json.load(f)

    # ── Find ALL open calls today (9:45 AM + 11 AM) ──────────────────────────
    open_calls = [c for c in log["calls"]
                  if c.get("date") == today and c.get("status") == "open"]

    if not open_calls:
        print(f"[CLOSE] No open positions for {today}.")
        return

    equity_start = log.get("equity", CAPITAL)
    total_net_pnl = 0.0

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null")

    print(f"\n{'='*65}")
    print(f"  EOD CLOSE — {today}  |  {len(open_calls)} position(s) to close")
    print(f"  Starting equity: ₹{equity_start:,.0f}")
    print(f"{'='*65}")

    # Cache fetched DataFrames to avoid double-downloading same ticker
    df_cache = {}

    for call in open_calls:
        ticker   = call.get("ticker", "")
        direction= call.get("action", "BUY")
        entry    = call.get("entry") or 0
        target   = call.get("target") or 0
        stoploss = call.get("stoploss") or 0
        invested = call.get("invest_inr") or call.get("position_value") or 0
        shares_held = call.get("shares") or (invested / entry if entry else 0)
        session  = call.get("signal_session", "MORNING")

        if not entry:
            print(f"  [SKIP] {ticker} — no entry price. Marking closed at entry.")
            call.update({"exit": entry, "exit_time": now, "exit_reason": "no_entry",
                         "pnl_pct": 0, "pnl_inr": 0, "equity_end": equity_start, "status": "closed"})
            continue

        print(f"\n  [{session}] Closing {direction} {ticker}")
        print(f"  Entry ₹{entry:,.2f} | Target ₹{target:,.2f} | SL ₹{stoploss:,.2f} | Shares {int(shares_held)}")

        if ticker not in df_cache:
            df_cache[ticker] = fetch_full_day(ticker)
        df = df_cache[ticker]

        if df.empty:
            exit_info = {"exit": entry, "reason": "no_data", "time": now}
        else:
            exit_info = find_exit(df, direction, entry, target, stoploss)

        exit_price  = exit_info["exit"]
        exit_reason = exit_info["reason"]
        exit_time   = exit_info.get("time", now)

        # ── P&L using actual shares (Kelly-sized from morning/midday) ─────────
        shares_used = max(1, int(shares_held)) if shares_held else max(1, int(invested / entry))
        if direction == "BUY":
            gross_pnl = (exit_price - entry) * shares_used
        else:
            gross_pnl = (entry - exit_price) * shares_used

        brokerage_cost = (shares_used * entry) * BROKERAGE
        net_pnl        = gross_pnl - brokerage_cost
        pnl_pct_call   = round((net_pnl / equity_start) * 100, 2)
        total_net_pnl += net_pnl

        running_equity = equity_start + total_net_pnl

        call.update({
            "exit":        round(exit_price, 2),
            "exit_time":   exit_time,
            "exit_reason": exit_reason,
            "pnl_pct":     pnl_pct_call,
            "pnl_inr":     round(net_pnl, 0),
            "equity_end":  round(running_equity, 0),
            "status":      "closed",
        })

        rl = REASON_LABEL.get(exit_reason, exit_reason)
        icon = "✅" if net_pnl >= 0 else "❌"
        print(f"  {icon} {rl} @ {exit_time}")
        print(f"  ₹{entry:,.2f} → ₹{exit_price:,.2f}  |  P&L: {pnl_pct_call:+.2f}% = ₹{net_pnl:+,.0f}")

        with open(summary_path, "a") as f:
            f.write(f"## {icon} [{session}] {direction} {ticker}\n\n")
            f.write(f"| | |\n|---|---|\n")
            f.write(f"| Exit Reason | {rl} |\n")
            f.write(f"| Entry | ₹{entry:,.2f} |\n")
            f.write(f"| Exit | ₹{exit_price:,.2f} @ {exit_time} |\n")
            f.write(f"| **P&L** | **{pnl_pct_call:+.2f}% = ₹{net_pnl:+,.0f}** |\n\n")

    # ── Consolidated result ───────────────────────────────────────────────────
    equity_end = equity_start + total_net_pnl
    consolidated_pct = round((total_net_pnl / equity_start) * 100, 2)

    result_icon = "✅ NET PROFIT" if total_net_pnl >= 0 else "❌ NET LOSS"
    print(f"\n{'─'*65}")
    print(f"  {result_icon}")
    print(f"  Total P&L: {consolidated_pct:+.2f}% = ₹{total_net_pnl:+,.0f}")
    print(f"  Equity: ₹{equity_start:,.0f} → ₹{equity_end:,.0f}")
    print(f"{'='*65}\n")

    with open(summary_path, "a") as f:
        icon2 = "✅" if total_net_pnl >= 0 else "❌"
        f.write(f"---\n## {icon2} CONSOLIDATED: {consolidated_pct:+.2f}% = ₹{total_net_pnl:+,.0f}\n")
        f.write(f"**Running Capital: ₹{equity_end:,.0f}**\n")

    # ── Save ──────────────────────────────────────────────────────────────────
    # Update all calls in log
    open_map = {id(c): c for c in open_calls}
    updated = []
    for c in log["calls"]:
        match = next((oc for oc in open_calls if oc.get("date") == c.get("date")
                      and oc.get("ticker") == c.get("ticker")
                      and oc.get("call_rank") == c.get("call_rank")), None)
        updated.append(match if match else c)
    log["calls"]  = updated
    log["equity"] = round(equity_end, 0)

    with open(CALLS_PATH, "w") as f:
        json.dump(_clean(log), f, indent=2, default=str)

    print(f"[CLOSE] Saved. Running equity: ₹{equity_end:,.0f}")


if __name__ == "__main__":
    record_eod_pnl()
