"""
Persistent state for the paper trader.
Saves/loads from a JSON file so the bot survives restarts.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional


STATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'paper_state.json')


def _default_state(initial_capital: float) -> dict:
    return {
        'started_at': datetime.now(timezone.utc).isoformat(),
        'initial_capital': initial_capital,
        'capital': initial_capital,
        'inventory': {},          # buy_price_str → btc_amount
        'grid_active': False,
        'grid_center': None,
        'grid_buy_levels': [],
        'grid_sell_levels': [],
        'trades': [],
        'total_grid_profit': 0.0,
        'total_trades': 0,
        'last_price': None,
        'last_tick': None,
    }


def load_state(initial_capital: float = 250.0) -> dict:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
        print(f"Loaded existing state (started {state['started_at'][:10]})")
        return state
    print(f"No existing state — starting fresh with ${initial_capital}")
    return _default_state(initial_capital)


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)


def reset_state(initial_capital: float = 250.0):
    state = _default_state(initial_capital)
    save_state(state)
    print(f"State reset. Starting fresh with ${initial_capital}")
    return state
