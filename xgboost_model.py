"""
Реальный XGBoost/GradientBoosting предсказатель цены.
Использует 20+ технических фичей для прогноза направления.
Работает на CPU, быстрый (~миллисекунды на предсказание).
"""

import logging
import numpy as np
import pandas as pd
import pickle
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# Пробуем XGBoost, если нет — sklearn GradientBoosting
_xgb_available = None
_model_class = None

def _check_xgboost():
    """Проверяет доступность XGBoost"""
    global _xgb_available, _model_class
    if _xgb_available is not None:
        return _xgb_available
    
    try:
        from xgboost import XGBRegressor
        _model_class = XGBRegressor
        _xgb_available = True
        logger.info("✅ XGBoost доступен")
    except ImportError:
        try:
            from sklearn.ensemble import GradientBoostingRegressor
            _model_class = GradientBoostingRegressor
            _xgb_available = True
            logger.info("✅ XGBoost не найден, используем sklearn GradientBoosting")
        except ImportError:
            _xgb_available = False
            logger.warning("⚠️ Ни XGBoost, ни sklearn не найдены")
    
    return _xgb_available


class XGBoostPredictor:
    """
    XGBoost предсказатель на основе технических индикаторов.
    
    Фичи (25):
    - RSI, MACD, MACD гистограмма
    - ATR, Bollinger %B
    - Изменение цены за 3/5/10/20 свечей
    - EMA 9/21/50 относительно цены
    - Объём относительно среднего
    - Час дня (0-23)
    - День недели (0-6)
    - Стандартное отклонение за 10/20 свечей
    - Количество зелёных свечей из последних 10
    """
    
    def __init__(self, forecast_horizon=12):
        self.forecast_horizon = forecast_horizon  # Свечей вперёд
        self.model = None
        self.is_trained = False
        self.trained_symbol = None
        self.feature_names = []
        
        self.model_dir = 'models'
        os.makedirs(self.model_dir, exist_ok=True)
    
    def _build_features(self, df):
        """
        Строит матрицу фичей из OHLCV данных.
        Возвращает DataFrame с фичами.
        """
        if df is None or len(df) < 60:
            return None
        
        feat = pd.DataFrame(index=df.index)
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        # === RSI ===
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        feat['rsi'] = 100 - (100 / (1 + rs))
        
        # === MACD ===
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        feat['macd'] = ema12 - ema26
        feat['macd_signal'] = feat['macd'].ewm(span=9, adjust=False).mean()
        feat['macd_hist'] = feat['macd'] - feat['macd_signal']
        
        # === ATR ===
        tr = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1)
        feat['atr'] = tr.rolling(14).mean()
        feat['atr_pct'] = feat['atr'] / close * 100  # ATR как % от цены
        
        # === Bollinger %B ===
        bb_sma = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_sma + 2 * bb_std
        bb_lower = bb_sma - 2 * bb_std
        feat['bb_pct_b'] = (close - bb_lower) / (bb_upper - bb_lower)
        
        # === Изменение цены (%) ===
        feat['price_change_3'] = close.pct_change(3) * 100
        feat['price_change_5'] = close.pct_change(5) * 100
        feat['price_change_10'] = close.pct_change(10) * 100
        feat['price_change_20'] = close.pct_change(20) * 100
        
        # === EMA относительно цены ===
        feat['ema9_diff'] = (close - close.ewm(9).mean()) / close * 100
        feat['ema21_diff'] = (close - close.ewm(21).mean()) / close * 100
        feat['ema50_diff'] = (close - close.ewm(50).mean()) / close * 100
        
        # === Объём ===
        vol_ma = volume.rolling(20).mean()
        feat['volume_ratio'] = volume / vol_ma
        feat['volume_change'] = volume.pct_change(5) * 100
        
        # === Волатильность ===
        feat['std_10'] = close.pct_change().rolling(10).std() * 100
        feat['std_20'] = close.pct_change().rolling(20).std() * 100
        
        # === Паттерны свечей ===
        green_candles = (close > df['open']).astype(int)
        feat['green_ratio_10'] = green_candles.rolling(10).mean()
        
        # === High/Low ratio ===
        feat['hl_ratio'] = (high - low) / close * 100
        
        # === Время (если есть timestamps) ===
        if 'ts' in df.columns:
            ts = pd.to_datetime(df['ts'])
            feat['hour'] = ts.dt.hour / 23.0  # Нормализация 0-1
            feat['day_of_week'] = ts.dt.dayofweek / 6.0
        else:
            feat['hour'] = 0.5
            feat['day_of_week'] = 0.5
        
        # === Momentum ===
        feat['momentum_5'] = close / close.shift(5) - 1
        feat['momentum_10'] = close / close.shift(10) - 1
        
        self.feature_names = feat.columns.tolist()
        
        return feat
    
    def _build_target(self, df):
        """
        Целевая переменная — изменение цены через forecast_horizon свечей (%).
        """
        close = df['close']
        future_price = close.shift(-self.forecast_horizon)
        target = (future_price - close) / close * 100  # % изменение
        return target
    
    def train(self, df, symbol=None):
        """Обучает XGBoost модель на исторических данных"""
        if not _check_xgboost():
            logger.error("❌ XGBoost/sklearn недоступны")
            return False
        
        try:
            features = self._build_features(df)
            target = self._build_target(df)
            
            if features is None:
                return False
            
            # Убираем NaN строки
            valid_mask = features.notna().all(axis=1) & target.notna()
            X = features[valid_mask].values
            y = target[valid_mask].values
            
            if len(X) < 50:
                logger.warning(f"⚠️ Мало данных для XGBoost: {len(X)}")
                return False
            
            # Разделяем на train/val (80/20)
            split = int(len(X) * 0.8)
            X_train, X_val = X[:split], X[split:]
            y_train, y_val = y[:split], y[split:]
            
            # Создаём модель
            try:
                from xgboost import XGBRegressor
                self.model = XGBRegressor(
                    n_estimators=200,
                    max_depth=6,
                    learning_rate=0.05,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    reg_alpha=0.1,
                    reg_lambda=1.0,
                    random_state=42,
                    verbosity=0
                )
            except ImportError:
                from sklearn.ensemble import GradientBoostingRegressor
                self.model = GradientBoostingRegressor(
                    n_estimators=200,
                    max_depth=6,
                    learning_rate=0.05,
                    subsample=0.8,
                    random_state=42
                )
            
            self.model.fit(X_train, y_train)
            
            # Оценка
            train_pred = self.model.predict(X_train)
            val_pred = self.model.predict(X_val)
            
            train_mae = np.mean(np.abs(train_pred - y_train))
            val_mae = np.mean(np.abs(val_pred - y_val))
            
            # Точность направления
            direction_acc = np.mean(np.sign(val_pred) == np.sign(y_val)) * 100
            
            self.is_trained = True
            self.trained_symbol = symbol
            
            # Сохраняем
            self._save_model(symbol)
            
            logger.info(
                f"✅ XGBoost обучен ({len(X_train)} train, {len(X_val)} val):\n"
                f"   Train MAE: {train_mae:.4f}%\n"
                f"   Val MAE: {val_mae:.4f}%\n"
                f"   Точность направления: {direction_acc:.1f}%\n"
                f"   Фичей: {len(self.feature_names)}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка обучения XGBoost: {e}")
            return False
    
    def predict(self, df):
        """
        Предсказывает цену через forecast_horizon свечей.
        Возвращает: (predicted_price, lower_bound, upper_bound)
        """
        if not self.is_trained or self.model is None:
            return None, None, None
        
        try:
            features = self._build_features(df)
            if features is None:
                return None, None, None
            
            # Берём последнюю строку (текущий момент)
            last_features = features.iloc[-1:].values
            
            # Проверяем на NaN
            if np.any(np.isnan(last_features)):
                logger.warning("⚠️ XGBoost: NaN в фичах")
                return None, None, None
            
            # Предсказание — % изменение цены
            predicted_change_pct = self.model.predict(last_features)[0]
            
            current_price = df['close'].iloc[-1]
            predicted_price = current_price * (1 + predicted_change_pct / 100)
            
            # Доверительный интервал на основе ATR
            atr = features['atr_pct'].iloc[-1] if 'atr_pct' in features.columns else 1.0
            lower = predicted_price * (1 - atr / 100)
            upper = predicted_price * (1 + atr / 100)
            
            logger.info(
                f"🌳 XGBoost прогноз: {predicted_change_pct:+.3f}% → "
                f"${predicted_price:.8f} (${lower:.8f}–${upper:.8f})"
            )
            
            return predicted_price, lower, upper
            
        except Exception as e:
            logger.error(f"❌ Ошибка XGBoost predict: {e}")
            return None, None, None
    
    def predict_direction(self, df):
        """Предсказывает направление: 1 (вверх), -1 (вниз), 0 (нейтрально)"""
        predicted, _, _ = self.predict(df)
        if predicted is None:
            return 0
        
        current_price = df['close'].iloc[-1]
        change_pct = ((predicted - current_price) / current_price) * 100
        
        if change_pct > 0.5:
            return 1
        elif change_pct < -0.5:
            return -1
        return 0
    
    def get_feature_importance(self):
        """Возвращает важность фичей"""
        if not self.is_trained or self.model is None:
            return {}
        
        try:
            if hasattr(self.model, 'feature_importances_'):
                importances = self.model.feature_importances_
                return dict(sorted(
                    zip(self.feature_names, importances),
                    key=lambda x: x[1], reverse=True
                ))
        except:
            pass
        return {}
    
    def _save_model(self, symbol=None):
        """Сохраняет модель"""
        try:
            clean = (symbol or 'default').replace('/', '_').replace(':', '_')
            path = f'{self.model_dir}/{clean}_xgboost.pkl'
            with open(path, 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'feature_names': self.feature_names,
                    'trained_symbol': self.trained_symbol,
                    'timestamp': datetime.now().isoformat()
                }, f)
            logger.info(f"✅ XGBoost сохранён: {path}")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения XGBoost: {e}")
    
    def _load_model(self, symbol=None):
        """Загружает модель"""
        try:
            clean = (symbol or 'default').replace('/', '_').replace(':', '_')
            path = f'{self.model_dir}/{clean}_xgboost.pkl'
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    data = pickle.load(f)
                self.model = data['model']
                self.feature_names = data['feature_names']
                self.trained_symbol = data.get('trained_symbol')
                self.is_trained = True
                logger.info(f"✅ XGBoost загружен: {path}")
                return True
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить XGBoost: {e}")
        return False
    
    def switch_symbol(self, new_symbol):
        """Переключает на новую монету"""
        if new_symbol == self.trained_symbol and self.is_trained:
            return True
        
        logger.info(f"🔄 XGBoost: переключение на {new_symbol}")
        
        # Пробуем загрузить
        if self._load_model(new_symbol):
            return True
        
        # Обучаем новую
        try:
            from exchange import exchange
            candles = exchange.fetch_ohlcv(new_symbol, '1h', limit=500)
            if candles and len(candles) >= 100:
                df = pd.DataFrame(candles, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
                df['ts'] = pd.to_datetime(df['ts'], unit='ms')
                return self.train(df, symbol=new_symbol)
        except Exception as e:
            logger.error(f"❌ Ошибка обучения XGBoost для {new_symbol}: {e}")
        
        return False


# Глобальный экземпляр
xgb_predictor = XGBoostPredictor(forecast_horizon=12)

def init_xgboost():
    """Инициализация XGBoost модели"""
    if not _check_xgboost():
        return False
    
    try:
        from config import SYMBOL
        
        if xgb_predictor._load_model(SYMBOL):
            return True
        
        # Обучаем
        df = fetch_ohlcv_df()
        if df is not None and len(df) >= 100:
            return xgb_predictor.train(df, symbol=SYMBOL)
        
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации XGBoost: {e}")
        return False

def get_xgb_prediction():
    """Получить предсказание XGBoost"""
    if not xgb_predictor.is_trained:
        return None, None, None
    
    try:
        from exchange import fetch_ohlcv_df
        df = fetch_ohlcv_df()
        return xgb_predictor.predict(df)
    except Exception as e:
        logger.error(f"❌ Ошибка XGBoost предсказания: {e}")
        return None, None, None

def get_xgb_direction():
    """Получить направление от XGBoost"""
    if not xgb_predictor.is_trained:
        return 0
    
    try:
        from exchange import fetch_ohlcv_df
        df = fetch_ohlcv_df()
        return xgb_predictor.predict_direction(df)
    except Exception as e:
        return 0
