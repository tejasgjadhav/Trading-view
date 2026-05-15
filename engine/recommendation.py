"""
Quant Signal Engine — Recommendation Generator
─────────────────────────────────────────────────────────────────────────────
Outputs UP TO TWO calls per day. ALWAYS outputs at least one stock.

4-TIER FALLBACK — something always comes out:
  Tier 1 (HIGH conviction)        → 70% WR + ≥3/7 live signals
  Tier 2 (MEDIUM conviction)      → 70% WR + ≥1/7 live signals
  Tier 3 (BEST MATCH)             → 60-day ORB data (all 95 stocks) + best live signals
  Tier 4 (EXPLORATORY)            → Pure live scan, all 95 stocks, no backtest gate

COMPOSITE SCORE (0–100) across 6 parameters:
  max_1day_return (25%) · win_rate (20%) · sharpe (15%) ·
  live_confidence (20%) · expected_return (10%) · vol_ratio (10%)
"""
import os, json, warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
from datetime import datetime

from engine.config import (
    CASH_EQUITIES, WATCHLIST, MIN_WIN_RATE_THRESHOLD,
    MIN_SIGNALS_REQUIRED, MIN_SIGNALS_WATCHLIST,
    MIN_REWARD_RISK, MIN_RETURN_PCT, CAPITAL, KILL_SWITCH_TIME,
    ONLY_BUY, IST, CALLS_PATH, SCORE_WEIGHTS, ORB_BACKTEST_PATH,
    MORNING_ENTRY_BAR, MIDDAY_ENTRY_BAR
)
from engine.data_fetcher import fetch_historical, fetch_intraday, get_previous_day_levels
from engine.signals import compute_signals
from engine.backtest import load_or_run_backtest
from engine.risk_manager import RiskManager


# ── Conviction labels ────────────────────────────────────────────────────────
CONVICTION_HIGH   = "HIGH"
CONVICTION_MEDIUM = "MEDIUM"
CONVICTION_BEST   = "BEST MATCH"
CONVICTION_EXPLO  = "EXPLORATORY"


def _no_trade(reason: str) -> dict:
    return {
        "action":     "NO_TRADE",
        "reason":     reason,
        "timestamp":  datetime.now(IST).isoformat(),
        "calls":      [],
        "allocation": None,
    }


# ── Composite scorer ─────────────────────────────────────────────────────────

def _normalize(values: list, cap: float = None) -> list:
    arr = [min(float(v), cap) if cap else float(v) for v in values]
    lo, hi = min(arr), max(arr)
    if hi == lo:
        return [1.0] * len(arr)
    return [(v - lo) / (hi - lo) for v in arr]


def compute_composite_scores(candidates: list) -> list:
    """
    Add composite_score (0-100) and score_breakdown to each candidate.
    Normalizes each factor across the pool before weighting.
    """
    if not candidates:
        return candidates

    def col(key):
        return [float(c.get(key, 0) or 0) for c in candidates]

    factors = {
        "max_1day_return": _normalize(col("bt_max_1day_return"), cap=10.0),
        "win_rate":        _normalize(col("bt_win_rate")),
        "sharpe_ratio":    _normalize(col("bt_sharpe"), cap=5.0),
        "confidence":      _normalize(col("confidence")),
        "expected_return": _normalize(col("expected_return"), cap=5.0),
        "vol_ratio":       _normalize([min(v, 3.0) for v in col("vol_ratio")]),
    }

    for i, c in enumerate(candidates):
        score = sum(SCORE_WEIGHTS[k] * factors[k][i] for k in SCORE_WEIGHTS) * 100
        c["composite_score"] = round(score, 1)
        c["score_breakdown"] = {k: round(SCORE_WEIGHTS[k] * factors[k][i] * 100, 1) for k in SCORE_WEIGHTS}

    return sorted(candidates, key=lambda x: x["composite_score"], reverse=True)


# ── Live signal scanner ───────────────────────────────────────────────────────

def _scan_live(tickers: list, bt_lookup: dict = None, entry_bar_idx: int = MORNING_ENTRY_BAR) -> list:
    results = []
    for ticker in tickers:
        try:
            df_daily = fetch_historical(ticker, years=0.5)
            df_5min  = fetch_intraday(ticker, interval="5m", period="1d")
            if df_5min.empty or len(df_5min) < max(6, entry_bar_idx + 1):
                continue
            levels = get_previous_day_levels(ticker, df_daily)
            sig    = compute_signals(df_daily, df_5min,
                                     levels["pdh"], levels["pdl"], levels["pdc"],
                                     entry_bar_idx=entry_bar_idx)
            sig["ticker"] = ticker
            bt = (bt_lookup or {}).get(ticker, {})
            sig["bt_win_rate"]        = float(bt.get("win_rate", 0) or 0)
            sig["bt_sharpe"]          = float(bt.get("sharpe_ratio", bt.get("sharpe", 0)) or 0)
            sig["bt_strategy"]        = bt.get("strategy", "ORB")
            sig["bt_max_1day_return"] = float(bt.get("max_1day_return", 0) or 0)
            # Pre-compute expected_return for scoring
            entry   = sig.get("current_price", 0)
            orb_low = sig.get("orb_low", entry * 0.99)
            stop    = orb_low * 0.998
            risk    = entry - stop
            target  = entry + risk * MIN_REWARD_RISK if risk > 0 else entry * 1.02
            sig["expected_return"] = round((target / entry - 1) * 100, 2) if entry else 0
            results.append(sig)
        except Exception:
            pass
    return results


# ── Level builder ────────────────────────────────────────────────────────────

def _build_call(sig: dict, now_ist: datetime, conviction: str):
    ticker  = sig["ticker"]
    entry   = sig.get("current_price", 0)
    orb_low = sig.get("orb_low", entry * 0.99)
    vwap    = sig.get("vwap", entry)

    if not entry or entry <= 0:
        return None

    stop  = round(orb_low * 0.998, 2)
    risk  = entry - stop
    if risk <= 0:
        return None

    target = round(entry + risk * MIN_REWARD_RISK, 2)
    exp    = (target / entry - 1) * 100
    rr     = (target - entry) / (entry - stop)

    if exp < MIN_RETURN_PCT or rr < MIN_REWARD_RISK:
        return None

    sizing = RiskManager().kelly_position(
        win_rate=max(sig.get("bt_win_rate", 0.5), 0.5),
        entry=entry, stop=stop
    )

    return {
        "action":           "BUY",
        "ticker":           ticker,
        "entry":            round(entry, 2),
        "target":           round(target, 2),
        "stop_loss":        stop,
        "expected_return":  round(exp, 2),
        "reward_risk":      round(rr, 2),
        "shares":           sizing["shares"],
        "position_value":   sizing["position_value"],
        "risk_amount":      sizing["risk_amount"],
        "risk_pct":         sizing["risk_pct"],
        "kelly_pct":        sizing["kelly_pct"],
        "signals_aligned":  sig.get("signals_aligned", 0),
        "signals_detail":   sig.get("signals_detail", {}),
        "confidence":       sig.get("confidence", 0),
        "regime":           sig.get("regime", "UNKNOWN"),
        "vwap":             vwap,
        "orb_high":         sig.get("orb_high", entry * 1.005),
        "orb_low":          orb_low,
        "rsi":              sig.get("rsi", 50),
        "vol_ratio":        sig.get("vol_ratio", 0),
        "bt_win_rate":      round(sig.get("bt_win_rate", 0), 4),
        "bt_sharpe":        round(sig.get("bt_sharpe", 0), 3),
        "bt_strategy":      sig.get("bt_strategy", "ORB"),
        "bt_max_1day":      round(sig.get("bt_max_1day_return", 0), 2),
        "composite_score":  sig.get("composite_score", 0),
        "score_breakdown":  sig.get("score_breakdown", {}),
        "conviction":       conviction,
        "exit_rule":        f"Sell at ₹{round(target,2):,.2f} if hit. Close ALL by {KILL_SWITCH_TIME} IST.",
        "timestamp":        now_ist.isoformat(),
    }


def _force_call(sig: dict, now_ist: datetime, conviction: str) -> dict:
    """Last-resort call with default 1.5% stop / 2% target when ORB levels fail."""
    entry  = sig.get("current_price", 0)
    stop   = round(entry * 0.985, 2)
    target = round(entry * 1.02, 2)
    shares = max(1, int(CAPITAL * 0.10 / entry)) if entry else 1
    return {
        "action": "BUY", "ticker": sig["ticker"],
        "entry": round(entry, 2), "target": target, "stop_loss": stop,
        "expected_return": 2.0, "reward_risk": round((target-entry)/(entry-stop), 2),
        "shares": shares, "position_value": round(shares*entry, 2),
        "risk_amount": round(shares*(entry-stop), 2), "risk_pct": 1.5, "kelly_pct": 10.0,
        "signals_aligned": sig.get("signals_aligned", 0),
        "signals_detail": sig.get("signals_detail", {}),
        "confidence": sig.get("confidence", 0), "regime": sig.get("regime", "UNKNOWN"),
        "vwap": sig.get("vwap", entry), "orb_high": sig.get("orb_high", entry*1.005),
        "orb_low": sig.get("orb_low", entry*0.995), "rsi": sig.get("rsi", 50),
        "vol_ratio": sig.get("vol_ratio", 1), "bt_win_rate": sig.get("bt_win_rate", 0),
        "bt_sharpe": sig.get("bt_sharpe", 0), "bt_strategy": sig.get("bt_strategy", "ORB"),
        "bt_max_1day": sig.get("bt_max_1day_return", 0),
        "composite_score": sig.get("composite_score", 0),
        "score_breakdown": sig.get("score_breakdown", {}),
        "conviction": conviction,
        "exit_rule": f"Close by {KILL_SWITCH_TIME} IST. Default levels used (ORB data unavailable).",
        "timestamp": now_ist.isoformat(),
    }


# ── Allocation commentary ─────────────────────────────────────────────────────

def _allocation_commentary(calls: list, capital: float = CAPITAL) -> dict:
    if not calls:
        return {}

    if len(calls) == 1:
        c = calls[0]
        invest  = min(c["position_value"], capital * 0.85)
        shares  = max(1, int(invest / c["entry"]))
        pct     = round(invest / capital * 100, 1)
        reserve = round(capital - invest)
        lines = [
            f"Single signal today.",
            f"Invest ₹{invest:,.0f} ({pct}% of ₹1L) in {c['ticker']}.",
            f"Buy {shares} shares @ ₹{c['entry']:,.2f}.",
            f"Target ₹{c['target']:,.2f} (+{c['expected_return']:.1f}%)  |  Stop ₹{c['stop_loss']:,.2f}.",
            f"Keep ₹{reserve:,.0f} as cash buffer.",
            f"Conviction: {c.get('conviction','—')}  |  Composite score: {c.get('composite_score',0):.1f}/100.",
        ]
        return {
            "primary":      {"ticker": c["ticker"], "invest_inr": round(invest), "invest_pct": pct, "shares": shares},
            "secondary":    None,
            "cash_reserve": reserve,
            "commentary":   " ".join(lines),
        }

    c1, c2 = calls[0], calls[1]
    s1 = max(c1.get("composite_score", 1), 1)
    s2 = max(c2.get("composite_score", 1), 1)
    total = s1 + s2

    alloc1 = min(c1["position_value"], capital * 0.85 * s1 / total)
    alloc2 = min(c2["position_value"], capital * 0.85 * s2 / total)
    if alloc1 + alloc2 > capital * 0.85:
        scale  = capital * 0.85 / (alloc1 + alloc2)
        alloc1 *= scale
        alloc2 *= scale

    sh1  = max(1, int(alloc1 / c1["entry"]))
    sh2  = max(1, int(alloc2 / c2["entry"]))
    p1   = round(alloc1 / capital * 100, 1)
    p2   = round(alloc2 / capital * 100, 1)
    res  = round(capital - alloc1 - alloc2)

    lines = [
        f"Two signals today — split ₹1L as follows:",
        f"► PRIMARY {c1['ticker']} (score {c1.get('composite_score',0):.0f}/100, {c1.get('conviction','')}): "
        f"₹{alloc1:,.0f} ({p1}%) — {sh1} shares @ ₹{c1['entry']:,.2f}, target +{c1['expected_return']:.1f}%.",
        f"► SECONDARY {c2['ticker']} (score {c2.get('composite_score',0):.0f}/100, {c2.get('conviction','')}): "
        f"₹{alloc2:,.0f} ({p2}%) — {sh2} shares @ ₹{c2['entry']:,.2f}, target +{c2['expected_return']:.1f}%.",
        f"► Cash buffer ₹{res:,.0f}.",
    ]
    return {
        "primary":      {"ticker": c1["ticker"], "invest_inr": round(alloc1), "invest_pct": p1, "shares": sh1},
        "secondary":    {"ticker": c2["ticker"], "invest_inr": round(alloc2), "invest_pct": p2, "shares": sh2},
        "cash_reserve": res,
        "commentary":   " ".join(lines),
    }


# ── Build result ─────────────────────────────────────────────────────────────

def _build_result(top_sigs: list, now_ist: datetime, conviction: str) -> dict:
    built = []
    for s in top_sigs:
        c = _build_call(s, now_ist, conviction)
        if c:
            built.append(c)

    # Last-resort: force levels if ORB math failed
    if not built and top_sigs:
        s = top_sigs[0]
        if s.get("current_price", 0) > 0:
            built.append(_force_call(s, now_ist, conviction))

    if not built:
        return _no_trade("Could not build valid levels for any candidate.")

    allocation = _allocation_commentary(built)
    return {
        "action":     "BUY",
        "calls":      built,
        "allocation": allocation,
        "conviction": conviction,
        "timestamp":  now_ist.isoformat(),
        **built[0],
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_orb_backtest() -> dict:
    if not os.path.exists(ORB_BACKTEST_PATH):
        return {}
    try:
        with open(ORB_BACKTEST_PATH) as f:
            data = json.load(f)
        lookup = {}
        for r in data.get("results", []):
            t = r.get("ticker", "")
            if t:
                wr = r.get("win_rate", 0)
                lookup[t] = {
                    "win_rate":        wr / 100 if wr > 1 else wr,
                    "max_1day_return": r.get("max_1day_return", 0),
                    "sharpe_ratio":    0,
                    "strategy":        "ORB",
                }
        return lookup
    except Exception:
        return {}


def _print_candidates(sigs: list, label: str):
    for s in sigs:
        print(f"  [{label}] {s['ticker']:<18} score={s.get('composite_score',0):5.1f}/100  "
              f"signals={s.get('signals_aligned',0)}/7  conf={s.get('confidence',0):.0%}  "
              f"maxDay={s.get('bt_max_1day_return',0):+.1f}%  vol={s.get('vol_ratio',0):.1f}x")


# ── Main ─────────────────────────────────────────────────────────────────────

def generate_recommendation(force_fresh_backtest: bool = False) -> dict:
    """MAIN — call at 9:45 AM. Always returns at least one call."""
    now_ist = datetime.now(IST)

    print(f"\n{'='*65}")
    print(f"  QUANT SIGNAL ENGINE — {now_ist.strftime('%d %b %Y  %I:%M %p IST')}")
    print(f"  Capital: ₹{CAPITAL:,.0f}  |  Gate: ≥{MIN_WIN_RATE_THRESHOLD:.0%} WR  |  BUY only")
    print(f"  Composite: max1d·25% + WR·20% + Sharpe·15% + conf·20% + retExp·10% + vol·10%")
    print(f"{'='*65}\n")

    # ── TIER 1 & 2: 2-year backtest gate ────────────────────────────────────
    print(f"[TIER 1/2] 2-year backtest (≥{MIN_WIN_RATE_THRESHOLD:.0%} WR)...")
    bt_df = load_or_run_backtest(CASH_EQUITIES, force_fresh=force_fresh_backtest)
    bt_lookup = {}

    if not bt_df.empty:
        for _, row in bt_df.iterrows():
            t = row["ticker"]
            if t not in bt_lookup or row.get("max_1day_return", 0) > bt_lookup[t].get("max_1day_return", 0):
                bt_lookup[t] = row.to_dict()

        top_tickers = list(bt_df["ticker"].unique()[:15])
        print(f"  {len(bt_df)} combos passed. Scanning {len(top_tickers)} live...")
        sigs = _scan_live(top_tickers, bt_lookup)
        scored = compute_composite_scores(sigs)

        tier1 = [s for s in scored if s.get("direction") == "LONG" and s.get("signals_aligned", 0) >= MIN_SIGNALS_REQUIRED]
        if tier1:
            print(f"  [TIER 1] {len(tier1)} stock(s) with ≥{MIN_SIGNALS_REQUIRED}/7 signals")
            _print_candidates(tier1[:3], "TIER 1")
            return _build_result(tier1[:2], now_ist, CONVICTION_HIGH)

        tier2 = [s for s in scored if s.get("signals_aligned", 0) >= MIN_SIGNALS_WATCHLIST]
        if tier2:
            print(f"  [TIER 2] No ≥{MIN_SIGNALS_REQUIRED} signals. Best with ≥{MIN_SIGNALS_WATCHLIST}: {len(tier2)} stock(s)")
            _print_candidates(tier2[:3], "TIER 2")
            return _build_result(tier2[:2], now_ist, CONVICTION_MEDIUM)

        print(f"  [TIER 1/2] Nothing cleared even minimum bar in 2-yr pool.")
    else:
        print(f"  [TIER 1/2] No combos passed ≥{MIN_WIN_RATE_THRESHOLD:.0%} WR gate.")

    # ── TIER 3: 60-day ORB backtest (all 95 stocks) ─────────────────────────
    print(f"\n[TIER 3] 60-day ORB backtest — full {len(WATCHLIST)}-stock universe...")
    orb_lookup = _load_orb_backtest()

    if orb_lookup:
        top_orb = sorted(orb_lookup, key=lambda t: orb_lookup[t].get("max_1day_return", 0), reverse=True)[:20]
        print(f"  Scanning top 20 stocks by max 1-day ORB return...")
        sigs   = _scan_live(top_orb, orb_lookup)
        scored = compute_composite_scores(sigs)
        best   = [s for s in scored if s.get("current_price", 0) > 0]
        if best:
            print(f"  [TIER 3] Best match: {best[0]['ticker']}  score={best[0].get('composite_score',0):.1f}/100")
            return _build_result(best[:1], now_ist, CONVICTION_BEST)

    # ── TIER 4: Pure live scan — all 95 stocks, no backtest ─────────────────
    print(f"\n[TIER 4] EXPLORATORY — live scanning all {len(WATCHLIST)} stocks...")
    sigs   = _scan_live(WATCHLIST, {})
    scored = compute_composite_scores(sigs)
    pool   = [s for s in scored if s.get("direction") == "LONG"] or scored

    if pool:
        print(f"  [TIER 4] Best exploratory: {pool[0]['ticker']}  score={pool[0].get('composite_score',0):.1f}/100")
        return _build_result(pool[:1], now_ist, CONVICTION_EXPLO)

    return _no_trade("No data available from any source. Check NSE / yfinance connectivity.")


# ── Continuous scan ───────────────────────────────────────────────────────────

def generate_continuous_recommendation() -> dict:
    """
    Called every 5 min during market hours (9:15 AM – 3:15 PM IST).
    Uses the CURRENT bar (latest price) — no fixed time anchor.
    Publishes a signal the moment ≥3/7 criteria fire.
    Skips if:
      - Before 9:45 AM (opening range not yet formed — need ≥6 bars)
      - Today already has 2 open/closed signals
      - A stock already has a signal today
    """
    now_ist = datetime.now(IST)
    hour, minute = now_ist.hour, now_ist.minute

    # Guard: need at least 9:45 AM for ORB to be established
    if hour < 9 or (hour == 9 and minute < 45):
        return _no_trade(f"Opening range not yet formed — wait until 9:45 AM IST (now {hour:02d}:{minute:02d}).")

    # Guard: market close
    if hour >= 15 and minute >= 20:
        return _no_trade("Past force-close time (3:20 PM IST). No new signals.")

    # Guard: max 2 signals per day
    open_today = _get_open_positions_today_all()
    if len(open_today) >= 2:
        tickers = [c["ticker"] for c in open_today]
        return _no_trade(f"Max 2 signals already issued today: {tickers}. No new signal.")

    avail = _remaining_capital()
    if avail < 5000:
        return _no_trade("Less than ₹5,000 available — capital fully deployed.")

    open_tickers = {c["ticker"] for c in open_today}

    print(f"\n{'='*65}")
    print(f"  CONTINUOUS SCAN — {now_ist.strftime('%d %b %Y  %I:%M %p IST')}")
    print(f"  Signals today: {len(open_today)}/2  |  Open: {open_tickers or 'none'}")
    print(f"  Available capital: ₹{avail:,.0f}")
    print(f"{'='*65}\n")

    def _filtered(tickers):
        return [t for t in tickers if t not in open_tickers]

    # -1 = dynamic/latest bar
    DYNAMIC = -1

    # TIER 1/2 — 2-year backtest gate
    bt_df = load_or_run_backtest(CASH_EQUITIES, force_fresh=False)
    bt_lookup = {}
    if not bt_df.empty:
        for _, row in bt_df.iterrows():
            t = row["ticker"]
            if t not in bt_lookup or row.get("max_1day_return", 0) > bt_lookup[t].get("max_1day_return", 0):
                bt_lookup[t] = row.to_dict()

        top_tickers = _filtered(list(bt_df["ticker"].unique()[:15]))
        if top_tickers:
            sigs   = _scan_live(top_tickers, bt_lookup, entry_bar_idx=DYNAMIC)
            scored = compute_composite_scores(sigs)

            tier1 = [s for s in scored if s.get("direction") == "LONG" and s.get("signals_aligned", 0) >= MIN_SIGNALS_REQUIRED]
            if tier1:
                print(f"  [TIER 1] Criteria met: {tier1[0]['ticker']} at {now_ist.strftime('%I:%M %p')}")
                return _build_result_continuous(tier1[:1], now_ist, CONVICTION_HIGH, avail)

            tier2 = [s for s in scored if s.get("signals_aligned", 0) >= MIN_SIGNALS_WATCHLIST]
            if tier2 and tier2[0].get("signals_aligned", 0) >= 2:
                print(f"  [TIER 2] Partial criteria: {tier2[0]['ticker']}")
                return _build_result_continuous(tier2[:1], now_ist, CONVICTION_MEDIUM, avail)

    # TIER 3
    orb_lookup = _load_orb_backtest()
    if orb_lookup:
        top_orb = _filtered(sorted(orb_lookup, key=lambda t: orb_lookup[t].get("max_1day_return", 0), reverse=True)[:20])
        if top_orb:
            sigs   = _scan_live(top_orb, orb_lookup, entry_bar_idx=DYNAMIC)
            scored = compute_composite_scores(sigs)
            tier1  = [s for s in scored if s.get("direction") == "LONG" and s.get("signals_aligned", 0) >= MIN_SIGNALS_REQUIRED]
            if tier1:
                return _build_result_continuous(tier1[:1], now_ist, CONVICTION_BEST, avail)

    return _no_trade(f"No setup meeting criteria at {now_ist.strftime('%I:%M %p IST')}. Will retry.")


# ── Midday helpers ────────────────────────────────────────────────────────────

def _get_open_positions_today() -> list:
    """Return list of open calls for today from daily_calls.json."""
    from datetime import date
    today = str(date.today())
    if not os.path.exists(CALLS_PATH):
        return []
    try:
        with open(CALLS_PATH) as f:
            log = json.load(f)
        return [c for c in log.get("calls", [])
                if c.get("date") == today and c.get("status") == "open"]
    except Exception:
        return []


def _get_open_positions_today_all() -> list:
    """Return ALL calls today (open + closed) — used to enforce 2-signal-per-day cap."""
    from datetime import date
    today = str(date.today())
    if not os.path.exists(CALLS_PATH):
        return []
    try:
        with open(CALLS_PATH) as f:
            log = json.load(f)
        return [c for c in log.get("calls", [])
                if c.get("date") == today and c.get("action") == "BUY"]
    except Exception:
        return []


def _remaining_capital() -> float:
    """Capital not yet deployed in today's open positions."""
    open_pos = _get_open_positions_today()
    deployed = sum(c.get("invest_inr", 0) or 0 for c in open_pos)
    log_equity = CAPITAL
    if os.path.exists(CALLS_PATH):
        try:
            with open(CALLS_PATH) as f:
                log = json.load(f)
            log_equity = log.get("equity", CAPITAL)
        except Exception:
            pass
    return max(0.0, log_equity - deployed)


# ── Midday entry (11:00 AM) ───────────────────────────────────────────────────

def generate_midday_recommendation() -> dict:
    """
    11:00 AM midday scan — same 4-tier logic, anchored to bar 20 (~10:55 AM price).
    Capital is whatever is NOT already deployed in the 9:45 AM call.
    Skips stocks already held in an open position.
    """
    now_ist = datetime.now(IST)

    avail = _remaining_capital()
    open_tickers = {c["ticker"] for c in _get_open_positions_today()}

    print(f"\n{'='*65}")
    print(f"  MIDDAY SIGNAL ENGINE — {now_ist.strftime('%d %b %Y  %I:%M %p IST')}")
    print(f"  Available capital: ₹{avail:,.0f}  |  Entry bar: ~10:55 AM (bar 20)")
    print(f"  Already open: {open_tickers or 'none'}")
    print(f"{'='*65}\n")

    if avail < 5000:
        return _no_trade("Less than ₹5,000 available — capital fully deployed at 9:45 AM.")

    def _filtered(tickers):
        return [t for t in tickers if t not in open_tickers]

    # TIER 1/2 — 2-year backtest gate
    print(f"[TIER 1/2] 2-year backtest (≥{MIN_WIN_RATE_THRESHOLD:.0%} WR)...")
    bt_df = load_or_run_backtest(CASH_EQUITIES, force_fresh=False)
    bt_lookup = {}
    if not bt_df.empty:
        for _, row in bt_df.iterrows():
            t = row["ticker"]
            if t not in bt_lookup or row.get("max_1day_return", 0) > bt_lookup[t].get("max_1day_return", 0):
                bt_lookup[t] = row.to_dict()

        top_tickers = _filtered(list(bt_df["ticker"].unique()[:15]))
        if top_tickers:
            sigs   = _scan_live(top_tickers, bt_lookup, entry_bar_idx=MIDDAY_ENTRY_BAR)
            scored = compute_composite_scores(sigs)

            tier1 = [s for s in scored if s.get("direction") == "LONG" and s.get("signals_aligned", 0) >= MIN_SIGNALS_REQUIRED]
            if tier1:
                print(f"  [TIER 1] {len(tier1)} stock(s) — midday continuation")
                _print_candidates(tier1[:2], "TIER 1 MIDDAY")
                return _build_result_midday(tier1[:1], now_ist, CONVICTION_HIGH, avail)

            tier2 = [s for s in scored if s.get("signals_aligned", 0) >= MIN_SIGNALS_WATCHLIST]
            if tier2:
                print(f"  [TIER 2] {len(tier2)} stock(s) — midday with reduced signals")
                return _build_result_midday(tier2[:1], now_ist, CONVICTION_MEDIUM, avail)

    # TIER 3 — 60-day ORB
    print(f"\n[TIER 3] 60-day ORB backtest — midday scan...")
    orb_lookup = _load_orb_backtest()
    if orb_lookup:
        top_orb = _filtered(sorted(orb_lookup, key=lambda t: orb_lookup[t].get("max_1day_return", 0), reverse=True)[:20])
        if top_orb:
            sigs   = _scan_live(top_orb, orb_lookup, entry_bar_idx=MIDDAY_ENTRY_BAR)
            scored = compute_composite_scores(sigs)
            best   = [s for s in scored if s.get("current_price", 0) > 0]
            if best:
                return _build_result_midday(best[:1], now_ist, CONVICTION_BEST, avail)

    # TIER 4 — pure live
    print(f"\n[TIER 4] EXPLORATORY midday scan...")
    sigs   = _scan_live(_filtered(WATCHLIST), {}, entry_bar_idx=MIDDAY_ENTRY_BAR)
    scored = compute_composite_scores(sigs)
    pool   = [s for s in scored if s.get("direction") == "LONG"] or scored
    if pool:
        return _build_result_midday(pool[:1], now_ist, CONVICTION_EXPLO, avail)

    return _no_trade("No midday setup found. Market may be choppy or capital fully deployed.")


def _build_result_continuous(top_sigs: list, now_ist: datetime, conviction: str, avail_capital: float) -> dict:
    """Continuous scan result — no fixed session label, uses available capital."""
    built = []
    for s in top_sigs:
        c = _build_call(s, now_ist, conviction)
        if c:
            rm = RiskManager(capital=avail_capital)
            sizing = rm.kelly_position(
                win_rate=max(s.get("bt_win_rate", 0.5), 0.5),
                entry=c["entry"], stop=c["stop_loss"]
            )
            c.update({
                "shares":         sizing["shares"],
                "position_value": sizing["position_value"],
                "risk_amount":    sizing["risk_amount"],
                "risk_pct":       sizing["risk_pct"],
                "kelly_pct":      sizing["kelly_pct"],
            })
            built.append(c)

    if not built and top_sigs:
        s = top_sigs[0]
        if s.get("current_price", 0) > 0:
            built.append(_force_call(s, now_ist, conviction))

    if not built:
        return _no_trade("Could not build valid levels.")

    allocation = _allocation_commentary(built, capital=avail_capital)
    return {
        "action":           "BUY",
        "calls":            built,
        "allocation":       allocation,
        "conviction":       conviction,
        "signal_session":   now_ist.strftime("%I:%M %p"),   # actual trigger time, not "MIDDAY"
        "timestamp":        now_ist.isoformat(),
        **built[0],
    }


def _build_result_midday(top_sigs: list, now_ist: datetime, conviction: str, avail_capital: float) -> dict:
    """Same as _build_result but uses available capital for sizing."""
    built = []
    for s in top_sigs:
        c = _build_call(s, now_ist, conviction)
        if c:
            # Re-size using available capital
            rm = RiskManager(capital=avail_capital)
            entry = c["entry"]
            stop  = c["stop_loss"]
            sizing = rm.kelly_position(
                win_rate=max(s.get("bt_win_rate", 0.5), 0.5),
                entry=entry, stop=stop
            )
            c.update({
                "shares":         sizing["shares"],
                "position_value": sizing["position_value"],
                "risk_amount":    sizing["risk_amount"],
                "risk_pct":       sizing["risk_pct"],
                "kelly_pct":      sizing["kelly_pct"],
            })
            built.append(c)

    if not built and top_sigs:
        s = top_sigs[0]
        if s.get("current_price", 0) > 0:
            built.append(_force_call(s, now_ist, conviction))

    if not built:
        return _no_trade("Could not build valid midday levels.")

    allocation = _allocation_commentary(built, capital=avail_capital)
    return {
        "action":     "BUY",
        "calls":      built,
        "allocation": allocation,
        "conviction": conviction,
        "signal_session": "MIDDAY",
        "timestamp":  now_ist.isoformat(),
        **built[0],
    }
