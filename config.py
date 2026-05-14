"""
Trading Strategy Configuration — NSE India
Inspired by strategies from world's top traders
"""

# ─── WATCHLIST (NSE India) ────────────────────────────────────────────────────
# Top Nifty 50 stocks + sector ETFs — suffix .NS = NSE, .BO = BSE
WATCHLIST = [
    # Large-cap — Nifty heavyweights
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "BAJFINANCE.NS", "BHARTIARTL.NS", "KOTAKBANK.NS", "WIPRO.NS",
    # Banking & Financials
    "SBIN.NS", "AXISBANK.NS", "HDFCLIFE.NS",
    # Industrials & Infra
    "ADANIENT.NS", "ADANIPORTS.NS", "LTIM.NS",
    # Consumer & Auto
    "MARUTI.NS", "TITAN.NS", "ASIANPAINT.NS",
    # ETFs (Nifty + Gold + IT)
    "NIFTYBEES.NS", "GOLDBEES.NS", "JUNIORBEES.NS",
]

# ─── BACKTEST SETTINGS ───────────────────────────────────────────────────────
BACKTEST_PERIOD_YEARS = 3          # Years of historical data to backtest
INITIAL_CAPITAL = 1_000_000        # Starting capital in INR (₹10 lakhs)
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
