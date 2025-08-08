# utils/logger.py
import logging, os
from logging.handlers import RotatingFileHandler
from pathlib import Path
import platform

def _log_path() -> Path:
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        d = Path(base) / "TradeBot"
    else:
        d = Path.home() / ".local" / "share" / "TradeBot"
    d.mkdir(parents=True, exist_ok=True)
    return d / "bot.log"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# консольный для DEV / UI тоже подцепит свой (не мешает)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', '%d/%m/%Y %H:%M:%S'))
logger.addHandler(ch)

# файл в стабильном месте
fh = RotatingFileHandler(_log_path(), maxBytes=10*1024*1024, backupCount=3, encoding='utf-8')
fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)-5s %(name)s: %(message)s', '%Y-%m-%d %H:%M:%S'))
logger.addHandler(fh)
