# NSE Intraday Signal Engine

**Live dashboard → [tejasgjadhav.github.io/Trade-Intraday](https://tejasgjadhav.github.io/Trade-Intraday/)**

Fully automated intraday trading signal system for NSE India. No manual intervention. No overnight positions.

---

## How it works — in plain English

**Every weekday, this is what happens automatically:**

**During market hours (9:45 AM – 3:15 PM IST)**
The engine scans 95 NSE stocks every 5 minutes. The moment a stock clears all the criteria below, a BUY signal is published to the dashboard. Maximum 2 signals per day.

**At 3:20 PM IST**
All open positions are closed. The engine checks whether the target was hit, the stop was triggered, or neither — and records the result. No positions are ever held overnight.

**Every Sunday at 6 PM IST**
The engine reruns a 2-year backtest on all 95 stocks and refreshes the eligible list for the coming week.

---

## What triggers a signal

A signal is only issued when **at least 3 of these 7 conditions** are true at the same time:

| # | Condition | What it means |
|---|-----------|---------------|
| 1 | Price above previous day's close | Momentum is continuing from yesterday |
| 2 | ORB breakout | Price broke above the 9:15–9:45 AM opening range |
| 3 | Above VWAP | Price is above the average price weighted by volume |
| 4 | RSI not overbought | Stock is not already overextended |
| 5 | EMA trend up | Short-term moving average is above long-term |
| 6 | Volume spike | Today's volume is 1.5× above normal |
| 7 | Near key level | Price is near yesterday's high or low |

---

## How the best stock is picked

All qualifying stocks are ranked by a **composite score (0–100)** built from 6 factors:

| Factor | Weight | What it measures |
|--------|--------|-----------------|
| Max single-day return (backtest) | 25% | Best intraday gain this stock ever produced |
| Backtest win rate | 20% | How often it was profitable historically |
| Sharpe ratio | 15% | Consistency of returns, risk-adjusted |
| Live signal confidence | 20% | How many of the 7 signals are aligned today |
| Expected return today | 10% | Entry to target % |
| Volume confirmation | 10% | How strong today's volume is vs average |

The highest-scoring stock gets the BUY call.

---

## What if nothing qualifies?

The engine has 4 fallback tiers so a call always appears:

| Tier | Label | Condition |
|------|-------|-----------|
| 1 | HIGH | ≥60% historical win rate + ≥3/7 signals today |
| 2 | MEDIUM | ≥60% historical win rate + at least 1 signal |
| 3 | BEST MATCH | Best stock from 60-day ORB backtest, no win rate gate |
| 4 | EXPLORATORY | Pure live scan, no backtest filter at all |

The dashboard shows which tier the call came from so you know how much weight to give it.

---

## Entry and exit rules

| Rule | Detail |
|------|--------|
| Entry | Current price at the moment criteria are met |
| Target | Entry + 2× the risk (minimum 2:1 reward-to-risk) |
| Stop loss | Just below the 9:15–9:45 AM opening range low |
| Force close | All positions closed by 3:20 PM IST regardless of P&L |
| Overnight | Never. All positions intraday only. |

---

## Position sizing

Uses **fractional Kelly criterion** (25% of full Kelly, capped at 20% of capital per trade). When two signals are active on the same day, capital is split proportionally by composite score.

---

## Automation schedule

| Time | What runs |
|------|-----------|
| Every 5 min, 9:45 AM – 3:15 PM IST (Mon–Fri) | Live scan → publishes signal when criteria met |
| 3:20 PM IST (Mon–Fri) | Records exit price and result |
| 6:00 PM IST (Sunday) | Reruns 2-year backtest, refreshes stock rankings |

---

## Stock universe

95 NSE F&O-eligible stocks across IT, Banking, Energy, Industrials, Pharma, Auto, FMCG, Metals, Telecom, and Consumer sectors. Full list in [`engine/config.py`](engine/config.py).

---

> ⚠️ Educational and research purposes only. Not financial advice. Past backtest performance does not guarantee future results.
