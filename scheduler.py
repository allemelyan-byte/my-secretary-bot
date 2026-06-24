import asyncio
from datetime import datetime
from telegram.ext import Application


class Scheduler:
    def __init__(self, application: Application):
        self.app = application

    async def schedule_reminder(self, user_id: int, task_id: int, task_data: dict):
        remind_at_str = task_data.get("remind_at")
        if not remind_at_str:
            return
        try:
            remind_at = datetime.strptime(remind_at_str, "%Y-%m-%d %H:%M")
            now = datetime.now()
            if remind_at <= now:
                return

            delay = (remind_at - now).total_seconds()
            title = task_data.get("title", "задача")
            location = task_data.get("location")

            job_data = {
                "user_id": user_id,
                "task_id": task_id,
                "title": title,
                "location": location,
            }

            self.app.job_queue.run_once(
                self._send_reminder,
                when=delay,
                data=job_data,
                name=f"reminder_{task_id}"
            )
        except Exception as e:
            print(f"Scheduler error: {e}")

    async def _send_reminder(self, context):
        data = context.job.data
        user_id = data["user_id"]
        title = data["title"]
        location = data.get("location")

        text = f"⏰ *Напоминание!*\n\n📌 {title}"
        if location:
            text += f"\n📍 Место: {location}"

        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="Markdown"
        )
