import os
import json
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Ты личный секретарь и помощник. Отвечай на русском языке.
Твоя задача — понять намерение пользователя и вернуть JSON-ответ.

Сегодняшняя дата: {today}
День недели: {weekday}

Возможные действия (поле "action"):
- "add_task" — добавить задачу/встречу/дело
- "add_habit" — добавить регулярную привычку
- "show_plan" — показать план на день
- "travel_time" — узнать время в пути
- "chat" — просто поговорить / дать совет

Формат ответа для add_task:
{{
  "action": "add_task",
  "message": "Краткое подтверждение для пользователя",
  "data": {{
    "title": "Название задачи",
    "description": "Описание (если есть)",
    "priority": "high/medium/low",
    "location": "Место (если есть)",
    "scheduled_date": "YYYY-MM-DD",
    "scheduled_time": "HH:MM или null",
    "remind_at": "YYYY-MM-DD HH:MM или null"
  }}
}}

Формат для add_habit:
{{
  "action": "add_habit",
  "message": "Подтверждение",
  "data": {{
    "name": "Название привычки",
    "description": "Описание",
    "scheduled_time": "HH:MM",
    "duration_minutes": 60,
    "days_of_week": "1,2,3,4,5,6,7"
  }}
}}

Формат для travel_time:
{{
  "action": "travel_time",
  "message": "Сообщение пользователю",
  "data": {{
    "origin": "Откуда",
    "destination": "Куда"
  }}
}}

Формат для chat:
{{
  "action": "chat",
  "message": "Твой ответ пользователю в Markdown"
}}

Контекст пользователя:
{user_context}

ВАЖНО: Возвращай ТОЛЬКО валидный JSON без markdown блоков и без пояснений."""

DAYS_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда", 3: "Четверг",
    4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}


def ask_groq(system: str, user: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        temperature=0.3,
        max_tokens=2000,
    )
    return response.choices[0].message.content.strip()


class AIHandler:
    def __init__(self):
        pass

    async def process_message(self, text: str, user_id: int, user_data: Dict) -> Dict:
        today = date.today()
        system = SYSTEM_PROMPT.format(
            today=today.isoformat(),
            weekday=DAYS_RU[today.weekday()],
            user_context=json.dumps(user_data, ensure_ascii=False, indent=2)
        )
        try:
            raw = ask_groq(system, text)
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```")
            return json.loads(raw)
        except Exception as e:
            return {
                "action": "chat",
                "message": f"Не смог обработать запрос: {str(e)[:100]}\nПопробуй ещё раз."
            }

    async def format_daily_plan(self, tasks: List[Dict], habits: List[Dict], user_id: int) -> str:
        if not tasks and not habits:
            return "📅 *На сегодня нет задач и привычек.*\n\nНапиши мне что нужно сделать!"
        try:
            system = "Ты помощник по планированию. Отвечай только готовым текстом без вступлений."
            user = f"""Составь красивый план дня на русском языке в Markdown формате.
Задачи: {json.dumps(tasks, ensure_ascii=False)}
Привычки: {json.dumps(habits, ensure_ascii=False)}
Сегодня: {date.today().isoformat()}, {DAYS_RU[date.today().weekday()]}
Сгруппируй по времени, расставь приоритеты, добавь эмодзи."""
            return ask_groq(system, user)
        except Exception:
            return self._format_plan_simple(tasks, habits)

    def _format_plan_simple(self, tasks: List[Dict], habits: List[Dict]) -> str:
        text = f"📅 *План на {date.today().strftime('%d.%m.%Y')}*\n\n"
        priorities = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        if tasks:
            text += "📋 *Задачи:*\n"
            for t in tasks:
                p = priorities.get(t.get("priority", "medium"), "🟡")
                status = "✅" if t["completed"] else "⬜"
                time_str = f" _{t['scheduled_time']}_" if t.get("scheduled_time") else ""
                text += f"{status} {p} {t['title']}{time_str}\n"
        if habits:
            text += "\n💪 *Привычки:*\n"
            for h in habits:
                status = "✅" if h.get("done_today") else "⬜"
                text += f"{status} {h['name']}"
                if h.get("scheduled_time"):
                    text += f" _{h['scheduled_time']}_"
                text += "\n"
        return text

    async def generate_morning_summary(self, tasks: List[Dict], habits: List[Dict], user_id: int) -> str:
        try:
            system = "Ты дружелюбный помощник. Пиши тепло и мотивирующе."
            user = f"""Сгенерируй утреннее резюме для пользователя.
Сегодня: {date.today().isoformat()}, {DAYS_RU[date.today().weekday()]}
Задачи: {json.dumps(tasks, ensure_ascii=False)}
Привычки: {json.dumps(habits, ensure_ascii=False)}
Включи: приветствие, обзор задач, напоминание о привычках, мотивирующую фразу. Используй эмодзи и Markdown."""
            return ask_groq(system, user)
        except Exception:
            return f"🌅 *Доброе утро!*\n\n📋 У тебя {len(tasks)} задач и {len(habits)} привычек на сегодня.\n\n✨ Отличного продуктивного дня!"

    async def generate_evening_summary(self, completed: List[Dict], pending: List[Dict], habits_done: List[Dict], user_id: int) -> str:
        try:
            system = "Ты поддерживающий помощник. Пиши без осуждения, с теплотой."
            user = f"""Сгенерируй вечернее резюме дня.
Выполнено: {json.dumps(completed, ensure_ascii=False)}
Не выполнено: {json.dumps(pending, ensure_ascii=False)}
Привычки выполнены: {json.dumps(habits_done, ensure_ascii=False)}
Включи: что сделано, статус привычек, позитивное завершение. Используй эмодзи и Markdown."""
            return ask_groq(system, user)
        except Exception:
            return f"🌙 *Итоги дня*\n\n✅ Выполнено: {len(completed)} задач\n📌 Не завершено: {len(pending)} задач\n\n🌟 Отдыхай!"

    async def format_weekly_report(self, stats: Dict, user_id: int) -> str:
        try:
            system = "Ты аналитик продуктивности. Будь конкретным с цифрами."
            user = f"""Составь недельный отчёт о продуктивности.
Статистика: {json.dumps(stats, ensure_ascii=False)}
Включи: общую статистику, прогресс привычек, достижения, рекомендации. Используй эмодзи и Markdown."""
            return ask_groq(system, user)
        except Exception:
            rate = stats.get("completion_rate", 0)
            return f"📊 *Статистика за неделю*\n\n✅ Выполнено: {stats.get('completed_tasks', 0)}/{stats.get('total_tasks', 0)} задач\n📈 Эффективность: {rate}%"

    async def parse_reschedule(self, text: str, tasks: List[Dict]) -> Dict:
        try:
            system = "Разбери запрос на перенос задачи. Верни ТОЛЬКО валидный JSON без пояснений."
            user = f"""Сообщение: {text}
Задачи: {json.dumps([{{"idx": i+1, "id": t["id"], "title": t["title"]}} for i, t in enumerate(tasks)], ensure_ascii=False)}
Сегодня: {date.today().isoformat()}
Верни JSON: {{"success": true/false, "task_id": ID, "task_title": "название", "new_datetime": "YYYY-MM-DD HH:MM", "new_datetime_str": "читаемая дата"}}"""
            raw = ask_groq(system, user)
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```")
            return json.loads(raw)
        except Exception:
            return {"success": False}
