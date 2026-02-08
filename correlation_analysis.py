"""
Correlation Analysis
Анализ корреляции между криптовалютами
Избегаем торговли скоррелированными активами
"""

import logging
import pandas as pd
import numpy as np
from exchange import exchange
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CorrelationAnalyzer:
    """Анализ корреляции между криптовалютами"""
    
    def __init__(self, symbols=None):
        """
        Args:
            symbols: список символов для анализа
            По умолчанию: ['BTC', 'ETH', 'SOL', 'ARB', 'LINK', 'NEAR']
        """
        self.symbols = symbols or [
            'BTC/USDT:USDT',
            'ETH/USDT:USDT',
            'SOL/USDT:USDT',
            'ARB/USDT:USDT',
            'LINK/USDT:USDT',
            'NEAR/USDT:USDT'
        ]
        self.data = {}
        self.correlation_matrix = None
        self.last_update = None
    
    def fetch_price_data(self, days=30):
        """Загружает данные цен за N дней"""
        try:
            logger.info(f"📊 Fetching price data for {len(self.symbols)} symbols...")
            
            for symbol in self.symbols:
                try:
                    # Загружаем дневные свечи за последний месяц
                    since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
                    candles = exchange.fetch_ohlcv(symbol, '1d', since=since, limit=days)
                    
                    prices = [c[4] for c in candles]  # close prices
                    timestamps = [datetime.fromtimestamp(c[0]/1000) for c in candles]
                    
                    self.data[symbol] = {
                        'prices': prices,
                        'timestamps': timestamps,
                        'returns': self.calculate_returns(prices)
                    }
                    
                    logger.debug(f"✅ Loaded {len(prices)} candles for {symbol}")
                
                except Exception as e:
                    logger.warning(f"⚠️ Error loading {symbol}: {e}")
            
            self.last_update = datetime.now()
            return True
        
        except Exception as e:
            logger.error(f"❌ Error fetching price data: {e}")
            return False
    
    def calculate_returns(self, prices):
        """Вычисляет дневные изменения (returns)"""
        if len(prices) < 2:
            return []
        
        returns = []
        for i in range(1, len(prices)):
            ret = (prices[i] - prices[i-1]) / prices[i-1] * 100
            returns.append(ret)
        
        return returns
    
    def calculate_correlation_matrix(self):
        """Рассчитывает матрицу корреляции"""
        try:
            # Подготавливаем данные
            returns_data = {}
            for symbol, data in self.data.items():
                if data['returns']:
                    returns_data[symbol] = data['returns']
            
            if not returns_data:
                logger.error("❌ No data for correlation calculation")
                return None
            
            # Создаём DataFrame
            df = pd.DataFrame(returns_data)
            
            # Рассчитываем корреляцию
            self.correlation_matrix = df.corr()
            
            logger.info("✅ Correlation matrix calculated")
            return self.correlation_matrix
        
        except Exception as e:
            logger.error(f"❌ Error calculating correlation: {e}")
            return None
    
    def get_correlation_with_btc(self):
        """Получает корреляцию каждого актива с BTC"""
        if self.correlation_matrix is None:
            return None
        
        try:
            btc_symbol = [s for s in self.symbols if 'BTC' in s][0]
            btc_correlation = self.correlation_matrix[btc_symbol].sort_values(ascending=False)
            
            return btc_correlation
        
        except Exception as e:
            logger.error(f"❌ Error getting BTC correlation: {e}")
            return None
    
    def should_trade_symbol(self, symbol, max_correlation_with_btc=0.8):
        """
        Определяет, стоит ли торговать символом
        
        Логика:
        ├─ Высокая корреляция с BTC → не торгуем (системный риск)
        ├─ Низкая корреляция → торгуем (диверсификация)
        └─ Идеально: корреляция 0.4-0.7 (коррелирован но независим)
        """
        btc_corr = self.get_correlation_with_btc()
        
        if btc_corr is None:
            return True
        
        symbol_correlation = btc_corr.get(symbol, 1.0)
        
        can_trade = symbol_correlation < max_correlation_with_btc
        
        logger.info(
            f"📊 Correlation check for {symbol}:\n"
            f"   Correlation with BTC: {symbol_correlation:.3f}\n"
            f"   Threshold: {max_correlation_with_btc}\n"
            f"   Can Trade: {'✅ YES' if can_trade else '❌ NO'}"
        )
        
        return can_trade
    
    def find_uncorrelated_pairs(self, max_correlation=0.7, count=5):
        """
        Находит пары с низкой корреляцией
        Идеально для параллельной торговли нескольких позиций
        """
        if self.correlation_matrix is None:
            return []
        
        uncorrelated = []
        
        for i, sym1 in enumerate(self.symbols):
            for sym2 in self.symbols[i+1:]:
                corr = abs(self.correlation_matrix.loc[sym1, sym2])
                
                if corr < max_correlation:
                    uncorrelated.append({
                        'pair': (sym1, sym2),
                        'correlation': corr,
                        'independence': 1 - corr
                    })
        
        # Сортируем по независимости (выше = лучше)
        uncorrelated.sort(key=lambda x: x['independence'], reverse=True)
        
        logger.info(
            f"📊 Found {len(uncorrelated)} uncorrelated pairs:\n"
            + "\n".join([
                f"   {i+1}. {pair['pair'][0]} ↔ {pair['pair'][1]}: {pair['correlation']:.3f}"
                for i, pair in enumerate(uncorrelated[:count])
            ])
        )
        
        return uncorrelated[:count]
    
    def print_correlation_matrix(self):
        """Красивый вывод матрицы корреляции"""
        if self.correlation_matrix is None:
            logger.warning("⚠️ No correlation matrix calculated")
            return
        
        logger.info(
            f"\n📊 CORRELATION MATRIX (Updated: {self.last_update})\n"
            + self.correlation_matrix.to_string()
        )
    
    def get_full_report(self):
        """Полный отчёт корреляции"""
        if self.correlation_matrix is None:
            self.fetch_price_data()
            self.calculate_correlation_matrix()
        
        btc_corr = self.get_correlation_with_btc()
        uncorrelated = self.find_uncorrelated_pairs()
        
        report = f"""
╔════════════════════════════════════════════════════════════╗
║           📊 CORRELATION ANALYSIS REPORT                   ║
╠════════════════════════════════════════════════════════════╣
║                 BTC CORRELATION                            ║
├────────────────────────────────────────────────────────────┤
"""
        
        if btc_corr is not None:
            for symbol, corr in btc_corr.items():
                icon = "🔴" if corr > 0.8 else "🟡" if corr > 0.6 else "🟢"
                report += f"║ {icon} {symbol:20} {corr:+.3f}\n"
        
        report += f"""╠════════════════════════════════════════════════════════════╣
║         UNCORRELATED PAIRS (Good for Trading)              ║
├───────────────────��────────────────────────────────────────┤
"""
        
        for i, pair in enumerate(uncorrelated):
            report += (
                f"║ {i+1}. {pair['pair'][0]:15} ↔ {pair['pair'][1]:15} "
                f"({pair['correlation']:.3f})\n"
            )
        
        report += "╚════════════════════════════════════════════════════════════╝\n"
        
        logger.info(report)
        return report


# Глобальный экземпляр
correlation_analyzer = CorrelationAnalyzer()
