"""
Полностью автономный торговец с поддержкой режимов и стратегий
"""

import logging
import asyncio
from datetime import datetime
from config import MODE
from exchange import get_balance_usdt, get_position, fetch_ohlcv_df
from trading_logic import place_buy, place_sell
from auto_balance_manager import auto_balance_manager
from smart_signals import smart_signal_generator
from telegram_utils import send_telegram_message
from trade_database import trade_db
from mode_manager import mode_manager
from strategy_manager import strategy_manager
import config

logger = logging.getLogger(__name__)

class FullyAutonomousTrader:
    """Полностью автономный трейдер с режимами и стратегиями"""
    
    def __init__(self):
        self.current_position = None
        self.entry_price = None
        self.entry_time = None
        self.last_leverage_adjustment = 0
    
    async def autonomous_trading_cycle(self):
        """Основной цикл с автоматической сменой стратегий"""
        logger.info("🤖 Запуск полностью автономного торговца...")
        
        strategy_check_counter = 0
        
        while True:
            try:
                # КАЖДЫЕ 5 МИНУТ ПРОВЕРЯЕМ СТРАТЕГИЮ
                strategy_check_counter += 1
                if strategy_check_counter >= 5:
                    logger.info("🔍 Проверка оптимальности текущей стратегии...")
                    
                    # Получаем статистику производительности
                    stats = trade_db.get_statistics(symbol=config.SYMBOL, days=7)
                    
                    # Автоматически подстраиваем стратегию
                    strategy_changed = strategy_manager.auto_adjust_strategy(
                        config.SYMBOL,
                        performance_stats=stats
                    )
                    
                    if strategy_changed:
                        msg = f"""🔄 <b>СМЕНА СТРАТЕГИИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{strategy_manager.get_current_strategy_info()}"""
                        send_telegram_message(msg)
                    
                    strategy_check_counter = 0
                
                # ПРОВЕРЯЕМ РЕЖИМ
                if not mode_manager.is_autonomous_mode():
                    # В ручном режиме - проверяем ручные команды
                    await self._handle_manual_mode()
                    await asyncio.sleep(60)
                    continue
                
                # В автономном режиме - стандартный цикл
                health_ok, health_status = auto_balance_manager.check_balance_health()
                
                if not health_ok:
                    logger.critical(f"⚠️ КРИТИЧНОЕ СОСТОЯНИЕ: {health_status}")
                    await self._emergency_shutdown()
                    break
                
                current_time = asyncio.get_event_loop().time()
                if (current_time - self.last_leverage_adjustment) > 3600:
                    logger.info("🔧 Проверка оптимального плеча...")
                    from auto_leverage_manager import auto_leverage_manager
                    auto_leverage_manager.auto_adjust_leverage(config.SYMBOL)
                    self.last_leverage_adjustment = current_time
                
                # Получаем позицию
                size, side, avg_price, upnl = get_position()
                self.current_position = size > 0
                
                if self.current_position and size > 0:
                    # Позиция открыта - проверяем выход
                    logger.info(f"📍 Позиция открыта: {side} {size:.4f}")
                    
                    df = fetch_ohlcv_df()
                    if df is not None:
                        current_price = df['close'].iloc[-1]
                        
                        exit_conditions = smart_signal_generator.analyze_exit_conditions(
                            config.SYMBOL, avg_price, current_price
                        )
                        
                        if exit_conditions['should_exit']:
                            if exit_conditions['exit_percent'] == 100:
                                await self._execute_exit(current_price, size, exit_conditions['exit_type'])
                                self.current_position = None
                            else:
                                exit_amount = size * (exit_conditions['exit_percent'] / 100)
                                await self._execute_partial_exit(current_price, exit_amount, exit_conditions['exit_type'])
                
                else:
                    # Позиция закрыта - ищем вход
                    logger.info("🔍 Позиция закрыта, ищу точку входа...")
                    entry_conditions = smart_signal_generator.analyze_entry_conditions(config.SYMBOL)
                    
                    # Получаем порог входа из текущей стратегии
                    current_strategy = strategy_manager.STRATEGIES[strategy_manager.current_strategy]
                    entry_threshold = current_strategy['entry_threshold']
                    
                    if entry_conditions['is_good_to_buy'] and entry_conditions['confidence'] >= entry_threshold:
                        position_size_usdt = auto_balance_manager.calculate_safe_position_size(config.SYMBOL)
                        await self._execute_entry(entry_conditions['entry_price'], position_size_usdt)
                        self.entry_price = entry_conditions['entry_price']
                        self.entry_time = datetime.now()
                        self.current_position = True
                    else:
                        logger.info(
                            f"⏳ Ожида��ие лучших условий: "
                            f"уверенность {entry_conditions['confidence']}% "
                            f"(порог {entry_threshold}%)"
                        )
                
                await asyncio.sleep(60)
            
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле торговли: {e}")
                await asyncio.sleep(10)
    
    async def _handle_manual_mode(self):
        """Обработка ручного режима"""
        try:
            # Проверяем ручные сигналы
            if mode_manager.has_manual_buy_signal():
                price = mode_manager.manual_controls['entry_price']
                if price:
                    logger.info(f"🟢 Выполнение ручной покупки по {price}")
                    place_buy(price)
                    mode_manager.clear_manual_signals()
            
            if mode_manager.has_manual_sell_signal():
                price = mode_manager.manual_controls['exit_price']
                if price:
                    logger.info(f"🔴 Выполнение ручной продажи по {price}")
                    place_sell(price)
                    mode_manager.clear_manual_signals()
        except Exception as e:
            logger.error(f"❌ Ошибка в ручном режиме: {e}")
    
    async def _execute_entry(self, price, position_size_usdt):
        """Выполняет вход"""
        try:
            config.BASE_AMOUNT = int(position_size_usdt)
            logger.info(f"💚 ВХОД: {config.SYMBOL} @ ${price:.8f}")
            place_buy(price)
            
            msg = f"""🟢 <b>АВТОМАТИЧЕСКИЙ ВХОД</b>
━━━━━━━━━━━━━━━━━━━━━━
Пара: {config.SYMBOL}
Цена: ${price:.8f}
Размер: ${position_size_usdt:.2f}
Стратегия: {strategy_manager.STRATEGIES[strategy_manager.current_strategy]['name']}
Время: {datetime.now().strftime('%H:%M:%S')}"""
            
            send_telegram_message(msg)
        except Exception as e:
            logger.error(f"❌ Ошибка входа: {e}")
    
    async def _execute_exit(self, price, amount, exit_type):
        """Выполняет выход"""
        try:
            logger.info(f"💚 ВЫХОД ({exit_type}): {config.SYMBOL} @ ${price:.8f}")
            place_sell(price)
            
            profit = (price - self.entry_price) / self.entry_price * 100 if self.entry_price else 0
            
            msg = f"""🔴 <b>АВТОМАТИЧЕСКИЙ ВЫХОД</b>
━━━━━━━━━━━━━━━━━━━━━━
Пара: {config.SYMBOL}
Тип: {exit_type}
Цена входа: ${self.entry_price:.8f}
Цена выхода: ${price:.8f}
Прибыль: {profit:+.2f}%
Время: {datetime.now().strftime('%H:%M:%S')}"""
            
            send_telegram_message(msg)
        except Exception as e:
            logger.error(f"❌ Ошибка выхода: {e}")
    
    async def _execute_partial_exit(self, price, amount, exit_type):
        """Выполняет частичный выход"""
        try:
            logger.info(f"⚪ ЧАСТИЧНЫЙ ВЫХОД ({exit_type}): {amount:.4f} @ ${price:.8f}")
            msg = f"""⚪ <b>ЧАСТИЧНЫЙ ВЫХОД</b>
━━━━━━━━━━━━━━━━━━━━━━
Тип: {exit_type}
Количество: {amount:.4f}
Цена: ${price:.8f}
Время: {datetime.now().strftime('%H:%M:%S')}"""
            
            send_telegram_message(msg)
        except Exception as e:
            logger.error(f"❌ Ошибка частичного выхода: {e}")
    
    async def _emergency_shutdown(self):
        """Аварийная остановка"""
        logger.critical("🚨 ЭКСТРЕННОЕ ЗАВЕРШЕНИЕ!")
        try:
            size, side, _, _ = get_position()
            if size > 0:
                logger.warning(f"🔴 Закрытие позиции {size:.4f}...")
                place_sell(0)
        except:
            pass
        
        send_telegram_message("🚨 BYSE ЭКСТРЕННАЯ ОСТАНОВКА - КРИТИЧЕСКИЕ ОШИБКИ")
    
    def get_autonomous_status(self):
        """Получает статус"""
        try:
            free, total = get_balance_usdt()
            size, side, avg, upnl = get_position()
            
            mode_text = "🤖 АВТОНОМНЫЙ" if mode_manager.is_autonomous_mode() else "🎮 РУЧНОЙ"
            strategy_text = strategy_manager.STRATEGIES[strategy_manager.current_strategy]['name']
            
            return f"""
╔════════════════════════════════════════════════════════════╗
║           📊 СТАТУС ТРЕЙДЕРА                               ║
╠════════════════════════════════════════════════════════════╣
║ <b>Режим:</b> {mode_text}
║ <b>Стратегия:</b> {strategy_text}
║ <b>Пара:</b> {config.SYMBOL}
║ <b>Позиция:</b> {side or 'НЕТ'} {size:.4f}
║ <b>P&L:</b> {upnl:+.4f} USDT
║ <b>Баланс:</b> ${total:.2f}
║ <b>Свободно:</b> ${free:.2f}
╚════════════════════════════════════════════════════════════╝
"""
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса: {e}")
            return f"❌ Ошибка: {e}"


fully_autonomous_trader = FullyAutonomousTrader()
