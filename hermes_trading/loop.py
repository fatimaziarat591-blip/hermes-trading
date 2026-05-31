#!/usr/bin/env python3
"""24/7 reliability loop for the trading agent."""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

import yaml
from httpx import AsyncClient, HTTPError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from hermes_trading.adapters.price import PriceAdapter
from hermes_trading.adapters.onchain import OnChainAdapter
from hermes_trading.adapters.news import NewsAdapter
from hermes_trading.adapters.macro import MacroAdapter
from hermes_trading.reflect import ReflectionCycle
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
console = Console()

# Circuit breaker state
class CircuitBreaker:
    """Circuit breaker to prevent cascading failures."""
    def __init__(self, failure_threshold: int = 5, timeout: int = 300):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = None

    def record_success(self):
        """Reset circuit breaker on success."""
        self.failures = 0
        self.last_failure_time = None

    def record_failure(self):
        """Record a failure and potentially trip the circuit."""
        self.failures += 1
        self.last_failure_time = datetime.now()

    def should_trip(self) -> bool:
        """Check if circuit should be tripped."""
        if self.failures >= self.failure_threshold:
            if self.last_failure_time:
                age = (datetime.now() - self.last_failure_time).total_seconds()
                if age > self.timeout:
                    # Reset after timeout
                    self.failures = 0
                    return False
            return True
        return False

    def is_open(self) -> bool:
        """Check if circuit is currently open."""
        return self.should_trip()

# Global circuit breakers
price_circuit = CircuitBreaker(failure_threshold=5, timeout=300)
onchain_circuit = CircuitBreaker(failure_threshold=5, timeout=300)
news_circuit = CircuitBreaker(failure_threshold=5, timeout=300)
macro_circuit = CircuitBreaker(failure_threshold=5, timeout=300)


class TradingLoop:
    """Main trading loop that runs 24/7."""

    def __init__(self, asset: str = "BTC/USDT"):
        self.asset = asset
        self.price_adapter = PriceAdapter()
        self.onchain_adapter = OnChainAdapter()
        self.news_adapter = NewsAdapter()
        self.macro_adapter = MacroAdapter()
        self.reflection_cycle = ReflectionCycle()
        self.trades_file = Path("state/trades.jsonl")
        self.heartbeat_file = Path("state/heartbeat.json")
        self.state_dir = Path("state")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.trades_file.touch(exist_ok=True)

        # Load current strategy
        self.strategy_path = self.state_dir / "strategy.yaml"
        self.strategy = self._load_strategy()

        # Trade counting for reflection trigger
        self.closed_trades_since_last_reflection = 0

    def _load_strategy(self) -> dict:
        """Load the current strategy from disk."""
        if self.strategy_path.exists():
            with open(self.strategy_path) as f:
                return yaml.safe_load(f)
        else:
            # Default v01
            return {
                "version": "01",
                "entry": {
                    "indicator": "rsi",
                    "threshold": 30,
                    "direction": "long"
                },
                "stop_loss_pct": 2.0,
                "position_size_r": 0.5
            }

    async def pull_data(self) -> dict:
        """Pull data from all adapters."""
        data = {"timestamp": datetime.now().isoformat()}

        # Fetch from each adapter with retries
        for adapter, circuit in [
            (self.price_adapter, price_circuit),
            (self.onchain_adapter, onchain_circuit),
            (self.news_adapter, news_circuit),
            (self.macro_adapter, macro_circuit)
        ]:
            try:
                if circuit.is_open():
                    logger.warning(f"Circuit breaker open for {adapter.__class__.__name__}")
                    continue

                fetched = await adapter.fetch()
                data[adapter.__class__.__name__.lower()] = fetched
                circuit.record_success()
            except Exception as e:
                circuit.record_failure()
                logger.error(f"Failed to fetch {adapter.__class__.__name__}: {e}")

        return data

    async def decide_trade(self, data: dict) -> str | None:
        """Decide whether to take a trade based on strategy and data."""
        indicator = self.strategy["entry"]["indicator"]
        threshold = self.strategy["entry"]["threshold"]
        direction = self.strategy["entry"]["direction"]

        # Simple indicator check
        if indicator == "rsi":
            price_data = data.get("priceadapter", {}).get("data", {})
            if isinstance(price_data, dict):
                rsi = price_data.get("rsi", 50)

                if direction == "long" and rsi < threshold:
                    return "entry"
                elif direction == "short" and rsi > (100 - threshold):
                    return "entry"

        return None

    async def log_trade(self, outcome: str, reason: str = ""):
        """Log a trade outcome."""
        trade = {
            "timestamp": datetime.now().isoformat(),
            "asset": self.asset,
            "outcome": outcome,  # "win", "loss", or side note
            "reason": reason,
            "strategy_version": self.strategy["version"]
        }

        with open(self.trades_file, "a") as f:
            f.write(json.dumps(trade) + "\n")

        logger.info(f"Trade logged: {outcome} - {reason}")

        # Increment reflection counter
        if outcome in ["win", "loss"]:
            self.closed_trades_since_last_reflection += 1

            # Check if we should trigger reflection
            reflection_every = int(self.strategy.get("reflection_every", 5))
            if self.closed_trades_since_last_reflection >= reflection_every:
                logger.info(f"Reflection trigger reached ({self.closed_trades_since_last_reflection} trades)")
                # In production, this would call reflection automatically
                # For now, we'll do it periodically
                await self.trigger_reflection()

    async def trigger_reflection(self):
        """Trigger a reflection cycle."""
        logger.info("Starting reflection cycle...")

        try:
            # Run reflection with deterministic fallback
            await self.reflection_cycle.run_fallback()

            # Reset counter
            self.closed_trades_since_last_reflection = 0
        except Exception as e:
            logger.error(f"Reflection failed: {e}")

    async def heartbeat(self):
        """Write heartbeat to disk."""
        heartbeat = {
            "timestamp": datetime.now().isoformat(),
            "asset": self.asset,
            "strategy_version": self.strategy["version"],
            "closed_trades": self.closed_trades_since_last_reflection
        }

        with open(self.heartbeat_file, "w") as f:
            json.dump(heartbeat, f, indent=2)

    async def run_cycle(self):
        """Run a single trading cycle (1 minute interval)."""
        try:
            # Pull data
            data = await self.pull_data()

            # Decide trade
            decision = await self.decide_trade(data)

            if decision == "entry":
                logger.info(f"Entry condition met for {self.asset}")
                # In paper mode, we just log it
                await self.log_trade(
                    outcome="paper_entry",
                    reason="Entry condition triggered"
                )
            elif decision == "exit":
                logger.info(f"Exit condition triggered for {self.asset}")

            # Write heartbeat
            await self.heartbeat()

        except Exception as e:
            logger.error(f"Error in cycle: {e}")

    async def run_forever(self):
        """Run the trading loop 24/7."""
        console.print("[bold green]🚀 Starting Hermes Trading Agent[/bold green]")
        console.print(f"   Asset: {self.asset}")
        console.print(f"   Mode: {os.getenv('HERMES_TRADING_MODE', 'paper')}")
        console.print(f"   Strategy: v{self.strategy['version']}")
        console.print()

        # Initial heartbeat
        await self.heartbeat()

        # Main loop
        while True:
            try:
                await self.run_cycle()
                await asyncio.sleep(60)  # Wait 1 minute
            except Exception as e:
                logger.error(f"Critical error in loop: {e}")
                await asyncio.sleep(60)  # Retry after 1 minute
