"""
Generate performance charts from backtest results.
"""

import matplotlib
matplotlib.use('Agg')  # headless
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import os


def plot_results(equity_df: pd.DataFrame, metrics: dict, output_dir: str = 'data'):
    os.makedirs(output_dir, exist_ok=True)
    fig, axes = plt.subplots(4, 1, figsize=(14, 18), facecolor='#0f0f0f')
    fig.suptitle('Trend-Filtered Grid Backtest — BTC/USDC', color='white', fontsize=16, y=0.98)

    ts = pd.to_datetime(equity_df['timestamp'])

    # Style
    for ax in axes:
        ax.set_facecolor('#1a1a2e')
        ax.tick_params(colors='#aaaaaa', labelsize=9)
        ax.spines[:].set_color('#333333')

    green = '#00FF41'
    cyan = '#00FFFF'
    red = '#FF073A'
    yellow = '#FFE600'

    # 1. Equity curve vs buy & hold
    ax1 = axes[0]
    start_price = equity_df['price'].iloc[0]
    buy_hold = equity_df['price'] / start_price * metrics['initial_capital']
    ax1.plot(ts, equity_df['total_value'], color=green, linewidth=1.5, label='Bot equity')
    ax1.plot(ts, buy_hold, color=cyan, linewidth=1, alpha=0.6, linestyle='--', label='Buy & hold')
    ax1.set_title('Portfolio Value', color='white', fontsize=11)
    ax1.set_ylabel('USD', color='#aaaaaa')
    ax1.legend(facecolor='#1a1a2e', labelcolor='white', fontsize=9)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:.0f}'))

    # 2. BTC price + grid active zones
    ax2 = axes[1]
    ax2.plot(ts, equity_df['price'], color=yellow, linewidth=1, alpha=0.9)
    active_mask = equity_df['grid_active']
    ax2.fill_between(ts, equity_df['price'].min(), equity_df['price'].max(),
                     where=active_mask, alpha=0.15, color=green, label='Grid active')
    ax2.set_title('BTC/USDC Price (green = grid active)', color='white', fontsize=11)
    ax2.set_ylabel('USDC', color='#aaaaaa')
    ax2.legend(facecolor='#1a1a2e', labelcolor='white', fontsize=9)

    # 3. RSI
    ax3 = axes[2]
    ax3.plot(ts, equity_df['rsi'], color=cyan, linewidth=1)
    ax3.axhline(65, color=red, linestyle='--', alpha=0.7, linewidth=0.8, label='RSI high (65)')
    ax3.axhline(35, color=green, linestyle='--', alpha=0.7, linewidth=0.8, label='RSI low (35)')
    ax3.axhline(50, color='#555555', linestyle=':', linewidth=0.6)
    ax3.set_title('RSI (14)', color='white', fontsize=11)
    ax3.set_ylabel('RSI', color='#aaaaaa')
    ax3.set_ylim(0, 100)
    ax3.legend(facecolor='#1a1a2e', labelcolor='white', fontsize=9)

    # 4. Drawdown
    ax4 = axes[3]
    roll_max = equity_df['total_value'].cummax()
    drawdown = (equity_df['total_value'] - roll_max) / roll_max * 100
    ax4.fill_between(ts, drawdown, 0, color=red, alpha=0.6)
    ax4.plot(ts, drawdown, color=red, linewidth=0.8)
    ax4.set_title('Drawdown %', color='white', fontsize=11)
    ax4.set_ylabel('%', color='#aaaaaa')

    # X axis formatting
    for ax in axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')

    # Stats box
    stats_text = (
        f"Return: {metrics['total_return_pct']:+.1f}%  |  "
        f"B&H: {metrics['buy_hold_return_pct']:+.1f}%  |  "
        f"Sharpe: {metrics['sharpe_ratio']:.2f}  |  "
        f"Max DD: {metrics['max_drawdown_pct']:.1f}%  |  "
        f"Trades: {metrics['grid_sells']}  |  "
        f"Win rate: {metrics['win_rate_pct']:.0f}%"
    )
    fig.text(0.5, 0.01, stats_text, ha='center', color='#aaaaaa', fontsize=9,
             bbox=dict(boxstyle='round', facecolor='#1a1a2e', alpha=0.8))

    plt.tight_layout(rect=[0, 0.03, 1, 0.97])
    out_path = os.path.join(output_dir, 'backtest_results.png')
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.close()
    print(f"Chart saved to {out_path}")
    return out_path
