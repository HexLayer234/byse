"""
Интеллектуальный выбор монет для торговли
ИИ анализирует все доступные монеты и выбирает самые перспективные
"""

import time
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from exchange import exchange
from ensemble_predictor import ensemble_predictor
from correlation_analysis import correlation_analyzer
from backtest import BacktestEngine
import asyncio

logger = logging.getLogger(__name__)

class CoinSelector:
    """Интеллектуальный выбор торговых пар"""
    
    def __init__(self, top_n=5, min_volume_usdt=1000000):
        self.top_n = top_n
        self.min_volume_usdt = min_volume_usdt
        self.analyzed_coins = []
        self.best_coins = []
    
    def get_top_coins_by_volume(self, count=50):
        """Получает топ монет по объёму"""
        try:
            logger.info(f"📊 Получаю топ {count} монет по объёму...")
            
            tickers = exchange.fetch_tickers()
            
            coins_data = []
            for symbol, ticker in tickers.items():
                if 'USDT' not in symbol:
                    continue
                
                volume_usdt = ticker.get('quoteVolume', 0) or 0
                
                if volume_usdt >= self.min_volume_usdt:
                    coins_data.append({
                        'symbol': symbol,
                        'volume': volume_usdt,
                        'price': ticker.get('last', 0),
                        'change_24h': ticker.get('percentage', 0)
                    })
            
            # Сортируем по объёму
            coins_data.sort(key=lambda x: x['volume'], reverse=True)
            
            logger.info(f"✅ Найдено {len(coins_data)} монет с достаточным объёмом")
            return coins_data[:count]
        
        except Exception as e:
            logger.error(f"❌ Ошибка получения монет: {e}")
            return []
    
    def analyze_coin_potential(self, symbol):
        """
        Анализирует потенциал монеты по разным критериям
        Возвращает оценку от 0 до 100
        """
        try:
            # Получаем исторические данные
            candles = exchange.fetch_ohlcv(symbol, '1d', limit=30)
            
            if not candles:
                return 0
            
            df = pd.DataFrame(candles, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            
            # 1. Волатильность (выше = лучше для торговли)
            returns = df['close'].pct_change().dropna()
            volatility = returns.std() * 100
            volatility_score = min(volatility * 10, 25)  # Макс 25 баллов
            
            # 2. Тренд (растущий тренд = лучше)
            price_change = ((df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0]) * 100
            trend_score = min(max(price_change, -25), 25)  # -25 до +25 баллов
            
            # 3. Объём (растущий объём = лучше)
            avg_volume = df['volume'].mean()
            current_volume = df['volume'].iloc[-1]
            volume_score = min((current_volume / avg_volume - 1) * 10, 20)  # Макс 20 баллов
            
            # 4. Волатильность цены (не должна быть слишком высокой)
            price_volatility = df['high'].max() / df['low'].min()
            stability_score = max(30 - (price_volatility * 10), 0)  # Макс 30 баллов
            
            total_score = volatility_score + trend_score + volume_score + stability_score
            
            return min(total_score, 100)
        
        except Exception as e:
            logger.debug(f"⚠️ Ошибка анализа {symbol}: {e}")
            return 0
    
    def rank_coins(self, coins):
        """Ранжирует монеты по потенциалу"""
        logger.info(f"🎯 Ранжирую {len(coins)} монет по потенциалу...")
    
        ranked_coins = []
    
        for i, coin in enumerate(coins):
            symbol = coin['symbol']
            potential = self.analyze_coin_potential(symbol)
        
            ranked_coins.append({
                'symbol': symbol,
                'potential_score': potential,
                'volume': coin['volume'],
                'price': coin['price'],
                'change_24h': coin['change_24h']
        })
        
        # Задержка каждые 10 монет для предотвращения рейтлимита
            if (i + 1) % 10 == 0:
                time.sleep(0.5)
                logger.debug(f"📊 Обработано {i+1}/{len(coins)} монет...")
        
        # Сортируем по потенциалу
        ranked_coins.sort(key=lambda x: x['potential_score'], reverse=True)
        
        logger.info("✅ Ранжирование завершено")
        
        return ranked_coins
    
    def select_best_coins(self):
        """Выбирает лучшие монеты для торговли"""
        logger.info(f"🚀 Выбираю лучшие {self.top_n} монет...")
        
        # Получаем топ монеты
        top_coins = self.get_top_coins_by_volume(count=50)
        
        if not top_coins:
            logger.error("❌ Не удалось получить монеты")
            return []
        
        # Ранжируем
        ranked = self.rank_coins(top_coins)
        
        # Берём топ N
        self.best_coins = ranked[:self.top_n]
        
        report = f"""
╔════════════════════════════════════════════════════════════╗
║            🎯 ТОП {self.top_n} ЛУЧШИХ МОНЕТ ДЛЯ ТОРГОВЛИ         ║
╠════════════════════════════════════════════════════════════╣
"""
        
        for i, coin in enumerate(self.best_coins, 1):
            report += f"""
║ {i}. {coin['symbol']:20} Score: {coin['potential_score']:6.2f}/100
║    Объём (24ч): ${coin['volume']:,.0f}
║    Изменение (24ч): {coin['change_24h']:+.2f}%
"""
        
        report += "╚════════════════════════════════════════════════════════════╝\n"
        
        logger.info(report)
        
        return self.best_coins
    
    def get_best_coin_to_trade(self):
        """Возвращает самую лучшую монету для немедленной торговли"""
        if not self.best_coins:
            self.select_best_coins()
        
        if self.best_coins:
            return self.best_coins[0]['symbol']
        
        return None


coin_selector = CoinSelector(top_n=5)
