# utils/logger.py
import logging
import os
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Глобально доступный путь к логу (заполним в _init_logger)
LOG_PATH: Path | None = None

def _get_appdata_dir() -> Path:
    """
    Куда писать лог в Windows/EXE:
    %APPDATA%\TradeBot\bot.log
    Если APPDATA нет (редко) — в домашнюю.
    """
    base = os.getenv("APPDATA")
    if base:
        d = Path(base) / "TradeBot"
    else:
        d = Path.home() / "TradeBot"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _init_logger() -> logging.Logger:
    """
    Инициализирует корневой логгер ровно один раз.
    Пишем:
      - в файл %APPDATA%\TradeBot\bot.log (ротация 10 МБ x 5)
      - в stdout (для отладки/видимости в dev и в UI-пайпах)
    """
    root = logging.getLogger()  # корневой
    if getattr(root, "_tradebot_inited", False):
        return root

    root.setLevel(logging.INFO)

    # --- File handler (ротация) ---
    global LOG_PATH
    LOG_PATH = _get_appdata_dir() / "bot.log"
    fh = RotatingFileHandler(
        LOG_PATH,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        "%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)

    # --- Console / Stream handler ---
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(logging.Formatter(
        "[%(asctime)s] %(message)s",
        "%d/%m/%Y %H:%M:%S",
    ))
    root.addHandler(sh)

    # Флаг, чтобы не инициализировать повторно
    root._tradebot_inited = True

    # Метка старта — чтобы убедиться, что лог реально пишется
    root.info("=== Logger initialized ===")
    root.info(f"Log file: {LOG_PATH}")

    return root

# Экспортируем готовый логгер
logger = _init_logger()

def get_log_path() -> str:
    """Удобный хелпер: путь к файлу лога строкой."""
    return str(LOG_PATH) if LOG_PATH else ""
