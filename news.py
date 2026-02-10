# news.py
"""
Модуль анализа новостей и сентимента
Использует DistilBERT для определения настроений
"""

import requests
import logging
from config import NEWS_API_KEY

# Ленивая загрузка модели — загружается только при первом использовании
_sentiment_analyzer = None
_sentiment_available = None

def _get_sentiment_analyzer():
    """Ленивая загрузка модели сентимент-анализа"""
    global _sentiment_analyzer, _sentiment_available
    
    if _sentiment_available is False:
        return None
    
    if _sentiment_analyzer is None:
        try:
            from transformers import pipeline
            logging.info("🧠 Загрузка модели сентимент-анализа...")
            _sentiment_analyzer = pipeline(
                "sentiment-analysis", 
                model="distilbert/distilbert-base-uncased-finetuned-sst-2-english"
            )
            _sentiment_available = True
            logging.info("✅ Модель сентимент-анализа загружена")
        except ImportError:
            logging.warning("⚠️ transformers не установлен, сентимент-анализ отключён")
            _sentiment_available = False
            return None
        except Exception as e:
            logging.error(f"❌ Ошибка загрузки модели: {e}")
            _sentiment_available = False
            return None
    
    return _sentiment_analyzer

def get_news(query="cryptocurrency"):
    """Получает новости через NewsAPI"""
    if not NEWS_API_KEY:
        logging.warning("⚠️ NEWS_API_KEY не установлен, новости недоступны")
        return []
    
    url = f'https://newsapi.org/v2/everything?q={query}&apiKey={NEWS_API_KEY}&sortBy=publishedAt&pageSize=20'
    try:
        response = requests.get(url, timeout=10)
        news_data = response.json()
        if news_data.get('status') == 'ok':
            return news_data.get('articles', [])
        return []
    except Exception as e:
        logging.error(f"❌ Ошибка получения новостей: {e}")
        return []

def analyze_sentiment(articles):
    """Анализирует сентимент новостных статей"""
    analyzer = _get_sentiment_analyzer()
    if analyzer is None:
        return "Neutral"
    
    score = 0
    count = 0
    for article in articles[:10]:  # берём только свежие 10
        title = article.get('title', '')
        description = article.get('description', '')
        text = (title + " " + description).strip()
        if text:
            try:
                sentiment = analyzer(text[:512])[0]  # DistilBERT лимит 512 токенов
                score += 1 if sentiment['label'] == 'POSITIVE' else -1
                count += 1
            except Exception as e:
                logging.debug(f"⚠️ Ошибка анализа статьи: {e}")
    
    if count == 0:
        return "Neutral"
    return "Buy" if score > 0 else "Sell" if score < 0 else "Neutral"

