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

        # сохраняем конфиг
        self.cfg: dict = config_dict or {}
        g = self.cfg.get("global") or {}

        # режим/символ
        self.mode: str = (self.cfg.get("mode") or "SIMPLE").upper()
        self.symbol: str = self.cfg.get("symbol", "BTCUSDT")
        logger.info("[Bot] mode=%s symbol=%s", self.mode, self.symbol)

        # клиент биржи
        self.client = BinanceClient(
            api_key=self.cfg.get("api_key", ""),
            api_secret=self.cfg.get("api_secret", ""),
            symbol=self.symbol,
            testnet=True,
            leverage=int(g.get("leverage", 10)),
            hedge=True,                   # если хочешь — сделай это флагом из настроек
        )

        # выбор стратегии
        strat_map = {
            "SIMPLE": SimpleStrategy,
            "RSI": RSIStrategy,
            "MRC": MRCStrategy,
            "ZONE": ZoneStrategy,
            "COMBO": ComboStrategy,
        }
        strat_cls = strat_map.get(self.mode, SimpleStrategy)
        self.strategy = strat_cls(self.client, self.cfg)

        logger.info("[Bot] strategy=%s ready", strat_cls.__name__)

     async def run(self):
        await self.client.init_session()
        logger.info(f"Бот запущен [{self.mode}]")

        try:
            while True:
                candle = await self.client.get_latest_candle()
                if candle:
                    logger.info(f"[{self.mode}] Обработка свечи. Цена: {candle['close']}")
                    await self.strategy.handle_candle(candle)
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            logger.info("Бот остановлен вручную")
        finally:
            await self.client.close()

