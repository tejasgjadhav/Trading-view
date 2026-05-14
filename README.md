# NSE Intraday Signal Engine

**Live dashboard → [tejasgjadhav.github.io/Trading-view](https://tejasgjadhav.github.io/Trading-view/)**

Fully automated intraday trading signal system for NSE India. Scans 95 F&O-eligible Nifty stocks every morning, runs a rigorous backtest gate, and outputs up to two BUY calls at 9:45 AM IST with exact entry, target, stop-loss, and capital allocation commentary. No overnight positions. No manual intervention.

---

## Strategy

### Signal Generation — 7-Factor Confluence Model

A signal is only issued when at least **3 of 7 factors** are aligned in the same direction (BUY only; no shorting):

| # | Signal | Description |
|---|--------|-------------|
| 1 | **PDC Position** | Price above previous day's close — momentum carry |
| 2 | **ORB Breakout** | Price breaks above the 9:15–9:45 AM opening range high |
| 3 | **VWAP Position** | Price above VWAP — institutional benchmark confirmation |
| 4 | **RSI** | RSI not overbought (< 65); oversold bounce preferred |
| 5 | **EMA Trend** | Fast EMA (9) above Slow EMA (21) — trend confirmation |
| 6 | **Volume Spike** | Current volume ≥ 1.5× 20-day average — conviction |
| 7 | **Key Level** | Price near previous day's high/low (support/resistance) |

A **confidence score** (0–100%) and **market regime** (Trending / Range / Volatile) are also computed per stock.

### Backtest Gate — Must Pass Before Any Live Signal

Every Sunday at 6 PM IST, the engine runs a **2-year daily backtest** across all 95 stocks using three strategy variants (ORB, VWAP, MOMENTUM).

- A stock-strategy combo is **only eligible** if its 2-year backtest win rate is **≥ 80%**
- Eligible combos are **ranked by maximum single-day return** — the best intraday gain ever produced by that setup in the backtest period
- On weekdays, only stocks from the top of this ranked list are scanned for live signals

This means no live trade is ever taken on a setup that hasn't proven itself over 2 years of daily history.

### Entry & Exit Rules

| Rule | Detail |
|------|--------|
| **Entry time** | 9:45 AM IST (after 30-min opening range is established) |
| **Entry price** | Live market price at 9:45 AM |
| **Target** | Entry + 2× risk (minimum 2:1 reward-to-risk) |
| **Stop Loss** | Just below ORB low (0.2% buffer) |
| **Minimum return** | ≥ 1% entry → target required |
| **Force close** | All positions closed by **2:00 PM IST** regardless of P&L |
| **Overnight** | Never held overnight under any circumstance |

### Position Sizing — Fractional Kelly

Position size is computed using the **fractional Kelly criterion** (25% of full Kelly), capped at 20% of capital per trade:

```
f* = (p × b − q) / b  ×  0.25
```

Where `p` = backtest win rate, `q` = 1 − p, `b` = reward-to-risk ratio.

When **two signals** are issued on the same day, capital is split proportionally by `confidence × max_1day_return`, with a maximum 85% total deployment (remaining 15% held as buffer).

---

## Automation Schedule

| Time (IST) | GitHub Actions Workflow | What it does |
|------------|------------------------|--------------|
| **9:45 AM Mon–Fri** | `intraday_morning.yml` | Runs signal engine → saves call to `data/daily_calls.json` |
| **3:35 PM Mon–Fri** | `intraday_close.yml` | Records exit price and P&L → updates equity |
| **6:00 PM Sunday** | `weekly_backtest.yml` | Reruns 2-year backtest → refreshes eligible stock rankings |

---

## Capital Tracking

- Starting capital: **₹1,00,000**
- Position size: Kelly-sized per trade (capped at 20% of current equity)
- Brokerage: 0.06% round-trip (Zerodha)
- All P&L tracked date-wise in `data/daily_calls.json`
- Running equity updated after each EOD close

---

## Repository Structure

```
├── engine/                    # Signal engine
│   ├── agent.py               # Entry point — run at 9:45 AM
│   ├── backtest.py            # 2-year backtester (80% WR gate, max 1-day ranking)
│   ├── config.py              # All parameters + 95-stock watchlist
│   ├── data_fetcher.py        # yfinance / NSE data wrapper
│   ├── recommendation.py      # Outputs top 2 BUY calls + allocation commentary
│   ├── risk_manager.py        # Fractional Kelly position sizing
│   └── signals.py             # 7-signal computation engine
├── live/
│   └── intraday_close.py      # EOD P&L recorder (3:35 PM)
├── docs/index.html            # Live dashboard (GitHub Pages)
├── data/daily_calls.json      # All signals + P&L log
└── results/intraday_backtest.json  # Latest weekly backtest rankings
```

---

## Universe

95 NSE F&O-eligible stocks across all major sectors:
IT, Banking, NBFC, Energy, Industrials, Cement, Metals, Auto, FMCG, Pharma, Consumer, Telecom.

Full list in [`engine/config.py`](engine/config.py).

---

> ⚠️ Educational and research purposes only. Not financial advice. Past backtest performance does not guarantee future results. Always exercise independent judgement before placing any trade.
