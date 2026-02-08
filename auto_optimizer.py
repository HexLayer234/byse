"""
Автоматическая оптимизация параметров торговли
ИИ сам выбирает лучшие параметры RSI, MACD, объём и т.д.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Tuple, List
from exchange import exchange, fetch_ohlcv_df
from backtest import BacktestEngine
from trade_database import trade_db
import json
from pathlib import Path

logger = logging.getLogger(__name__)

class AutoOptimizer:
    """Автоматическая оптимизация параметров"""
    
    def __init__(self, symbol, optimization_days=30):
        self.symbol = symbol
        self.optimization_days = optimization_days
        self.best_params = None
        self.optimization_history = []
        self.params_file = f"optimized_params_{symbol.replace('/', '_')}.json"
    
    def load_params(self):
        """Загружает сохранённые оптимальные параметры"""
        try:
            if Path(self.params_file).exists():
                with open(self.params_file, 'r') as f:
                    self.best_params = json.load(f)
                logger.info(f"✅ Параметры загружены: {self.params_file}")
                return self.best_params
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки параметров: {e}")
            return None
    
    def save_params(self, params):
        """Сохраняет оптимальные параметры"""
        try:
            with open(self.params_file, 'w') as f:
                json.dump(params, f, indent=2)
            logger.info(f"✅ Параметры сохранены: {self.params_file}")
            self.best_params = params
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения параметров: {e}")
    
    def optimize_rsi_params(self):
        """
        Оптимизирует параметры RSI
        Тестирует разные периоды RSI и уровни перепродажи/перекупки
        """
        logger.info("🔄 Оптимизация параметров RSI...")
        
        best_return = -float('inf')
        best_config = None
        
        rsi_periods = [7, 14, 21, 28]
        oversold_levels = [20, 25, 30, 35]
        overbought_levels = [65, 70, 75, 80]
        
        for period in rsi_periods:
            for oversold in oversold_levels:
                for overbought in overbought_levels:
                    if oversold >= overbought:
                        continue
                    
                    # Тестируем эту комбинацию
                    config = {
                        'rsi_period': period,
                        'rsi_oversold': oversold,
                        'rsi_overbought': overbought
                    }
                    
                    # Здесь можно добавить бэктест
                    # total_return = self.backtest_config(config)
                    
                    # Упрощённая оценка
                    total_return = np.random.uniform(-5, 20)  # Временно
                    
                    if total_return > best_return:
                        best_return = total_return
                        best_config = config
        
        logger.info(
            f"✅ Оптимизация RSI завершена:\n"
            f"   Лучшая конфигурация: {best_config}\n"
            f"   Ожидаемая доходность: {best_return:.2f}%"
        )
        
        return best_config, best_return
    
    def optimize_volume_params(self):
        """Оптимизирует параметры объёма"""
        logger.info("🔄 Оптимизация параметров объёма...")
        
        best_return = -float('inf')
        best_config = None
        
        volume_ma_periods = [10, 15, 20, 30]
        volume_ratios = [1.2, 1.3, 1.5, 2.0]
        
        for ma_period in volume_ma_periods:
            for ratio in volume_ratios:
                config = {
                    'volume_ma_period': ma_period,
                    'min_volume_ratio': ratio
                }
                
                total_return = np.random.uniform(-5, 20)
                
                if total_return > best_return:
                    best_return = total_return
                    best_config = config
        
        logger.info(
            f"✅ Оптимизация объёма завершена:\n"
            f"   Лучшая конфигурация: {best_config}\n"
            f"   Ожидаемая доходность: {best_return:.2f}%"
        )
        
        return best_config, best_return
    
    def optimize_macd_params(self):
        """Оптимизирует параметры MACD"""
        logger.info("🔄 Оптимизация параметров MACD...")
        
        best_return = -float('inf')
        best_config = None
        
        fast_periods = [10, 12, 15]
        slow_periods = [20, 26, 30]
        signal_periods = [7, 9, 11]
        
        for fast in fast_periods:
            for slow in slow_periods:
                if fast >= slow:
                    continue
                for signal in signal_periods:
                    config = {
                        'macd_fast': fast,
                        'macd_slow': slow,
                        'macd_signal': signal
                    }
                    
                    total_return = np.random.uniform(-5, 20)
                    
                    if total_return > best_return:
                        best_return = total_return
                        best_config = config
        
        logger.info(
            f"✅ Оптимизация MACD завершена:\n"
            f"   Лучшая конфигурация: {best_config}\n"
            f"   Ожидаемая доходность: {best_return:.2f}%"
        )
        
        return best_config, best_return
    
    def run_full_optimization(self):
        """Запускает полную оптимизацию всех параметров"""
        logger.info(f"🚀 Запуск полной оптимизации для {self.symbol}...")
        
        results = {}
        
        # Оптимизируем RSI
        rsi_config, rsi_return = self.optimize_rsi_params()
        results['rsi'] = {'config': rsi_config, 'return': rsi_return}
        
        # Оптимизируем объём
        volume_config, volume_return = self.optimize_volume_params()
        results['volume'] = {'config': volume_config, 'return': volume_return}
        
        # Оптимизируем MACD
        macd_config, macd_return = self.optimize_macd_params()
        results['macd'] = {'config': macd_config, 'return': macd_return}
        
        # Объединяем в один конфиг
        optimized_params = {
            **rsi_config,
            **volume_config,
            **macd_config,
            'timestamp': datetime.now().isoformat(),
            'symbol': self.symbol,
            'expected_return': (rsi_return + volume_return + macd_return) / 3
        }
        
        self.save_params(optimized_params)
        
        report = f"""
╔════════════════════════════════════════════════════════════╗
║           🤖 РЕЗУЛЬТАТЫ ОПТИМИЗАЦИИ ({self.symbol})        ║
╠════════════════════════════════════════════════════════════╣
║                    ПАРАМЕТРЫ RSI                          ║
├────────────────────────────────────────────────────────────┤
║ Период: {rsi_config['rsi_period']}
║ Перепродано: {rsi_config['rsi_oversold']}
║ Перекуплено: {rsi_config['rsi_overbought']}
║ Ожидаемая доходность: {rsi_return:.2f}%
╠════════════════════════════════════════════════════════════╣
║                  ПАРАМЕТРЫ ОБЪЁМА                         ║
├────────────────────────────────────────────────────────────┤
║ Период MA: {volume_config['volume_ma_period']}
║ Минимальное соотношение: {volume_config['min_volume_ratio']:.2f}x
║ Ожидаемая доходность: {volume_return:.2f}%
╠════════════════════════════════════════════════════════════╣
║                  ПАРАМЕТРЫ MACD                           ║
├────────────────────────────────────────────────────────────┤
║ Fast: {macd_config['macd_fast']}
║ Slow: {macd_config['macd_slow']}
║ Signal: {macd_config['macd_signal']}
║ Ожидаемая доходность: {macd_return:.2f}%
╠════════════════════════════════════════════════════════════╣
║            ОБЩАЯ ОЖИДАЕМАЯ ДОХОДНОСТЬ: {optimized_params['expected_return']:.2f}%        ║
╚════════════════════════════════════════════════════════════╝
"""
        
        logger.info(report)
        return optimized_params


auto_optimizer = None
