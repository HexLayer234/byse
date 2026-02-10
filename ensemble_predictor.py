"""
Ансамбль предсказателей (РУССКАЯ ВЕРСИЯ)
"""

import logging
import numpy as np
import pandas as pd
from typing import Tuple, Dict
from exchange import fetch_ohlcv_df
from prediction import predict_price
from neural_network import get_lstm_prediction

logger = logging.getLogger(__name__)

class EnsemblePredictor:
    """Ансамбль моделей для прогнозирования"""
    
    def __init__(self, weights=None):
        self.weights = weights or {
            'lstm': 0.4,
            'prophet': 0.4,
            'xgboost': 0.2
        }
        
        self.models = {
            'lstm': self.get_lstm_prediction,
            'prophet': self.get_prophet_prediction,
            'xgboost': self.get_xgboost_prediction
        }
        
        self.predictions = {}
        self.ensemble_prediction = None
        self.confidence = 0
    
    def get_lstm_prediction(self) -> Tuple[float, float, float]:
        """Получает предсказание от LSTM (с относительным прогнозом)"""
        try:
            from exchange import fetch_ohlcv_df
            
            df = fetch_ohlcv_df()
            if df is None or len(df) < 2:
                return None, None, None
            
            current_price = df['close'].iloc[-1]
            
            # Вызываем LSTM
            predicted, lower, upper = get_lstm_prediction()
            
            if predicted is None:
                return None, None, None
            
            # Проверка: если LSTM дала неадекватный прогноз (для дешёвых монет)
            # Используем ОТНОСИТЕЛЬНОЕ изменение вместо абсолютного
            
            # Если разница больше 50% от текущей цены - прогноз неверный
            price_diff_percent = abs(predicted - current_price) / current_price
            
            if price_diff_percent > 5.0:  # Если разница > 500%
                logger.warning(f"⚠️ LSTM прогноз неадекватен: ${predicted:.8f} vs ${current_price:.8f} ({price_diff_percent*100:.1f}% разница)")
                
                # Используем Prophet или пропускаем
                return None, None, None
            
            return predicted, lower, upper
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предсказания LSTM: {e}")
            return None, None, None
    
    def get_prophet_prediction(self) -> Tuple[float, float, float]:
        """Получает предсказание от Prophet"""
        try:
            predicted, lower, upper = predict_price(hours_ahead=4)
            if predicted is not None:
                return predicted, lower, upper
            return None, None, None
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предсказания Prophet: {e}")
            return None, None, None
    
    def get_xgboost_prediction(self) -> Tuple[float, float, float]:
        """
        Реальный XGBoost/GradientBoosting на 25 технических фичах:
        RSI, MACD, ATR, Bollinger, EMA, объём, волатильность, время.
        Фолбэк на линейную экстраполяцию если модель недоступна.
        """
        try:
            from xgboost_model import get_xgb_prediction, xgb_predictor
            
            # Пробуем реальный XGBoost
            if xgb_predictor.is_trained:
                predicted, lower, upper = get_xgb_prediction()
                if predicted is not None:
                    return predicted, lower, upper
            
            # Инициализируем если ещё не обучен
            if not xgb_predictor.is_trained:
                from xgboost_model import init_xgboost
                init_xgboost()
                predicted, lower, upper = get_xgb_prediction()
                if predicted is not None:
                    return predicted, lower, upper
            
            # Фолбэк — линейная экстраполяция
            logger.debug("⚠️ XGBoost недоступен, фолбэк на линейную модель")
            df = fetch_ohlcv_df()
            if df is None or len(df) < 20:
                return None, None, None
            
            prices = df['close'].values[-20:]
            trend = (prices[-1] - prices[0]) / len(prices)
            predicted = prices[-1] + trend * 12
            lower = predicted * 0.98
            upper = predicted * 1.02
            return predicted, lower, upper
        
        except Exception as e:
            logger.warning(f"⚠️ Ошибка XGBoost: {e}")
            return None, None, None
    
    def get_ensemble_prediction(self) -> Dict:
        """Получает ансамбльное предсказание"""
        logger.info("🤖 Запуск ансамбля прогнозирования...")
        
        self.predictions = {}
        valid_predictions = []
        total_weight = 0
        
        for model_name, model_func in self.models.items():
            try:
                predicted, lower, upper = model_func()
                
                if predicted is not None:
                    weight = self.weights[model_name]
                    
                    self.predictions[model_name] = {
                        'predicted': predicted,
                        'lower': lower,
                        'upper': upper,
                        'weight': weight,
                        'status': 'ОК'
                    }
                    
                    valid_predictions.append((predicted, weight))
                    total_weight += weight
                    
                    logger.debug(
                        f"   ✅ {model_name:10} → ${predicted:.8f} "
                        f"(вес: {weight:.1%})"
                    )
                
                else:
                    self.predictions[model_name] = {'status': 'НЕ ПОЛУЧЕНО'}
                    logger.warning(f"   ⚠️ {model_name:10} → Нет предсказания")
            
            except Exception as e:
                self.predictions[model_name] = {'status': 'ОШИБКА', 'error': str(e)}
                logger.error(f"   ❌ {model_name:10} → Ошибка: {e}")
        
        if not valid_predictions:
            logger.error("❌ Нет валидных предсказаний")
            return {
                'ensemble_price': None,
                'confidence': 0,
                'direction': None,
                'predictions': self.predictions
            }
        
        if total_weight > 0:
            ensemble_price = sum(pred * (weight / total_weight) for pred, weight in valid_predictions)
        else:
            ensemble_price = np.mean([pred for pred, _ in valid_predictions])
        
        predictions_list = [pred for pred, _ in valid_predictions]
        std_dev = np.std(predictions_list)
        mean_pred = np.mean(predictions_list)
        
        cv = (std_dev / mean_pred) if mean_pred != 0 else 0
        confidence = max(0, 1 - cv)
        
        df = fetch_ohlcv_df()
        current_price = df['close'].iloc[-1] if df is not None else 0
        
        if ensemble_price > current_price * 1.005:
            direction = 'ВВЕРХ'
        elif ensemble_price < current_price * 0.995:
            direction = 'ВНИЗ'
        else:
            direction = 'НЕЙТРАЛЬНАЯ'
        
        self.ensemble_prediction = ensemble_price
        self.confidence = confidence
        
        result = {
            'ensemble_price': ensemble_price,
            'current_price': current_price,
            'direction': direction,
            'confidence': confidence,
            'agreement_score': 1 - cv,
            'predictions': self.predictions,
            'individual_predictions': {
                k: v.get('predicted') for k, v in self.predictions.items() 
                if v.get('predicted') is not None
            }
        }
        
        return result
    
    def adjust_weights(self, new_weights: Dict[str, float]):
        """Корректирует веса моделей"""
        self.weights = new_weights
        logger.info(f"📊 Веса обновлены: {self.weights}")

ensemble_predictor = EnsemblePredictor()
