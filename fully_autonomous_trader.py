"""
Полностью автономный торговец с поддержкой режимов и стратегий
"""

import logging
import asyncio
from datetime import datetime
from config import MODE
from exchange import get_balance_usdt, get_position, fetch_ohlcv_df
from trading_logic import place_buy, place_sell, place_short, place_close_short, calculate_profit_pct
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
        self.last_coin_change_time = 0
        self.price_history = []
        self.consecutive_waits = 0
    
    async def autonomous_trading_cycle(self):
        """Основной цикл с автоматической сменой стратегий"""
        logger.info("🤖 Запуск полностью автономного торговца...")
        
        strategy_check_counter = 0
        self.last_coin_change_time = asyncio.get_event_loop().time()
        
        while True:
            try:
                # КАЖДЫЕ 5 МИНУТ ПРОВЕРЯЕМ СТРАТЕГИЮ
                strategy_check_counter += 1
                if strategy_check_counter >= 5:
                    logger.info("🔍 Проверка оптимальности текущей стратегии...")
                    
                    stats = trade_db.get_statistics(symbol=config.SYMBOL, days=7)
                    
                    strategy_changed = strategy_manager.auto_adjust_strategy(
                        config.SYMBOL,
                        performance_stats=stats
                    )
                    
                    if strategy_changed:
                        msg = f"""🔄 <b>СМЕНА ��ТРАТЕГИИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{strategy_manager.get_current_strategy_info()}"""
                        send_telegram_message(msg)
                    
                    strategy_check_counter = 0
                
                # ПРОВЕРКА ДВИЖЕНИЯ ЦЕНЫ И АВТОСМЕНА МОНЕТЫ
                df = fetch_ohlcv_df()
                if df is not None and len(df) > 0:
                    current_price = df['close'].iloc[-1]
                    self.price_history.append(current_price)
                    
                    if len(self.price_history) > 30:
                        self.price_history.pop(0)
                    
                    current_time = asyncio.get_event_loop().time()
                    time_since_change = (current_time - self.last_coin_change_time) / 60
                    
                    # Смена монеты только когда НЕТ открытой позиции
                    size, _, _, _ = get_position()
                    if time_since_change >= 30 and len(self.price_history) >= 30 and size == 0:
                        price_range = max(self.price_history) - min(self.price_history)
                        volatility_pct = (price_range / current_price) * 100
                        
                        logger.info(f"📊 Волатильность за 30 мин: {volatility_pct:.2f}%")
                        
                        if volatility_pct < 2.0:
                            logger.warning(
                                f"⚠️ Нет движений 30 минут (волатильность {volatility_pct:.2f}%), "
                                f"меняю монету"
                            )
                            
                            from coin_selector import coin_selector
                            from state_manager import state_manager
                            
                            best_coins = coin_selector.select_best_coins()
                            if best_coins and len(best_coins) > 1:
                                coin_changed = False
                                for coin in best_coins:
                                    if coin['symbol'] != config.SYMBOL:
                                        new_coin = coin['symbol']
                                        old_coin = config.SYMBOL
                                        
                                        config.SYMBOL = new_coin
                                        state_manager.set_symbol(new_coin)
                                        
                                        try:
                                            from neural_network import switch_lstm_symbol
                                            lstm_ok = switch_lstm_symbol(new_coin)
                                            lstm_status = "✅ LSTM переобучена" if lstm_ok else "⚠️ LSTM без переобучения"
                                        except Exception as e:
                                            lstm_status = f"⚠️ LSTM ошибка: {e}"
                                        
                                        msg = f"""🔄 <b>АВТОСМЕНА МОНЕТЫ (НЕТ ДВИЖЕНИЯ)</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Старая: {old_coin}
  └─ Волатильность: {volatility_pct:.2f}% (< 2%)

Новая: {new_coin}
  └─ Score: {coin['potential_score']:.1f}/100
  └─ Объём: ${coin['volume']:,.0f}

{lstm_status}"""
                                        
                                        send_telegram_message(msg)
                                        self.last_coin_change_time = current_time
                                        self.price_history = []
                                        self.consecutive_waits = 0
                                        coin_changed = True
                                        break
                                
                                if not coin_changed:
                                    self.last_coin_change_time = current_time
                                    self.price_history = []
                
                # ПРОВЕРЯЕМ РЕЖИМ
                if not mode_manager.is_autonomous_mode():
                    await self._handle_manual_mode()
                    await asyncio.sleep(60)
                    continue
                
                # АВТОНОМНЫЙ РЕЖИМ
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
                    # === ПОЗИЦИЯ ОТКРЫТА — ПРОВЕРЯЕМ ВЫХОД ===
                    self.consecutive_waits = 0
                    
                    df = fetch_ohlcv_df()
                    if df is not None and len(df) > 0:
                        current_price = df['close'].iloc[-1]
                        
                        # Определяем цену входа
                        # Приоритет: self.entry_price > avg_price из биржи
                        entry = self.entry_price if self.entry_price and self.entry_price > 0 else avg_price

                        if entry and entry > 0:
                            # ИСПРАВЛЕНО: используем calculate_profit_pct с учётом направления позиции
                            profit_pct = calculate_profit_pct(entry, current_price, side)

                            logger.info(
                                f"📍 Позиция: {side} {size:.4f} | "
                                f"Вход: ${entry:.8f} | "
                                f"Текущая: ${current_price:.8f} | "
                                f"P&L: {profit_pct:+.2f}% (${upnl:+.4f})"
                            )
                            
                            exit_conditions = smart_signal_generator.analyze_exit_conditions(
                                config.SYMBOL, entry, current_price, side
                            )

                            if exit_conditions['should_exit']:
                                if exit_conditions['exit_percent'] == 100:
                                    await self._execute_exit(current_price, size, exit_conditions['exit_type'], side)
                                    self.current_position = None
                                    self.entry_price = None
                                    self.entry_time = None
                                else:
                                    exit_amount = size * (exit_conditions['exit_percent'] / 100)
                                    await self._execute_partial_exit(current_price, exit_amount, exit_conditions['exit_type'], side)
                        else:
                            logger.warning(
                                f"⚠️ Позиция открыта ({side} {size:.4f}) но нет цены входа! "
                                f"avg_price={avg_price}, self.entry_price={self.entry_price}"
                            )
                            # Пытаемся восстановить цену входа из avg_price
                            if avg_price and avg_price > 0:
                                self.entry_price = avg_price
                                logger.info(f"✅ Цена входа восстановлена из биржи: ${avg_price:.8f}")
                            else:
                                # Берём текущую цену как входную (не идеально, но лучше чем ничего)
                                self.entry_price = current_price
                                logger.warning(f"⚠️ Используем текущую цену как входную: ${current_price:.8f}")
                    else:
                        logger.warning("⚠️ Не удалось получить данные OHLCV для проверки выхода")
                
                else:
                    # === ПОЗИЦИЯ ЗАКРЫТА — ИЩЕМ ВХОД ===
                    logger.info("🔍 Позиция закрыта, ищу точку входа...")
                    entry_conditions = smart_signal_generator.analyze_entry_conditions(config.SYMBOL)
                    
                    # Порог из стратегии
                    current_strategy = strategy_manager.STRATEGIES.get(
                        strategy_manager.current_strategy, {}
                    )
                    entry_threshold = current_strategy.get('entry_threshold', 45)
                    
                    # Адаптивное снижение порога
                    if self.consecutive_waits > 10:
                        reduction = min((self.consecutive_waits - 10) // 10 * 3, 15)
                        entry_threshold = max(30, entry_threshold - reduction)
                        
                        if self.consecutive_waits % 10 == 0:
                            logger.info(
                                f"📉 Адаптивный порог: снижен до {entry_threshold} "
                                f"(ожиданий: {self.consecutive_waits})"
                            )
                    
                    if entry_conditions['is_good_to_buy'] and entry_conditions['confidence'] >= entry_threshold:
                        position_size_usdt = auto_balance_manager.calculate_safe_position_size(config.SYMBOL)
                        await self._execute_entry(entry_conditions['entry_price'], position_size_usdt)
                        self.entry_price = entry_conditions['entry_price']
                        self.entry_time = datetime.now()
                        self.current_position = True
                        self.consecutive_waits = 0
                    else:
                        self.consecutive_waits += 1
                        logger.info(
                            f"⏳ Ожидание: уверенность {entry_conditions['confidence']}% "
                            f"(порог {entry_threshold}%) "
                            f"[ожиданий: {self.consecutive_waits}]"
                        )
                        
                        # Каждые 2 часа (120 ожиданий) меняем монету если не можем войти
                        if self.consecutive_waits >= 120 and self.consecutive_waits % 120 == 0:
                            try:
                                from coin_selector import coin_selector
                                from state_manager import state_manager
                                
                                best_coins = coin_selector.select_best_coins()
                                if best_coins:
                                    for coin in best_coins:
                                        if coin['symbol'] != config.SYMBOL:
                                            old_coin = config.SYMBOL
                                            new_coin = coin['symbol']
                                            config.SYMBOL = new_coin
                                            state_manager.set_symbol(new_coin)
                                            
                                            try:
                                                from neural_network import switch_lstm_symbol
                                                switch_lstm_symbol(new_coin)
                                            except:
                                                pass
                                            
                                            send_telegram_message(
                                                f"🔄 Смена монеты (долгое ожидание):\n"
                                                f"{old_coin} → <b>{new_coin}</b>\n"
                                                f"Score: {coin['potential_score']:.1f}/100"
                                            )
                                            self.consecutive_waits = 0
                                            self.price_history = []
                                            break
                            except Exception as e:
                                logger.warning(f"⚠️ Ошибка смены монеты: {e}")
                
                await asyncio.sleep(60)
            
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле торговли: {e}")
                import traceback
                logger.error(traceback.format_exc())
                await asyncio.sleep(10)
    
    async def _handle_manual_mode(self):
        """Обработка ручного режима"""
        try:
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
            order = place_buy(price)
            
            if order:
                msg = f"""🟢 <b>АВТОМАТИЧЕСКИЙ ВХОД</b>
━━━━━━━━━━━━━━━━━━━━━━
Пара: {config.SYMBOL}
Цена: ${price:.8f}
Размер: ${position_size_usdt:.2f}
Стратегия: {strategy_manager.STRATEGIES[strategy_manager.current_strategy]['name']}
Вр��мя: {datetime.now().strftime('%H:%M:%S')}"""
                send_telegram_message(msg)
            else:
                logger.error("❌ Ордер на покупку не исполнен!")
                self.current_position = None
                self.entry_price = None
        except Exception as e:
            logger.error(f"❌ Ошибка входа: {e}")
    
    async def _execute_exit(self, price, amount, exit_type, side):
        """Выполняет выход"""
        try:
            logger.info(f"💔 ВЫХОД ({exit_type}): {config.SYMBOL} {side} @ ${price:.8f}")

            # Выбираем правильную функцию в зависимости от направления позиции
            if side == 'Buy':
                # Закрытие LONG позиции
                order = place_sell()
            elif side == 'Sell':
                # Закрытие SHORT позиции
                order = place_close_short()
            else:
                logger.error(f"❌ Неизвестное направление позиции: {side}")
                return

            profit = 0
            if self.entry_price and self.entry_price > 0:
                # Используем правильную формулу для расчёта прибыли
                profit = calculate_profit_pct(self.entry_price, price, side)

            if order:
                msg = f"""🔴 <b>АВТОМАТИЧЕСКИЙ ВЫХОД</b>
━━━━━━━━━━━━━━━━━━━━━━
Пара: {config.SYMBOL}
Направление: {side}
Тип: {exit_type}
Цена входа: ${self.entry_price:.8f if self.entry_price else 0:.8f}
Цена выхода: ${price:.8f}
Прибыль: {profit:+.2f}%
Время: {datetime.now().strftime('%H:%M:%S')}"""
                send_telegram_message(msg)
            else:
                logger.error("❌ Ордер на закрытие не исполнен!")
        except Exception as e:
            logger.error(f"❌ Ошибка выхода: {e}")
    
    async def _execute_partial_exit(self, price, amount, exit_type, side):
        """Выполняет частичный выход"""
        try:
            logger.info(f"⚪ ЧАСТИЧНЫЙ ВЫХОД ({exit_type}): {side} {amount:.4f} @ ${price:.8f}")

            # Для частичного выхода передаём конкретное количество
            from state_manager import state_manager
            symbol = state_manager.get_symbol()

            market_info = exchange.market(symbol)
            precision = market_info['precision']['amount']

            if isinstance(precision, float) and precision < 1:
                import math
                decimal_places = max(0, -int(math.floor(math.log10(precision))))
                amount = round(amount, decimal_places)
            else:
                amount = round(amount, int(precision))

            # Выбираем правильную операцию в зависимости от направления
            from exchange import exchange
            if side == 'Buy':
                # Частичное закрытие LONG = продажа части
                order = exchange.create_market_sell_order(symbol=symbol, amount=amount)
            elif side == 'Sell':
                # Частичное закрытие SHORT = покупка части
                order = exchange.create_market_buy_order(symbol=symbol, amount=amount)
            else:
                logger.error(f"❌ Неизвестное направление позиции: {side}")
                return

            if order:
                msg = f"""⚪ <b>ЧАСТИЧНЫЙ ВЫХОД</b>
━━━━━━━━━━━━━━━━━━━━━━
Направление: {side}
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
                place_sell()
        except:
            pass
        
        send_telegram_message("🚨 BYSE ЭКСТРЕННАЯ ОСТАНОВКА")
    
    def get_autonomous_status(self):
        """Получает статус"""
        try:
            free, total = get_balance_usdt()
            size, side, avg, upnl = get_position()

            mode_text = "🤖 АВТОНОМНЫЙ" if mode_manager.is_autonomous_mode() else "🎮 РУЧНОЙ"
            strategy_text = strategy_manager.STRATEGIES[strategy_manager.current_strategy]['name']

            entry = self.entry_price if self.entry_price else avg

            # ИСПРАВЛЕНО: используем правильную формулу в зависимости от направления
            if entry and entry > 0 and size > 0 and side:
                profit_pct = calculate_profit_pct(entry, avg, side)
            else:
                profit_pct = 0

            return f"""
╔════════════════════════════════════════════════════════════╗
║           📊 СТАТУС ТРЕЙДЕРА                               ║
╠════════════════════════════════════════════════════════════╣
║ <b>Режим:</b> {mode_text}
║ <b>Стратегия:</b> {strategy_text}
║ <b>Пара:</b> {config.SYMBOL}
║ <b>Позиция:</b> {side or 'НЕТ'} {size:.4f}
║ <b>Вход:</b> ${entry:.8f if entry else 0:.8f}
║ <b>P&L:</b> {upnl:+.4f} USDT ({profit_pct:+.2f}%)
║ <b>Баланс:</b> ${total:.2f}
║ <b>Свободно:</b> ${free:.2f}
║ <b>Ожиданий:</b> {self.consecutive_waits}
╚════════════════════════════════════════════════════════════╝
"""
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса: {e}")
            return f"❌ Ошибка: {e}"


fully_autonomous_trader = FullyAutonomousTrader()
