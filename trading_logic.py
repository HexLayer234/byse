"""
Торговая логика с поддержкой LONG/SHORT и лимитных ордеров
"""

import logging
import math
import pandas as pd
from datetime import datetime
from state_manager import state_manager
from exchange import exchange, get_position
from trade_database import trade_db

logger = logging.getLogger(__name__)

# ===== УТИЛИТЫ =====

def _round_quantity(exchange_obj, symbol, quantity):
    """Округляет количество по точности биржи"""
    market_info = exchange_obj.market(symbol)
    precision = market_info['precision']['amount']
    
    if isinstance(precision, float):
        if precision < 1:
            decimal_places = max(0, -int(math.floor(math.log10(precision))))
            quantity = round(quantity, decimal_places)
        else:
            quantity = round(quantity, int(precision))
    else:
        quantity = round(quantity, int(precision))
    
    # Минимальный размер
    min_amount = market_info.get('limits', {}).get('amount', {}).get('min', 0)
    if min_amount and quantity < min_amount:
        logger.warning(f"⚠️ Количество {quantity} < минимум {min_amount}, увеличиваю")
        quantity = min_amount
    
    return quantity

def _round_price(exchange_obj, symbol, price):
    """Округляет цену по точности биржи"""
    market_info = exchange_obj.market(symbol)
    precision = market_info['precision']['price']
    
    if isinstance(precision, float):
        if precision < 1:
            decimal_places = max(0, -int(math.floor(math.log10(precision))))
            return round(price, decimal_places)
        return round(price, int(precision))
    return round(price, int(precision))

def _get_current_price(symbol):
    """Получает текущую цену"""
    ticker = exchange.fetch_ticker(symbol)
    return ticker['last']

# ===== ОСНОВНЫЕ ФУНКЦИИ =====

def place_long(price=None, amount=None, use_limit=True):
    """
    Открывает LONG позицию (покупка).
    use_limit=True — лимитный ордер (дешевле комиссия)
    use_limit=False — маркет ордер (быстрее исполнение)
    """
    try:
        import config
        symbol = state_manager.get_symbol()
        
        if amount is None:
            amount = config.BASE_AMOUNT
        
        current_price = price if price else _get_current_price(symbol)
        quantity = _round_quantity(exchange, symbol, float(amount) / current_price)
        
        logger.info(f"💚 LONG: {quantity} {symbol} @ ${current_price:.8f} (${float(amount):.2f})")
        
        if use_limit:
            # Лимитный ордер чуть выше текущей цены (для гарантии исполнения)
            limit_price = _round_price(exchange, symbol, current_price * 1.0005)
            order = exchange.create_limit_buy_order(
                symbol=symbol, amount=quantity, price=limit_price
            )
            logger.info(f"✅ Лимитный LONG ордер: ID {order['id']} @ ${limit_price:.8f}")
        else:
            order = exchange.create_market_buy_order(symbol=symbol, amount=quantity)
            logger.info(f"✅ Маркет LONG ордер: ID {order['id']}")
        
        trade_db.log_trade(
            symbol=symbol, side='buy', entry_price=current_price,
            amount=quantity, entry_time=datetime.now(),
            notes=f"LONG {'limit' if use_limit else 'market'} ID:{order['id']}"
        )
        return order
        
    except Exception as e:
        logger.error(f"❌ Ошибка LONG: {e}")
        return None

def place_short(price=None, amount=None, use_limit=True):
    """
    Открывает SHORT позицию (продажа без покрытия).
    Зарабатывает на ПАДЕНИИ цены.
    """
    try:
        import config
        symbol = state_manager.get_symbol()
        
        if amount is None:
            amount = config.BASE_AMOUNT
        
        current_price = price if price else _get_current_price(symbol)
        quantity = _round_quantity(exchange, symbol, float(amount) / current_price)
        
        logger.info(f"🔴 SHORT: {quantity} {symbol} @ ${current_price:.8f} (${float(amount):.2f})")
        
        if use_limit:
            # Лимитный ордер чуть ниже текущей цены
            limit_price = _round_price(exchange, symbol, current_price * 0.9995)
            order = exchange.create_limit_sell_order(
                symbol=symbol, amount=quantity, price=limit_price
            )
            logger.info(f"✅ Лимитный SHORT ордер: ID {order['id']} @ ${limit_price:.8f}")
        else:
            order = exchange.create_market_sell_order(symbol=symbol, amount=quantity)
            logger.info(f"✅ Маркет SHORT ордер: ID {order['id']}")
        
        trade_db.log_trade(
            symbol=symbol, side='sell', entry_price=current_price,
            amount=quantity, entry_time=datetime.now(),
            notes=f"SHORT {'limit' if use_limit else 'market'} ID:{order['id']}"
        )
        return order
        
    except Exception as e:
        logger.error(f"❌ Ошибка SHORT: {e}")
        return None

def close_long(price=None, amount=None, use_limit=True):
    """Закрывает LONG позицию (продажа)"""
    try:
        symbol = state_manager.get_symbol()
        current_price = price if price and price > 0 else _get_current_price(symbol)
        
        if amount is None:
            size, side, avg_price, upnl = get_position(symbol)
            if size == 0:
                logger.warning("⚠️ Нет LONG позиции для закрытия")
                return None
            quantity = size
        else:
            quantity = _round_quantity(exchange, symbol, float(amount) / current_price)
        
        quantity = _round_quantity(exchange, symbol, quantity)
        logger.info(f"💔 Закрытие LONG: {quantity} {symbol} @ ${current_price:.8f}")
        
        if use_limit:
            limit_price = _round_price(exchange, symbol, current_price * 0.9995)
            order = exchange.create_limit_sell_order(
                symbol=symbol, amount=quantity, price=limit_price
            )
        else:
            order = exchange.create_market_sell_order(symbol=symbol, amount=quantity)
        
        logger.info(f"✅ LONG закрыт: ID {order['id']}")
        return order
        
    except Exception as e:
        logger.error(f"❌ Ошибка закрытия LONG: {e}")
        return None

def close_short(price=None, amount=None, use_limit=True):
    """Закрывает SHORT позицию (обратная покупка)"""
    try:
        symbol = state_manager.get_symbol()
        current_price = price if price and price > 0 else _get_current_price(symbol)
        
        if amount is None:
            size, side, avg_price, upnl = get_position(symbol)
            if size == 0:
                logger.warning("⚠️ Нет SHORT позиции для закрытия")
                return None
            quantity = size
        else:
            quantity = _round_quantity(exchange, symbol, float(amount) / current_price)
        
        quantity = _round_quantity(exchange, symbol, quantity)
        logger.info(f"💚 Закрытие SHORT: {quantity} {symbol} @ ${current_price:.8f}")
        
        if use_limit:
            limit_price = _round_price(exchange, symbol, current_price * 1.0005)
            order = exchange.create_limit_buy_order(
                symbol=symbol, amount=quantity, price=limit_price
            )
        else:
            order = exchange.create_market_buy_order(symbol=symbol, amount=quantity)
        
        logger.info(f"✅ SHORT закрыт: ID {order['id']}")
        return order
        
    except Exception as e:
        logger.error(f"❌ Ошибка закрытия SHORT: {e}")
        return None

# Обратная совместимость
def place_buy(price=None, amount=None):
    """Обратная совместимость — вызывает place_long"""
    return place_long(price=price, amount=amount, use_limit=True)

def place_sell(price=None, amount=None):
    """Обратная совместимость — вызывает close_long"""
    return close_long(price=price, amount=amount, use_limit=True)

# ===== ИНДИКАТОРЫ =====

def compute_indicators(df):
    """Рассчитывает технические индикаторы (параметры из конфига)"""
    try:
        import config
        
        if df is None or len(df) < 50:
            return None
        
        rsi_period = getattr(config, 'RSI_PERIOD', 14)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        macd_fast = getattr(config, 'MACD_FAST', 12)
        macd_slow = getattr(config, 'MACD_SLOW', 26)
        macd_signal_period = getattr(config, 'MACD_SIGNAL', 9)
        exp1 = df['close'].ewm(span=macd_fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=macd_slow, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=macd_signal_period, adjust=False).mean()
        histogram = macd - signal
        
        atr_period = getattr(config, 'ATR_PERIOD', 14)
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(atr_period).mean()
        
        bb_period = getattr(config, 'BOLLINGER_PERIOD', 20)
        bb_std_dev = getattr(config, 'BOLLINGER_STD_DEV', 2)
        bb_sma = df['close'].rolling(window=bb_period).mean()
        bb_std = df['close'].rolling(window=bb_period).std()
        bb_upper = bb_sma + (bb_std * bb_std_dev)
        bb_lower = bb_sma - (bb_std * bb_std_dev)
        
        vol_period = getattr(config, 'VOLUME_MA_PERIOD', 20)
        volume_ma = df['volume'].rolling(window=vol_period).mean()
        
        return {
            'rsi': rsi.iloc[-1],
            'macd': macd.iloc[-1],
            'macd_signal': signal.iloc[-1],
            'macd_histogram': histogram.iloc[-1],
            'atr': atr.iloc[-1],
            'bb_upper': bb_upper.iloc[-1],
            'bb_lower': bb_lower.iloc[-1],
            'bb_sma': bb_sma.iloc[-1],
            'volume_ma': volume_ma.iloc[-1],
            'current_volume': df['volume'].iloc[-1],
            'rsi_series': rsi,
            'macd_series': macd,
            'macd_signal_series': signal
        }
    
    except Exception as e:
        logger.error(f"❌ Ошибка расчёта индикаторов: {e}")
        return None

def calculate_signal_score(rsi, macd, macd_signal, sentiment, price_up, 
                          is_active, volume_ratio, atr, price_change_pct, lstm_direction):
    """Рассчитывает оценку сигнала (положительный = LONG, отрицательный = SHORT)"""
    score = 0
    
    if rsi < 30:
        score += 20
    elif rsi > 70:
        score -= 20
    
    if macd > macd_signal:
        score += 15
    else:
        score -= 15
    
    if sentiment == "Buy":
        score += 10
    elif sentiment == "Sell":
        score -= 10
    
    if price_up:
        score += 10
    else:
        score -= 5
    
    if is_active:
        score += 10
    
    if volume_ratio > 1.5:
        score += 10
    
    if lstm_direction == 1:
        score += 15
    elif lstm_direction == -1:
        score -= 15
    
    return score

def check_market_activity_detailed(df):
    """Проверяет активность рынка"""
    try:
        import config
        
        if df is None or len(df) < 20:
            return False, 0, 0, 0
        
        volume_ma = df['volume'].rolling(window=config.VOLUME_MA_PERIOD).mean()
        current_volume = df['volume'].iloc[-1]
        avg_volume = volume_ma.iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(config.ATR_PERIOD).mean()
        current_atr = atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else 0
        
        recent_close = df['close'].iloc[-10:] if len(df) >= 10 else df['close']
        price_change_pct = ((recent_close.iloc[-1] - recent_close.iloc[0]) / recent_close.iloc[0] * 100) if len(recent_close) > 0 else 0
        
        is_active = (
            volume_ratio > config.MIN_VOLUME_RATIO and
            current_atr > 0 and
            abs(price_change_pct) > 0.5
        )
        
        return is_active, volume_ratio, current_atr, price_change_pct
    
    except Exception as e:
        logger.error(f"❌ Ошибка анализа активности: {e}")
        return False, 0, 0, 0
