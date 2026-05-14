"""
Trading Strategy Configuration
Inspired by strategies from world's top traders
"""

# ─── WATCHLIST ───────────────────────────────────────────────────────────────
# Top liquid stocks + ETFs across sectors
WATCHLIST = [
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
    # Financials
    "JPM", "GS", "BAC",
    # ETFs (for macro plays)
    "SPY", "QQQ", "IWM", "GLD", "TLT",
    # Energy
    "XOM", "CVX",
    # Healthcare
    "UNH", "JNJ",
]

# ─── BACKTEST SETTINGS ───────────────────────────────────────────────────────
BACKTEST_PERIOD_YEARS = 3          # Years of historical data to backtest
INITIAL_CAPITAL = 100_000          # Starting capital in USD
POSITION_SIZE_PCT = 0.10           # 10% of capital per trade (risk management)
MAX_POSITIONS = 8                  # Max concurrent open positions
COMMISSION_PCT = 0.001             # 0.1% commission per trade (realistic)
SLIPPAGE_PCT = 0.0005              # 0.05% slippage

# ─── RISK MANAGEMENT ─────────────────────────────────────────────────────────
STOP_LOSS_PCT = 0.07               # 7% stop loss (Paul Tudor Jones rule)
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

# ─── SCHEDULE ────────────────────────────────────────────────────────────────
SIGNAL_TIME = "09:00"              # Generate signals at 9am ET (pre-market)
TIMEZONE = "America/New_York"

# ─── DATA PATHS ──────────────────────────────────────────────────────────────
TRADE_LOG_PATH = "data/trade_log.json"
BACKTEST_RESULTS_PATH = "results/backtest_results.json"
PERFORMANCE_LOG_PATH = "data/performance_log.json"
REPORT_PATH = "reports/daily_report.md"
