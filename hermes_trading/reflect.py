#!/usr/bin/env python3
"""Reflection cycle for the trading agent."""

import argparse
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import yaml
from httpx import AsyncClient, HTTPError

from hermes_trading.score import score_trades

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.getenv("HERMES_LOG_FILE", "hermes.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ReflectionCycle:
    """Handles reflection on trade outcomes and strategy evolution."""

    def __init__(self):
        self.trades_file = Path("state/trades.jsonl")
        self.strategy_path = Path("state/strategy.yaml")
        self.hypotheses_file = Path("state/hypotheses.jsonl")
        self.history_dir = Path("state/history")

    def _load_trades(self, n: int = 25) -> list:
        """Load the last n trades."""
        trades = []
        if not self.trades_file.exists():
            return trades

        with open(self.trades_file) as f:
            for line in f:
                if line.strip():
                    trades.append(json.loads(line))

        return trades[-n:]  # Return last n

    def _load_strategy(self) -> dict:
        """Load the current strategy."""
        with open(self.strategy_path) as f:
            return yaml.safe_load(f)

    def _score_trades(self, trades: list, goal: dict) -> list:
        """Score each trade against the goal."""
        return [
            score_trades([trade], goal)
            for trade in trades
        ]

    def _get_avg_return(self, trades: list) -> float:
        """Calculate average return of trades."""
        returns = []
        for trade in trades:
            outcome = trade.get("outcome", "")
            if "win" in outcome.lower():
                returns.append(0.5)  # Positive return
            elif "loss" in outcome.lower():
                returns.append(-0.5)  # Negative return

        if not returns:
            return 0.0

        return sum(returns) / len(returns)

    def _get_current_drawdown(self, trades: list) -> float:
        """Calculate current drawdown."""
        if len(trades) < 2:
            return 0.0

        # Simple cumulative drawdown
        peak = 0.0
        max_dd = 0.0

        for trade in trades:
            outcome = trade.get("outcome", "")
            if "win" in outcome.lower():
                peak += 0.5
            elif "loss" in outcome.lower():
                peak -= 0.5

            drawdown = (peak - 0.0) / (0.0 + 0.0001) if peak > 0 else 0.0
            max_dd = max(max_dd, drawdown)

        return max_dd

    def _get_sharpe(self, trades: list) -> float:
        """Calculate Sharpe ratio."""
        returns = []
        for trade in trades:
            outcome = trade.get("outcome", "")
            if "win" in outcome.lower():
                returns.append(0.05)  # 5% return
            elif "loss" in outcome.lower():
                returns.append(-0.05)  # 5% loss

        if not returns or len(set(returns)) == 1:
            return 0.0

        import statistics
        import numpy as np

        return np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0.0

    async def run_fallback(self):
        """Run deterministic fallback reflection (Phase 5)."""
        goal = yaml.safe_load(open(Path("state/goal.yaml")))

        trades = self._load_trades(25)
        strategy = self._load_strategy()

        avg_return = self._get_avg_return(trades)
        current_drawdown = self._get_current_drawdown(trades)
        sharpe = self._get_sharpe(trades)

        # Reflection rules
        reasons = []
        changed = False

        # Check if we should loosen entry threshold
        target_return = goal.get("target_return_30d", 0.05)
        if avg_return < target_return:
            strategy["entry"]["threshold"] = max(strategy["entry"]["threshold"] - 2, 10)
            changed = True
            reasons.append(f"Average return ({avg_return:.2%}) below target ({target_return:.2%}), loosening entry threshold")

        # Check if we should tighten stop loss
        max_drawdown = goal.get("max_drawdown", 0.08)
        if current_drawdown > max_drawdown:
            strategy["stop_loss_pct"] = max(strategy["stop_loss_pct"] - 0.2, 1.0)
            changed = True
            reasons.append(f"Drawdown ({current_drawdown:.2%}) above max ({max_drawdown:.2%}), tightening stop loss")

        # Check if we should tighten position size
        if sharpe < goal.get("min_sharpe", 1.0):
            strategy["position_size_r"] = max(strategy["position_size_r"] - 0.1, 0.1)
            changed = True
            reasons.append(f"Sharpe ({sharpe:.2f}) below min ({goal.get('min_sharpe', 1.0):.2f}), reducing position size")

        # Save hypothesis
        if changed:
            new_version = self._bump_version(strategy["version"])

            # Save prior version
            self.history_dir.mkdir(exist_ok=True)
            prior_path = self.history_dir / f"v{new_version}.yaml"
            with open(prior_path, "w") as f:
                yaml.dump(strategy, f)

            # Update strategy
            strategy["version"] = new_version

            with open(self.strategy_path, "w") as f:
                yaml.dump(strategy, f)

            # Write hypothesis
            hypothesis = {
                "timestamp": datetime.now().isoformat(),
                "version_from": new_version,
                "version_to": new_version,
                "reason": " ".join(reasons),
                "rule": "deterministic_fallback"
            }

            with open(self.hypotheses_file, "a") as f:
                f.write(json.dumps(hypothesis) + "\n")

            logger.info(f"✓ Strategy evolved: v{new_version}")
            logger.info(f"   Changes: {', '.join(reasons)}")
        else:
            logger.info("No changes needed based on outcomes")

    def _bump_version(self, version: str) -> str:
        """Bump strategy version."""
        try:
            major, minor = version.split(".")
            return f"{major}.{int(minor) + 1:02d}"
        except:
            return "01"


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Hermes Reflection Cycle")
    parser.add_argument(
        "--fallback",
        action="store_true",
        help="Run deterministic fallback (used before Hermes)"
    )
    parser.add_argument(
        "--hermes",
        action="store_true",
        help="Run Hermes-based reflection (production mode)"
    )

    args = parser.parse_args()

    if not args.fallback and not args.hermes:
        parser.print_help()
        return

    reflection = ReflectionCycle()

    if args.fallback:
        await reflection.run_fallback()
    elif args.hermes:
        await reflection.run_hermes()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
