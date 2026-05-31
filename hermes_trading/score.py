#!/usr/bin/env python3
"""Score trades against the strategy goal."""

import logging

logger = logging.getLogger(__name__)


def score_trades(trades: list, goal: dict) -> float:
    """
    Score trades against goal [-1, +1].

    Args:
        trades: List of trade dictionaries
        goal: Goal configuration from state/goal.yaml

    Returns:
        Score in range [-1, +1] where:
            +1 = perfect performance
            0 = neutral
            -1 = terrible performance
    """
    if not trades:
        return 0.0

    # Weights for each component
    return_weight = 0.5
    drawdown_weight = 0.3
    sharpe_weight = 0.2

    # Calculate return component
    returns = []
    for trade in trades:
        outcome = trade.get("outcome", "")
        if "win" in outcome.lower():
            returns.append(0.5)
        elif "loss" in outcome.lower():
            returns.append(-0.5)

    avg_return = sum(returns) / len(returns) if returns else 0.0

    # Normalize return to [-1, +1] based on target
    target_return = goal.get("target_return_30d", 0.05)
    return_score = (avg_return / target_return) * return_weight

    # Calculate drawdown component
    max_dd = 0.0
    peak = 0.0
    for trade in trades:
        outcome = trade.get("outcome", "")
        if "win" in outcome.lower():
            peak += 0.5
        elif "loss" in outcome.lower():
            peak -= 0.5

        dd = (peak - 0.0) / (0.0 + 0.0001) if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    max_drawdown = goal.get("max_drawdown", 0.08)
    drawdown_score = -((max_dd / max_drawdown) * drawdown_weight)

    # Calculate Sharpe component
    sharpe = 0.0
    if returns and len(set(returns)) > 1:
        import numpy as np
        sharpe = np.mean(returns) / np.std(returns)

    min_sharpe = goal.get("min_sharpe", 1.0)
    sharpe_score = ((sharpe - min_sharpe) / 1.0) * sharpe_weight

    # Combine scores
    total_score = return_score + drawdown_score + sharpe_score

    # Clamp to [-1, +1]
    total_score = max(-1.0, min(1.0, total_score))

    logger.info(f"Trade score: {total_score:.3f}")
    logger.info(f"  Return: {return_score:.3f}, Drawdown: {drawdown_score:.3f}, Sharpe: {sharpe_score:.3f}")

    return total_score
