#!/usr/bin/env python3
import yaml
import json
import os
from pathlib import Path

# Determine the correct path based on environment
if os.getenv('RAILWAY_ENVIRONMENT'):
    # Running on Railway - use /app/state
    state_dir = Path('/app/state')
else:
    # Running locally - use state directory in current path
    state_dir = Path.cwd() / 'state'

print(f"Looking in: {state_dir}")

# Read and print files
print("=== STRATEGY ===")
strategy_path = state_dir / 'strategy.yaml'
if strategy_path.exists():
    with open(strategy_path) as f:
        print(yaml.safe_load(f))
else:
    print("File not found")

print("\n=== HYPOTHESES ===")
hypotheses_path = state_dir / 'hypotheses.jsonl'
if hypotheses_path.exists():
    with open(hypotheses_path) as f:
        for line in f:
            print(json.loads(line))
else:
    print("File not found")

print("\n=== TRADES ===")
trades_path = state_dir / 'trades.jsonl'
if trades_path.exists():
    with open(trades_path) as f:
        for line in f:
            print(json.loads(line))
else:
    print("File not found")
