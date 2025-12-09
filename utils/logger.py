import logging
import sys
import os

def setup_logger():
    # Создаем форматтер: Время - Уровень - Модуль - Сообщение
    log_format = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    # Основной логгер
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 1. Хендлер для ФАЙЛА (bot.log) - всегда UTF-8
    file_handler = logging.FileHandler(filename='bot.log', encoding='utf-8', mode='a')
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    # 2. Хендлер для КОНСОЛИ
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)
    
    # Пытаемся починить кодировку консоли Windows
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    return logger