# core/strategies/mrc.py
import logging
from .base import BaseStrategy
from core.indicators import calculate_mrc_levels

logger = logging.getLogger(__name__)

class MRCStrategy(BaseStrategy):
    def __init__(self, client, settings):
        super().__init__(client, settings)
        m = settings.get('mrc', {})
        self.mode = m.get('mode', 'normal')  
        self.entry_level = str(m.get('entry_level', '2'))
        self.exit_level  = str(m.get('exit_level', '2.1'))
        self.entry_type  = m.get('entry_candle_type', 'cross')
        self.exit_type   = m.get('exit_candle_type', 'cross')
        self.close_prices = []
        self.levels = {}

    def _signal(self, price, candle):
        op = candle['open']
        self.close_prices.append(price)
        if len(self.close_prices) < 30:
            return None

        # пересчитываем уровни каждые 30 свечей
        if not self.levels:
            self.levels = calculate_mrc_levels(self.close_prices[-30:])

        ent_p = self.levels.get(self.entry_level)
        if ent_p is None:
            return None

        # определяем сторону по цвету уровня
        def side_for(level: str):
            return 'BUY' if not level.endswith('.1') else 'SELL'

        desired_side = side_for(self.entry_level)
        invert = (self.mode.lower() == 'inverted')

        # проверка условия на вход
        if self.entry_type == 'cross':
            cond = (op < ent_p < price) or (op > ent_p > price)
        else:  # reverse
            cond = (op < ent_p and price < ent_p) or (op > ent_p and price > ent_p)

        if not cond:
            return None

        # применяем инверсию, если надо
        sig = desired_side
        if invert:
            sig = 'SELL' if sig == 'BUY' else 'BUY'

        # фильтрация по trade_direction
        dir_setting = self.settings.get('trade_direction', 'BOTH').upper()
        if sig == 'BUY' and dir_setting not in ('LONG', 'BOTH'):
            return None
        if sig == 'SELL' and dir_setting not in ('SHORT', 'BOTH'):
            return None

        return sig