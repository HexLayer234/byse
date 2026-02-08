"""
BYSE ULTIMATE с поддержкой режимов
"""

import logging
import asyncio
import sys
from config import LEVERAGE
from bot import create_bot, start_bot_async, TRADING_STATE
from exchange import sync_time_with_exchange
from neural_network import init_lstm_model
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
            
            if counter % 60 == 0:
                import config
                auto_leverage_manager.auto_adjust_leverage(config.SYMBOL)
            
            if counter % 240 == 0:
                recommendation = performance_tracker.get_recommendation()
                logger.info(recommendation)
                send_telegram_message(recommendation)
            
            if counter % 1440 == 0:
                try:
                    from auto_optimizer import AutoOptimizer
                    import config
                    optimizer = AutoOptimizer(config.SYMBOL)
                    params = optimizer.run_full_optimization()
                    logger.info("✅ Параметры переоптимизированы")
                except Exception as e:
                    logger.warning(f"��️ Ошибка переоптимизации: {e}")
            
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

    logger.info("🧠 Инициализация LSTM...")
    lstm_ok = init_lstm_model()
    if lstm_ok:
        send_telegram_message("✅ LSTM инициализирована")

    logger.info("🤖 Инициализация модулей...")
    
    try:
        logger.info("📊 Выбор лучшей монеты...")
        best_coins = coin_selector.select_best_coins()
        
        if best_coins:
            import config
            from state_manager import state_manager
            best_coin = best_coins[0]['symbol']
            config.SYMBOL = best_coin
            state_manager.set_symbol(best_coin)
            send_telegram_message(f"🎯 ИИ выбрал: <b>{best_coin}</b>\nScore: {best_coins[0]['potential_score']:.1f}/100")
            logger.info(f"✅ Выбрана монета: {best_coin}")
        
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
