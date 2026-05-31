#!/usr/bin/env python3
"""Entry point for the Hermes trading worker."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add the project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from hermes_trading.loop import TradingLoop
from hermes_trading.reflect import ReflectionCycle


def load_goal() -> dict:
    """Load the strategy goal from state/goal.yaml."""
    goal_path = PROJECT_ROOT / "state" / "goal.yaml"
    import yaml
    with open(goal_path) as f:
        return yaml.safe_load(f)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Hermes Trading Agent")
    parser.add_argument(
        "--asset",
        type=str,
        default=None,
        help="Override asset from goal.yaml (e.g., BTC/USDT)"
    )
    args = parser.parse_args()

    goal = load_goal()
    asset = args.asset or goal["asset"]

    print(f"🤖 Hermes Trading Agent started")
    print(f"   Asset: {asset}")
    print(f"   Mode: {os.getenv('HERMES_TRADING_MODE', 'paper')}")
    print(f"   PID: {os.getpid()}")

    # Initialize the trading loop
    loop = TradingLoop(asset=asset)

    try:
        # Start the 24/7 reliability loop
        await loop.run_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
