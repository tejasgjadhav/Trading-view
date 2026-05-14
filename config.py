"""
Trading Strategy Configuration — NSE India
Inspired by strategies from world's top traders
"""

# ─── WATCHLIST — Full Nifty 50 + Midcap leaders + ETFs ──────────────────────
# suffix .NS = NSE | covers all major Nifty 50 constituents
WATCHLIST = [
    # IT & Tech
    "TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "LTIM.NS",
    # Banking & Financials
    "HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "SBIN.NS", "AXISBANK.NS",
    "BAJFINANCE.NS", "BAJAJFINSV.NS", "HDFCLIFE.NS", "SBILIFE.NS", "INDUSINDBK.NS",
    # Energy & Oil
    "RELIANCE.NS", "ONGC.NS", "BPCL.NS", "COALINDIA.NS", "POWERGRID.NS", "NTPC.NS",
    # Industrials & Infra
    "LT.NS", "ADANIENT.NS", "ADANIPORTS.NS", "GRASIM.NS", "ULTRACEMCO.NS",
    # Metals & Materials
    "JSWSTEEL.NS", "TATASTEEL.NS", "HINDALCO.NS",
    # Consumer & FMCG
    "HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS", "TATACONSUM.NS", "ASIANPAINT.NS",
    # Auto
    "MARUTI.NS", "TATAMOTORS.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS", "EICHERMOT.NS",
    # Pharma & Health
    "SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "APOLLOHOSP.NS",
    # Others
    "TITAN.NS", "SHRIRAMFIN.NS",
    # ETFs
    "NIFTYBEES.NS", "GOLDBEES.NS", "JUNIORBEES.NS",
]

# ─── BACKTEST SETTINGS ───────────────────────────────────────────────────────
BACKTEST_PERIOD_YEARS = 3          # Years of historical data to backtest
INITIAL_CAPITAL = 100_000          # Starting capital in INR (₹1 lakh)
POSITION_SIZE_PCT = 0.10           # 10% of capital per trade
MAX_POSITIONS = 8                  # Max concurrent open positions
COMMISSION_PCT = 0.0003            # 0.03% brokerage (Zerodha flat fee approx)
SLIPPAGE_PCT = 0.0005              # 0.05% slippage

# ─── RISK MANAGEMENT ─────────────────────────────────────────────────────────
STOP_LOSS_PCT = 0.07               # 7% stop loss
TAKE_PROFIT_PCT = 0.20             # 20% take profit
TRAILING_STOP_PCT = 0.05           # 5% trailing stop

# ─── STRATEGY WEIGHTS (Ensemble) ─────────────────────────────────────────────
STRATEGY_WEIGHTS = {
    "turtle":           0.25,      # Richard Dennis / William Eckhardt
    "ma_crossover":     0.20,      # Paul Tudor Jones / Stanley Druckenmiller
    "momentum_rsi":     0.25,      # Jesse Livermore momentum style
    "breakout_volume":  0.15,      # Jesse Livermore breakout
    "mean_reversion":   0.15,      # Ray Dalio / John Henry mean reversion
}

# Minimum ensemble score to generate a signal
ENSEMBLE_BUY_THRESHOLD = 0.55
ENSEMBLE_SELL_THRESHOLD = -0.40

# ─── SCHEDULE (IST = UTC+5:30) ───────────────────────────────────────────────
SIGNAL_TIME = "09:00"              # 9:00am IST (pre-market, NSE opens 9:15am)
TIMEZONE = "Asia/Kolkata"
CURRENCY = "INR"
CURRENCY_SYMBOL = "₹"

# ─── DATA PATHS ──────────────────────────────────────────────────────────────
TRADE_LOG_PATH = "data/trade_log.json"
BACKTEST_RESULTS_PATH = "results/backtest_results.json"
PERFORMANCE_LOG_PATH = "data/performance_log.json"
REPORT_PATH = "reports/daily_report.md"
