"""
Умная система сигналов покупки/продажи
Определяет оптимальный момент для входа и выхода
"""

import logging
import pandas as pd
import numpy as np
from exchange import fetch_ohlcv_df
from ensemble_predictor import ensemble_predictor
from trading_logic import compute_indicators

logger = logging.getLogger(__name__)

class SmartSignalGenerator:
    """Умная генерация сигналов"""
    
    def __init__(self):
        self.signal_history = []
    
    def analyze_entry_conditions(self, symbol):
        """
        Анализирует условия для ВХОДА в позицию
        
        Система оценки (макс 100 очков):
        ├─ MTF анализ: 0-30 очков
        ├─ RSI + MACD: 0-30 очков
        ├─ ML прогноз: 0-25 очков
        └─ Объём: 0-15 очков
        
        Порог входа определяется стратегией в fully_autonomous_trader
        """
        try:
            logger.info(f"🔍 Анализирую условия входа для {symbol}...")
            
            conditions = {
                'symbol': symbol,
                'is_good_to_buy': False,
                'reasons': [],
                'confidence': 0,
                'entry_price': None
            }
            
            df = fetch_ohlcv_df()
            if df is None or len(df) == 0:
                conditions['reasons'].append("❌ Нет данных")
                return conditions
            
            current_price = df['close'].iloc[-1]
            conditions['entry_price'] = current_price
            
            confidence_score = 0
            bearish_block = False
            
            # === 1. MTF АНАЛИЗ (0-30 очков) ===
            try:
                from multiframe_analysis import create_mtf_analyzer
                mtf = create_mtf_analyzer(symbol)
                mtf_results = mtf.run_multiframe_analysis()
                mtf_score, consensus = mtf.get_consensus_signal(mtf_results)
                
                if mtf_score >= 2.0:
                    conditions['reasons'].append("✅ Все таймфреймы бычьи (сильный)")
                    confidence_score += 30
                elif mtf_score >= 1.0:
                    conditions['reasons'].append("✅ Большинство таймфреймов бычьи")
                    confidence_score += 22
                elif mtf_score >= 0.3:
                    conditions['reasons'].append("⚪ Таймфреймы слабо бычьи")
                    confidence_score += 15
                elif mtf_score >= 0:
                    conditions['reasons'].append("⚪ Таймфреймы смешанные")
                    confidence_score += 10
                elif mtf_score >= -1.0:
                    conditions['reasons'].append("⚠️ Таймфреймы слабо медвежьи")
                    confidence_score += 5
                else:
                    conditions['reasons'].append("❌ Все таймфреймы медвежьи")
                    bearish_block = True
            except Exception as e:
                logger.debug(f"⚠️ Ошибка MTF анализа: {e}")
                conditions['reasons'].append("⚠️ MTF анализ недоступен")
                # Даём базовые очки чтобы не блокировать вход
                confidence_score += 8
            
            # === 2. RSI + MACD АНАЛИЗ (0-30 очков) ===
            try:
                indicators = compute_indicators(df)
                
                if indicators and isinstance(indicators, dict):
                    rsi = indicators.get('rsi', 50)
                    macd_val = indicators.get('macd', 0)
                    macd_sig = indicators.get('macd_signal', 0)
                    macd_hist = indicators.get('macd_histogram', 0)
                    
                    # RSI оценка (0-20 очков)
                    if rsi < 25:
                        conditions['reasons'].append(f"✅ RSI сильно перепродан: {rsi:.1f}")
                        confidence_score += 20
                    elif rsi < 35:
                        conditions['reasons'].append(f"✅ RSI перепродан: {rsi:.1f}")
                        confidence_score += 16
                    elif rsi < 45:
                        conditions['reasons'].append(f"⚪ RSI в нижней зоне: {rsi:.1f}")
                        confidence_score += 10
                    elif rsi < 55:
                        conditions['reasons'].append(f"⚠️ RSI нейтральный: {rsi:.1f}")
                        confidence_score += 5
                    elif rsi < 70:
                        conditions['reasons'].append(f"⚠️ RSI в верхней зоне: {rsi:.1f}")
                        confidence_score += 0
                    else:
                        conditions['reasons'].append(f"❌ RSI перекуплен: {rsi:.1f}")
                        confidence_score -= 5
                    
                    # MACD оценка (0-10 очков)
                    if macd_val > macd_sig and macd_hist > 0:
                        conditions['reasons'].append("✅ MACD бычий кроссовер")
                        confidence_score += 10
                    elif macd_val > macd_sig:
                        conditions['reasons'].append("⚪ MACD бычий")
                        confidence_score += 6
                    elif macd_val < macd_sig and macd_hist < 0:
                        conditions['reasons'].append("❌ MACD медвежий кроссовер")
                        confidence_score -= 3
                    else:
                        conditions['reasons'].append("⚠️ MACD нейтральный")
                        confidence_score += 2
                        
            except Exception as e:
                logger.debug(f"⚠️ Ошибка расчёта индикаторов: {e}")
                conditions['reasons'].append("⚠️ Индикаторы недоступны")
            
            # === 3. ML ПРОГНОЗ (0-25 очков) ===
            try:
                ensemble_result = ensemble_predictor.get_ensemble_prediction()
                
                if ensemble_result and ensemble_result.get('ensemble_price') is not None:
                    direction = ensemble_result.get('direction', 'НЕЙТРАЛЬНАЯ')
                    confidence = ensemble_result.get('confidence', 0)
                    
                    if direction == 'ВВЕРХ':
                        if confidence > 0.7:
                            conditions['reasons'].append(f"✅ ML уверенно: рост ({confidence:.0%})")
                            confidence_score += 25
                        elif confidence > 0.5:
                            conditions['reasons'].append(f"✅ ML предсказывает рост ({confidence:.0%})")
                            confidence_score += 18
                        else:
                            conditions['reasons'].append(f"⚪ ML слабо: рост ({confidence:.0%})")
                            confidence_score += 10
                    elif direction == 'ВНИЗ':
                        if confidence > 0.7:
                            conditions['reasons'].append(f"❌ ML уверенно: падение ({confidence:.0%})")
                            confidence_score -= 10
                        else:
                            conditions['reasons'].append(f"⚠️ ML слабо: падение ({confidence:.0%})")
                            confidence_score -= 3
                    else:
                        conditions['reasons'].append(f"⚠️ ML нейтральный ({confidence:.0%})")
                        confidence_score += 5
                else:
                    conditions['reasons'].append("⚠️ ML прогноз недоступен")
                    confidence_score += 3
            except Exception as e:
                logger.debug(f"⚠️ Ошибка ансамбля: {e}")
                conditions['reasons'].append("⚠️ ML анализ недоступен")
                confidence_score += 3
            
            # === 4. ОБЪЁМ (0-15 очков) ===
            try:
                if len(df) >= 20:
                    avg_volume = df['volume'].tail(20).mean()
                    current_volume = df['volume'].iloc[-1]
                    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
                    
                    if volume_ratio > 2.0:
                        conditions['reasons'].append(f"✅ Объём сильно растёт ({volume_ratio:.1f}x)")
                        confidence_score += 15
                    elif volume_ratio > 1.5:
                        conditions['reasons'].append(f"✅ Объём выше среднего ({volume_ratio:.1f}x)")
                        confidence_score += 12
                    elif volume_ratio > 1.2:
                        conditions['reasons'].append(f"⚪ Объём немного выше ({volume_ratio:.1f}x)")
                        confidence_score += 8
                    elif volume_ratio > 0.8:
                        conditions['reasons'].append(f"⚠️ Объём обычный ({volume_ratio:.1f}x)")
                        confidence_score += 4
                    else:
                        conditions['reasons'].append(f"❌ Объём низкий ({volume_ratio:.1f}x)")
                        confidence_score += 0
            except Exception as e:
                logger.debug(f"⚠️ Ошибка анализа объёма: {e}")
            
            # === ИТОГОВАЯ ОЦЕНКА ===
            conditions['confidence'] = max(0, min(confidence_score, 100))
            
            # Блокировка при сильном медвежьем тренде
            if bearish_block:
                conditions['is_good_to_buy'] = False
                conditions['reasons'].append("🚫 Блокировка: сильный медвежий тренд")
            else:
                # Базовый порог — 35 очков
                # Финальный порог определяется стратегией в fully_autonomous_trader
                conditions['is_good_to_buy'] = confidence_score >= 35
            
            logger.info(
                f"📊 Результат анализа входа для {symbol}:\n"
                f"   Уверенность: {conditions['confidence']}%\n"
                f"   Рекомендация: {'🟢 КУПИТЬ' if conditions['is_good_to_buy'] else '🔴 ЖДАТЬ'}\n"
                + "\n".join(conditions['reasons'])
            )
            
            return conditions
        
        except Exception as e:
            logger.error(f"❌ Ошибка анализа входа: {e}")
            return {
                'is_good_to_buy': False,
                'reasons': [f"❌ Ошибка: {e}"],
                'confidence': 0,
                'entry_price': None
            }
    
    def analyze_exit_conditions(self, symbol, entry_price, current_price, side='Buy'):
        """
        Анализирует условия для ВЫХОДА из позиции
        Использует параметры текущей стратегии
        Теперь поддерживает как LONG так и SHORT позиции

        Args:
            symbol: торговая пара
            entry_price: цена входа в позицию
            current_price: текущая цена
            side: направление позиции ('Buy' для LONG, 'Sell' для SHORT)
        """
        try:
            # ✅ ПРАВИЛЬНЫЙ РАСЧЕТ ДЛЯ LONG И SHORT
            if side == 'Buy':  # LONG позиция
                profit_percent = ((current_price - entry_price) / entry_price) * 100
            else:  # SHORT позиция (side == 'Sell')
                profit_percent = ((entry_price - current_price) / entry_price) * 100

            # Получаем параметры из текущей стратегии
            from strategy_manager import strategy_manager
            strategy = strategy_manager.STRATEGIES[strategy_manager.current_strategy]
            tp = strategy['take_profit']
            sl = strategy['stop_loss']

            exit_signal = {
                'should_exit': False,
                'exit_type': None,
                'exit_percent': 100,
                'profit_percent': profit_percent,
                'reason': None
            }
            
            # 1. ПОЛНЫЙ Take Profit
            if profit_percent >= tp:
                exit_signal['should_exit'] = True
                exit_signal['exit_type'] = 'TAKE_PROFIT'
                exit_signal['exit_percent'] = 100
                exit_signal['reason'] = f"🟢 TAKE PROFIT: +{profit_percent:.2f}% (цель {tp}%)"
            
            # 2. ЧАСТИЧНЫЙ ВЫХОД — 50% позиции при 60% от TP
            elif profit_percent >= tp * 0.6:
                exit_signal['should_exit'] = True
                exit_signal['exit_type'] = 'PARTIAL_EXIT'
                exit_signal['exit_percent'] = 50
                exit_signal['reason'] = f"⚪ ЧАСТИЧНЫЙ ВЫХОД 50%: +{profit_percent:.2f}% (60% от TP)"
            
            # 3. ТРЕЙЛИН�� — при 40% от TP проверяем тренд
            elif profit_percent >= tp * 0.4:
                try:
                    from multiframe_analysis import create_mtf_analyzer
                    mtf = create_mtf_analyzer(symbol)
                    mtf_results = mtf.run_multiframe_analysis()
                    mtf_score, _ = mtf.get_consensus_signal(mtf_results)
                    
                    if mtf_score < 0.3:
                        exit_signal['should_exit'] = True
                        exit_signal['exit_type'] = 'TREND_END'
                        exit_signal['exit_percent'] = 30
                        exit_signal['reason'] = f"⚪ ТРЕНД УГАСАЕТ: +{profit_percent:.2f}%"
                except:
                    pass
            
            # 4. Stop Loss
            if profit_percent <= -sl:
                exit_signal['should_exit'] = True
                exit_signal['exit_type'] = 'STOP_LOSS'
                exit_signal['exit_percent'] = 100
                exit_signal['reason'] = f"🔴 СТОП-ЛОСС: {profit_percent:.2f}% (лимит -{sl}%)"
            
            # 5. ТРЕЙЛИНГ стоп: если было +2% и упало до +0.5% — выходим
            elif profit_percent >= 0.5 and profit_percent < tp * 0.3:
                # Маленькая прибыль и не растёт — лучше зафиксировать
                try:
                    from exchange import fetch_ohlcv_df
                    df = fetch_ohlcv_df()
                    if df is not None and len(df) >= 5:
                        recent_closes = df['close'].tail(5).tolist()
                        # Цена падает последние 5 свечей
                        falling = all(recent_closes[i] >= recent_closes[i+1] for i in range(len(recent_closes)-1))
                        if falling:
                            exit_signal['should_exit'] = True
                            exit_signal['exit_type'] = 'TRAILING_STOP'
                            exit_signal['exit_percent'] = 100
                            exit_signal['reason'] = f"📉 ТРЕЙЛИНГ: прибыль тает +{profit_percent:.2f}%, цена падает"
                except:
                    pass
            
            if exit_signal['should_exit']:
                logger.info(
                    f"📊 Сигнал выхода для {symbol}:\n"
                    f"   Тип: {exit_signal['exit_type']}\n"
                    f"   Прибыль: {profit_percent:+.2f}%\n"
                    f"   Выход: {exit_signal['exit_percent']}%\n"
                    f"   Причина: {exit_signal['reason']}"
                )
            
            return exit_signal
        
        except Exception as e:
            logger.error(f"❌ Ошибка анализа выхода: {e}")
            return {'should_exit': False}


smart_signal_generator = SmartSignalGenerator()
