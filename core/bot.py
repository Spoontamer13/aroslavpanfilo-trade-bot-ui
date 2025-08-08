# core/bot.py
import logging
from utils.logger import logger
from utils.binance_api import BinanceClient

from core.strategies.simple import SimpleStrategy
from core.strategies.rsi import RSIStrategy
from core.strategies.mrc import MRCStrategy
from core.strategies.zone import ZoneStrategy
from core.strategies.combo import ComboStrategy

logger.info("=== core.bot imported ===")

class TradingBot:
    def __init__(self, config_dict: dict | None = None):
        logger.info("[Bot] init enter")
        self.settings = config_dict or {}
        self.mode = (self.settings.get("mode") or "SIMPLE").upper()
        symbol = (self.settings.get("symbol") or "BTCUSDT").upper()

        logger.info("[Bot] mode=%s symbol=%s", self.mode, symbol)

        self.client = BinanceClient(
            api_key   = self.settings.get("api_key", ""),
            api_secret= self.settings.get("api_secret", ""),
            symbol    = symbol,
            testnet   = True,   # как и обсуждали
        )

        strat_map = {
            "SIMPLE": SimpleStrategy,
            "RSI":    RSIStrategy,
            "MRC":    MRCStrategy,
            "ZONE":   ZoneStrategy,
            "COMBO":  ComboStrategy,
        }
        cls = strat_map.get(self.mode)
        if cls is None:
            raise ValueError(f"Unknown mode: {self.mode}")
        self.strategy = cls(self.client, self.settings)
        logger.info("[Bot] strategy=%s ready", cls.__name__)
