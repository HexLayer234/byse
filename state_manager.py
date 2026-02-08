"""
Глобальный менеджер состояния
Хранит актуальную информацию о текущей торговле
"""

import logging
import json
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class StateManager:
    """Менеджер глобального состояния бота"""
    
    def __init__(self):
        self.current_symbol = "ETH/USDT:USDT"
        self.current_leverage = 10
        self.current_strategy = "BALANCED"
        self.current_mode = "AUTONOMOUS"
        self.trading_mode = "FUTURES"
        self.state_file = "bot_state.json"
        
        self.load_state()
    
    def load_state(self):
        """Загружа��т сохранённое состояние"""
        try:
            if Path(self.state_file).exists():
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.current_symbol = data.get('symbol', 'ETH/USDT:USDT')
                    self.current_leverage = data.get('leverage', 10)
                    self.current_strategy = data.get('strategy', 'BALANCED')
                    self.current_mode = data.get('mode', 'AUTONOMOUS')
                    self.trading_mode = data.get('trading_mode', 'FUTURES')
                logger.info(f"✅ Состояние загружено: {self.current_symbol}")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки состояния: {e}")
    
    def save_state(self):
        """Сохраняет текущее состояние"""
        try:
            data = {
                'symbol': self.current_symbol,
                'leverage': self.current_leverage,
                'strategy': self.current_strategy,
                'mode': self.current_mode,
                'trading_mode': self.trading_mode,
                'timestamp': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения состояния: {e}")
    
    def set_symbol(self, symbol: str):
        """Устанавливает текущий символ"""
        old_symbol = self.current_symbol
        self.current_symbol = symbol
        self.save_state()
        
        import config
        config.SYMBOL = symbol
        
        logger.info(f"🔄 Символ изменён: {old_symbol} → {symbol}")
        return True
    
    def get_symbol(self) -> str:
        """Возвращает текущий символ"""
        return self.current_symbol
    
    def set_leverage(self, leverage: int):
        """Устанавливает плечо"""
        self.current_leverage = leverage
        self.save_state()
        
        import config
        config.LEVERAGE = leverage
        
        logger.info(f"📊 Плечо изменено: {leverage}x")
    
    def get_leverage(self) -> int:
        """Возвращает текущее плечо"""
        return self.current_leverage
    
    def set_strategy(self, strategy: str):
        """Устанавливает стратегию"""
        self.current_strategy = strategy
        self.save_state()
    
    def get_strategy(self) -> str:
        """Возвращает текущую стратегию"""
        return self.current_strategy
    
    def get_info(self) -> dict:
        """Возвращает всю информацию о состоянии"""
        return {
            'symbol': self.current_symbol,
            'leverage': self.current_leverage,
            'strategy': self.current_strategy,
            'mode': self.current_mode,
            'trading_mode': self.trading_mode
        }


state_manager = StateManager()
