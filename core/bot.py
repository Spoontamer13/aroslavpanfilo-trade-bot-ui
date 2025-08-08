# core/bot.py
import logging

from utils.binance_api import BinanceClient
from core.strategies.simple import SimpleStrategy
from core.strategies.rsi import RSIStrategy
from core.strategies.mrc import MRCStrategy
from core.strategies.zone import ZoneStrategy
from core.strategies.combo import ComboStrategy

logger = logging.getLogger()
logger.info("=== core.bot imported ===")


class TradingBot:
    def __init__(self, config_dict: dict | None = None):
        logger.info("[Bot] __init__ enter")

        # сохраняем конфиг единообразно
        self.settings = config_dict or {}
        g = self.settings.get("global") or {}

        # режим
        self.mode = (self.settings.get("mode") or "SIMPLE").upper()
        symbol    = self.settings.get("symbol", "BTCUSDT")
        api_key   = self.settings.get("api_key", "")
        api_secret= self.settings.get("api_secret", "")

        logger.info("[Bot] mode=%s symbol=%s", self.mode, symbol)

        # клиент бинанса
        self.client = BinanceClient(
            api_key=api_key,
            api_secret=api_secret,
            symbol=symbol,
            testnet=True,   # как договаривались; при необходимости прокинем из настроек
        )

        # стратегия
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

    # В UI мы этим не пользуемся, но оставим для автономного запуска
    async def run(self):
        await self.client.init_session()
        logger.info("Бот запущен [%s]", self.mode)
        try:
            while True:
                candle = await self.client.get_latest_candle()
                if candle:
                    logger.info("[%s] Обработка свечи. Цена: %s", self.mode, candle["close"])
                    await self.strategy.handle_candle(candle)
                await asyncio.sleep(60)
        finally:
            await self.client.close()
