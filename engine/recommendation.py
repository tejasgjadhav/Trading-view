"""
AVCM Signal Engine — Recommendation Generator
Adaptive Volume-Confirmed Momentum · NSE Intraday · Long Only

Flow:
  Pre-market regime check → sector momentum ranking → watchlist build →
  every 5 min: 5-factor AVCM check → quality gates → VIX-adjusted sizing →
  residual ATR target → tranche exit plan → publish BUY or NO_TRADE

Composite score (0–100) when multiple stocks qualify:
  max_1day_return (25%) · win_rate (20%) · sharpe (15%) ·
  confidence (20%) · expected_return (10%) · vol_ratio (10%)
  × time multiplier (1.0 at 9:45 AM → 0.0 at 1:30 PM)
"""
import os, json, warnings, time
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
from datetime import datetime, date

from engine.config import (
    CASH_EQUITIES, WATCHLIST, MIN_WIN_RATE_THRESHOLD,
    MIN_SIGNALS_REQUIRED, MIN_SIGNALS_WATCHLIST,
    MIN_REWARD_RISK, MIN_RETURN_PCT, CAPITAL, KILL_SWITCH_TIME,
    ONLY_BUY, IST, CALLS_PATH, SCORE_WEIGHTS, ORB_BACKTEST_PATH,
    MORNING_ENTRY_BAR, SCORE_TIME_START, SCORE_TIME_END,
    MIN_VOL_RATIO, MIN_RETURN_PER_HOUR, MIN_ORB_RANGE_PCT,
    NIFTY_TREND_TICKER, MIN_NIFTY_TREND_PCT,
    INDIA_VIX_TICKER, VIX_NO_TRADE, VIX_HIGH, VIX_LOW,
    EQUITY_PCT_LOW_VIX, EQUITY_PCT_NORMAL_VIX, EQUITY_PCT_HIGH_VIX,
    RETEST_BONUS, CIRCUIT_BREAKER_CONSEC_LOSSES, MAX_EQUITY_DRAWDOWN_PCT,
    SECTOR_MOMENTUM_TOP_N, EXIT_TRANCHE_1_PCT, EXIT_TRANCHE_2_PCT,
    EXIT_TRANCHE_3_PCT, EXIT_TRANCHE_1_R_MULT,
    SIGNAL_CUTOFF, NIFTY_EMA_PERIOD, MIN_NIFTY_PREOPEN_PCT,
    SCAN_LOG_PATH,
)
from engine.data_fetcher import fetch_historical, fetch_intraday, get_previous_day_levels
from engine.signals import compute_signals
from engine.backtest import load_or_run_backtest


# ── Conviction label ─────────────────────────────────────────────────────────
CONVICTION_AVCM   = "AVCM_SIGNAL"
CONVICTION_MEDIUM = "MEDIUM"
CONVICTION_BEST   = "BEST MATCH"
CONVICTION_EXPLO  = "EXPLORATORY"

# ── Sector map ───────────────────────────────────────────────────────────────
SECTOR_MAP = {
    "HDFCBANK.NS":"BANK","ICICIBANK.NS":"BANK","SBIN.NS":"BANK","AXISBANK.NS":"BANK",
    "KOTAKBANK.NS":"BANK","INDUSINDBK.NS":"BANK","FEDERALBNK.NS":"BANK",
    "BANKBARODA.NS":"BANK","PNB.NS":"BANK","IDFCFIRSTB.NS":"BANK","BANDHANBNK.NS":"BANK",
    "BAJFINANCE.NS":"NBFC","BAJAJFINSV.NS":"NBFC","HDFCLIFE.NS":"INSURANCE",
    "SBILIFE.NS":"INSURANCE","CHOLAFIN.NS":"NBFC","MUTHOOTFIN.NS":"NBFC",
    "SHRIRAMFIN.NS":"NBFC","RECLTD.NS":"NBFC","PFC.NS":"NBFC","IRFC.NS":"NBFC",
    "TCS.NS":"IT","INFY.NS":"IT","WIPRO.NS":"IT","HCLTECH.NS":"IT","TECHM.NS":"IT",
    "MPHASIS.NS":"IT","COFORGE.NS":"IT","PERSISTENT.NS":"IT","OFSS.NS":"IT","LTIM.NS":"IT",
    "RELIANCE.NS":"ENERGY","ONGC.NS":"ENERGY","BPCL.NS":"ENERGY","IOC.NS":"ENERGY",
    "COALINDIA.NS":"ENERGY","POWERGRID.NS":"ENERGY","NTPC.NS":"ENERGY",
    "TATAPOWER.NS":"ENERGY","ADANIGREEN.NS":"ENERGY",
    "LT.NS":"INFRA","ADANIENT.NS":"INFRA","ADANIPORTS.NS":"INFRA",
    "SIEMENS.NS":"INFRA","ABB.NS":"INFRA","BHEL.NS":"INFRA",
    "HAVELLS.NS":"INFRA","POLYCAB.NS":"INFRA","VOLTAS.NS":"INFRA",
    "JSWSTEEL.NS":"METALS","TATASTEEL.NS":"METALS","HINDALCO.NS":"METALS",
    "VEDL.NS":"METALS","SAIL.NS":"METALS","NMDC.NS":"METALS",
    "ULTRACEMCO.NS":"CEMENT","GRASIM.NS":"CEMENT","AMBUJACEM.NS":"CEMENT","ACC.NS":"CEMENT",
    "MARUTI.NS":"AUTO","BAJAJ-AUTO.NS":"AUTO","HEROMOTOCO.NS":"AUTO",
    "EICHERMOT.NS":"AUTO","M&M.NS":"AUTO","TATAMOTORS.NS":"AUTO",
    "ASHOKLEY.NS":"AUTO","BALKRISIND.NS":"AUTO",
    "HINDUNILVR.NS":"FMCG","ITC.NS":"FMCG","NESTLEIND.NS":"FMCG","BRITANNIA.NS":"FMCG",
    "TATACONSUM.NS":"FMCG","GODREJCP.NS":"FMCG","MARICO.NS":"FMCG",
    "DABUR.NS":"FMCG","PIDILITIND.NS":"FMCG","ASIANPAINT.NS":"FMCG",
    "SUNPHARMA.NS":"PHARMA","DRREDDY.NS":"PHARMA","CIPLA.NS":"PHARMA",
    "DIVISLAB.NS":"PHARMA","APOLLOHOSP.NS":"PHARMA","LUPIN.NS":"PHARMA",
    "TORNTPHARM.NS":"PHARMA","AUROPHARMA.NS":"PHARMA","ZYDUSLIFE.NS":"PHARMA",
    "TITAN.NS":"RETAIL","DMART.NS":"RETAIL","TRENT.NS":"RETAIL","JUBLFOOD.NS":"RETAIL",
    "BHARTIARTL.NS":"TELECOM","NAUKRI.NS":"TECH","INDIGO.NS":"AVIATION",
    "DLF.NS":"REALTY","GODREJPROP.NS":"REALTY","ZOMATO.NS":"TECH",
}

# ── Daily caches ─────────────────────────────────────────────────────────────
_nifty_cache      = {}   # {date: pct_from_open}
_vix_cache        = {}   # {date: vix_level}
_regime_cache     = {}   # {date: (ok, reason)}
_sector_rank_cache= {}   # {date: {sector: rank}}


def _no_trade(reason: str) -> dict:
    return {
        "action":    "NO_TRADE",
        "reason":    reason,
        "timestamp": datetime.now(IST).isoformat(),
        "calls":     [],
        "allocation": None,
    }


# ── Market data helpers ──────────────────────────────────────────────────────

def _get_nifty_pct() -> float:
    """Nifty % change from its own open today. Cached per day."""
    today = str(date.today())
    if today in _nifty_cache:
        return _nifty_cache[today]
    try:
        df = fetch_intraday(NIFTY_TREND_TICKER, interval="5m", period="1d")
        if df.empty:
            _nifty_cache[today] = 0.0
            return 0.0
        pct = round((float(df["Close"].iloc[-1]) - float(df["Close"].iloc[0])) / float(df["Close"].iloc[0]) * 100, 3)
        _nifty_cache[today] = pct
        return pct
    except Exception:
        _nifty_cache[today] = 0.0
        return 0.0


def _get_vix() -> float:
    """India VIX current level. Cached per day."""
    today = str(date.today())
    if today in _vix_cache:
        return _vix_cache[today]
    try:
        df = fetch_intraday(INDIA_VIX_TICKER, interval="5m", period="1d")
        if df.empty:
            _vix_cache[today] = 15.0   # assume normal
            return 15.0
        vix = round(float(df["Close"].iloc[-1]), 2)
        _vix_cache[today] = vix
        return vix
    except Exception:
        _vix_cache[today] = 15.0
        return 15.0


def _check_market_regime() -> tuple:
    """
    Pre-market regime check — ALL 3 must pass or trade nothing today.
    1. Nifty above its 20-day EMA
    2. India VIX below 22
    3. Nifty not a gap-down day (pre-open > -0.5%)

    Returns (go: bool, reason: str, vix: float)
    """
    today = str(date.today())
    if today in _regime_cache:
        return _regime_cache[today]

    vix = _get_vix()
    if vix >= VIX_NO_TRADE:
        result = (False, f"India VIX {vix:.1f} ≥ {VIX_NO_TRADE} — no trade today", vix)
        _regime_cache[today] = result
        return result

    try:
        df_nifty = fetch_historical(NIFTY_TREND_TICKER, years=0.25)
        if not df_nifty.empty and len(df_nifty) >= NIFTY_EMA_PERIOD:
            ema_20 = float(df_nifty["Close"].ewm(span=NIFTY_EMA_PERIOD, adjust=False).mean().iloc[-1])
            curr   = float(df_nifty["Close"].iloc[-1])
            if curr < ema_20:
                result = (False, f"Nifty ({curr:.0f}) below 20d EMA ({ema_20:.0f}) — bearish regime", vix)
                _regime_cache[today] = result
                return result
    except Exception:
        pass

    nifty_pct = _get_nifty_pct()
    if nifty_pct <= MIN_NIFTY_PREOPEN_PCT:
        result = (False, f"Nifty gap-down ({nifty_pct:+.2f}% from open, threshold {MIN_NIFTY_PREOPEN_PCT}%)", vix)
        _regime_cache[today] = result
        return result

    result = (True, "Market regime OK", vix)
    _regime_cache[today] = result
    return result


def _get_sector_rankings() -> dict:
    """
    Returns sector → 5-day rank (1=best). Uses 2 proxy stocks per sector.
    Cached per day. Top SECTOR_MOMENTUM_TOP_N are eligible.
    """
    today = str(date.today())
    if today in _sector_rank_cache:
        return _sector_rank_cache[today]

    # Representative stocks per sector (1-2 large caps per sector)
    proxies = {
        "BANK":      ["HDFCBANK.NS", "ICICIBANK.NS"],
        "IT":        ["TCS.NS", "INFY.NS"],
        "FMCG":      ["HINDUNILVR.NS", "ITC.NS"],
        "PHARMA":    ["SUNPHARMA.NS", "DRREDDY.NS"],
        "AUTO":      ["MARUTI.NS", "M&M.NS"],
        "METALS":    ["JSWSTEEL.NS", "HINDALCO.NS"],
        "ENERGY":    ["RELIANCE.NS", "NTPC.NS"],
        "INFRA":     ["LT.NS", "ADANIENT.NS"],
        "NBFC":      ["BAJFINANCE.NS", "MUTHOOTFIN.NS"],
        "CEMENT":    ["ULTRACEMCO.NS", "AMBUJACEM.NS"],
        "RETAIL":    ["TITAN.NS", "DMART.NS"],
        "TELECOM":   ["BHARTIARTL.NS"],
        "REALTY":    ["DLF.NS", "GODREJPROP.NS"],
        "TECH":      ["NAUKRI.NS", "ZOMATO.NS"],
    }

    sector_returns = {}
    for sector, tickers in proxies.items():
        returns = []
        for t in tickers:
            try:
                df = fetch_historical(t, years=0.1)
                if len(df) >= 6:
                    ret = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[-6]) - 1) * 100
                    returns.append(ret)
            except Exception:
                pass
        if returns:
            sector_returns[sector] = round(sum(returns) / len(returns), 3)

    # Rank: 1 = best 5d return
    ranked = sorted(sector_returns, key=sector_returns.get, reverse=True)
    ranks  = {s: i + 1 for i, s in enumerate(ranked)}
    _sector_rank_cache[today] = ranks
    print(f"  [SECTOR RANK] {' | '.join(f'{s}:{r}' for s,r in sorted(ranks.items(), key=lambda x: x[1]))}")
    return ranks


def _is_sector_eligible(ticker: str, sector_ranks: dict) -> tuple:
    """Returns (eligible: bool, reason: str)."""
    sector = SECTOR_MAP.get(ticker, "UNKNOWN")
    if sector == "UNKNOWN":
        return True, ""   # unmapped stock — don't block
    rank = sector_ranks.get(sector)
    if rank is None:
        return True, ""
    n_sectors = len(sector_ranks)
    block_threshold = n_sectors - SECTOR_MOMENTUM_TOP_N + 1  # bottom 4
    if rank > n_sectors - SECTOR_MOMENTUM_TOP_N:
        return False, f"Sector {sector} ranked {rank}/{n_sectors} (bottom {SECTOR_MOMENTUM_TOP_N})"
    return True, ""


# ── ATR helpers ──────────────────────────────────────────────────────────────

def _compute_atr(df_daily: pd.DataFrame, period: int = 14) -> float:
    if df_daily.empty or len(df_daily) < period + 1:
        return 0.0
    hi = df_daily["High"].values
    lo = df_daily["Low"].values
    cl = df_daily["Close"].values
    trs = [max(hi[i] - lo[i], abs(hi[i] - cl[i-1]), abs(lo[i] - cl[i-1])) for i in range(1, len(cl))]
    return float(sum(trs[-period:]) / period)


def _residual_atr_target(entry: float, stop: float, atr_14: float, df_5min: pd.DataFrame) -> float:
    """
    AVCM target = Entry + max(Residual ATR, 0.8% of entry)
    where Residual ATR = max(0, ATR_14 − range already consumed today).
    Floor: Entry + 2.5× stop distance.

    This ensures target reflects how much move actually REMAINS in the day,
    not the full ATR as if we're starting from zero.
    """
    day_high = float(df_5min["High"].max()) if not df_5min.empty else entry
    day_low  = float(df_5min["Low"].min())  if not df_5min.empty else entry
    range_consumed = max(0.0, day_high - day_low)
    residual_atr   = max(0.0, atr_14 - range_consumed)

    raw_target  = entry + max(residual_atr, entry * 0.008)
    stop_dist   = entry - stop
    rr_floor    = entry + MIN_REWARD_RISK * stop_dist if stop_dist > 0 else entry * 1.015
    return round(max(raw_target, rr_floor), 2)


# ── VIX-adjusted position sizing ─────────────────────────────────────────────

def _vix_size(vix: float, equity: float, entry: float, is_retest: bool = False) -> dict:
    """
    AVCM half-Kelly position sizing adjusted by VIX level.
    VIX < 13     → 8% of equity
    VIX 13–18    → 6% of equity
    VIX 18–22    → 3% of equity
    VIX ≥ 22     → no trade (caller should have already returned NO_TRADE)
    Retest bonus → +25% on top of the above
    """
    if vix >= VIX_NO_TRADE:
        pct = 0.0
    elif vix >= VIX_HIGH:
        pct = EQUITY_PCT_HIGH_VIX   # 3%
    elif vix >= VIX_LOW:
        pct = EQUITY_PCT_NORMAL_VIX # 6%
    else:
        pct = EQUITY_PCT_LOW_VIX    # 8%

    if is_retest:
        pct *= RETEST_BONUS  # +25%

    invest = equity * pct
    shares = max(1, int(invest / entry)) if entry > 0 else 1
    return {
        "invest_inr":    round(invest, 0),
        "invest_pct":    round(pct * 100, 1),
        "shares":        shares,
        "position_value": round(shares * entry, 2),
        "vix_level":     vix,
        "is_retest":     is_retest,
    }


# ── Quality gates ─────────────────────────────────────────────────────────────

def _passes_quality_gates(sig: dict, now_ist: datetime = None) -> tuple:
    """
    Hard entry gates — all must pass:
    1. Volume ≥ 1× daily avg (base liquidity)
    2. ORB range ≥ 0.8% of price
    3. Expected return achievable in time remaining (≥ 0.5%/hr)
    (Nifty positive and sector eligibility checked separately)
    """
    if now_ist is None:
        now_ist = datetime.now(IST)

    vol = sig.get("vol_ratio") or 0
    if vol < MIN_VOL_RATIO:
        return False, f"Low volume ({vol:.2f}× avg < {MIN_VOL_RATIO}×)"

    orb_high = sig.get("orb_high") or 0
    orb_low  = sig.get("orb_low")  or 0
    price    = sig.get("current_price") or 1
    if orb_high > 0 and orb_low > 0:
        orb_range_pct = (orb_high - orb_low) / price * 100
        if orb_range_pct < MIN_ORB_RANGE_PCT:
            return False, f"ORB too tight ({orb_range_pct:.2f}% < {MIN_ORB_RANGE_PCT}%)"

    cutoff_h, cutoff_m = map(int, SIGNAL_CUTOFF.split(":"))
    now_min    = now_ist.hour * 60 + now_ist.minute
    cutoff_min = cutoff_h * 60 + cutoff_m
    hours_left = max((cutoff_min - now_min) / 60, 0.25)
    exp_return = sig.get("expected_return", 0) or 0
    required   = MIN_RETURN_PER_HOUR * hours_left
    if exp_return < required:
        return False, f"Target {exp_return:.1f}% too low for {hours_left:.1f}h left (need {required:.1f}%)"

    return True, ""


# ── Time multiplier ───────────────────────────────────────────────────────────

def _time_remaining_multiplier(now_ist: datetime = None) -> float:
    if now_ist is None:
        now_ist = datetime.now(IST)
    def to_min(t):
        h, m = map(int, t.split(":"))
        return h * 60 + m
    now_min   = now_ist.hour * 60 + now_ist.minute
    start_min = to_min(SCORE_TIME_START)   # 9:45 AM
    end_min   = to_min(SCORE_TIME_END)     # 1:30 PM
    if now_min <= start_min: return 1.0
    if now_min >= end_min:   return 0.0
    return round((end_min - now_min) / (end_min - start_min), 3)


# ── Composite scorer ─────────────────────────────────────────────────────────

def _normalize(values: list, cap: float = None) -> list:
    arr = [min(float(v), cap) if cap else float(v) for v in values]
    lo, hi = min(arr), max(arr)
    if hi == lo:
        return [1.0] * len(arr)
    return [(v - lo) / (hi - lo) for v in arr]


def compute_composite_scores(candidates: list, now_ist: datetime = None) -> list:
    if not candidates:
        return candidates
    time_mult = _time_remaining_multiplier(now_ist)

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
        raw  = sum(SCORE_WEIGHTS[k] * factors[k][i] for k in SCORE_WEIGHTS) * 100
        c["composite_score"] = round(raw * time_mult, 1)
        c["time_mult"]       = time_mult
        c["score_breakdown"] = {k: round(SCORE_WEIGHTS[k] * factors[k][i] * 100, 1) for k in SCORE_WEIGHTS}
    return sorted(candidates, key=lambda x: x["composite_score"], reverse=True)


# ── Live signal scanner ───────────────────────────────────────────────────────

def _scan_live(tickers: list, bt_lookup: dict = None, entry_bar_idx: int = MORNING_ENTRY_BAR,
               nifty_pct: float = None) -> list:
    results = []
    for ticker in tickers:
        try:
            df_daily = fetch_historical(ticker, years=0.5)
            df_5min  = fetch_intraday(ticker, interval="5m", period="1d")
            if df_5min.empty or len(df_5min) < max(6, entry_bar_idx + 1 if entry_bar_idx >= 0 else 6):
                continue
            levels = get_previous_day_levels(ticker, df_daily)
            sig    = compute_signals(df_daily, df_5min,
                                     levels["pdh"], levels["pdl"], levels["pdc"],
                                     entry_bar_idx=entry_bar_idx,
                                     nifty_pct=nifty_pct)
            sig["ticker"]   = ticker
            sig["atr_14"]   = _compute_atr(df_daily, period=14)
            sig["df_daily"] = df_daily
            sig["df_5min"]  = df_5min

            bt = (bt_lookup or {}).get(ticker, {})
            sig["bt_win_rate"]        = float(bt.get("win_rate", 0) or 0)
            sig["bt_sharpe"]          = float(bt.get("sharpe_ratio", bt.get("sharpe", 0)) or 0)
            sig["bt_strategy"]        = bt.get("strategy", "ORB")
            sig["bt_max_1day_return"] = float(bt.get("max_1day_return", 0) or 0)

            # Pre-compute expected_return with residual ATR target
            entry   = sig.get("limit_entry", sig.get("current_price", 0))
            atr     = sig.get("atr_14", 0)
            orb_low = sig.get("orb_low", entry * 0.99)
            stop    = round(orb_low * 0.998, 2)
            target  = _residual_atr_target(entry, stop, atr, df_5min)
            sig["expected_return"] = round((target / entry - 1) * 100, 2) if entry else 0
            results.append(sig)
        except Exception:
            pass
    return results


# ── Build single call ─────────────────────────────────────────────────────────

def _build_call(sig: dict, now_ist: datetime, conviction: str, vix: float, equity: float) -> dict:
    ticker  = sig["ticker"]
    # AVCM entry: limit at ORB High + 0.1%
    entry   = sig.get("limit_entry", sig.get("current_price", 0))
    orb_low = sig.get("orb_low", entry * 0.99)
    vwap    = sig.get("vwap", entry)
    atr     = sig.get("atr_14", 0)
    df_5min = sig.get("df_5min", pd.DataFrame())
    is_ret  = sig.get("is_retest", False)

    if not entry or entry <= 0:
        return None

    # AVCM stop: ORB Low − 0.2% buffer
    stop = round(orb_low * 0.998, 2)
    risk = entry - stop
    if risk <= 0:
        return None

    # Residual ATR target
    target = _residual_atr_target(entry, stop, atr, df_5min)
    exp    = round((target / entry - 1) * 100, 2)
    rr     = round((target - entry) / risk, 2)

    if exp < MIN_RETURN_PCT or rr < MIN_REWARD_RISK:
        return None

    # VIX-adjusted sizing
    sizing = _vix_size(vix, equity, entry, is_retest=is_ret)

    # Tranche exit levels
    tranche1_target = round(entry + EXIT_TRANCHE_1_R_MULT * risk, 2)  # 1× risk profit
    tranche2_target = target                                            # full target
    tranche3_time   = KILL_SWITCH_TIME                                  # 3:10 PM

    return {
        "action":           "BUY",
        "ticker":           ticker,
        "entry":            round(entry, 2),
        "target":           round(target, 2),
        "stop_loss":        stop,
        "expected_return":  exp,
        "reward_risk":      rr,
        "shares":           sizing["shares"],
        "position_value":   sizing["position_value"],
        "invest_inr":       sizing["invest_inr"],
        "invest_pct":       sizing["invest_pct"],
        "vix_level":        vix,
        "is_retest":        is_ret,
        "tranche_1":        {"sell_pct": EXIT_TRANCHE_1_PCT, "at_price": tranche1_target,
                             "action": "Sell 35% — move stop to breakeven"},
        "tranche_2":        {"sell_pct": EXIT_TRANCHE_2_PCT, "at_price": tranche2_target,
                             "action": f"Sell 35% at target or 1:30 PM"},
        "tranche_3":        {"sell_pct": EXIT_TRANCHE_3_PCT, "at_time": tranche3_time,
                             "action": f"Force close 30% at {KILL_SWITCH_TIME} IST"},
        "signals_aligned":  sig.get("signals_aligned", 0),
        "signals_detail":   sig.get("signals_detail", {}),
        "confidence":       sig.get("confidence", 0),
        "regime":           sig.get("regime", "UNKNOWN"),
        "vwap":             vwap,
        "orb_high":         sig.get("orb_high", entry),
        "orb_low":          orb_low,
        "rsi":              sig.get("rsi", 50),
        "vol_ratio":        sig.get("vol_ratio", 0),
        "vol_ratio_orb":    sig.get("vol_ratio_orb", 0),
        "bt_win_rate":      round(sig.get("bt_win_rate", 0), 4),
        "bt_sharpe":        round(sig.get("bt_sharpe", 0), 3),
        "bt_strategy":      sig.get("bt_strategy", "ORB"),
        "bt_max_1day":      round(sig.get("bt_max_1day_return", 0), 2),
        "composite_score":  sig.get("composite_score", 0),
        "score_breakdown":  sig.get("score_breakdown", {}),
        "conviction":       conviction,
        "exit_rule":        (f"Exit 1: Sell 35% at ₹{tranche1_target:,.2f} (1× risk) → stop to breakeven. "
                             f"Exit 2: Sell 35% at ₹{target:,.2f} target or 1:30 PM. "
                             f"Exit 3: Force close 30% at {KILL_SWITCH_TIME} IST."),
        "timestamp":        now_ist.isoformat(),
    }


# ── Circuit breaker check ─────────────────────────────────────────────────────

def _check_circuit_breakers() -> tuple:
    """
    Returns (can_trade: bool, reason: str).
    Checks: 3 consecutive stop-outs, daily loss > 2%, equity drawdown > 8%.
    """
    if not os.path.exists(CALLS_PATH):
        return True, "OK"
    try:
        with open(CALLS_PATH) as f:
            log = json.load(f)
        calls = log.get("calls", [])
        today = str(date.today())
        equity = log.get("equity", CAPITAL)
        peak   = log.get("equity_peak", equity)

        # Daily loss
        today_calls = [c for c in calls if c.get("date") == today and c.get("pnl_inr") is not None]
        daily_pnl   = sum(c.get("pnl_inr", 0) or 0 for c in today_calls)
        if daily_pnl < -CAPITAL * 0.02:
            return False, f"Daily loss limit hit (₹{daily_pnl:,.0f}). No more trades today."

        # Consecutive stop-outs (last N closed trades)
        closed = [c for c in reversed(calls) if c.get("status") in ("loss", "stopped_out") and c.get("pnl_inr") is not None]
        if len(closed) >= CIRCUIT_BREAKER_CONSEC_LOSSES:
            last_n = closed[:CIRCUIT_BREAKER_CONSEC_LOSSES]
            if all(c.get("pnl_inr", 0) < 0 for c in last_n):
                return False, f"{CIRCUIT_BREAKER_CONSEC_LOSSES} consecutive losses — stop trading today. Market choppy."

        # Equity drawdown
        if peak > 0 and (peak - equity) / peak > MAX_EQUITY_DRAWDOWN_PCT:
            return False, f"Equity drawdown {(peak-equity)/peak:.1%} exceeds {MAX_EQUITY_DRAWDOWN_PCT:.0%}. Halve sizes."

        return True, "OK"
    except Exception:
        return True, "OK"


# ── Already stopped out today? ────────────────────────────────────────────────

def _stopped_out_today(ticker: str) -> bool:
    """Returns True if this ticker already hit stop or closed at a loss today."""
    if not os.path.exists(CALLS_PATH):
        return False
    try:
        with open(CALLS_PATH) as f:
            log = json.load(f)
        today = str(date.today())
        for c in log.get("calls", []):
            if c.get("date") == today and c.get("ticker") == ticker:
                if c.get("status") in ("loss", "stopped_out") or (
                    c.get("pnl_inr") is not None and c.get("pnl_inr", 0) < 0
                ):
                    return True
        return False
    except Exception:
        return False


# ── Allocation commentary ─────────────────────────────────────────────────────

def _allocation_commentary(calls: list, equity: float = CAPITAL, vix: float = 15.0) -> dict:
    if not calls:
        return {}
    sizing_note = (
        f"VIX {vix:.1f} → "
        + ("8% per trade (low vol)" if vix < VIX_LOW else
           "3% per trade (elevated risk)" if vix >= VIX_HIGH else
           "6% per trade (normal)")
    )
    if len(calls) == 1:
        c = calls[0]
        return {
            "primary":     {"ticker": c["ticker"], "invest_inr": c["invest_inr"],
                            "invest_pct": c["invest_pct"], "shares": c["shares"]},
            "secondary":   None,
            "cash_reserve": round(equity - c["invest_inr"]),
            "commentary":  (f"Single signal. {sizing_note}. "
                            f"Buy {c['shares']} shares of {c['ticker']} @ ₹{c['entry']:,.2f}. "
                            f"Tranche 1 exit at ₹{c['tranche_1']['at_price']:,.2f}."),
        }
    c1, c2 = calls[0], calls[1]
    return {
        "primary":     {"ticker": c1["ticker"], "invest_inr": c1["invest_inr"],
                        "invest_pct": c1["invest_pct"], "shares": c1["shares"]},
        "secondary":   {"ticker": c2["ticker"], "invest_inr": c2["invest_inr"],
                        "invest_pct": c2["invest_pct"], "shares": c2["shares"]},
        "cash_reserve": round(equity - c1["invest_inr"] - c2["invest_inr"]),
        "commentary":  (f"Two signals. {sizing_note}. "
                        f"PRIMARY {c1['ticker']}: {c1['shares']} sh @ ₹{c1['entry']:,.2f} "
                        f"({c1['invest_pct']}%). "
                        f"SECONDARY {c2['ticker']}: {c2['shares']} sh @ ₹{c2['entry']:,.2f} "
                        f"({c2['invest_pct']}%)."),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _get_issued_tickers_today() -> set:
    today = str(date.today())
    if not os.path.exists(CALLS_PATH):
        return set()
    try:
        with open(CALLS_PATH) as f:
            log = json.load(f)
        return {c["ticker"] for c in log.get("calls", [])
                if c.get("date") == today and c.get("action") == "BUY"}
    except Exception:
        return set()


def _remaining_capital() -> float:
    if not os.path.exists(CALLS_PATH):
        return float(CAPITAL)
    try:
        with open(CALLS_PATH) as f:
            log = json.load(f)
        equity   = log.get("equity", CAPITAL)
        today    = str(date.today())
        deployed = sum(c.get("invest_inr", 0) or 0 for c in log.get("calls", [])
                       if c.get("date") == today and c.get("status") == "open")
        return max(0.0, equity - deployed)
    except Exception:
        return float(CAPITAL)


# ── Main continuous scan (called every 5 min) ─────────────────────────────────

def generate_continuous_recommendation() -> dict:
    """
    AVCM main loop — called every 5 min 9:15 AM – 3:15 PM IST.

    1. Check signal cutoff (1:30 PM)
    2. Check market regime (Nifty EMA, VIX, gap-down)
    3. Check circuit breakers (consecutive losses, daily loss)
    4. Get sector rankings → eligible sectors
    5. Scan watchlist: all 5 AVCM factors must fire
    6. Apply quality gates (volume, ORB range, time-to-target)
    7. Score and rank → pick best 2 from different sectors
    8. VIX-adjusted sizing → residual ATR target → tranche exits
    """
    now_ist = datetime.now(IST)
    hour, minute = now_ist.hour, now_ist.minute

    if hour < 9 or (hour == 9 and minute < 45):
        return _no_trade(f"ORB not yet formed — signals start 9:45 AM IST (now {hour:02d}:{minute:02d}).")

    cutoff_h, cutoff_m = map(int, SIGNAL_CUTOFF.split(":"))
    if hour > cutoff_h or (hour == cutoff_h and minute >= cutoff_m):
        return _no_trade(f"Past {SIGNAL_CUTOFF} IST signal cutoff. No new entries — force close at {KILL_SWITCH_TIME}.")

    # Regime check
    regime_ok, regime_reason, vix = _check_market_regime()
    if not regime_ok:
        return _no_trade(f"Regime: {regime_reason}")

    # Circuit breakers
    cb_ok, cb_reason = _check_circuit_breakers()
    if not cb_ok:
        return _no_trade(f"Circuit breaker: {cb_reason}")

    avail  = _remaining_capital()
    if avail < 5000:
        return _no_trade("Less than ₹5,000 available — capital fully deployed.")

    issued_today  = _get_issued_tickers_today()
    nifty_pct     = _get_nifty_pct()
    time_mult     = _time_remaining_multiplier(now_ist)

    print(f"\n{'='*65}")
    print(f"  AVCM SCAN — {now_ist.strftime('%d %b %Y  %I:%M %p IST')}")
    print(f"  VIX: {vix:.1f}  |  Nifty: {nifty_pct:+.2f}%  |  Time mult: {time_mult:.2f}x")
    print(f"  Issued today: {issued_today or 'none'}  |  Available: ₹{avail:,.0f}")
    print(f"{'='*65}\n")

    # Sector rankings (cached per day — one fetch)
    try:
        sector_ranks = _get_sector_rankings()
    except Exception:
        sector_ranks = {}

    all_candidates = []

    def _scan_and_score(tickers, bt_lookup):
        eligible = [t for t in tickers
                    if t not in issued_today and not _stopped_out_today(t)]
        sigs    = _scan_live(eligible, bt_lookup, entry_bar_idx=-1, nifty_pct=nifty_pct)
        # AVCM: ALL 5 must fire
        signals_ok = [s for s in sigs if s.get("direction") == "LONG"
                      and s.get("signals_aligned", 0) >= MIN_SIGNALS_REQUIRED]
        # Sector eligibility
        sector_ok = []
        for s in signals_ok:
            ok, reason = _is_sector_eligible(s["ticker"], sector_ranks)
            if not ok:
                print(f"  [SKIP] {s['ticker']}: {reason}")
                continue
            sector_ok.append(s)
        # Quality gates
        final = []
        for s in sector_ok:
            ok, reason = _passes_quality_gates(s, now_ist)
            if not ok:
                print(f"  [SKIP] {s['ticker']}: {reason}")
                continue
            final.append(s)
        return compute_composite_scores(final, now_ist)

    # TIER 1/2: 2-year backtest pool
    bt_df = load_or_run_backtest(CASH_EQUITIES, force_fresh=False)
    bt_lookup = {}
    if not bt_df.empty:
        for _, row in bt_df.iterrows():
            t = row["ticker"]
            if t not in bt_lookup or row.get("max_1day_return", 0) > bt_lookup[t].get("max_1day_return", 0):
                bt_lookup[t] = row.to_dict()
        scored = _scan_and_score(list(bt_df["ticker"].unique()[:15]), bt_lookup)
        all_candidates.extend([(s, CONVICTION_AVCM) for s in scored])

    # TIER 3: ORB universe (stocks not already in candidates)
    orb_lookup = _load_orb_backtest()
    if orb_lookup:
        already = {s["ticker"] for s, _ in all_candidates}
        top_orb = sorted(orb_lookup, key=lambda t: orb_lookup[t].get("max_1day_return", 0), reverse=True)[:20]
        top_orb = [t for t in top_orb if t not in already]
        if top_orb:
            scored = _scan_and_score(top_orb, orb_lookup)
            all_candidates.extend([(s, CONVICTION_BEST) for s in scored])

    if not all_candidates:
        return _no_trade(f"No AVCM setup (all 5 factors) at {now_ist.strftime('%I:%M %p IST')}. Will retry.")

    # Rank by composite score; pick best 2 from DIFFERENT sectors
    all_candidates.sort(key=lambda x: x[0].get("composite_score", 0), reverse=True)
    best = []
    used_sectors = set()
    for sig, conv in all_candidates:
        ticker = sig["ticker"]
        sector = SECTOR_MAP.get(ticker, ticker)
        if sector in used_sectors:
            print(f"  [SKIP] {ticker} — sector '{sector}' already represented")
            continue
        best.append((sig, conv))
        used_sectors.add(sector)
        if len(best) == 2:
            break

    if not best:
        return _no_trade(f"No AVCM setup at {now_ist.strftime('%I:%M %p IST')}. Will retry.")

    calls_built = []
    for sig, conv in best:
        call = _build_call(sig, now_ist, conv, vix, avail)
        if call:
            calls_built.append(call)

    if not calls_built:
        return _no_trade("Signal found but could not build valid levels.")

    tickers_out = [c["ticker"] for c in calls_built]
    print(f"  [AVCM SIGNAL] {tickers_out} | VIX {vix:.1f} | sectors {used_sectors}")

    alloc = _allocation_commentary(calls_built, equity=avail, vix=vix)
    return {
        "action":       "BUY",
        "calls":        calls_built,
        "allocation":   alloc,
        "conviction":   best[0][1],
        "signal_session": now_ist.strftime("%I:%M %p"),
        "timestamp":    now_ist.isoformat(),
        **calls_built[0],
    }


# ── Legacy morning recommendation (kept for --morning flag) ──────────────────

def generate_recommendation(force_fresh_backtest: bool = False) -> dict:
    """Morning fixed-time recommendation. Wraps continuous scan at 9:45 AM."""
    return generate_continuous_recommendation()


def generate_midday_recommendation() -> dict:
    """Kept for backward compat. AVCM has no fixed midday — use continuous scan."""
    return generate_continuous_recommendation()
