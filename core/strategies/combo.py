from .rsi import RSIStrategy
from .mrc import MRCStrategy
from .zone import ZoneStrategy

class ComboStrategy:
    def __init__(self, client, settings):
        super().__init__(client, settings)
        from .rsi  import RSIStrategy
        from .mrc  import MRCStrategy
        from .zone import ZoneStrategy
        # Вложенные стратегии только для сигналов
        self._rsi  = RSIStrategy(client, settings)
        self._mrc  = MRCStrategy(client, settings)
        self._zone = ZoneStrategy(client, settings)

    def _signal(self, price, candle):
        s1 = self._rsi._signal(price, candle)
        s2 = self._mrc._signal(price, candle)
        s3 = self._zone._signal(price, candle)
        if s1 and s1 == s2 == s3:
            # фильтруем по trade_direction из настроек
            td = self.settings.get('trade_direction', 'BOTH').upper()
            if s1 == 'BUY'  and td not in ('LONG','BOTH'):  return None
            if s1 == 'SELL' and td not in ('SHORT','BOTH'): return None
            return s1
        return None
