"""
Advanced Order Types
Лимитные ордера, OCO ордера, условные ордера
"""

import logging
from exchange import exchange
from config import SYMBOL
from telegram_utils import send_telegram_message

logger = logging.getLogger(__name__)

class AdvancedOrderManager:
    """Управление продвинутыми типами ордеров"""
    
    def __init__(self):
        self.active_orders = {}
    
    def place_limit_buy(self, symbol, amount, price):
        """
        Лимитный ордер на покупку
        
        Особенности:
        ├─ Исполняется только по указанной цене или ниже
        ├─ Может не исполниться если цена не дойдёт
        ├─ Экономит на комиссии (часто ниже чем market)
        └─ Меньше слипп (исполнение точнее)
        """
        try:
            order = exchange.create_limit_buy_order(symbol, amount, price)
            
            self.active_orders[order['id']] = {
                'type': 'LIMIT_BUY',
                'symbol': symbol,
                'amount': amount,
                'price': price,
                'order_id': order['id'],
                'status': 'OPEN'
            }
            
            msg = f"""🟢 LIMIT BUY ORDER
{amount:.4f} {symbol}
@ ${price:.8f}
Order ID: {order['id']}"""
            
            send_telegram_message(msg)
            logger.info(f"✅ Limit buy order placed: {order['id']}")
            
            return order
        
        except Exception as e:
            msg = f"❌ Limit BUY error: {e}"
            send_telegram_message(msg)
            logger.error(msg)
            return None
    
    def place_limit_sell(self, symbol, amount, price):
        """
        Лимитный ордер на продажу
        
        Особенности:
        ├─ Исполняется только по указанной цене или выше
        ├─ Может не исполниться если цена не дойдёт
        ├─ Позволяет продать дороже текущей цены
        └─ Используется для Take Profit
        """
        try:
            order = exchange.create_limit_sell_order(symbol, amount, price)
            
            self.active_orders[order['id']] = {
                'type': 'LIMIT_SELL',
                'symbol': symbol,
                'amount': amount,
                'price': price,
                'order_id': order['id'],
                'status': 'OPEN'
            }
            
            msg = f"""🔴 LIMIT SELL ORDER
{amount:.4f} {symbol}
@ ${price:.8f}
Order ID: {order['id']}"""
            
            send_telegram_message(msg)
            logger.info(f"✅ Limit sell order placed: {order['id']}")
            
            return order
        
        except Exception as e:
            msg = f"❌ Limit SELL error: {e}"
            send_telegram_message(msg)
            logger.error(msg)
            return None
    
    def cancel_order(self, order_id, symbol):
        """Отменить ордер"""
        try:
            exchange.cancel_order(order_id, symbol)
            
            if order_id in self.active_orders:
                self.active_orders[order_id]['status'] = 'CANCELLED'
            
            msg = f"🚫 Ордер {order_id} отменён"
            send_telegram_message(msg)
            logger.info(msg)
            
            return True
        
        except Exception as e:
            msg = f"❌ Ошибка отмены ордера: {e}"
            logger.error(msg)
            return False
    
    def get_active_orders(self):
        """Получить список активных ордеров"""
        active = {k: v for k, v in self.active_orders.items() if v['status'] == 'OPEN'}
        return active
    
    def check_order_status(self, order_id, symbol):
        """Проверить статус ордера"""
        try:
            order = exchange.fetch_order(order_id, symbol)
            
            if order_id in self.active_orders:
                self.active_orders[order_id]['status'] = order['status']
            
            return order
        
        except Exception as e:
            logger.error(f"❌ Ошибка проверки ордера: {e}")
            return None


# Глобальный экземпляр
advanced_order_manager = AdvancedOrderManager()
