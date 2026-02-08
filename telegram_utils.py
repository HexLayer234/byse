# telegram_utils.py
import requests
import logging
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_message(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'HTML'},
            timeout=10,
        )
        logging.info(f"TG sent: {text}")
    except Exception as e:
        logging.error(f"TG error: {e}")
