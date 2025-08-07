from .base import BaseStrategy
from core.indicators import calculate_rsi

class RSIStrategy(BaseStrategy):
    def __init__(self, client, settings):
        super().__init__(client, settings)
        r = settings.get('rsi', {})
        self.period = r.get('period', 14)
        self.upper = r.get('upper', 70)
        self.lower = r.get('lower', 30)
        self.threshold = r.get('threshold', 30)
        self.close_prices = []
        self.state = None  # 'BUY' or 'SELL'

    def _signal(self, price, candle):
        
        self.close_prices.append(price)
        if len(self.close_prices) < self.period + 1:
            return None

       
        rsi = calculate_rsi(self.close_prices[-(self.period+1):], self.period)

        sig = None

        
        if self.state is None:
            if rsi > self.upper:
                self.state = 'SELL'
            elif rsi < self.lower:
                self.state = 'BUY'
            return None

       
        if self.state == 'BUY' and rsi >= self.threshold:
            sig = 'BUY'
        elif self.state == 'SELL' and rsi <= (100 - self.threshold):
            sig = 'SELL'

       
        dir_setting = self.settings.get('trade_direction', 'BOTH').upper()
        if sig == 'BUY' and dir_setting not in ('LONG', 'BOTH'):
            return None
        if sig == 'SELL' and dir_setting not in ('SHORT', 'BOTH'):
            return None

        return sig