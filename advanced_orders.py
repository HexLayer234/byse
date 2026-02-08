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
        self.active_orders = {}  # {order_id: order_info}
    
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
            
            msg = f"""
🟢 LIMIT BUY ORDER
{amount:.4f} {symbol}
@ ${price:.8f}
Order ID: {order['id']}
            """
            
            send_telegram_message(msg)
            logger.info(f"✅ Limit buy order placed: {order['id']}")
            
            return order
        
        except Exception as e:
            msg = f"❌ Limit BUY error: {e}"
            send_telegram_message(msg)
            logger.error(msg)
            return None
    
    def place_limit_sell(self, symbol, amount, price):
        """Лимитный ордер на продажу"""
        try:
            order = exchange.create_limit_sell_order(symbol, amount, price)
            
            self.active_orders[order['id']] = {
                'type
