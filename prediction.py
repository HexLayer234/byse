from prophet import Prophet
import pandas as pd
import logging
from exchange import fetch_ohlcv_df

def fetch_historical_data():
    """Получить исторические данные для Prophet"""
    try:
        df = fetch_ohlcv_df()
        if df is None:
            return None
        
        df_prophet = pd.DataFrame({
            'ds': df['ts'],
            'y': df['close']
        })
        return df_prophet
    except Exception as e:
        logging.error(f"❌ Ошибка получения данных для прогноза: {e}")
        return None

def predict_price(hours_ahead=4):
    """Прогноз цены на N часов вперёд используя Prophet"""
    try:
        df = fetch_historical_data()
        if df is None or len(df) < 50:
            logging.warning(f"⚠️ Недостаточно данных для прогноза (need 50, got {len(df) if df is not None else 0})")
            return None, None, None

        model = Prophet(
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False,
            changepoint_prior_scale=0.05,
            interval_width=0.95
        )
        
        with open('/dev/null', 'w') as f:
            import sys
            sys.stderr = f
            model.fit(df)
            sys.stderr = sys.__stderr__

        # Количество периодов (5м свечи)
        periods = hours_ahead * 12
        future = model.make_future_dataframe(periods=periods, freq='5min')
        forecast = model.predict(future)

        future_price = forecast['yhat'].iloc[-1]
        lower = forecast['yhat_lower'].iloc[-1]
        upper = forecast['yhat_upper'].iloc[-1]

        logging.info(f"📊 Прогноз на {hours_ahead}ч: {future_price:.8f} (диапазон {lower:.8f}–{upper:.8f})")
        return future_price, lower, upper
        
    except Exception as e:
        logging.error(f"❌ Ошибка прогноза: {e}")
        return None, None, None
