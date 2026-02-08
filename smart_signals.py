"""
Умная система сигналов покупки/продажи
Определяет оптимальный момент для входа и выхода
"""

import logging
import pandas as pd
import numpy as np
from exchange import fetch_ohlcv_df
from ensemble_predictor import ensemble_predictor

logger = logging.getLogger(__name__)

class SmartSignalGenerator:
    """Умная генерация сигналов"""
    
    def __init__(self):
        self.signal_history = []
    
    def analyze_entry_conditions(self, symbol):
        """
        Анализирует условия для ВХОДА в позицию
        """
        try:
            logger.info(f"🔍 Анализирую условия входа для {symbol}...")
            
            conditions = {
                'symbol': symbol,
                'is_good_to_buy': True,
                'reasons': [],
                'confidence': 0,
                'entry_price': None
            }
            
            df = fetch_ohlcv_df()
            if df is None or len(df) == 0:
                conditions['is_good_to_buy'] = False
                conditions['reasons'].append("❌ Нет данных")
                return conditions
            
            current_price = df['close'].iloc[-1]
            conditions['entry_price'] = current_price
            
            confidence_score = 0
            
            # 1. Проверяем MTF тренд
            try:
                from multiframe_analysis import create_mtf_analyzer
                mtf = create_mtf_analyzer(symbol)
                mtf_results = mtf.run_multiframe_analysis()
                mtf_score, consensus = mtf.get_consensus_signal(mtf_results)
                
                if mtf_score >= 1.0:
                    conditions['reasons'].append("✅ Все таймфреймы бычьи")
                    confidence_score += 25
                elif mtf_score > 0:
                    conditions['reasons'].append("⚪ Таймфреймы смешанные")
                    confidence_score += 10
                else:
                    conditions['reasons'].append("❌ Таймфреймы медвежьи")
                    conditions['is_good_to_buy'] = False
            except Exception as e:
                logger.debug(f"⚠️ Ошибка MTF анализа: {e}")
                conditions['reasons'].append("⚠️ MTF анализ недоступен")
            
            # 2. Проверяем простой технический анализ
            try:
                from trading_logic import compute_indicators
                indicators = compute_indicators(df)
                
                if indicators:
                    rsi = indicators.get('rsi', 50)
                    
                    if rsi < 30:
                        conditions['reasons'].append("✅ RSI перепродан (хороший вход)")
                        confidence_score += 20
                    elif rsi < 45:
                        conditions['reasons'].append("⚪ RSI в нижней половине")
                        confidence_score += 10
                    elif rsi > 70:
                        conditions['reasons'].append("❌ RSI перекуплен")
                        conditions['is_good_to_buy'] = False
                    else:
                        conditions['reasons'].append("⚠️ RSI нейтральный")
            except Exception as e:
                logger.debug(f"⚠️ Ошибка расчёта индикаторов: {e}")
            
            # 3. Проверяем Ensemble
            try:
                ensemble_result = ensemble_predictor.get_ensemble_prediction()
                
                if ensemble_result and ensemble_result.get('direction') == 'ВВЕРХ':
                    confidence = ensemble_result.get('confidence', 0)
                    if confidence > 0.6:
                        conditions['reasons'].append(f"✅ ML предсказывает рост ({confidence:.1%})")
                        confidence_score += 25
                    else:
                        conditions['reasons'].append(f"⚪ ML слабо предсказывает рост ({confidence:.1%})")
                        confidence_score += 10
                else:
                    conditions['reasons'].append("❌ ML предсказывает падение")
                    conditions['is_good_to_buy'] = False
            except Exception as e:
                logger.debug(f"⚠️ Ошибка ансамбля: {e}")
                conditions['reasons'].append("⚠️ ML анализ недоступен")
            
            # 4. Простая проверка объёма
            try:
                if len(df) >= 20:
                    avg_volume = df['volume'].tail(20).mean()
                    current_volume = df['volume'].iloc[-1]
                    
                    if current_volume > avg_volume * 1.3:
                        conditions['reasons'].append("✅ Объём растёт")
                        confidence_score += 15
                    else:
                        conditions['reasons'].append("⚠️ Объём обычный")
            except Exception as e:
                logger.debug(f"⚠️ Ошибка анализа объёма: {e}")
            
            conditions['confidence'] = confidence_score
            conditions['is_good_to_buy'] = conditions['is_good_to_buy'] and confidence_score >= 50
            
            logger.info(
                f"📊 Результат анализа входа для {symbol}:\n"
                f"   Уверенность: {confidence_score}%\n"
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
    
    def analyze_exit_conditions(self, symbol, entry_price, current_price):
        """
        Анализирует условия для ВЫХОДА из позиции
        """
        try:
            profit_percent = ((current_price - entry_price) / entry_price) * 100
            
            exit_signal = {
                'should_exit': False,
                'exit_type': None,
                'exit_percent': 100,
                'profit_percent': profit_percent,
                'reason': None
            }
            
            # 1. Take Profit уровни
            if profit_percent >= 15:
                exit_signal['should_exit'] = True
                exit_signal['exit_type'] = 'TAKE_PROFIT'
                exit_signal['exit_percent'] = 100
                exit_signal['reason'] = f"🟢 TAKE PROFIT: +{profit_percent:.2f}%"
            
            elif profit_percent >= 10:
                exit_signal['should_exit'] = True
                exit_signal['exit_type'] = 'PARTIAL_EXIT'
                exit_signal['exit_percent'] = 50
                exit_signal['reason'] = f"⚪ PARTIAL EXIT: +{profit_percent:.2f}%"
            
            elif profit_percent >= 5:
                # Проверяем тренд
                try:
                    from multiframe_analysis import create_mtf_analyzer
                    mtf = create_mtf_analyzer(symbol)
                    mtf_results = mtf.run_multiframe_analysis()
                    mtf_score, _ = mtf.get_consensus_signal(mtf_results)
                    
                    if mtf_score < 0.5:
                        exit_signal['should_exit'] = True
                        exit_signal['exit_type'] = 'TREND_END'
                        exit_signal['exit_percent'] = 30
                        exit_signal['reason'] = f"⚪ TREND FADING: +{profit_percent:.2f}%"
                except:
                    pass
            
            # 2. Stop Loss
            if profit_percent < -3:
                exit_signal['should_exit'] = True
                exit_signal['exit_type'] = 'STOP_LOSS'
                exit_signal['exit_percent'] = 100
                exit_signal['reason'] = f"🔴 STOP LOSS: {profit_percent:.2f}%"
            
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
