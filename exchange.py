import ccxt
import logging
import pandas as pd
import time
from config import API_KEY, API_SECRET, MODE, SYMBOL
from telegram_utils import send_telegram_message

# Создаём exchange с синхронизацией времени
exchange = ccxt.bybit({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',
        'defaultContractType': 'linear',
        'recvWindow': 10000,
    },
})

def sync_time_with_exchange():
    """Синхронизация времени клиента с сервером биржи"""
    try:
        server_time = exchange.fetch_time()
        local_time = int(time.time() * 1000)
        time_diff = server_time - local_time
        
        logging.info(f"⏱️ Время сервера: {server_time}, локальное: {local_time}, разница: {time_diff}ms")
        
        if abs(time_diff) > 5000:
            logging.warning(f"⚠️ Большая разница времени: {time_diff}ms. Проверь системное время сервера!")
            
        return True
    except Exception as e:
        logging.error(f"❌ Ошибка синхронизации времени: {e}")
        return False

def set_leverage(symbol=None, leverage=None):
    """Установка плеча для фьючерсов"""
    if MODE != 'futures':
        logging.info("Режим spot — плечо не требуется")
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
            logging.info(f"✅ Плечо {lev}x установлено для {clean_symbol}")
            send_telegram_message(f"✅ Плечо <b>{lev}x</b> установлено для <b>{sym}</b>")
        elif ret_code == 110043:
            # Это НОРМАЛЬНО — плечо уже стоит
            logging.info(f"ℹ️ Плечо уже {lev}x для {clean_symbol} (не требуется изменение)")
        else:
            msg = f"❌ retCode {ret_code}: {ret_msg}"
            logging.error(msg)
            send_telegram_message(msg)
    except ccxt.ExchangeError as e:
        # Ловим ошибки биржи отдельно
        if "110043" in str(e) or "not modified" in str(e):
            logging.info(f"ℹ️ Плечо уже установлено")
        else:
            msg = f"❌ Ошибка биржи при установке плеча: {e}"
            logging.error(msg)
            send_telegram_message(msg)
    except Exception as e:
        # Другие ошибки (сеть, таймауты и т.д.)
        msg = f"❌ Ошибка установки плеча для {sym}: {str(e)[:100]}"
        logging.error(msg)

def fetch_ohlcv_df():
    """Получение OHLCV данных в виде DataFrame"""
    try:
        from config import SYMBOL, TIMEFRAME, OHLCV_LIMIT
        symbol_for_fetch = SYMBOL if ':USDT' in SYMBOL else SYMBOL + ':USDT'
        candles = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=OHLCV_LIMIT)
        df = pd.DataFrame(candles, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        return df
    except Exception as e:
        logging.error(f"❌ OHLCV error: {e}")
        return None

def get_balance_usdt():
    """Получить баланс USDT (свободный и общий)"""
    try:
        balance = exchange.fetch_balance()
        usdt = balance.get('USDT', {})
        free = float(usdt.get('free', 0))
        total = float(usdt.get('total', 0))
        return free, total
    except Exception as e:
        logging.error(f"❌ Balance fetch error: {e}")
        return 0.0, 0.0

def safe_float(value, default=0.0):
    """Безопасно преобразует значение в float"""
    try:
        if value is None or value == '' or value == '':
            return default
        return float(value)
    except (ValueError, TypeError):
        return default

def get_position(symbol=None):
    """Получить информацию о позиции (size, side, avg_price, unrealized_pnl)"""
    try:
        from config import SYMBOL, MODE
        if MODE != 'futures':
            return 0, None, 0, 0

        # Используем переданный symbol, если есть, иначе SYMBOL из config
        symbol_to_use = symbol if symbol else SYMBOL
        clean_symbol = symbol_to_use.replace('/', '').replace(':USDT', '')

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
    except Exception as e:
        logging.error(f"❌ Position fetch error: {e}")
        return 0, None, 0, 0

def get_pnl():
    """Получить нереализованный и реализованный P&L"""
    try:
        _, _, _, upnl = get_position()
        return upnl, 0
    except Exception as e:
        logging.error(f"❌ PnL fetch error: {e}")
        return 0, 0

def has_open_position():
    """Проверить наличие открытой позиции"""
    size, _, _, _ = get_position()
    return abs(size) > 0
