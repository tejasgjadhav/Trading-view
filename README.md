# NSE Intraday Signal Engine

**Live dashboard → [tejasgjadhav.github.io/Trade-Intraday](https://tejasgjadhav.github.io/Trade-Intraday/)**

---

## What is this?

A **fully automated stock-picking robot** for the Indian stock market (NSE).

Every weekday, it watches 95 Indian stocks throughout the trading day and tells you exactly **which stock to buy, at what price, and where to exit** — before the market closes. No human involved. No overnight risk. No emotion.

Think of it like a very disciplined assistant that watches the market all day so you don't have to.

---

## What problem does it solve?

Most people who try intraday trading lose money because:
- They act on emotion, not logic
- They enter too late or too early
- They don't know when to cut losses
- They hold positions overnight hoping for recovery

This engine removes all of that. Every decision is rule-based, automatic, and consistent.

---

## What does it do, day by day?

| Time | What happens |
|------|-------------|
| 9:15 AM – 2:00 PM (Mon–Fri) | Checks 95 stocks every 5 minutes. Posts a BUY when everything lines up. |
| 3:20 PM (Mon–Fri) | Closes all open positions. Records profit or loss. No overnight positions — ever. |
| Sunday 6:00 PM | Reruns 2 years of data to decide which stocks to watch next week. |
| Sunday 6:30 PM | Replays last week's market and updates model weights based on what actually worked. |

---

## Framework 1 — The 7 Signals (Confluence Model)

The engine checks **7 conditions** every 5 minutes. It requires **at least 4 of 7** to be true before even considering a trade.

**Why 4 of 7?** Testing showed that 3/7 entries consistently lost money — too many false positives. Requiring 4 means multiple independent indicators must agree, reducing noise.

| # | Signal | What it's checking | Why it matters |
|---|--------|--------------------|---------------|
| 1 | **Above Previous Day's Close** | Is today's price higher than yesterday's closing price? | Confirms the stock has momentum carrying over from the previous session |
| 2 | **ORB Breakout** | Did price break above the high of the first 30 minutes (9:15–9:45 AM)? | The opening range is a key battleground — a breakout means buyers have taken control |
| 3 | **Above VWAP** | Is price above the average price weighted by volume traded today? | VWAP is where institutional investors anchor their orders — being above it signals strength |
| 4 | **RSI in Range** | Is the momentum indicator between 55–75? | Below 55 = no momentum. Above 75 = overextended, likely to reverse. The sweet spot is in between |
| 5 | **EMA Trend Up** | Is the 9-period average price above the 21-period average price? | Short-term trend is rising faster than medium-term — textbook uptrend structure |
| 6 | **Volume Spike** | Is today's volume at least 1.5× the 20-day average? | High volume means real conviction. Low volume moves are fakeouts |
| 7 | **Near Key Level** | Is price within 0.5% of yesterday's high or low? | These levels attract attention — a break above them often accelerates the move |

**Threshold: minimum 4 of 7 must fire simultaneously. Fewer = no signal.**

---

## Framework 2 — The 4 Hard Quality Gates

Even if 4+ signals fire, the trade is **blocked** if any of these 4 gates fail:

| Gate | Exact Threshold | Plain English Explanation |
|------|-----------------|--------------------------|
| **Volume Gate** | Volume ≥ 1× 20-day average | If fewer shares than normal are trading, there's no real interest in this stock today. We skip it. |
| **ORB Range Gate** | Opening range height ≥ 1% of stock price | If the first 30 minutes of trading were very tight (e.g. a ₹500 stock only moved ₹4), the mathematical gap to the profit target is too small to be meaningful. We skip it. |
| **Nifty Trend Gate** | Nifty 50 index up ≥ 0.3% from its open | If the overall market is flat or falling, individual stocks rarely trend strongly regardless of their own signals. We skip everything. |
| **Time-to-Target Gate** | Expected profit ≥ 0.5% per hour remaining | A 1% target at 1:50 PM with 1.5 hours left doesn't clear this bar. Not enough time = not worth the risk. |

**All 4 gates must pass. Any single failure = no trade, regardless of signals.**

---

## Framework 3 — The Composite Scoring Model (0–100)

When multiple stocks pass all signals and all gates, they are scored and ranked. The top 2 are selected.

The score is built from **6 factors with fixed weights**:

| Factor | Weight | What it measures | Why this weight |
|--------|--------|-----------------|-----------------|
| **Max Single-Day Return (backtest)** | **25%** | The best single-day gain this stock ever produced in the last 2 years | Highest weight because it shows the stock's true intraday potential ceiling |
| **Backtest Win Rate** | **20%** | What % of historical signals on this stock resulted in profit | High win rate = this setup works reliably for this specific stock |
| **Live Signal Confidence** | **20%** | How many of the 7 signals are active right now (e.g. 6/7 = 0.86) | More signals aligned = higher conviction today |
| **Sharpe Ratio** | **15%** | Consistency of returns, adjusted for risk (not just average return) | A stock that returns 1% every day beats one that returns 5% one day and -4% the next |
| **Expected Return Today** | **10%** | Entry price to target price % for this specific trade | Sanity check — higher expected gain scores better |
| **Volume Confirmation** | **10%** | Today's volume vs 20-day average (capped at 3×) | Confirms real institutional participation today |

**Total = weighted sum × time multiplier (explained below)**

These weights are automatically updated every Sunday based on real trade outcomes.

---

## Framework 4 — Time Decay Multiplier

**The same stock scoring 80 at 9:45 AM beats the same stock scoring 80 at 1:30 PM.**

Why? Because a stock at 9:45 AM has 4+ hours to hit its target. The same stock at 1:30 PM has 30 minutes. Same setup, very different probability.

| Time | Multiplier | Effect on Score |
|------|-----------|-----------------|
| 9:45 AM | **1.0×** | Full score |
| 11:00 AM | ~0.75× | Score reduced by 25% |
| 12:30 PM | ~0.5× | Score halved |
| 1:30 PM | ~0.25× | Score down to a quarter |
| 2:00 PM | **0.0×** | Hard cutoff — no new signals |

The multiplier decays linearly from 9:45 AM to 2:00 PM. After 2:00 PM: no new signals, period.

---

## Framework 5 — Sector Concentration Check

The engine always picks **exactly 2 stocks from different sectors**.

If the top 2 stocks by score are both banks, or both IT companies — the second one is dropped and the next best stock from a different sector is chosen instead.

**Why?** Two stocks from the same sector move together. If banking stocks fall, both positions lose simultaneously. Picking from different sectors gives genuine diversification within the day's calls.

The 95 stocks are mapped across 14 sectors: Banking, IT, Infrastructure, Pharma, FMCG, Auto, Energy, Metals, Telecom, Real Estate, Retail, NBFC, Chemicals, and Diversified.

---

## Framework 6 — ATR-Based Profit Targets (not fixed %)

**Target = Entry Price + 14-day Average True Range (ATR)**

ATR measures how much a stock typically moves in a single day based on the last 14 trading days. The target adapts to each stock's actual behavior.

| Stock | Typical Daily Move (ATR) | Entry | Target |
|-------|--------------------------|-------|--------|
| Reliance | ₹33 (2.4%) | ₹1,360 | ₹1,393 |
| TCS | ₹78 (2.1%) | ₹3,680 | ₹3,758 |
| HDFC Bank | ₹28 (1.6%) | ₹1,740 | ₹1,768 |

A minimum 2:1 reward-to-risk ratio is enforced. If ATR gives a target that's less than 2× the stop-loss distance, the target is raised to maintain the ratio.

**Why not a fixed 2%?** Some stocks naturally move 1%, some move 4%. A fixed % either sets targets too tight (misses) or too wide (never hits).

---

## Framework 7 — Self-Learning Weight Update (Every Sunday)

Every Sunday at 6:30 PM the engine:

1. **Replays last week** — simulates every 5-minute scan bar by bar using actual market data (no hindsight)
2. **Finds winning trades** — did the stock hit the target before stop or close?
3. **Finds losing trades** — did it hit stop, or get force-closed with a loss?
4. **Measures signal quality** — for each of the 7 signals, what % of the time was it present in winners vs losers?
5. **Adjusts weights** — factors that predicted winners get slightly more weight; factors that predicted losers get less

**Guardrails:**
- Maximum weight change: ±1.5% per week (gradual, not reactive)
- Weight learning only begins after enough real trades have accumulated (minimum 5 qualifying signals)
- All 6 score factors stay within defined min/max bounds — no single factor can dominate

**This means the model improves from real market behavior, not just simulated history.**

---

## Entry and Exit Rules

| Rule | Detail |
|------|--------|
| Entry price | Price at the exact bar when all conditions are met |
| Profit target | Entry + 14-day ATR, minimum 2:1 reward/risk ratio |
| Stop loss | Just below the 9:15–9:45 AM opening range low |
| Signal cutoff | No new signals after 2:00 PM IST |
| Force close | All positions closed at 3:20 PM IST regardless of P&L |
| Overnight | Never. All positions intraday only. |
| Direction | Long (BUY) only — no shorting |

---

## What the dashboard shows

At [tejasgjadhav.github.io/Trade-Intraday](https://tejasgjadhav.github.io/Trade-Intraday/):

- Today's BUY signals: company name, entry ₹, target ₹, target %, stop ₹, stop %, R:R ratio, signals active
- Live scan log: every 5-minute check, what was found, time remaining, score, and reason if skipped
- Weekly review: signal importance table, weight changes, replayed trades from last week
- Historical trade log with outcomes (WIN / LOSS / FORCE CLOSE)

---

## Goal in one sentence

> Automatically find the 2 best Indian stocks to buy each trading day, manage the exit, never hold overnight, and get measurably smarter every week — with zero human intervention.

---

> ⚠️ For educational and research purposes only. Not financial advice. Past performance does not guarantee future results.
