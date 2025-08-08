# ui/executor.py
import asyncio
import logging
import sys
from datetime import datetime
from PySide6.QtCore import QThread, Signal
from core.bot import TradingBot
from utils.logger import logger  # важно: используем тот же корневой

class BotWorker(QThread):
    log_signal    = Signal(str)
    price_signal  = Signal(float)
    slippage_signal = Signal(float)
    finished      = Signal()

    def __init__(self, settings: dict = None):
        super().__init__()
        self.settings_dict = settings
        self._stop_requested = False

        # дублируем в UI то, что пишет логгер
        root = logging.getLogger()
        if not any(getattr(h, "_is_ui_handler", False) for h in root.handlers):
            h = logging.StreamHandler()
            h._is_ui_handler = True
            h.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', '%d/%m/%Y %H:%M:%S'))
            def emit(record):
                try:
                    text = h.format(record)
                except Exception:
                    msg = record.getMessage()
                    ts = datetime.fromtimestamp(record.created).strftime('%d/%m/%Y %H:%M:%S')
                    text = f"[{ts}] {msg}"
                self.log_signal.emit(text)
            h.emit = emit
            root.addHandler(h)
        root.setLevel(logging.INFO)

    def set_settings(self, settings: dict):
        self.settings_dict = settings

    def start(self):
        logging.getLogger().info("[Worker] start() called")
        self._stop_requested = False
        super().start()

    def run(self):
        try:
            logging.getLogger().info("[Worker] run() enter, platform=%s", sys.platform)
            if sys.platform.startswith("win"):
                try:
                    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                    logging.getLogger().info("[Worker] WindowsSelectorEventLoopPolicy set")
                except Exception as e:
                    logging.getLogger().warning("[Worker] set_event_loop_policy warn: %r", e)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logging.getLogger().info("[Worker] event loop created")

            async def _runner():
                try:
                    logging.getLogger().info("[Worker] creating TradingBot…")
                    bot = TradingBot(config_dict=self.settings_dict)
                    logging.getLogger().info("[Worker] TradingBot created; calling init_session()")
                    await bot.client.init_session()
                    logging.getLogger().info("[Worker] init_session OK")
                except Exception:
                    logging.getLogger().exception("[Worker] init phase failed")
                    return

                # быстрый REST-пинг
                try:
                    t = await bot.client.exchange_time()
                    logging.getLogger().info("[Worker] /time -> %s", t)
                except Exception:
                    logging.getLogger().exception("[Worker] /time failed")
                    return

                try:
                    while not self._stop_requested:
                        t0 = loop.time()
                        try:
                            candle = await bot.client.get_latest_candle()
                        except Exception:
                            logging.getLogger().exception("[Worker] get_latest_candle failed")
                            await asyncio.sleep(5)
                            continue
                        ping_ms = int((loop.time() - t0) * 1000)
                        logging.getLogger().info("[Ping] %d ms", ping_ms)

                        if candle:
                            logging.getLogger().info("[Candle] %s", candle)
                            self.price_signal.emit(candle["close"])
                            await bot.strategy.handle_candle(candle)

                        for _ in range(60):
                            if self._stop_requested:
                                break
                            await asyncio.sleep(1)
                finally:
                    try:
                        await bot.client.close()
                    except Exception:
                        logging.getLogger().exception("[Worker] close() failed")
                    self.finished.emit()
                    logging.getLogger().info("[Worker] finished")

            loop.run_until_complete(_runner())
        except Exception:
            logging.getLogger().exception("[Worker] run() top-level crash")
        finally:
            try:
                loop.close()
            except Exception:
                pass
