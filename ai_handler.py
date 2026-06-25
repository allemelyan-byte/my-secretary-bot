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
- "show_plan" — показать план на день (сегодня)
- "show_plan_date" — показать план на конкретную дату
- "travel_time" — узнать время в пути
- "chat" — просто поговорить / дать совет

Формат для add_task:
{{
  "action": "add_task",
  "message": "Подтверждение для пользователя (без markdown)",
  "data": {{
    "title": "Название задачи",
    "description": "Описание",
    "priority": "high/medium/low",
    "location": "Место если есть",
    "scheduled_date": "YYYY-MM-DD",
    "scheduled_time": "HH:MM или null",
    "remind_at": "YYYY-MM-DD HH:MM или null"
  }}
}}

Формат для show_plan_date:
{{
  "action": "show_plan_date",
  "message": "Показываю план на дату",
  "data": {{
    "date": "YYYY-MM-DD"
  }}
}}

Формат для add_habit:
{{
  "action": "add_habit",
  "message": "Подтверждение",
  "data": {{
    "name": "Название",
    "description": "Описание",
    "scheduled_time": "HH:MM",
    "duration_minutes": 60,
    "days_of_week": "1,2,3,4,5,6,7"
  }}
}}

Формат для travel_time:
{{
  "action": "travel_time",
  "message": "Сообщение",
  "data": {{
    "origin": "Откуда",
    "destination": "Куда"
  }}
}}

Формат для chat:
{{
  "action": "chat",
  "message": "Твой ответ (без markdown символов * # **)"
}}

Контекст пользователя:
{user_context}

ВАЖНО:
1. Возвращай ТОЛЬКО валидный JSON без markdown блоков
2. В поле message НИКОГДА не используй * ** # ### — только обычный текст
3. Для дат в будущем (например "2 июля") используй правильный год {year}"""

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


def clean_text(text: str) -> str:
    """Remove markdown symbols that Telegram can't render properly."""
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'\*{3,}', '', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    return text.strip()


class AIHandler:
    def __init__(self):
        pass

    async def process_message(self, text: str, user_id: int, user_data: Dict) -> Dict:
        today = date.today()
        system = SYSTEM_PROMPT.format(
            today=today.isoformat(),
            weekday=DAYS_RU[today.weekday()],
            year=today.year,
            user_context=json.dumps(user_data, ensure_ascii=False, indent=2)
        )
        try:
            raw = ask_groq(system, text)
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```")
            return json.loads(raw)
        except Exception as e:
            return {
                "action": "chat",
                "message": f"Не смог обработать запрос. Попробуй ещё раз."
            }

    async def format_daily_plan(self, tasks: List[Dict], habits: List[Dict], user_id: int, plan_date: str = None) -> str:
        if not tasks and not habits:
            if plan_date:
                return f"На {plan_date} ничего не запланировано."
            return "На сегодня нет задач и привычек.\n\nНапиши или надиктуй мне что нужно сделать!"

        today = date.today()
        date_str = plan_date or today.strftime("%d.%m.%Y")

        try:
            system = "Ты помощник по планированию. Отвечай только готовым текстом без вступлений. НИКОГДА не используй символы * ** # ### в тексте."
            user = f"""Составь план дня на русском языке БЕЗ markdown символов (* # **).
Используй только эмодзи и обычный текст.
Задачи: {json.dumps(tasks, ensure_ascii=False)}
Привычки: {json.dumps(habits, ensure_ascii=False)}
Дата: {date_str}
Сгруппируй по времени, добавь эмодзи."""
            result = ask_groq(system, user)
            return clean_text(result)
        except Exception:
            return self._format_plan_simple(tasks, habits, date_str)

    def _format_plan_simple(self, tasks: List[Dict], habits: List[Dict], date_str: str = None) -> str:
        text = f"📅 План на {date_str or date.today().strftime('%d.%m.%Y')}\n\n"
        priorities = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        if tasks:
            text += "📋 Задачи:\n"
            for t in tasks:
                p = priorities.get(t.get("priority", "medium"), "🟡")
                status = "✅" if t["completed"] else "⬜"
                time_str = f" {t['scheduled_time']}" if t.get("scheduled_time") else ""
                text += f"{status} {p} {t['title']}{time_str}\n"
        if habits:
            text += "\n💪 Привычки:\n"
            for h in habits:
                status = "✅" if h.get("done_today") else "⬜"
                text += f"{status} {h['name']}"
                if h.get("scheduled_time"):
                    text += f" {h['scheduled_time']}"
                text += "\n"
        return text

    async def generate_morning_summary(self, tasks: List[Dict], habits: List[Dict], user_id: int) -> str:
        try:
            system = "Ты дружелюбный помощник. Пиши тепло и мотивирующе. НИКОГДА не используй * ** # ### — только обычный текст и эмодзи."
            user = f"""Сгенерируй утреннее резюме для пользователя.
Сегодня: {date.today().strftime('%d.%m.%Y')}, {DAYS_RU[date.today().weekday()]}
Задачи: {json.dumps(tasks, ensure_ascii=False)}
Привычки: {json.dumps(habits, ensure_ascii=False)}
Включи: приветствие, обзор задач, привычки, мотивирующую фразу. Только обычный текст и эмодзи."""
            result = ask_groq(system, user)
            return clean_text(result)
        except Exception:
            return f"🌅 Доброе утро!\n\n📋 У тебя {len(tasks)} задач и {len(habits)} привычек на сегодня.\n\n✨ Отличного дня!"

    async def generate_evening_summary(self, completed: List[Dict], pending: List[Dict], habits_done: List[Dict], user_id: int) -> str:
        try:
            system = "Ты поддерживающий помощник. НИКОГДА не используй * ** # ### — только обычный текст и эмодзи."
            user = f"""Сгенерируй вечернее резюме дня.
Выполнено: {json.dumps(completed, ensure_ascii=False)}
Не выполнено: {json.dumps(pending, ensure_ascii=False)}
Привычки выполнены: {json.dumps(habits_done, ensure_ascii=False)}
Только обычный текст и эмодзи, никаких * # **."""
            result = ask_groq(system, user)
            return clean_text(result)
        except Exception:
            return f"🌙 Итоги дня\n\n✅ Выполнено: {len(completed)} задач\n📌 Не завершено: {len(pending)} задач\n\n🌟 Отдыхай!"

    async def format_weekly_report(self, stats: Dict, user_id: int) -> str:
        try:
            system = "Ты аналитик продуктивности. НИКОГДА не используй * ** # ### — только обычный текст и эмодзи."
            user = f"""Составь недельный отчёт о продуктивности.
Статистика: {json.dumps(stats, ensure_ascii=False)}
Только обычный текст и эмодзи."""
            result = ask_groq(system, user)
            return clean_text(result)
        except Exception:
            rate = stats.get("completion_rate", 0)
            return f"📊 Статистика за неделю\n\n✅ Выполнено: {stats.get('completed_tasks', 0)}/{stats.get('total_tasks', 0)} задач\n📈 Эффективность: {rate}%"

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
