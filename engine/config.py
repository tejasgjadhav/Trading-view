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

# Full 95-stock NSE F&O liquid watchlist (used by weekly backtest scanner)
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
MIN_SIGNALS_REQUIRED        = 3   # Full BUY: ≥3 of 7 signals
MIN_SIGNALS_WATCHLIST       = 1   # Reduced conviction: ≥1 of 7 signals

# --- BACKTEST CONFIG ---
BACKTEST_PERIOD_YEARS   = 2
MIN_WIN_RATE_THRESHOLD  = 0.60   # Gate: ≥60% win rate required for Tier 1/2
COMMISSION_PER_TRADE    = 20     # INR per order (Zerodha)
SLIPPAGE_PERCENT        = 0.001  # 0.1%

# --- COMPOSITE SCORE WEIGHTS (must sum to 1.0) ---
# Score is 0–100; each factor normalized to 0–1 before weighting
SCORE_WEIGHTS = {
    "max_1day_return":  0.25,   # Best single-day backtest gain potential
    "win_rate":         0.20,   # Historical reliability
    "sharpe_ratio":     0.15,   # Risk-adjusted consistency
    "confidence":       0.20,   # Live signal alignment (signals/7)
    "expected_return":  0.10,   # Entry→target % today
    "vol_ratio":        0.10,   # Volume confirmation (capped at 3×)
}

# --- FALLBACK TICKERS (expanded NSE universe for deep scan) ---
ORB_BACKTEST_PATH = "results/intraday_backtest.json"  # 60-day data for 95 stocks

# --- ONLY BUY (user requirement) ---
ONLY_BUY = True   # Never short, never puts

# --- PATHS ---
CALLS_PATH   = "data/daily_calls.json"
REPORTS_DIR  = "reports"
BT_CACHE_PATH = "results/quant_backtest_cache.json"
