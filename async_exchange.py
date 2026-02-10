"""
Async обёртка для exchange — позволяет вызывать sync ccxt из async кода
без блокировки event loop через ThreadPoolExecutor
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

logger = logging.getLogger(__name__)

# Пул потоков для неблокирующих вызовов к бирже
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="exchange")

async def run_sync(func, *args, **kwargs):
    """
    Запускает синхронную функцию в отдельном потоке.
    Используется для вызовов ccxt без блокировки event loop.
    
    Пример:
        balance = await run_sync(get_balance_usdt)
        df = await run_sync(fetch_ohlcv_df)
        order = await run_sync(place_long, price=100, amount=50)
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, partial(func, *args, **kwargs))

async def async_fetch_ohlcv(symbol, timeframe='1h', limit=100):
    """Async получение OHLCV"""
    from exchange import exchange
    import pandas as pd
    
    def _fetch():
        candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(candles, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        return df
    
    return await run_sync(_fetch)

async def async_get_position(symbol=None):
    """Async получение позиции"""
    from exchange import get_position
    return await run_sync(get_position, symbol)

async def async_get_balance():
    """Async получение баланса"""
    from exchange import get_balance_usdt
    return await run_sync(get_balance_usdt)

async def async_fetch_ticker(symbol):
    """Async получение тикера"""
    from exchange import exchange
    return await run_sync(exchange.fetch_ticker, symbol)

async def async_fetch_positions():
    """Async получение всех позиций"""
    from exchange import exchange
    return await run_sync(exchange.fetch_positions)

async def async_place_long(price=None, amount=None, use_limit=True):
    """Async открытие LONG"""
    from trading_logic import place_long
    return await run_sync(place_long, price=price, amount=amount, use_limit=use_limit)

async def async_place_short(price=None, amount=None, use_limit=True):
    """Async открытие SHORT"""
    from trading_logic import place_short
    return await run_sync(place_short, price=price, amount=amount, use_limit=use_limit)

async def async_close_long(price=None, amount=None, use_limit=True):
    """Async закрытие LONG"""
    from trading_logic import close_long
    return await run_sync(close_long, price=price, amount=amount, use_limit=use_limit)

async def async_close_short(price=None, amount=None, use_limit=True):
    """Async закрытие SHORT"""
    from trading_logic import close_short
    return await run_sync(close_short, price=price, amount=amount, use_limit=use_limit)
