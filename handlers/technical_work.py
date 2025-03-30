"""
Модуль обработчика команды /technical_work.
Отправляет уведомление о технических работах с изображением 
в канал для публикаций.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import POST_CHAT_ID  # Или, если нужен другой чат, определите другой ID

async def technical_work_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /technical_work — сообщает о начале технических работ.
    Отправляет в указанный чат картинку technical_work.jpg и информационное сообщение.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст обработчика
        
    Note:
        Сообщение отправляется в канал, указанный в POST_CHAT_ID,
        а не в чат, из которого была вызвана команда.
    """
    try:
        with open("pictures/technical_work.jpg", "rb") as photo:
            await context.bot.send_photo(
                chat_id=POST_CHAT_ID,
                photo=photo,
                caption="⚙️ Ведутся технические работы, бот будет недоступен.\n\nГотовьтесь к обновлениям, отдыхайте, пока можете! 😄"
            )
    except Exception as e:
        logging.error(f"Ошибка отправки technical_work.jpg: {e}")
        await context.bot.send_message(
            chat_id=POST_CHAT_ID,
            text="Ошибка: не удалось отправить сообщение о технических работах."
        )
