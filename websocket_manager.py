"""
WebSocket менеджер для мгновенных обновлений цен.
Вместо polling каждые 60 секунд — получаем цены в реальном времени.
"""

import asyncio
import logging
import json
import time
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)

class WebSocketManager:
    """Менеджер WebSocket подключений к бирже"""
    
    def __init__(self):
        self.prices = {}          # {symbol: last_price}
        self.orderbooks = {}      # {symbol: {bids, asks}}
        self.last_update = {}     # {symbol: timestamp}
        self._running = False
        self._ws_thread = None
        self._callbacks = defaultdict(list)  # {event: [callbacks]}
    
    def get_price(self, symbol):
        """Мгновенная цена из WebSocket (или None если нет подключения)"""
        return self.prices.get(symbol)
    
    def get_all_prices(self):
        """Все текущие цены"""
        return dict(self.prices)
    
    def on_price_update(self, callback):
        """Регистрация callback на обновление цены"""
        self._callbacks['price'].append(callback)
    
    def start(self, symbols):
        """Запускает WebSocket в фоновом потоке"""
        if self._running:
            return
        
        self._running = True
        self._ws_thread = threading.Thread(
            target=self._run_ws_loop,
            args=(symbols,),
            daemon=True
        )
        self._ws_thread.start()
        logger.info(f"✅ WebSocket запущен для {len(symbols)} символов")
    
    def stop(self):
        """Останавливает WebSocket"""
        self._running = False
        logger.info("🛑 WebSocket остановлен")
    
    def _run_ws_loop(self, symbols):
        """Основной цикл WebSocket (в отдельном потоке)"""
        try:
            from exchange import exchange as _exchange
            
            # Используем ccxt watch_ticker если доступен
            if hasattr(_exchange, 'watch_ticker'):
                asyncio.run(self._watch_tickers_async(_exchange, symbols))
            else:
                # Фолбэк — быстрый polling (каждые 5 секунд вместо 60)
                self._fast_polling(symbols)
                
        except Exception as e:
            logger.error(f"❌ WebSocket ошибка: {e}")
            # Фолбэк на быстрый polling
            self._fast_polling(symbols)
    
    async def _watch_tickers_async(self, exchange_obj, symbols):
        """Async подписка на тикеры через ccxt pro"""
        try:
            while self._running:
                for symbol in symbols:
                    try:
                        ticker = await exchange_obj.watch_ticker(symbol)
                        self._update_price(symbol, ticker['last'])
                    except Exception as e:
                        logger.debug(f"⚠️ WS ticker {symbol}: {e}")
                        await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"⚠️ watch_ticker не поддерживается: {e}")
    
    def _fast_polling(self, symbols):
        """Быстрый polling как фолбэк (каждые 5 секунд)"""
        from exchange import exchange as _exchange
        
        logger.info("📡 WebSocket фолбэк: быстрый polling (5с)")
        
        while self._running:
            try:
                # Получаем все тикеры одним запросом
                tickers = _exchange.fetch_tickers(symbols)
                
                for symbol, ticker in tickers.items():
                    price = ticker.get('last', 0)
                    if price and price > 0:
                        self._update_price(symbol, price)
                
                time.sleep(5)  # 5 секунд вместо 60
                
            except Exception as e:
                logger.debug(f"⚠️ Polling ошибка: {e}")
                time.sleep(10)
    
    def _update_price(self, symbol, price):
        """Обновляет цену и вызывает callbacks"""
        old_price = self.prices.get(symbol)
        self.prices[symbol] = price
        self.last_update[symbol] = time.time()
        
        # Вызываем callbacks
        for cb in self._callbacks['price']:
            try:
                cb(symbol, price, old_price)
            except Exception as e:
                logger.debug(f"⚠️ Callback ошибка: {e}")
    
    def get_status(self):
        """Статус WebSocket"""
        now = time.time()
        status = {
            'running': self._running,
            'symbols': len(self.prices),
            'prices': {}
        }
        for sym, price in self.prices.items():
            age = now - self.last_update.get(sym, 0)
            status['prices'][sym] = {
                'price': price,
                'age_seconds': round(age, 1)
            }
        return status


# Глобальный экземпляр
ws_manager = WebSocketManager()
