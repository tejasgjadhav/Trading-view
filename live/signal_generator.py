"""
Live Signal Generator
─────────────────────────────────────────────────────────────────────────────
Downloads fresh market data and generates today's trading signals.
Designed to run daily via GitHub Actions (pre-market, 9am ET).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from datetime import datetime, date
from typing import Dict, List

import yfinance as yf
import pandas as pd
import numpy as np

from config import WATCHLIST, BACKTEST_PERIOD_YEARS
from strategies import EnsembleStrategy
from tracking import TradeLogger


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex columns from yfinance (newer versions return Price/Ticker multi-index)."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def fetch_data(tickers: List[str], period_years: int = 2) -> Dict[str, pd.DataFrame]:
    """Download OHLCV data for all tickers."""
    print(f"[DATA] Fetching {len(tickers)} tickers from Yahoo Finance...")
    data = {}
    for ticker in tickers:
        try:
            df = yf.download(ticker, period=f"{period_years}y", auto_adjust=True, progress=False)
            df = _flatten_columns(df)
            if len(df) > 100:
                data[ticker] = df
                print(f"  ✓ {ticker}: {len(df)} bars")
            else:
                print(f"  ✗ {ticker}: insufficient data ({len(df)} bars)")
        except Exception as e:
            print(f"  ✗ {ticker}: {e}")
    return data


def enrich_signals(signals: List[Dict], data: Dict[str, pd.DataFrame]) -> List[Dict]:
    """Add current price, volume, and market context to each signal."""
    for sig in signals:
        ticker = sig["ticker"]
        if ticker in data:
            df = data[ticker]
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else df.iloc[-1]

            sig["price"] = round(float(latest["Close"]), 2)
            sig["volume"] = int(latest["Volume"])
            sig["change_pct"] = round(float((latest["Close"] / prev["Close"] - 1) * 100), 2)

            # 52-week context
            year_high = float(df["High"].rolling(252).max().iloc[-1])
            year_low = float(df["Low"].rolling(252).min().iloc[-1])
            sig["52w_high"] = round(year_high, 2)
            sig["52w_low"] = round(year_low, 2)
            sig["pct_from_52w_high"] = round((latest["Close"] / year_high - 1) * 100, 1)

            # ATR for position sizing suggestion
            tr = pd.concat([
                df["High"] - df["Low"],
                abs(df["High"] - df["Close"].shift(1)),
                abs(df["Low"] - df["Close"].shift(1)),
            ], axis=1).max(axis=1)
            atr = float(tr.rolling(14).mean().iloc[-1])
            sig["atr"] = round(atr, 2)
            sig["atr_pct"] = round(atr / float(latest["Close"]) * 100, 1)

    return signals


def generate_daily_signals(tickers: List[str] = None) -> List[Dict]:
    """
    Main function: generate today's trading signals.
    Returns list of signals sorted by score (best opportunities first).
    """
    if tickers is None:
        tickers = WATCHLIST

    today = str(date.today())
    print(f"\n{'='*60}")
    print(f"  TRADING SIGNAL ENGINE — {today}")
    print(f"  Ensemble of 5 Elite Strategies")
    print(f"{'='*60}\n")

    # 1. Fetch data
    data = fetch_data(tickers, period_years=BACKTEST_PERIOD_YEARS)
    if not data:
        print("[ERROR] No data fetched!")
        return []

    # 2. Generate ensemble signals
    ensemble = EnsembleStrategy()
    print(f"\n[SIGNALS] Analyzing {len(data)} tickers...")
    signals = ensemble.get_batch_signals(data)

    # 3. Enrich with market data
    signals = enrich_signals(signals, data)

    # 4. Filter and categorize
    buys = [s for s in signals if s.get("action") == "BUY"]
    sells = [s for s in signals if s.get("action") == "SELL"]
    holds = [s for s in signals if s.get("action") == "HOLD"]

    print(f"\n[RESULTS] {len(buys)} BUY | {len(sells)} SELL | {len(holds)} HOLD\n")

    # 5. Print top signals
    print("TOP BUY SIGNALS:")
    print("-" * 60)
    for sig in buys[:5]:
        print(f"  {sig['ticker']:<6} Score: {sig['score']:+.3f} | Conf: {sig['confidence']:.0%} | "
              f"Price: ${sig.get('price', 0):.2f} | ATR: {sig.get('atr_pct', 0):.1f}%")
        for strat, details in sig.get("strategies", {}).items():
            arrow = "▲" if details.get("signal", 0) > 0 else ("▼" if details.get("signal", 0) < 0 else "─")
            print(f"    {arrow} {strat:<20} score: {details.get('score', 0):+.3f}")
        print()

    if sells:
        print("\nSELL SIGNALS:")
        print("-" * 60)
        for sig in sells[:3]:
            print(f"  {sig['ticker']:<6} Score: {sig['score']:+.3f} | Price: ${sig.get('price', 0):.2f}")

    return signals


def update_open_positions(logger: TradeLogger, data: Dict[str, pd.DataFrame]):
    """Check open positions against stop-loss / take-profit."""
    from config import STOP_LOSS_PCT, TAKE_PROFIT_PCT

    open_tickers = logger.get_open_positions()
    if not open_tickers:
        return

    print(f"\n[POSITIONS] Monitoring {len(open_tickers)} open positions...")
    log_data = json.load(open("data/trade_log.json"))

    for ticker in open_tickers:
        if ticker not in data:
            continue
        df = data[ticker]
        current_price = float(df.iloc[-1]["Close"])

        # Find entry price
        call_id = log_data["open_positions"].get(ticker)
        for call in log_data["calls"]:
            if call["call_id"] == call_id and call.get("entry_price"):
                entry_price = call["entry_price"]
                pnl_pct = (current_price / entry_price - 1) * 100

                print(f"  {ticker}: Entry ${entry_price:.2f} → Current ${current_price:.2f} "
                      f"({pnl_pct:+.1f}%)")

                # Check stops
                if pnl_pct <= -STOP_LOSS_PCT * 100:
                    print(f"    ⚠ STOP LOSS triggered!")
                    logger.log_exit(ticker, current_price, reason="stop_loss")
                elif pnl_pct >= TAKE_PROFIT_PCT * 100:
                    print(f"    ✓ TAKE PROFIT hit!")
                    logger.log_exit(ticker, current_price, reason="take_profit")
                break


if __name__ == "__main__":
    # Initialize logger
    logger = TradeLogger()

    # Fetch data
    data = fetch_data(WATCHLIST, period_years=BACKTEST_PERIOD_YEARS)

    # Check existing positions
    update_open_positions(logger, data)

    # Generate new signals
    ensemble = EnsembleStrategy()
    signals = ensemble.get_batch_signals(data)
    signals = enrich_signals(signals, data)

    # Log all signals
    for sig in signals:
        if sig.get("action") in ("BUY", "SELL"):
            logger.log_signal(sig)

    # Log daily performance
    prices = {
        ticker: float(df.iloc[-1]["Close"])
        for ticker, df in data.items()
    }
    logger.log_daily_performance(signals, prices)

    # Print summary
    summary = logger.get_performance_summary()
    if summary:
        print("\n[PERFORMANCE TRACKER]")
        print(f"  Total calls:   {summary.get('total_calls', 0)}")
        print(f"  Closed trades: {summary.get('closed_trades', 0)}")
        print(f"  Win rate:      {summary.get('win_rate_pct', 0)}%")
        print(f"  Avg return:    {summary.get('avg_return_pct', 0):+.2f}%")
        print(f"  Profit factor: {summary.get('profit_factor', 0):.2f}")

    # Save signals to file for report generation
    os.makedirs("results", exist_ok=True)
    with open("results/latest_signals.json", "w") as f:
        json.dump({
            "date": str(date.today()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "signals": signals,
            "summary": {
                "buys": sum(1 for s in signals if s.get("action") == "BUY"),
                "sells": sum(1 for s in signals if s.get("action") == "SELL"),
                "holds": sum(1 for s in signals if s.get("action") == "HOLD"),
            }
        }, f, indent=2, default=str)

    print("\n[DONE] Signals saved to results/latest_signals.json")
