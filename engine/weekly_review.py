"""
Sunday Weekly Review — Signal Replay & Weight Updater

Runs every Sunday at 6:30 PM IST via GitHub Actions.
1. Replays last week's market data at 9:45 AM bar for all stocks
2. Checks if targets would have been hit (no lookahead)
3. Analyzes which signals drove wins vs losses
4. Nudges SCORE_WEIGHTS in config.py toward winners (70% momentum blend)
5. Saves data/weekly_review.json for dashboard

Usage:
    python -m engine.weekly_review
    python -m engine.weekly_review --dry-run   # compute but don't write config
"""
import os, json, re, time, math, warnings
warnings.filterwarnings("ignore")

import pandas as pd
from datetime import datetime, date, timedelta
import pytz

from engine.config import (
    CASH_EQUITIES, WATCHLIST, IST, SCORE_WEIGHTS,
    MIN_SIGNALS_REQUIRED, MIN_VOL_RATIO, MIN_ORB_RANGE_PCT,
    MIN_NIFTY_TREND_PCT, MIN_REWARD_RISK,
    NIFTY_TREND_TICKER, MORNING_ENTRY_BAR,
)
from engine.data_fetcher import fetch_historical, fetch_intraday
from engine.signals import compute_signals

SIGNAL_NAMES = ["above_pdc", "orb", "vwap", "rsi", "ema_trend", "volume_spike", "key_level"]
REVIEW_PATH  = "data/weekly_review.json"
CONFIG_PATH  = "engine/config.py"

# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_week_data(tickers: list) -> dict:
    """Fetch 5-day 5-min data for all tickers. Returns {ticker: df}."""
    result = {}
    for i, ticker in enumerate(tickers):
        try:
            df = fetch_intraday(ticker, interval="5m", period="5d")
            if not df.empty:
                result[ticker] = df
        except Exception:
            pass
        if i % 10 == 9:
            time.sleep(0.5)
    return result


def get_week_dates(df_map: dict) -> list:
    """Extract unique trading dates from any ticker's 5-min data."""
    for df in df_map.values():
        if not df.empty:
            dates = sorted({
                idx.astimezone(IST).date()
                for idx in df.index
            })
            return dates
    return []


def compute_nifty_pct_by_day(df_nifty: pd.DataFrame) -> dict:
    """
    Pre-compute Nifty % from open for each trading day.
    Returns {date_str: pct_float}.
    """
    cache = {}
    if df_nifty.empty:
        return cache
    df_ist = df_nifty.copy()
    df_ist.index = df_ist.index.tz_convert(IST)
    for d, grp in df_ist.groupby(df_ist.index.date):
        if len(grp) < 2:
            continue
        open_p = float(grp["Close"].iloc[0])
        close_p = float(grp["Close"].iloc[-1])
        cache[str(d)] = round((close_p - open_p) / open_p * 100, 3)
    return cache


# ── Per-day signal replay ─────────────────────────────────────────────────────

def replay_day(ticker: str, df_daily: pd.DataFrame, df_5min_full: pd.DataFrame,
               trade_date: date, bt_lookup: dict, nifty_pct_cache: dict) -> dict:
    """
    Replay a single ticker on a single day at 9:45 AM bar.
    Returns signal dict if a valid LONG would have been issued, else None.
    No lookahead — only bars 0..5 are visible at decision point.
    """
    # Slice 5-min to this day only
    df_ist = df_5min_full.copy()
    df_ist.index = df_ist.index.tz_convert(IST)
    df_day = df_ist[df_ist.index.date == trade_date]
    if len(df_day) < max(6, MORNING_ENTRY_BAR + 1):
        return None

    # Slice daily to strictly before trade_date (no lookahead)
    df_daily_hist = df_daily[df_daily.index.normalize() < pd.Timestamp(trade_date, tz=IST)]
    if len(df_daily_hist) < 5:
        return None

    # Get previous day levels
    pdh = float(df_daily_hist["High"].iloc[-1])
    pdl = float(df_daily_hist["Low"].iloc[-1])
    pdc = float(df_daily_hist["Close"].iloc[-1])

    # Compute signals at bar 5 (9:45 AM)
    try:
        sig = compute_signals(df_daily_hist, df_day, pdh, pdl, pdc, entry_bar_idx=MORNING_ENTRY_BAR)
    except Exception:
        return None

    if sig.get("direction") != "LONG":
        return None
    if sig.get("signals_aligned", 0) < MIN_SIGNALS_REQUIRED:
        return None

    # Volume gate
    vol = sig.get("vol_ratio") or 0
    if vol < MIN_VOL_RATIO:
        return None

    # ORB range gate
    orb_high = sig.get("orb_high") or 0
    orb_low  = sig.get("orb_low") or 0
    price    = sig.get("current_price") or 1
    if orb_high > 0 and orb_low > 0:
        orb_range_pct = (orb_high - orb_low) / price * 100
        if orb_range_pct < MIN_ORB_RANGE_PCT:
            return None

    # Nifty gate — use pre-computed value for that day
    nifty_pct = nifty_pct_cache.get(str(trade_date), 0.0)
    if nifty_pct < MIN_NIFTY_TREND_PCT:
        return None

    # Time-to-target gate (9:45 AM → 2:00 PM = 4.25 hours)
    hours_left = 4.25
    exp_return = sig.get("expected_return", 0) or 0
    required   = 0.5 * hours_left  # MIN_RETURN_PER_HOUR
    if exp_return < required:
        return None

    # Enrich with backtest data
    bt = bt_lookup.get(ticker, {})
    sig["ticker"]           = ticker
    sig["trade_date"]       = str(trade_date)
    sig["bt_win_rate"]      = float(bt.get("win_rate", 0) or 0)
    sig["bt_sharpe"]        = float(bt.get("sharpe_ratio", bt.get("sharpe", 0)) or 0)
    sig["bt_strategy"]      = bt.get("strategy", "ORB")
    sig["bt_max_1day"]      = float(bt.get("max_1day_return", 0) or 0)
    sig["nifty_pct"]        = nifty_pct
    sig["df_5min_day"]      = df_day  # carry forward for outcome simulation
    return sig


# ── Outcome simulation ────────────────────────────────────────────────────────

def simulate_outcome(sig: dict) -> dict:
    """
    Scan bars after entry bar to check target/stop/force-close.
    Returns {outcome, exit_price, exit_time, bars_held, pnl_pct}.
    """
    df_day    = sig.pop("df_5min_day")
    entry     = sig.get("current_price", 0)
    orb_low   = sig.get("orb_low", entry * 0.99)
    stop      = orb_low * 0.998
    risk      = entry - stop
    target    = entry + risk * MIN_REWARD_RISK if risk > 0 else entry * 1.02

    sig["entry"]    = round(entry, 2)
    sig["target"]   = round(target, 2)
    sig["stoploss"] = round(stop, 2)

    kill_time = datetime.now(IST).replace(hour=15, minute=20, second=0, microsecond=0)

    outcome    = "FORCE_CLOSE"
    exit_price = float(df_day["Close"].iloc[-1])
    exit_time  = str(df_day.index[-1].time())[:5]
    bars_held  = 0

    for i, (ts, row) in enumerate(df_day.iloc[MORNING_ENTRY_BAR + 1:].iterrows()):
        bar_time = ts.astimezone(IST)
        if bar_time.hour >= 15 and bar_time.minute >= 20:
            exit_price = float(row["Close"])
            exit_time  = f"{bar_time.hour}:{bar_time.minute:02d}"
            outcome    = "FORCE_CLOSE"
            bars_held  = i + 1
            break
        if row["High"] >= target:
            exit_price = target
            exit_time  = f"{bar_time.hour}:{bar_time.minute:02d}"
            outcome    = "WIN"
            bars_held  = i + 1
            break
        if row["Low"] <= stop:
            exit_price = stop
            exit_time  = f"{bar_time.hour}:{bar_time.minute:02d}"
            outcome    = "LOSS"
            bars_held  = i + 1
            break

    pnl_pct = round((exit_price - entry) / entry * 100, 2) if entry else 0
    sig["outcome"]     = outcome
    sig["exit_price"]  = round(exit_price, 2)
    sig["exit_time"]   = exit_time
    sig["bars_held"]   = bars_held
    sig["pnl_pct"]     = pnl_pct
    return sig


# ── Feature analysis ──────────────────────────────────────────────────────────

def analyze_signal_features(trades: list) -> dict:
    """Per-signal win% vs loss% — tells us which signals predict wins."""
    winners = [t for t in trades if t["outcome"] == "WIN"]
    losers  = [t for t in trades if t["outcome"] in ("LOSS", "FORCE_CLOSE")]

    stats = {}
    for name in SIGNAL_NAMES:
        win_active  = sum(1 for t in winners if (t.get("signals_detail") or {}).get(name) == 1)
        loss_active = sum(1 for t in losers  if (t.get("signals_detail") or {}).get(name) == 1)
        win_pct     = round(win_active  / len(winners), 3) if winners else 0.0
        loss_pct    = round(loss_active / len(losers),  3) if losers  else 0.0
        importance  = round(win_pct - loss_pct, 3)
        stats[name] = {
            "win_count":  win_active,
            "loss_count": loss_active,
            "win_pct":    win_pct,
            "loss_pct":   loss_pct,
            "importance": importance,
        }
    return stats


# ── Weight update ─────────────────────────────────────────────────────────────

def compute_new_weights(current_weights: dict, signal_stats: dict, trades: list) -> dict:
    """
    Nudge SCORE_WEIGHTS based on signal feature importance from last week.
    Uses 70% momentum blend — weights can't jump more than ~1.5% per week.
    Returns new weight dict summing to 1.0.
    """
    if len(trades) < 5:
        print(f"  [WEIGHTS] Only {len(trades)} trades — need ≥5 to update weights. Unchanged.")
        return current_weights

    # Average importance across all 7 signals
    importances     = [v["importance"] for v in signal_stats.values()]
    avg_importance  = sum(importances) / len(importances)

    # Adjust confidence weight by up to ±0.05 based on signal predictiveness
    importance_adj      = avg_importance * 0.05
    raw_new_confidence  = current_weights["confidence"] + importance_adj
    raw_new_confidence  = max(0.05, min(0.40, raw_new_confidence))

    # Blend: 70% old + 30% new
    new_confidence = 0.70 * current_weights["confidence"] + 0.30 * raw_new_confidence

    # Redistribute delta to other weights proportionally
    delta      = new_confidence - current_weights["confidence"]
    other_keys = [k for k in current_weights if k != "confidence"]
    other_sum  = sum(current_weights[k] for k in other_keys)

    new_weights = {}
    for k in other_keys:
        proportion  = current_weights[k] / other_sum
        new_weights[k] = current_weights[k] - delta * proportion
    new_weights["confidence"] = new_confidence

    # Normalize to exactly 1.0
    total = sum(new_weights.values())
    new_weights = {k: round(v / total, 6) for k, v in new_weights.items()}

    print(f"  [WEIGHTS] avg_importance={avg_importance:+.3f}  confidence: {current_weights['confidence']:.4f} → {new_weights['confidence']:.4f}")
    return new_weights


def update_config_weights(new_weights: dict, dry_run: bool = False) -> bool:
    """Safely rewrite SCORE_WEIGHTS block in engine/config.py."""
    today_str = str(date.today())
    lines = []
    for k, v in new_weights.items():
        lines.append(f'    "{k}": {v},')
    lines.append(f'    # Updated by weekly_review — {today_str}')
    replacement = "SCORE_WEIGHTS = {{\n{}\n}}".format("\n".join(lines))

    pattern = re.compile(r'SCORE_WEIGHTS\s*=\s*\{[^}]+\}', re.DOTALL)

    with open(CONFIG_PATH, "r") as f:
        content = f.read()

    new_content, count = pattern.subn(replacement.replace("{{", "{").replace("}}", "}"), content)
    if count == 0:
        print("  [WEIGHTS] ERROR: SCORE_WEIGHTS block not found in config.py")
        return False

    if dry_run:
        print("  [WEIGHTS] Dry run — would write:")
        print(replacement.replace("{{", "{").replace("}}", "}"))
        return True

    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        f.write(new_content)
    os.replace(tmp, CONFIG_PATH)
    print(f"  [WEIGHTS] config.py updated ✅")
    return True


# ── Report saving ─────────────────────────────────────────────────────────────

def _clean(obj):
    if isinstance(obj, dict):  return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):  return [_clean(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)): return None
    if isinstance(obj, pd.DataFrame): return None
    return obj


def save_weekly_review(report: dict):
    os.makedirs("data", exist_ok=True)
    with open(REVIEW_PATH, "w") as f:
        json.dump(_clean(report), f, indent=2, default=str)
    print(f"  [REVIEW] Saved → {REVIEW_PATH}")


# ── Main orchestrator ─────────────────────────────────────────────────────────

def run_weekly_review(dry_run: bool = False) -> dict:
    now_ist = datetime.now(IST)
    print(f"\n{'='*65}")
    print(f"  SUNDAY WEEKLY REVIEW — {now_ist.strftime('%d %b %Y  %I:%M %p IST')}")
    print(f"{'='*65}\n")

    # Deduplicated ticker universe
    all_tickers = list(dict.fromkeys(CASH_EQUITIES + WATCHLIST))

    # Load backtest cache
    from engine.backtest import load_or_run_backtest
    bt_df = load_or_run_backtest(CASH_EQUITIES, force_fresh=False)
    bt_lookup = {}
    if not bt_df.empty:
        for _, row in bt_df.iterrows():
            t = row["ticker"]
            if t not in bt_lookup or row.get("max_1day_return", 0) > bt_lookup[t].get("max_1day_return", 0):
                bt_lookup[t] = row.to_dict()

    # Fetch Nifty 5-min for last week
    print(f"  Fetching Nifty trend data...")
    try:
        df_nifty = fetch_intraday(NIFTY_TREND_TICKER, interval="5m", period="5d")
        nifty_pct_cache = compute_nifty_pct_by_day(df_nifty)
    except Exception as e:
        print(f"  [WARN] Nifty fetch failed: {e} — gate will pass for all days")
        nifty_pct_cache = {}

    print(f"  Nifty by day: {nifty_pct_cache}")

    # Fetch 5-min data for all tickers
    print(f"\n  Fetching 5-min data for {len(all_tickers)} tickers (last 5 days)...")
    df_5min_map = fetch_week_data(all_tickers)
    print(f"  Got data for {len(df_5min_map)} tickers")

    # Determine trading days
    week_dates = get_week_dates(df_5min_map)
    if not week_dates:
        print("  No trading data found — aborting.")
        return {}

    week_start = str(week_dates[0])
    week_end   = str(week_dates[-1])
    print(f"  Trading days: {[str(d) for d in week_dates]}")

    # Fetch daily historical data
    print(f"\n  Fetching daily history...")
    df_daily_map = {}
    for i, ticker in enumerate(df_5min_map.keys()):
        try:
            df_daily_map[ticker] = fetch_historical(ticker, years=0.5)
        except Exception:
            pass
        if i % 10 == 9:
            time.sleep(0.3)

    # Replay every ticker × every trading day
    print(f"\n  Replaying signals...")
    replayed_trades = []

    for ticker in df_5min_map:
        df_5min = df_5min_map[ticker]
        df_daily = df_daily_map.get(ticker)
        if df_daily is None or df_daily.empty:
            continue

        for trade_date in week_dates:
            sig = replay_day(ticker, df_daily, df_5min, trade_date, bt_lookup, nifty_pct_cache)
            if sig is None:
                continue
            sig = simulate_outcome(sig)
            icon = "✅" if sig["outcome"] == "WIN" else ("🛑" if sig["outcome"] == "LOSS" else "🔔")
            print(f"  {icon} {trade_date} {ticker:<18} {sig['signals_aligned']}/7  {sig['pnl_pct']:+.2f}%  {sig['outcome']}")
            replayed_trades.append(sig)

    # Summary
    wins        = sum(1 for t in replayed_trades if t["outcome"] == "WIN")
    losses      = sum(1 for t in replayed_trades if t["outcome"] == "LOSS")
    force_close = sum(1 for t in replayed_trades if t["outcome"] == "FORCE_CLOSE")
    total       = len(replayed_trades)
    win_rate    = round(wins / total, 3) if total else 0.0
    no_signals  = total == 0

    print(f"\n  {'─'*55}")
    print(f"  Signals: {total}  |  Wins: {wins}  |  Losses: {losses}  |  Force close: {force_close}")
    print(f"  Replay Win Rate: {win_rate:.1%}")

    # Feature analysis + weight update
    old_weights    = dict(SCORE_WEIGHTS)
    new_weights    = dict(SCORE_WEIGHTS)
    signal_stats   = {}
    weights_changed = False

    # Need ≥5 qualifying signals before weight learning is meaningful
    # (first run May 18 is observation only; May 25 onward will update weights)
    enough_data = total >= 5
    if not enough_data:
        print(f"\n  [WEIGHTS] Only {total} replayed signals — need ≥5 to update weights.")
        print(f"  [WEIGHTS] Observation-only run. Weights unchanged until more data accumulates.")

    if not no_signals:
        signal_stats = analyze_signal_features(replayed_trades)
        print(f"\n  Signal importance (observation):")
        for name, s in signal_stats.items():
            bar = "█" * int(abs(s["importance"]) * 10)
            print(f"    {name:<15} win={s['win_pct']:.0%}  loss={s['loss_pct']:.0%}  importance={s['importance']:+.2f}  {bar}")

        if enough_data:
            new_weights = compute_new_weights(old_weights, signal_stats, replayed_trades)
            if new_weights != old_weights:
                weights_changed = True
                update_config_weights(new_weights, dry_run=dry_run)
        else:
            new_weights = old_weights

    # Clean trades for JSON (remove any non-serializable fields)
    clean_trades = []
    for t in replayed_trades:
        clean_trades.append({
            "date":            t.get("trade_date"),
            "ticker":          t.get("ticker"),
            "entry":           t.get("entry"),
            "target":          t.get("target"),
            "stoploss":        t.get("stoploss"),
            "signals_aligned": t.get("signals_aligned"),
            "signals_detail":  t.get("signals_detail", {}),
            "vol_ratio":       t.get("vol_ratio"),
            "nifty_pct":       t.get("nifty_pct"),
            "outcome":         t.get("outcome"),
            "exit_price":      t.get("exit_price"),
            "exit_time":       t.get("exit_time"),
            "bars_held":       t.get("bars_held"),
            "pnl_pct":         t.get("pnl_pct"),
        })

    report = {
        "generated_at":      now_ist.isoformat(),
        "week_start":        week_start,
        "week_end":          week_end,
        "trading_days":      [str(d) for d in week_dates],
        "tickers_scanned":   len(df_5min_map),
        "signals_generated": total,
        "wins":              wins,
        "losses":            losses,
        "force_closes":      force_close,
        "win_rate":          win_rate,
        "no_signals_week":   no_signals,
        "per_signal_stats":  signal_stats,
        "old_weights":       old_weights,
        "new_weights":       new_weights,
        "weights_changed":   weights_changed,
        "replayed_trades":   clean_trades,
    }

    save_weekly_review(report)

    print(f"\n{'='*65}")
    print(f"  REVIEW COMPLETE")
    print(f"  Win rate: {win_rate:.1%} over {total} signals")
    print(f"  Weights {'updated ✅' if weights_changed else 'unchanged'}")
    print(f"{'='*65}\n")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Compute but don't write config.py")
    args = parser.parse_args()
    run_weekly_review(dry_run=args.dry_run)
