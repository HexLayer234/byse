# news.py
import requests
from transformers import pipeline
from config import NEWS_API_KEY
import logging

sentiment_analyzer = pipeline("sentiment-analysis", model="distilbert/distilbert-base-uncased-finetuned-sst-2-english")

def get_news(query="cryptocurrency"):
    url = f'https://newsapi.org/v2/everything?q={query}&apiKey={NEWS_API_KEY}&sortBy=publishedAt&pageSize=20'
    try:
        response = requests.get(url)
        news_data = response.json()
        if news_data['status'] == 'ok':
            return news_data['articles']
        return []
    except Exception as e:
        logging.error(f"Error fetching news: {e}")
        return []

def analyze_sentiment(articles):
    score = 0
    count = 0
    for article in articles[:10]:  # берём только свежие 10
        title = article.get('title', '')
        description = article.get('description', '')
        text = title + " " + description
        if text.strip():
            sentiment = sentiment_analyzer(text)[0]
            score += 1 if sentiment['label'] == 'POSITIVE' else -1
            count += 1
    if count == 0:
        return "Neutral"
    return "Buy" if score > 0 else "Sell" if score < 0 else "Neutral"

