# telegram_utils.py
"""
Утилиты для отправки Telegram сообщений
Поддержка как sync так и async режимов
"""

import logging
import threading
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

def send_telegram_message(text: str):
    """
    Отправляет сообщение в Telegram.
    Безопасно вызывать из любого контекста (sync/async).
    Выполняется в отдельном потоке чтобы не блокировать event loop.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("TG: Токен или chat_id не установлены, пропускаем отправку")
        return
    
    def _send():
        try:
            import requests
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={
                    'chat_id': TELEGRAM_CHAT_ID,
                    'text': text[:4096],  # Telegram лимит 4096 символов
                    'parse_mode': 'HTML'
                },
                timeout=10,
            )
            logger.debug(f"TG sent: {text[:100]}...")
        except Exception as e:
            logger.error(f"❌ TG error: {e}")
    
    # Отправляем в отдельном потоке чтобы не блокировать async event loop
    thread = threading.Thread(target=_send, daemon=True)
    thread.start()
