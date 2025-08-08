import yaml
import asyncio
from utils.logger import logger
from utils.binance_api import BinanceClient
from core.strategies.simple import SimpleStrategy
from core.strategies.rsi import RSIStrategy
from core.strategies.mrc import MRCStrategy
from core.strategies.zone import ZoneStrategy
from core.strategies.combo import ComboStrategy

class TradingBot:
    def __init__(self, config_dict: dict = None):
       
        with open("config/settings.yaml", "r") as f:
            file_cfg = yaml.safe_load(f) or {}

        
        if config_dict:
            file_cfg.update(config_dict)

        self.settings = file_cfg

       
        api_key    = self.settings.get("api_key")
        api_secret = self.settings.get("api_secret")
        symbol     = self.settings.get("symbol")

       

        
        self.client = BinanceClient(api_key, api_secret, symbol) 
        
        self.mode = self.settings.get("mode", "SIMPLE").upper()

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