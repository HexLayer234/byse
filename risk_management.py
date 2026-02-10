"""
Управление рисками и динамический расчёт размера позиции (РУССКАЯ ВЕРСИЯ)
"""

import logging
import pandas as pd
from config import BASE_AMOUNT, LEVERAGE, STOP_LOSS_PERCENT
from exchange import get_balance_usdt, fetch_ohlcv_df

logger = logging.getLogger(__name__)

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
