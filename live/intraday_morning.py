"""
9:45 AM Signal — Backtest-Weighted ORB + VWAP
─────────────────────────────────────────────────────────────────────────────
Step 1: Load Sunday's backtest rankings (which stocks historically profit)
Step 2: Scan all ~100 Nifty stocks live at 9:45 AM
Step 3: Combined score = backtest rank (40%) + live ORB strength (60%)
         → Only consider stocks with POSITIVE backtest return
         → Among those, pick the one with strongest live breakout
Step 4: Output ONE call — entry at 9:45 price, target, stop-loss
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date
import pytz, warnings
warnings.filterwarnings("ignore")
import yfinance as yf
import pandas as pd

from strategies.intraday import calc_orb_signal

IST = pytz.timezone("Asia/Kolkata")

CALLS_PATH   = "data/daily_calls.json"
BACKTEST_PATH = "results/intraday_backtest.json"
CAPITAL      = 100_000

# Full Nifty 100+ liquid stocks (F&O eligible — tight spreads, high volume)
INTRADAY_WATCHLIST = [
    # IT & Tech
    "TCS.NS","INFY.NS","WIPRO.NS","HCLTECH.NS","TECHM.NS",
    "MPHASIS.NS","COFORGE.NS","PERSISTENT.NS","OFSS.NS",
    # Banking
    "HDFCBANK.NS","ICICIBANK.NS","KOTAKBANK.NS","SBIN.NS","AXISBANK.NS",
    "INDUSINDBK.NS","FEDERALBNK.NS","IDFCFIRSTB.NS","BANDHANBNK.NS",
    "BANKBARODA.NS","PNB.NS","UNIONBANK.NS",
    # NBFC & Financials
    "BAJFINANCE.NS","BAJAJFINSV.NS","HDFCLIFE.NS","SBILIFE.NS",
    "CHOLAFIN.NS","MUTHOOTFIN.NS","SHRIRAMFIN.NS","RECLTD.NS","PFC.NS","IRFC.NS",
    # Energy
    "RELIANCE.NS","ONGC.NS","BPCL.NS","IOC.NS","COALINDIA.NS",
    "POWERGRID.NS","NTPC.NS","TATAPOWER.NS","ADANIGREEN.NS",
    # Industrials
    "LT.NS","ADANIENT.NS","ADANIPORTS.NS","SIEMENS.NS","ABB.NS",
    "BHEL.NS","HAVELLS.NS","POLYCAB.NS","VOLTAS.NS",
    # Cement
    "ULTRACEMCO.NS","GRASIM.NS","AMBUJACEM.NS","ACC.NS",
    # Metals
    "JSWSTEEL.NS","TATASTEEL.NS","HINDALCO.NS","VEDL.NS","SAIL.NS","NMDC.NS",
    # Auto
    "MARUTI.NS","BAJAJ-AUTO.NS","HEROMOTOCO.NS",
    "EICHERMOT.NS","M&M.NS","ASHOKLEY.NS","BALKRISIND.NS",
    # FMCG
    "HINDUNILVR.NS","ITC.NS","NESTLEIND.NS","BRITANNIA.NS",
    "TATACONSUM.NS","ASIANPAINT.NS","GODREJCP.NS","MARICO.NS","DABUR.NS","PIDILITIND.NS",
    # Pharma
    "SUNPHARMA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS","APOLLOHOSP.NS",
    "LUPIN.NS","TORNTPHARM.NS","AUROPHARMA.NS","ZYDUSLIFE.NS",
    # Consumer
    "TITAN.NS","DMART.NS","TRENT.NS","JUBLFOOD.NS",
    # Telecom & Others
    "BHARTIARTL.NS","NAUKRI.NS","INDIGO.NS","DLF.NS","GODREJPROP.NS",
    "ZOMATO.NS",
]


def fetch_intraday(ticker: str) -> pd.DataFrame:
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


def load_backtest_rankings() -> dict:
    """
    Load Sunday's backtest results.
    Returns dict: ticker → return_pct
    Only includes stocks with positive backtest return.
    """
    if not os.path.exists(BACKTEST_PATH):
        return {}
    try:
        with open(BACKTEST_PATH) as f:
            bt = json.load(f)
        rankings = {}
        for r in bt.get("results", []):
            if r.get("return_pct", 0) > 0:          # only profitable in backtest
                rankings[r["ticker"]] = r["return_pct"]
        return rankings
    except:
        return {}


def pick_best_call() -> dict:
    """
    Scan all stocks. Combine backtest rank + live ORB score.
    Return ONE best call.
    """
    bt_rankings = load_backtest_rankings()
    has_backtest = len(bt_rankings) > 0

    print(f"\n{'='*65}")
    print(f"  INTRADAY SIGNAL ENGINE — {datetime.now(IST).strftime('%d %b %Y  %I:%M %p IST')}")
    print(f"  Strategy: ORB + VWAP  |  Stocks: {len(INTRADAY_WATCHLIST)}  |  Backtest filter: {'ON' if has_backtest else 'OFF (no backtest data)'}")
    print(f"{'='*65}\n")

    if has_backtest:
        max_ret = max(bt_rankings.values())
        min_ret = min(bt_rankings.values())
        ret_range = max_ret - min_ret if max_ret != min_ret else 1.0
        print(f"  Backtest profitable stocks: {len(bt_rankings)} / {len(INTRADAY_WATCHLIST)}")
        print(f"  Best backtest performer: {max(bt_rankings, key=bt_rankings.get)} (+{max_ret:.1f}%)\n")

    candidates = []

    for ticker in INTRADAY_WATCHLIST:
        # --- Step 1: backtest filter ---
        bt_ret = bt_rankings.get(ticker, None)
        if has_backtest and bt_ret is None:
            continue  # Skip stocks that lost money in backtest

        # --- Step 2: live ORB signal ---
        df = fetch_intraday(ticker)
        if df.empty:
            continue

        sig = calc_orb_signal(df)

        # --- Filter 1: BUY only, no short/sell ---
        if sig["action"] != "BUY":
            continue

        # --- Filter 2: Expected return must be ≥ 1% (entry → target) ---
        entry  = sig.get("entry", 0)
        target = sig.get("target", 0)
        expected_return = ((target / entry) - 1) * 100 if entry else 0
        if expected_return < 1.0:
            print(f"  ─ {ticker:<20} BUY signal but return only {expected_return:.2f}% — skipped (< 1%)")
            continue

        # --- Step 3: combined score ---
        live_score = abs(sig.get("score", 0))

        if has_backtest and bt_ret is not None:
            bt_score = (bt_ret - min_ret) / ret_range
            combined = (bt_score * 0.40) + (live_score * 0.60)
        else:
            combined = live_score
            bt_score = 0.0
            bt_ret   = 0.0

        sig["ticker"]         = ticker
        sig["bt_return"]      = round(bt_ret, 2)
        sig["bt_score"]       = round(bt_score, 3)
        sig["live_score"]     = round(live_score, 3)
        sig["combined_score"] = round(combined, 4)
        sig["expected_return"]= round(expected_return, 2)
        candidates.append(sig)

        print(f"  ▲ {ticker:<20} ORB={live_score:.3f}  BT={bt_ret:+.1f}%  Exp={expected_return:.1f}%  Combined={combined:.3f}")

    if not candidates:
        print("\n  No actionable setup today — all stocks either failed backtest filter or have no ORB breakout.")
        return {
            "action":  "HOLD",
            "ticker":  "—",
            "reason":  "No stock passed both backtest filter and live ORB signal",
            "score":   0,
            "entry":   None,
        }

    # Pick the highest combined score
    best = max(candidates, key=lambda x: x["combined_score"])

    print(f"\n{'─'*65}")
    print(f"  WINNER: {best['ticker']}  ({best['action']})")
    print(f"  Live ORB score:  {best['live_score']:.3f}")
    print(f"  Backtest return: {best['bt_return']:+.1f}% (60-day)")
    print(f"  Combined score:  {best['combined_score']:.4f}")
    print(f"{'─'*65}\n")

    return best


def generate_morning_call():
    today = str(date.today())
    now   = datetime.now(IST).strftime("%I:%M %p IST")

    best = pick_best_call()

    # Load or init calls log
    if os.path.exists(CALLS_PATH):
        with open(CALLS_PATH) as f:
            log = json.load(f)
    else:
        log = {"calls": [], "equity": CAPITAL}

    equity = log.get("equity", CAPITAL)

    call = {
        "date":           today,
        "signal_time":    now,
        "ticker":         best.get("ticker", "—"),
        "action":         best.get("action", "HOLD"),
        "entry":          best.get("entry"),           # exact 9:45 price
        "target":         best.get("target"),
        "stoploss":       best.get("stoploss"),
        "or_high":        best.get("or_high"),
        "or_low":         best.get("or_low"),
        "vwap":           best.get("vwap"),
        "vol_ratio":      best.get("vol_ratio"),
        "reason":         best.get("reason", ""),
        "bt_return":      best.get("bt_return", 0),
        "live_score":     best.get("live_score", 0),
        "combined_score": best.get("combined_score", 0),
        "equity_start":   equity,
        "exit":           None,
        "exit_time":      None,
        "exit_reason":    None,
        "pnl_pct":        None,
        "pnl_inr":        None,
        "equity_end":     None,
        "status":         "open" if best.get("action") not in ("HOLD", None) else "hold",
    }

    # Remove any existing call for today (re-run protection)
    log["calls"] = [c for c in log["calls"] if c["date"] != today]
    log["calls"].append(call)

    os.makedirs("data", exist_ok=True)
    with open(CALLS_PATH, "w") as f:
        json.dump(log, f, indent=2, default=str)

    # ─── Print the call ───────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    action = best.get("action", "HOLD")
    ticker = best.get("ticker", "—")

    if action in ("BUY", "SELL"):
        direction = "BUY  ▲" if action == "BUY" else "SELL ▼"
        entry     = best.get("entry", 0)
        target    = best.get("target", 0)
        sl        = best.get("stoploss", 0)
        upside    = abs((target / entry - 1) * 100) if entry else 0
        downside  = abs((sl / entry - 1) * 100) if entry else 0

        print(f"  TODAY'S CALL: {direction}  {ticker}")
        print(f"")
        print(f"  Entry Price : ₹{entry:,.2f}   (9:45 AM price)")
        print(f"  Target      : ₹{target:,.2f}   (+{upside:.1f}%)  ← sell here")
        print(f"  Stop Loss   : ₹{sl:,.2f}   (-{downside:.1f}%)")
        print(f"  VWAP        : ₹{best.get('vwap',0):,.2f}")
        print(f"  Volume      : {best.get('vol_ratio',0):.1f}x average")
        print(f"  Backtest    : +{best.get('bt_return',0):.1f}% (60-day ORB)")
        print(f"")
        print(f"  EXIT RULE   : Sell at ₹{target:,.2f} if hit, else close at 3:30 PM")
        print(f"  Capital     : ₹{equity:,.0f}")
    else:
        print(f"  TODAY'S CALL: HOLD")
        print(f"  {best.get('reason', 'No setup today')}")

    print(f"{'='*65}\n")

    # GitHub Actions step summary
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null")
    with open(summary_path, "a") as f:
        if action in ("BUY", "SELL"):
            icon = "📈" if action == "BUY" else "📉"
            entry  = best.get("entry", 0)
            target = best.get("target", 0)
            sl     = best.get("stoploss", 0)
            f.write(f"## {icon} {action}: **{ticker}** @ ₹{entry:,.2f}\n\n")
            f.write(f"| | |\n|---|---|\n")
            f.write(f"| **Entry** | ₹{entry:,.2f} (9:45 AM) |\n")
            f.write(f"| **Target** | ₹{target:,.2f} (+{abs((target/entry-1)*100):.1f}%) |\n")
            f.write(f"| **Stop Loss** | ₹{sl:,.2f} (-{abs((sl/entry-1)*100):.1f}%) |\n")
            f.write(f"| **VWAP** | ₹{best.get('vwap',0):,.2f} |\n")
            f.write(f"| **Volume** | {best.get('vol_ratio',0):.1f}x avg |\n")
            f.write(f"| **Backtest (60d)** | +{best.get('bt_return',0):.1f}% |\n")
            f.write(f"| **Combined Score** | {best.get('combined_score',0):.4f} |\n")
            f.write(f"\n> Exit at ₹{target:,.2f} if target hit, else close at 3:30 PM\n")
            f.write(f"\n**Running Capital:** ₹{equity:,.0f}\n")
        else:
            f.write(f"## ⏸️ HOLD — No trade today\n{best.get('reason','')}\n")

    return call


if __name__ == "__main__":
    generate_morning_call()
