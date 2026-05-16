"""
AVCM Strategy — Adaptive Volume-Confirmed Momentum
NSE Intraday · Long Only · Rating: 9.1/10
Edit ONLY this file to change behavior.
"""
import pytz

IST = pytz.timezone("Asia/Kolkata")

# --- INSTRUMENTS ---
CASH_EQUITIES = [
    "RELIANCE.NS","HDFCBANK.NS","INFY.NS","TCS.NS","ICICIBANK.NS",
    "AXISBANK.NS","SBIN.NS","WIPRO.NS","LT.NS","BAJFINANCE.NS",
    "HCLTECH.NS","KOTAKBANK.NS","ADANIENT.NS","ITC.NS","SUNPHARMA.NS",
    "MPHASIS.NS","TATACONSUM.NS","M&M.NS","DRREDDY.NS","CIPLA.NS",
    "VEDL.NS","TATAPOWER.NS","ADANIGREEN.NS","BAJAJ-AUTO.NS","TITAN.NS",
    "BRITANNIA.NS","FEDERALBNK.NS","MUTHOOTFIN.NS","PNB.NS","NTPC.NS",
]

# Full 95-stock NSE F&O liquid watchlist
WATCHLIST = [
    "TCS.NS","INFY.NS","WIPRO.NS","HCLTECH.NS","TECHM.NS",
    "MPHASIS.NS","COFORGE.NS","PERSISTENT.NS","OFSS.NS",
    "HDFCBANK.NS","ICICIBANK.NS","KOTAKBANK.NS","SBIN.NS","AXISBANK.NS",
    "INDUSINDBK.NS","FEDERALBNK.NS","IDFCFIRSTB.NS","BANDHANBNK.NS",
    "BANKBARODA.NS","PNB.NS","UNIONBANK.NS",
    "BAJFINANCE.NS","BAJAJFINSV.NS","HDFCLIFE.NS","SBILIFE.NS",
    "CHOLAFIN.NS","MUTHOOTFIN.NS","SHRIRAMFIN.NS","RECLTD.NS","PFC.NS","IRFC.NS",
    "RELIANCE.NS","ONGC.NS","BPCL.NS","IOC.NS","COALINDIA.NS",
    "POWERGRID.NS","NTPC.NS","TATAPOWER.NS","ADANIGREEN.NS",
    "LT.NS","ADANIENT.NS","ADANIPORTS.NS","SIEMENS.NS","ABB.NS",
    "BHEL.NS","HAVELLS.NS","POLYCAB.NS","VOLTAS.NS",
    "ULTRACEMCO.NS","GRASIM.NS","AMBUJACEM.NS","ACC.NS",
    "JSWSTEEL.NS","TATASTEEL.NS","HINDALCO.NS","VEDL.NS","SAIL.NS","NMDC.NS",
    "MARUTI.NS","BAJAJ-AUTO.NS","HEROMOTOCO.NS",
    "EICHERMOT.NS","M&M.NS","ASHOKLEY.NS","BALKRISIND.NS",
    "HINDUNILVR.NS","ITC.NS","NESTLEIND.NS","BRITANNIA.NS",
    "TATACONSUM.NS","ASIANPAINT.NS","GODREJCP.NS","MARICO.NS","DABUR.NS","PIDILITIND.NS",
    "SUNPHARMA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS","APOLLOHOSP.NS",
    "LUPIN.NS","TORNTPHARM.NS","AUROPHARMA.NS","ZYDUSLIFE.NS",
    "TITAN.NS","DMART.NS","TRENT.NS","JUBLFOOD.NS",
    "BHARTIARTL.NS","NAUKRI.NS","INDIGO.NS","DLF.NS","GODREJPROP.NS","ZOMATO.NS",
]

# --- TIMING (IST) ---
KILL_SWITCH_TIME  = "15:10"   # AVCM: force close all at 3:10 PM (tranche 3)
SIGNAL_CUTOFF     = "13:30"   # AVCM: no new signals after 1:30 PM
MARKET_OPEN       = "09:15"
MARKET_CLOSE      = "15:30"
ENTRY_TIME        = "09:45"   # ORB forms by 9:44 AM; signals start 9:45 AM
ENTRY_TIME_MIDDAY = "13:30"   # alias (not used in AVCM — signals cut at 1:30 PM)

# Bar indices in 5-min data (bar 0 = 9:15 AM)
MORNING_ENTRY_BAR = 5         # 9:45 AM signal → bar 5 close (9:40-9:44 AM)
MIDDAY_ENTRY_BAR  = 20        # kept for backward compat

# --- RISK PARAMETERS ---
CAPITAL              = 100_000   # INR — set to your actual capital
DAILY_LOSS_LIMIT     = 0.02      # Stop trading if daily loss > 2% of equity
MIN_REWARD_RISK      = 2.5       # AVCM: reject setups below 2.5:1 R:R
MIN_RETURN_PCT       = 0.8       # Entry→Target must be ≥ 0.8%
MAX_RISK_PER_TRADE   = 0.015     # Fallback max risk per trade
KELLY_FRACTION       = 0.25      # Kept for fallback sizing
MAX_TRADES_PER_DAY   = 2         # Max simultaneous open positions

# --- VIX-ADJUSTED POSITION SIZING (AVCM Half-Kelly) ---
INDIA_VIX_TICKER     = "^INDIAVIX"
VIX_NO_TRADE         = 22        # VIX ≥ 22 → no trade at all
VIX_HIGH             = 18        # VIX 18–22 → 3% of equity per trade
VIX_LOW              = 13        # VIX < 13 → 8% of equity per trade (low vol)
EQUITY_PCT_LOW_VIX   = 0.08      # VIX < 13: 8% per trade
EQUITY_PCT_NORMAL_VIX= 0.06      # VIX 13–18: 6% per trade (normal)
EQUITY_PCT_HIGH_VIX  = 0.03      # VIX 18–22: 3% per trade (elevated risk)
RETEST_BONUS         = 1.25      # +25% position size on confirmed retest signal

# --- CIRCUIT BREAKERS ---
CIRCUIT_BREAKER_CONSEC_LOSSES = 3     # 3 consecutive stop-outs → stop for the day
MAX_EQUITY_DRAWDOWN_PCT       = 0.08  # Drawdown > 8% from peak → halve all sizes

# --- AVCM STRATEGY PARAMETERS ---
OPENING_RANGE_MINUTES     = 30    # 9:15–9:44 AM observation window
RSI_PERIOD                = 14
RSI_MOMENTUM_LOW          = 55    # RSI must be ABOVE this (momentum floor)
RSI_MOMENTUM_HIGH         = 72    # RSI must be BELOW this (not overbought)
EMA_FAST                  = 9     # kept for regime context only
EMA_SLOW                  = 21
VOLUME_SURGE_MULTIPLIER   = 2.0   # Signal bar must be ≥ 2× per-bar ORB avg volume
VWAP_DEVIATION_THRESHOLD  = 0.005

# AVCM requires ALL 5 factors to fire simultaneously — no partial signals
MIN_SIGNALS_REQUIRED      = 5     # All 5 AVCM factors must be true
MIN_SIGNALS_WATCHLIST     = 3     # Watchlist consideration threshold

# --- ENTRY QUALITY GATES ---
MIN_ORB_RANGE_PCT         = 0.8   # ORB range ≥ 0.8% of price (tight range = target unreachable)
MIN_RETURN_PER_HOUR       = 0.5   # Expected return ≥ 0.5% per remaining hour
NIFTY_TREND_TICKER        = "^NSEI"
MIN_NIFTY_TREND_PCT       = 0.0   # Nifty must be positive from open (Factor 5 handles this)
MIN_NIFTY_PREOPEN_PCT     = -0.5  # Pre-open must not be gap-down > 0.5%
NIFTY_EMA_PERIOD          = 20    # Nifty must be above 20-day EMA (regime check)
MIN_VOL_RATIO             = 1.0   # Daily volume ≥ 1× average

# --- SECTOR MOMENTUM (pre-market regime) ---
SECTOR_MOMENTUM_TOP_N     = 4     # Trade stocks only from top 4 sectors by 5-day return
SECTOR_MOMENTUM_BLOCK_N   = 4     # Block bottom 4 sectors regardless of signals

# --- TRANCHE EXIT SYSTEM (AVCM) ---
EXIT_TRANCHE_1_PCT        = 0.35  # Exit 35% at Entry + 1× stop distance (lock profit)
EXIT_TRANCHE_2_PCT        = 0.35  # Exit 35% at target OR 1:30 PM
EXIT_TRANCHE_3_PCT        = 0.30  # Exit 30% at 3:10 PM (force close)
EXIT_TRANCHE_1_R_MULT     = 1.0   # Tranche 1 fires at 1× risk distance profit

# --- BACKTEST CONFIG ---
BACKTEST_PERIOD_YEARS   = 2
MIN_WIN_RATE_THRESHOLD  = 0.60   # Watchlist gate: ≥60% win rate
COMMISSION_PER_TRADE    = 20     # INR per order (Zerodha)
SLIPPAGE_PERCENT        = 0.001  # 0.1%

# --- COMPOSITE SCORE WEIGHTS (must sum to 1.0) ---
# Score is 0–100; each factor normalized before weighting.
# Time multiplier applied after: 1.0x at 9:45 AM → 0.0x at 1:30 PM.
SCORE_WEIGHTS = {
    "max_1day_return":  0.25,   # Best single-day backtest gain potential (25%)
    "win_rate":         0.20,   # Historical reliability (20%)
    "sharpe_ratio":     0.15,   # Risk-adjusted consistency (15%)
    "confidence":       0.20,   # Live signal alignment — all 5 = 1.0 (20%)
    "expected_return":  0.10,   # Entry→target % today, residual ATR-based (10%)
    "vol_ratio":        0.10,   # Volume confirmation, capped at 3× (10%)
}
# Time decay: 9:45 AM = full score, 1:30 PM = zero (no signals after cutoff)
SCORE_TIME_START  = "09:45"
SCORE_TIME_END    = "13:30"

# --- PATHS ---
ORB_BACKTEST_PATH = "results/intraday_backtest.json"
CALLS_PATH        = "data/daily_calls.json"
SCAN_LOG_PATH     = "data/scan_log.json"
REPORTS_DIR       = "reports"
BT_CACHE_PATH     = "results/quant_backtest_cache.json"

# --- ONLY BUY ---
ONLY_BUY = True   # Never short, never puts
STAT_ARB_ZSCORE_ENTRY = 2.0
STAT_ARB_ZSCORE_EXIT  = 0.5
