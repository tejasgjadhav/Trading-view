# NSE Intraday Signal Engine

**Live dashboard → [tejasgjadhav.github.io/Trade-Intraday](https://tejasgjadhav.github.io/Trade-Intraday/)**

---

## What is this?

This is a **fully automated stock-picking robot** for the Indian stock market (NSE).

Every weekday, it wakes up on its own, watches 95 Indian stocks throughout the trading day, and tells you exactly **which stock to buy, at what price, and where to exit** — before the market closes. No human involved. No overnight risk.

Think of it like a very disciplined assistant that watches the market all day so you don't have to.

---

## What problem does it solve?

Most people who try intraday trading (buying and selling stocks within the same day) lose money because:

- They act on emotion, not logic
- They enter too late or too early
- They don't know when to cut losses
- They hold positions overnight hoping for recovery

This engine removes all of that. Every decision is rule-based, automatic, and consistent — no panic, no greed, no guesswork.

---

## What does it actually do, day by day?

**Morning (9:15 AM – 2:00 PM)**
The robot wakes up and checks 95 stocks every 5 minutes. It's looking for stocks that show strong signs of going up. The moment it finds one that passes all its checks, it posts a BUY signal on the dashboard with the exact buy price, profit target, and stop-loss.

**Afternoon (3:20 PM)**
Whether the trade hit its target or not — the robot closes everything and records the result. No positions are ever held overnight. You go to sleep knowing you're flat.

**Every Sunday (6:00 PM)**
The robot reruns 2 years of historical data to decide which stocks are worth watching next week.

**Every Sunday (6:30 PM)**
The robot replays last week's market, checks which of its own rules actually predicted winning trades, and quietly adjusts its own weights — making itself slightly smarter each week.

---

## How does it decide to buy?

It checks **7 conditions** before buying. At least 4 must be true simultaneously:

| # | Plain English |
|---|--------------|
| 1 | The stock is already above yesterday's closing price |
| 2 | The stock just broke above the price range from the first 30 minutes of trading |
| 3 | The stock is trading above where the average buyer paid today |
| 4 | The stock's momentum indicator is in a healthy zone — not overheated |
| 5 | The short-term price trend is pointing upward |
| 6 | More shares are being traded than usual today (1.5× normal) |
| 7 | The stock is near a price level that proved important yesterday |

If fewer than 4 of these are true, no signal. The robot waits.

---

## What are the hard safety checks?

Even if 4 conditions are met, the robot will still say NO if any of these fail:

| Check | What it means in plain English |
|-------|-------------------------------|
| Volume check | Not enough people trading this stock today — we skip it |
| Price range check | The morning price range was too tight — mathematically can't make enough profit |
| Market mood check | The overall Nifty index is flat or falling — individual stocks won't move either |
| Time check | It's too late in the day — not enough time left to reach the profit target |

These four filters catch the "technically looks good but practically won't work" situations.

---

## How does it pick which stock to buy?

When multiple stocks pass all the checks, each one gets a score from 0 to 100 based on:

- How well this stock has performed historically
- How consistent its past returns were
- How confident the signals are today
- How much profit we expect vs the risk
- How strong today's trading volume is

**The score also adjusts for time of day** — a stock signaling at 9:45 AM gets full marks, the same stock at 1:00 PM gets a lower score because there's less time to reach the target.

The robot picks the **top 2 stocks from different industries** (e.g. one bank stock + one IT stock). It never picks two stocks from the same sector — that would be putting all eggs in one basket.

---

## What happens after the buy signal?

| Decision | How it's made |
|----------|--------------|
| Buy price | The price when all conditions are met |
| Profit target | Based on how much this stock typically moves in a day (not a fixed %) |
| Stop loss | Just below the morning's lowest price — protecting against a big fall |
| Latest signal time | 2:00 PM — no new signals after this |
| Force exit | 3:20 PM — everything is closed, profit or loss locked in |

---

## Does it learn from mistakes?

Yes. Every Sunday it looks at last week's trades and asks:

*"Which of my 7 conditions were active in the winning trades? Which were active in the losing ones?"*

It then quietly adjusts how much weight it gives each condition — giving more importance to the ones that predicted winners and less to the ones that led to losses. The adjustment is small (max 1.5% per week) so it learns gradually, not reactively.

Over time, the model gets calibrated to real market behavior — not just backtested guesses.

---

## What does the dashboard show?

The live dashboard at [tejasgjadhav.github.io/Trade-Intraday](https://tejasgjadhav.github.io/Trade-Intraday/) shows:

- Today's BUY signals with company name, entry price, target price, stop loss, and expected profit %
- A live scan log — every 5-minute check, what was found, and why
- Last week's performance review with signal-by-signal analysis
- Historical trade log with outcomes

---

## The goal in one sentence

> Buy the right Indian stock at the right time every trading day, exit before market close, never hold overnight, and get a little smarter every week — all without any human involvement.

---

> ⚠️ For educational and research purposes only. Not financial advice. Past performance does not guarantee future results.
