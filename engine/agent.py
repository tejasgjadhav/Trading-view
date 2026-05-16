"""
AVCM Signal Engine — Main Orchestrator
Runs every 5 min during market hours via GitHub Actions.

Usage:
    python -m engine.agent              # run once (continuous mode)
    python -m engine.agent --backtest   # backtest only
    python -m engine.agent --fresh      # force fresh backtest
    python -m engine.agent --continuous # explicit continuous flag (same as default)
"""
import argparse, json, os, sys, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date
import pytz

from engine.recommendation import generate_recommendation, generate_midday_recommendation, generate_continuous_recommendation
from engine.config import CAPITAL, CALLS_PATH, SCAN_LOG_PATH, REPORTS_DIR, IST, KILL_SWITCH_TIME, SIGNAL_CUTOFF


def send_whatsapp_alert(rec: dict):
    """Send WhatsApp message via CallMeBot when an AVCM BUY signal fires."""
    phone  = os.environ.get("CALLMEBOT_PHONE")
    apikey = os.environ.get("CALLMEBOT_APIKEY")
    if not phone or not apikey:
        print("  [WhatsApp] CALLMEBOT_PHONE / CALLMEBOT_APIKEY not set — skipping alert")
        return

    calls = rec.get("calls", [rec])
    r     = calls[0]
    now   = datetime.now(IST).strftime("%I:%M %p IST")
    vix   = r.get("vix_level", "—")
    t1    = r.get("tranche_1", {})
    t2    = r.get("tranche_2", {})

    lines = [
        f"📈 *AVCM SIGNAL — {r['ticker']}*",
        f"⏰ {now}  |  Signals: {r['signals_aligned']}/5  |  VIX: {vix}",
        f"",
        f"Entry (Limit):  ₹{r['entry']:,.2f}  (ORB High + 0.1%)",
        f"Stop Loss:      ₹{r['stop_loss']:,.2f}  (ORB Low − 0.2%)",
        f"R:R:            {r['reward_risk']:.1f}:1",
        f"",
        f"🎯 Exit Plan (Tranches):",
        f"  Exit 1 (35%): ₹{t1.get('at_price', 0):,.2f} → move stop to breakeven",
        f"  Exit 2 (35%): ₹{r['target']:,.2f} or {SIGNAL_CUTOFF} PM",
        f"  Exit 3 (30%): Force close at {KILL_SWITCH_TIME} IST",
        f"",
        f"Size: {r['shares']} shares  ({r['invest_pct']}% of equity)",
        f"BT Win Rate: {r['bt_win_rate']:.0%}  |  Score: {r.get('composite_score', 0):.0f}/100",
        f"Retest: {'YES +25% size' if r.get('is_retest') else 'No'}",
        f"",
        f"⚠ Educational only. Not financial advice.",
    ]
    if len(calls) > 1:
        r2 = calls[1]
        lines.insert(4, f"\n2nd: {r2['ticker']} @ ₹{r2['entry']:,.2f}  Stop ₹{r2['stop_loss']:,.2f}")

    msg = "\n".join(lines)
    url = ("https://api.callmebot.com/whatsapp.php?"
           + urllib.parse.urlencode({"phone": phone, "text": msg, "apikey": apikey}))
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            print(f"  [WhatsApp] Alert sent → {resp.status}")
    except Exception as e:
        print(f"  [WhatsApp] Failed: {e}")


def print_recommendation(rec: dict):
    print(f"\n{'='*65}")
    print(f"  AVCM SIGNAL ENGINE — FINAL CALL")
    print(f"{'='*65}")

    if rec["action"] == "NO_TRADE":
        print(f"\n  NO TRADE")
        print(f"  Reason: {rec['reason']}")
        print(f"{'='*65}")
        return

    calls  = rec.get("calls", [rec])
    alloc  = rec.get("allocation", {})

    FACTOR_LABELS = {
        "structural_breakout": "Structural Breakout (close > ORB High)",
        "volume_confirm":      "Volume Confirm (≥2× ORB per-bar avg)",
        "vwap_position":       "Above VWAP",
        "rsi_momentum":        "RSI 55–72 (momentum window)",
        "market_align":        "Market Aligned (Nifty positive)",
    }

    for i, call in enumerate(calls):
        label = "PRIMARY" if i == 0 else "SECONDARY"
        print(f"\n  [{label}] BUY {call['ticker']}")
        print(f"  {'─'*55}")
        print(f"  Entry (Limit)  : ₹{call['entry']:,.2f}   (ORB High + 0.1% — LIMIT ORDER)")
        print(f"  Stop Loss      : ₹{call['stop_loss']:,.2f}   (ORB Low − 0.2% — place immediately)")
        print(f"  R:R Ratio      : {call['reward_risk']:.1f}:1")
        print(f"  VIX            : {call.get('vix_level', '—')}  → {call['invest_pct']}% of equity sizing")
        if call.get("is_retest"):
            print(f"  ★ RETEST SIGNAL: +25% position size (higher quality)")
        print(f"")
        print(f"  ── Tranche Exit Plan ──────────────────────────────")
        t1, t2, t3 = call.get("tranche_1", {}), call.get("tranche_2", {}), call.get("tranche_3", {})
        print(f"  Exit 1 (35%):  ₹{t1.get('at_price',0):,.2f}  → {t1.get('action','')}")
        print(f"  Exit 2 (35%):  ₹{call['target']:,.2f}  target  OR at {SIGNAL_CUTOFF} PM")
        print(f"  Exit 3 (30%):  Force close at {KILL_SWITCH_TIME} IST (VWAP limit, market if unfilled by 3:18)")
        print(f"")
        print(f"  ── Composite Score: {call.get('composite_score',0):.1f}/100  (time-decay applied) ──")
        for k, pts in call.get("score_breakdown", {}).items():
            bar = "█" * int(pts / 5) if pts > 0 else ""
            lbl = {"max_1day_return":"Max 1-Day BT","win_rate":"BT Win Rate",
                   "sharpe_ratio":"Sharpe","confidence":"Signal Confidence",
                   "expected_return":"Expected Return","vol_ratio":"Volume"}.get(k, k)
            print(f"    {lbl:<30} {pts:5.1f}  {bar}")
        print(f"")
        print(f"  ── AVCM 5-Factor Check (ALL must be ✓) ───────────")
        for k, v in call.get("signals_detail", {}).items():
            icon = "[✓]" if v == 1 else "[✗]"
            print(f"    {icon}  {FACTOR_LABELS.get(k, k)}")
        print(f"")
        print(f"  VWAP: ₹{call['vwap']:,.2f}  ORB: ₹{call['orb_low']:,.2f}–₹{call['orb_high']:,.2f}  RSI: {call['rsi']}")
        print(f"  Vol ratio (daily): {call['vol_ratio']:.1f}×  Vol ratio (ORB bar): {call.get('vol_ratio_orb',0):.1f}×")
        print(f"  BT WR: {call['bt_win_rate']:.1%}  Sharpe: {call['bt_sharpe']:.2f}  Strategy: {call['bt_strategy']}")

    print(f"\n{'─'*65}")
    print(f"  ALLOCATION  —  {alloc.get('commentary','')}")
    p = alloc.get("primary")
    s = alloc.get("secondary")
    if p: print(f"\n  PRIMARY   {p['ticker']:<18} ₹{p['invest_inr']:>9,.0f} ({p['invest_pct']}%)  {p['shares']} shares")
    if s: print(f"  SECONDARY {s['ticker']:<18} ₹{s['invest_inr']:>9,.0f} ({s['invest_pct']}%)  {s['shares']} shares")
    print(f"  CASH RESERVE            ₹{alloc.get('cash_reserve',0):>9,.0f}")
    print(f"\n{'='*65}\n")


def save_to_calls_log(rec: dict, continuous: bool = False):
    """Merge into existing daily_calls.json for dashboard."""
    import math

    def _clean(obj):
        if isinstance(obj, dict):  return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):  return [_clean(v) for v in obj]
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)): return None
        return obj

    today = str(date.today())
    if os.path.exists(CALLS_PATH):
        with open(CALLS_PATH) as f:
            log = json.load(f)
    else:
        log = {"calls": [], "equity": CAPITAL}

    equity = log.get("equity", CAPITAL)

    if rec["action"] == "NO_TRADE":
        call = {
            "date": today, "action": "HOLD", "ticker": "-",
            "reason": rec["reason"], "status": "hold", "equity_start": equity,
        }
        log["calls"] = [c for c in log["calls"] if c["date"] != today]
        log["calls"].append(call)
    else:
        calls = rec.get("calls", [rec])
        alloc = rec.get("allocation", {})
        if not continuous:
            log["calls"] = [c for c in log["calls"] if c["date"] != today]

        session = rec.get("signal_session", "CONTINUOUS")
        for i, r in enumerate(calls):
            a_key  = "primary" if i == 0 else "secondary"
            a_info = alloc.get(a_key, {})
            t1     = r.get("tranche_1", {})
            t2     = r.get("tranche_2", {})
            call = {
                "date":             today,
                "signal_time":      datetime.now(IST).strftime("%I:%M %p IST"),
                "signal_session":   session,
                "call_rank":        "primary" if i == 0 else "secondary",
                "ticker":           r["ticker"],
                "action":           "BUY",
                "entry":            r["entry"],
                "target":           r["target"],
                "stoploss":         r["stop_loss"],
                "expected_return":  r["expected_return"],
                "reward_risk":      r["reward_risk"],
                "shares":           a_info.get("shares", r["shares"]),
                "invest_inr":       a_info.get("invest_inr", r["invest_inr"]),
                "invest_pct":       a_info.get("invest_pct", r["invest_pct"]),
                "position_value":   r.get("position_value", r["invest_inr"]),
                "vix_level":        r.get("vix_level"),
                "is_retest":        r.get("is_retest", False),
                "tranche_1_price":  t1.get("at_price"),
                "tranche_2_price":  r["target"],
                "tranche_3_time":   KILL_SWITCH_TIME,
                "vwap":             r["vwap"],
                "orb_high":         r["orb_high"],
                "orb_low":          r["orb_low"],
                "rsi":              r["rsi"],
                "vol_ratio":        r.get("vol_ratio"),
                "vol_ratio_orb":    r.get("vol_ratio_orb"),
                "signals_aligned":  r["signals_aligned"],
                "confidence":       r["confidence"],
                "regime":           r["regime"],
                "bt_win_rate":      r["bt_win_rate"],
                "bt_sharpe":        r["bt_sharpe"],
                "bt_strategy":      r["bt_strategy"],
                "bt_max_1day":      r.get("bt_max_1day", 0),
                "signals_detail":   r.get("signals_detail", {}),
                "composite_score":  r.get("composite_score", 0),
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
        json.dump(_clean(log), f, indent=2, default=str)

    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(f"{REPORTS_DIR}/rec_{today}.json", "w") as f:
        json.dump(rec, f, indent=2, default=str)

    # GitHub Actions step summary
    summary = os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null")
    with open(summary, "a") as f:
        if rec["action"] == "NO_TRADE":
            f.write(f"## ⏸️ NO TRADE — {today}\n{rec['reason']}\n")
        else:
            calls = rec.get("calls", [rec])
            for i, r in enumerate(calls):
                label  = "📈 PRIMARY" if i == 0 else "📊 SECONDARY"
                t1     = r.get("tranche_1", {})
                f.write(f"## {label}: **{r['ticker']}** @ ₹{r['entry']:,.2f}\n\n")
                f.write(f"| | |\n|---|---|\n")
                f.write(f"| **Entry (Limit)** | ₹{r['entry']:,.2f} |\n")
                f.write(f"| **Target** | ₹{r['target']:,.2f} (+{r['expected_return']:.1f}%) |\n")
                f.write(f"| **Stop Loss** | ₹{r['stop_loss']:,.2f} |\n")
                f.write(f"| **Exit 1 (35%)** | ₹{t1.get('at_price',0):,.2f} → stop to breakeven |\n")
                f.write(f"| **VIX** | {r.get('vix_level','—')} → {r['invest_pct']}% equity |\n")
                f.write(f"| **Signals** | {r['signals_aligned']}/5 (AVCM all-5 rule) |\n")
                f.write(f"| **Retest** | {'YES +25%' if r.get('is_retest') else 'No'} |\n")
                f.write(f"| **Invest** | ₹{r['invest_inr']:,.0f} — {r['shares']} shares |\n\n")


def save_scan_log(rec: dict):
    """Append every 5-min scan result to scan_log.json."""
    import math

    def _clean(obj):
        if isinstance(obj, dict):  return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):  return [_clean(v) for v in obj]
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)): return None
        return obj

    now_ist = datetime.now(IST)
    today   = str(date.today())
    if os.path.exists(SCAN_LOG_PATH):
        with open(SCAN_LOG_PATH) as f:
            log = json.load(f)
    else:
        log = {"scans": []}

    calls_list = rec.get("calls", []) if rec.get("action") == "BUY" else []
    time_mult  = calls_list[0].get("time_mult", 1.0) if calls_list else None
    entry = {
        "date":       today,
        "time":       now_ist.strftime("%I:%M %p IST"),
        "action":     rec.get("action", "NO_TRADE"),
        "reason":     rec.get("reason", ""),
        "tickers":    [c["ticker"] for c in calls_list],
        "scores":     [round(c.get("composite_score", 0), 1) for c in calls_list],
        "signals":    [c.get("signals_aligned", 0) for c in calls_list],
        "time_mult":  round(time_mult, 2) if time_mult is not None else None,
        "conviction": rec.get("conviction", ""),
    }
    log["scans"].append(_clean(entry))
    os.makedirs(os.path.dirname(SCAN_LOG_PATH), exist_ok=True)
    with open(SCAN_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2, default=str)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtest",   action="store_true")
    parser.add_argument("--fresh",      action="store_true")
    parser.add_argument("--continuous", action="store_true")
    args = parser.parse_args()

    if args.backtest:
        from engine.backtest import run_all_backtests
        from engine.config import CASH_EQUITIES
        print("Running 2-year backtest...")
        df = run_all_backtests(CASH_EQUITIES, ["ORB", "VWAP", "MOMENTUM"])
        if df.empty:
            print("No strategies passed win rate threshold.")
        else:
            cols = ["ticker","strategy","win_rate","max_1day_return","total_trades","sharpe_ratio"]
            print(df[[c for c in cols if c in df.columns]].to_string(index=False))
    else:
        # Both --continuous flag and default run the same AVCM continuous scan
        rec = generate_continuous_recommendation()
        print_recommendation(rec)
        save_scan_log(rec)
        if rec.get("action") == "BUY":
            save_to_calls_log(rec, continuous=True)
            send_whatsapp_alert(rec)
        else:
            print(f"  [{rec.get('reason','')}]")
