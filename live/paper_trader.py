"""
Paper Trader — runs the trend-filtered grid strategy against live MEXC prices.
No real money. Simulates fills using real bid/ask prices.

Usage:
    python -m live.paper_trader          # run continuously
    python -m live.paper_trader --status # print current status and exit
    python -m live.paper_trader --reset  # reset state and start fresh
"""

import sys
import os
import time
import argparse
from datetime import datetime, timezone

import ccxt
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backtest.strategy import compute_rsi, trend_filter_active
from live.state import load_state, save_state, reset_state


# ── Config ────────────────────────────────────────────────────────────────────

SYMBOL = 'BTC/USDC'
TIMEFRAME = '1h'
INITIAL_CAPITAL = 250.0
GRID_SPACING_PCT = 0.005     # 0.5% — best params from backtest
GRID_LEVELS = 6
POSITION_SIZE_PCT = 0.12     # 12% of capital per level
MAKER_FEE = 0.0
TAKER_FEE = 0.0005
RSI_LOW = 30
RSI_HIGH = 70
SMA_PERIOD = 50
RSI_PERIOD = 14
TICK_INTERVAL = 60           # seconds between ticks
WARMUP_CANDLES = 100         # candles needed before strategy can run

# ── Exchange ──────────────────────────────────────────────────────────────────

exchange = ccxt.mexc({'enableRateLimit': True})


def fetch_recent_candles(limit: int = 150) -> pd.DataFrame:
    """Fetch recent OHLCV candles."""
    candles = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=limit)
    df = pd.DataFrame(candles, columns=['timestamp_ms', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp_ms'], unit='ms', utc=True)
    return df


def fetch_ticker() -> dict:
    """Fetch current bid/ask/last price."""
    ticker = exchange.fetch_ticker(SYMBOL)
    return {
        'last': ticker['last'],
        'bid': ticker['bid'],
        'ask': ticker['ask'],
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }


def compute_indicators_live(df: pd.DataFrame) -> dict:
    """Compute SMA + RSI from recent candles."""
    close = df['close']
    sma = close.rolling(SMA_PERIOD).mean().iloc[-1]
    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=RSI_PERIOD - 1, min_periods=RSI_PERIOD).mean().iloc[-1]
    avg_loss = loss.ewm(com=RSI_PERIOD - 1, min_periods=RSI_PERIOD).mean().iloc[-1]
    rs = avg_gain / avg_loss if avg_loss > 0 else float('inf')
    rsi = 100 - (100 / (1 + rs))
    return {'sma': sma, 'rsi': rsi}


def make_grid(center: float) -> tuple:
    half = GRID_LEVELS // 2
    buys = [center * (1 - GRID_SPACING_PCT * (k + 1)) for k in range(half)]
    sells = [center * (1 + GRID_SPACING_PCT * (k + 1)) for k in range(half)]
    return buys, sells


def log_trade(state: dict, trade_type: str, price: float, btc: float, usd: float, profit: float = 0.0):
    entry = {
        'type': trade_type,
        'price': round(price, 2),
        'btc': round(btc, 8),
        'usd': round(usd, 4),
        'profit': round(profit, 4),
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    state['trades'].append(entry)
    if profit != 0:
        state['total_grid_profit'] = round(state.get('total_grid_profit', 0) + profit, 4)
    if trade_type in ('grid_buy', 'grid_sell'):
        state['total_trades'] = state.get('total_trades', 0) + 1

    emoji = '🟢' if trade_type == 'grid_sell' else '🔴' if trade_type == 'grid_buy' else '⚪'
    profit_str = f'  profit=${profit:+.4f}' if profit != 0 else ''
    print(f"  {emoji} {trade_type.upper():<18} @ ${price:,.2f}  ({btc:.6f} BTC){profit_str}")


def tick(state: dict, price: float, high: float, low: float, indicators: dict) -> dict:
    """Process one price tick against the grid state."""

    position_size_usd = INITIAL_CAPITAL * POSITION_SIZE_PCT

    # Inventory: stored as str keys in JSON, convert to float
    inventory = {float(k): v for k, v in state.get('inventory', {}).items()}

    # Trend filter
    above_sma = price > indicators['sma']
    rsi_ok = RSI_LOW <= indicators['rsi'] <= RSI_HIGH
    filter_ok = above_sma and rsi_ok
    grid_active = state.get('grid_active', False)

    # Activate grid
    if filter_ok and not grid_active:
        state['grid_active'] = True
        state['grid_center'] = price
        buys, sells = make_grid(price)
        state['grid_buy_levels'] = buys
        state['grid_sell_levels'] = sells
        inventory = {}
        print(f"  ✅ GRID ACTIVATED  center=${price:,.2f}  RSI={indicators['rsi']:.1f}")

    # Deactivate grid
    elif not filter_ok and grid_active:
        # Return inventory at cost basis (no directional P&L)
        for buy_p, btc_amt in inventory.items():
            state['capital'] += btc_amt * buy_p
        inventory = {}
        state['grid_active'] = False
        state['grid_center'] = None
        print(f"  ⏸️  GRID PAUSED    price=${price:,.2f}  RSI={indicators['rsi']:.1f}  above_sma={above_sma}")

    # Grid execution
    if state.get('grid_active', False):
        buy_levels = state.get('grid_buy_levels', [])
        sell_levels = state.get('grid_sell_levels', [])
        center = state.get('grid_center', price)

        # Check buys
        for buy_price in buy_levels:
            if low <= buy_price and buy_price not in inventory:
                btc_to_buy = position_size_usd / buy_price
                cost = btc_to_buy * buy_price * (1 + MAKER_FEE)
                if state['capital'] >= cost:
                    state['capital'] -= cost
                    inventory[buy_price] = btc_to_buy
                    log_trade(state, 'grid_buy', buy_price, btc_to_buy, -cost)

        # Check sells
        for sell_price in sell_levels:
            if high >= sell_price:
                matching = [p for p in inventory if p < sell_price]
                if matching:
                    buy_price = min(matching)
                    btc_amount = inventory.pop(buy_price)
                    proceeds = btc_amount * sell_price * (1 - MAKER_FEE)
                    profit = proceeds - (btc_amount * buy_price)
                    state['capital'] += proceeds
                    log_trade(state, 'grid_sell', sell_price, btc_amount, proceeds, profit)

        # Recenter if price drifts far
        grid_range = GRID_SPACING_PCT * (GRID_LEVELS // 2)
        if center and abs(price - center) / center > grid_range * 3:
            for buy_p, btc_amt in inventory.items():
                state['capital'] += btc_amt * buy_p
            inventory = {}
            state['grid_center'] = price
            buys, sells = make_grid(price)
            state['grid_buy_levels'] = buys
            state['grid_sell_levels'] = sells
            print(f"  🔄 GRID RECENTERED @ ${price:,.2f}")

    # Save inventory back as str keys for JSON
    state['inventory'] = {str(k): v for k, v in inventory.items()}
    state['last_price'] = price
    state['last_tick'] = datetime.now(timezone.utc).isoformat()

    return state


def print_status(state: dict):
    capital = state['capital']
    inventory = {float(k): v for k, v in state.get('inventory', {}).items()}
    last_price = state.get('last_price') or 0
    btc_value = sum(amt * last_price for amt in inventory.values())
    total_value = capital + btc_value
    initial = state['initial_capital']
    pnl = total_value - initial
    pnl_pct = pnl / initial * 100

    print()
    print("═" * 55)
    print("  📊 PAPER TRADER STATUS")
    print("═" * 55)
    print(f"  Started:          {state['started_at'][:10]}")
    print(f"  Last tick:        {state.get('last_tick', 'never')[:19].replace('T', ' ')}")
    print(f"  Initial capital:  ${initial:.2f}")
    print(f"  Cash:             ${capital:.2f}")
    print(f"  BTC held:         {sum(inventory.values()):.6f} BTC (${btc_value:.2f})")
    print(f"  Total value:      ${total_value:.2f}")
    print(f"  P&L:              ${pnl:+.2f}  ({pnl_pct:+.2f}%)")
    print(f"  Grid profit:      ${state.get('total_grid_profit', 0):.4f}")
    print(f"  Total trades:     {state.get('total_trades', 0)}")
    print(f"  Grid active:      {'✅ YES' if state.get('grid_active') else '⏸️  NO'}")
    if state.get('grid_center'):
        print(f"  Grid center:      ${state['grid_center']:,.2f}")
    print(f"  BTC price:        ${last_price:,.2f}")
    print("─" * 55)
    # Last 5 trades
    trades = state.get('trades', [])
    if trades:
        print("  Recent trades:")
        for t in trades[-5:]:
            emoji = '🟢' if t['type'] == 'grid_sell' else '🔴' if t['type'] == 'grid_buy' else '⚪'
            ts = t['timestamp'][:16].replace('T', ' ')
            profit_str = f"  +${t['profit']:.4f}" if t.get('profit', 0) > 0 else ''
            print(f"    {emoji} {ts}  {t['type']:<18} @ ${t['price']:>10,.2f}{profit_str}")
    print("═" * 55)
    print()


def run_loop(state: dict):
    print(f"\n🚀 Paper trader started — {SYMBOL} | {GRID_SPACING_PCT*100:.1f}% grid | RSI {RSI_LOW}-{RSI_HIGH}")
    print(f"   Ticking every {TICK_INTERVAL}s. Ctrl+C to stop.\n")

    while True:
        try:
            now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{now}] Fetching data...")

            # Fetch candles for indicators + current ticker for price
            df = fetch_recent_candles(limit=WARMUP_CANDLES + 20)
            indicators = compute_indicators_live(df)
            ticker = fetch_ticker()

            price = ticker['last']
            # Use a tight simulated high/low around last price for this tick
            spread = price * 0.0005
            high = price + spread
            low = price - spread

            print(f"  BTC=${price:,.2f}  RSI={indicators['rsi']:.1f}  SMA=${indicators['sma']:,.0f}  "
                  f"above_sma={'✅' if price > indicators['sma'] else '❌'}")

            state = tick(state, price, high, low, indicators)
            save_state(state)

            # Print mini summary every tick
            capital = state['capital']
            inv = {float(k): v for k, v in state.get('inventory', {}).items()}
            btc_val = sum(amt * price for amt in inv.values())
            total = capital + btc_val
            pnl_pct = (total - state['initial_capital']) / state['initial_capital'] * 100
            print(f"  💰 Total=${total:.2f}  P&L={pnl_pct:+.2f}%  "
                  f"Grid={'ON' if state.get('grid_active') else 'OFF'}\n")

        except KeyboardInterrupt:
            print("\n\nStopping paper trader...")
            print_status(state)
            break
        except Exception as e:
            print(f"  ⚠️  Error: {e} — retrying in {TICK_INTERVAL}s")

        time.sleep(TICK_INTERVAL)


def main():
    parser = argparse.ArgumentParser(description='Paper Trader')
    parser.add_argument('--status', action='store_true', help='Print current status and exit')
    parser.add_argument('--reset', action='store_true', help='Reset state and start fresh')
    parser.add_argument('--capital', type=float, default=INITIAL_CAPITAL, help='Starting capital')
    args = parser.parse_args()

    if args.reset:
        state = reset_state(args.capital)
        print("State reset.")
        return

    state = load_state(args.capital)

    if args.status:
        print_status(state)
        return

    run_loop(state)


if __name__ == '__main__':
    main()
