import logging
from logging.handlers import RotatingFileHandler


logger = logging.getLogger()
logger.setLevel(logging.INFO)


console_handler = logging.StreamHandler()

console_fmt = logging.Formatter('[%(asctime)s] %(message)s', '%d/%m/%Y %H:%M:%S')
console_handler.setFormatter(console_fmt)
logger.addHandler(console_handler)


file_handler = RotatingFileHandler('bot.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
file_fmt = logging.Formatter('%(asctime)s %(levelname)-5s %(name)s: %(message)s', '%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(file_fmt)
logger.addHandler(file_handler)