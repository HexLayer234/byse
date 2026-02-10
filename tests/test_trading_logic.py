"""
Тесты для торговой логики
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ===== ТЕСТЫ ИНДИКАТОРОВ =====

def _make_df(n=100, base_price=100):
    """Создаёт тестовый DataFrame с OHLCV данными"""
    np.random.seed(42)
    dates = pd.date_range(start='2025-01-01', periods=n, freq='1h')
    close = base_price + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 1)  # Цена не может быть отрицательной
    
    return pd.DataFrame({
        'ts': dates,
        'open': close - np.random.uniform(0, 0.5, n),
        'high': close + np.random.uniform(0, 1, n),
        'low': close - np.random.uniform(0, 1, n),
        'close': close,
        'volume': np.random.uniform(1000, 10000, n)
    })

def test_compute_indicators_returns_dict():
    """compute_indicators должен вернуть словарь с нужными ключами"""
    from trading_logic import compute_indicators
    df = _make_df(100)
    result = compute_indicators(df)
    
    assert result is not None
    assert isinstance(result, dict)
    assert 'rsi' in result
    assert 'macd' in result
    assert 'macd_signal' in result
    assert 'atr' in result
    assert 'bb_upper' in result
    assert 'bb_lower' in result

def test_compute_indicators_rsi_range():
    """RSI должен быть в диапазоне 0-100"""
    from trading_logic import compute_indicators
    df = _make_df(100)
    result = compute_indicators(df)
    
    assert result is not None
    rsi = result['rsi']
    assert 0 <= rsi <= 100, f"RSI вне диапазона: {rsi}"

def test_compute_indicators_insufficient_data():
    """При недостаточных данных должен вернуть None"""
    from trading_logic import compute_indicators
    df = _make_df(10)  # Слишком мало данных
    result = compute_indicators(df)
    assert result is None

def test_compute_indicators_none_df():
    """При None DataFrame должен вернуть None"""
    from trading_logic import compute_indicators
    result = compute_indicators(None)
    assert result is None

# ===== ТЕСТЫ SIGNAL SCORE =====

def test_signal_score_bullish():
    """Бычий сигнал должен быть положительным"""
    from trading_logic import calculate_signal_score
    score = calculate_signal_score(
        rsi=25, macd=1, macd_signal=0, sentiment="Buy",
        price_up=True, is_active=True, volume_ratio=2.0,
        atr=0.5, price_change_pct=2.0, lstm_direction=1
    )
    assert score > 0, f"Бычий сигнал должен быть > 0, получили {score}"

def test_signal_score_bearish():
    """Медвежий сигнал должен быть отрицательным"""
    from trading_logic import calculate_signal_score
    score = calculate_signal_score(
        rsi=80, macd=-1, macd_signal=0, sentiment="Sell",
        price_up=False, is_active=True, volume_ratio=2.0,
        atr=0.5, price_change_pct=-2.0, lstm_direction=-1
    )
    assert score < 0, f"Медвежий сигнал должен быть < 0, получили {score}"

def test_signal_score_neutral():
    """Нейтральный сигнал должен быть около нуля"""
    from trading_logic import calculate_signal_score
    score = calculate_signal_score(
        rsi=50, macd=0, macd_signal=0, sentiment="Neutral",
        price_up=True, is_active=False, volume_ratio=1.0,
        atr=0.5, price_change_pct=0, lstm_direction=0
    )
    assert -30 <= score <= 30, f"Нейтральный сигнал должен быть около 0, получили {score}"

# ===== ТЕСТЫ TWE =====

def test_twe_manager():
    """TWE менеджер должен правильно рассчитывать лимиты"""
    from risk_management import TWEManager
    twe = TWEManager(max_twe_percent=80)
    assert twe.max_twe_percent == 80

# ===== ТЕСТЫ UNSTUCKING =====

def test_unstucking_not_triggered_early():
    """Unstucking не должен срабатывать для свежих позиций"""
    from risk_management import UnstuckingManager
    um = UnstuckingManager(max_stuck_hours=4)
    
    # Позиция открыта только что
    should, info = um.should_unstuck(
        symbol='TEST/USDT',
        entry_time=datetime.now(),
        entry_price=100,
        current_price=95,
        pnl_percent=-5
    )
    assert should == False

def test_unstucking_triggered_after_hours():
    """Unstucking должен сработать для старых убыточных позиций"""
    from risk_management import UnstuckingManager
    um = UnstuckingManager(max_stuck_hours=4)
    
    # Позиция открыта 5 часов назад
    should, info = um.should_unstuck(
        symbol='TEST/USDT',
        entry_time=datetime.now() - timedelta(hours=5),
        entry_price=100,
        current_price=95,
        pnl_percent=-5
    )
    assert should == True
    assert info is not None
    assert 'close_percent' in info

def test_unstucking_not_triggered_profitable():
    """Unstucking не должен срабатывать для прибыльных позиций"""
    from risk_management import UnstuckingManager
    um = UnstuckingManager(max_stuck_hours=4)
    
    should, info = um.should_unstuck(
        symbol='TEST/USDT',
        entry_time=datetime.now() - timedelta(hours=10),
        entry_price=100,
        current_price=110,
        pnl_percent=10
    )
    assert should == False

# ===== ТЕСТЫ DATABASE =====

def test_trade_db_init():
    """БД должна инициализироваться"""
    from trade_database import TradeDatabase
    import tempfile, os
    
    tmp = tempfile.mktemp(suffix='.db')
    try:
        db = TradeDatabase(tmp)
        stats = db.get_statistics()
        assert stats is None  # Нет сделок
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def test_trade_db_log_and_stats():
    """Логирование и статистика должны работать"""
    from trade_database import TradeDatabase
    import tempfile, os
    
    tmp = tempfile.mktemp(suffix='.db')
    try:
        db = TradeDatabase(tmp)
        
        now = datetime.now()
        db.log_trade(
            symbol='TEST/USDT', side='buy', entry_price=100,
            amount=1.0, entry_time=now, exit_price=110,
            exit_time=now, pnl=10, pnl_percent=10
        )
        db.log_trade(
            symbol='TEST/USDT', side='buy', entry_price=100,
            amount=1.0, entry_time=now, exit_price=95,
            exit_time=now, pnl=-5, pnl_percent=-5
        )
        
        stats = db.get_statistics()
        assert stats is not None
        assert stats['total_trades'] == 2
        assert stats['winning_trades'] == 1
        assert stats['losing_trades'] == 1
        assert stats['win_rate'] == 50.0
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

# ===== ТЕСТЫ TRAILING STOP =====

def test_trailing_stop_register():
    """Trailing stop должен регистрировать позицию"""
    from trailing_stop import TrailingStopManager
    ts = TrailingStopManager(trailing_percent=2.0)
    ts.register_position('TEST/USDT', 100.0)
    
    stats = ts.get_stats('TEST/USDT')
    assert stats is not None
    assert stats['entry_price'] == 100.0
    assert stats['trailing_stop'] == 98.0  # 100 * (1 - 2%)

def test_trailing_stop_moves_up():
    """Trailing stop должен двигаться вверх при росте цены"""
    from trailing_stop import TrailingStopManager
    ts = TrailingStopManager(trailing_percent=2.0)
    ts.register_position('TEST/USDT', 100.0)
    
    ts.update_trailing_stop('TEST/USDT', 110.0)  # Цена выросла
    
    stats = ts.get_stats('TEST/USDT')
    assert stats['peak_price'] == 110.0
    assert stats['trailing_stop'] == 107.8  # 110 * (1 - 2%)

def test_trailing_stop_triggers():
    """Trailing stop должен сработать при падении"""
    from trailing_stop import TrailingStopManager
    ts = TrailingStopManager(trailing_percent=2.0)
    ts.register_position('TEST/USDT', 100.0)
    
    ts.update_trailing_stop('TEST/USDT', 110.0)  # Пик
    ts.update_trailing_stop('TEST/USDT', 107.0)  # Падение ниже стопа
    
    stats = ts.get_stats('TEST/USDT')
    assert stats['status'] == 'СРАБОТАЛ'


# ===== ТЕСТЫ XGBOOST =====

def test_xgboost_build_features():
    """XGBoost должен построить фичи из DataFrame"""
    from xgboost_model import XGBoostPredictor
    xgb = XGBoostPredictor(forecast_horizon=12)
    df = _make_df(100)
    features = xgb._build_features(df)
    
    assert features is not None
    assert len(features) == 100
    assert 'rsi' in features.columns
    assert 'macd' in features.columns
    assert 'volume_ratio' in features.columns
    assert 'ema9_diff' in features.columns
    assert len(features.columns) >= 20, f"Ожидалось 20+ фичей, получили {len(features.columns)}"

def test_xgboost_build_features_insufficient():
    """При недостаточных данных должен вернуть None"""
    from xgboost_model import XGBoostPredictor
    xgb = XGBoostPredictor()
    df = _make_df(10)
    features = xgb._build_features(df)
    assert features is None

def test_xgboost_train_and_predict():
    """XGBoost должен обучиться и предсказать"""
    from xgboost_model import XGBoostPredictor, _check_xgboost
    
    if not _check_xgboost():
        pytest.skip("XGBoost/sklearn не установлен")
    
    xgb = XGBoostPredictor(forecast_horizon=5)
    df = _make_df(200, base_price=50)
    
    success = xgb.train(df, symbol='TEST')
    assert success == True
    assert xgb.is_trained == True
    
    predicted, lower, upper = xgb.predict(df)
    assert predicted is not None
    assert lower is not None
    assert upper is not None
    assert lower <= predicted <= upper
    assert predicted > 0

def test_xgboost_feature_importance():
    """XGBoost должен вернуть важность фичей"""
    from xgboost_model import XGBoostPredictor, _check_xgboost
    
    if not _check_xgboost():
        pytest.skip("XGBoost/sklearn не установлен")
    
    xgb = XGBoostPredictor(forecast_horizon=5)
    df = _make_df(200)
    xgb.train(df, symbol='TEST')
    
    importance = xgb.get_feature_importance()
    assert isinstance(importance, dict)
    assert len(importance) > 0
    
    # Топ фича должна иметь значение > 0
    top_feature = list(importance.keys())[0]
    assert importance[top_feature] > 0

def test_xgboost_direction():
    """predict_direction должен вернуть -1, 0 или 1"""
    from xgboost_model import XGBoostPredictor, _check_xgboost
    
    if not _check_xgboost():
        pytest.skip("XGBoost/sklearn не установлен")
    
    xgb = XGBoostPredictor(forecast_horizon=5)
    df = _make_df(200)
    xgb.train(df, symbol='TEST')
    
    direction = xgb.predict_direction(df)
    assert direction in [-1, 0, 1]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
