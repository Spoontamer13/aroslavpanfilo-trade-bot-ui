import asyncio
import logging
import os
import sys
from datetime import datetime

from PySide6.QtCore import QThread, Signal
from core.bot import TradingBot  # ваш класс из core/bot.py

class BotWorker(QThread):
    log_signal    = Signal(str)
    price_signal  = Signal(float)
    slippage_signal = Signal(float)
    finished      = Signal()

    def __init__(self, settings: dict = None):
        super().__init__()
        self.settings_dict = settings
        self._stop_requested = False

        # UI-хендлер на корневой логгер
        root = logging.getLogger()
        if not any(getattr(h, "_is_ui_handler", False) for h in root.handlers):
            handler = logging.StreamHandler()
            handler._is_ui_handler = True
            handler.setFormatter(
                logging.Formatter('[%(asctime)s] %(message)s', '%d/%m/%Y %H:%M:%S')
            )
            def emit(record):
                try:
                    text = handler.format(record)
                except Exception:
                    msg = record.getMessage()
                    ts = datetime.fromtimestamp(record.created).strftime('%d/%m/%Y %H:%M:%S')
                    text = f"[{ts}] {msg}"
                self.log_signal.emit(text)
            handler.emit = emit
            root.addHandler(handler)
        root.setLevel(logging.INFO)

    def set_settings(self, settings: dict):
        """Сохраняем переданные из UI настройки."""
        self.settings_dict = settings

    def start(self):
        self._stop_requested = False
        super().start()

    def run(self):
        if sys.platform.startswith("win"):
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            except Exception:
                pass

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        bot = TradingBot(config_dict=self.settings_dict)

        async def _runner():
            try:
                await bot.client.init_session()
                self.log_signal.emit(f"▶️ Бот запущен [{bot.mode}]")
            except Exception as e:
                import traceback
                self.log_signal.emit(f"[Ошибка init_session] {e}\n{traceback.format_exc()}")
                return

            # 2) простой REST-пинг к бирже (покажет проблемы сети/SSL)
            try:
                if hasattr(bot.client, "exchange_time"):
                    t = await bot.client.exchange_time()
                    self.log_signal.emit(f"[API] time ok: {t}")
            except Exception as e:
                import traceback
                self.log_signal.emit(f"[Ошибка сети (time)] {e}\n{traceback.format_exc()}")
                return

            try:
                while not self._stop_requested:
                    # замер пинга и получение свечи
                    t0 = asyncio.get_event_loop().time()
                    try:
                        candle = await bot.client.get_latest_candle()
                    except Exception as e:
                        self.log_signal.emit(f"[Ошибка сети] {e}")
                        await asyncio.sleep(5)
                        continue
                    ping_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
                    self.log_signal.emit(f"[Ping] {ping_ms} ms")

                    if candle:
                        self.log_signal.emit(f"[{bot.mode}] Новая свеча: {candle['close']:.2f}")
                        self.price_signal.emit(candle["close"])
                        sl = getattr(bot.client, 'avg_slippage', None)
                        if sl is not None:
                            self.slippage_signal.emit(sl)
                        await bot.strategy.handle_candle(candle)

                        # если стратегия копит avg_slippage — покажем в UI как %
                        sl = getattr(bot.strategy, "avg_slippage", None)
                        if sl is not None:
                            self.slippage_signal.emit(sl * 100)

                    # ждём минуту, но с проверкой флага
                    for _ in range(60):
                        if self._stop_requested:
                            break
                        await asyncio.sleep(1)
            finally:
                # При остановке: закрываем все открытые позиции
                if hasattr(bot.strategy, 'positions') and bot.strategy.positions:
                    self.log_signal.emit("[Stop] Закрываю все открытые позиции...")
                    for pos in list(bot.strategy.positions):
                        side = 'SELL' if pos['side'] == 'BUY' else 'BUY'
                        qty = pos['qty']
                        await bot.client.order(side, qty)
                        self.log_signal.emit(f"[Stop] Отправлен {side} ордер на {qty:.6f}")
                    bot.strategy.positions.clear()
                    bot.strategy.active = False
                await bot.client.close()
                self.finished.emit()


        loop.run_until_complete(_runner())
        loop.close()

    def stop(self):
        self._stop_requested = True
