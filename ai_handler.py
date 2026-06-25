import sqlite3
import json
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional


class Database:
    def __init__(self, db_path: str = "secretary.db"):
        self.db_path = db_path
        self.init_db()

    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT,
                    last_location TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    title TEXT NOT NULL,
                    description TEXT,
                    priority TEXT DEFAULT 'medium',
                    location TEXT,
                    scheduled_date TEXT,
                    scheduled_time TEXT,
                    remind_at TEXT,
                    completed INTEGER DEFAULT 0,
                    completed_at TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    name TEXT NOT NULL,
                    description TEXT,
                    scheduled_time TEXT,
                    duration_minutes INTEGER,
                    days_of_week TEXT DEFAULT '1,2,3,4,5,6,7',
                    current_streak INTEGER DEFAULT 0,
                    longest_streak INTEGER DEFAULT 0,
                    active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS habit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit_id INTEGER,
                    user_id INTEGER,
                    completed_date TEXT,
                    completed_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (habit_id) REFERENCES habits(id)
                );

                CREATE TABLE IF NOT EXISTS locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    name TEXT,
                    address TEXT,
                    last_visited TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
            """)

    def ensure_user(self, user_id: int, name: str):
        with self.get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, name) VALUES (?, ?)",
                (user_id, name)
            )

    def get_all_users(self) -> List[Dict]:
        with self.get_conn() as conn:
            rows = conn.execute("SELECT * FROM users").fetchall()
            return [dict(r) for r in rows]

    def get_user_context(self, user_id: int) -> Dict:
        with self.get_conn() as conn:
            user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            tasks = conn.execute(
                "SELECT * FROM tasks WHERE user_id=? AND scheduled_date=? AND completed=0",
                (user_id, date.today().isoformat())
            ).fetchall()
            habits = conn.execute(
                "SELECT * FROM habits WHERE user_id=? AND active=1", (user_id,)
            ).fetchall()
            return {
                "user": dict(user) if user else {},
                "today_tasks": [dict(t) for t in tasks],
                "habits": [dict(h) for h in habits],
                "last_location": user["last_location"] if user else None
            }

    def add_task(self, user_id: int, data: Dict) -> int:
        with self.get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO tasks
                   (user_id, title, description, priority, location,
                    scheduled_date, scheduled_time, remind_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    data.get("title", "Задача"),
                    data.get("description"),
                    data.get("priority", "medium"),
                    data.get("location"),
                    data.get("scheduled_date", date.today().isoformat()),
                    data.get("scheduled_time"),
                    data.get("remind_at"),
                )
            )
            return cursor.lastrowid

    def add_habit(self, user_id: int, data: Dict):
        with self.get_conn() as conn:
            conn.execute(
                """INSERT INTO habits
                   (user_id, name, description, scheduled_time, duration_minutes, days_of_week)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    data.get("name", "Привычка"),
                    data.get("description"),
                    data.get("scheduled_time"),
                    data.get("duration_minutes"),
                    data.get("days_of_week", "1,2,3,4,5,6,7"),
                )
            )

    def get_today_tasks(self, user_id: int, incomplete_only: bool = False) -> List[Dict]:
        with self.get_conn() as conn:
            query = "SELECT * FROM tasks WHERE user_id=? AND scheduled_date=?"
            params = [user_id, date.today().isoformat()]
            if incomplete_only:
                query += " AND completed=0"
            query += " ORDER BY scheduled_time ASC NULLS LAST"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_today_habits(self, user_id: int) -> List[Dict]:
        today_weekday = str(date.today().isoweekday())
        with self.get_conn() as conn:
            habits = conn.execute(
                "SELECT * FROM habits WHERE user_id=? AND active=1", (user_id,)
            ).fetchall()
            result = []
            for h in habits:
                days = h["days_of_week"].split(",")
                if today_weekday in days:
                    # Check if done today
                    done = conn.execute(
                        "SELECT id FROM habit_logs WHERE habit_id=? AND completed_date=?",
                        (h["id"], date.today().isoformat())
                    ).fetchone()
                    h_dict = dict(h)
                    h_dict["done_today"] = done is not None
                    result.append(h_dict)
            return result

    def get_habits(self, user_id: int) -> List[Dict]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM habits WHERE user_id=? AND active=1 ORDER BY scheduled_time",
                (user_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def complete_task(self, task_id: int):
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE tasks SET completed=1, completed_at=datetime('now') WHERE id=?",
                (task_id,)
            )

    def reschedule_task(self, task_id: int, new_datetime: str):
        parts = new_datetime.split(" ")
        new_date = parts[0] if len(parts) > 0 else date.today().isoformat()
        new_time = parts[1] if len(parts) > 1 else None
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE tasks SET scheduled_date=?, scheduled_time=? WHERE id=?",
                (new_date, new_time, task_id)
            )

    def complete_habit(self, habit_id: int, user_id: int):
        today = date.today().isoformat()
        with self.get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM habit_logs WHERE habit_id=? AND completed_date=?",
                (habit_id, today)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO habit_logs (habit_id, user_id, completed_date) VALUES (?, ?, ?)",
                    (habit_id, user_id, today)
                )
                # Update streak
                yesterday = (date.today() - timedelta(days=1)).isoformat()
                yesterday_done = conn.execute(
                    "SELECT id FROM habit_logs WHERE habit_id=? AND completed_date=?",
                    (habit_id, yesterday)
                ).fetchone()
                if yesterday_done:
                    conn.execute(
                        "UPDATE habits SET current_streak=current_streak+1 WHERE id=?",
                        (habit_id,)
                    )
                else:
                    conn.execute(
                        "UPDATE habits SET current_streak=1 WHERE id=?",
                        (habit_id,)
                    )
                # Update longest streak
                conn.execute(
                    """UPDATE habits SET longest_streak=MAX(longest_streak, current_streak)
                       WHERE id=?""",
                    (habit_id,)
                )

    def get_completed_today(self, user_id: int) -> List[Dict]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE user_id=? AND scheduled_date=? AND completed=1",
                (user_id, date.today().isoformat())
            ).fetchall()
            return [dict(r) for r in rows]

    def get_habits_completed_today(self, user_id: int) -> List[Dict]:
        today = date.today().isoformat()
        with self.get_conn() as conn:
            rows = conn.execute(
                """SELECT h.* FROM habits h
                   JOIN habit_logs hl ON h.id=hl.habit_id
                   WHERE hl.user_id=? AND hl.completed_date=?""",
                (user_id, today)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_weekly_stats(self, user_id: int) -> Dict:
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        today = date.today().isoformat()
        with self.get_conn() as conn:
            total_tasks = conn.execute(
                "SELECT COUNT(*) as cnt FROM tasks WHERE user_id=? AND scheduled_date BETWEEN ? AND ?",
                (user_id, week_ago, today)
            ).fetchone()["cnt"]

            completed_tasks = conn.execute(
                """SELECT COUNT(*) as cnt FROM tasks
                   WHERE user_id=? AND scheduled_date BETWEEN ? AND ? AND completed=1""",
                (user_id, week_ago, today)
            ).fetchone()["cnt"]

            habits = conn.execute(
                "SELECT h.*, COUNT(hl.id) as completions FROM habits h "
                "LEFT JOIN habit_logs hl ON h.id=hl.habit_id AND hl.completed_date BETWEEN ? AND ? "
                "WHERE h.user_id=? AND h.active=1 GROUP BY h.id",
                (week_ago, today, user_id)
            ).fetchall()

            return {
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "completion_rate": round(completed_tasks / max(total_tasks, 1) * 100),
                "habits": [dict(h) for h in habits],
                "week_ago": week_ago,
                "today": today,
            }

    def update_last_location(self, user_id: int, location: str):
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE users SET last_location=? WHERE user_id=?",
                (location, user_id)
            )

    def get_last_location(self, user_id: int) -> Optional[str]:
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT last_location FROM users WHERE user_id=?", (user_id,)
            ).fetchone()
            return row["last_location"] if row else None

    def get_tasks_by_date(self, user_id: int, target_date: str) -> List[Dict]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE user_id=? AND scheduled_date=? ORDER BY scheduled_time ASC NULLS LAST",
                (user_id, target_date)
            ).fetchall()
            return [dict(r) for r in rows]
