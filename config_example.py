"""
Конфигурация BYSE
"""

import os
import logging

logger = logging.getLogger(__name__)

# ===== API КЛЮЧИ =====

# 🔴 BINANCE/BYBIT API (КРИТИЧНО!)
# Установите через переменные окружения:
#   export API_KEY='ваш_ключ'
#   export API_SECRET='ваш_секрет'
API_KEY = os.getenv('API_KEY', '')
API_SECRET = os.getenv('API_SECRET', '')

# 📰 NEWS API (для анализа новостей)
NEWS_API_KEY = os.getenv('NEWS_API_KEY', '')

# 📱 TELEGRAM
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# ===== РЕЖИМ ТОРГОВЛИ =====

TRADING_MODE = "FUTURES"  # "FUTURES" или "SPOT"

# ===== ТОРГОВЛЯ =====

SYMBOL = "ETH/USDT:USDT"  # Для фьючерсов
BASE_AMOUNT = 1000  # USDT на сделку
LEVERAGE = 1  # Плечо

# ===== РЕЖИМЫ =====

MODE = TRADING_MODE.lower()

if TRADING_MODE == "FUTURES":
    LEVERAGE = 20
    SYMBOL = "ETH/USDT:USDT"
    USE_MARGIN = False
else:
    LEVERAGE = 1
    SYMBOL = "ETH/USDT"
    USE_MARGIN = False

# ===== ТАЙМФРЕЙМЫ =====

TIMEFRAME = "1h"  # "1m", "5m", "15m", "1h", "4h", "1d"
TIMEFRAMES = {
    '5m': '5m',
    '15m': '15m',
    '1h': '1h',
    '4h': '4h',
    '1d': '1d'
}

# ===== РИСК-МЕНЕДЖМЕНТ =====

RISK_PER_TRADE = 2.0
STOP_LOSS_PERCENT = 3.0
TAKE_PROFIT_PERCENT = 15.0

# ===== ПАРАМЕТРЫ ИНДИКАТОРОВ =====

RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

VOLUME_MA_PERIOD = 20
MIN_VOLUME_RATIO = 1.5

ATR_PERIOD = 14
BOLLINGER_PERIOD = 20
BOLLINGER_STD_DEV = 2

# ===== БИРЖА =====

EXCHANGE = "binance"
SANDBOX_MODE = False

# ===== ПРОЧЕЕ =====

TRADING_ENABLED = True
LOG_LEVEL = "INFO"

# ===== ПАРАМЕТРЫ ПОДКЛЮЧЕНИЯ К БИРЖЕ =====

# Для exchange.py
OHLCV_LIMIT = 500  # Количество свечей для загрузки
MARKET_ORDER_TIMEOUT = 10  # Секунды
LIMIT_ORDER_TIMEOUT = 300  # Секунды

# ===== DATABASE =====

DATABASE_FILE = "trades.db"

# ===== КЭШИРОВАНИЕ =====

CACHE_TIMEOUT = 60  # Секунды
PRICE_CACHE_TIMEOUT = 5  # Секунды

# ===== ПРОВЕРКА КОНФИГУРАЦИИ =====

if not API_KEY or not API_SECRET:
    logger.critical("❌ КРИТИЧНО: Не установлены API_KEY и API_SECRET!")
    logger.critical("❌ Установите через переменные окружения:")
    logger.critical("   export API_KEY='ваш_ключ'")
    logger.critical("   export API_SECRET='ваш_секрет'")
    raise ValueError("API_KEY и API_SECRET обязательны для работы бота!")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    logger.warning("⚠️ ВНИМАНИЕ! Не установлены TELEGRAM_TOKEN и/или TELEGRAM_CHAT_ID!")
    logger.warning("⚠️ Telegram уведомления будут отключены.")
