#!/usr/bin/env python3
"""Price data adapter using ccxt."""

import asyncio
import logging
from typing import Dict, Any

import ccxt.async_support as ccxt
import yfinance as yf

from hermes_trading.adapters.base import BaseAdapter, SchemaError

logger = logging.getLogger(__name__)


class PriceAdapter(BaseAdapter):
    """Adapter for price data using CCXT and Yahoo Finance."""

    def __init__(self):
        self.schema_version = "1.0"
        self.exchange = ccxt.binance()

    async def fetch(self) -> Dict[str, Any]:
        """Fetch current price data."""
        try:
            # Try CCXT first (works for crypto)
            try:
                symbol = "BTC/USDT"
                ticker = await self.exchange.fetch_ticker(symbol)
                price = ticker.get("last", 0)

                return {
                    "schema_version": self.schema_version,
                    "asset": "BTC/USDT",
                    "price": price,
                    "rsi": 50,  # Simplified - would need full RSI calculation
                    "timestamp": ticker.get("timestamp")
                }
            except Exception as e:
                logger.warning(f"CCXT failed, falling back to Yahoo Finance: {e}")

            # Fallback to Yahoo Finance
            ticker = yf.Ticker("BTC-USD")
            info = ticker.info
            price = info.get("currentPrice", 0)

            return {
                "schema_version": self.schema_version,
                "asset": "BTC/USDT",
                "price": price,
                "rsi": 50,  # Simplified
                "timestamp": info.get("currentTimestamp")
            }

        except Exception as e:
            raise SchemaError(f"Price adapter failed: {e}")

    async def close(self):
        """Close the exchange connection."""
        await self.exchange.close()
