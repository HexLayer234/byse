"""
Менеджер стратегий
Автоматически выбирает оптимальную стратегию на основе условий рынка
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from exchange import fetch_ohlcv_df
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

class StrategyManager:
    """Управление торговыми стратегиями"""
    
    STRATEGIES = {
        'ULTRA_CONSERVATIVE': {
            'name': '🐌 УЛЬТРА-КОНСЕРВАТИВНАЯ',
            'leverage': 1,
            'risk_per_trade': 0.5,
            'position_size': 0.2,  # 20% баланса
            'stop_loss': 2.0,
            'take_profit': 5.0,
            'entry_threshold': 80,  # Нужна высокая уверенность
            'description': 'Минимальный риск, долгосрочные позиции'
        },
        'CONSERVATIVE': {
            'name': '🛡️ КОНСЕРВАТИВНАЯ',
            'leverage': 3,
            'risk_per_trade': 1.0,
            'position_size': 0.3,  # 30% баланса
            'stop_loss': 2.5,
            'take_profit': 8.0,
            'entry_threshold': 70,
            'description': 'Низкий риск, стабильная торговля'
        },
        'BALANCED': {
            'name': '⚖️ СБАЛАНСИРОВАННАЯ',
            'leverage': 10,
            'risk_per_trade': 2.0,
            'position_size': 0.5,  # 50% баланса
            'stop_loss': 3.0,
            'take_profit': 12.0,
            'entry_threshold': 60,
            'description': 'Средний риск/прибыль'
        },
        'MODERATE_AGGRESSIVE': {
            'name': '💪 УМЕРЕННО-АГРЕССИВНАЯ',
            'leverage': 20,
            'risk_per_trade': 3.0,
            'position_size': 0.7,  # 70% баланса
            'stop_loss': 4.0,
            'take_profit': 18.0,
            'entry_threshold': 55,
            'description': 'Выше риск, больше прибыль'
        },
        'AGGRESSIVE': {
            'name': '🔥 АГРЕССИВНАЯ',
            'leverage': 30,
            'risk_per_trade': 4.0,
            'position_size': 0.8,  # 80% баланса
            'stop_loss': 5.0,
            'take_profit': 25.0,
            'entry_threshold': 50,
            'description': 'Высокий риск, быстрая прибыль'
        },
        'ULTRA_AGGRESSIVE': {
            'name': '🚀 УЛЬТРА-АГРЕССИВНАЯ',
            'leverage': 50,
            'risk_per_trade': 5.0,
            'position_size': 0.9,  # 90% баланса
            'stop_loss': 7.0,
            'take_profit': 35.0,
            'entry_threshold': 45,
            'description': 'Максимальный риск и прибыль'
        },
        'SCALPING': {
            'name': '⚡ СКАЛЬПИНГ',
            'leverage': 15,
            'risk_per_trade': 2.5,
            'position_size': 0.6,  # 60% баланса
            'stop_loss': 1.0,
            'take_profit': 2.0,
            'entry_threshold': 50,
            'description': 'Быстрые сделки, маленький профит'
        },
        'SWING': {
            'name': '📈 СВИНГ-ТРЕЙДИНГ',
            'leverage': 5,
            'risk_per_trade': 1.5,
            'position_size': 0.4,  # 40% баланса
            'stop_loss': 5.0,
            'take_profit': 20.0,
            'entry_threshold': 65,
            'description': 'Среднесрочные позиции'
        }
    }
    
    def __init__(self):
        self.current_strategy = 'BALANCED'
        self.strategy_history = []
        self.history_file = "strategy_history.json"
        self.auto_switch_enabled = True
        self.load_history()
    
    def load_history(self):
        """Загружает историю стратегий"""
        try:
            if Path(self.history_file).exists():
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    self.current_strategy = data.get('current_strategy', 'BALANCED')
                    self.strategy_history = data.get('history', [])
                logger.info(f"✅ Стратегия загружена: {self.current_strategy}")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки стратегии: {e}")
    
    def save_history(self):
        """Сохраняет историю стратегий"""
        try:
            data = {
                'current_strategy': self.current_strategy,
                'history': self.strategy_history[-100:],  # Последние 100 записей
                'timestamp': datetime.now().isoformat()
            }
            with open(self.history_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения стратегии: {e}")
    
    def analyze_market_conditions(self, symbol):
        """
        Анализирует условия рынка
        Возвращает: volatility, trend, volume, market_type
        """
        try:
            df = fetch_ohlcv_df()
            
            if df is None or len(df) < 50:
                return None
            
            # 1. ВОЛАТИЛЬНОСТЬ
            returns = df['close'].pct_change().dropna()
            volatility = returns.std() * 100
            
            # 2. ТРЕНД
            sma_20 = df['close'].rolling(window=20).mean().iloc[-1]
            sma_50 = df['close'].rolling(window=50).mean().iloc[-1]
            current_price = df['close'].iloc[-1]
            
            if current_price > sma_20 > sma_50:
                trend = 'STRONG_UPTREND'
                trend_score = 100
            elif current_price > sma_20:
                trend = 'UPTREND'
                trend_score = 70
            elif current_price < sma_20 < sma_50:
                trend = 'STRONG_DOWNTREND'
                trend_score = -100
            elif current_price < sma_20:
                trend = 'DOWNTREND'
                trend_score = -70
            else:
                trend = 'RANGING'
                trend_score = 0
            
            # 3. ОБЪЁМ
            avg_volume = df['volume'].tail(20).mean()
            current_volume = df['volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            # 4. ТИП РЫНКА
            if volatility > 5.0 and volume_ratio > 1.5:
                market_type = 'HIGH_VOLATILITY_HIGH_VOLUME'
            elif volatility > 3.0:
                market_type = 'HIGH_VOLATILITY'
            elif volatility < 1.0:
                market_type = 'LOW_VOLATILITY'
            elif volume_ratio > 1.5:
                market_type = 'HIGH_VOLUME'
            else:
                market_type = 'NORMAL'
            
            # 5. ДИНАМИКА ЦЕНЫ (за последние 24ч)
            price_change_24h = ((df['close'].iloc[-1] - df['close'].iloc[-24]) / df['close'].iloc[-24]) * 100 if len(df) >= 24 else 0
            
            return {
                'volatility': volatility,
                'trend': trend,
                'trend_score': trend_score,
                'volume_ratio': volume_ratio,
                'market_type': market_type,
                'price_change_24h': price_change_24h
            }
        
        except Exception as e:
            logger.error(f"❌ Ошибка анализа рынка: {e}")
            return None
    
    def select_optimal_strategy(self, market_conditions, performance_stats=None):
        """
        Выбирает оптимальную стратегию на основе условий рынка
        """
        try:
            if market_conditions is None:
                return self.current_strategy
            
            volatility = market_conditions['volatility']
            trend = market_conditions['trend']
            trend_score = market_conditions['trend_score']
            volume_ratio = market_conditions['volume_ratio']
            market_type = market_conditions['market_type']
            price_change = market_conditions['price_change_24h']
            
            logger.info(f"📊 Условия рынка:")
            logger.info(f"   Волатильность: {volatility:.2f}%")
            logger.info(f"   Тренд: {trend} (score: {trend_score})")
            logger.info(f"   Объём: {volume_ratio:.2f}x")
            logger.info(f"   Тип рынка: {market_type}")
            logger.info(f"   Изменение 24ч: {price_change:+.2f}%")
            
            # ЛОГИКА ВЫБОРА СТРАТЕГИИ
            
            # 1. НИЗКАЯ ВОЛАТИЛЬНОСТЬ → КОНСЕРВАТИВНО
            if volatility < 1.0:
                recommended = 'CONSERVATIVE'
                reason = "Низкая волатильность → консервативный подход"
            
            # 2. СИЛЬНЫЙ ВОСХОДЯЩИЙ ТРЕНД + ВЫСОКИЙ ОБЪЁМ → АГРЕССИВНО
            elif trend == 'STRONG_UPTREND' and volume_ratio > 1.5:
                recommended = 'AGGRESSIVE'
                reason = "Сильный бычий тренд + высокий объём → агрессивная торговля"
            
            # 3. ВЫСОКАЯ ВОЛАТИЛЬНОСТЬ + ВОСХОДЯЩИЙ ТРЕНД → УМЕРЕННО-АГРЕССИВНО
            elif volatility > 3.0 and trend_score > 50:
                recommended = 'MODERATE_AGGRESSIVE'
                reason = "Высокая волатильность + бычий тренд → умеренно-агрессивно"
            
            # 4. ОЧЕНЬ ВЫСОКАЯ ВОЛАТИЛЬНОСТЬ (>5%) + СИЛЬНЫЙ ТРЕНД → УЛЬТРА-АГРЕССИВНО
            elif volatility > 5.0 and abs(trend_score) > 70:
                recommended = 'ULTRA_AGGRESSIVE'
                reason = "Экстремальная волатильность + сильный тренд → максимальный риск"
            
            # 5. ОЧЕНЬ НИЗКАЯ ВОЛАТИЛЬНОСТЬ + ФЛЭТ → СКАЛЬПИНГ
            elif volatility < 1.5 and trend == 'RANGING':
                recommended = 'SCALPING'
                reason = "Низкая волатильность + флэт → скальпинг"
            
            # 6. СРЕДНЯЯ ВОЛАТИЛЬНОСТЬ + ТРЕНД → СВИНГ
            elif 2.0 < volatility < 4.0 and abs(trend_score) > 50:
                recommended = 'SWING'
                reason = "Умеренная волатильность + тренд → свинг-трейдинг"
            
            # 7. НИСХОДЯЩИЙ ТРЕНД → УЛЬТРА-КОНСЕРВАТИВНО или НЕ ТОРГОВАТЬ
            elif trend_score < -50:
                recommended = 'ULTRA_CONSERVATIVE'
                reason = "Медвежий рынок → минимальный риск"
            
            # 8. ДЕФОЛТ → СБАЛАНСИРОВАННАЯ
            else:
                recommended = 'BALANCED'
                reason = "Нормальные условия → сбалансированная стратегия"
            
            # Учитываем производительность
            if performance_stats:
                win_rate = performance_stats.get('win_rate', 50)
                
                # Если win rate низкий - понижаем агрессивность
                if win_rate < 40 and recommended in ['ULTRA_AGGRESSIVE', 'AGGRESSIVE']:
                    recommended = 'BALANCED'
                    reason += " | Низкий win rate → снижаем риск"
                
                # Если win rate высокий - можем повысить агрессивность
                elif win_rate > 70 and recommended == 'BALANCED':
                    recommended = 'MODERATE_AGGRESSIVE'
                    reason += " | Высокий win rate → увеличиваем риск"
            
            logger.info(f"🎯 Рекомендуемая стратегия: {self.STRATEGIES[recommended]['name']}")
            logger.info(f"   Причина: {reason}")
            
            return recommended, reason
        
        except Exception as e:
            logger.error(f"❌ Ошибка выбора стратегии: {e}")
            return self.current_strategy, "Ошибка анализа"
    
    def switch_strategy(self, new_strategy, reason="Ручное переключение"):
        """Переключает стратегию"""
        try:
            if new_strategy not in self.STRATEGIES:
                logger.error(f"❌ Неизвестная стратегия: {new_strategy}")
                return False
            
            old_strategy = self.current_strategy
            self.current_strategy = new_strategy
            
            # Сохраняем в историю
            self.strategy_history.append({
                'timestamp': datetime.now().isoformat(),
                'from': old_strategy,
                'to': new_strategy,
                'reason': reason
            })
            
            self.save_history()
            
            # Применяем параметры стратегии
            self._apply_strategy_params(new_strategy)
            
            logger.info(f"🔄 Стратегия изменена: {old_strategy} → {new_strategy}")
            logger.info(f"   Причина: {reason}")
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Ошибка переключения стратегии: {e}")
            return False
    
    def _apply_strategy_params(self, strategy_name):
        """Применяет параметры стратегии к конфигурации"""
        try:
            import config
            
            strategy = self.STRATEGIES[strategy_name]
            
            config.LEVERAGE = strategy['leverage']
            config.RISK_PER_TRADE = strategy['risk_per_trade']
            config.STOP_LOSS_PERCENT = strategy['stop_loss']
            config.TAKE_PROFIT_PERCENT = strategy['take_profit']
            
            logger.info(f"✅ Параметры стратегии '{strategy['name']}' применены:")
            logger.info(f"   Плечо: {strategy['leverage']}x")
            logger.info(f"   Риск: {strategy['risk_per_trade']}%")
            logger.info(f"   SL: {strategy['stop_loss']}% | TP: {strategy['take_profit']}%")
        
        except Exception as e:
            logger.error(f"❌ Ошибка применения параметров: {e}")
    
    def auto_adjust_strategy(self, symbol, performance_stats=None):
        """Автоматически подстраивает стратегию"""
        try:
            if not self.auto_switch_enabled:
                return False
            
            market_conditions = self.analyze_market_conditions(symbol)
            
            if market_conditions is None:
                return False
            
            recommended, reason = self.select_optimal_strategy(market_conditions, performance_stats)
            
            if recommended != self.current_strategy:
                return self.switch_strategy(recommended, reason)
            
            return False
        
        except Exception as e:
            logger.error(f"❌ Ошибка автоподстройки: {e}")
            return False
    
    def get_current_strategy_info(self):
        """Возвращает информацию о текущей стратегии"""
        strategy = self.STRATEGIES[self.current_strategy]
        
        return f"""
╔════════════════════════════════════════════════════════════╗
║           {strategy['name']}                              ║
╠════════════════════════════════════════════════════════════╣
║ {strategy['description']}
║
║ 📊 ПАРАМЕТРЫ:
║   • Плечо: {strategy['leverage']}x
║   • Риск на сделку: {strategy['risk_per_trade']}%
║   • Размер позиции: {strategy['position_size']*100:.0f}% баланса
║   • Stop Loss: {strategy['stop_loss']}%
║   • Take Profit: {strategy['take_profit']}%
║   • Порог входа: {strategy['entry_threshold']}%
╚════════════════════════════════════════════════════════════╝
"""
    
    def get_all_strategies_info(self):
        """Возвращает информацию о всех стратегиях"""
        info = "<b>📊 ДОСТУПНЫЕ СТРАТЕГИИ:</b>\n\n"
        
        for key, strategy in self.STRATEGIES.items():
            is_current = "✅" if key == self.current_strategy else "⚪"
            info += f"{is_current} <b>{strategy['name']}</b>\n"
            info += f"   Плечо: {strategy['leverage']}x | Риск: {strategy['risk_per_trade']}%\n"
            info += f"   {strategy['description']}\n\n"
        
        return info


strategy_manager = StrategyManager()
