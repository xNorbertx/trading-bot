"""
Trend-Filtered Grid Strategy
-----------------------------
Layer 1 (Trend filter): Uses RSI + 50-period SMA to decide if grid should be active.
Layer 2 (Grid): Simulates limit order ladder within the active zone.

Fee model: 0% maker (MEXC), 0.05% taker (only on forced liquidations).

Key design decisions:
- Position size is fixed at initial_capital * position_size_pct per grid level
- Grid only activates/deactivates on trend filter changes
- Grid recenters conservatively (3x grid range breach only)
- Deactivation sells BTC at cost basis (no accidental directional PnL)
  — this gives a pure view of grid profitability, not BTC carry gains
"""

import numpy as np
import pandas as pd


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_indicators(df: pd.DataFrame, sma_period: int = 50, rsi_period: int = 14) -> pd.DataFrame:
    df = df.copy()
    df['sma'] = df['close'].rolling(sma_period).mean()
    df['rsi'] = compute_rsi(df['close'], rsi_period)
    return df


def trend_filter_active(row, rsi_low: float = 35, rsi_high: float = 65) -> bool:
    """Returns True if conditions are safe for grid trading."""
    if pd.isna(row['sma']) or pd.isna(row['rsi']):
        return False
    above_sma = row['close'] > row['sma']
    rsi_ok = rsi_low <= row['rsi'] <= rsi_high
    return above_sma and rsi_ok


class GridBacktester:
    def __init__(
        self,
        initial_capital: float = 250.0,
        grid_levels: int = 6,
        grid_spacing_pct: float = 0.008,   # 0.8% between levels
        position_size_pct: float = 0.12,   # 12% of capital per grid level
        maker_fee: float = 0.0,
        taker_fee: float = 0.0005,
        rsi_low: float = 35,
        rsi_high: float = 65,
        sma_period: int = 50,
        rsi_period: int = 14,
        stop_loss_pct: float = 0.15,       # pause if equity drops 15%
    ):
        self.initial_capital = initial_capital
        self.grid_levels = grid_levels
        self.grid_spacing_pct = grid_spacing_pct
        self.position_size_pct = position_size_pct
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.rsi_low = rsi_low
        self.rsi_high = rsi_high
        self.sma_period = sma_period
        self.rsi_period = rsi_period
        self.stop_loss_pct = stop_loss_pct

    def _make_grid(self, center: float) -> tuple:
        half = self.grid_levels // 2
        buys = [center * (1 - self.grid_spacing_pct * (k + 1)) for k in range(half)]
        sells = [center * (1 + self.grid_spacing_pct * (k + 1)) for k in range(half)]
        return buys, sells

    def run(self, df: pd.DataFrame) -> dict:
        df = compute_indicators(df, self.sma_period, self.rsi_period).dropna().reset_index(drop=True)

        capital = self.initial_capital
        # BTC inventory tracked as {buy_price: btc_amount} — so we know cost basis
        inventory: dict[float, float] = {}   # buy_price → btc_amount

        trades = []
        equity_curve = []
        grid_active = False
        grid_center = None
        grid_buy_levels = []
        grid_sell_levels = []
        trade_count = 0
        paused_drawdown = False

        # Fixed position size per grid level (never grows — clean accounting)
        position_size_usd = self.initial_capital * self.position_size_pct

        for i, row in df.iterrows():
            price = row['close']
            high = row['high']
            low = row['low']

            # --- Risk check ---
            btc_value = sum(amt * price for amt in inventory.values())
            total_value = capital + btc_value
            drawdown = (self.initial_capital - total_value) / self.initial_capital
            if drawdown >= self.stop_loss_pct:
                paused_drawdown = True

            # --- Trend filter ---
            filter_ok = trend_filter_active(row, self.rsi_low, self.rsi_high)
            should_be_active = filter_ok and not paused_drawdown

            # --- Grid state transitions ---
            if should_be_active and not grid_active:
                grid_center = price
                grid_buy_levels, grid_sell_levels = self._make_grid(grid_center)
                inventory = {}
                grid_active = True

            elif not should_be_active and grid_active:
                # Return all held BTC to cash at COST BASIS (no directional P&L)
                # This isolates pure grid profitability
                for buy_p, btc_amt in inventory.items():
                    refund = btc_amt * buy_p  # cost basis, no gain/loss
                    capital += refund
                    trades.append({
                        'type': 'deactivate_return',
                        'price': buy_p,
                        'btc': btc_amt,
                        'usd': refund,
                        'profit': 0.0,
                        'timestamp': row['timestamp'],
                    })
                inventory = {}
                grid_active = False

            # --- Grid execution ---
            if grid_active:
                # Check buy levels hit
                for buy_price in grid_buy_levels:
                    if low <= buy_price and buy_price not in inventory:
                        btc_to_buy = position_size_usd / buy_price
                        cost = btc_to_buy * buy_price * (1 + self.maker_fee)
                        if capital >= cost:
                            capital -= cost
                            inventory[buy_price] = btc_to_buy
                            trade_count += 1
                            trades.append({
                                'type': 'grid_buy',
                                'price': buy_price,
                                'btc': btc_to_buy,
                                'usd': -cost,
                                'profit': 0.0,
                                'timestamp': row['timestamp'],
                            })

                # Check sell levels hit
                for sell_price in grid_sell_levels:
                    if high >= sell_price:
                        # Match with lowest cost basis buy
                        matching = [p for p in inventory if p < sell_price]
                        if matching:
                            buy_price = min(matching)
                            btc_amount = inventory.pop(buy_price)
                            proceeds = btc_amount * sell_price * (1 - self.maker_fee)
                            profit = proceeds - (btc_amount * buy_price)
                            capital += proceeds
                            trade_count += 1
                            trades.append({
                                'type': 'grid_sell',
                                'price': sell_price,
                                'btc': btc_amount,
                                'usd': proceeds,
                                'profit': profit,
                                'timestamp': row['timestamp'],
                            })

                # Conservative recenter: only if price moves 3x outside grid range
                grid_range = self.grid_spacing_pct * (self.grid_levels // 2)
                if grid_center and abs(price - grid_center) / grid_center > grid_range * 3:
                    # Return inventory at cost basis
                    for buy_p, btc_amt in inventory.items():
                        capital += btc_amt * buy_p
                    inventory = {}
                    grid_center = price
                    grid_buy_levels, grid_sell_levels = self._make_grid(grid_center)

            # Record equity
            btc_value = sum(amt * price for amt in inventory.values())
            total_value = capital + btc_value
            equity_curve.append({
                'timestamp': row['timestamp'],
                'price': price,
                'capital': capital,
                'btc_value': btc_value,
                'total_value': total_value,
                'grid_active': grid_active,
                'rsi': row['rsi'],
            })

        equity_df = pd.DataFrame(equity_curve)
        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()

        return {
            'equity': equity_df,
            'trades': trades_df,
            'final_value': equity_df['total_value'].iloc[-1] if len(equity_df) else self.initial_capital,
            'trade_count': trade_count,
        }
