"""
Trading Strategy System — Main Entry Point
─────────────────────────────────────────────────────────────────────────────
Usage:
  python main.py signals          → Generate today's signals (default)
  python main.py backtest         → Run full backtest on all strategies
  python main.py backtest AAPL    → Backtest specific ticker
  python main.py report           → Generate markdown report
  python main.py summary          → Show performance summary
"""

import sys
import os
import json
from datetime import date, datetime

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_signals():
    from live.signal_generator import generate_daily_signals, fetch_data, enrich_signals, update_open_positions
    from strategies import EnsembleStrategy
    from tracking import TradeLogger
    from config import WATCHLIST, BACKTEST_PERIOD_YEARS

    logger = TradeLogger()
    data = fetch_data(WATCHLIST, period_years=BACKTEST_PERIOD_YEARS)

    update_open_positions(logger, data)

    ensemble = EnsembleStrategy()
    signals = ensemble.get_batch_signals(data)
    signals = enrich_signals(signals, data)

    for sig in signals:
        if sig.get("action") in ("BUY", "SELL"):
            logger.log_signal(sig)

    prices = {t: float(df.iloc[-1]["Close"]) for t, df in data.items()}
    logger.log_daily_performance(signals, prices)

    os.makedirs("results", exist_ok=True)
    with open("results/latest_signals.json", "w") as f:
        json.dump({
            "date": str(date.today()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "signals": signals,
        }, f, indent=2, default=str)

    run_report()
    return signals


def run_backtest(ticker: str = None):
    import yfinance as yf
    import pandas as pd
    from strategies import TurtleStrategy, MACrossoverStrategy, MomentumRSIStrategy, BreakoutVolumeStrategy, MeanReversionStrategy
    from backtest import BacktestEngine, compute_metrics
    from backtest.metrics import format_metrics_table
    from config import WATCHLIST, BACKTEST_PERIOD_YEARS

    tickers = [ticker] if ticker else WATCHLIST[:10]  # limit for speed
    all_results = {}

    strategies = {
        "turtle":           TurtleStrategy(),
        "ma_crossover":     MACrossoverStrategy(),
        "momentum_rsi":     MomentumRSIStrategy(),
        "breakout_volume":  BreakoutVolumeStrategy(),
        "mean_reversion":   MeanReversionStrategy(),
    }

    engine = BacktestEngine()

    print(f"\n{'='*60}")
    print(f"  BACKTESTING — {BACKTEST_PERIOD_YEARS}y historical | {len(tickers)} tickers")
    print(f"{'='*60}\n")

    for tick in tickers:
        print(f"\n[{tick}] Downloading data...")
        df = yf.download(tick, period=f"{BACKTEST_PERIOD_YEARS}y", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if len(df) < 100:
            print(f"  Insufficient data, skipping.")
            continue

        all_results[tick] = {}

        for strat_name, strategy in strategies.items():
            try:
                sigs = strategy.compute_signals(df)
                result = engine.run(df, sigs["signal"])
                metrics = compute_metrics(result)
                all_results[tick][strat_name] = metrics

                print(f"  {strat_name:<20} → "
                      f"Return: {metrics['total_return_pct']:+.1f}% | "
                      f"Sharpe: {metrics['sharpe_ratio']:.2f} | "
                      f"MaxDD: {metrics['max_drawdown_pct']:.1f}% | "
                      f"WinRate: {metrics['win_rate_pct']:.0f}%")
            except Exception as e:
                print(f"  {strat_name:<20} → ERROR: {e}")

    # Save results
    os.makedirs("results", exist_ok=True)
    with open("results/backtest_results.json", "w") as f:
        json.dump({
            "run_date": str(date.today()),
            "period_years": BACKTEST_PERIOD_YEARS,
            "tickers": tickers,
            "results": all_results,
        }, f, indent=2, default=str)

    print(f"\n[DONE] Results saved to results/backtest_results.json")
    return all_results


def run_report():
    """Generate markdown report from latest signals and performance."""
    from tracking import TradeLogger
    from config import STRATEGY_WEIGHTS

    logger = TradeLogger()
    summary = logger.get_performance_summary()
    recent = logger.get_recent_calls(n=15)
    open_pos = logger.get_open_positions()

    today = str(date.today())

    # Load latest signals
    signals_data = {}
    if os.path.exists("results/latest_signals.json"):
        with open("results/latest_signals.json") as f:
            signals_data = json.load(f)

    signals = signals_data.get("signals", [])
    buys = [s for s in signals if s.get("action") == "BUY"]
    sells = [s for s in signals if s.get("action") == "SELL"]

    lines = [
        f"# Trading Signals — {today}",
        f"> Auto-generated by 5-Strategy Ensemble | Inspired by world's top traders",
        f"",
        f"## Today's Signals",
        f"",
        f"Generated: `{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}`",
        f"",
    ]

    if buys:
        lines += [f"### BUY Signals ({len(buys)})", ""]
        lines += ["| Ticker | Score | Conf | Price | ATR% | 52W-High% | Votes |", "|--------|-------|------|-------|------|-----------|-------|"]
        for s in buys:
            lines.append(
                f"| **{s['ticker']}** | {s['score']:+.3f} | {s.get('confidence', 0):.0%} | "
                f"${s.get('price', 0):.2f} | {s.get('atr_pct', 0):.1f}% | "
                f"{s.get('pct_from_52w_high', 0):+.1f}% | "
                f"{s.get('buy_votes', 0)}/{s.get('buy_votes', 0) + s.get('sell_votes', 0) + s.get('hold_votes', 0)} |"
            )
        lines.append("")

    if sells:
        lines += [f"### SELL Signals ({len(sells)})", ""]
        lines += ["| Ticker | Score | Price |", "|--------|-------|-------|"]
        for s in sells:
            lines.append(f"| **{s['ticker']}** | {s['score']:+.3f} | ${s.get('price', 0):.2f} |")
        lines.append("")

    if open_pos:
        lines += ["## Open Positions", ""]
        for pos in open_pos:
            lines.append(f"- `{pos}`")
        lines.append("")

    if summary:
        lines += [
            "## Performance Tracker",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Calls | {summary.get('total_calls', 0)} |",
            f"| Closed Trades | {summary.get('closed_trades', 0)} |",
            f"| Win Rate | {summary.get('win_rate_pct', 0):.1f}% |",
            f"| Avg Return | {summary.get('avg_return_pct', 0):+.2f}% |",
            f"| Profit Factor | {summary.get('profit_factor', 0):.2f} |",
            f"| Best Trade | {summary.get('best_trade_pct', 0):+.1f}% |",
            f"| Worst Trade | {summary.get('worst_trade_pct', 0):+.1f}% |",
            "",
        ]

    if recent:
        lines += ["## Recent Calls", ""]
        lines += ["| Date | Ticker | Action | Score | Price | P&L | Status |", "|------|--------|--------|-------|-------|-----|--------|"]
        for call in recent[:10]:
            pnl = f"{call.get('pnl_pct', 0):+.1f}%" if call.get('pnl_pct') is not None else "—"
            lines.append(
                f"| {call['date']} | `{call['ticker']}` | **{call['action']}** | "
                f"{call['score']:+.3f} | ${call.get('price_at_signal') or '—'} | {pnl} | {call['status']} |"
            )
        lines.append("")

    lines += [
        "## Strategies",
        "",
        "| Strategy | Inspired By | Weight |",
        "|----------|-------------|--------|",
        "| Turtle Trading | Richard Dennis / William Eckhardt | 25% |",
        "| MA Crossover | Paul Tudor Jones / Stanley Druckenmiller | 20% |",
        "| Momentum + RSI | Jesse Livermore | 25% |",
        "| Breakout + Volume | Jesse Livermore | 15% |",
        "| Mean Reversion | Ray Dalio / George Soros | 15% |",
        "",
        "---",
        f"*This is for educational purposes. Not financial advice.*",
        f"*Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*",
    ]

    report = "\n".join(lines)
    os.makedirs("reports", exist_ok=True)
    with open("reports/daily_report.md", "w") as f:
        f.write(report)

    # Also update README
    with open("README.md", "w") as f:
        f.write(report)

    print(f"[REPORT] Generated reports/daily_report.md and README.md")
    return report


def run_summary():
    from tracking import TradeLogger
    logger = TradeLogger()
    summary = logger.get_performance_summary()
    recent = logger.get_recent_calls(20)

    print("\n[PERFORMANCE SUMMARY]")
    print("=" * 50)
    for k, v in summary.items():
        if k != "last_updated":
            print(f"  {k:<25} {v}")

    print("\n[RECENT CALLS]")
    print("-" * 50)
    for call in recent[:10]:
        pnl = f"{call.get('pnl_pct', 0):+.2f}%" if call.get('pnl_pct') is not None else "pending"
        print(f"  {call['date']} | {call['ticker']:<6} | {call['action']:<4} | "
              f"score={call['score']:+.3f} | {pnl} | {call['status']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "signals"

    if cmd == "signals":
        run_signals()
    elif cmd == "backtest":
        ticker = sys.argv[2] if len(sys.argv) > 2 else None
        run_backtest(ticker)
    elif cmd == "report":
        run_report()
    elif cmd == "summary":
        run_summary()
    else:
        print(__doc__)
        sys.exit(1)
