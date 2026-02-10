"""
Grid Trading (РУССКАЯ ВЕРСИЯ)
Автоматическая покупка на спадах, продажа на взлётах

ВНИМАНИЕ: Этот модуль НЕ ИСПОЛЬЗУЕТСЯ в основной логике бота!
Это ДЕМО-КОД для будущей реализации Grid Trading стратегии.
Для реальной торговли используется fully_autonomous_trader.py

ТЕКУЩЕЕ СОСТОЯНИЕ:
- Модуль симулирует сетку ордеров в памяти
- НЕ выставляет реальные ордера на биржу
- Используется для тестирования логики

ДЛЯ АКТИВАЦИИ:
1. Раскомментируй код выставления ордеров в initialize_grid()
2. Добавь в main.py импорт grid_trading_bot
3. Запусти через команду /start_grid в Telegram

ТРЕБОВАНИЯ:
- Минимальный баланс: $500-1000
- Работает только в боковом тренде
- Высокий риск в трендовых рынках
"""

import logging
import time
from datetime import datetime
from exchange import get_balance_usdt, fetch_ohlcv_df
from telegram_utils import send_telegram_message

logger = logging.getLogger(__name__)

class GridTradingBot:
    """Grid Trading - автоматическая торговля на сетке"""
    
    def __init__(self, symbol, grid_levels=10, grid_step_percent=2.0, grid_size_usdt=100):
        self.symbol = symbol
        self.grid_levels = grid_levels
        self.grid_step_percent = grid_step_percent
        self.grid_size_usdt = grid_size_usdt
        
        self.buy_orders = {}
        self.sell_orders = {}
        self.grid_center = None
        self.is_active = False
        self.pnl = 0
    
    def initialize_grid(self, center_price):
        """Инициализирует сетку вокруг центральной цены"""
        try:
            self.grid_center = center_price
            self.buy_orders.clear()
            self.sell_orders.clear()
            
            free_balance, _ = get_balance_usdt()
            total_grid_usdt = self.grid_levels * self.grid_size_usdt
            
            if free_balance < total_grid_usdt:
                logger.warning(
                    f"⚠️ Недостаточно баланса для сетки:\n"
                    f"   Нужно: ${total_grid_usdt:.2f}\n"
                    f"   Есть: ${free_balance:.2f}"
                )
                return False
            
            logger.info(
                f"🔲 Инициализация Grid Trading:\n"
                f"   Пара: {self.symbol}\n"
                f"   Центр: ${center_price:.8f}\n"
                f"   Уровней: {self.grid_levels} × {self.grid_step_percent}%\n"
                f"   Размер сетки: ${self.grid_size_usdt}/уровень\n"
                f"   Всего: ${total_grid_usdt:.2f}"
            )
            
            from trading_logic import _round_quantity, _round_price
            from exchange import exchange as _exchange
            
            # Сетка покупки (ниже центра) — РЕАЛЬНЫЕ лимитные ордера
            for i in range(1, self.grid_levels + 1):
                buy_price = center_price * (1 - (self.grid_step_percent / 100) * i)
                buy_price = _round_price(_exchange, self.symbol, buy_price)
                amount = _round_quantity(_exchange, self.symbol, self.grid_size_usdt / buy_price)
                
                order_id = None
                try:
                    order = _exchange.create_limit_buy_order(self.symbol, amount, buy_price)
                    order_id = order['id']
                    logger.info(f"🟢 Grid LONG #{i}: {amount} @ ${buy_price}")
                except Exception as e:
                    logger.warning(f"⚠️ Grid LONG #{i} ошибка: {e}")
                
                self.buy_orders[buy_price] = {
                    'price': buy_price,
                    'amount': amount,
                    'usdt': self.grid_size_usdt,
                    'level': i,
                    'status': 'ОЖИДАНИЕ',
                    'filled': False,
                    'order_id': order_id
                }
            
            # Сетка продажи (выше центра) — РЕАЛЬНЫЕ лимитные ордера
            for i in range(1, self.grid_levels + 1):
                sell_price = center_price * (1 + (self.grid_step_percent / 100) * i)
                sell_price = _round_price(_exchange, self.symbol, sell_price)
                amount = _round_quantity(_exchange, self.symbol, self.grid_size_usdt / center_price)
                
                order_id = None
                try:
                    order = _exchange.create_limit_sell_order(self.symbol, amount, sell_price)
                    order_id = order['id']
                    logger.info(f"🔴 Grid SHORT #{i}: {amount} @ ${sell_price}")
                except Exception as e:
                    logger.warning(f"⚠️ Grid SHORT #{i} ошибка: {e}")
                
                self.sell_orders[sell_price] = {
                    'price': sell_price,
                    'amount': amount,
                    'usdt': self.grid_size_usdt,
                    'level': i,
                    'status': 'ОЖИДАНИЕ',
                    'filled': False,
                    'order_id': order_id
                }
            
            self.is_active = True
            msg = f"✅ Grid Trading активирован для {self.symbol}"
            send_telegram_message(msg)
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации сетки: {e}")
            return False
    
    def check_grid_execution(self):
        """Проверяет исполнение сетки"""
        df = fetch_ohlcv_df()
        if df is None or len(df) == 0:
            return
        
        current_price = df['close'].iloc[-1]
        
        executed_buys = []
        executed_sells = []
        
        for buy_price, order_info in self.buy_orders.items():
            if order_info['filled']:
                continue
            
            if current_price <= buy_price * 0.995:
                executed_buys.append((buy_price, order_info))
                order_info['filled'] = True
                order_info['fill_price'] = current_price
                order_info['fill_time'] = datetime.now()
        
        for sell_price, order_info in self.sell_orders.items():
            if order_info['filled']:
                continue
            
            if current_price >= sell_price * 1.005:
                executed_sells.append((sell_price, order_info))
                order_info['filled'] = True
                order_info['fill_price'] = current_price
                order_info['fill_time'] = datetime.now()
        
        for price, order in executed_buys:
            pnl_per_grid = (price - order['fill_price']) * order['amount']
            logger.info(
                f"🟢 Сетка КУПИЛ исполнена:\n"
                f"   Уровень {order['level']}: ${price:.8f}\n"
                f"   Исполнено: ${order['fill_price']:.8f}\n"
                f"   Количество: {order['amount']:.4f}\n"
                f"   P&L: ${pnl_per_grid:.2f}"
            )
        
        for price, order in executed_sells:
            pnl_per_grid = (order['fill_price'] - price) * order['amount']
            self.pnl += pnl_per_grid
            
            logger.info(
                f"🔴 Сетка ПРОДАЛ исполнена:\n"
                f"   Уровень {order['level']}: ${price:.8f}\n"
                f"   Исполнено: ${order['fill_price']:.8f}\n"
                f"   Количество: {order['amount']:.4f}\n"
                f"   P&L: ${pnl_per_grid:.2f}\n"
                f"   Общий P&L сетки: ${self.pnl:.2f}"
            )
    
    def get_grid_status(self):
        """Получает статус сетки"""
        total_buy_levels = len([o for o in self.buy_orders.values() if o['filled']])
        total_sell_levels = len([o for o in self.sell_orders.values() if o['filled']])
        
        return {
            'is_active': self.is_active,
            'center_price': self.grid_center,
            'buy_filled': total_buy_levels,
            'sell_filled': total_sell_levels,
            'total_pnl': self.pnl,
            'fill_rate': ((total_buy_levels + total_sell_levels) / (self.grid_levels * 2) * 100)
                        if self.grid_levels > 0 else 0
        }
    
    def stop_grid(self):
        """Остановить grid trading"""
        self.is_active = False
        
        status = self.get_grid_status()
        msg = f""" GRID TRADING ОСТАНОВЛЕН
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Уровней покупки исполнено: {status['buy_filled']}/{self.grid_levels}
Уровней продажи исполнено: {status['sell_filled']}/{self.grid_levels}
Общий P&L: ${status['total_pnl']:+.2f}
Процент заполнения: {status['fill_rate']:.1f}%
        """
        send_telegram_message(msg)
        logger.info(msg)

grid_trading_bot = None
