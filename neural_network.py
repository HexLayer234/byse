import numpy as np
import pandas as pd
import logging
import warnings
import pickle
import os
warnings.filterwarnings('ignore')

from exchange import fetch_ohlcv_df
from config import SYMBOL

# TensorFlow/Keras
try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential, load_model
    from tensorflow.keras.layers import LSTM, Dense, Dropout, Bidirectional
    from tensorflow.keras.optimizers import Adam
    from tensorflow.keras.callbacks import EarlyStopping
    from sklearn.preprocessing import MinMaxScaler
    NEURAL_NETWORK_AVAILABLE = True
except ImportError as e:
    logging.warning(f"⚠️ TensorFlow не установлена: {e}")
    NEURAL_NETWORK_AVAILABLE = False

class LSTMTradingModel:
    """LSTM модель для предсказания цены и торговых сигналов"""
    
    def __init__(self, lookback=60, forecast_horizon=12):
        self.lookback = lookback
        self.forecast_horizon = forecast_horizon
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.model = None
        self.is_trained = False
        self.trained_symbol = None  # ✨ НОВОЕ: запоминаем на какой монете обучена
        
        # Пути для сохранения
        self.model_dir = 'models'
        os.makedirs(self.model_dir, exist_ok=True)
        
        self._update_paths(SYMBOL)
    
    def _update_paths(self, symbol):
        """Обновляет пути к файлам модели для текущего символа"""
        clean_symbol = symbol.replace("/", "_").replace(":", "_")
        self.model_path = f'{self.model_dir}/{clean_symbol}_lstm_model.keras'
        self.scaler_path = f'{self.model_dir}/{clean_symbol}_scaler.pkl'
        self.trained_symbol = symbol
        
    def prepare_data(self, df, validation_split=0.2):
        """Подготовить данные для LSTM (без утечки данных)"""
        try:
            if df is None or len(df) < self.lookback + self.forecast_horizon:
                logging.warning(f"⚠️ Недостаточно данных для LSTM: {len(df) if df is not None else 0}")
                return None, None, None
            
            features = df[['close', 'volume', 'high', 'low']].values
            
            # Fit scaler ТОЛЬКО на тренировочных данных (без утечки!)
            train_size = int(len(features) * (1 - validation_split))
            self.scaler.fit(features[:train_size])
            scaled_features = self.scaler.transform(features)
            
            X, y = [], []
            
            for i in range(len(scaled_features) - self.lookback - self.forecast_horizon + 1):
                X.append(scaled_features[i:i + self.lookback])
                y.append(scaled_features[i + self.lookback + self.forecast_horizon - 1, 0])
            
            X = np.array(X)
            y = np.array(y)
            
            if len(X) < 10:
                logging.warning(f"⚠️ Слишком мало обучающих данных: {len(X)}")
                return None, None, None
            
            logging.info(f"✅ Данные подготовлены: X.shape={X.shape}, y.shape={y.shape}")
            return X, y, scaled_features
            
        except Exception as e:
            logging.error(f"❌ Ошибка подготовки данных: {e}")
            return None, None, None
    
    def create_model(self, input_shape):
        """Создать LSTM архитектуру"""
        model = Sequential([
            Bidirectional(LSTM(128, return_sequences=True, activation='relu'), 
                         input_shape=input_shape),
            Dropout(0.2),
            
            LSTM(64, return_sequences=True, activation='relu'),
            Dropout(0.2),
            
            LSTM(32, return_sequences=False, activation='relu'),
            Dropout(0.2),
            
            Dense(16, activation='relu'),
            Dense(8, activation='relu'),
            Dense(1, activation='sigmoid')
        ])
        
        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='mse',
            metrics=['mae']
        )
        
        logging.info("✅ LSTM модель создана")
        return model
    
    def train(self, df, epochs=50, batch_size=32, validation_split=0.2):
        """Обучить LSTM модель"""
        try:
            if not NEURAL_NETWORK_AVAILABLE:
                logging.error("❌ TensorFlow не доступна")
                return False
            
            X, y, _ = self.prepare_data(df)
            if X is None:
                return False
            
            split_idx = int(len(X) * (1 - validation_split))
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]
            
            self.model = self.create_model((X.shape[1], X.shape[2]))
            
            early_stop = EarlyStopping(
                monitor='val_loss',
                patience=5,
                restore_best_weights=True
            )
            
            logging.info(f"🧠 Обучение LSTM ({epochs} эпох)...")
            history = self.model.fit(
                X_train, y_train,
                validation_data=(X_val, y_val),
                epochs=epochs,
                batch_size=batch_size,
                callbacks=[early_stop],
                verbose=0
            )
            
            train_loss, train_mae = self.model.evaluate(X_train, y_train, verbose=0)
            val_loss, val_mae = self.model.evaluate(X_val, y_val, verbose=0)
            
            logging.info(
                f"✅ LSTM обучена:\n"
                f"   Train Loss: {train_loss:.6f}, MAE: {train_mae:.6f}\n"
                f"   Val Loss: {val_loss:.6f}, MAE: {val_mae:.6f}"
            )
            
            self.is_trained = True
            self.save_model()
            self.save_scaler()
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка обучения LSTM: {e}")
            return False
    
    def predict_price(self, df):
        """Предсказать цену на forecast_horizon свечей вперёд"""
        try:
            if not self.is_trained or self.model is None:
                logging.warning("⚠️ LSTM модель не обучена")
                return None, None, None
            
            if df is None or len(df) < self.lookback:
                return None, None, None
            
            # Используем загруженный scaler
            features = df[['close', 'volume', 'high', 'low']].values
            scaled_features = self.scaler.transform(features)
            
            last_sequence = scaled_features[-self.lookback:]
            last_sequence = last_sequence.reshape(1, self.lookback, 4)
            
            normalized_pred = self.model.predict(last_sequence, verbose=0)[0, 0]
            
            # Денормализуем правильно
            dummy = np.zeros((1, 4))
            dummy[0, 0] = normalized_pred
            predicted_price = self.scaler.inverse_transform(dummy)[0, 0]
            
            current_price = df['close'].iloc[-1]
            
            lower_bound = predicted_price * 0.98
            upper_bound = predicted_price * 1.02
            
            logging.info(
                f"🧠 LSTM прогноз на {self.forecast_horizon * 5}мин: "
                f"{predicted_price:.8f} (диапазон {lower_bound:.8f}–{upper_bound:.8f})"
            )
            
            return predicted_price, lower_bound, upper_bound
            
        except Exception as e:
            logging.error(f"❌ Ошибка предсказания LSTM: {e}")
            return None, None, None
    
    def predict_direction(self, df):
        """Предсказать направление цены (-1, 0, 1)"""
        try:
            predicted, _, _ = self.predict_price(df)
            if predicted is None:
                return 0
            
            current_price = df['close'].iloc[-1]
            
            if predicted > current_price * 1.01:
                return 1
            elif predicted < current_price * 0.99:
                return -1
            else:
                return 0
                
        except Exception as e:
            logging.error(f"❌ Ошибка предсказания направления: {e}")
            return 0
    
    def save_model(self):
        """Сохранить модель на диск"""
        try:
            self.model.save(self.model_path)
            logging.info(f"✅ Модель сохранена: {self.model_path}")
        except Exception as e:
            logging.error(f"❌ Ошибка сохранения модели: {e}")
    
    def save_scaler(self):
        """Сохранить scaler отдельно"""
        try:
            with open(self.scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
            logging.info(f"✅ Scaler сохранён: {self.scaler_path}")
        except Exception as e:
            logging.error(f"❌ Ошибка сохранения scaler: {e}")
    
    def load_model(self):
        """Загрузить модель с диска"""
        try:
            self.model = load_model(self.model_path)
            self.load_scaler()
            self.is_trained = True
            logging.info(f"✅ Модель загружена: {self.model_path}")
            return True
        except Exception as e:
            logging.warning(f"⚠️ Не удалось загрузить модель: {e}")
            return False
    
    def load_scaler(self):
        """Загрузить scaler"""
        try:
            with open(self.scaler_path, 'rb') as f:
                self.scaler = pickle.load(f)
            logging.info(f"✅ Scaler загружен: {self.scaler_path}")
        except Exception as e:
            logging.warning(f"⚠️ Не удалось загрузить scaler: {e}")
    
    def switch_symbol(self, new_symbol):
        """
        ✨ НОВОЕ: Переключает LSTM на новую монету
        Загружает существующую модель или обучает новую
        """
        if new_symbol == self.trained_symbol and self.is_trained:
            logging.info(f"ℹ️ LSTM уже обучена на {new_symbol}, переобучение не требуется")
            return True
        
        logging.info(f"🔄 Переключение LSTM: {self.trained_symbol} → {new_symbol}")
        
        # Обновляем пути для новой монеты
        self._update_paths(new_symbol)
        
        # Сбрасываем состояние
        self.model = None
        self.is_trained = False
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        
        # Пробуем загрузить сохранённую модель для этой монеты
        if self.load_model():
            logging.info(f"✅ Загружена сохранённая LSTM модель для {new_symbol}")
            return True
        
        # Нет сохранённой модели — обучаем новую
        logging.info(f"🧠 Обучение новой LSTM модели для {new_symbol}...")
        
        try:
            from exchange import exchange
            candles = exchange.fetch_ohlcv(new_symbol, '1h', limit=500)
            
            if candles and len(candles) >= 100:
                df = pd.DataFrame(candles, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
                df['ts'] = pd.to_datetime(df['ts'], unit='ms')
                return self.train(df, epochs=30)
            else:
                logging.warning(f"⚠️ Недостаточно данных для обучения LSTM на {new_symbol}")
                return False
                
        except Exception as e:
            logging.error(f"❌ Ошибка обучения LSTM для {new_symbol}: {e}")
            return False


# Глобальный экземпляр модели
lstm_model = None

def init_lstm_model():
    """Инициализировать LSTM модель"""
    global lstm_model
    
    if not NEURAL_NETWORK_AVAILABLE:
        logging.warning("❌ TensorFlow не установлена, LSTM отключена")
        return False
    
    try:
        lstm_model = LSTMTradingModel(lookback=60, forecast_horizon=12)
        
        if not lstm_model.load_model():
            logging.info("🧠 Обучение новой LSTM модели...")
            df = fetch_ohlcv_df()
            if df is not None and len(df) >= 100:
                lstm_model.train(df, epochs=30)
            else:
                logging.warning("⚠️ Недостаточно данных для обучения LSTM")
                return False
        
        return lstm_model.is_trained
        
    except Exception as e:
        logging.error(f"❌ Ошибка инициализации LSTM: {e}")
        return False

def switch_lstm_symbol(new_symbol):
    """✨ НОВОЕ: Переключить LSTM на новую монету"""
    global lstm_model
    
    if lstm_model is None:
        if not NEURAL_NETWORK_AVAILABLE:
            logging.warning("❌ TensorFlow не установлена, LSTM отключена")
            return False
        lstm_model = LSTMTradingModel(lookback=60, forecast_horizon=12)
    
    return lstm_model.switch_symbol(new_symbol)

def get_lstm_prediction():
    """Получить предсказание от LSTM"""
    global lstm_model
    
    if lstm_model is None or not lstm_model.is_trained:
        return None, None, None
    
    try:
        df = fetch_ohlcv_df()
        return lstm_model.predict_price(df)
    except Exception as e:
        logging.error(f"❌ Ошибка LSTM предсказания: {e}")
        return None, None, None

def get_lstm_direction():
    """Получить направление от LSTM (-1, 0, 1)"""
    global lstm_model
    
    if lstm_model is None or not lstm_model.is_trained:
        return 0
    
    try:
        df = fetch_ohlcv_df()
        return lstm_model.predict_direction(df)
    except Exception as e:
        logging.error(f"❌ Ошибка LSTM направления: {e}")
        return 0
