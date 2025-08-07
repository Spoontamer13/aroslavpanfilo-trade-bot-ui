from .base import BaseStrategy

class SimpleStrategy(BaseStrategy):
   
    def __init__(self, client, settings):
        super().__init__(client, settings)

    def _signal(self, price, candle):
        sig = None
        
        if not self.active:
            dir_setting = self.settings.get('trade_direction', 'BOTH').upper()
            
            if dir_setting in ('LONG', 'BOTH'):
                sig = 'BUY'
            elif dir_setting in ('SHORT', 'BOTH'):
                sig = 'SELL'

       
        if sig == 'BUY' and dir_setting not in ('LONG', 'BOTH'):
            return None
        if sig == 'SELL' and dir_setting not in ('SHORT', 'BOTH'):
            return None

        return sig