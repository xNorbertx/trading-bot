"""
Fetch historical OHLCV data from MEXC via ccxt.
Caches to CSV so we don't re-fetch every run.
"""

import ccxt
import pandas as pd
import os
import time
from datetime import datetime, timezone


def fetch_ohlcv(
    symbol: str = 'BTC/USDC',
    timeframe: str = '1h',
    days: int = 730,
    cache_dir: str = 'data',
    force_refresh: bool = False,
) -> pd.DataFrame:

    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{symbol.replace('/', '_')}_{timeframe}_{days}d.csv")

    if os.path.exists(cache_file) and not force_refresh:
        print(f"Loading cached data from {cache_file}")
        df = pd.read_csv(cache_file)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df

    print(f"Fetching {days} days of {symbol} {timeframe} data from MEXC...")

    exchange = ccxt.mexc({
        'enableRateLimit': True,
    })

    since_ms = int((datetime.now(timezone.utc).timestamp() - days * 86400) * 1000)
    all_candles = []
    limit = 500  # MEXC max per request

    while True:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)
        except Exception as e:
            print(f"Error fetching: {e}. Retrying in 5s...")
            time.sleep(5)
            continue

        if not candles:
            break

        all_candles.extend(candles)
        last_ts = candles[-1][0]

        print(f"  Fetched up to {datetime.fromtimestamp(last_ts/1000).strftime('%Y-%m-%d %H:%M')} ({len(all_candles)} candles)")

        if len(candles) < limit:
            break

        since_ms = last_ts + 1
        time.sleep(exchange.rateLimit / 1000)

    df = pd.DataFrame(all_candles, columns=['timestamp_ms', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp_ms'], unit='ms', utc=True)
    df = df.drop_duplicates('timestamp_ms').sort_values('timestamp').reset_index(drop=True)
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

    df.to_csv(cache_file, index=False)
    print(f"Saved {len(df)} candles to {cache_file}")

    return df
