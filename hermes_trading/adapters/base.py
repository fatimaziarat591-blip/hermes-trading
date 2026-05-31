#!/usr/bin/env python3
"""Base adapter class."""

import logging

logger = logging.getLogger(__name__)


class SchemaError(Exception):
    """Raised when schema version mismatches."""
    pass


class BaseAdapter:
    """Base class for all data adapters."""

    def __init__(self):
        self.schema_version = "1.0"

    async def fetch(self):
        """Fetch data. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement fetch()")

    async def close(self):
        """Close any open connections. Optional."""
        pass
