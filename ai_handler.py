import os
import json
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


SYSTEM_PROMPT = """Ты личный секретарь и помощник. Отвечай на русском языке.
Твоя задача — понять намерение пользователя и вернуть JSON-ответ.

Сегодняшняя дата: {today}
День недели: {weekday}

Возможные действия (поле "action"):
- "add_task" — добавить задачу/встречу/дело
- "add_habit" — добавить регулярную привычку
- "complete_task" — отметить задачу выполненной
- "show_plan" — показать план на день
- "travel_time" — узнать время в пути
- "update_location" — обновить текущее местоположение
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
    "origin": "Откуда (адрес или название)",
    "destination": "Куда (адрес или название)"
  }}
}}

Формат для chat:
{{
  "action": "chat",
  "message": "Твой ответ пользователю в Markdown"
}}

Контекст пользователя:
{user_context}

ВАЖНО: Возвращай ТОЛЬКО валидный JSON без markdown блоков.
"""

DAYS_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда", 3: "Четверг",
    4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}


class AIHandler:
    def __init__(self):
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    async def process_message(self, text: str, user_id: int, user_data: Dict) -> Dict:
        today = date.today()
        prompt = SYSTEM_PROMPT.format(
            today=today.isoformat(),
            weekday=DAYS_RU[today.weekday()],
            user_context=json.dumps(user_data, ensure_ascii=False, indent=2)
        )
        try:
            response = self.model.generate_content(
                f"{prompt}\n\nСообщение пользователя: {text}"
            )
            raw = response.text.strip()
            # Clean markdown code blocks if present
            raw = re.sub(r"```(?:json)?", "", raw).strip()
            return json.loads(raw)
        except Exception as e:
            return {
                "action": "chat",
                "message": f"Понял тебя! Но возникла небольшая ошибка: {str(e)[:100]}\nПопробуй ещё раз."
            }

    async def format_daily_plan(self, tasks: List[Dict], habits: List[Dict], user_id: int) -> str:
        if not tasks and not habits:
            return "📅 *На сегодня нет задач и привычек.*\n\nНапиши мне что нужно сделать!"

        prompt = f"""Составь красивый план дня на русском языке в Markdown формате.
        
Задачи: {json.dumps(tasks, ensure_ascii=False)}
Привычки: {json.dumps(habits, ensure_ascii=False)}
Сегодня: {date.today().isoformat()}, {DAYS_RU[date.today().weekday()]}

Сгруппируй по времени, расставь приоритеты, добавь эмодзи.
Если у задачи есть место — укажи. Напомни про несделанные привычки.
Отвечай ТОЛЬКО готовым текстом плана без вступлений."""

        try:
            response = self.model.generate_content(prompt)
            return response.text
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
        prompt = f"""Сгенерируй мотивирующее утреннее резюме для пользователя.
        
Сегодня: {date.today().isoformat()}, {DAYS_RU[date.today().weekday()]}
Задачи на день: {json.dumps(tasks, ensure_ascii=False)}
Привычки на день: {json.dumps(habits, ensure_ascii=False)}

Включи:
1. 🌅 Тёплое приветствие с датой
2. 📋 Краткий обзор задач (сколько и какие приоритетные)
3. 💪 Напоминание о привычках
4. ✨ Мотивирующая фраза на день

Стиль: тёплый, дружелюбный, краткий. Используй Markdown и эмодзи."""

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception:
            return f"🌅 *Доброе утро!*\n\n📋 У тебя {len(tasks)} задач и {len(habits)} привычек на сегодня.\n\n✨ Отличного продуктивного дня!"

    async def generate_evening_summary(
        self, completed: List[Dict], pending: List[Dict],
        habits_done: List[Dict], user_id: int
    ) -> str:
        prompt = f"""Сгенерируй вечернее резюме дня для пользователя.

Выполнено задач: {json.dumps(completed, ensure_ascii=False)}
Не выполнено: {json.dumps(pending, ensure_ascii=False)}
Привычки выполнены: {json.dumps(habits_done, ensure_ascii=False)}

Включи:
1. 🌙 Тёплое приветствие
2. ✅ Что было сделано сегодня (похвали!)
3. 📌 Что не успел (без упрёков, просто факт)
4. 💪 Статус привычек
5. 🔄 Предложение перенести незавершённые задачи
6. 🌟 Позитивное завершение дня

Стиль: поддерживающий, без осуждения. Используй Markdown и эмодзи."""

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception:
            done_count = len(completed)
            pending_count = len(pending)
            return (
                f"🌙 *Итоги дня*\n\n"
                f"✅ Выполнено: {done_count} задач\n"
                f"📌 Не завершено: {pending_count} задач\n\n"
                f"🌟 Отдыхай, завтра будет новый день!"
            )

    async def format_weekly_report(self, stats: Dict, user_id: int) -> str:
        prompt = f"""Составь детальный недельный отчёт о продуктивности пользователя.

Статистика: {json.dumps(stats, ensure_ascii=False)}

Включи:
1. 📊 Общая статистика (задачи, процент выполнения)
2. 💪 Прогресс по привычкам (серии, выполнение)
3. 🏆 Достижения недели
4. 💡 Рекомендации по улучшению
5. 🎯 Совет на следующую неделю

Будь конкретным с цифрами. Используй Markdown и эмодзи."""

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception:
            rate = stats.get("completion_rate", 0)
            return (
                f"📊 *Статистика за неделю*\n\n"
                f"✅ Выполнено: {stats.get('completed_tasks', 0)}/{stats.get('total_tasks', 0)} задач\n"
                f"📈 Эффективность: {rate}%\n"
            )

    async def parse_reschedule(self, text: str, tasks: List[Dict]) -> Dict:
        prompt = f"""Пользователь хочет перенести задачу. Разбери его сообщение.

Сообщение: {text}
Доступные задачи: {json.dumps([{"idx": i+1, "id": t["id"], "title": t["title"]} for i, t in enumerate(tasks)], ensure_ascii=False)}
Сегодня: {date.today().isoformat()}

Верни JSON:
{{
  "success": true/false,
  "task_id": ID задачи,
  "task_title": "Название",
  "new_datetime": "YYYY-MM-DD HH:MM",
  "new_datetime_str": "читаемая дата"
}}

Только JSON, без markdown."""

        try:
            response = self.model.generate_content(prompt)
            raw = re.sub(r"```(?:json)?", "", response.text).strip()
            return json.loads(raw)
        except Exception:
            return {"success": False}
