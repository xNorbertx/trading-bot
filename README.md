# 📈 Trading Bot — Trend-Filtered Grid Strategy

A crypto grid trading bot with a trend filter (RSI + SMA) to avoid trading in bad market conditions.

## Strategy
- **Layer 1 (Filter):** RSI between 30-70, price above 50-period SMA → grid active
- **Layer 2 (Grid):** Ladder of limit buy/sell orders around current price
- **Exchange:** MEXC (0% maker fees on BTC/USDC)

## Backtest Results (2 years BTC/USDC, $250 capital)

| Spacing | RSI Filter | Return | Sharpe | Max DD | Trades |
|---------|-----------|--------|--------|--------|--------|
| 0.5%    | 30-70     | +77.7% | 7.98   | -0.63% | 475    |
| 0.5%    | 35-65     | +62.5% | 6.95   | -0.63% | 391    |
| 0.8%    | 30-70     | +44.8% | 5.39   | -1.32% | 190    |
| 1.0%    | 30-70     | +32.6% | 4.49   | -1.06% | 114    |

## Usage

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py                        # default settings
python main.py --spacing 0.005 --rsi-low 30 --rsi-high 70  # best params
python main.py --days 365 --refresh   # 1 year, fresh data
```

## Project structure
```
backtest/
  data_fetcher.py   ← fetch OHLCV from MEXC via ccxt
  strategy.py       ← trend-filtered grid engine
  metrics.py        ← performance stats
  plot.py           ← charts
main.py             ← CLI entry point
live/               ← live trading (coming soon)
```
