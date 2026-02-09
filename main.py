"""
BYSE ULTIMATE с поддержкой режимов
"""

import logging
import asyncio
import sys
from config import LEVERAGE
from bot import create_bot, start_bot_async, TRADING_STATE
from exchange import sync_time_with_exchange
from neural_network import init_lstm_model, switch_lstm_symbol
from telegram_utils import send_telegram_message

from coin_selector import coin_selector
from auto_leverage_manager import auto_leverage_manager
from auto_balance_manager import auto_balance_manager
from fully_autonomous_trader import fully_autonomous_trader
from performance_tracker import performance_tracker
from mode_manager import mode_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('byse.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

async def autonomous_trading_loop():
    """🤖 Основной цикл торговли"""
    await fully_autonomous_trader.autonomous_trading_cycle()

async def ai_optimization_loop():
    """🧠 Цикл оптимизации"""
    counter = 0
    while True:
        try:
            counter += 1
            
            # Только в автономном режиме
            if not mode_manager.is_autonomous_mode():
                await asyncio.sleep(60)
                continue
            
            # Каждый час — подстройка плеча
            if counter % 60 == 0:
                import config
                auto_leverage_manager.auto_adjust_leverage(config.SYMBOL)
            
            # Каждые 4 часа — рекомендации
            if counter % 240 == 0:
                recommendation = performance_tracker.get_recommendation()
                logger.info(recommendation)
                send_telegram_message(recommendation)
            
            # Каждые 6 часов — смена монеты + переобучение LSTM
            if counter % 360 == 0:
                try:
                    import config
                    from state_manager import state_manager
                    
                    logger.info("🔄 Переоценка лучшей монеты...")
                    best_coins = coin_selector.select_best_coins()
                    
                    if best_coins:
                        new_symbol = best_coins[0]['symbol']
                        old_symbol = config.SYMBOL
                        
                        if new_symbol != old_symbol:
                            config.SYMBOL = new_symbol
                            state_manager.set_symbol(new_symbol)
                            
                            # ✨ ПЕРЕОБУЧАЕМ LSTM НА НОВУЮ МОНЕТУ
                            logger.info(f"🧠 Переобучение LSTM: {old_symbol} → {new_symbol}")
                            lstm_ok = switch_lstm_symbol(new_symbol)
                            
                            status = "✅ LSTM переобучена" if lstm_ok else "⚠️ LSTM не переобучена"
                            
                            send_telegram_message(
                                f"🔄 Смена монеты: {old_symbol} → <b>{new_symbol}</b>\n"
                                f"Score: {best_coins[0]['potential_score']:.1f}/100\n"
                                f"{status}"
                            )
                        else:
                            logger.info(f"ℹ️ Лучшая монета не изменилась: {old_symbol}")
                            
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка смены монеты: {e}")
            
            # Каждые 24 часа — переоптимизация параметров
            if counter % 1440 == 0:
                try:
                    from auto_optimizer import AutoOptimizer
                    import config
                    optimizer = AutoOptimizer(config.SYMBOL)
                    params = optimizer.run_full_optimization()
                    logger.info("✅ Параметры переоптимизированы")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка переоптимизации: {e}")
            
            await asyncio.sleep(60)
        
        except Exception as e:
            logger.error(f"❌ Ошибка цикла оптимизации: {e}")
            await asyncio.sleep(60)

async def main():
    """Главная функция"""
    logger.info("🚀🤖 Запуск BYSE ULTIMATE с поддержкой режимов...")
    send_telegram_message("""🚀🤖 <b>BYSE ULTIMATE - С ПОДДЕРЖКОЙ РЕЖИМОВ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 АВТОНОМНЫЙ режим - БОТ САМ ТОРГУЕТ
🎮 РУЧНОЙ режим - ВЫ УПРАВЛЯЕТЕ
🔄 ПЕРЕКЛЮЧЕНИЕ по команде /modes""")

    logger.info("⏱️ Синхронизация времени...")
    if not sync_time_with_exchange():
        logger.error("❌ Синхронизация не удалась")
    
    await asyncio.sleep(2)

    # Сначала выбираем монету, потом обучаем LSTM на ней
    logger.info("🤖 Инициализация модулей...")
    
    try:
        # 🔍 Сначала проверяем есть ли открытая позиция на бирже
        logger.info("🔍 Проверка открытых позиций на бирже...")
        from exchange import exchange as _exchange
        import config
        from state_manager import state_manager
        
        existing_position = None
        try:
            all_positions = _exchange.fetch_positions()
            active_positions = [p for p in all_positions if float(p.get('contracts', 0)) > 0]
            if active_positions:
                existing_position = active_positions[0]
                pos_symbol = existing_position['symbol']
                pos_size = float(existing_position['contracts'])
                pos_side = existing_position['side']
                pos_entry = existing_position.get('entryPrice', 0)
                logger.info(f"📍 Найдена открытая позиция: {pos_symbol} | {pos_side} {pos_size} @ ${pos_entry}")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки позиций: {e}")
        
        if existing_position:
            # Есть открытая позиция — НЕ меняем монету!
            pos_symbol = existing_position['symbol']
            config.SYMBOL = pos_symbol
            state_manager.set_symbol(pos_symbol)
            logger.info(f"⚠️ Открытая позиция на {pos_symbol} — продолжаем мониторить!")
            send_telegram_message(
                f"📍 <b>Найдена открытая позиция!</b>\n"
                f"Пара: {pos_symbol}\n"
                f"Направление: {existing_position['side']}\n"
                f"Размер: {float(existing_position['contracts']):.4f}\n"
                f"Вход: ${existing_position.get('entryPrice', 0)}\n"
                f"⚠️ Продолжаю мониторинг (монета НЕ меняется)"
            )
        else:
            # Нет позиции — выбираем лучшую монету
            logger.info("📊 Выбор лучшей монеты...")
            best_coins = coin_selector.select_best_coins()
            
            if best_coins:
                best_coin = best_coins[0]['symbol']
                config.SYMBOL = best_coin
                state_manager.set_symbol(best_coin)
                send_telegram_message(f"🎯 ИИ выбрал: <b>{best_coin}</b>\nScore: {best_coins[0]['potential_score']:.1f}/100")
                logger.info(f"✅ Выбрана монета: {best_coin}")
        
        # ✨ Теперь инициализируем LSTM на выбранной монете
        logger.info(f"🧠 Инициализация LSTM для {config.SYMBOL}...")
        lstm_ok = init_lstm_model()
        if lstm_ok:
            send_telegram_message(f"✅ LSTM инициализирована для {config.SYMBOL}")
        else:
            send_telegram_message(f"⚠️ LSTM не удалось инициализировать для {config.SYMBOL}")
        
        logger.info("🔧 Подстройка плеча...")
        auto_leverage_manager.auto_adjust_leverage(config.SYMBOL)
        
        # Показываем текущий режим
        mode_status = mode_manager.get_mode_status()
        send_telegram_message(mode_status)
    
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации: {e}")

    app = create_bot()
    
    if app is None:
        logger.critical("❌ Не удалось создать Telegram приложение!")
        sys.exit(1)

    trading_task = asyncio.create_task(autonomous_trading_loop())
    optimization_task = asyncio.create_task(ai_optimization_loop())
    bot_task = asyncio.create_task(start_bot_async(app))

    try:
        await asyncio.gather(trading_task, optimization_task, bot_task)
    
    except KeyboardInterrupt:
        logger.info("⏹ Остановка...")
        send_telegram_message("🛑 BYSE остановлен")
        trading_task.cancel()
        optimization_task.cancel()
        bot_task.cancel()
        try:
            await asyncio.gather(trading_task, optimization_task, bot_task, return_exceptions=True)
        except:
            pass
        sys.exit(0)
    
    except Exception as e:
        logger.critical(f"❌ Критическая ошибка: {e}")
        send_telegram_message(f"🛑 BYSE УПАЛ: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Приложение остановлено")
        send_telegram_message("🛑 BYSE остановлен пользователем")
