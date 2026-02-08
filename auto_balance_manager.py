"""
Автоматическое управление балансом
ИИ сам решает сколько средств использовать
"""

import logging
from exchange import get_balance_usdt, get_position
from risk_management import risk_manager
from trade_database import trade_db

logger = logging.getLogger(__name__)

class AutoBalanceManager:
    """Автоматическое управление балансом"""
    
    def __init__(self, min_reserve_percent=10, max_position_percent=90):
        """
        Args:
            min_reserve_percent: минимальный резерв (10% баланса)
            max_position_percent: максимально в позиции (90%)
        """
        self.min_reserve_percent = min_reserve_percent
        self.max_position_percent = max_position_percent
    
    def calculate_safe_position_size(self, symbol):
        """
        Рассчитывает безопасный размер позиции
        
        Логика:
        ├─ Если win rate > 70% → использовать 80-90% баланса
        ├─ Если win rate 50-70% → использовать 50-70% баланса
        ├─ Если win rate < 50% → использовать 30-50% баланса
        └─ Всегда оставляем минимум 10% резерва
        """
        try:
            free_balance, total_balance = get_balance_usdt()
            
            # Получаем статистику за последние 14 дней
            stats = trade_db.get_statistics(symbol=symbol, days=14)
            
            if not stats or stats['total_trades'] < 10:
                # Недостаточно данных - консервативный подход
                available = total_balance * 0.4  # 40% баланса
                logger.warning(
                    f"⚠️ Недостаточно данных для {symbol}, "
                    f"используем консервативный размер: ${available:.2f}"
                )
                return available
            
            win_rate = stats['win_rate']
            
            # Рассчитываем процент для использования
            if win_rate >= 70:
                # Очень успешно
                usage_percent = 0.85
            elif win_rate >= 60:
                # Успешно
                usage_percent = 0.70
            elif win_rate >= 50:
                # Нормально
                usage_percent = 0.55
            elif win_rate >= 40:
                # Ниже среднего
                usage_percent = 0.40
            else:
                # Плохо - минимум
                usage_percent = 0.25
            
            # Рассчитываем доступный баланс с резервом
            available_for_trading = total_balance * (1 - self.min_reserve_percent / 100)
            position_size = available_for_trading * usage_percent
            
            logger.info(
                f"💰 Расчёт размера позиции для {symbol}:\n"
                f"   Всего баланса: ${total_balance:.2f}\n"
                f"   Win Rate: {win_rate:.1f}%\n"
                f"   Процент использования: {usage_percent*100:.0f}%\n"
                f"   Размер позиции: ${position_size:.2f}\n"
                f"   Резерв (10%): ${total_balance * 0.1:.2f}"
            )
            
            return position_size
        
        except Exception as e:
            logger.error(f"❌ Ошибка расчёта размера позиции: {e}")
            free, total = get_balance_usdt()
            return total * 0.3  # Дефолт 30%
    
    def check_balance_health(self):
        """Проверяет здоровье баланса"""
        try:
            free, total = get_balance_usdt()
            reserve = free / total * 100 if total > 0 else 0
            
            if reserve < self.min_reserve_percent:
                logger.warning(
                    f"⚠️ ВНИМАНИЕ! Резерв низкий: {reserve:.1f}% "
                    f"(минимум: {self.min_reserve_percent}%)"
                )
                return False, "НИЗКИЙ РЕЗЕРВ"
            
            if free <= 0:
                logger.error("❌ КРИТИЧНО! Нет свободных средств!")
                return False, "НЕТ СРЕДСТВ"
            
            return True, "ОК"
        
        except Exception as e:
            logger.error(f"❌ Ошибка проверки баланса: {e}")
            return False, "ОШИБКА"
    
    def get_balance_report(self):
        """Получает отчёт о балансе"""
        try:
            free, total = get_balance_usdt()
            size, side, avg, upnl = get_position()
            
            in_position = size * avg if size > 0 else 0
            reserve = free / total * 100 if total > 0 else 0
            
            report = f"""
╔════════════════════════════════════════════════════════════╗
║              💰 ОТЧЁТ О БАЛАНСЕ                           ║
╠════════════════════════════════════════════════════════════╣
║ <b>Баланс USDT:</b>
║   Всего: ${total:.2f}
║   Свободно: ${free:.2f}
║   В позиции: ${in_position:.2f}
║
║ <b>Резерв:</b>
║   {reserve:.1f}% (минимум: {self.min_reserve_percent}%)
║   Статус: {'✅ ОК' if reserve >= self.min_reserve_percent else '⚠️ НИЗКИЙ'}
║
║ <b>Текущая позиция:</b>
║   Статус: {side or 'НЕТ'}
║   Объём: {size:.4f}
║   Нереализ. P&L: ${upnl:+.2f}
╚════════════════════════════════════════════════════════════╝
"""
            return report
        
        except Exception as e:
            logger.error(f"❌ Ошибка отчёта баланса: {e}")
            return None


auto_balance_manager = AutoBalanceManager(min_reserve_percent=10)
