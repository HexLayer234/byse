"""
Передвижной стоп-лосс (РУССКАЯ ВЕРСИЯ)
"""

import logging
import time
from datetime import datetime
from exchange import get_position, fetch_ohlcv_df
from telegram_utils import send_telegram_message

logger = logging.getLogger(__name__)

class TrailingStopManager:
    """Управление передвижным стоп-лоссом"""
    
    def __init__(self, trailing_percent=1.0, check_interval=60):
        self.trailing_percent = trailing_percent
        self.check_interval = check_interval
        self.active_positions = {}
        self.last_check = time.time()
    
    def register_position(self, symbol, entry_price):
        """Регистрирует новую позицию для отслеживания"""
        self.active_positions[symbol] = {
            'entry_price': entry_price,
            'peak_price': entry_price,
            'trailing_stop': entry_price * (1 - self.trailing_percent / 100),
            'entry_time': datetime.now(),
            'status': 'АКТИВНА'
        }
        
        logger.info(
            f"📍 Передвижной стоп зарегистрирован для {symbol}:\n"
            f"   Вход: ${entry_price:.8f}\n"
            f"   Пик: ${entry_price:.8f}\n"
            f"   Стоп: ${self.active_positions[symbol]['trailing_stop']:.8f}\n"
            f"   Расстояние: {self.trailing_percent}%"
        )
    
    def update_trailing_stop(self, symbol, current_price):
        """Обновляет стоп-лосс если цена выросла"""
        if symbol not in self.active_positions:
            return False
        
        position = self.active_positions[symbol]
        
        if current_price > position['peak_price']:
            old_peak = position['peak_price']
            old_trail = position['trailing_stop']
            
            position['peak_price'] = current_price
            position['trailing_stop'] = current_price * (1 - self.trailing_percent / 100)
            
            logger.info(
                f"📈 Передвижной стоп обновлён для {symbol}:\n"
                f"   Пик: ${old_peak:.8f} → ${current_price:.8f}\n"
                f"   Стоп: ${old_trail:.8f} → ${position['trailing_stop']:.8f}\n"
                f"   Прибыль: {((current_price - position['entry_price']) / position['entry_price'] * 100):.2f}%"
            )
            
            return True
        
        if current_price <= position['trailing_stop']:
            logger.warning(
                f"🔴 СТОП СРАБОТАЛ для {symbol}:\n"
                f"   Вход: ${position['entry_price']:.8f}\n"
                f"   Пик: ${position['peak_price']:.8f}\n"
                f"   Закрыто: ${current_price:.8f}\n"
                f"   Прибыль: {((position['peak_price'] - position['entry_price']) / position['entry_price'] * 100):.2f}%"
            )
            
            position['status'] = 'СРАБОТАЛ'
            return True
        
        return False
    
    def check_all_positions(self):
        """Проверяет все активные позиции"""
        df = fetch_ohlcv_df()
        if df is None or len(df) == 0:
            return []
        
        current_price = df['close'].iloc[-1]
        positions_to_close = []
        
        for symbol in list(self.active_positions.keys()):
            if self.active_positions[symbol]['status'] != 'АКТИВНА':
                continue
            
            triggered = self.update_trailing_stop(symbol, current_price)
            
            if triggered:
                positions_to_close.append(symbol)
                self.active_positions[symbol]['status'] = 'ЗАКРЫТА'
        
        return positions_to_close
    
    def get_stats(self, symbol):
        """Получить статистику по позиции"""
        if symbol not in self.active_positions:
            return None
        
        pos = self.active_positions[symbol]
        entry = pos['entry_price']
        peak = pos['peak_price']
        current_gain = ((peak - entry) / entry) * 100
        time_held = (datetime.now() - pos['entry_time']).total_seconds() / 60
        
        return {
            'symbol': symbol,
            'entry_price': entry,
            'peak_price': peak,
            'trailing_stop': pos['trailing_stop'],
            'gain_percent': current_gain,
            'time_held_minutes': time_held,
            'status': pos['status']
        }
    
    def remove_position(self, symbol):
        """Удаляет позицию из отслеживания"""
        if symbol in self.active_positions:
            stats = self.get_stats(symbol)
            del self.active_positions[symbol]
            logger.info(f"📊 Позиция удалена из отслеживания: {symbol}")
            return stats
        return None

trailing_stop_manager = TrailingStopManager(trailing_percent=1.0)
