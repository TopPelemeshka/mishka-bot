# autopost.py
"""
Модуль для автоматической публикации контента в Telegram канале/группе.
Обеспечивает функционал:
- Автоматическая публикация постов с изображениями и анекдотами
- Автоматическая публикация видеоконтента
- Планирование постов по расписанию
- Отслеживание статистики публикаций
"""
import datetime
import random
import logging

from telegram import InputMediaPhoto, InputMediaVideo
from telegram.ext import ContextTypes

from config import POST_CHAT_ID, TIMEZONE_OFFSET
from utils import random_time_in_range
from utils_autopost import (
    get_top_anecdote_and_remove,
    get_random_file_from_folder,
    move_file_to_archive,
    get_available_stats,
    predict_10pics_posts,
    predict_4videos_posts,
    predict_full_days,
    is_valid_file,
)

from quiz import count_quiz_questions
from wisdom import count_wisdoms

import state

logger = logging.getLogger(__name__)

def _get_folder_by_category(category: str):
    """
    Вспомогательная функция для выбора папки по названию категории.
    
    Args:
        category: Строка с названием категории контента
        
    Returns:
        Путь к директории с соответствующим контентом или None если категория не найдена
    """
    from config import (
        ERO_ANIME_DIR,
        ERO_REAL_DIR,
        SINGLE_MEME_DIR,
        STANDART_ART_DIR,
        STANDART_MEME_DIR,
        VIDEO_MEME_DIR,
        VIDEO_ERO_DIR,
        VIDEO_AUTO_DIR
    )
    if category == "ero-anime":
        return ERO_ANIME_DIR
    elif category == "ero-real":
        return ERO_REAL_DIR
    elif category == "single-meme":
        return SINGLE_MEME_DIR
    elif category == "standart-art":
        return STANDART_ART_DIR
    elif category == "standart-meme":
        return STANDART_MEME_DIR
    elif category == "video-meme":
        return VIDEO_MEME_DIR
    elif category == "video-ero":
        return VIDEO_ERO_DIR
    elif category == "video-auto":
        return VIDEO_AUTO_DIR
    return None


async def autopost_10_pics_callback(context: ContextTypes.DEFAULT_TYPE):
    """
    Callback-функция для публикации поста с 10 изображениями и анекдотом.
    Выбирает изображения из разных категорий согласно заданному списку.
    
    Args:
        context: Контекст от планировщика задач Telegram
    """
    if not state.autopost_enabled:
        return
    categories = [
        "ero-real",
        "standart-art/standart-meme",
        "ero-anime",
        "single-meme/standart-meme",
        "ero-real",
        "standart-meme",
        "ero-anime",
        "standart-meme",
        "ero-real",
        "standart-meme"
    ]

    anecdote = get_top_anecdote_and_remove()
    if not anecdote:
        await context.bot.send_message(chat_id=POST_CHAT_ID, text="Анекдоты закончились 😭")
        return

    media = []
    used_files = []  # Список кортежей (file_path, real_cat)

    for cat in categories:
        if "/" in cat:
            # Если указана альтернатива через слеш, пробуем первую категорию, а если не выйдет - вторую
            cat1, cat2 = cat.split("/")
            file_path = get_random_file_from_folder(_get_folder_by_category(cat1))
            if file_path is None:
                file_path = get_random_file_from_folder(_get_folder_by_category(cat2))
                real_cat = cat2
            else:
                real_cat = cat1
        else:
            file_path = get_random_file_from_folder(_get_folder_by_category(cat))
            real_cat = cat

        if file_path is None:
            await context.bot.send_message(
                chat_id=POST_CHAT_ID,
                text=f"У нас закончились {cat} 😭"
            )
            return

        # Логируем выбранный файл
        logger.info(f"Подготовка файла для категории {real_cat}: {file_path}")
        
        # Дополнительная проверка перед отправкой
        if not is_valid_file(file_path):
            logger.error(f"Файл не прошел проверку: {file_path}")
            await context.bot.send_message(
                chat_id=POST_CHAT_ID,
                text=f"Файл для категории {real_cat} не прошел проверку: {file_path}"
            )
            return
            
        media.append(InputMediaPhoto(open(file_path, "rb")))
        used_files.append((file_path, real_cat))

    try:
        # Отправляем медиагруппу из 10 изображений
        await context.bot.send_media_group(
            chat_id=POST_CHAT_ID,
            media=media,
            read_timeout=180
        )
        # Отправляем анекдот отдельным сообщением
        await context.bot.send_message(
            chat_id=POST_CHAT_ID,
            text=anecdote,
            read_timeout=180
        )
    except Exception as e:
        # Логируем список файлов, с которыми произошла ошибка
        logger.error(f"Ошибка при отправке поста. Файлы: {used_files}. Ошибка: {e}")
        await context.bot.send_message(
            chat_id=POST_CHAT_ID,
            text=f"Ошибка при отправке поста: {e}"
        )
        return

    # Перемещаем использованные файлы в архив
    for path, cat in used_files:
        move_file_to_archive(path, cat)


async def autopost_4_videos_callback(context: ContextTypes.DEFAULT_TYPE):
    """
    Пост с 4 видео (по одному из video-meme, video-ero, и два из video-auto) и анекдотом.
    
    Если нет видео из категории video-auto или video-ero,
    то вместо него используется видео из video-meme.
    
    Args:
        context: Контекст от планировщика задач Telegram
    """
    if not state.autopost_enabled:
        return

    anecdote = get_top_anecdote_and_remove()
    if not anecdote:
        await context.bot.send_message(chat_id=POST_CHAT_ID, text="Анекдоты закончились 😭")
        return

    media = []
    used_files = []
    
    # Видео из категории video-meme (обязательно)
    file_meme = get_random_file_from_folder(_get_folder_by_category("video-meme"))
    if file_meme is None:
        await context.bot.send_message(
            chat_id=POST_CHAT_ID,
            text="Не хватает видео video-meme 😭"
        )
        return
    
    # Видео из категории video-ero (с фолбеком на video-meme)
    file_ero = get_random_file_from_folder(_get_folder_by_category("video-ero"))
    category_ero = "video-ero"
    if file_ero is None:
        # Используем ещё одно видео из video-meme вместо video-ero
        file_ero = get_random_file_from_folder(_get_folder_by_category("video-meme"))
        category_ero = "video-meme" # меняем категорию для перемещения в архив
        if file_ero is None:
            await context.bot.send_message(
                chat_id=POST_CHAT_ID,
                text="Не хватает видео video-meme для замены video-ero 😭"
            )
            return
    
    # Первое видео из категории video-auto (с фолбеком на video-meme)
    file_auto1 = get_random_file_from_folder(_get_folder_by_category("video-auto"))
    category_auto1 = "video-auto"
    if file_auto1 is None:
        # Используем ещё одно видео из video-meme вместо video-auto
        file_auto1 = get_random_file_from_folder(_get_folder_by_category("video-meme"))
        category_auto1 = "video-meme" # меняем категорию для перемещения в архив
        if file_auto1 is None:
            await context.bot.send_message(
                chat_id=POST_CHAT_ID,
                text="Не хватает видео video-meme для замены video-auto 😭"
            )
            return
    
    # Второе видео из категории video-auto (с фолбеком на video-meme)
    file_auto2 = get_random_file_from_folder(_get_folder_by_category("video-auto"))
    category_auto2 = "video-auto"
    if file_auto2 is None:
        # Используем ещё одно видео из video-meme вместо video-auto
        file_auto2 = get_random_file_from_folder(_get_folder_by_category("video-meme"))
        category_auto2 = "video-meme" # меняем категорию для перемещения в архив
        if file_auto2 is None:
            await context.bot.send_message(
                chat_id=POST_CHAT_ID,
                text="Не хватает видео video-meme для замены второго video-auto 😭"
            )
            return
    
    # Проверяем каждое видео
    for file_path, category in [
        (file_auto1, category_auto1),
        (file_meme, "video-meme"), 
        (file_ero, category_ero), 
        (file_auto2, category_auto2)
    ]:
        # Дополнительная проверка перед отправкой
        if not is_valid_file(file_path):
            logger.error(f"Видео не прошло проверку: {file_path}")
            await context.bot.send_message(
                chat_id=POST_CHAT_ID,
                text=f"Видео из категории {category} не прошло проверку: {file_path}"
            )
            return
        
        media.append(InputMediaVideo(open(file_path, "rb")))
        used_files.append((file_path, category))

    # Публикуем
    try:
        # Увеличиваем таймаут до 180 секунд
        await context.bot.send_media_group(
            chat_id=POST_CHAT_ID,
            media=media,
            read_timeout=180
        )
        await context.bot.send_message(
            chat_id=POST_CHAT_ID,
            text=anecdote,
            read_timeout=180
        )
    except Exception as e:
        # Логируем подробности об ошибке вместе с информацией о файлах
        logger.error(f"Ошибка при отправке видео. Файлы: {used_files}. Ошибка: {e}")
        await context.bot.send_message(
            chat_id=POST_CHAT_ID,
            text=f"Ошибка при отправке видео: {e}\nИспользуемые файлы: {used_files}"
        )
        return

    # Переносим в архив
    for path, cat in used_files:
        move_file_to_archive(path, cat)


async def stop_autopost_command(update, context):
    """Обработчик команды для отключения автопостинга."""
    state.autopost_enabled = False
    state.save_state(state.autopost_enabled, state.quiz_enabled, state.wisdom_enabled, state.betting_enabled)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Автопостинг отключён!")

async def start_autopost_command(update, context):
    """Обработчик команды для включения автопостинга."""
    state.autopost_enabled = True
    state.save_state(state.autopost_enabled, state.quiz_enabled, state.wisdom_enabled, state.betting_enabled)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Автопостинг включён!")

async def stats_command(update, context):
    """Отображаем статистику остатков, прогнозы и узкое место (в том числе с учётом видео)."""
    stats = get_available_stats()
    # Получаем предсказания для разных типов постов
    max_10pics = predict_10pics_posts(stats)
    max_4videos = predict_4videos_posts(stats)
    
    wisdom_count = count_wisdoms()
    
    # Формируем словарь «отношений» для ключевых категорий.
    # Для изображений:
    #   ero-real: требуется 3 штуки на пост → количество постов = count / 3
    #   ero-anime: требуется 2 штуки на пост → количество постов = count / 2
    #   standart-meme: требуется 3 штуки на пост (без учёта fallback) → count / 3
    #   anecdotes: 1 анекдот на пост → count постов
    # Для видео:
    #   video-meme: требуется минимум 1 и до 4 видео на пост, в зависимости от наличия video-ero и video-auto
    ratios = {}
    
    # Расчёт для ero-real (требуется 9 на день: 3 * 3)
    if stats.get("ero-real", 0):
        ratios["ero-real"] = stats["ero-real"] / 9  # 3*3 для 3-х постов с 10 картинками в день
    
    # Расчёт для ero-anime (требуется 6 на день: 2 * 3)
    if stats.get("ero-anime", 0):
        ratios["ero-anime"] = stats["ero-anime"] / 6  # 2*3 для 3-х постов с 10 картинками в день
    
    # НЕ включаем в ratios заменяемые категории:
    # standart-art (заменяется на standart-meme)
    # single-meme (заменяется на standart-meme)
    
    # Расчёт для standart-meme с учётом возможных замен
    if stats.get("standart-meme", 0):
        # Базовое потребление: 9 (по 3 на каждый пост)
        base_meme_needed = 9
        
        # Потенциальные замены standart-art
        if stats.get("standart-art", 0) < 3:
            additional_for_art = 3 - stats.get("standart-art", 0)
        else:
            additional_for_art = 0
            
        # Потенциальные замены single-meme
        if stats.get("single-meme", 0) < 3:
            additional_for_single = 3 - stats.get("single-meme", 0)
        else:
            additional_for_single = 0
            
        total_meme_needed = base_meme_needed + additional_for_art + additional_for_single
        ratios["standart-meme"] = stats["standart-meme"] / total_meme_needed
    
    # Расчёт для анекдотов (требуется 4 на день: 3 для картинок + 1 для видео)
    if stats.get("anecdotes", 0):
        ratios["anecdotes"] = stats["anecdotes"] / 4  # 3 для картинок + 1 для видео в день
    
    # НЕ включаем в ratios заменяемые категории:
    # video-ero (заменяется на video-meme)
    # video-auto (заменяется на video-meme)
        
    # Расчет для video-meme с учетом возможных замен
    if stats.get("video-meme", 0):
        # Базовое потребление всегда 1
        needed_meme_videos = 1
        
        # Если нет video-ero, нужно ещё +1 video-meme как замена
        if stats.get("video-ero", 0) == 0:
            needed_meme_videos += 1
            
        # Если video-auto < 2, нужны замены (1 или 2)
        if stats.get("video-auto", 0) < 2:
            needed_meme_videos += (2 - stats.get("video-auto", 0))
            
        ratios["video-meme"] = stats["video-meme"] / needed_meme_videos

    # Добавляем информацию о заменяемых категориях для справки
    replaceable_categories = {}
    # Проверяем заменяемые категории
    if stats.get("standart-art", 0):
        replaceable_categories["standart-art"] = stats["standart-art"] / 3
        
    if stats.get("single-meme", 0):
        replaceable_categories["single-meme"] = stats["single-meme"] / 3
        
    if stats.get("video-ero", 0):
        replaceable_categories["video-ero"] = stats["video-ero"] / 1
        
    if stats.get("video-auto", 0):
        replaceable_categories["video-auto"] = stats["video-auto"] / 2  # Теперь нужно 2 видео на пост

    if ratios:
        bottleneck_category = min(ratios, key=ratios.get)
        bottleneck_posts = int(ratios[bottleneck_category])
    else:
        bottleneck_category = "нет данных"
        bottleneck_posts = 0
        
    # Рассчитываем дни для картинок на основе bottleneck_category для картинок
    pic_ratios = {k: v for k, v in ratios.items() if k in ['ero-real', 'ero-anime', 'standart-meme', 'anecdotes']}
    if pic_ratios:
        pics_bottleneck = min(pic_ratios.values())
        pics_days = int(pics_bottleneck)
    else:
        pics_days = 0
        
    # Рассчитываем дни для видео с учетом всех возможных замен
    video_days = 0
    if stats.get("video-meme", 0):
        # Количество видео-мемов
        video_meme_count = stats.get("video-meme", 0)
        # Количество видео-эро (может быть заменено видео-мемами)
        video_ero_count = stats.get("video-ero", 0)
        # Количество авто-видео (нужно 2 на пост, может быть заменено видео-мемами)
        video_auto_count = stats.get("video-auto", 0)
        # Количество анекдотов
        anecdote_count = stats.get("anecdotes", 0)
        
        # Фаза 1: Используем video-auto, video-ero и 1 video-meme
        auto_pairs = video_auto_count // 2  # Сколько пар video-auto (2 на пост)
        phase1_posts = min(auto_pairs, video_ero_count, video_meme_count)
        
        remaining_meme = video_meme_count - phase1_posts
        remaining_ero = video_ero_count - phase1_posts
        remaining_anecdotes = anecdote_count - phase1_posts
        
        # Фаза 2: Заменяем video-auto на video-meme, используем video-ero
        # Нужно 3 video-meme (1 основной + 2 замены auto) и 1 video-ero на пост
        if remaining_meme >= 3 and remaining_ero > 0 and remaining_anecdotes > 0:
            phase2_posts = min(remaining_meme // 3, remaining_ero, remaining_anecdotes)
            
            remaining_meme -= phase2_posts * 3
            remaining_ero -= phase2_posts
            remaining_anecdotes -= phase2_posts
        else:
            phase2_posts = 0
        
        # Фаза 3: Заменяем и video-auto и video-ero на video-meme
        # Нужно 4 video-meme (1 основной + 2 замены auto + 1 замена ero) на пост
        if remaining_meme >= 4 and remaining_anecdotes > 0:
            phase3_posts = min(remaining_meme // 4, remaining_anecdotes)
        else:
            phase3_posts = 0
        
        # Общее количество постов
        video_days = phase1_posts + phase2_posts + phase3_posts

    quiz_count = count_quiz_questions()
    text_lines = []
    text_lines.append(f"У НАС НЕХВАТКА КАРТИНОК 70 ПРОЦЕНТОВ. \nTOPPELEMESHKA, ГДЕ, СУКА, МЕМЫ?")
    text_lines.append("")
    text_lines.append("Текущие остатки материалов:")
    for k, v in stats.items():
        text_lines.append(f"  {k}: {v}")
    text_lines.append("")
    text_lines.append(
        f"Дефицит: '{bottleneck_category}' (хватит примерно на {bottleneck_posts} дней)"
    )
    text_lines.append(f"Соотношения основных категорий (дней):")
    for cat, value in sorted(ratios.items(), key=lambda x: x[1]):
        text_lines.append(f"  {cat}: {value:.1f}")
    
    if replaceable_categories:
        text_lines.append("")
        text_lines.append(f"Заменяемые категории (не учитываются в дефиците):")
        for cat, value in sorted(replaceable_categories.items(), key=lambda x: x[1]):
            text_lines.append(f"  {cat}: {value:.1f}")
    
    text_lines.append("")
    text_lines.append(f"Вопросов для викторины осталось: {quiz_count}")
    text_lines.append(f"Цитат дня осталось: {wisdom_count}")
    text_lines.append("")
    text_lines.append("")
    text_lines.append(f"<b>ПОСТОВ С КАРТИНКАМИ ОСТАЛОСЬ НА {pics_days} ДНЕЙ.</b>")
    text_lines.append(f"<b>ПОСТОВ С ВИДЕО ОСТАЛОСЬ НА {video_days} ДНЕЙ.</b>")
    text_lines.append(f"<b>ВИКТОРИН ОСТАЛОСЬ НА {round(quiz_count/8)} ДНЕЙ.</b>")
    text_lines.append(f"<b>ЦИТАТ ДНЯ ОСТАЛОСЬ НА {wisdom_count} ДНЕЙ.</b>")

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="\n".join(text_lines),
        parse_mode="HTML"
    )

async def next_posts_command(update, context):
    """
    Показывает время следующего запуска постов
    и сколько до них осталось (в часах и минутах).
    Отображает время в локальном часовом поясе согласно настройке TIMEZONE_OFFSET.
    """
    # Получаем текущее время в UTC
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    # Получаем список всех заданий
    all_jobs = context.job_queue.jobs()

    if not all_jobs:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Нет запланированных задач.")
        return

    lines = []
    for job in all_jobs:
        if job.next_run_time is None:
            continue
        
        # Приводим время следующего запуска к UTC
        job_next_utc = job.next_run_time.astimezone(datetime.timezone.utc)
        delta = job_next_utc - now_utc
        total_seconds = delta.total_seconds()
        if total_seconds < 0:
            continue

        # Конвертируем время запуска в локальный часовой пояс
        local_timezone = datetime.timezone(datetime.timedelta(hours=TIMEZONE_OFFSET))
        job_next_local = job_next_utc.astimezone(local_timezone)
        
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        lines.append(f"Задача: {job.name}")
        lines.append(f"  Следующий запуск: {job_next_local.strftime('%Y-%m-%d %H:%M:%S')} (UTC+{TIMEZONE_OFFSET})")
        lines.append(f"  До запуска осталось: {hours} ч {minutes} мин\n")

    if not lines:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Не найдено активных задач с будущим временем запуска.")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="\n".join(lines))
