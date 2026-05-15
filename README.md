# NSE Intraday Signal Engine

**Live dashboard → [tejasgjadhav.github.io/Trade-Intraday](https://tejasgjadhav.github.io/Trade-Intraday/)**

Fully automated intraday trading signal system for NSE India. No manual intervention. No overnight positions.

---

## How it works — in plain English

**Every weekday, this is what happens automatically:**

**9:15 AM – 2:00 PM IST — Continuous scan**
The engine scans 95 NSE stocks every 5 minutes. The moment a stock clears all entry criteria, a BUY signal is published to the dashboard. No fixed signal time — it fires exactly when the setup is ready. No new signals after 2:00 PM (not enough time left to hit target).

**3:20 PM IST — Force close**
All open positions are closed. The engine records whether the target was hit, stop was triggered, or neither. No positions held overnight — ever.

**Every Sunday at 6:30 PM IST — Weekly review**
The engine replays last week's market data bar by bar, checks which signals would have been issued, simulates outcomes, and analyses which of the 7 signals predicted winners vs losers. From the second Sunday onward, it automatically nudges the model weights toward what actually worked.

**Every Sunday at 6:00 PM IST — Backtest refresh**
Reruns 2-year backtest on all stocks and refreshes the eligible list for the coming week.

---

## What triggers a signal

A signal is only issued when **at least 4 of these 7 conditions** are true at the same time:

| # | Condition | What it means |
|---|-----------|---------------|
| 1 | Price above previous day's close | Momentum continuing from yesterday |
| 2 | ORB breakout | Price broke above the 9:15–9:45 AM opening range |
| 3 | Above VWAP | Price is above the volume-weighted average price |
| 4 | RSI momentum | RSI is in a healthy range — not overextended |
| 5 | EMA trend up | Short-term moving average above long-term |
| 6 | Volume spike | Today's volume is 1.5× above normal |
| 7 | Near key level | Price is near yesterday's high or low |

---

## Hard entry quality gates

Even if 4/7 signals fire, the signal is **blocked** if any of these fail:

| Gate | Threshold | Why |
|------|-----------|-----|
| Volume | ≥ 1× average | Low volume = no institutional participation |
| ORB range width | ≥ 1% of price | Tight range = target mathematically unreachable |
| Nifty trend | ≥ +0.3% from open | Rangebound market = individual stocks won't trend |
| Time-to-target | ≥ 0.5% per hour left | Late entries with small targets = not worth the risk |

---

## How the best stock is picked

All qualifying stocks are ranked by a **composite score (0–100)** built from 6 factors. Scores decay linearly throughout the day — a stock scoring 80 at 9:45 AM beats the same stock scoring 80 at 1:00 PM.

| Factor | Weight | What it measures |
|--------|--------|-----------------|
| Max single-day return (backtest) | 25% | Best intraday gain this stock ever produced |
| Backtest win rate | 20% | How often it was profitable historically |
| Sharpe ratio | 15% | Consistency of returns, risk-adjusted |
| Live signal confidence | 20% | How many of the 7 signals are aligned today |
| Expected return today | 10% | Entry to target % |
| Volume confirmation | 10% | How strong today's volume is vs average |

The **top 2 highest-scoring stocks from different sectors** get the BUY call. Two signals from the same sector (e.g. two banks or two IT stocks) are blocked — only the better one is taken.

Weights are automatically updated every Sunday based on what actually worked the previous week.

---

## Entry and exit rules

| Rule | Detail |
|------|--------|
| Entry | Price at the bar when criteria are met (anchored to 9:45 AM for morning signals) |
| Target | Entry + 1× 14-day ATR (Average True Range) — adapts to each stock's actual volatility, minimum 2:1 R:R |
| Stop loss | Just below the 9:15–9:45 AM opening range low |
| Signal cutoff | No new signals after 2:00 PM IST |
| Force close | All positions closed at 3:20 PM IST regardless of P&L |
| Overnight | Never. All positions intraday only. |

---

## Automation schedule

| Time | What runs |
|------|-----------|
| 9:15 AM – 2:00 PM IST, every 5 min (Mon–Fri) | Live scan → publishes signal when all gates pass |
| 3:20 PM IST (Mon–Fri) | Force closes all positions, records P&L |
| 6:00 PM IST (Sunday) | Reruns 2-year backtest, refreshes stock rankings |
| 6:30 PM IST (Sunday) | Replays last week bar by bar, analyses signal performance, updates model weights |

---

## Self-learning model

Every Sunday the engine:
1. Replays the entire previous week using actual market data
2. Identifies which signals (ORB, VWAP, RSI etc.) were active in winning trades
3. Identifies which were active in losing trades
4. Nudges the composite score weights toward signals that predicted winners
5. Maximum weight change is ±1.5% per week — gradual, not reactive

This means the model improves from real trade outcomes over time, not just historical backtests.

---

## Stock universe

95 NSE-listed stocks across IT, Banking, NBFC, Energy, Infra, Metals, Auto, FMCG, Pharma, Retail, Telecom, and Real Estate. Signals are picked from different sectors each day to avoid concentration risk. Full list in [`engine/config.py`](engine/config.py).

---

> ⚠️ Educational and research purposes only. Not financial advice. Past performance does not guarantee future results.
