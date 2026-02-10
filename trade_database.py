"""
Trade Database & History
Сохранение и анализ истории всех сделок
SQLite база данных
"""

import sqlite3
import logging
from datetime import datetime
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)

class TradeDatabase:
    """SQLite база данных для торговой истории"""
    
    def __init__(self, db_path='trades.db'):
        self.db_path = Path(db_path)
        self.init_database()
    
    def init_database(self):
        """Инициализирует базу данных и создаёт таблицы"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Таблица сделок
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,  -- BUY, SELL
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    amount REAL NOT NULL,
                    pnl REAL,
                    pnl_percent REAL,
                    entry_time DATETIME NOT NULL,
                    exit_time DATETIME,
                    duration_seconds INTEGER,
                    reason TEXT,  -- SIGNAL, STOP_LOSS, TAKE_PROFIT, TRAILING_STOP
                    risk_amount REAL,
                    position_size REAL,
                    status TEXT DEFAULT 'OPEN',  -- OPEN, CLOSED
                    notes TEXT
                )
            ''')
            
            # Таблица баланса
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS balance_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    balance REAL NOT NULL,
                    free REAL NOT NULL,
                    used REAL NOT NULL
                )
            ''')
            
            # Таблица сигналов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    symbol TEXT NOT NULL,
                    signal_type TEXT NOT NULL,  -- BUY, SELL, NEUTRAL
                    score REAL NOT NULL,
                    rsi REAL,
                    macd REAL,
                    sentiment TEXT,
                    lstm_direction INTEGER,
                    notes TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Database initialized: {self.db_path}")
        
        except Exception as e:
            logger.error(f"❌ Database init error: {e}")
    
    def log_trade(self, symbol, side, entry_price, amount, entry_time, 
                  exit_price=None, exit_time=None, pnl=None, pnl_percent=None,
                  reason=None, risk_amount=None, position_size=None, notes=None):
        """Логирует сделку"""
        try:
            duration = None
            if exit_time and entry_time:
                duration = int((exit_time - entry_time).total_seconds())
            
            status = 'CLOSED' if exit_price is not None else 'OPEN'
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO trades (
                        timestamp, symbol, side, entry_price, exit_price, amount,
                        pnl, pnl_percent, entry_time, exit_time, duration_seconds,
                        reason, risk_amount, position_size, status, notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    datetime.now(), symbol, side, entry_price, exit_price, amount,
                    pnl, pnl_percent, entry_time, exit_time, duration,
                    reason, risk_amount, position_size, status, notes
                ))
                conn.commit()
            
            logger.info(f"📝 Trade logged: {side} {amount:.4f} {symbol} @ {entry_price:.8f}")
        
        except Exception as e:
            logger.error(f"❌ Trade logging error: {e}")
    
    def update_trade_exit(self, trade_id, exit_price, exit_time, pnl, pnl_percent, reason=None):
        """Обновляет выход из сделки"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE trades
                    SET exit_price = ?, exit_time = ?, pnl = ?, pnl_percent = ?,
                        status = 'CLOSED', reason = ?
                    WHERE id = ?
                ''', (exit_price, exit_time, pnl, pnl_percent, reason, trade_id))
                conn.commit()
            
            logger.info(f"✏️ Trade {trade_id} updated: exit @ {exit_price:.8f}")
        
        except Exception as e:
            logger.error(f"❌ Trade update error: {e}")
    
    def log_balance(self, balance, free, used):
        """Логирует баланс"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO balance_history (timestamp, balance, free, used)
                    VALUES (?, ?, ?, ?)
                ''', (datetime.now(), balance, free, used))
                conn.commit()
        
        except Exception as e:
            logger.error(f"❌ Balance logging error: {e}")
    
    def log_signal(self, symbol, signal_type, score, rsi=None, macd=None, 
                   sentiment=None, lstm_direction=None, notes=None):
        """Логирует торговый сигнал"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO signals (
                        timestamp, symbol, signal_type, score,
                        rsi, macd, sentiment, lstm_direction, notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    datetime.now(), symbol, signal_type, score,
                    rsi, macd, sentiment, lstm_direction, notes
                ))
                conn.commit()
        
        except Exception as e:
            logger.error(f"❌ Signal logging error: {e}")
    
    def get_trades_df(self, symbol=None, days=None):
        """Получает историю сделок в виде DataFrame"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            query = 'SELECT * FROM trades WHERE status = "CLOSED"'
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            if days:
                query += " AND exit_time >= datetime('now', ? || ' days')"
                params.append(f"-{int(days)}")
            
            query += ' ORDER BY exit_time DESC'
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            return df
        
        except Exception as e:
            logger.error(f"❌ Error getting trades: {e}")
            return None
    
    def get_statistics(self, symbol=None, days=None):
        """Рассчитывает статистику сделок"""
        df = self.get_trades_df(symbol, days)
        
        if df is None or len(df) == 0:
            logger.warning("⚠️ Нет сделок для анализа")
            return None
        
        winning_trades = df[df['pnl'] > 0]
        losing_trades = df[df['pnl'] < 0]
        
        total_trades = len(df)
        winning = len(winning_trades)
        losing = len(losing_trades)
        
        stats = {
            'total_trades': total_trades,
            'winning_trades': winning,
            'losing_trades': losing,
            'win_rate': (winning / total_trades * 100) if total_trades > 0 else 0,
            'total_pnl': df['pnl'].sum(),
            'avg_win': winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0,
            'avg_loss': losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0,
            'largest_win': winning_trades['pnl'].max() if len(winning_trades) > 0 else 0,
            'largest_loss': losing_trades['pnl'].min() if len(losing_trades) > 0 else 0,
            'avg_duration_minutes': df['duration_seconds'].mean() / 60 if 'duration_seconds' in df else 0,
            'profit_factor': abs(winning_trades['pnl'].sum() / losing_trades['pnl'].sum())
                            if len(losing_trades) > 0 and losing_trades['pnl'].sum() != 0 else 0
        }
        
        return stats
    
    def print_statistics(self, symbol=None, days=None):
        """Красивый вывод статистики"""
        stats = self.get_statistics(symbol, days)
        
        if stats is None:
            return
        
        period = f"({days} дней)" if days else "(all time)"
        symbol_str = f"{symbol} " if symbol else ""
        
        report = f"""
╔════════════════════════════════════════════════════════════╗
║        📊 TRADE STATISTICS {symbol_str}{period}             ║
╠═════════════════════════��══════════════════════════════════╣
║ Total Trades: {stats['total_trades']}
║ Winning: {stats['winning_trades']} ({stats['win_rate']:.1f}%)
║ Losing: {stats['losing_trades']}
║ Win/Loss Ratio: {stats['profit_factor']:.2f}x
╠════════════════════════════════════════════════════════════╣
║ Total P&L: ${stats['total_pnl']:+.2f}
║ Avg Win: ${stats['avg_win']:.2f}
║ Avg Loss: ${stats['avg_loss']:.2f}
║ Largest Win: ${stats['largest_win']:.2f}
║ Largest Loss: ${stats['largest_loss']:.2f}
╠════════════════════════════════════════════════════════════╣
║ Avg Duration: {stats['avg_duration_minutes']:.0f} minutes
╚════════════════════════════════════════════════════════════╝
"""
        
        logger.info(report)
        return report


# Глобальный экземпляр
trade_db = TradeDatabase('trades.db')
