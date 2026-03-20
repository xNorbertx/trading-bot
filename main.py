#!/usr/bin/env python3
"""
Trend-Filtered Grid Backtest — main entry point.

Usage:
    python main.py                    # default settings
    python main.py --spacing 0.01     # 1% grid spacing
    python main.py --days 365         # 1 year only
    python main.py --refresh          # re-fetch data
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from backtest.data_fetcher import fetch_ohlcv
from backtest.strategy import GridBacktester
from backtest.metrics import compute_metrics, print_report
from backtest.plot import plot_results


def main():
    parser = argparse.ArgumentParser(description='Trend-Filtered Grid Backtest')
    parser.add_argument('--capital', type=float, default=250.0, help='Starting capital in USD (default: 250)')
    parser.add_argument('--days', type=int, default=730, help='Days of history (default: 730)')
    parser.add_argument('--spacing', type=float, default=0.008, help='Grid spacing pct (default: 0.008 = 0.8%%)')
    parser.add_argument('--levels', type=int, default=6, help='Grid levels (default: 6)')
    parser.add_argument('--rsi-low', type=float, default=35, help='RSI lower bound (default: 35)')
    parser.add_argument('--rsi-high', type=float, default=65, help='RSI upper bound (default: 65)')
    parser.add_argument('--sma', type=int, default=50, help='SMA period (default: 50)')
    parser.add_argument('--refresh', action='store_true', help='Force refresh cached data')
    parser.add_argument('--no-chart', action='store_true', help='Skip chart generation')
    args = parser.parse_args()

    # 1. Fetch data
    df = fetch_ohlcv(
        symbol='BTC/USDC',
        timeframe='1h',
        days=args.days,
        cache_dir='data',
        force_refresh=args.refresh,
    )
    print(f"Data range: {df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]} ({len(df)} candles)")

    # 2. Run backtest
    print(f"\nRunning backtest (capital=${args.capital}, spacing={args.spacing*100:.1f}%, levels={args.levels})...")
    bot = GridBacktester(
        initial_capital=args.capital,
        grid_levels=args.levels,
        grid_spacing_pct=args.spacing,
        rsi_low=args.rsi_low,
        rsi_high=args.rsi_high,
        sma_period=args.sma,
    )
    result = bot.run(df)

    # 3. Metrics
    metrics = compute_metrics(result['equity'], args.capital, result['trades'])
    print_report(metrics)

    # 4. Chart
    if not args.no_chart:
        plot_results(result['equity'], metrics)


if __name__ == '__main__':
    main()
