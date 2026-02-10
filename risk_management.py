"""
Управление рисками: TWE, Unstucking, размер позиции
"""

import logging
import time
import pandas as pd
from config import BASE_AMOUNT, LEVERAGE, STOP_LOSS_PERCENT
from exchange import get_balance_usdt, fetch_ohlcv_df

logger = logging.getLogger(__name__)

# ===== TWE (Total Wallet Exposure) =====

class TWEManager:
    """
    Total Wallet Exposure — контроль суммарной маржи.
    Не позволяет суммарной марже всех позиций превысить лимит.
    """
    
    def __init__(self, max_twe_percent=80):
        self.max_twe_percent = max_twe_percent  # Максимум 80% баланса в позициях
    
    def get_current_twe(self):
        """Рассчитывает текущий TWE (% баланса в позициях)"""
        try:
            from exchange import exchange as _exchange
            free, total = get_balance_usdt()
            
            if total <= 0:
                return 0, 0, total
            
            used = total - free
            twe_percent = (used / total) * 100
            
            return twe_percent, used, total
        except Exception as e:
            logger.error(f"❌ Ошибка расчёта TWE: {e}")
            return 0, 0, 0
    
    def can_open_position(self, additional_margin_usdt=0):
        """Проверяет можно ли открыть новую позицию"""
        twe_pct, used, total = self.get_current_twe()
        
        if total <= 0:
            return False, "Нет баланса"
        
        new_twe = ((used + additional_margin_usdt) / total) * 100
        
        if new_twe > self.max_twe_percent:
            msg = f"TWE превышен: {new_twe:.1f}% > {self.max_twe_percent}% (маржа: ${used:.2f} + ${additional_margin_usdt:.2f})"
            logger.warning(f"🚫 {msg}")
            return False, msg
        
        return True, f"TWE OK: {new_twe:.1f}% / {self.max_twe_percent}%"
    
    def get_available_margin(self):
        """Сколько ещё маржи можно использовать"""
        twe_pct, used, total = self.get_current_twe()
        max_used = total * (self.max_twe_percent / 100)
        available = max(0, max_used - used)
        return available

twe_manager = TWEManager(max_twe_percent=80)

# ===== UNSTUCKING MECHANISM =====

class UnstuckingManager:
    """
    Механизм разгрузки застрявших позиций.
    Если позиция висит в убытке слишком долго — 
    постепенно фиксирует маленькие убытки.
    """
    
    def __init__(self, max_stuck_hours=4, unstuck_percent=10, max_loss_per_unstuck=1.0):
        self.max_stuck_hours = max_stuck_hours  # Часов до начала unstuck
        self.unstuck_percent = unstuck_percent   # Сколько % позиции закрывать за раз
        self.max_loss_per_unstuck = max_loss_per_unstuck  # Макс убыток за одну разгрузку (%)
        self.unstuck_history = {}  # {symbol: last_unstuck_time}
    
    def should_unstuck(self, symbol, entry_time, entry_price, current_price, pnl_percent):
        """Нужно ли разгружать позицию?"""
        if entry_time is None:
            return False, None
        
        hours_stuck = (time.time() - entry_time.timestamp()) / 3600
        
        # Позиция не достаточно старая
        if hours_stuck < self.max_stuck_hours:
            return False, None
        
        # Позиция в прибыли — не трогаем
        if pnl_percent >= 0:
            return False, None
        
        # Убыток не критичный (меньше 0.5%) — ещё подождём
        if abs(pnl_percent) < 0.5:
            return False, None
        
        # Проверяем кулдаун — не чаще чем раз в 30 минут
        last_unstuck = self.unstuck_history.get(symbol, 0)
        if time.time() - last_unstuck < 1800:
            return False, None
        
        # Рассчитываем сколько закрывать
        close_percent = min(self.unstuck_percent, abs(pnl_percent) * 5)
        close_percent = max(5, close_percent)  # Минимум 5%
        
        reason = (
            f"Позиция застряла {hours_stuck:.1f}ч, убыток {pnl_percent:.2f}%. "
            f"Закрываем {close_percent:.0f}% позиции."
        )
        
        return True, {
            'close_percent': close_percent,
            'hours_stuck': hours_stuck,
            'pnl_percent': pnl_percent,
            'reason': reason
        }
    
    def record_unstuck(self, symbol):
        """Записывает время последней разгрузки"""
        self.unstuck_history[symbol] = time.time()

unstucking_manager = UnstuckingManager(max_stuck_hours=4, unstuck_percent=10)

class RiskManager:
    """Управление риском и расчёт размера позиции"""
    
    def __init__(self, risk_percent_per_trade=2.0, max_position_size=None):
        self.risk_percent = risk_percent_per_trade
        self.max_position_size = max_position_size
        self.trades_history = []
    
    def calculate_position_size(self, current_price, stop_loss_price, current_atr=None):
        """Динамический расчёт размера позиции"""
        try:
            free_balance, total_balance = get_balance_usdt()
            
            if free_balance <= 0:
                logger.warning("❌ Недостаточно баланса для расчёта позиции")
                return 0, 0, 0
            
            # Рассчитываем сумму риска в USDT
            risk_amount = free_balance * (self.risk_percent / 100)
            
            # Расстояние до стоп-лосса
            distance_to_sl = abs(current_price - stop_loss_price)
            
            if distance_to_sl == 0:
                logger.error("❌ Стоп-лосс не может быть равен цене входа")
                return 0, 0, 0
            
            # Количество монет
            position_size_coins = risk_amount / distance_to_sl
            
            # Стоимость в USDT
            position_size_usdt = position_size_coins * current_price
            position_size_usdt_with_leverage = position_size_usdt / max(LEVERAGE, 1)
            
            # Проверяем максимум
            if self.max_position_size and position_size_coins > self.max_position_size:
                logger.warning(
                    f"⚠️ Размер позиции {position_size_coins:.4f} превышает максимум "
                    f"{self.max_position_size:.4f}, ограничиваю"
                )
                position_size_coins = self.max_position_size
                position_size_usdt = position_size_coins * current_price
                position_size_usdt_with_leverage = position_size_usdt / max(LEVERAGE, 1)
            
            logger.info(
                f"📊 Расчёт размера позиции:\n"
                f"   Баланс: ${free_balance:.2f}\n"
                f"   Риск: ${risk_amount:.2f} ({self.risk_percent}%)\n"
                f"   Цена входа: ${current_price:.8f}\n"
                f"   Стоп-лосс: ${stop_loss_price:.8f}\n"
                f"   Расстояние до SL: ${distance_to_sl:.8f}\n"
                f"   Размер: {position_size_coins:.4f} монет = ${position_size_usdt:.2f}\n"
                f"   С плечом {LEVERAGE}x: ${position_size_usdt_with_leverage:.2f}"
            )
            
            return position_size_coins, position_size_usdt_with_leverage, risk_amount
        
        except Exception as e:
            logger.error(f"❌ Ошибка расчёта позиции: {e}")
            return 0, 0, 0
    
    def calculate_kelly_criterion(self, win_rate, win_loss_ratio):
        """Kelly Criterion для оптимального размера позиции"""
        if win_rate <= 0 or win_rate >= 1:
            logger.warning("⚠️ Процент выигрышей должен быть между 0 и 1")
            return 0.02
        
        q = 1 - win_rate
        kelly_fraction = ((win_loss_ratio * win_rate) - q) / win_loss_ratio
        fractional_kelly = max(0, kelly_fraction / 2)
        fractional_kelly = min(fractional_kelly, 0.25)
        
        logger.info(
            f"📊 Критерий Келли:\n"
            f"   Процент выигрышей: {win_rate*100:.1f}%\n"
            f"   Соотношение выигрыш/убыток: {win_loss_ratio:.2f}x\n"
            f"   Полный Келли: {kelly_fraction*100:.2f}%\n"
            f"   Дробный Келли (÷2): {fractional_kelly*100:.2f}%\n"
            f"   Рекомендация: Риск {fractional_kelly*100:.2f}% за сделку"
        )
        
        return fractional_kelly
    
    def adjust_for_volatility(self, base_position, current_atr, avg_atr):
        """Корректировка размера позиции в зависимости от волатильности"""
        if avg_atr == 0:
            return base_position
        
        volatility_ratio = avg_atr / current_atr
        adjusted_position = base_position * volatility_ratio
        
        logger.debug(
            f"📊 Корректировка волатильности:\n"
            f"   Базовая позиция: {base_position:.4f}\n"
            f"   Текущее ATR: {current_atr:.8f}\n"
            f"   Среднее ATR: {avg_atr:.8f}\n"
            f"   Коэффициент волатильности: {volatility_ratio:.2f}x\n"
            f"   Скорректированная позиция: {adjusted_position:.4f}"
        )
        
        return adjusted_position
    
    def get_max_drawdown_risk(self, consecutive_losses=3):
        """Расчёт риска при серии убытков"""
        free_balance, _ = get_balance_usdt()
        balance_after_loss = free_balance * ((1 - self.risk_percent/100) ** consecutive_losses)
        drawdown_percent = ((free_balance - balance_after_loss) / free_balance) * 100
        
        logger.info(
            f"📊 Максимальный риск просадки:\n"
            f"   Текущий баланс: ${free_balance:.2f}\n"
            f"   Риск за сделку: {self.risk_percent}%\n"
            f"   Последовательных убытков: {consecutive_losses}\n"
            f"   Баланс после убытков: ${balance_after_loss:.2f}\n"
            f"   Просадка: {drawdown_percent:.2f}%"
        )
        
        return drawdown_percent
    
    def log_trade(self, symbol, side, entry_price, exit_price, amount, pnl, duration):
        """Логирование сделки — в память И в БД"""
        from datetime import datetime
        from trade_database import trade_db
        
        trade = {
            'symbol': symbol,
            'side': side,
            'entry': entry_price,
            'exit': exit_price,
            'amount': amount,
            'pnl': pnl,
            'duration_seconds': duration,
            'timestamp': pd.Timestamp.now()
        }
        self.trades_history.append(trade)
        
        # Дублируем в БД чтобы не терять при перезапуске
        try:
            now = datetime.now()
            trade_db.log_trade(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                exit_price=exit_price,
                amount=amount,
                pnl=pnl,
                entry_time=now,
                exit_time=now,
                reason='RISK_MANAGER',
                notes=f"duration={duration}s"
            )
        except Exception as e:
            logger.warning(f"⚠️ Не удалось сохранить сделку в БД: {e}")
        
        logger.info(
            f"📝 Сделка залогирована: {side} {amount:.4f} {symbol} @ "
            f"${entry_price:.8f} → ${exit_price:.8f} = ${pnl:.2f}"
        )
    
    def get_statistics(self, symbol=None, days=14):
        """Расчёт статистики — сначала из БД, потом из памяти"""
        from trade_database import trade_db
        
        # Пробуем получить из БД (переживает перезапуски)
        db_stats = trade_db.get_statistics(symbol=symbol, days=days)
        if db_stats and db_stats['total_trades'] > 0:
            return db_stats
        
        # Фолбэк — данные из памяти
        if not self.trades_history:
            logger.warning("⚠️ Нет сделок в истории")
            return None
        
        df = pd.DataFrame(self.trades_history)
        
        winning_trades = df[df['pnl'] > 0]
        losing_trades = df[df['pnl'] < 0]
        
        win_rate = len(winning_trades) / len(df) * 100 if len(df) > 0 else 0
        avg_win = winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0
        avg_loss = abs(losing_trades['pnl'].mean()) if len(losing_trades) > 0 else 0
        win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        
        total_pnl = df['pnl'].sum()
        profit_factor = winning_trades['pnl'].sum() / abs(losing_trades['pnl'].sum()) \
                       if len(losing_trades) > 0 else 0
        
        return {
            'total_trades': len(df),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'win_loss_ratio': win_loss_ratio,
            'total_pnl': total_pnl,
            'profit_factor': profit_factor,
            'avg_duration': df['duration_seconds'].mean()
        }

risk_manager = RiskManager(risk_percent_per_trade=2.0)
