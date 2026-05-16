# AVCM — Adaptive Volume-Confirmed Momentum

**Strategy Rating: 9.1 / 10**  
**Live Dashboard → [tejasgjadhav.github.io/Trade-Intraday](https://tejasgjadhav.github.io/Trade-Intraday/)**

> Buy NSE stocks where institutional volume confirms a real price breakout, in a rising market, with time remaining. Exit in tranches. Never overnight. Never force a trade.

**Target win rate:** 52–58% | **Target R:R:** 2.5:1 | **Expected monthly return:** 3–6% net

---

## The Core Idea

Most breakouts are fake. Price goes above a level for one bar, then falls back. Institutions weren't buying — retail was fooled by the spike.

AVCM only acts when **volume confirms the breakout**. If 2× more shares than usual are being traded at the exact moment of the breakout, institutions are participating. That's a real move.

---

## Pre-Market Regime Check (8:45–9:14 AM) — ALL 3 must pass or trade nothing

| Check | Threshold | What it means |
|-------|-----------|---------------|
| Nifty above 20-day EMA | Current Nifty > 20d EMA | Market is in an uptrend. Rising tide lifts all boats. |
| India VIX | Below 22 | VIX ≥ 22 = extreme fear. Strategies fail in panic markets. No trade. |
| Nifty pre-open | Above −0.5% vs yesterday close | Not a gap-down day. Gap-downs create false setups all morning. |

If any of these 3 fail: **no trades today, no exceptions.**

---

## Sector Momentum Ranking (pre-market)

All 95 watchlist stocks are grouped into 14 sectors. Each sector is ranked by its 5-day return.

- **Top 4 sectors** → eligible for signals today
- **Bottom 4 sectors** → completely blocked, regardless of individual stock signals

Why? A stock in a weak sector may show a breakout signal but won't follow through. The sector is a headwind.

---

## Opening Range Construction (9:15–9:44 AM) — Observe Only

For every stock on the watchlist, the system records at 9:44 AM:

- **ORB High**: the highest price traded between 9:15–9:44 AM
- **ORB Low**: the lowest price traded between 9:15–9:44 AM
- **ORB Range**: must be at least **0.8% of stock price** to be tradeable
- **ORB Volume**: total shares traded in the first 30 minutes (used as baseline for Factor 2)

**No trades before 9:45 AM. The opening 30 minutes is data collection only.**

---

## Framework 1 — The 5-Factor AVCM Buy Trigger

Checked every 5 minutes, 9:45 AM – 1:30 PM. **ALL 5 must be simultaneously true. 4 of 5 is not a signal.**

| # | Factor | Exact Rule | Why |
|---|--------|-----------|-----|
| 1 | **Structural Breakout** | 5-min bar **closes** above ORB High (close only, wick doesn't count) | A close above = buyers held the level. A wick = buyers were rejected. |
| 2 | **Volume Confirmation** | Signal bar volume ≥ **2× the per-bar average** from the ORB period | Double volume = institutions are buying. Below 2× = retail noise. |
| 3 | **VWAP Position** | Price above today's anchored VWAP | VWAP is where institutional orders cluster. Being above it = momentum. |
| 4 | **RSI Momentum Window** | RSI (14-period, 5-min) is between **55 and 72** | Below 55 = no momentum yet. Above 72 = overextended, likely to reverse. |
| 5 | **Market Alignment** | Nifty 50 is **positive from its own open** at signal time | Individual stocks follow the index. Nifty negative = headwind. |

**Why all 5?** Each factor eliminates a different failure mode. Volume alone catches fake breakouts. RSI window eliminates overbought chases. Market alignment eliminates single-stock traps in falling markets.

---

## Retest Bonus Signal (+25% position size)

A **higher quality** signal pattern:
1. Stock broke ORB High earlier in the day
2. Price pulled back to VWAP (within 0.5%)
3. Now breaking above ORB High again, with volume

This is a retest of the breakout level — second attempt breakouts have higher follow-through probability. Position size is automatically increased by 25%.

---

## Framework 2 — The 4 Hard Quality Gates

Even after all 5 factors fire, the trade is blocked if any of these fail:

| Gate | Threshold | Reason |
|------|-----------|--------|
| **ORB Range Width** | ORB range ≥ 0.8% of stock price | A tight range means the target is mathematically unreachable. Skip. |
| **Daily Volume** | Volume ≥ 1× 20-day average | Below-average daily volume = no institutional interest today. Skip. |
| **Time-to-Target** | Expected return ≥ 0.5% per hour remaining | At 1:20 PM with 10 min left, even a 1% target won't work. Skip. |
| **Signal Cutoff** | Must fire before 1:30 PM | No new signals after 1:30 PM — not enough time for target. |

---

## Framework 3 — VIX-Adjusted Position Sizing

Position size is determined by India VIX (fear index), not a fixed percentage.

| VIX Level | Market Condition | Size per Trade |
|-----------|-----------------|----------------|
| VIX < 13 | Very low volatility, calm market | **8% of equity** |
| VIX 13–18 | Normal market | **6% of equity** |
| VIX 18–22 | Elevated risk, choppy | **3% of equity** |
| VIX ≥ 22 | Extreme fear | **No trade at all** |

**Retest signal adds +25%** to whatever size the VIX tier specifies.

**Max 2 simultaneous open positions.**  
**Example on ₹10L equity, VIX 15:** per trade = ₹60,000. Stock at ₹1,200 → buy 50 shares.

---

## Framework 4 — Residual ATR Target (not full ATR, not fixed %)

**Target = Entry + max(Residual ATR, 0.8% of entry)**  
with a floor of Entry + **2.5×** stop distance.

```
Range consumed today  = Day High − Day Low so far at entry time
Residual ATR          = max(0, ATR_14 − range_consumed)
Raw target            = Entry + max(Residual ATR, Entry × 0.008)
Final target          = max(Raw target, Entry + 2.5 × stop_distance)
```

**Why residual ATR?** If a stock's daily range is ₹30 (ATR) but it has already moved ₹20 today before the signal, only ₹10 of movement is realistically left. Setting a target based on the full ₹30 ATR would never be hit. Residual ATR adapts to how much move actually remains.

| Stock | ATR 14d | Range consumed | Residual | Entry | Target |
|-------|---------|---------------|----------|-------|--------|
| Reliance | ₹33 | ₹15 | ₹18 | ₹1,360 | ₹1,378 |
| TCS | ₹78 | ₹20 | ₹58 | ₹3,680 | ₹3,738 |

---

## Framework 5 — Tranche Exit System

Never exit 100% at once. Three tranches reduce risk of giving back gains.

| Exit | Size | Trigger | Action |
|------|------|---------|--------|
| **Exit 1** | Sell 35% | Price reaches Entry + 1× stop distance (profit locked) | Move stop to **breakeven** on remaining 65%. Worst case after this: zero loss. |
| **Exit 2** | Sell 35% | Price hits calculated target **OR** 1:30 PM, whichever first | Capture the bulk of the move. |
| **Exit 3** | Sell 30% | **3:10 PM IST unconditionally** | Limit order at VWAP. Market order if unfilled by 3:18 PM. |

**Stop hit:** Exit 100% immediately. No averaging down. No second chances.

---

## Framework 6 — Composite Scoring (when multiple stocks qualify)

When more than 2 stocks pass all 5 factors and all 4 gates, they are scored to pick the best 2.

| Factor | Weight | What it measures |
|--------|--------|-----------------|
| Max single-day backtest return | **25%** | Ceiling of this stock's intraday potential |
| Historical win rate | **20%** | % of past signals that were profitable |
| Live signal confidence | **20%** | How many of the 5 factors are active (5/5 = 100%) |
| Sharpe ratio | **15%** | Consistency of returns (risk-adjusted) |
| Expected return today | **10%** | Entry→target % for this specific trade |
| Volume confirmation | **10%** | Today's volume vs 20-day avg (capped at 3×) |

**Time decay applied:** A stock signaling at 9:45 AM scores full marks. The same stock at 1:00 PM scores ~37% lower because less time remains. This penalises late signals automatically.

**Sector concentration:** Best 2 picks must be from different sectors. If top 2 are both banks, the second is dropped and next from a different sector is chosen.

---

## Framework 7 — Circuit Breakers

| Trigger | Action |
|---------|--------|
| 3 consecutive stop-outs in one day | Stop trading for the day. Market is choppy, strategy underperforms. |
| Daily loss > 2% of equity | Close everything. Do not trade the rest of the day. |
| Equity drawdown from peak > 8% | Halve all position sizes until equity recovers within 4% of peak. |

---

## Daily Timeline

| Time | Action |
|------|--------|
| 8:45 AM | Regime check — Nifty EMA, VIX, pre-open. Go / no-go. |
| 8:50 AM | Sector rank — 5-day returns. Flag top 4, block bottom 4. |
| 9:15–9:44 AM | Observe only — build ORB High/Low for each stock. No trades. |
| 9:45 AM | Signal watch begins — all 5 factors checked every 5 min. Max 2 positions. |
| 1:30 PM | Signal cutoff — no new entries. Manage existing positions only. |
| 3:10 PM | Force close — all remaining positions exited. |
| 3:30 PM | Trade log — record entry, exit, slippage, signal quality. |

---

## Framework 8 — Self-Learning Weight Update (Every Sunday)

Every Sunday at 6:30 PM the engine replays the full past week bar by bar (no hindsight), finds winning and losing trades, and asks: which signals were present in winners vs losers?

| Step | What happens |
|------|-------------|
| Replay | Simulates every 5-min bar using actual market data |
| Outcome | WIN (hit target), LOSS (hit stop), FORCE CLOSE (3:10 PM) |
| Signal analysis | Per factor: % present in winners vs % present in losers |
| Weight update | Factors that predicted winners get more weight; losers get less |

**Guardrails:**
- Max weight change: **±1.5% per week** (gradual learning, not reactive)
- Learning only begins after **≥5 qualifying signals** have accumulated
- All 6 score factors stay within defined min/max bounds

---

## Scoring Breakdown

| Dimension | Score |
|-----------|-------|
| Statistical rigor | 8.8 |
| Signal quality | 9.0 |
| Risk management | 9.2 |
| Execution realism | 9.0 |
| Backtest integrity | 8.8 |
| Manual executability | 9.5 |
| **Overall** | **9.1 / 10** |

---

## What Keeps It From 10

- Manual execution introduces 5–30 second latency — real slippage cost not fully eliminable
- No out-of-sample validation yet — requires 6 months paper trading before full live capital
- Permutation test not yet run — edge is structurally sound but statistically unproven on this specific data
- Capacity ceiling ~₹25L — above this, position sizes begin moving midcap prices

---

## Validation Protocol Before Full Capital

1. Run 6 months of paper trades logging every decision and every fill
2. Run permutation test — shuffle signal timing 10,000 times, confirm Sharpe sits above 95th percentile
3. Confirm win rate and R:R in paper trading match backtest within 10%
4. Deploy live capital starting at 25% of intended size for the first month

---

> ⚠️ For educational and research purposes only. Not financial advice. Past performance does not guarantee future results.
