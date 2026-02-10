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
from trailing_stop import trailing_stop_manager
import config

logger = logging.getLogger(__name__)

class FullyAutonomousTrader:
    """Полностью автономный трейдер с мультимонетной торговлей"""
    
    def __init__(self):
        self.current_position = None
        self.entry_price = None
        self.entry_time = None
        self.last_leverage_adjustment = 0
        self.last_coin_change_time = 0
        self.price_history = []
        self.consecutive_waits = 0
        
        # Мультимонетная торговля — позиции по каждой монете
        self.positions = {}  # {symbol: {entry_price, entry_time, size, side}}
        self.max_coins = getattr(config, 'MAX_COINS', 2)
        self.last_analysis = {}  # {symbol: {confidence, direction, reasons, timestamp}}
    
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
                    
                    if len(self.price_history) > 15:
                        self.price_history.pop(0)
                    
                    current_time = asyncio.get_event_loop().time()
                    time_since_change = (current_time - self.last_coin_change_time) / 60
                    
                    # Смена монеты когда НЕТ открытой позиции — проверяем чаще
                    size, _, _, _ = get_position()
                    if time_since_change >= 15 and len(self.price_history) >= 10 and size == 0:
                        price_range = max(self.price_history) - min(self.price_history)
                        volatility_pct = (price_range / current_price) * 100
                        
                        logger.info(f"📊 Волатильность за {int(time_since_change)} мин: {volatility_pct:.2f}%")
                        
                        if volatility_pct < 1.5:
                            logger.warning(
                                f"⚠️ Нет движений {int(time_since_change)} мин (волатильность {volatility_pct:.2f}%), "
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
                
                # ===== МУЛЬТИМОНЕТНАЯ ТОРГОВЛЯ =====
                # Получаем все открытые позиции с биржи
                try:
                    from exchange import exchange as _exchange
                    all_positions = _exchange.fetch_positions()
                    active_positions = {
                        p['symbol']: p for p in all_positions 
                        if float(p.get('contracts', 0)) > 0
                    }
                except Exception as e:
                    logger.debug(f"⚠️ Ошибка получения позиций: {e}")
                    active_positions = {}
                
                # Обновляем словарь positions + актуализируем size из биржи
                for sym, pos in active_positions.items():
                    real_size = float(pos.get('contracts', 0))
                    if sym not in self.positions:
                        self.positions[sym] = {
                            'entry_price': float(pos.get('entryPrice', 0)),
                            'entry_time': datetime.now(),
                            'size': real_size,
                            'side': pos.get('side', 'long')
                        }
                    else:
                        # Обновляем size из биржи (актуальный)
                        self.positions[sym]['size'] = real_size
                
                # Убираем закрытые
                closed = [s for s in self.positions if s not in active_positions]
                for s in closed:
                    del self.positions[s]
                
                open_count = len(active_positions)
                self.current_position = open_count > 0
                
                # === 1. МОНИТОРИНГ ОТКРЫТЫХ ПОЗИЦИЙ ===
                for sym, pos_data in list(self.positions.items()):
                    try:
                        # Получаем данные для этой монеты
                        candles = _exchange.fetch_ohlcv(sym, config.TIMEFRAME, limit=100)
                        if not candles:
                            continue
                        import pandas as pd
                        df_sym = pd.DataFrame(candles, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
                        current_price = df_sym['close'].iloc[-1]
                        
                        entry = pos_data['entry_price']
                        size = pos_data['size']
                        
                        if entry and entry > 0:
                            profit_pct = ((current_price - entry) / entry) * 100
                            
                            # Trailing stop
                            trailing_stop_manager.update_trailing_stop(sym, current_price)
                            ts_stats = trailing_stop_manager.get_stats(sym)
                            ts_info = f" | Trail: ${ts_stats['trailing_stop']:.8f}" if ts_stats else ""
                            
                            logger.info(
                                f"📍 [{sym}] {pos_data['side']} {size:.4f} | "
                                f"Вход: ${entry:.8f} | "
                                f"Текущая: ${current_price:.8f} | "
                                f"P&L: {profit_pct:+.2f}%{ts_info}"
                            )
                            
                            # Trailing stop сработал
                            if ts_stats and ts_stats['status'] == 'СРАБОТАЛ':
                                logger.warning(f"📉 Trailing stop для {sym}!")
                                old_symbol = config.SYMBOL
                                config.SYMBOL = sym
                                await self._execute_exit(current_price, size, 'TRAILING_STOP')
                                trailing_stop_manager.remove_position(sym)
                                config.SYMBOL = old_symbol
                            else:
                                # Проверка условий выхода
                                exit_conditions = smart_signal_generator.analyze_exit_conditions(
                                    sym, entry, current_price
                                )
                                if exit_conditions.get('should_exit'):
                                    old_symbol = config.SYMBOL
                                    config.SYMBOL = sym
                                    if exit_conditions['exit_percent'] == 100:
                                        await self._execute_exit(current_price, size, exit_conditions['exit_type'])
                                        trailing_stop_manager.remove_position(sym)
                                    else:
                                        exit_amount = size * (exit_conditions['exit_percent'] / 100)
                                        await self._execute_partial_exit(current_price, exit_amount, exit_conditions['exit_type'])
                                    config.SYMBOL = old_symbol
                    except Exception as e:
                        logger.error(f"❌ Ошибка мониторинга {sym}: {e}")
                
                # === 2. ПОИСК ВХОДА ДЛЯ НОВЫХ МОНЕТ ===
                if open_count < self.max_coins:
                    # Выбираем лучшие монеты для входа
                    from coin_selector import coin_selector
                    from state_manager import state_manager
                    
                    symbols_to_check = []
                    
                    # Текущий символ из конфига — всегда первый кандидат
                    symbols_to_check.append(config.SYMBOL)
                    
                    # Если нужна ещё одна монета — берём из рейтинга
                    if open_count < self.max_coins:
                        try:
                            best_coins = coin_selector.select_best_coins()
                            for coin in best_coins:
                                if coin['symbol'] not in active_positions and coin['symbol'] not in symbols_to_check:
                                    symbols_to_check.append(coin['symbol'])
                                    if len(symbols_to_check) >= self.max_coins:
                                        break
                        except Exception as e:
                            logger.debug(f"⚠️ Ошибка выбора монет: {e}")
                    
                    entered_this_cycle = False
                    for sym in symbols_to_check:
                        if sym in active_positions:
                            continue
                        if open_count >= self.max_coins:
                            break
                        
                        logger.info(f"🔍 [{sym}] Ищу точку входа...")
                        
                        # Временно переключаем символ для анализа
                        old_symbol = config.SYMBOL
                        config.SYMBOL = sym
                        
                        try:
                            entry_conditions = smart_signal_generator.analyze_entry_conditions(sym)
                            
                            current_strategy = strategy_manager.STRATEGIES.get(
                                strategy_manager.current_strategy, {}
                            )
                            entry_threshold = current_strategy.get('entry_threshold', 45)
                            
                            # Адаптивное снижение — быстрее и агрессивнее
                            if self.consecutive_waits > 5:
                                reduction = min((self.consecutive_waits - 5) // 3 * 3, 20)
                                entry_threshold = max(15, entry_threshold - reduction)
                            
                            # Сохраняем результат анализа для /status
                            self.last_analysis[sym] = {
                                'confidence': entry_conditions.get('confidence', 0),
                                'direction': entry_conditions.get('direction', 'NEUTRAL'),
                                'is_good_to_buy': entry_conditions.get('is_good_to_buy', False),
                                'is_good_to_short': entry_conditions.get('is_good_to_short', False),
                                'reasons': entry_conditions.get('reasons', []),
                                'entry_threshold': entry_threshold,
                                'timestamp': datetime.now().isoformat()
                            }
                            
                            # Также проверяем SHORT сигнал
                            is_entry = (
                                (entry_conditions.get('is_good_to_buy') and entry_conditions['confidence'] >= entry_threshold) or
                                (entry_conditions.get('is_good_to_short') and entry_conditions['confidence'] >= entry_threshold)
                            )
                            entry_direction = entry_conditions.get('direction', 'LONG')
                            
                            if is_entry:
                                # Делим баланс только между СВОБОДНЫМИ слотами
                                free_slots = max(self.max_coins - open_count, 1)
                                position_size_usdt = auto_balance_manager.calculate_safe_position_size(sym)
                                position_size_usdt = position_size_usdt / free_slots
                                
                                state_manager.set_symbol(sym)
                                
                                pos_side = 'short' if entry_direction == 'SHORT' else 'long'
                                
                                order = None
                                if pos_side == 'short':
                                    from trading_logic import place_short
                                    config.BASE_AMOUNT = int(position_size_usdt)
                                    order = place_short(entry_conditions['entry_price'])
                                else:
                                    config.BASE_AMOUNT = int(position_size_usdt)
                                    from trading_logic import place_long
                                    order = place_long(entry_conditions['entry_price'])
                                
                                # Получаем реальный размер из ордера
                                real_size = 0
                                if order:
                                    real_size = float(order.get('filled', 0) or order.get('amount', 0) or 0)
                                
                                # Если ордер лимитный — может ещё не исполниться, берём из биржи
                                if real_size == 0:
                                    try:
                                        import time
                                        time.sleep(2)  # Ждём исполнения лимитного ордера
                                        pos_size, _, _, _ = get_position(sym)
                                        real_size = pos_size
                                    except:
                                        real_size = position_size_usdt / entry_conditions['entry_price']
                                
                                self.positions[sym] = {
                                    'entry_price': entry_conditions['entry_price'],
                                    'entry_time': datetime.now(),
                                    'size': real_size,
                                    'side': pos_side
                                }
                                trailing_stop_manager.register_position(sym, entry_conditions['entry_price'])
                                
                                self.entry_price = entry_conditions['entry_price']
                                self.entry_time = datetime.now()
                                self.consecutive_waits = 0
                                open_count += 1
                                entered_this_cycle = True
                                
                                side_icon = '🔴 SHORT' if pos_side == 'short' else '🟢 LONG'
                                send_telegram_message(
                                    f"{side_icon} <b>ВХОД [{open_count}/{self.max_coins}]</b>\n"
                                    f"Монета: {sym}\n"
                                    f"Цена: ${entry_conditions['entry_price']:.8f}\n"
                                    f"Размер: ${position_size_usdt:.2f}\n"
                                    f"Уверенность: {entry_conditions['confidence']}%"
                                )
                            else:
                                logger.info(
                                    f"⏳ [{sym}] уверенность {entry_conditions['confidence']}% "
                                    f"(порог {entry_threshold}%)"
                                )
                        except Exception as e:
                            logger.error(f"❌ Ошибка анализа {sym}: {e}")
                        finally:
                            config.SYMBOL = old_symbol
                    
                    if not entered_this_cycle:
                        self.consecutive_waits += 1
                    
                    # Смена монет при долгом ожидании (каждые 30 минут)
                    if self.consecutive_waits >= 30 and self.consecutive_waits % 30 == 0:
                        try:
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
                                            f"🔄 Смена монеты:\n"
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
    
    async def _execute_exit(self, price, amount, exit_type):
        """Выполняет выход"""
        try:
            logger.info(f"💔 ВЫХОД ({exit_type}): {config.SYMBOL} @ ${price:.8f}")
            order = place_sell()
            
            profit = 0
            if self.entry_price and self.entry_price > 0:
                profit = (price - self.entry_price) / self.entry_price * 100
            
            if order:
                entry_display = self.entry_price if self.entry_price else 0
                msg = f"""🔴 <b>АВТОМАТИЧЕСКИЙ ВЫХОД</b>
━━━━━━━━━━━━━━━━━━━━━━
Пара: {config.SYMBOL}
Тип: {exit_type}
Цена входа: ${entry_display:.8f}
Цена выхода: ${price:.8f}
Прибыль: {profit:+.2f}%
Время: {datetime.now().strftime('%H:%M:%S')}"""
                send_telegram_message(msg)
            else:
                logger.error("❌ Ордер на продажу не исполнен!")
        except Exception as e:
            logger.error(f"❌ Ошибка выхода: {e}")
    
    async def _execute_partial_exit(self, price, amount, exit_type):
        """Выполняет частичный выход"""
        try:
            logger.info(f"⚪ ЧАСТИЧНЫЙ ВЫХОД ({exit_type}): {amount:.4f} @ ${price:.8f}")
            
            # Для частичного выхода передаём конкретное количество
            from state_manager import state_manager
            from exchange import exchange as _exchange
            import math
            
            symbol = state_manager.get_symbol()
            
            market_info = _exchange.market(symbol)
            precision = market_info['precision']['amount']
            
            if isinstance(precision, float) and precision < 1:
                decimal_places = max(0, -int(math.floor(math.log10(precision))))
                amount = round(amount, decimal_places)
            else:
                amount = round(amount, int(precision))
            
            order = _exchange.create_market_sell_order(symbol=symbol, amount=amount)
            
            if order:
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
            profit_pct = ((avg - entry) / entry * 100) if entry and entry > 0 and size > 0 else 0
            
            entry_display = entry if entry else 0
            return f"""
╔════════════════════════════════════════════════════════════╗
║           📊 СТАТУС ТРЕЙДЕРА                               ║
╠════════════════════════════════════════════════════════════╣
║ <b>Режим:</b> {mode_text}
║ <b>Стратегия:</b> {strategy_text}
║ <b>Пара:</b> {config.SYMBOL}
║ <b>Позиция:</b> {side or 'НЕТ'} {size:.4f}
║ <b>Вход:</b> ${entry_display:.8f}
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
