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

### Composite Score — 6-Parameter Ranking (0–100)

All candidates are ranked by a weighted composite score. Each factor is normalized across the candidate pool (0–1) before weighting:

| Factor | Weight | Description |
|--------|--------|-------------|
| Max 1-Day Return (BT) | 25% | Best single intraday gain in 2-year backtest |
| Backtest Win Rate | 20% | Historical % of profitable days |
| Sharpe Ratio | 15% | Risk-adjusted consistency |
| Live Signal Confidence | 20% | Signals aligned ÷ 7 today |
| Expected Return Today | 10% | Entry → target % |
| Volume Confirmation | 10% | Current volume vs 20-day average (capped 3×) |

### Backtest Gate & 4-Tier Fallback — Always One Stock Shows Up

Every Sunday at 6 PM IST the engine reruns a **2-year daily backtest** (ORB / VWAP / MOMENTUM) on the 30-stock core list. Win rate threshold is **≥ 70%**. If no stock clears the bar, the engine falls through tiers until it finds the best available setup:

| Tier | Conviction | Condition |
|------|-----------|-----------|
| **1** | HIGH | 2-yr WR ≥ 70% **and** ≥ 3/7 live signals aligned |
| **2** | MEDIUM | 2-yr WR ≥ 70% **and** ≥ 1/7 live signals |
| **3** | BEST MATCH | 60-day ORB backtest on all 95 stocks — best composite score |
| **4** | EXPLORATORY | Pure live scan of all 95 stocks — no backtest filter |

A call is **always issued**. The dashboard shows which tier it came from so you know how much weight to give it.

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

When **two signals** are issued on the same day, capital is split proportionally by composite score, with a maximum 85% total deployment (remaining 15% held as buffer).

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
