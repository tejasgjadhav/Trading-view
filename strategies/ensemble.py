"""
Ensemble Strategy — The Master Signal
─────────────────────────────────────────────────────────────────────────────
Combines all 5 strategies with weighted scoring. The ensemble approach is used
by Renaissance Technologies, Two Sigma, and other top quant funds —
no single strategy is best in all conditions, but the ensemble is more robust.

Weighting:
  Each strategy contributes a score (-1 to +1)
  Weighted sum → final score
  BUY  if score ≥ ENSEMBLE_BUY_THRESHOLD
  SELL if score ≤ ENSEMBLE_SELL_THRESHOLD
"""

import pandas as pd
import numpy as np
from typing import List, Dict

from .turtle_trading import TurtleStrategy
from .ma_crossover import MACrossoverStrategy
from .momentum_rsi import MomentumRSIStrategy
from .breakout_volume import BreakoutVolumeStrategy
from .mean_reversion import MeanReversionStrategy
from config import STRATEGY_WEIGHTS, ENSEMBLE_BUY_THRESHOLD, ENSEMBLE_SELL_THRESHOLD


class EnsembleStrategy:
    name = "Ensemble (Renaissance / Quant Style)"
    short_name = "ensemble"

    def __init__(self):
        self.strategies = {
            "turtle":           TurtleStrategy(),
            "ma_crossover":     MACrossoverStrategy(),
            "momentum_rsi":     MomentumRSIStrategy(),
            "breakout_volume":  BreakoutVolumeStrategy(),
            "mean_reversion":   MeanReversionStrategy(),
        }
        self.weights = STRATEGY_WEIGHTS

    def get_signal(self, df: pd.DataFrame) -> Dict:
        """
        Get weighted ensemble signal for a given ticker dataframe.
        Returns dict with final signal, composite score, and per-strategy breakdown.
        """
        results = {}
        weighted_score = 0.0
        total_weight = 0.0

        for name, strategy in self.strategies.items():
            try:
                sig = strategy.get_signal(df)
                results[name] = sig
                weight = self.weights.get(name, 0.2)
                weighted_score += sig["score"] * weight
                total_weight += weight
            except Exception as e:
                results[name] = {"strategy": name, "signal": 0, "score": 0.0, "error": str(e)}

        if total_weight > 0:
            weighted_score /= total_weight

        # Final signal decision
        if weighted_score >= ENSEMBLE_BUY_THRESHOLD:
            final_signal = 1
            action = "BUY"
        elif weighted_score <= ENSEMBLE_SELL_THRESHOLD:
            final_signal = -1
            action = "SELL"
        else:
            final_signal = 0
            action = "HOLD"

        # Confidence: how many strategies agree
        signals = [r.get("signal", 0) for r in results.values()]
        buy_votes = sum(1 for s in signals if s == 1)
        sell_votes = sum(1 for s in signals if s == -1)
        total_votes = len(signals)

        if final_signal == 1:
            confidence = buy_votes / total_votes
        elif final_signal == -1:
            confidence = sell_votes / total_votes
        else:
            confidence = max(buy_votes, sell_votes) / total_votes

        return {
            "action": action,
            "signal": final_signal,
            "score": round(weighted_score, 4),
            "confidence": round(confidence, 2),
            "buy_votes": buy_votes,
            "sell_votes": sell_votes,
            "hold_votes": total_votes - buy_votes - sell_votes,
            "strategies": results,
        }

    def get_batch_signals(self, tickers_data: Dict[str, pd.DataFrame]) -> List[Dict]:
        """Get ensemble signals for multiple tickers, sorted by score."""
        signals = []
        for ticker, df in tickers_data.items():
            try:
                sig = self.get_signal(df)
                sig["ticker"] = ticker
                signals.append(sig)
            except Exception as e:
                signals.append({
                    "ticker": ticker,
                    "action": "ERROR",
                    "signal": 0,
                    "score": 0.0,
                    "confidence": 0.0,
                    "error": str(e),
                })

        # Sort by score descending (best buys first)
        signals.sort(key=lambda x: x["score"], reverse=True)
        return signals
