# utils.py
"""
Общие утилиты и вспомогательные функции, используемые в разных частях бота.
Включает функции для проверки прав доступа, работы со временем и другие.
"""
import logging
import random
import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config import ALLOWED_CHAT_IDS

logger = logging.getLogger(__name__)

def is_allowed_chat(chat_id: int) -> bool:
    """
    Проверяет, разрешен ли чат для работы бота.
    
    Args:
        chat_id: ID чата для проверки
        
    Returns:
        True если чат разрешен, False в противном случае
    """
    return chat_id in ALLOWED_CHAT_IDS

async def check_chat_and_execute(update: Update, context: ContextTypes.DEFAULT_TYPE, handler_func):
    """
    Проверяет, разрешен ли чат, и только потом выполняет обработчик.
    Если чат не разрешен, отправляет сообщение и пытается покинуть его.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст обработчика
        handler_func: Функция-обработчик, которую нужно выполнить
    """
    chat_id = update.effective_chat.id
    if not is_allowed_chat(chat_id):
        await context.bot.send_message(chat_id=chat_id, text="Извините, я могу работать только в разрешённых группах.")
        try:
            await context.bot.leave_chat(chat_id)
        except Exception as e:
            logger.error(f"Ошибка при попытке покинуть чат {chat_id}: {e}")
        return
    await handler_func(update, context)

def random_time_in_range(start: datetime.time, end: datetime.time) -> datetime.time:
    """
    Возвращает случайное время (datetime.time) между start и end.
    Например, если start = datetime.time(18, 15) и end = datetime.time(18, 45),
    то функция вернёт время между 18:15:00 и 18:45:00.
    
    Args:
        start: Начальное время диапазона
        end: Конечное время диапазона
        
    Returns:
        Случайное время в заданном диапазоне
    """
    start_s = start.hour * 3600 + start.minute * 60 + start.second
    end_s = end.hour * 3600 + end.minute * 60 + end.second
    r = random.randint(start_s, end_s)
    hh = r // 3600
    mm = (r % 3600) // 60
    ss = r % 60
    return datetime.time(hour=hh, minute=mm, second=ss)

def parse_time_from_string(time_str: str) -> datetime.time:
    """
    Преобразует строку времени в формате HH:MM в объект datetime.time
    
    Args:
        time_str: Строка времени в формате "часы:минуты"
        
    Returns:
        Объект datetime.time, соответствующий переданной строке
    """
    hours, minutes = map(int, time_str.split(':'))
    return datetime.time(hour=hours, minute=minutes)
