# main.py
import logging
import asyncio

from core.bot import TradingBot

if __name__ == "__main__":
    # 1) Логируем и в консоль, и в файл (если у вас настроен файл в logger)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    # 2) Создаём бота
    bot = TradingBot()

    try:
        # 3) Выводим сразу в stdout (чтобы UI видел, что процесс ещё жив)
        print(f"▶️ Запускаю бота в режиме: {bot.mode}")

        # 4) Запускаем основной цикл работы бота
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("✋ Бот остановлен вручную")