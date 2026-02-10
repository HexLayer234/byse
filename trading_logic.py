"""
Торговая логика с РЕАЛЬНЫМИ ордерами
"""

import logging
import pandas as pd
from datetime import datetime
from state_manager import state_manager
from exchange import exchange, get_position
from trade_database import trade_db

logger = logging.getLogger(__name__)

def place_buy(price=None, amount=None):
    """РЕАЛЬНАЯ покупка на бирже"""
    try:
        from mode_manager import mode_manager
        import config
        
        symbol = state_manager.get_symbol()
        
        if amount is None:
            amount = config.BASE_AMOUNT
        
        # Получаем текущую цену
        if price:
            current_price = price
        else:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
        
        # Рассчитываем количество монет
        quantity = float(amount) / current_price
        
        # Округляем по точности биржи
        market_info = exchange.market(symbol)
        precision = market_info['precision']['amount']
        
        # Точность может быть float или int — обрабатываем оба варианта
        if isinstance(precision, float):
            # Если точность — это шаг (например 0.01), вычисляем кол-во знаков
            if precision < 1:
                import math
                decimal_places = max(0, -int(math.floor(math.log10(precision))))
                quantity = round(quantity, decimal_places)
            else:
                quantity = round(quantity, int(precision))
        else:
            quantity = round(quantity, int(precision))
        
        # Проверяем минимальный размер ордера
        min_amount = market_info.get('limits', {}).get('amount', {}).get('min', 0)
        if min_amount and quantity < min_amount:
            logger.warning(f"⚠️ Количество {quantity} меньше минимума {min_amount}, увеличиваю")
            quantity = min_amount
        
        logger.info(f"💚 ПОКУПКА: {quantity} {symbol} @ ${current_price:.8f} (сумма: ${float(amount):.2f})")
        
        # РЕАЛЬНЫЙ ОРДЕР
        order = exchange.create_market_buy_order(
            symbol=symbol,
            amount=quantity
        )
        
        logger.info(f"✅ Ордер исполнен: ID {order['id']}")
        
        # Сохраняем в БД
        trade_db.log_trade(
            symbol=symbol,
            side='buy',
            entry_price=current_price,
            amount=quantity,
            entry_time=datetime.now(),
            notes=f"Order ID: {order['id']}"
        )
        
        return order
        
    except Exception as e:
        logger.error(f"❌ Ошибка покупки: {e}")
        return None

def place_sell(price=None, amount=None):
    """РЕАЛЬНАЯ продажа на бирже"""
    try:
        symbol = state_manager.get_symbol()
        
        # Получаем текущую цену если не указана
        if price is None or price <= 0:
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
        
        # Если amount не указан — закрываем всю позицию
        if amount is None:
            size, side, avg_price, upnl = get_position(symbol)
            if size == 0:
                logger.warning("⚠️ Нет позиции для продажи")
                return None
            quantity = size
        else:
            quantity = float(amount) / price
        
        # Округляем по точности биржи
        market_info = exchange.market(symbol)
        precision = market_info['precision']['amount']
        
        if isinstance(precision, float):
            if precision < 1:
                import math
                decimal_places = max(0, -int(math.floor(math.log10(precision))))
                quantity = round(quantity, decimal_places)
            else:
                quantity = round(quantity, int(precision))
        else:
            quantity = round(quantity, int(precision))
        
        logger.info(f"💔 ПРОДАЖА: {quantity} {symbol} @ ${price:.8f}")
        
        # РЕАЛЬНЫЙ ОРДЕР
        order = exchange.create_market_sell_order(
            symbol=symbol,
            amount=quantity
        )
        
        logger.info(f"✅ Ордер исполнен: ID {order['id']}")
        
        return order
        
    except Exception as e:
        logger.error(f"❌ Ошибка продажи: {e}")
        return None

def compute_indicators(df):
    """Рассчитывает технические индикаторы"""
    try:
        if df is None or len(df) < 50:
            return None
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(14).mean()
        
        # Bollinger Bands
        bb_sma = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        bb_upper = bb_sma + (bb_std * 2)
        bb_lower = bb_sma - (bb_std * 2)
        
        # Volume MA
        volume_ma = df['volume'].rolling(window=20).mean()
        
        result = {
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
            # Для совместимости с backtest.py
            'rsi_series': rsi,
            'macd_series': macd,
            'macd_signal_series': signal
        }
        
        return result
    
    except Exception as e:
        logger.error(f"❌ Ошибка расчёта индикаторов: {e}")
        return None

def calculate_signal_score(rsi, macd, macd_signal, sentiment, price_up, 
                          is_active, volume_ratio, atr, price_change_pct, lstm_direction):
    """Рассчитывает оценку сигнала"""
    score = 0
    
    # RSI
    if rsi < 30:
        score += 20
    elif rsi > 70:
        score -= 20
    
    # MACD
    if macd > macd_signal:
        score += 15
    else:
        score -= 15
    
    # Сентимент
    if sentiment == "Buy":
        score += 10
    elif sentiment == "Sell":
        score -= 10
    
    # Направление цены
    if price_up:
        score += 10
    
    # Активность рынка
    if is_active:
        score += 10
    
    # Объём
    if volume_ratio > 1.5:
        score += 10
    
    # LSTM
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
        
        # Объём
        volume_ma = df['volume'].rolling(window=config.VOLUME_MA_PERIOD).mean()
        current_volume = df['volume'].iloc[-1]
        avg_volume = volume_ma.iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(config.ATR_PERIOD).mean()
        current_atr = atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else 0
        
        # Изменение цены
        recent_close = df['close'].iloc[-10:] if len(df) >= 10 else df['close']
        price_change_pct = ((recent_close.iloc[-1] - recent_close.iloc[0]) / recent_close.iloc[0] * 100) if len(recent_close) > 0 else 0
        
        # Проверка активности
        is_active = (
            volume_ratio > config.MIN_VOLUME_RATIO and
            current_atr > 0 and
            abs(price_change_pct) > 0.5
        )
        
        return is_active, volume_ratio, current_atr, price_change_pct
    
    except Exception as e:
        logger.error(f"❌ Ошибка анализа активности: {e}")
        return False, 0, 0, 0
