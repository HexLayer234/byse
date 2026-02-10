"""
Автоматическая оптимизация параметров с РЕАЛЬНЫМ бэктестом
Эволюционный поиск лучших параметров RSI, MACD, объём
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Tuple, List
from exchange import exchange, fetch_ohlcv_df
from trading_logic import compute_indicators, calculate_signal_score
import json
from pathlib import Path
import multiprocessing as mp

logger = logging.getLogger(__name__)

class AutoOptimizer:
    """Автоматическая оптимизация с реальным бэктестом"""
    
    def __init__(self, symbol, optimization_days=30):
        self.symbol = symbol
        self.optimization_days = optimization_days
        self.best_params = None
        self.optimization_history = []
        self.params_file = f"optimized_params_{symbol.replace('/', '_').replace(':', '_')}.json"
    
    def load_params(self):
        """Загружает сохранённые параметры"""
        try:
            if Path(self.params_file).exists():
                with open(self.params_file, 'r') as f:
                    self.best_params = json.load(f)
                logger.info(f"✅ Параметры загружены: {self.params_file}")
                return self.best_params
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки: {e}")
            return None
    
    def save_params(self, params):
        """Сохраняет параметры"""
        try:
            with open(self.params_file, 'w') as f:
                json.dump(params, f, indent=2)
            self.best_params = params
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения: {e}")
    
    def _load_historical_data(self):
        """Загружает исторические данные для бэктеста"""
        try:
            candles = exchange.fetch_ohlcv(self.symbol, '1h', limit=500)
            if not candles or len(candles) < 100:
                return None
            df = pd.DataFrame(candles, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            return df
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки данных: {e}")
            return None
    
    def _backtest_config(self, df, params):
        """
        РЕАЛЬНЫЙ бэктест конфигурации на исторических данных.
        Возвращает: total_return %, win_rate %, profit_factor
        """
        rsi_period = params.get('rsi_period', 14)
        rsi_oversold = params.get('rsi_oversold', 30)
        rsi_overbought = params.get('rsi_overbought', 70)
        
        balance = 1000.0
        position = None  # {price, side, qty}
        trades = []
        
        for i in range(max(rsi_period + 10, 50), len(df)):
            window = df.iloc[:i+1].copy()
            close = window['close'].iloc[-1]
            
            # RSI
            delta = window['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
            rs = gain / loss
            rsi_val = (100 - (100 / (1 + rs))).iloc[-1]
            
            if pd.isna(rsi_val):
                continue
            
            # MACD
            fast = params.get('macd_fast', 12)
            slow = params.get('macd_slow', 26)
            sig = params.get('macd_signal', 9)
            exp1 = window['close'].ewm(span=fast, adjust=False).mean()
            exp2 = window['close'].ewm(span=slow, adjust=False).mean()
            macd_val = (exp1 - exp2).iloc[-1]
            signal_val = (exp1 - exp2).ewm(span=sig, adjust=False).mean().iloc[-1]
            
            if position is None:
                # Вход LONG
                if rsi_val < rsi_oversold and macd_val > signal_val:
                    qty = balance * 0.5 / close
                    position = {'price': close, 'side': 'long', 'qty': qty}
                # Вход SHORT
                elif rsi_val > rsi_overbought and macd_val < signal_val:
                    qty = balance * 0.5 / close
                    position = {'price': close, 'side': 'short', 'qty': qty}
            else:
                pnl_pct = 0
                if position['side'] == 'long':
                    pnl_pct = ((close - position['price']) / position['price']) * 100
                    # Выход LONG
                    if pnl_pct >= 3.0 or pnl_pct <= -2.0 or rsi_val > rsi_overbought:
                        pnl = (close - position['price']) * position['qty']
                        balance += pnl
                        trades.append(pnl)
                        position = None
                elif position['side'] == 'short':
                    pnl_pct = ((position['price'] - close) / position['price']) * 100
                    # Выход SHORT
                    if pnl_pct >= 3.0 or pnl_pct <= -2.0 or rsi_val < rsi_oversold:
                        pnl = (position['price'] - close) * position['qty']
                        balance += pnl
                        trades.append(pnl)
                        position = None
        
        # Закрываем открытую позицию
        if position:
            close = df['close'].iloc[-1]
            if position['side'] == 'long':
                pnl = (close - position['price']) * position['qty']
            else:
                pnl = (position['price'] - close) * position['qty']
            balance += pnl
            trades.append(pnl)
        
        if not trades:
            return -100, 0, 0
        
        total_return = ((balance - 1000) / 1000) * 100
        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t < 0]
        win_rate = (len(wins) / len(trades)) * 100 if trades else 0
        profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 0
        
        return total_return, win_rate, profit_factor
    
    def optimize_rsi_params(self, df):
        """Оптимизация RSI с реальным бэктестом"""
        logger.info("🔄 Оптимизация RSI (реальный бэктест)...")
        
        best_return = -float('inf')
        best_config = None
        
        for period in [7, 14, 21]:
            for oversold in [20, 25, 30, 35]:
                for overbought in [65, 70, 75, 80]:
                    if oversold >= overbought:
                        continue
                    
                    params = {
                        'rsi_period': period,
                        'rsi_oversold': oversold,
                        'rsi_overbought': overbought,
                        'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9
                    }
                    
                    ret, wr, pf = self._backtest_config(df, params)
                    
                    # Комбинированная оценка: доходность + win rate + profit factor
                    score = ret * 0.5 + wr * 0.3 + pf * 10
                    
                    if score > best_return:
                        best_return = score
                        best_config = {
                            'rsi_period': period,
                            'rsi_oversold': oversold,
                            'rsi_overbought': overbought
                        }
                        best_config['_return'] = ret
                        best_config['_win_rate'] = wr
                        best_config['_profit_factor'] = pf
        
        logger.info(f"✅ RSI: {best_config}, return={best_config.get('_return', 0):.2f}%")
        return best_config, best_return
    
    def optimize_macd_params(self, df):
        """Оптимизация MACD с реальным бэктестом"""
        logger.info("🔄 Оптимизация MACD (реальный бэктест)...")
        
        best_return = -float('inf')
        best_config = None
        
        for fast in [8, 12, 15]:
            for slow in [20, 26, 30]:
                if fast >= slow:
                    continue
                for signal in [7, 9, 12]:
                    params = {
                        'rsi_period': 14, 'rsi_oversold': 30, 'rsi_overbought': 70,
                        'macd_fast': fast, 'macd_slow': slow, 'macd_signal': signal
                    }
                    
                    ret, wr, pf = self._backtest_config(df, params)
                    score = ret * 0.5 + wr * 0.3 + pf * 10
                    
                    if score > best_return:
                        best_return = score
                        best_config = {
                            'macd_fast': fast, 'macd_slow': slow, 'macd_signal': signal,
                            '_return': ret, '_win_rate': wr, '_profit_factor': pf
                        }
        
        logger.info(f"✅ MACD: {best_config}, return={best_config.get('_return', 0):.2f}%")
        return best_config, best_return
    
    def run_full_optimization(self):
        """Полная оптимизация с реальным бэктестом"""
        logger.info(f"🚀 Оптимизация для {self.symbol} (реальный бэктест)...")
        
        df = self._load_historical_data()
        if df is None or len(df) < 100:
            logger.error("❌ Недостаточно данных для оптимизации")
            return None
        
        rsi_cfg, rsi_score = self.optimize_rsi_params(df)
        macd_cfg, macd_score = self.optimize_macd_params(df)
        
        # Финальный бэктест с лучшими параметрами
        final_params = {**rsi_cfg, **macd_cfg}
        final_return, final_wr, final_pf = self._backtest_config(df, final_params)
        
        optimized = {
            'rsi_period': rsi_cfg['rsi_period'],
            'rsi_oversold': rsi_cfg['rsi_oversold'],
            'rsi_overbought': rsi_cfg['rsi_overbought'],
            'macd_fast': macd_cfg['macd_fast'],
            'macd_slow': macd_cfg['macd_slow'],
            'macd_signal': macd_cfg['macd_signal'],
            'timestamp': datetime.now().isoformat(),
            'symbol': self.symbol,
            'backtest_return': final_return,
            'backtest_win_rate': final_wr,
            'backtest_profit_factor': final_pf
        }
        
        self.save_params(optimized)
        
        from telegram_utils import send_telegram_message
        send_telegram_message(
            f"🤖 <b>Оптимизация завершена</b>\n"
            f"Монета: {self.symbol}\n"
            f"RSI: {rsi_cfg['rsi_period']}/{rsi_cfg['rsi_oversold']}/{rsi_cfg['rsi_overbought']}\n"
            f"MACD: {macd_cfg['macd_fast']}/{macd_cfg['macd_slow']}/{macd_cfg['macd_signal']}\n"
            f"Бэктест: {final_return:+.2f}% | WR: {final_wr:.0f}% | PF: {final_pf:.2f}x"
        )
        
        logger.info(f"✅ Оптимизация: return={final_return:+.2f}%, WR={final_wr:.0f}%, PF={final_pf:.2f}x")
        return optimized

auto_optimizer = None
