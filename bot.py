import asyncio
import logging
import os
from datetime import datetime, time
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, JobQueue
)
from ai_handler import AIHandler
from database import Database
from voice_handler import VoiceHandler
from scheduler import Scheduler

load_dotenv()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))

db = Database()
ai = AIHandler()
voice = VoiceHandler()


def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📋 Мои задачи"), KeyboardButton("📅 План на сегодня")],
        [KeyboardButton("✅ Выполнить задачу"), KeyboardButton("🔄 Перенести задачу")],
        [KeyboardButton("💪 Мои привычки"), KeyboardButton("📊 Статистика недели")],
        [KeyboardButton("🌅 Утреннее резюме"), KeyboardButton("🌙 Вечернее резюме")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, persistent=True)


async def check_user(update: Update) -> bool:
    if ALLOWED_USER_ID != 0 and update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update):
        return
    user = update.effective_user
    db.ensure_user(user.id, user.first_name)
    welcome = (
        f"👋 Привет, {user.first_name}! Я твой личный секретарь.\n\n"
        "Я умею:\n"
        "📝 Принимать задачи текстом и голосом\n"
        "📅 Планировать твой день\n"
        "💪 Отслеживать привычки\n"
        "⏰ Напоминать о задачах\n"
        "🚇 Считать время в пути\n"
        "📊 Анализировать продуктивность\n\n"
        "Просто напиши мне что нужно сделать, или используй кнопки ниже!"
    )
    await update.message.reply_text(welcome, reply_markup=get_main_keyboard())


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update):
        return

    user_id = update.effective_user.id
    text = update.message.text

    # Button handlers
    if text == "📋 Мои задачи":
        await show_tasks(update, context)
        return
    elif text == "📅 План на сегодня":
        await show_daily_plan(update, context)
        return
    elif text == "✅ Выполнить задачу":
        await complete_task_prompt(update, context)
        return
    elif text == "🔄 Перенести задачу":
        await reschedule_task_prompt(update, context)
        return
    elif text == "💪 Мои привычки":
        await show_habits(update, context)
        return
    elif text == "📊 Статистика недели":
        await show_weekly_stats(update, context)
        return
    elif text == "🌅 Утреннее резюме":
        await morning_summary(update, context)
        return
    elif text == "🌙 Вечернее резюме":
        await evening_summary(update, context)
        return

    # Context-aware state handling
    state = context.user_data.get("state")

    if state == "completing_task":
        await complete_task(update, context, text)
        return
    elif state == "rescheduling_task":
        await reschedule_task(update, context, text)
        return

    # Free-form AI processing
    await update.message.reply_text("🤔 Обрабатываю...")
    user_data = db.get_user_context(user_id)
    response = await ai.process_message(text, user_id, user_data)
    await handle_ai_response(update, context, user_id, response)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update):
        return

    await update.message.reply_text("🎤 Распознаю голосовое сообщение...")
    file = await update.message.voice.get_file()
    file_path = f"/tmp/voice_{update.effective_user.id}.ogg"
    await file.download_to_drive(file_path)

    transcribed = await voice.transcribe(file_path)
    if not transcribed:
        await update.message.reply_text("❌ Не удалось распознать голос. Попробуй ещё раз.")
        return

    await update.message.reply_text(f"✅ Распознано: *{transcribed}*", parse_mode="Markdown")
    update.message.text = transcribed
    await handle_text(update, context)


async def handle_ai_response(update, context, user_id, response):
    action = response.get("action")
    message = response.get("message", "")
    data = response.get("data", {})

    if action == "add_task":
        task_id = db.add_task(user_id, data)
        await update.message.reply_text(
            f"✅ Задача добавлена!\n\n{message}",
            reply_markup=get_main_keyboard()
        )
        # Schedule reminder if time is set
        if data.get("remind_at"):
            scheduler = Scheduler(context.application)
            await scheduler.schedule_reminder(user_id, task_id, data)

    elif action == "add_habit":
        db.add_habit(user_id, data)
        await update.message.reply_text(
            f"💪 Привычка добавлена!\n\n{message}",
            reply_markup=get_main_keyboard()
        )

    elif action == "show_plan":
        plan = db.get_today_tasks(user_id)
        habits = db.get_today_habits(user_id)
        plan_text = await ai.format_daily_plan(plan, habits, user_id)
        await update.message.reply_text(plan_text, parse_mode="Markdown")

    elif action == "travel_time":
        from maps_handler import MapsHandler
        maps = MapsHandler()
        origin = data.get("origin")
        destination = data.get("destination")
        if origin and destination:
            travel_info = await maps.get_transit_time(origin, destination)
            await update.message.reply_text(
                f"🚇 {message}\n\n{travel_info}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(message)

    elif action == "update_location":
        db.update_last_location(user_id, data.get("location"))
        await update.message.reply_text(f"📍 {message}")

    else:
        await update.message.reply_text(message, parse_mode="Markdown")


async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = db.get_today_tasks(user_id)
    if not tasks:
        await update.message.reply_text(
            "📋 На сегодня задач нет!\n\nНапиши мне что нужно сделать.",
            reply_markup=get_main_keyboard()
        )
        return

    text = "📋 *Твои задачи на сегодня:*\n\n"
    priorities = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    for i, task in enumerate(tasks, 1):
        status = "✅" if task["completed"] else "⬜"
        priority = priorities.get(task.get("priority", "medium"), "🟡")
        time_str = f" _{task['scheduled_time']}_" if task.get("scheduled_time") else ""
        text += f"{status} {priority} *{i}. {task['title']}*{time_str}\n"
        if task.get("location"):
            text += f"   📍 {task['location']}\n"
        text += "\n"

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())


async def show_daily_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = db.get_today_tasks(user_id)
    habits = db.get_today_habits(user_id)
    plan_text = await ai.format_daily_plan(tasks, habits, user_id)
    await update.message.reply_text(plan_text, parse_mode="Markdown", reply_markup=get_main_keyboard())


async def complete_task_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = db.get_today_tasks(user_id, incomplete_only=True)
    if not tasks:
        await update.message.reply_text("✅ Все задачи на сегодня выполнены! Отличная работа!")
        return

    text = "✅ *Какую задачу выполнил?* Напиши номер:\n\n"
    for i, task in enumerate(tasks, 1):
        text += f"{i}. {task['title']}\n"

    context.user_data["state"] = "completing_task"
    context.user_data["pending_tasks"] = tasks
    await update.message.reply_text(text, parse_mode="Markdown")


async def complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    tasks = context.user_data.get("pending_tasks", [])
    try:
        idx = int(text.strip()) - 1
        if 0 <= idx < len(tasks):
            task = tasks[idx]
            db.complete_task(task["id"])
            context.user_data["state"] = None
            # Update last location if task has one
            if task.get("location"):
                db.update_last_location(update.effective_user.id, task["location"])
            await update.message.reply_text(
                f"✅ Отлично! Задача *{task['title']}* выполнена! 🎉",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text("❌ Неверный номер. Попробуй ещё раз.")
    except ValueError:
        await update.message.reply_text("❌ Напиши номер задачи цифрой.")


async def reschedule_task_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = db.get_today_tasks(user_id, incomplete_only=True)
    if not tasks:
        await update.message.reply_text("📋 Нет задач для переноса!")
        return

    text = "🔄 *Какую задачу перенести?* Напиши: номер и новое время\nПример: `1 завтра в 15:00`\n\n"
    for i, task in enumerate(tasks, 1):
        text += f"{i}. {task['title']}\n"

    context.user_data["state"] = "rescheduling_task"
    context.user_data["pending_tasks"] = tasks
    await update.message.reply_text(text, parse_mode="Markdown")


async def reschedule_task(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    tasks = context.user_data.get("pending_tasks", [])
    user_id = update.effective_user.id
    response = await ai.parse_reschedule(text, tasks)
    if response.get("success"):
        db.reschedule_task(response["task_id"], response["new_datetime"])
        context.user_data["state"] = None
        await update.message.reply_text(
            f"🔄 Задача *{response['task_title']}* перенесена на *{response['new_datetime_str']}*",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Не понял. Напиши так: `1 завтра в 15:00`",
            parse_mode="Markdown"
        )


async def show_habits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    habits = db.get_habits(user_id)
    if not habits:
        await update.message.reply_text(
            "💪 У тебя пока нет привычек!\n\nНапиши мне, например:\n"
            "_«Добавь привычку: читать книгу 1 час в день»_",
            parse_mode="Markdown"
        )
        return

    text = "💪 *Твои привычки:*\n\n"
    for habit in habits:
        streak = habit.get("current_streak", 0)
        streak_emoji = "🔥" if streak >= 3 else "⭐"
        text += f"{streak_emoji} *{habit['name']}*\n"
        text += f"   ⏰ {habit.get('scheduled_time', 'Время не задано')}\n"
        text += f"   🔥 Серия: {streak} дней\n\n"

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())


async def show_weekly_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = db.get_weekly_stats(user_id)
    text = await ai.format_weekly_report(stats, user_id)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())


async def morning_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = db.get_today_tasks(user_id)
    habits = db.get_today_habits(user_id)
    summary = await ai.generate_morning_summary(tasks, habits, user_id)
    await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=get_main_keyboard())


async def evening_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    completed = db.get_completed_today(user_id)
    pending = db.get_today_tasks(user_id, incomplete_only=True)
    habits_done = db.get_habits_completed_today(user_id)
    summary = await ai.generate_evening_summary(completed, pending, habits_done, user_id)
    await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=get_main_keyboard())


# Scheduled jobs
async def send_morning_summary_job(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data["user_id"]
    tasks = db.get_today_tasks(user_id)
    habits = db.get_today_habits(user_id)
    summary = await ai.generate_morning_summary(tasks, habits, user_id)
    await context.bot.send_message(chat_id=user_id, text=summary, parse_mode="Markdown")


async def send_evening_summary_job(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data["user_id"]
    completed = db.get_completed_today(user_id)
    pending = db.get_today_tasks(user_id, incomplete_only=True)
    habits_done = db.get_habits_completed_today(user_id)
    summary = await ai.generate_evening_summary(completed, pending, habits_done, user_id)
    await context.bot.send_message(chat_id=user_id, text=summary, parse_mode="Markdown")


async def post_init(application: Application):
    """Schedule daily jobs after bot starts."""
    users = db.get_all_users()
    for user in users:
        user_id = user["user_id"]
        # Morning at 8:00
        application.job_queue.run_daily(
            send_morning_summary_job,
            time=time(8, 0),
            data={"user_id": user_id},
            name=f"morning_{user_id}"
        )
        # Evening at 21:00
        application.job_queue.run_daily(
            send_evening_summary_job,
            time=time(21, 0),
            data={"user_id": user_id},
            name=f"evening_{user_id}"
        )


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Бот запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
