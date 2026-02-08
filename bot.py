"""
Telegram Bot с поддержкой FUTURES и SPOT режимов
"""

import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from config import TELEGRAM_TOKEN, LEVERAGE
from telegram_utils import send_telegram_message
from state_manager import state_manager  # ✨ ДОБАВЛЕНО
from exchange import (
    set_leverage, get_balance_usdt, get_position, get_pnl,
    fetch_ohlcv_df
)
from trading_logic import place_buy, place_sell
from mode_manager import mode_manager
from strategy_manager import strategy_manager

logger = logging.getLogger(__name__)

# 🔴 ГЛАВНОЕ: ТОРГОВЫЙ СТАТУС
TRADING_STATE = {'enabled': True}

# ===== РЕЖИМЫ И ПЕРЕКЛЮЧЕНИЕ =====

async def cmd_trading_modes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает кнопки выбора режима торговли"""
    keyboard = [
        [
            InlineKeyboardButton("📈 Фьючерсы (плечо)", callback_data='trade_futures'),
            InlineKeyboardButton("💰 Спот (без плеча)", callback_data='trade_spot')
        ],
        [
            InlineKeyboardButton("ℹ️ Статус", callback_data='trade_status')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = """<b>🔄 ВЫБЕРИТЕ РЕЖИМ ТОРГОВЛИ:</b>

📈 <b>Фьючерсы</b>
├─ Плечо 1-50x
├─ Выше прибыль
└─ Выше риск

💰 <b>Спот</b>
├─ Без плеча (1x)
├─ Стабильнее
└─ Ниже риск"""
    
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode='HTML')

async def trading_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора режима торговли"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'trade_futures':
        mode_manager.switch_trading_mode("FUTURES")
        msg = """📈 <b>ФЬЮЧЕРСЫ АКТИВИРОВАНЫ</b>
━━━━━━━━━━━━━━━━━━━━━━
✅ Плечо: включено
✅ Риск: выше
✅ Прибыль: выше"""
        await query.edit_message_text(text=msg, parse_mode='HTML')
        send_telegram_message(msg)
    
    elif query.data == 'trade_spot':
        mode_manager.switch_trading_mode("SPOT")
        msg = """💰 <b>СПОТ АКТИВИРОВАН</b>
━━━━━━━━━━━━━━━━━━━━━━
✅ Плечо: отключено (1x)
✅ Риск: ниже
✅ Стабильность: выше"""
        await query.edit_message_text(text=msg, parse_mode='HTML')
        send_telegram_message(msg)
    
    elif query.data == 'trade_status':
        status = mode_manager.get_mode_status()
        await query.edit_message_text(text=status, parse_mode='HTML')

async def cmd_switch_futures(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение на фьючерсы"""
    try:
        mode_manager.switch_trading_mode("FUTURES")
        
        current_symbol = state_manager.get_symbol()  # ✨ ИСПОЛЬЗУЕТ state_manager
        
        msg = f"""📈 <b>РЕЖИМ ФЬЮЧЕРСОВ АКТИВИРОВАН</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Торговля с плечом (1-50x)
✅ Символ: {current_symbol}
✅ Плечо: будет автоматически подстраиваться
✅ Риск выше, прибыль выше

⚙️ Команды:
/manual_leverage <1-50> - установить плечо
/status - статус"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
        send_telegram_message(msg)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cmd_switch_spot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение на спот"""
    try:
        mode_manager.switch_trading_mode("SPOT")
        
        current_symbol = state_manager.get_symbol()  # ✨ ИСПОЛЬЗУЕТ state_manager
        
        msg = f"""💰 <b>РЕЖИМ СПОТА АКТИВИРОВАН</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Обычная торговля БЕЗ плеча
✅ Символ: {current_symbol}
✅ Плечо: всегда 1x (отключено)
✅ Риск ниже, но стабильнее

⚙️ Команды:
/manual_amount <USDT> - размер позиции
/status - статус"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
        send_telegram_message(msg)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ===== СТРАТЕГИИ =====

async def cmd_strategies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все стратегии"""
    info = strategy_manager.get_all_strategies_info()
    await update.message.reply_text(info, parse_mode='HTML')

async def cmd_current_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Текущая стратегия"""
    info = strategy_manager.get_current_strategy_info()
    await update.message.reply_text(info, parse_mode='HTML')

async def cmd_set_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить стратегию вручную"""
    if not context.args:
        await update.message.reply_text(
            "📝 Использование: /set_strategy <название>\n\n"
            "Доступные:\n"
            "- ULTRA_CONSERVATIVE\n"
            "- CONSERVATIVE\n"
            "- BALANCED\n"
            "- MODERATE_AGGRESSIVE\n"
            "- AGGRESSIVE\n"
            "- ULTRA_AGGRESSIVE\n"
            "- SCALPING\n"
            "- SWING"
        )
        return
    
    strategy_name = context.args[0].upper()
    success = strategy_manager.switch_strategy(strategy_name, "Ручная установка")
    
    if success:
        info = strategy_manager.get_current_strategy_info()
        await update.message.reply_text(f"✅ Стратегия изменена!\n\n{info}", parse_mode='HTML')
    else:
        await update.message.reply_text("❌ Неверное название стратегии!")

# ===== ОСНОВНЫЕ КОМАНДЫ =====

async def cmd_modes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает кнопки переключения режимов (АВТОНОМНЫЙ/РУЧНОЙ)"""
    keyboard = [
        [
            InlineKeyboardButton("🤖 Автономный режим", callback_data='mode_autonomous'),
            InlineKeyboardButton("🎮 Ручной режим", callback_data='mode_manual')
        ],
        [
            InlineKeyboardButton("📊 Статус режима", callback_data='mode_status')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "<b>🔄 ВЫБЕРИТЕ РЕЖИМ УПРАВЛЕНИЯ:</b>\n\n"
        "🤖 <b>Автономный</b> - БОТ САМ ТОРГУЕТ\n"
        "🎮 <b>Ручной</b> - ВЫ УПРАВЛЯЕТЕ\n",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def mode_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок режимов (АВТОНОМНЫЙ/РУЧНОЙ)"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'mode_autonomous':
        report = mode_manager.switch_to_autonomous()
        await query.edit_message_text(text=report, parse_mode='HTML')
        send_telegram_message(report)
    
    elif query.data == 'mode_manual':
        report = mode_manager.switch_to_manual()
        await query.edit_message_text(text=report, parse_mode='HTML')
        send_telegram_message(report)
    
    elif query.data == 'mode_status':
        status = mode_manager.get_mode_status()
        await query.edit_message_text(text=status, parse_mode='HTML')

async def cmd_switch_autonomous(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Быстрое переключение на автономный режим"""
    report = mode_manager.switch_to_autonomous()
    await update.message.reply_text(report, parse_mode='HTML')
    send_telegram_message(report)

async def cmd_switch_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Быстрое переключение на ручной режим"""
    report = mode_manager.switch_to_manual()
    await update.message.reply_text(report, parse_mode='HTML')
    send_telegram_message(report)

async def cmd_mode_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус режима"""
    status = mode_manager.get_mode_status()
    await update.message.reply_text(status, parse_mode='HTML')

# ===== РУЧНОЙ РЕЖИМ КОМАНДЫ =====

async def cmd_manual_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручная покупка"""
    if not mode_manager.is_manual_mode():
        await update.message.reply_text(
            "❌ Ручной режим не активирован!\n\n"
            "Используйте /switch_manual для включения",
            parse_mode='HTML'
        )
        return
    
    try:
        if not context.args:
            await update.message.reply_text(
                "📝 Использование: /manual_buy <цена>\n"
                "Пример: /manual_buy 2500"
            )
            return
        
        price = float(context.args[0])
        current_symbol = state_manager.get_symbol()  # ✨ ИСПОЛЬЗУЕТ state_manager
        
        mode_manager.set_manual_buy(price=price)
        
        msg = f"""🟢 <b>РУЧНАЯ ПОКУПКА УСТАНОВЛЕНА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Пара: {current_symbol}
Цена: ${price:.8f}
Статус: ⏳ В ожидании исполнения"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
        send_telegram_message(msg)
    
    except ValueError:
        await update.message.reply_text("❌ Неверная цена! Используйте число")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cmd_manual_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручная продажа"""
    if not mode_manager.is_manual_mode():
        await update.message.reply_text(
            "❌ Ручной режим не активирован!\n\n"
            "Используйте /switch_manual для включения",
            parse_mode='HTML'
        )
        return
    
    try:
        if not context.args:
            await update.message.reply_text(
                "📝 Использование: /manual_sell <цена>\n"
                "��ример: /manual_sell 2600"
            )
            return
        
        price = float(context.args[0])
        current_symbol = state_manager.get_symbol()  # ✨ ИСПОЛЬЗУЕТ state_manager
        
        mode_manager.set_manual_sell(price=price)
        
        msg = f"""🔴 <b>РУЧНАЯ ПРОДАЖА УСТАНОВЛЕНА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Пара: {current_symbol}
Цена: ${price:.8f}
Статус: ⏳ В ожидании исполнения"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
        send_telegram_message(msg)
    
    except ValueError:
        await update.message.reply_text("❌ Неверная цена! Используйте число")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cmd_manual_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрыть позицию в ручном режиме"""
    if not mode_manager.is_manual_mode():
        await update.message.reply_text("❌ Ручной режим не активирован!")
        return
    
    try:
        current_symbol = state_manager.get_symbol()  # ✨ ИСПОЛЬЗУЕТ state_manager
        size, side, avg, upnl = get_position(current_symbol)
        
        if size <= 0:
            await update.message.reply_text("❌ Нет открытой позиции!")
            return
        
        df = fetch_ohlcv_df()
        current_price = df['close'].iloc[-1] if df is not None else 0
        
        place_sell(current_price)
        
        msg = f"""🔴 <b>ПОЗИЦИЯ ЗАКРЫТА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Пара: {current_symbol}
Сторона: {side}
Объём: {size:.4f}
Закрыто по: ${current_price:.8f}
P&L: ${upnl:+.2f}"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
        send_telegram_message(msg)
    
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cmd_manual_leverage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить плечо в ручном режиме"""
    if not mode_manager.is_manual_mode():
        await update.message.reply_text("❌ Ручной режим не активирован!")
        return
    
    if not mode_manager.is_futures_mode():
        await update.message.reply_text("❌ Плечо доступно только в режиме ФЬЮЧЕРСОВ!")
        return
    
    try:
        if not context.args:
            await update.message.reply_text(
                "📝 Использование: /manual_leverage <1-50>\n"
                "Пример: /manual_leverage 20"
            )
            return
        
        leverage = int(context.args[0])
        current_symbol = state_manager.get_symbol()  # ✨ ИСПОЛЬЗУЕТ state_manager
        
        if not (1 <= leverage <= 50):
            await update.message.reply_text("❌ Плечо должно быть от 1 до 50")
            return
        
        set_leverage(current_symbol, leverage)
        
        msg = f"""📊 <b>ПЛЕЧО УСТАНОВЛЕНО</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Плечо: {leverage}x
Пара: {current_symbol}
Статус: ✅ Применено"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
        send_telegram_message(msg)
    
    except ValueError:
        await update.message.reply_text("❌ Неверное значение плеча!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cmd_manual_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить размер позиции в ручном режиме"""
    if not mode_manager.is_manual_mode():
        await update.message.reply_text("❌ Ручной режим не активирован!")
        return
    
    try:
        if not context.args:
            await update.message.reply_text(
                "📝 Использование: /manual_amount <USDT>\n"
                "Пример: /manual_amount 1000"
            )
            return
        
        amount = float(context.args[0])
        
        if amount <= 0:
            await update.message.reply_text("❌ Размер должен быть больше 0")
            return
        
        import config
        config.BASE_AMOUNT = int(amount)
        mode_manager.manual_controls['position_size'] = amount
        
        msg = f"""💰 <b>РАЗМЕР ПОЗИЦИИ УСТАНОВЛЕН</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Размер: ${amount:.2f}
Статус: ✅ Применено"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
        send_telegram_message(msg)
    
    except ValueError:
        await update.message.reply_text("❌ Неверное значение суммы!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cmd_manual_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о текущей позиции"""
    try:
        current_symbol = state_manager.get_symbol()  # ✨ ИСПОЛЬЗУЕТ state_manager
        size, side, avg, upnl = get_position(current_symbol)
        free, total = get_balance_usdt()
        
        mode_text = "📈 ФЬЮЧЕРСЫ" if mode_manager.is_futures_mode() else "💰 СПОТ"
        
        if size > 0:
            msg = f"""📍 <b>ТЕКУЩАЯ ПОЗИЦИЯ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Режим: {mode_text}
Пара: {current_symbol}
Сторона: {side}
Объём: {size:.4f}
Ср. цена: ${avg:.8f}
P&L: ${upnl:+.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Баланс: ${total:.2f}
Свободно: ${free:.2f}"""
        else:
            msg = f"""📍 <b>ПОЗИЦИЯ НЕ ОТКРЫТА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Режим: {mode_text}
Пара: {current_symbol}
Баланс: ${total:.2f}
Свободно: ${free:.2f}"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
    
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ===== ОСНОВНЫЕ КОМАНДЫ =====

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главная команда"""
    keyboard = [
        [InlineKeyboardButton("🔄 Режимы торговли", callback_data='mode_status')],
        [InlineKeyboardButton("💱 Тип торговли (Futures/Spot)", callback_data='trade_status')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = """<b>🤖 BYSE ULTIMATE - Торговый бот</b>

<b>🎯 ГЛАВНЫЕ КОМАНДЫ:</b>
/modes - переключение режимов 🔴
/trading_modes - выбор торговли 🔴
/strategies - все стратегии 🔴
/switch_autonomous - автономный режим
/switch_manual - ручной режим
/switch_futures - фьючерсы
/switch_spot - спот

<b>📊 ИНФОРМАЦИЯ:</b>
/status - статус торговли
/balance - баланс
/pause / /resume - управление

<b>🎮 РУЧНОЙ РЕЖИМ:</b>
/manual_buy - покупка
/manual_sell - продажа
/manual_close - закрыть позицию
/manual_leverage - плечо
/manual_amount - размер позиции
/manual_position - информация"""
    
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode='HTML')

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус торговли"""
    try:
        current_symbol = state_manager.get_symbol()  # ✨ ИСПОЛЬЗУЕТ state_manager
        
        free, total = get_balance_usdt()
        size, side, avg, upnl = get_position(current_symbol)
        
        mode_text = "🤖 АВТОНОМНЫЙ" if mode_manager.is_autonomous_mode() else "🎮 РУЧНОЙ"
        trading_text = "📈 ФЬЮЧЕРСЫ" if mode_manager.is_futures_mode() else "💰 СПОТ"
        
        msg = f"""<b>📊 Статус торговли</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>Режим управления:</b> {mode_text}
<b>Тип торговли:</b> {trading_text}
<b>Пара:</b> {current_symbol}
<b>Торговля:</b> {'✅ ВКЛЮЧЕНА' if TRADING_STATE['enabled'] else '⏸️ НА ПАУЗЕ'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>💰 Баланс:</b>
  Всего: ${total:.2f}
  Свободно: ${free:.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>📍 Позиция:</b> {side or 'НЕТ'} {size:.4f}
<b>P&L:</b> ${upnl:+.2f}"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Баланс"""
    try:
        free, total = get_balance_usdt()
        unreal, real = get_pnl()
        
        msg = f"""<b>💰 Баланс</b>
━━━━━━━━━━━━━━━━━━━━━━━━
Всего: ${total:.2f}
Свободно: ${free:.2f}
━━━━━━━━━━━━━━━━━━━━━━━━
<b>P&L:</b>
  Нереал.: ${unreal:+.2f}
  Реал.: ${real:+.2f}"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пауза"""
    TRADING_STATE['enabled'] = False
    await update.message.reply_text("⏸️ <b>Торговля остановлена</b>", parse_mode='HTML')

async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возобновить"""
    TRADING_STATE['enabled'] = True
    await update.message.reply_text("▶️ <b>Торговля возобновлена</b>", parse_mode='HTML')

async def start_bot_async(app: Application):
    """Запуск бота"""
    try:
        if app is None:
            logger.error("❌ Application is None!")
            return
        
        async with app:
            await app.start()
            await app.updater.start_polling(allowed_updates=['message', 'callback_query'])
            logger.info("✅ Telegram бот запущен (polling)")
            
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                await app.updater.stop()
                await app.stop()
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram бота: {e}")

def create_bot() -> Application:
    """Создание бота"""
    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Основные команды
        application.add_handler(CommandHandler("start", cmd_start))
        application.add_handler(CommandHandler("status", cmd_status))
        application.add_handler(CommandHandler("balance", cmd_balance))
        application.add_handler(CommandHandler("pause", cmd_pause))
        application.add_handler(CommandHandler("resume", cmd_resume))
        
        # Режимы управления (АВТОНОМНЫЙ/РУЧНОЙ)
        application.add_handler(CommandHandler("modes", cmd_modes))
        application.add_handler(CommandHandler("switch_autonomous", cmd_switch_autonomous))
        application.add_handler(CommandHandler("switch_manual", cmd_switch_manual))
        application.add_handler(CommandHandler("mode_status", cmd_mode_status))
        
        # Типы торговли (FUTURES/SPOT)
        application.add_handler(CommandHandler("trading_modes", cmd_trading_modes))
        application.add_handler(CommandHandler("switch_futures", cmd_switch_futures))
        application.add_handler(CommandHandler("switch_spot", cmd_switch_spot))
        
        # Стратегии
        application.add_handler(CommandHandler("strategies", cmd_strategies))
        application.add_handler(CommandHandler("current_strategy", cmd_current_strategy))
        application.add_handler(CommandHandler("set_strategy", cmd_set_strategy))
        
        # Ручной режим
        application.add_handler(CommandHandler("manual_buy", cmd_manual_buy))
        application.add_handler(CommandHandler("manual_sell", cmd_manual_sell))
        application.add_handler(CommandHandler("manual_close", cmd_manual_close))
        application.add_handler(CommandHandler("manual_leverage", cmd_manual_leverage))
        application.add_handler(CommandHandler("manual_amount", cmd_manual_amount))
        application.add_handler(CommandHandler("manual_position", cmd_manual_position))
        
        # Обработчики кнопок
        application.add_handler(CallbackQueryHandler(mode_button_handler, pattern='^mode_'))
        application.add_handler(CallbackQueryHandler(trading_mode_handler, pattern='^trade_'))
        
        logger.info("✅ Telegram приложение создано")
        return application
    
    except Exception as e:
        logger.error(f"❌ Ошибка создания приложения: {e}")
        return None
