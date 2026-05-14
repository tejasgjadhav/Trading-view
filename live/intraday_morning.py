"""
9:45 AM Signal Generator — Intraday ORB + VWAP
─────────────────────────────────────────────────────────────────────────────
Runs at 9:45 AM IST via GitHub Actions.
Downloads live 1-minute NSE data, picks ONE best stock to trade,
outputs the call with entry / target / stop-loss.
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date
import pytz
import yfinance as yf
import pandas as pd

from strategies.intraday import calc_orb_signal, calc_vwap
from tracking.trade_logger import TradeLogger

IST = pytz.timezone("Asia/Kolkata")

# Full 100+ liquid NSE stocks — all F&O eligible (high volume, tight spreads)
INTRADAY_WATCHLIST = [
    # ── IT & Tech ──────────────────────────────────────────────────────────
    "TCS.NS","INFY.NS","WIPRO.NS","HCLTECH.NS","TECHM.NS","LTIM.NS",
    "MPHASIS.NS","COFORGE.NS","PERSISTENT.NS","OFSS.NS",
    # ── Banking ────────────────────────────────────────────────────────────
    "HDFCBANK.NS","ICICIBANK.NS","KOTAKBANK.NS","SBIN.NS","AXISBANK.NS",
    "INDUSINDBK.NS","FEDERALBNK.NS","IDFCFIRSTB.NS","BANDHANBNK.NS",
    "BANKBARODA.NS","PNB.NS","CANARABANK.NS","UNIONBANK.NS",
    # ── NBFC & Financials ──────────────────────────────────────────────────
    "BAJFINANCE.NS","BAJAJFINSV.NS","HDFCLIFE.NS","SBILIFE.NS",
    "CHOLAFIN.NS","MUTHOOTFIN.NS","SHRIRAMFIN.NS","RECLTD.NS",
    "PFC.NS","IRFC.NS","M&MFIN.NS",
    # ── Energy & Oil ───────────────────────────────────────────────────────
    "RELIANCE.NS","ONGC.NS","BPCL.NS","IOC.NS","COALINDIA.NS",
    "POWERGRID.NS","NTPC.NS","TATAPOWER.NS","ADANIGREEN.NS","ADANIPOWER.NS",
    # ── Industrials & Infra ────────────────────────────────────────────────
    "LT.NS","ADANIENT.NS","ADANIPORTS.NS","SIEMENS.NS","ABB.NS",
    "BHEL.NS","CUMMINSIND.NS","HAVELLS.NS","POLYCAB.NS","VOLTAS.NS",
    # ── Cement & Materials ─────────────────────────────────────────────────
    "ULTRACEMCO.NS","GRASIM.NS","AMBUJACEM.NS","ACC.NS","SHREECEM.NS",
    # ── Metals ─────────────────────────────────────────────────────────────
    "JSWSTEEL.NS","TATASTEEL.NS","HINDALCO.NS","VEDL.NS","SAIL.NS","NMDC.NS",
    # ── Auto ───────────────────────────────────────────────────────────────
    "MARUTI.NS","TATAMOTORS.NS","BAJAJ-AUTO.NS","HEROMOTOCO.NS",
    "EICHERMOT.NS","M&M.NS","ASHOKLEY.NS","BALKRISIND.NS","MOTHERSON.NS",
    # ── FMCG & Consumer ────────────────────────────────────────────────────
    "HINDUNILVR.NS","ITC.NS","NESTLEIND.NS","BRITANNIA.NS",
    "TATACONSUM.NS","ASIANPAINT.NS","GODREJCP.NS","MARICO.NS",
    "DABUR.NS","EMAMILTD.NS","COLPAL.NS","PIDILITIND.NS",
    # ── Pharma & Health ────────────────────────────────────────────────────
    "SUNPHARMA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS","APOLLOHOSP.NS",
    "LUPIN.NS","TORNTPHARM.NS","AUROPHARMA.NS","ZYDUSLIFE.NS","BIOCON.NS",
    # ── Retail & Consumer Discretionary ────────────────────────────────────
    "TITAN.NS","DMART.NS","TRENT.NS","JUBLFOOD.NS","NYKAA.NS",
    # ── Telecom ────────────────────────────────────────────────────────────
    "BHARTIARTL.NS","IDEA.NS",
    # ── New-age & Others ───────────────────────────────────────────────────
    "ZOMATO.NS","PAYTM.NS","NAUKRI.NS","INDIGO.NS",
    "DLF.NS","GODREJPROP.NS","OBEROIRLTY.NS",
]

CAPITAL = 100_000


def fetch_intraday(ticker: str) -> pd.DataFrame:
    """Fetch today's 1-minute bars."""
    try:
        df = yf.download(ticker, period="1d", interval="1m", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty:
            return pd.DataFrame()
        # Localize timezone
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)
        return df
    except Exception as e:
        print(f"  Error fetching {ticker}: {e}")
        return pd.DataFrame()


def pick_best_call(watchlist: list) -> dict:
    """
    Scan all stocks, rank by signal score, return the ONE best trade.
    """
    candidates = []

    print(f"\n{'='*60}")
    print(f"  INTRADAY SIGNAL — {datetime.now(IST).strftime('%d %b %Y %I:%M %p IST')}")
    print(f"  Opening Range Breakout + VWAP Strategy")
    print(f"{'='*60}\n")

    for ticker in watchlist:
        df = fetch_intraday(ticker)
        if df.empty:
            print(f"  {ticker:<15} — no data")
            continue

        sig = calc_orb_signal(df)
        sig["ticker"] = ticker

        arrow = "▲ BUY " if sig["action"] == "BUY" else ("▼ SELL" if sig["action"] == "SELL" else "─ HOLD")
        print(f"  {ticker:<15} {arrow}  score={sig['score']:+.3f}  {sig.get('reason','')}")
        candidates.append(sig)

    # Pick highest absolute score with a real signal
    actionable = [c for c in candidates if c["action"] in ("BUY", "SELL")]
    if not actionable:
        hold = max(candidates, key=lambda x: abs(x["score"])) if candidates else {}
        hold["action"] = "HOLD"
        hold["reason"] = "No clean ORB breakout across watchlist — sit out today"
        return hold

    best = max(actionable, key=lambda x: abs(x["score"]))
    return best


def generate_morning_call():
    today = str(date.today())
    now   = datetime.now(IST).strftime("%H:%M IST")

    best = pick_best_call(INTRADAY_WATCHLIST)

    # Load previous equity
    calls_path = "data/daily_calls.json"
    if os.path.exists(calls_path):
        with open(calls_path) as f:
            log = json.load(f)
    else:
        log = {"calls": [], "equity": CAPITAL}

    equity = log.get("equity", CAPITAL)

    # Build the call record
    call = {
        "date":       today,
        "signal_time": now,
        "ticker":     best.get("ticker", "—"),
        "action":     best.get("action", "HOLD"),
        "score":      best.get("score", 0),
        "entry":      best.get("entry", None),
        "target":     best.get("target", None),
        "stoploss":   best.get("stoploss", None),
        "or_high":    best.get("or_high", None),
        "or_low":     best.get("or_low", None),
        "vwap":       best.get("vwap", None),
        "vol_ratio":  best.get("vol_ratio", None),
        "reason":     best.get("reason", ""),
        "equity_start": equity,
        "exit":       None,
        "exit_time":  None,
        "exit_reason": None,
        "pnl_pct":    None,
        "pnl_inr":    None,
        "equity_end": None,
        "status":     "open" if best.get("action") != "HOLD" else "hold",
    }

    # Remove duplicate for today if re-run
    log["calls"] = [c for c in log["calls"] if c["date"] != today]
    log["calls"].append(call)

    os.makedirs("data", exist_ok=True)
    with open(calls_path, "w") as f:
        json.dump(log, f, indent=2, default=str)

    # Console output — the "call"
    print(f"\n{'='*60}")
    if best.get("action") == "BUY":
        print(f"  TODAY'S CALL: BUY {best.get('ticker','')}")
        print(f"  Entry:     ₹{best.get('entry', 0):,.2f}")
        print(f"  Target:    ₹{best.get('target', 0):,.2f}  (+{((best.get('target',0)/best.get('entry',1))-1)*100:.1f}%)")
        print(f"  Stop Loss: ₹{best.get('stoploss', 0):,.2f}  (-{((1-(best.get('stoploss',0)/best.get('entry',1)))*100):.1f}%)")
        print(f"  VWAP:      ₹{best.get('vwap', 0):,.2f}")
        print(f"  Volume:    {best.get('vol_ratio', 0):.1f}x average")
    elif best.get("action") == "SELL":
        print(f"  TODAY'S CALL: SHORT/SELL {best.get('ticker','')}")
        print(f"  Entry:     ₹{best.get('entry', 0):,.2f}")
        print(f"  Target:    ₹{best.get('target', 0):,.2f}  (-{((1-(best.get('target',0)/best.get('entry',1)))*100):.1f}%)")
        print(f"  Stop Loss: ₹{best.get('stoploss', 0):,.2f}  (+{((best.get('stoploss',0)/best.get('entry',1))-1)*100:.1f}%)")
        print(f"  VWAP:      ₹{best.get('vwap', 0):,.2f}")
    else:
        print(f"  TODAY'S CALL: HOLD — {best.get('reason', 'No signal')}")
        print(f"  Sit out today. No clear setup.")

    print(f"\n  Capital tracking: ₹{equity:,.0f}")
    print(f"{'='*60}\n")

    # Write GitHub Actions summary
    with open(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null"), "a") as f:
        action = best.get("action", "HOLD")
        ticker = best.get("ticker", "—")
        if action == "BUY":
            f.write(f"## 📈 TODAY'S CALL: BUY {ticker}\n")
            f.write(f"| | |\n|---|---|\n")
            f.write(f"| Entry | ₹{best.get('entry',0):,.2f} |\n")
            f.write(f"| Target | ₹{best.get('target',0):,.2f} |\n")
            f.write(f"| Stop Loss | ₹{best.get('stoploss',0):,.2f} |\n")
            f.write(f"| VWAP | ₹{best.get('vwap',0):,.2f} |\n")
            f.write(f"| Volume | {best.get('vol_ratio',0):.1f}x |\n")
        elif action == "SELL":
            f.write(f"## 📉 TODAY'S CALL: SHORT {ticker}\n")
            f.write(f"| Entry | ₹{best.get('entry',0):,.2f} |\n")
            f.write(f"| Target | ₹{best.get('target',0):,.2f} |\n")
            f.write(f"| Stop Loss | ₹{best.get('stoploss',0):,.2f} |\n")
        else:
            f.write(f"## ⏸️ TODAY'S CALL: HOLD\n{best.get('reason','')}\n")
        f.write(f"\n**Capital:** ₹{equity:,.0f}\n")

    return call


if __name__ == "__main__":
    generate_morning_call()
