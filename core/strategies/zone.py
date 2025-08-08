# core/strategies/zone.py
import logging
from .base import BaseStrategy
from core.indicators import calculate_mrc_levels

logger = logging.getLogger(__name__)

class ZoneStrategy(BaseStrategy):
    def __init__(self, client, settings):
        super().__init__(client, settings)
        z = settings.get('zone', {})
        self.mode = z.get('mode', 1)            
        self.level = z.get('level')            
        self.entry_type = z.get('entry_candle_type', 'cross')
        self.close_prices = []
        self.levels = {}

    def _signal(self, price, candle):
        op = candle['open']
        self.close_prices.append(price)
        if len(self.close_prices) < 30:
            return None

        if not self.levels:
            self.levels = calculate_mrc_levels(self.close_prices[-30:])

        
        def lvl_price(lvl):
            return self.levels.get(str(lvl))

        sig = None
        # Режим 1: Outside Line
        if self.mode == 1:
            p = lvl_price(self.level)
            if p is None:
                return None
            if self.entry_type == 'cross':
                cond = (op < p < price) or (op > p > price)
            else: 
                cond = (op < p and price < p) or (op > p and price > p)
            if cond:
                sig = 'BUY' if not str(self.level).endswith('.1') else 'SELL'

        # Режим 2: Symmetric Channel
        elif self.mode == 2:
            
            low, high = self.level
            p_low = lvl_price(low)
            p_high = lvl_price(high)
            if p_low is None or p_high is None:
                return None
            inside = p_low < price < p_high
            if inside:
                mid = (p_low + p_high) / 2
                sig = 'BUY' if price < mid else 'SELL'

        # Режим 3: Half-Channel from Center
        elif self.mode == 3:
            p_c = lvl_price('1')
            p_l = lvl_price(self.level)
            if p_c is None or p_l is None:
                return None
            if self.entry_type == 'cross':
                if p_c < p_l and (op < p_c < price):
                    sig = 'BUY'
                elif p_c > p_l and (op > p_c > price):
                    sig = 'SELL'
            else:
                if p_c < p_l and price < p_c:
                    sig = 'BUY'
                elif p_c > p_l and price > p_c:
                    sig = 'SELL'

        
        if sig is None:
            return None

        
        dir_setting = self.settings.get('trade_direction', 'BOTH').upper()
        if sig == 'BUY' and dir_setting not in ('LONG', 'BOTH'):
            return None
        if sig == 'SELL' and dir_setting not in ('SHORT', 'BOTH'):
            return None

        return sig