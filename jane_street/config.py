"""
Quant Signal Engine — Master Config
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

PAIRS_FOR_STAT_ARB = [
    ("HDFCBANK.NS", "ICICIBANK.NS"),
    ("RELIANCE.NS",  "ONGC.NS"),
    ("INFY.NS",      "TCS.NS"),
]

# --- TIMING (IST) ---
ENTRY_TIME        = "09:45"   # Never before this
KILL_SWITCH_TIME  = "14:00"   # Force-close all positions at 2 PM
MARKET_OPEN       = "09:15"
MARKET_CLOSE      = "15:30"

# --- RISK PARAMETERS ---
CAPITAL              = 100_000   # INR — user set ₹1 lakh
MAX_RISK_PER_TRADE   = 0.015     # 1.5% of capital max risk per trade
DAILY_LOSS_LIMIT     = 0.02      # Stop trading if daily loss > 2%
KELLY_FRACTION       = 0.25      # 25% of full Kelly (conservative)
MIN_REWARD_RISK      = 2.0       # Reject setups below 2:1 R:R
MIN_RETURN_PCT       = 1.0       # Entry→Target must be ≥ 1%
MAX_TRADES_PER_DAY   = 2         # Quality > quantity

# --- STRATEGY PARAMETERS ---
OPENING_RANGE_MINUTES      = 30    # 9:15–9:45 for ORB range
VWAP_DEVIATION_THRESHOLD   = 0.005 # 0.5% from VWAP to trigger
RSI_PERIOD                 = 14
RSI_OVERSOLD               = 35
RSI_OVERBOUGHT             = 65
EMA_FAST                   = 9
EMA_SLOW                   = 21
STAT_ARB_ZSCORE_ENTRY      = 2.0
STAT_ARB_ZSCORE_EXIT       = 0.5
VOLUME_SURGE_MULTIPLIER    = 1.5

# --- SIGNAL CONFLUENCE ---
MIN_SIGNALS_REQUIRED = 3   # Must have ≥3 of 7 signals aligned

# --- BACKTEST CONFIG ---
BACKTEST_PERIOD_YEARS   = 2
MIN_WIN_RATE_THRESHOLD  = 0.80   # Agent does NOT trade if backtest < 80%
COMMISSION_PER_TRADE    = 20     # INR per order (Zerodha)
SLIPPAGE_PERCENT        = 0.001  # 0.1%

# --- ONLY BUY (user requirement) ---
ONLY_BUY = True   # Never short, never puts

# --- PATHS ---
CALLS_PATH   = "data/daily_calls.json"
REPORTS_DIR  = "reports"
BT_CACHE_PATH = "results/quant_backtest_cache.json"
