"""
Управление режим��ми торговли
Поддержка FUTURES и SPOT
"""

import logging
import json
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class ModeManager:
    """Управление режимами торговли"""
    
    def __init__(self):
        self.current_mode = "AUTONOMOUS"  # AUTONOMOUS или MANUAL
        self.trading_mode = "FUTURES"  # FUTURES или SPOT
        self.mode_history = []
        self.mode_file = "trading_mode.json"
        self.auto_trading_enabled = True
        self.manual_controls = {
            'position_size': None,
            'leverage': None,
            'entry_price': None,
            'exit_price': None,
            'buy_signal': False,
            'sell_signal': False
        }
        self.load_mode()
    
    def load_mode(self):
        """Загружает сохранённый режим"""
        try:
            if Path(self.mode_file).exists():
                with open(self.mode_file, 'r') as f:
                    data = json.load(f)
                    self.current_mode = data.get('mode', 'AUTONOMOUS')
                    self.trading_mode = data.get('trading_mode', 'FUTURES')
                    self.auto_trading_enabled = data.get('auto_trading_enabled', True)
                logger.info(f"✅ Режим загружен: {self.current_mode} | Торговля: {self.trading_mode}")
            else:
                self.save_mode()
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки режима: {e}")
    
    def save_mode(self):
        """Сохраняет текущий режим"""
        try:
            data = {
                'mode': self.current_mode,
                'trading_mode': self.trading_mode,
                'auto_trading_enabled': self.auto_trading_enabled,
                'timestamp': datetime.now().isoformat()
            }
            with open(self.mode_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"✅ Режим сохранён: {self.current_mode} | Торговля: {self.trading_mode}")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения режима: {e}")
    
    def switch_to_autonomous(self):
        """Переключение на автономный режим"""
        logger.info("🤖 Переключение на АВТОНОМНЫЙ режим...")
        
        self.current_mode = "AUTONOMOUS"
        self.auto_trading_enabled = True
        self.save_mode()
        
        self.manual_controls = {
            'position_size': None,
            'leverage': None,
            'entry_price': None,
            'exit_price': None,
            'buy_signal': False,
            'sell_signal': False
        }
        
        mode_type = "📈 ФЬЮЧЕРСЫ" if self.trading_mode == "FUTURES" else "💰 СПОТ"
        
        report = f"""
╔════════════════════════════════════════════════════════════╗
║           🤖 РЕЖИМ: ПОЛНАЯ АВТОНОМИЯ                      ║
╠════════════════════════════════════════════════════════════╣
║ Режим торговли: {mode_type}
║
║ ✅ БОТ САМ:
║   ✓ Выбирает монеты
║   ✓ Выставляет плечо (если фьючерсы)
║   ✓ Рассчитывает размер позиции
║   ✓ Определяет вход/выход
║   ✓ Адаптируется к рынку
║
║ Время включения: {datetime.now().strftime('%H:%M:%S')}
╚════════════════════════════════════════════════════════════╝
"""
        logger.info(report)
        return report
    
    def switch_to_manual(self):
        """Переключение на ручной режим"""
        logger.info("🎮 Переключение на РУЧНОЙ режим...")
        
        self.current_mode = "MANUAL"
        self.auto_trading_enabled = False
        self.save_mode()
        
        mode_type = "📈 ФЬЮЧЕРСЫ" if self.trading_mode == "FUTURES" else "💰 СПОТ"
        
        report = f"""
╔════════════════════════════════════════════════════════════╗
║           🎮 РЕЖИМ: ПОЛНОСТЬЮ РУЧНОЙ                      ║
╠════════════════════════════════════════════════════════════╣
║ Режим торговли: {mode_type}
║
║ 👤 ВЫ УПРАВЛЯЕТЕ:
║   • /buy - выполнить покупку
║   • /sell - выполнить продажу
║   • /close - закрыть позицию
║   • /set_leverage - плечо (только фьючерсы)
║   • /set_amount - размер позиции
║
║ ⚙️ ДОСТУПНЫЕ КОМАНДЫ:
║   • /manual_status - статус режима
║   • /manual_buy <цена> - лимит покупка
║   • /manual_sell <цена> - лимит продажа
║   • /manual_position - текущая позиция
║
║ Время включения: {datetime.now().strftime('%H:%M:%S')}
╚════════════════════════════════════════════════════════════╝
"""
        logger.info(report)
        return report
    
    def switch_trading_mode(self, mode: str):
        """Переключает режим торговли (FUTURES/SPOT)"""
        if mode.upper() not in ["FUTURES", "SPOT"]:
            logger.error(f"❌ Неизвестный режим: {mode}")
            return False
        
        old_mode = self.trading_mode
        self.trading_mode = mode.upper()
        self.save_mode()
        
        logger.info(f"🔄 Режим торговли изменён: {old_mode} → {self.trading_mode}")
        
        # Обновляем конфиг — НЕ сбрасываем текущий символ!
        import config
        config.TRADING_MODE = self.trading_mode
        config.MODE = self.trading_mode.lower()
        
        # Конвертируем текущий символ в правильный формат
        current_symbol = config.SYMBOL
        base_symbol = current_symbol.replace(':USDT', '').replace('/USDT', '')
        
        if self.trading_mode == "FUTURES":
            config.LEVERAGE = 20
            config.SYMBOL = f"{base_symbol}/USDT:USDT"
        else:  # SPOT
            config.LEVERAGE = 1
            config.SYMBOL = f"{base_symbol}/USDT"
        
        logger.info(f"📊 Символ обновлён: {current_symbol} → {config.SYMBOL}")
        
        return True
    
    def set_manual_buy(self, price: float = None, amount: float = None):
        """Устанавливает ручную команду покупки"""
        self.manual_controls['buy_signal'] = True
        self.manual_controls['entry_price'] = price
        self.manual_controls['position_size'] = amount
        
        logger.info(f"🟢 Ручная команда ПОКУПКА установлена: цена={price}, размер={amount}")
        return True
    
    def set_manual_sell(self, price: float = None, amount: float = None):
        """Устанавливает ручную команду продажи"""
        self.manual_controls['sell_signal'] = True
        self.manual_controls['exit_price'] = price
        
        logger.info(f"🔴 Ручная команда ПРОДАЖА установлена: цена={price}")
        return True
    
    def clear_manual_signals(self):
        """Очищает ручные команды"""
        self.manual_controls = {
            'position_size': None,
            'leverage': None,
            'entry_price': None,
            'exit_price': None,
            'buy_signal': False,
            'sell_signal': False
        }
        logger.info("🔄 Ручные команды очищены")
    
    def get_mode_status(self):
        """Получает статус текущего режима"""
        trading_mode_text = "📈 ФЬЮЧЕРСЫ (с плечом)" if self.trading_mode == "FUTURES" else "💰 СПОТ (без плеча)"
        
        if self.current_mode == "AUTONOMOUS":
            status = f"""
╔════════════════════════════════════════════════════════════╗
║           🤖 ТЕКУЩИЙ РЕЖИМ: АВТОНОМИЯ                     ║
╠════════════════════════════════════════════════════════════╣
║ Статус: ✅ АКТИВЕН
║ Торговля: {trading_mode_text}
║
║ 🔧 ПАРАМЕТРЫ:
║   • Выбор монет: АВТОМАТИЧЕСКИЙ
║   • Плечо: АВТОМАТИЧЕСКОЕ (на основе win rate)
║   • Размер позиции: ДИНАМИЧЕСКИЙ
║   • Вход/выход: АВТОМАТИЧЕСКИЙ (ИИ анализ)
║   • Адаптация: НЕПРЕРЫВНАЯ (каждый час)
║
║ 📊 ИНТЕРВАЛЫ ОПТИМИЗАЦИИ:
║   • Каждый час: проверка плеча
║   • Каждые 4 часа: рекомендации
║   • Каждые 6 часов: смена монеты
║   • Каждые 24 часа: переоптимизация
║
║ ⚙️ КОМАНДЫ:
║   /switch_manual - ручной режим
║   /switch_futures - фьючерсы
║   /switch_spot - спот торговля
╚════════════════════════════════════════════════════════════╝
"""
        else:
            status = f"""
╔════════════════════════════════════════════════════════════╗
║           🎮 ТЕКУЩИЙ РЕЖИМ: РУЧНОЙ                        ║
╠════════════════════════════════════════════════════════════╣
║ Статус: 👤 РУЧНОЕ УПРАВЛЕНИЕ
║ Торговля: {trading_mode_text}
║
║ 🎮 ДОСТУПНЫЕ КОМАНДЫ:
║   • /manual_buy <цена> - лимит покупка
║   • /manual_sell <цена> - лимит продажа
║   • /manual_close - закрыть позицию
║   • /manual_leverage <1-50> - плечо (фьючерсы)
║   • /manual_amount <USDT> - размер позиции
║   • /manual_position - информация о позиции
║
║ ℹ️ ИИ АНАЛИЗ ДОСТУПЕН:
║   • /ai_analysis - анализ условий входа
║   • /ai_recommendation - рекомендации ИИ
║   • /leverage - статус плеча
║
║ ⚙️ КОМАНДЫ:
║   /switch_autonomous - автономный режим
║   /switch_futures - фьючерсы
║   /switch_spot - спот торговля
╚════════════════════════════════════════════════════════════╝
"""
        return status
    
    def is_autonomous_mode(self):
        """Проверяет автономный ли режим"""
        return self.current_mode == "AUTONOMOUS" and self.auto_trading_enabled
    
    def is_manual_mode(self):
        """Проверяет ручной ли режим"""
        return self.current_mode == "MANUAL" and not self.auto_trading_enabled
    
    def is_futures_mode(self):
        """Проверяет режим фьючерсов"""
        return self.trading_mode == "FUTURES"
    
    def is_spot_mode(self):
        """Проверяет режим спота"""
        return self.trading_mode == "SPOT"
    
    def has_manual_buy_signal(self):
        """Проверяет есть ли сигнал ручной покупки"""
        return self.manual_controls['buy_signal']
    
    def has_manual_sell_signal(self):
        """Проверяет есть ли сигнал ручной продажи"""
        return self.manual_controls['sell_signal']


mode_manager = ModeManager()
