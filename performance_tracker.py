"""
Отслеживание производительности и адаптация
Система изучает какие параметры работают лучше
"""

import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from trade_database import trade_db
import pandas as pd

logger = logging.getLogger(__name__)

class PerformanceTracker:
    """Отслеживает производительность и рекомендует улучшения"""
    
    def __init__(self):
        self.performance_history = {}
        self.history_file = "performance_history.json"
        self.load_history()
    
    def load_history(self):
        """Загружает историю производительности"""
        try:
            if Path(self.history_file).exists():
                with open(self.history_file, 'r') as f:
                    self.performance_history = json.load(f)
                logger.info(f"✅ История производительности загружена")
            else:
                self.performance_history = {}
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки истории: {e}")
            self.performance_history = {}
    
    def save_history(self):
        """Сохраняет историю производительности"""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.performance_history, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения истории: {e}")
    
    def analyze_coin_performance(self, symbol, days=7):
        """Анализирует производительность по монете"""
        try:
            stats = trade_db.get_statistics(symbol=symbol, days=days)
            
            if not stats or stats['total_trades'] == 0:
                return None
            
            performance = {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'total_trades': stats['total_trades'],
                'win_rate': stats['win_rate'],
                'total_pnl': stats['total_pnl'],
                'profit_factor': stats['profit_factor'],
                'avg_win': stats['avg_win'],
                'avg_loss': stats['avg_loss'],
                'sharpe_ratio': (stats['avg_win'] / stats['avg_loss']) if stats['avg_loss'] > 0 else 0
            }
            
            return performance
        
        except Exception as e:
            logger.error(f"❌ Ошибка анализа: {e}")
            return None
    
    def get_coins_ranking(self):
        """Получает рейтинг монет по производительности"""
        try:
            # Получаем все уникальные монеты из БД
            conn = __import__('sqlite3').connect('trades.db')
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT symbol FROM trades WHERE status='CLOSED'")
            symbols = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            rankings = []
            for symbol in symbols:
                perf = self.analyze_coin_performance(symbol, days=7)
                if perf:
                    rankings.append(perf)
            
            # Сортируем по win_rate
            rankings.sort(key=lambda x: x['win_rate'], reverse=True)
            
            return rankings
        
        except Exception as e:
            logger.error(f"❌ Ошибка получения рейтинга: {e}")
            return []
    
    def get_recommendation(self):
        """Получает рекомендацию по улучшению"""
        try:
            rankings = self.get_coins_ranking()
            
            if not rankings:
                return "📊 Недостаточно данных для рекомендации"
            
            # Лучшая монета
            best = rankings[0]
            
            report = f"""
╔════════════════════════════════════════════════════════════╗
║           📊 РЕКОМЕНДАЦИИ ПО УЛУЧШЕНИЮ                    ║
╠════════════════════════════════════════════════════════════╣
║ <b>Лучшая монета за 7 дней:</b>
║   {best['symbol']} (Win Rate: {best['win_rate']:.1f}%)
║
║ <b>Статистика:</b>
║   Сделок: {best['total_trades']}
║   P&L: ${best['total_pnl']:+.2f}
║   Коэффициент прибыли: {best['profit_factor']:.2f}x
║
║ <b>Рекомендация:</b>"""
            
            if best['win_rate'] > 60:
                report += "\n║   ✅ Отличная производительность!"
                report += f"\n║   → Увеличьте BASE_AMOUNT на 20%"
            elif best['win_rate'] > 45:
                report += "\n║   ✅ Хорошая производительность"
                report += "\n║   → Оставьте текущие параметры"
            elif best['win_rate'] > 30:
                report += "\n║   ⚠️ Средняя производительность"
                report += "\n║   → Уменьшите BASE_AMOUNT на 20%"
            else:
                report += "\n║   ❌ Низкая производительность"
                report += "\n║   → Смените монету немедленно"
            
            report += "\n╚════════════════════════════════════════════════════════════╝"
            
            return report
        
        except Exception as e:
            logger.error(f"❌ Ошибка получения рекомендации: {e}")
            return None


performance_tracker = PerformanceTracker()
