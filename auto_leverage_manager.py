"""
Автоматическое управление плечом
ИИ сам выбирает оптимальное плечо на основе:
- Win Rate
- Волатильности
- Баланса
- Просадки
"""

import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from trade_database import trade_db
from exchange import set_leverage, get_balance_usdt
import numpy as np

logger = logging.getLogger(__name__)

class AutoLeverageManager:
    """Автоматическое управление плечом"""
    
    def __init__(self, min_leverage=1, max_leverage=50):
        self.min_leverage = min_leverage
        self.max_leverage = max_leverage
        self.current_leverage = 1
        self.leverage_history = []
        self.history_file = "leverage_history.json"
        self.load_history()
    
    def load_history(self):
        """Загружает историю плечей"""
        try:
            if Path(self.history_file).exists():
                with open(self.history_file, 'r') as f:
                    self.leverage_history = json.load(f)
                logger.info(f"✅ История плечей загружена")
            else:
                self.leverage_history = []
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки истории плечей: {e}")
            self.leverage_history = []
    
    def save_history(self):
        """Сохраняет историю плечей"""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.leverage_history, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения истории: {e}")
    
    def calculate_optimal_leverage(self, symbol, days=7):
        """
        Рассчитывает оптимальное плечо
        
        Формула:
        ├─ Если win rate > 70% → плечо = 20-30x (агрессивное)
        ├─ Если win rate 50-70% → плечо = 10-20x (среднее)
        ├─ Если win rate 30-50% → плечо = 5-10x (консервативное)
        └─ Если win rate < 30% → плечо = 1x (минимальное, без риска)
        """
        try:
            stats = trade_db.get_statistics(symbol=symbol, days=days)
            
            if not stats or stats['total_trades'] < 5:
                logger.warning(f"⚠️ Недостаточно сделок для расчёта плеча ({stats['total_trades'] if stats else 0})")
                return self.min_leverage
            
            win_rate = stats['win_rate']
            profit_factor = stats['profit_factor']
            max_drawdown = self._calculate_max_drawdown(symbol, days)
            
            # Базовое плечо на основе win rate
            if win_rate >= 70:
                # Очень успешно торгуем
                base_leverage = self.max_leverage * 0.8  # 40x при max=50
                confidence = "ОЧЕНЬ ВЫСОКАЯ"
            elif win_rate >= 60:
                base_leverage = self.max_leverage * 0.6  # 30x
                confidence = "ВЫСОКАЯ"
            elif win_rate >= 50:
                base_leverage = self.max_leverage * 0.4  # 20x
                confidence = "СРЕДНЯЯ"
            elif win_rate >= 40:
                base_leverage = self.max_leverage * 0.2  # 10x
                confidence = "НИЗКАЯ"
            else:
                base_leverage = self.min_leverage  # 1x (без плечо)
                confidence = "ОЧЕНЬ НИЗКАЯ"
            
            # Корректировка по коэффициенту прибыли
            if profit_factor > 2.0:
                # Очень хороший profit factor
                leverage = base_leverage * 1.2
            elif profit_factor < 1.0:
                # Плохой profit factor
                leverage = base_leverage * 0.5
            else:
                leverage = base_leverage
            
            # Корректировка по просадке
            if max_drawdown > 30:
                # Большая просадка - уменьшаем плечо
                leverage = leverage * 0.5
            elif max_drawdown < 10:
                # Маленькая просадка - можем увеличить
                leverage = leverage * 1.1
            
            # Убедимся что плечо в диапазоне
            leverage = int(max(self.min_leverage, min(leverage, self.max_leverage)))
            
            logger.info(
                f"📊 Расчёт оптимального плеча для {symbol}:\n"
                f"   Win Rate: {win_rate:.1f}%\n"
                f"   Profit Factor: {profit_factor:.2f}x\n"
                f"   Max Drawdown: {max_drawdown:.2f}%\n"
                f"   Уверенность: {confidence}\n"
                f"   Рекомендуемое плечо: {leverage}x"
            )
            
            return leverage
        
        except Exception as e:
            logger.error(f"❌ Ошибка расчёта плеча: {e}")
            return self.min_leverage
    
    def _calculate_max_drawdown(self, symbol, days=7):
        """Рассчитывает максимальную просадку"""
        try:
            stats = trade_db.get_statistics(symbol=symbol, days=days)
            if stats and stats['total_pnl'] > 0:
                # Упрощённый расчёт
                return stats['avg_loss'] / (stats['avg_loss'] + stats['avg_win']) * 100
            return 0
        except:
            return 0
    
    def apply_leverage(self, symbol, leverage):
        """Применяет плечо к бирже"""
        try:
            if leverage == self.current_leverage:
                logger.debug(f"ℹ️ Плечо уже {leverage}x, изменение не требуется")
                return True
            
            logger.info(f"🔧 Установка плечо {leverage}x для {symbol}...")
            set_leverage(symbol, leverage)
            
            self.current_leverage = leverage
            
            # Сохраняем в историю
            self.leverage_history.append({
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'leverage': leverage
            })
            
            if len(self.leverage_history) > 1000:
                self.leverage_history = self.leverage_history[-1000:]
            
            self.save_history()
            
            logger.info(f"✅ Плечо установлено: {leverage}x")
            return True
        
        except Exception as e:
            logger.error(f"❌ Ошибка установки плеча: {e}")
            return False
    
    def auto_adjust_leverage(self, symbol):
        """Автоматически подстраивает плечо"""
        try:
            optimal_leverage = self.calculate_optimal_leverage(symbol)
            return self.apply_leverage(symbol, optimal_leverage)
        except Exception as e:
            logger.error(f"❌ Ошибка автоподстройки плеча: {e}")
            return False
    
    def get_leverage_status(self, symbol):
        """Получает информацию о текущем плече"""
        stats = trade_db.get_statistics(symbol=symbol, days=7)
        
        if not stats:
            return None
        
        optimal = self.calculate_optimal_leverage(symbol)
        
        return {
            'current_leverage': self.current_leverage,
            'optimal_leverage': optimal,
            'win_rate': stats['win_rate'],
            'profit_factor': stats['profit_factor'],
            'total_trades_7d': stats['total_trades'],
            'recommendation': self._get_recommendation(optimal, self.current_leverage)
        }
    
    def _get_recommendation(self, optimal, current):
        """Даёт рекомендацию по плечу"""
        if optimal > current:
            return f"🟢 Можно увеличить плечо до {optimal}x (безопаснее)"
        elif optimal < current:
            return f"🔴 РЕКОМЕНДУЕТСЯ уменьшить плечо до {optimal}x (риск высокий)"
        else:
            return f"✅ Плечо {current}x оптимально"


auto_leverage_manager = AutoLeverageManager(min_leverage=1, max_leverage=50)
