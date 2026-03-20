"""
Performance metrics for backtest results.
"""

import numpy as np
import pandas as pd


def compute_metrics(equity_df: pd.DataFrame, initial_capital: float, trades_df: pd.DataFrame) -> dict:
    equity = equity_df['total_value']
    returns = equity.pct_change().dropna()

    # Total return
    final = equity.iloc[-1]
    total_return_pct = (final - initial_capital) / initial_capital * 100

    # Max drawdown
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max
    max_drawdown_pct = drawdown.min() * 100

    # Sharpe ratio (annualised, assuming hourly data → 8760 periods/year)
    periods_per_year = 8760
    sharpe = (returns.mean() / returns.std()) * np.sqrt(periods_per_year) if returns.std() > 0 else 0

    # Win rate from grid trades
    grid_sells = trades_df[trades_df['type'] == 'grid_sell'] if len(trades_df) else pd.DataFrame()
    win_rate = 0.0
    avg_profit_per_trade = 0.0
    total_profit = 0.0
    if len(grid_sells) > 0 and 'profit' in grid_sells.columns:
        wins = grid_sells[grid_sells['profit'] > 0]
        win_rate = len(wins) / len(grid_sells) * 100
        avg_profit_per_trade = grid_sells['profit'].mean()
        total_profit = grid_sells['profit'].sum()

    # Time active
    active_pct = equity_df['grid_active'].mean() * 100 if 'grid_active' in equity_df.columns else 0

    # Buy & hold comparison
    start_price = equity_df['price'].iloc[0]
    end_price = equity_df['price'].iloc[-1]
    buy_hold_return = (end_price - start_price) / start_price * 100

    return {
        'initial_capital': initial_capital,
        'final_value': round(final, 2),
        'total_return_pct': round(total_return_pct, 2),
        'buy_hold_return_pct': round(buy_hold_return, 2),
        'max_drawdown_pct': round(max_drawdown_pct, 2),
        'sharpe_ratio': round(sharpe, 3),
        'total_trades': len(trades_df),
        'grid_sells': len(grid_sells),
        'win_rate_pct': round(win_rate, 1),
        'avg_profit_per_trade_usd': round(avg_profit_per_trade, 4),
        'total_grid_profit_usd': round(total_profit, 2),
        'grid_active_pct': round(active_pct, 1),
    }


def print_report(metrics: dict):
    print("\n" + "═" * 50)
    print("  BACKTEST RESULTS")
    print("═" * 50)
    print(f"  Initial capital:      ${metrics['initial_capital']:.2f}")
    print(f"  Final value:          ${metrics['final_value']:.2f}")
    print(f"  Total return:         {metrics['total_return_pct']:+.2f}%")
    print(f"  Buy & hold return:    {metrics['buy_hold_return_pct']:+.2f}%")
    print(f"  Max drawdown:         {metrics['max_drawdown_pct']:.2f}%")
    print(f"  Sharpe ratio:         {metrics['sharpe_ratio']:.3f}")
    print("─" * 50)
    print(f"  Total trades:         {metrics['total_trades']}")
    print(f"  Grid sell trades:     {metrics['grid_sells']}")
    print(f"  Win rate:             {metrics['win_rate_pct']:.1f}%")
    print(f"  Avg profit/trade:     ${metrics['avg_profit_per_trade_usd']:.4f}")
    print(f"  Total grid profit:    ${metrics['total_grid_profit_usd']:.2f}")
    print(f"  Time grid active:     {metrics['grid_active_pct']:.1f}%")
    print("═" * 50 + "\n")
