"""
Trade Logger — Self-Tracking System
─────────────────────────────────────────────────────────────────────────────
Every signal generated is logged with full metadata.
Actual prices are recorded at signal time AND next-day open (for realistic fill).
Tracks: signals, fills, P&L, running performance, regime.
"""

import json
import os
from datetime import datetime, date
from typing import Dict, List, Optional
import pandas as pd


TRADE_LOG_PATH = "data/trade_log.json"
PERFORMANCE_LOG_PATH = "data/performance_log.json"


class TradeLogger:
    def __init__(
        self,
        trade_log_path: str = TRADE_LOG_PATH,
        performance_log_path: str = PERFORMANCE_LOG_PATH,
    ):
        self.trade_log_path = trade_log_path
        self.performance_log_path = performance_log_path
        self._ensure_files()

    def _ensure_files(self):
        os.makedirs(os.path.dirname(self.trade_log_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.performance_log_path), exist_ok=True)
        for path, default in [
            (self.trade_log_path, {"calls": [], "open_positions": {}, "summary": {}}),
            (self.performance_log_path, {"daily": [], "overall": {}}),
        ]:
            if not os.path.exists(path):
                with open(path, "w") as f:
                    json.dump(default, f, indent=2)

    def _load(self, path: str) -> dict:
        with open(path, "r") as f:
            return json.load(f)

    def _save(self, path: str, data: dict):
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    # ─── Signal Logging ───────────────────────────────────────────────────────

    def log_signal(self, signal: Dict) -> str:
        """Log a new signal call. Returns call_id."""
        log = self._load(self.trade_log_path)
        call_id = f"{signal['ticker']}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        entry = {
            "call_id": call_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "date": str(date.today()),
            "ticker": signal["ticker"],
            "action": signal["action"],           # BUY / SELL / HOLD
            "signal": signal["signal"],            # 1 / -1 / 0
            "score": signal["score"],
            "confidence": signal.get("confidence", 0),
            "buy_votes": signal.get("buy_votes", 0),
            "sell_votes": signal.get("sell_votes", 0),
            "price_at_signal": signal.get("price", None),
            "strategy_breakdown": {
                k: {"signal": v.get("signal"), "score": v.get("score")}
                for k, v in signal.get("strategies", {}).items()
            },
            "status": "open" if signal["action"] == "BUY" else "signal",
            "entry_price": None,
            "exit_price": None,
            "exit_date": None,
            "pnl_pct": None,
            "result": "pending",
        }

        log["calls"].append(entry)

        # Track open positions
        if signal["action"] == "BUY":
            log["open_positions"][signal["ticker"]] = call_id

        self._save(self.trade_log_path, log)
        return call_id

    def log_fill(self, ticker: str, fill_price: float, fill_type: str = "entry"):
        """Record when a position is actually filled (next-day open)."""
        log = self._load(self.trade_log_path)

        call_id = log["open_positions"].get(ticker)
        if not call_id:
            return

        for call in log["calls"]:
            if call["call_id"] == call_id:
                if fill_type == "entry":
                    call["entry_price"] = fill_price
                    call["status"] = "filled"
                elif fill_type == "exit":
                    call["exit_price"] = fill_price
                    call["exit_date"] = str(date.today())
                    if call["entry_price"]:
                        call["pnl_pct"] = round(
                            (fill_price / call["entry_price"] - 1) * 100, 2
                        )
                        call["result"] = "win" if call["pnl_pct"] > 0 else "loss"
                    call["status"] = "closed"
                    if ticker in log["open_positions"]:
                        del log["open_positions"][ticker]
                break

        self._save(self.trade_log_path, log)

    def log_exit(self, ticker: str, exit_price: float, reason: str = "signal"):
        """Close a position."""
        log = self._load(self.trade_log_path)
        call_id = log["open_positions"].get(ticker)
        if not call_id:
            return

        for call in log["calls"]:
            if call["call_id"] == call_id:
                call["exit_price"] = exit_price
                call["exit_date"] = str(date.today())
                call["exit_reason"] = reason
                if call.get("entry_price"):
                    call["pnl_pct"] = round(
                        (exit_price / call["entry_price"] - 1) * 100, 2
                    )
                    call["result"] = "win" if call["pnl_pct"] > 0 else "loss"
                call["status"] = "closed"
                break

        if ticker in log["open_positions"]:
            del log["open_positions"][ticker]

        self._save(self.trade_log_path, log)
        self._update_summary(log)

    # ─── Performance Tracking ─────────────────────────────────────────────────

    def _update_summary(self, log: dict):
        closed = [c for c in log["calls"] if c["status"] == "closed" and c["pnl_pct"] is not None]
        if not closed:
            log["summary"] = {}
            self._save(self.trade_log_path, log)
            return

        pnls = [c["pnl_pct"] for c in closed]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]

        log["summary"] = {
            "total_calls": len(log["calls"]),
            "closed_trades": len(closed),
            "open_positions": len(log["open_positions"]),
            "win_rate_pct": round(len(winners) / len(closed) * 100, 1),
            "avg_return_pct": round(sum(pnls) / len(pnls), 2),
            "total_return_pct": round(sum(pnls), 2),
            "best_trade_pct": round(max(pnls), 2),
            "worst_trade_pct": round(min(pnls), 2),
            "avg_win_pct": round(sum(winners) / len(winners), 2) if winners else 0,
            "avg_loss_pct": round(sum(losers) / len(losers), 2) if losers else 0,
            "profit_factor": round(
                sum(winners) / abs(sum(losers)), 2
            ) if losers and sum(losers) != 0 else float("inf"),
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }
        self._save(self.trade_log_path, log)

    def log_daily_performance(self, signals: List[Dict], prices: Dict[str, float]):
        """Log end-of-day performance snapshot."""
        perf = self._load(self.performance_log_path)
        log = self._load(self.trade_log_path)

        daily_entry = {
            "date": str(date.today()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "signals_generated": len(signals),
            "buy_signals": sum(1 for s in signals if s.get("action") == "BUY"),
            "sell_signals": sum(1 for s in signals if s.get("action") == "SELL"),
            "hold_signals": sum(1 for s in signals if s.get("action") == "HOLD"),
            "open_positions": len(log.get("open_positions", {})),
            "summary": log.get("summary", {}),
        }

        perf["daily"].append(daily_entry)
        perf["overall"] = log.get("summary", {})
        self._save(self.performance_log_path, perf)

    # ─── Reporting ────────────────────────────────────────────────────────────

    def get_open_positions(self) -> List[str]:
        log = self._load(self.trade_log_path)
        return list(log.get("open_positions", {}).keys())

    def get_performance_summary(self) -> dict:
        log = self._load(self.trade_log_path)
        return log.get("summary", {})

    def get_recent_calls(self, n: int = 20) -> List[Dict]:
        log = self._load(self.trade_log_path)
        calls = log.get("calls", [])
        return sorted(calls, key=lambda x: x["timestamp"], reverse=True)[:n]
