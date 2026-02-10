import ccxt
import logging
import pandas as pd
import time
import functools
from config import API_KEY, API_SECRET, MODE, SYMBOL, EXCHANGE as EXCHANGE_NAME
from telegram_utils import send_telegram_message

logger = logging.getLogger(__name__)

# ===== RETRY ДЕКОРАТОР =====

def retry_on_error(max_retries=3, delay=2, backoff=2, exceptions=(ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout)):
    """
    Декоратор для повторных попыток при сетевых ошибках биржи.
    max_retries: максимум попыток
    delay: начальная задержка (сек)
    backoff: множитель задержки
    exceptions: на какие ошибки реагировать
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"⚠️ {func.__name__} попытка {attempt}/{max_retries} не удалась: {e}. "
                            f"Повтор через {current_delay}с..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"❌ {func.__name__} все {max_retries} попыток исчерпаны: {e}")
            raise last_exception
        return wrapper
    return decorator

# ===== СОЗДАНИЕ EXCHANGE =====

_exchange_config = {
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',
        'defaultContractType': 'linear',
        'recvWindow': 10000,
    },
}

# Поддержка разных бирж из конфига
_exchange_class = getattr(ccxt, EXCHANGE_NAME.lower(), None)
if _exchange_class is None:
    logger.warning(f"⚠️ Биржа '{EXCHANGE_NAME}' не найдена в ccxt, используем bybit")
    _exchange_class = ccxt.bybit

exchange = _exchange_class(_exchange_config)

# ===== ФУНКЦИИ С RETRY =====

def sync_time_with_exchange():
    """Синхронизация времени клиента с сервером биржи"""
    try:
        server_time = exchange.fetch_time()
        local_time = int(time.time() * 1000)
        time_diff = server_time - local_time
        
        logger.info(f"⏱️ Время сервера: {server_time}, локальное: {local_time}, разница: {time_diff}ms")
        
        if abs(time_diff) > 5000:
            logger.warning(f"⚠️ Большая разница времени: {time_diff}ms. Проверь системное время сервера!")
            
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка синхронизации времени: {e}")
        return False

def set_leverage(symbol=None, leverage=None):
    """Установка плеча для фьючерсов"""
    if MODE != 'futures':
        logger.info("Режим spot — плечо не требуется")
        return

    from config import SYMBOL as CONFIG_SYMBOL, LEVERAGE as CONFIG_LEVERAGE
    sym = symbol or CONFIG_SYMBOL
    lev = leverage or CONFIG_LEVERAGE
    clean_symbol = sym.replace('/', '').replace(':USDT', '')

    try:
        response = exchange.private_post_v5_position_set_leverage({
            'category': 'linear',
            'symbol': clean_symbol,
            'buyLeverage': str(lev),
            'sellLeverage': str(lev),
        })
        ret_code = response.get('retCode', -1)
        ret_msg = response.get('retMsg', '')

        if ret_code == 0:
            logger.info(f"✅ Плечо {lev}x установлено для {clean_symbol}")
            send_telegram_message(f"✅ Плечо <b>{lev}x</b> установлено для <b>{sym}</b>")
        elif ret_code == 110043:
            logger.info(f"ℹ️ Плечо уже {lev}x для {clean_symbol} (не требуется изменение)")
        else:
            msg = f"❌ retCode {ret_code}: {ret_msg}"
            logger.error(msg)
            send_telegram_message(msg)
    except ccxt.ExchangeError as e:
        if "110043" in str(e) or "not modified" in str(e):
            logger.info(f"ℹ️ Плечо уже установлено")
        else:
            msg = f"❌ Ошибка биржи при установке плеча: {e}"
            logger.error(msg)
            send_telegram_message(msg)
    except Exception as e:
        msg = f"❌ Ошибка установки плеча для {sym}: {str(e)[:100]}"
        logger.error(msg)

@retry_on_error(max_retries=3, delay=2)
def fetch_ohlcv_df():
    """Получение OHLCV данных в виде DataFrame (с retry)"""
    try:
        from config import SYMBOL, TIMEFRAME, OHLCV_LIMIT
        symbol_for_fetch = SYMBOL if ':USDT' in SYMBOL else SYMBOL + ':USDT'
        candles = exchange.fetch_ohlcv(symbol_for_fetch, timeframe=TIMEFRAME, limit=OHLCV_LIMIT)
        df = pd.DataFrame(candles, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        return df
    except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout):
        raise  # Пробрасываем для retry
    except Exception as e:
        logger.error(f"❌ OHLCV error: {e}")
        return None

@retry_on_error(max_retries=3, delay=1)
def get_balance_usdt():
    """Получить баланс USDT (с retry)"""
    try:
        balance = exchange.fetch_balance()
        usdt = balance.get('USDT', {})
        free = float(usdt.get('free', 0))
        total = float(usdt.get('total', 0))
        return free, total
    except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout):
        raise
    except Exception as e:
        logger.error(f"❌ Balance fetch error: {e}")
        return 0.0, 0.0

def safe_float(value, default=0.0):
    """Безопасно преобразует значение в float"""
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (ValueError, TypeError):
        return default

@retry_on_error(max_retries=3, delay=1)
def get_position(symbol=None):
    """Получить информацию о позиции (с retry)"""
    try:
        from config import SYMBOL as DEFAULT_SYMBOL, MODE
        if MODE != 'futures':
            return 0, None, 0, 0
        
        sym = symbol or DEFAULT_SYMBOL
        clean_symbol = sym.replace('/', '').replace(':USDT', '')
        response = exchange.private_get_v5_position_list({
            'category': 'linear',
            'symbol': clean_symbol,
        })
        
        positions = response.get('result', {}).get('list', [])
        if not positions:
            return 0, None, 0, 0
        
        pos = positions[0]
        size = safe_float(pos.get('size', 0))
        side = pos.get('side', None)
        avg_price = safe_float(pos.get('avgPrice', 0))
        upnl = safe_float(pos.get('unrealisedPnl', 0))
        
        return size, side, avg_price, upnl
    except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout):
        raise
    except Exception as e:
        logger.error(f"❌ Position fetch error: {e}")
        return 0, None, 0, 0

def get_pnl():
    """Получить нереализованный и реализованный P&L"""
    try:
        _, _, _, upnl = get_position()
        return upnl, 0
    except Exception as e:
        logger.error(f"❌ PnL fetch error: {e}")
        return 0, 0

def has_open_position():
    """Проверить наличие открытой позиции"""
    size, _, _, _ = get_position()
    return abs(size) > 0
