"""
Volume Profile Analysis
Анализ распределения объёма по ценовым уровням
Поиск поддержки и сопротивления
"""

import logging
import pandas as pd
import numpy as np
from exchange import fetch_ohlcv_df

logger = logging.getLogger(__name__)

class VolumeProfileAnalyzer:
    """Анализ профиля объёма"""
    
    def __init__(self, price_bins=50):
        """
        Args:
            price_bins: количество ценовых уровней для анализа
        """
        self.price_bins = price_bins
        self.volume_profile = None
        self.poc = None  # Point of Control (максимальный объём)
        self.vah = None  # Value Area High (верхняя граница области стоимости)
        self.val = None  # Value Area Low (нижняя граница области стоимости)
    
    def calculate_volume_profile(self, df=None):
        """
        Рассчитывает профиль объёма
        
        Логика:
        ├─ Делим цену на N уровней (bins)
        ├─ Для каждого уровня суммируем объём
        ├─ Находим уровень с максимальным объёмом (POC)
        └─ Находим диапазон, содержащий 70% объёма (Value Area)
        """
        try:
            if df is None:
                df = fetch_ohlcv_df()
            
            if df is None or len(df) == 0:
                logger.error("❌ No data for volume profile")
                return None
            
            # Используем средние цены свече��
            df['mid_price'] = (df['high'] + df['low']) / 2
            
            min_price = df['low'].min()
            max_price = df['high'].max()
            
            # Создаём ценовые уровни
            price_levels = np.linspace(min_price, max_price, self.price_bins)
            
            # Рассчитываем объём для каждого уровня
            volume_by_price = []
            
            for i in range(len(price_levels) - 1):
                level_low = price_levels[i]
                level_high = price_levels[i + 1]
                
                # Объём на этом уровне = сумма объёмов свечей пересекающих уровень
                mask = (df['low'] <= level_high) & (df['high'] >= level_low)
                volume = df[mask]['volume'].sum()
                
                volume_by_price.append({
                    'price_level': (level_low + level_high) / 2,
                    'volume': volume
                })
            
            self.volume_profile = pd.DataFrame(volume_by_price)
            
            # POC - самый активный уровень
            poc_idx = self.volume_profile['volume'].idxmax()
            self.poc = self.volume_profile.loc[poc_idx, 'price_level']
            
            # Value Area - 70% объёма
            total_volume = self.volume_profile['volume'].sum()
            sorted_profile = self.volume_profile.sort_values('volume', ascending=False)
            
            cumsum = 0
            va_prices = []
            for _, row in sorted_profile.iterrows():
                cumsum += row['volume']
                va_prices.append(row['price_level'])
                if cumsum >= total_volume * 0.7:
                    break
            
            self.val = min(va_prices)
            self.vah = max(va_prices)
            
            return self.volume_profile
        
        except Exception as e:
            logger.error(f"❌ Volume profile calculation error: {e}")
            return None
    
    def get_support_resistance_levels(self):
        """
        Определяет уровни поддержки и сопротивления
        на основе профиля объёма
        """
        if self.volume_profile is None:
            self.calculate_volume_profile()
        
        if self.volume_profile is None:
            return None
        
        # Top 5 уровней с максимальным объёмом
        top_levels = self.volume_profile.nlargest(5, 'volume')
        
        support_resistance = []
        for _, row in top_levels.iterrows():
            level = row['price_level']
            volume = row['volume']
            volume_pct = (volume / self.volume_profile['volume'].max()) * 100
            
            support_resistance.append({
                'price': level,
                'volume': volume,
                'volume_percent': volume_pct,
                'type': 'RESISTANCE' if level > self.poc else 'SUPPORT'
            })
        
        return sorted(support_resistance, key=lambda x: x['price'])
    
    def should_trade_at_price(self, current_price, threshold=0.05):
        """
        Определяет, стоит ли торговать при текущей цене
        
        Логика:
        ├─ Если цена около POC → хороший момент для входа
        ├─ Если цена в VA → нормальная цена
        ├─ Если цена вне VA → возможен разворот
        """
        if self.poc is None or self.val is None or self.vah is None:
            self.calculate_volume_profile()
        
        # Расстояние от POC в процентах
        poc_distance = abs(current_price - self.poc) / self.poc
        
        # Находимся ли в Value Area?
        in_va = self.val <= current_price <= self.vah
        
        # Хорошее место для входа если близко к POC или вне VA
        good_entry = poc_distance < threshold or not in_va
        
        return good_entry, {
            'current_price': current_price,
            'poc': self.poc,
            'distance_from_poc_percent': poc_distance * 100,
            'in_value_area': in_va,
            'val': self.val,
            'vah': self.vah,
            'good_entry': good_entry
        }
    
    def print_volume_profile(self):
        """Красивый вывод профиля объёма"""
        if self.volume_profile is None:
            self.calculate_volume_profile()
        
        if self.volume_profile is None:
            logger.warning("⚠️ Volume profile not available")
            return
        
        max_volume = self.volume_profile['volume'].max()
        
        report = f"""
╔════════════════════════════════════════════════════════════╗
║            📊 VOLUME PROFILE ANALYSIS                      ║
╠════════════════════════════════════════════════════════════╣
"""
        
        for _, row in self.volume_profile.iterrows():
            price = row['price_level']
            volume = row['volume']
            bar_length = int((volume / max_volume) * 30)
            bar = '█' * bar_length
            
            is_poc = " ← POC" if price == self.poc else ""
            in_va = " (VA)" if self.val <= price <= self.vah else ""
            
            report += f"║ ${price:10.2f} │ {bar:30} {in_va}{is_poc}\n"
        
        report += f"""╠════════════════════════════════════════════════════════════╣
║ POC (Point of Control): ${self.poc:.8f}
║ VAL (Value Area Low): ${self.val:.8f}
║ VAH (Value Area High): ${self.vah:.8f}
╚════════════════════════════════════════════════════════════╝
"""
        
        logger.info(report)
        return report
    
    def get_full_analysis(self):
        """Полный анализ объёма"""
        self.calculate_volume_profile()
        sr_levels = self.get_support_resistance_levels()
        
        report = f"""
╔════════════════════════════════════════════════════════════╗
║        📊 FULL VOLUME PROFILE ANALYSIS                     ║
╠════════════════════════════════════════════════════════════╣
║               SUPPORT & RESISTANCE LEVELS                  ║
├────────────────────────────────────────────────────────────┤
"""
        
        if sr_levels:
            for i, level in enumerate(sr_levels):
                icon = "🔴" if level['type'] == 'RESISTANCE' else "🟢"
                report += (
                    f"║ {icon} Level {i+1}: ${level['price']:.8f} "
                    f"({level['volume_percent']:.1f}%)\n"
                )
        
        report += "╚════════════════════════════════════════════════════════════╝\n"
        
        logger.info(report)
        return report


# Глобальный экземпляр
volume_profile_analyzer = VolumeProfileAnalyzer(price_bins=50)
