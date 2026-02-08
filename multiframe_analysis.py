"""
Multiple Timeframe Analysis (MTF)
Анализ на нескольких таймфреймах одновременно
Сигнал только когда ВСЕ таймфреймы согласны
"""

import logging
import pandas as pd
from exchange import exchange
from trading_logic import compute_indicators, check_market_activity_detailed

logger = logging.getLogger(__name__)

class MultiTimeframeAnalyzer:
    """Анализ на нескольких таймфре��мах"""
    
    def __init__(self, symbol):
        self.symbol = symbol
        self.timeframes = {
            '5m': {'weight': 1, 'df': None},   # Краткосрочный
            '15m': {'weight': 2, 'df': None},  # Среднесрочный
            '1h': {'weight': 3, 'df': None},   # Долгосрочный
        }
    
    def fetch_data_for_timeframe(self, timeframe):
        """Загружает данные для конкретного таймфрейма"""
        try:
            candles = exchange.fetch_ohlcv(self.symbol, timeframe=timeframe, limit=100)
            df = pd.DataFrame(candles, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            return df
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки {timeframe}: {e}")
            return None
    
    def analyze_timeframe(self, df):
        """Анализирует один таймфрейм и возвращает сигнал"""
        if df is None or len(df) < 50:
            return None
        
        rsi, macd, macd_signal = compute_indicators(df)
        if rsi is None:
            return None
        
        signal = {
            'rsi': rsi,
            'rsi_signal': self.get_rsi_signal(rsi),
            'macd': macd,
            'macd_signal': macd_signal,
            'macd_direction': self.get_macd_signal(macd, macd_signal),
            'trend': self.get_trend(df),
            'price': df['close'].iloc[-1]
        }
        
        return signal
    
    def get_rsi_signal(self, rsi):
        """RSI сигнал: 1=BUY, -1=SELL, 0=NEUTRAL"""
        if rsi < 30:
            return 1  # Перепродано - BUY
        elif rsi > 70:
            return -1  # Перекуплено - SELL
        elif rsi < 45:
            return 0.5  # Слабый BUY
        elif rsi > 55:
            return -0.5  # Слабый SELL
        else:
            return 0  # Нейтрально
    
    def get_macd_signal(self, macd, macd_signal):
        """MACD сигнал: 1=BUY, -1=SELL"""
        if macd > macd_signal:
            return 1  # Бычий
        else:
            return -1  # Медвежий
    
    def get_trend(self, df):
        """Определяет тренд по MA200"""
        try:
            if len(df) < 200:
                return 0  # Недостаточно данных
            
            ma200 = df['close'].rolling(200).mean().iloc[-1]
            current_price = df['close'].iloc[-1]
            
            if current_price > ma200:
                return 1  # Восходящий тренд
            elif current_price < ma200:
                return -1  # Нисходящий тренд
            else:
                return 0  # Боковое движение
        except Exception as e:
            logger.error(f"❌ Ошибка расчёта тренда: {e}")
            return 0
    
    def run_multiframe_analysis(self):
        """Запускает анализ на всех таймфреймах"""
        logger.info(f"🔄 MTF анализ для {self.symbol}...")
        
        results = {}
        
        for timeframe in self.timeframes.keys():
            df = self.fetch_data_for_timeframe(timeframe)
            self.timeframes[timeframe]['df'] = df
            
            signal = self.analyze_timeframe(df)
            results[timeframe] = signal
            
            if signal:
                logger.debug(
                    f"   {timeframe}: RSI={signal['rsi']:.1f} "
                    f"({self.describe_signal(signal['rsi_signal'])}), "
                    f"Trend={'UP' if signal['trend'] == 1 else 'DOWN' if signal['trend'] == -1 else 'SIDE'}"
                )
        
        return results
    
    def describe_signal(self, signal_value):
        """Описание сигнала"""
        if signal_value == 1:
            return "🟢BUY"
        elif signal_value == -1:
            return "🔴SELL"
        elif signal_value == 0.5:
            return "⚪WEAK BUY"
        elif signal_value == -0.5:
            return "⚪WEAK SELL"
        else:
            return "⚫NEUTRAL"
    
    def get_consensus_signal(self, results):
        """
        Получает консенсус-сигнал со всех таймфреймов
        
        Логика:
        ├─ ��аждый таймфрейм имеет вес
        ├─ Суммируем взвешенные сигналы
        └─ Результат: сильный или слабый сигнал
        
        Результаты:
        ├─ score >= 2.0: 🟢 STRONG BUY (все согласны)
        ├─ 1.0 <= score < 2.0: ⚪ WEAK BUY
        ├─ -1.0 < score < 1.0: ⚫ NEUTRAL
        ├─ -2.0 < score <= -1.0: ⚪ WEAK SELL
        └─ score <= -2.0: 🔴 STRONG SELL (все согласны)
        """
        if not results or all(v is None for v in results.values()):
            logger.warning("⚠️ Нет данных для консенсуса")
            return 0, None
        
        weighted_score = 0
        
        for timeframe in self.timeframes.keys():
            signal = results[timeframe]
            weight = self.timeframes[timeframe]['weight']
            
            if signal:
                # Комбинируем RSI + MACD + Trend
                rsi_part = signal['rsi_signal'] * weight * 0.4
                macd_part = signal['macd_direction'] * weight * 0.3
                trend_part = signal['trend'] * weight * 0.3
                
                timeframe_score = rsi_part + macd_part + trend_part
                weighted_score += timeframe_score
                
                logger.debug(
                    f"   {timeframe} score: "
                    f"RSI={rsi_part:+.2f} + MACD={macd_part:+.2f} + Trend={trend_part:+.2f} "
                    f"= {timeframe_score:+.2f}"
                )
        
        # Нормализуем
        total_weight = sum(self.timeframes[tf]['weight'] for tf in self.timeframes)
        normalized_score = weighted_score / (total_weight * 0.6)  # Нормализация
        
        consensus = self.describe_consensus(normalized_score)
        
        logger.info(
            f"📊 MTF Consensus for {self.symbol}:\n"
            f"   Score: {normalized_score:+.2f}\n"
            f"   Signal: {consensus}\n"
            f"   Strength: {abs(normalized_score):.2f}/3.0"
        )
        
        return normalized_score, consensus
    
    def describe_consensus(self, score):
        """Описание консенсуса"""
        if score >= 2.0:
            return "🟢 STRONG BUY - All timeframes bullish!"
        elif score >= 1.0:
            return "⚪ WEAK BUY - Mostly bullish"
        elif score > -1.0:
            return "⚫ NEUTRAL - Mixed signals"
        elif score >= -2.0:
            return "⚪ WEAK SELL - Mostly bearish"
        else:
            return "🔴 STRONG SELL - All timeframes bearish!"
    
    def should_trade(self, consensus_score, min_strength=1.5):
        """Определяет, следует ли торговать"""
        return abs(consensus_score) >= min_strength
    
    def get_full_report(self):
        """Полный отчёт MTF анализа"""
        results = self.run_multiframe_analysis()
        score, consensus = self.get_consensus_signal(results)
        
        report = f"""
╔════════════════════════════════════════════════════════════╗
║          📊 MULTI-TIMEFRAME ANALYSIS ({self.symbol})       ║
╠════════════════════════════════════════════════════════════╣
"""
        
        for timeframe in self.timeframes.keys():
            signal = results[timeframe]
            if signal:
                report += f"""
║ {timeframe.upper():>2} | RSI: {signal['rsi']:>5.1f} ({self.describe_signal(signal['rsi_signal'])}) |
║    | MACD: {self.describe_signal(signal['macd_direction'])} | Trend: {self.describe_signal(signal['trend'])}
"""
        
        report += f"""╠════════════════════════════════════════════════════════════╣
║ CONSENSUS: {consensus:<43} ║
║ Score: {score:+.2f}/3.0                                  ║
╚════════════════════════════════════════════════════════════╝
"""
        
        return report


# Глобальный экземпляр
def create_mtf_analyzer(symbol):
    return MultiTimeframeAnalyzer(symbol)
