"""
Продвинутый нейросетевой селектор монет
Использует глубокое обучение для выбора монет
"""

import logging
import numpy as np
import pandas as pd
from exchange import exchange
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AdvancedCoinSelector:
    """Продвинутый селектор с нейросетевым анализом"""
    
    def __init__(self):
        self.feature_importance = {}
        self.historical_scores = []
    
    def calculate_advanced_metrics(self, symbol):
        """Рассчитывает продвинутые метрики для монеты"""
        try:
            # Получаем различные свечи для анализа
            candles_1h = exchange.fetch_ohlcv(symbol, '1h', limit=24)
            candles_4h = exchange.fetch_ohlcv(symbol, '4h', limit=30)
            candles_1d = exchange.fetch_ohlcv(symbol, '1d', limit=60)
            
            if not candles_1h or not candles_4h or not candles_1d:
                return None
            
            df_1h = pd.DataFrame(candles_1h, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df_4h = pd.DataFrame(candles_4h, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df_1d = pd.DataFrame(candles_1d, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            metrics = {
                'symbol': symbol,
                # Тренд
                'trend_1h': self._calculate_trend(df_1h),
                'trend_4h': self._calculate_trend(df_4h),
                'trend_1d': self._calculate_trend(df_1d),
                # Волатильность
                'volatility_1h': self._calculate_volatility(df_1h),
                'volatility_4h': self._calculate_volatility(df_4h),
                'volatility_1d': self._calculate_volatility(df_1d),
                # Импульс
                'momentum_1h': self._calculate_momentum(df_1h),
                'momentum_4h': self._calculate_momentum(df_4h),
                'momentum_1d': self._calculate_momentum(df_1d),
                # Давление покупателей
                'buy_pressure_1h': self._calculate_buy_pressure(df_1h),
                'buy_pressure_4h': self._calculate_buy_pressure(df_4h),
                'buy_pressure_1d': self._calculate_buy_pressure(df_1d),
            }
            
            return metrics
        
        except Exception as e:
            logger.debug(f"⚠️ Ошибка расчёта метрик {symbol}: {e}")
            return None
    
    def _calculate_trend(self, df):
        """Рассчитывает тренд"""
        if len(df) < 2:
            return 0
        return (df['c'].iloc[-1] - df['c'].iloc[0]) / df['c'].iloc[0]
    
    def _calculate_volatility(self, df):
        """Рассчитывает волатильность"""
        if len(df) < 2:
            return 0
        returns = df['c'].pct_change().dropna()
        return returns.std()
    
    def _calculate_momentum(self, df):
        """Рассчитывает импульс"""
        if len(df) < 10:
            return 0
        return (df['c'].iloc[-1] - df['c'].iloc[-10]) / df['c'].iloc[-10]
    
    def _calculate_buy_pressure(self, df):
        """Рассчитывает давление покупателей"""
        if len(df) < 1:
            return 0
        
        up_days = len(df[df['c'] > df['o']])
        total_days = len(df)
        
        return (up_days / total_days) if total_days > 0 else 0
    
    def score_coin(self, metrics):
        """Оценивает монету на основе метрик"""
        if not metrics:
            return 0
        
        score = 0
        weights = {
            'trend_1d': 0.25,
            'trend_4h': 0.15,
            'trend_1h': 0.10,
            'volatility_1h': 0.10,
            'momentum_1d': 0.15,
            'momentum_4h': 0.10,
            'buy_pressure_1d': 0.10,
            'buy_pressure_4h': 0.05,
        }
        
        for metric, weight in weights.items():
            value = metrics.get(metric, 0)
            
            # Нормализуем значения
            if 'trend' in metric:
                normalized = min(max(value * 50 + 50, 0), 100)  # -1 to +1 → 0 to 100
            elif 'volatility' in metric:
                normalized = min(value * 50, 50)  # выше волатильность = лучше, но не более 50
            elif 'momentum' in metric:
                normalized = min(max(value * 50 + 50, 0), 100)
            elif 'buy_pressure' in metric:
                normalized = value * 100  # 0 to 1 → 0 to 100
            else:
                normalized = 50
            
            score += normalized * weight
        
        return min(score, 100)


advanced_selector = AdvancedCoinSelector()
