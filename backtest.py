"""
Backtesting Engine
Проверка стратегии на исторических данных
Рассчитывает метрики эффективности
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from exchange import exchange, fetch_ohlcv_df
from trading_logic import calculate_signal_score, compute_indicators, check_market_activity_detailed
from prediction import predict_price
from news import get_news, analyze_sentiment
from neural_network import get_lstm_direction
from risk_management import risk_manager

logger = logging.getLogger(__name__)

class BacktestEngine:
    """Мощный engine для бэктестирования стратегии"""
    
    def __init__(self, symbol, initial_balance=1000, leverage=1):
        """
        Args:
            symbol: пара для тестирования
            initial_balance: начальный баланс в USDT
            leverage: плечо для фьючерсов
        """
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.leverage = leverage
        
        self.balance = initial_balance
        self.position = None  # {'entry_price': X, 'entry_time': X, 'amount': X}
        self.trades = []  # История всех сделок
        self.equity_curve = []  # Кривая баланса
    
    def load_historical_data(self, days=30):
        """Загружает исторические данные"""
        try:
            # CCXT может загружать данные по частям
            # Загружаем за последние N дней по 5м свечам
            all_candles = []
            
            for i in range(days):
                try:
                    since = int((datetime.now() - timedelta(days=days-i)).timestamp() * 1000)
                    candles = exchange.fetch_ohlcv(self.symbol, '5m', since=since, limit=288)
                    all_candles.extend(candles)
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка загрузки для дня {days-i}: {e}")
            
            if not all_candles:
                logger.error("❌ Не удалось загрузить данные")
                return None
            
            # Удаляем дубликаты и сортируем
            df = pd.DataFrame(all_candles, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            df = df.drop_duplicates(subset=['ts']).sort_values('ts').reset_index(drop=True)
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            
            logger.info(f"✅ Загружено {len(df)} свечей за {days} дней")
            return df
        
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки данных: {e}")
            return None
    
    def run_backtest(self, df):
        """Запускает бэктест на исторических данных"""
        if df is None or len(df) < 50:
            logger.error("❌ Недостаточно данных для бэктеста")
            return None
        
        logger.info(f"🔄 Запуск бэктеста на {len(df)} свечах...")
        
        for i in range(50, len(df)):  # Начинаем с 50-й свечи (достаточно для индикаторов)
            current_candle = df.iloc[i]
            current_price = current_candle['close']
            current_time = current_candle['ts']
            
            # Получаем данные до текущей свечи
            df_current = df.iloc[:i+1].copy()
            
            # Вычисляем индикаторы
            rsi, macd, macd_signal = compute_indicators(df_current)
            if rsi is None:
                continue
            
            # Активность рынка
            is_active, volume_ratio, atr, price_change = check_market_activity_detailed_backtest(df_current)
            
            # Для бэктеста используем упрощённый прогноз
            # (реальный Prophet требует обучения на каждой итерации)
            price_up = current_price > df_current['close'].iloc[-2]
            
            # LSTM направление (если доступна модель)
            lstm_direction = 0  # Упрощённо для бэктеста
            
            # Sentiment (упрощённо)
            sentiment = "Neutral"  # Для бэктеста не загружаем новости
            
            # Расчет сигнала
            score = calculate_signal_score(
                rsi=rsi, macd=macd, macd_signal=macd_signal,
                sentiment=sentiment, price_up=price_up,
                is_active=is_active, volume_ratio=volume_ratio,
                atr=atr, price_change_pct=price_change,
                lstm_direction=lstm_direction
            )
            
            # ТОРГОВАЯ ЛОГИКА
            if score >= 30 and self.position is None:
                # BUY SIGNAL
                entry_price = current_price
                stop_loss = entry_price * (1 - 0.02)  # -2% SL
                
                # Расчет размера позиции
                position_size_coins, position_size_usdt, risk_amount = risk_manager.calculate_position_size(
                    entry_price, stop_loss
                )
                
                if position_size_coins > 0:
                    self.position = {
                        'entry_price': entry_price,
                        'entry_time': current_time,
                        'amount': position_size_coins,
                        'stop_loss': stop_loss,
                        'side': 'BUY'
                    }
            
            elif score <= -30 and self.position is not None:
                # SELL SIGNAL
                exit_price = current_price
                pnl = (exit_price - self.position['entry_price']) * self.position['amount']
                
                self.trades.append({
                    'entry_time': self.position['entry_time'],
                    'exit_time': current_time,
                    'entry_price': self.position['entry_price'],
                    'exit_price': exit_price,
                    'amount': self.position['amount'],
                    'pnl': pnl,
                    'pnl_percent': ((exit_price - self.position['entry_price']) / self.position['entry_price'] * 100),
                    'duration': (current_time - self.position['entry_time']).total_seconds() / 60,
                    'score': score
                })
                
                self.balance += pnl
                self.position = None
            
            # Stop Loss проверка
            if self.position and current_price <= self.position['stop_loss']:
                exit_price = self.position['stop_loss']
                pnl = (exit_price - self.position['entry_price']) * self.position['amount']
                
                self.trades.append({
                    'entry_time': self.position['entry_time'],
                    'exit_time': current_time,
                    'entry_price': self.position['entry_price'],
                    'exit_price': exit_price,
                    'amount': self.position['amount'],
                    'pnl': pnl,
                    'pnl_percent': ((exit_price - self.position['entry_price']) / self.position['entry_price'] * 100),
                    'duration': (current_time - self.position['entry_time']).total_seconds() / 60,
                    'stop': 'SL'
                })
                
                self.balance += pnl
                self.position = None
            
            # Логируем баланс
            self.equity_curve.append({
                'timestamp': current_time,
                'balance': self.balance,
                'open_position': self.position is not None
            })
        
        # Закрываем открытую позицию в конце
        if self.position:
            exit_price = df.iloc[-1]['close']
            pnl = (exit_price - self.position['entry_price']) * self.position['amount']
            
            self.trades.append({
                'entry_time': self.position['entry_time'],
                'exit_time': df.iloc[-1]['ts'],
                'entry_price': self.position['entry_price'],
                'exit_price': exit_price,
                'amount': self.position['amount'],
                'pnl': pnl,
                'pnl_percent': ((exit_price - self.position['entry_price']) / self.position['entry_price'] * 100),
                'duration': (df.iloc[-1]['ts'] - self.position['entry_time']).total_seconds() / 60,
                'status': 'OPEN AT END'
            })
            
            self.balance += pnl
        
        return self.calculate_metrics()
    
    def calculate_metrics(self):
        """Рассчитывает метрики производительности"""
        if not self.trades:
            logger.warning("⚠️ Нет выполненных сделок для анализа")
            return None
        
        df_trades = pd.DataFrame(self.trades)
        
        winning_trades = df_trades[df_trades['pnl'] > 0]
        losing_trades = df_trades[df_trades['pnl'] < 0]
        
        total_trades = len(df_trades)
        winning_count = len(winning_trades)
        losing_count = len(losing_trades)
        
        win_rate = (winning_count / total_trades * 100) if total_trades > 0 else 0
        
        avg_win = winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0
        avg_loss = losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0
        
        total_pnl = df_trades['pnl'].sum()
        
        profit_factor = abs(winning_trades['pnl'].sum() / losing_trades['pnl'].sum()) \
            if len(losing_trades) > 0 and losing_trades['pnl'].sum() != 0 else 0
        
        # Max Drawdown
        equity_curve = pd.DataFrame(self.equity_curve)
        running_max = equity_curve['balance'].expanding().max()
        drawdown = (equity_curve['balance'] - running_max) / running_max
        max_drawdown = drawdown.min() * 100
        
        # Sharpe Ratio (упрощённо)
        returns = df_trades['pnl_percent'].values
        sharpe_ratio = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 0 else 0
        
        total_return = ((self.balance - self.initial_balance) / self.initial_balance) * 100
        
        metrics = {
            'initial_balance': self.initial_balance,
            'final_balance': self.balance,
            'total_pnl': total_pnl,
            'total_return_percent': total_return,
            'total_trades': total_trades,
            'winning_trades': winning_count,
            'losing_trades': losing_count,
            'win_rate_percent': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown_percent': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'avg_trade_duration_minutes': df_trades['duration'].mean()
        }
        
        return metrics
    
    def print_report(self, metrics):
        """Красивый вывод отчёта бэктеста"""
        if metrics is None:
            logger.error("❌ Не удалось рассчитать метрики")
            return
        
        report = f"""
╔════════════════════════════════════════════════════════════╗
║              📊 BACKTEST REPORT ({self.symbol})             ║
╠════════════════════════════════════════════════════════════╣
║                      ОСНОВНЫЕ МЕТРИКИ                      ║
├────────────────────────────────────────────────────────────┤
║ Initial Balance: ${metrics['initial_balance']:.2f}
║ Final Balance: ${metrics['final_balance']:.2f}
║ Total P&L: ${metrics['total_pnl']:.2f}
║ Total Return: {metrics['total_return_percent']:+.2f}%
╠════════════════════════════════════════════════════════════╣
║                      СТАТИСТИКА СДЕЛОК                     ║
├────────────────────────────────────────────────────────────┤
║ Total Trades: {metrics['total_trades']}
║ Winning Trades: {metrics['winning_trades']} ({metrics['win_rate_percent']:.1f}%)
║ Losing Trades: {metrics['losing_trades']} ({100-metrics['win_rate_percent']:.1f}%)
║ Avg Win: ${metrics['avg_win']:.2f}
║ Avg Loss: ${metrics['avg_loss']:.2f}
║ Profit Factor: {metrics['profit_factor']:.2f}x
║ Avg Trade Duration: {metrics['avg_trade_duration_minutes']:.0f} minutes
╠════════════════════════════════════════════════════════════╣
║                      МЕТРИКИ РИСКА                         ║
├──────���─────────────────────────────────────────────────────┤
║ Max Drawdown: {metrics['max_drawdown_percent']:.2f}%
║ Sharpe Ratio: {metrics['sharpe_ratio']:.2f}
╚════════════════════════════════════════════════════════════╝
"""
        logger.info(report)
        return report


def check_market_activity_detailed_backtest(df):
    """Упрощённая версия для бэктеста"""
    try:
        from config import VOLUME_MA_PERIOD, ATR_PERIOD, MIN_VOLUME_RATIO, MIN_VOLATILITY, MIN_PRICE_CHANGE_PCT
        
        df['volume_ma'] = df['volume'].rolling(window=VOLUME_MA_PERIOD).mean()
        current_volume = df['volume'].iloc[-1]
        avg_volume = df['volume_ma'].iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        atr = df.ta.atr(length=ATR_PERIOD)
        current_atr = atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else 0
        
        recent_close = df['close'].iloc[-10:] if len(df) >= 10 else df['close']
        price_change_pct = ((recent_close.iloc[-1] - recent_close.iloc[0]) / recent_close.iloc[0] * 100) if len(recent_close) > 0 else 0
        
        is_active = (
            volume_ratio > MIN_VOLUME_RATIO and
            current_atr > MIN_VOLATILITY and
            abs(price_change_pct) > MIN_PRICE_CHANGE_PCT
        )
        
        return is_active, volume_ratio, current_atr, price_change_pct
    
    except Exception as e:
        logger.error(f"❌ Ошибка анализа рынка: {e}")
        return False, 0, 0, 0
