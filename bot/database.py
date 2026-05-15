import sqlite3
import os
from datetime import datetime
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", os.path.join("data", "workout.db"))


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            raw_input TEXT,
            structured_md TEXT,
            analysis TEXT,
            estimated_kcal REAL,
            category TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            name TEXT,
            weight_kg REAL,
            height_cm REAL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, chat_id)
        );
        CREATE TABLE IF NOT EXISTS group_members (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            is_trainer BOOLEAN DEFAULT 0,
            added_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS inbody_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            measured_at TEXT NOT NULL,
            weight_kg REAL,
            skeletal_muscle_kg REAL,
            body_fat_kg REAL,
            body_fat_pct REAL,
            bmi REAL,
            bmr_kcal REAL,
            body_water_kg REAL,
            protein_kg REAL,
            mineral_kg REAL,
            visceral_fat_level REAL,
            raw_json TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            metric TEXT NOT NULL,
            start_value REAL,
            target_value REAL NOT NULL,
            target_date TEXT NOT NULL,
            is_primary INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            meal_type TEXT NOT NULL,
            raw_input TEXT,
            structured_md TEXT,
            estimated_kcal REAL,
            protein_g REAL,
            carbs_g REAL,
            fat_g REAL,
            analysis TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS daily_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            target_kcal_intake REAL,
            target_kcal_burn REAL,
            breakfast_suggestion TEXT,
            lunch_suggestion TEXT,
            dinner_suggestion TEXT,
            full_plan TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (user_id, date)
        );
        CREATE TABLE IF NOT EXISTS daily_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            summary_md TEXT,
            goal_assessment_md TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (user_id, date)
        );
    """)
    # Add category column if missing (existing DBs)
    try:
        conn.execute("ALTER TABLE records ADD COLUMN category TEXT")
        conn.commit()
    except Exception:
        pass
    # Add height_cm column if missing
    try:
        conn.execute("ALTER TABLE users ADD COLUMN height_cm REAL")
        conn.commit()
    except Exception:
        pass
    # Add username column if missing
    try:
        conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
        conn.commit()
    except Exception:
        pass
    conn.close()


def upsert_user(user_id: int, chat_id: int, name: str, weight_kg: Optional[float] = None, username: Optional[str] = None) -> None:
    conn = get_conn()
    existing = conn.execute(
        "SELECT weight_kg FROM users WHERE user_id=? AND chat_id=?",
        (user_id, chat_id),
    ).fetchone()
    if existing:
        if weight_kg is not None:
            conn.execute(
                "UPDATE users SET name=?, weight_kg=?, username=? WHERE user_id=? AND chat_id=?",
                (name, weight_kg, username, user_id, chat_id),
            )
        else:
            conn.execute(
                "UPDATE users SET name=?, username=? WHERE user_id=? AND chat_id=?",
                (name, username, user_id, chat_id),
            )
    else:
        conn.execute(
            "INSERT INTO users (user_id, chat_id, name, weight_kg, username, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, chat_id, name, weight_kg, username, datetime.utcnow().isoformat()),
        )
    conn.commit()
    conn.close()


def get_user_by_username(chat_id: int, username: str) -> Optional[dict]:
    """username으로 유저 조회 (@ 제외한 소문자)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT user_id, name, username FROM users WHERE chat_id=? AND LOWER(username)=LOWER(?)",
        (chat_id, username.lstrip("@")),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def set_weight(user_id: int, chat_id: int, weight_kg: float) -> None:
    conn = get_conn()
    existing = conn.execute(
        "SELECT 1 FROM users WHERE user_id=? AND chat_id=?", (user_id, chat_id)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE users SET weight_kg=? WHERE user_id=? AND chat_id=?",
            (weight_kg, user_id, chat_id),
        )
    else:
        conn.execute(
            "INSERT INTO users (user_id, chat_id, name, weight_kg, created_at) VALUES (?,?,?,?,?)",
            (user_id, chat_id, "", weight_kg, datetime.utcnow().isoformat()),
        )
    conn.commit()
    conn.close()


def set_height(user_id: int, chat_id: int, height_cm: float) -> None:
    conn = get_conn()
    existing = conn.execute(
        "SELECT 1 FROM users WHERE user_id=? AND chat_id=?", (user_id, chat_id)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE users SET height_cm=? WHERE user_id=? AND chat_id=?",
            (height_cm, user_id, chat_id),
        )
    else:
        conn.execute(
            "INSERT INTO users (user_id, chat_id, name, height_cm, created_at) VALUES (?,?,?,?,?)",
            (user_id, chat_id, "", height_cm, datetime.utcnow().isoformat()),
        )
    conn.commit()
    conn.close()


def get_user_height(user_id: int, chat_id: int) -> Optional[float]:
    conn = get_conn()
    row = conn.execute(
        "SELECT height_cm FROM users WHERE user_id=? AND chat_id=?",
        (user_id, chat_id),
    ).fetchone()
    conn.close()
    return row["height_cm"] if row and row["height_cm"] else None


def get_user_weight(user_id: int, chat_id: int) -> Optional[float]:
    conn = get_conn()
    row = conn.execute(
        "SELECT weight_kg FROM users WHERE user_id=? AND chat_id=?",
        (user_id, chat_id),
    ).fetchone()
    conn.close()
    return row["weight_kg"] if row and row["weight_kg"] else None


def save_record(
    chat_id: int,
    user_id: int,
    raw_input: str,
    structured_md: str,
    analysis: str,
    estimated_kcal: Optional[float],
    date: Optional[str] = None,
    category: Optional[str] = None,
) -> int:
    conn = get_conn()
    record_date = date or datetime.utcnow().strftime("%Y-%m-%d")
    cur = conn.execute(
        "INSERT INTO records (chat_id, user_id, date, raw_input, structured_md, analysis, estimated_kcal, category, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            chat_id,
            user_id,
            record_date,
            raw_input,
            structured_md,
            analysis,
            estimated_kcal,
            category,
            datetime.utcnow().isoformat(),
        ),
    )
    record_id = cur.lastrowid
    conn.commit()
    conn.close()
    return record_id


def get_today_record(chat_id: int, user_id: int, date: str) -> Optional[dict]:
    """Get existing record for today (same date) to merge with."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM records WHERE chat_id=? AND user_id=? AND date=? ORDER BY created_at DESC LIMIT 1",
        (chat_id, user_id, date),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def merge_record(record_id: int, structured_md: str, analysis: str, estimated_kcal: Optional[float], category: Optional[str] = None) -> None:
    """Update an existing record with merged data."""
    conn = get_conn()
    conn.execute(
        "UPDATE records SET structured_md=?, analysis=?, estimated_kcal=?, category=? WHERE id=?",
        (structured_md, analysis, estimated_kcal, category, record_id),
    )
    conn.commit()
    conn.close()


def delete_record(record_id: int, user_id: int) -> bool:
    """Delete a single record. Returns True if successful."""
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM records WHERE id=?", (record_id,)).fetchone()
    if not row or row["user_id"] != user_id:
        conn.close()
        return False
    conn.execute("DELETE FROM records WHERE id=?", (record_id,))
    conn.commit()
    conn.close()
    return True


def delete_all_records(chat_id: int, user_id: int) -> int:
    """Delete all records for a user in a chat. Returns count deleted."""
    conn = get_conn()
    cur = conn.execute("DELETE FROM records WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


def update_record_date(record_id: int, new_date: str, user_id: int) -> bool:
    """Update the date of a record. Returns True if successful."""
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM records WHERE id=?", (record_id,)).fetchone()
    if not row or row["user_id"] != user_id:
        conn.close()
        return False
    conn.execute("UPDATE records SET date=? WHERE id=?", (new_date, record_id))
    conn.commit()
    conn.close()
    return True


def get_recent_records(chat_id: int, user_id: int, limit: int = 5) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM records WHERE chat_id=? AND user_id=? ORDER BY date DESC, created_at DESC LIMIT ?",
        (chat_id, user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats(chat_id: int, user_id: int) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt, AVG(estimated_kcal) as avg_kcal, SUM(estimated_kcal) as total_kcal FROM records WHERE chat_id=? AND user_id=?",
        (chat_id, user_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else {"cnt": 0, "avg_kcal": 0, "total_kcal": 0}


def get_last_record(chat_id: int, user_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM records WHERE chat_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1",
        (chat_id, user_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Group Members ────────────────────────────────────────────

def add_group_member(chat_id: int, user_id: int, is_trainer: bool = False) -> None:
    conn = get_conn()
    existing = conn.execute(
        "SELECT is_trainer FROM group_members WHERE chat_id=? AND user_id=?",
        (chat_id, user_id),
    ).fetchone()
    if existing:
        # Don't downgrade trainer status
        pass
    else:
        conn.execute(
            "INSERT INTO group_members (chat_id, user_id, is_trainer, added_at) VALUES (?,?,?,?)",
            (chat_id, user_id, int(is_trainer), datetime.utcnow().isoformat()),
        )
        conn.commit()
    conn.close()


def set_trainer(chat_id: int, user_id: int) -> None:
    conn = get_conn()
    existing = conn.execute(
        "SELECT 1 FROM group_members WHERE chat_id=? AND user_id=?",
        (chat_id, user_id),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE group_members SET is_trainer=1 WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        )
    else:
        conn.execute(
            "INSERT INTO group_members (chat_id, user_id, is_trainer, added_at) VALUES (?,?,1,?)",
            (chat_id, user_id, datetime.utcnow().isoformat()),
        )
    conn.commit()
    conn.close()


def unset_trainer(chat_id: int, user_id: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE group_members SET is_trainer=0 WHERE chat_id=? AND user_id=?",
        (chat_id, user_id),
    )
    conn.commit()
    conn.close()


def is_user_trainer(user_id: int) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM group_members WHERE user_id=? AND is_trainer=1 LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return row is not None


def get_trainer_groups(user_id: int) -> list[int]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT chat_id FROM group_members WHERE user_id=? AND is_trainer=1",
        (user_id,),
    ).fetchall()
    conn.close()
    return [r["chat_id"] for r in rows]


def get_user_groups(user_id: int) -> list[int]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT chat_id FROM group_members WHERE user_id=?",
        (user_id,),
    ).fetchall()
    conn.close()
    return [r["chat_id"] for r in rows]


def get_group_members(chat_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT gm.user_id, gm.is_trainer, u.name
           FROM group_members gm
           LEFT JOIN users u ON gm.user_id = u.user_id AND gm.chat_id = u.chat_id
           WHERE gm.chat_id=?""",
        (chat_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_records_for_trainer(user_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT r.*, u.name FROM records r
           LEFT JOIN users u ON r.user_id=u.user_id AND r.chat_id=u.chat_id
           WHERE r.chat_id IN (SELECT chat_id FROM group_members WHERE user_id=? AND is_trainer=1)
           ORDER BY r.created_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_records_for_user(user_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM records WHERE user_id=? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_records_by_month(user_id: int, year: int, month: int) -> list[dict]:
    """Get all records for a user in a given month (across all chats)."""
    date_prefix = f"{year:04d}-{month:02d}"
    conn = get_conn()
    rows = conn.execute(
        "SELECT r.*, u.name FROM records r LEFT JOIN users u ON r.user_id=u.user_id AND r.chat_id=u.chat_id WHERE r.user_id=? AND r.date LIKE ? ORDER BY r.date",
        (user_id, date_prefix + "%"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_records_by_month_for_trainer(user_id: int, year: int, month: int) -> list[dict]:
    """Get records from all trainer's groups for a month."""
    date_prefix = f"{year:04d}-{month:02d}"
    conn = get_conn()
    rows = conn.execute(
        """SELECT r.*, u.name FROM records r
           LEFT JOIN users u ON r.user_id=u.user_id AND r.chat_id=u.chat_id
           WHERE r.chat_id IN (SELECT chat_id FROM group_members WHERE user_id=? AND is_trainer=1)
           AND r.date LIKE ?
           ORDER BY r.date""",
        (user_id, date_prefix + "%"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_trainer_in_chat(user_id: int, chat_id: int) -> bool:
    """Check if user is a trainer in this specific chat."""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM group_members WHERE chat_id=? AND user_id=? AND is_trainer=1",
        (chat_id, user_id),
    ).fetchone()
    conn.close()
    return row is not None


def get_group_clients(chat_id: int) -> list[dict]:
    """Get non-trainer members in a group."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT gm.user_id, u.name
           FROM group_members gm
           LEFT JOIN users u ON gm.user_id = u.user_id AND gm.chat_id = u.chat_id
           WHERE gm.chat_id=? AND gm.is_trainer=0""",
        (chat_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_records_without_category() -> list[dict]:
    """Get records that have no category set."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, structured_md FROM records WHERE category IS NULL AND structured_md IS NOT NULL"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_record_category(record_id: int, category: str) -> None:
    """Update the category of a record."""
    conn = get_conn()
    conn.execute("UPDATE records SET category=? WHERE id=?", (category, record_id))
    conn.commit()
    conn.close()


# ── InBody ───────────────────────────────────────────────────

def save_inbody(
    chat_id: int,
    user_id: int,
    measured_at: str,
    metrics: dict,
    raw_json: str = "",
) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO inbody_records (
            chat_id, user_id, measured_at,
            weight_kg, skeletal_muscle_kg, body_fat_kg, body_fat_pct,
            bmi, bmr_kcal, body_water_kg, protein_kg, mineral_kg, visceral_fat_level,
            raw_json, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            chat_id, user_id, measured_at,
            metrics.get("weight_kg"),
            metrics.get("skeletal_muscle_kg"),
            metrics.get("body_fat_kg"),
            metrics.get("body_fat_pct"),
            metrics.get("bmi"),
            metrics.get("bmr_kcal"),
            metrics.get("body_water_kg"),
            metrics.get("protein_kg"),
            metrics.get("mineral_kg"),
            metrics.get("visceral_fat_level"),
            raw_json,
            datetime.utcnow().isoformat(),
        ),
    )
    inbody_id = cur.lastrowid
    # Also update user's current weight if available
    w = metrics.get("weight_kg")
    if w:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE user_id=? AND chat_id=?", (user_id, chat_id)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET weight_kg=? WHERE user_id=? AND chat_id=?",
                (w, user_id, chat_id),
            )
        else:
            conn.execute(
                "INSERT INTO users (user_id, chat_id, name, weight_kg, created_at) VALUES (?,?,?,?,?)",
                (user_id, chat_id, "", w, datetime.utcnow().isoformat()),
            )
    conn.commit()
    conn.close()
    return inbody_id


def get_latest_inbody(user_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM inbody_records WHERE user_id=? ORDER BY measured_at DESC, created_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_inbody_history(user_id: int, limit: int = 50) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM inbody_records WHERE user_id=? ORDER BY measured_at DESC, created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_inbody(inbody_id: int, user_id: int) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM inbody_records WHERE id=?", (inbody_id,)).fetchone()
    if not row or row["user_id"] != user_id:
        conn.close()
        return False
    conn.execute("DELETE FROM inbody_records WHERE id=?", (inbody_id,))
    conn.commit()
    conn.close()
    return True


# ── Goals ────────────────────────────────────────────────────

GOAL_METRICS = {
    "weight": ("체중", "kg"),
    "body_fat_pct": ("체지방률", "%"),
    "body_fat_kg": ("체지방량", "kg"),
    "skeletal_muscle_kg": ("골격근량", "kg"),
}


def create_goal(
    user_id: int,
    chat_id: int,
    metric: str,
    target_value: float,
    target_date: str,
    start_value: Optional[float] = None,
    is_primary: bool = False,
) -> int:
    conn = get_conn()
    if is_primary:
        conn.execute(
            "UPDATE goals SET is_primary=0 WHERE user_id=? AND status='active'",
            (user_id,),
        )
    cur = conn.execute(
        """INSERT INTO goals (user_id, chat_id, metric, start_value, target_value, target_date, is_primary, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            user_id, chat_id, metric, start_value, target_value, target_date,
            int(is_primary), "active", datetime.utcnow().isoformat(),
        ),
    )
    goal_id = cur.lastrowid
    # Ensure exactly one primary among active goals
    primary_count = conn.execute(
        "SELECT COUNT(*) as c FROM goals WHERE user_id=? AND status='active' AND is_primary=1",
        (user_id,),
    ).fetchone()["c"]
    if primary_count == 0:
        conn.execute("UPDATE goals SET is_primary=1 WHERE id=?", (goal_id,))
    conn.commit()
    conn.close()
    return goal_id


def list_goals(user_id: int, status: str = "active") -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM goals WHERE user_id=? AND status=? ORDER BY is_primary DESC, target_date ASC",
        (user_id, status),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_goal(goal_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_primary_goal(user_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM goals WHERE user_id=? AND status='active' AND is_primary=1 LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def set_primary_goal(goal_id: int, user_id: int) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM goals WHERE id=?", (goal_id,)).fetchone()
    if not row or row["user_id"] != user_id:
        conn.close()
        return False
    conn.execute("UPDATE goals SET is_primary=0 WHERE user_id=?", (user_id,))
    conn.execute("UPDATE goals SET is_primary=1, updated_at=? WHERE id=?",
                 (datetime.utcnow().isoformat(), goal_id))
    conn.commit()
    conn.close()
    return True


def update_goal_status(goal_id: int, user_id: int, status: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM goals WHERE id=?", (goal_id,)).fetchone()
    if not row or row["user_id"] != user_id:
        conn.close()
        return False
    conn.execute(
        "UPDATE goals SET status=?, updated_at=? WHERE id=?",
        (status, datetime.utcnow().isoformat(), goal_id),
    )
    conn.commit()
    conn.close()
    return True


def delete_goal(goal_id: int, user_id: int) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM goals WHERE id=?", (goal_id,)).fetchone()
    if not row or row["user_id"] != user_id:
        conn.close()
        return False
    conn.execute("DELETE FROM goals WHERE id=?", (goal_id,))
    conn.commit()
    conn.close()
    return True


def update_goal(goal_id: int, user_id: int, target_value: Optional[float] = None,
                target_date: Optional[str] = None) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM goals WHERE id=?", (goal_id,)).fetchone()
    if not row or row["user_id"] != user_id:
        conn.close()
        return False
    if target_value is not None:
        conn.execute("UPDATE goals SET target_value=?, updated_at=? WHERE id=?",
                     (target_value, datetime.utcnow().isoformat(), goal_id))
    if target_date is not None:
        conn.execute("UPDATE goals SET target_date=?, updated_at=? WHERE id=?",
                     (target_date, datetime.utcnow().isoformat(), goal_id))
    conn.commit()
    conn.close()
    return True


# ── Meals ────────────────────────────────────────────────────

def save_meal(
    chat_id: int,
    user_id: int,
    date: str,
    meal_type: str,
    raw_input: str,
    structured_md: str,
    estimated_kcal: Optional[float],
    macros: Optional[dict] = None,
    analysis: str = "",
) -> int:
    macros = macros or {}
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO meals (chat_id, user_id, date, meal_type, raw_input, structured_md,
                              estimated_kcal, protein_g, carbs_g, fat_g, analysis, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            chat_id, user_id, date, meal_type, raw_input, structured_md,
            estimated_kcal,
            macros.get("protein_g"),
            macros.get("carbs_g"),
            macros.get("fat_g"),
            analysis,
            datetime.utcnow().isoformat(),
        ),
    )
    meal_id = cur.lastrowid
    conn.commit()
    conn.close()
    return meal_id


def get_meals_for_date(user_id: int, date: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM meals WHERE user_id=? AND date=? ORDER BY created_at ASC",
        (user_id, date),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_meals(user_id: int, limit: int = 30) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM meals WHERE user_id=? ORDER BY date DESC, created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_meal(meal_id: int, user_id: int) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM meals WHERE id=?", (meal_id,)).fetchone()
    if not row or row["user_id"] != user_id:
        conn.close()
        return False
    conn.execute("DELETE FROM meals WHERE id=?", (meal_id,))
    conn.commit()
    conn.close()
    return True


# ── Daily plan / summary ─────────────────────────────────────

def upsert_daily_plan(
    user_id: int,
    chat_id: int,
    date: str,
    target_kcal_intake: Optional[float],
    target_kcal_burn: Optional[float],
    breakfast: str,
    lunch: str,
    dinner: str,
    full_plan: str,
) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO daily_plans (user_id, chat_id, date, target_kcal_intake, target_kcal_burn,
                                    breakfast_suggestion, lunch_suggestion, dinner_suggestion,
                                    full_plan, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(user_id, date) DO UPDATE SET
             target_kcal_intake=excluded.target_kcal_intake,
             target_kcal_burn=excluded.target_kcal_burn,
             breakfast_suggestion=excluded.breakfast_suggestion,
             lunch_suggestion=excluded.lunch_suggestion,
             dinner_suggestion=excluded.dinner_suggestion,
             full_plan=excluded.full_plan""",
        (
            user_id, chat_id, date, target_kcal_intake, target_kcal_burn,
            breakfast, lunch, dinner, full_plan,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_daily_plan(user_id: int, date: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM daily_plans WHERE user_id=? AND date=?",
        (user_id, date),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_daily_summary(
    user_id: int,
    chat_id: int,
    date: str,
    summary_md: str,
    goal_assessment_md: str,
) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO daily_summaries (user_id, chat_id, date, summary_md, goal_assessment_md, created_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(user_id, date) DO UPDATE SET
             summary_md=excluded.summary_md,
             goal_assessment_md=excluded.goal_assessment_md""",
        (
            user_id, chat_id, date, summary_md, goal_assessment_md,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_daily_summary(user_id: int, date: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM daily_summaries WHERE user_id=? AND date=?",
        (user_id, date),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_records_for_date(user_id: int, date: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM records WHERE user_id=? AND date=? ORDER BY created_at ASC",
        (user_id, date),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def estimate_daily_target_kcal(user_id: int, date: str) -> tuple:
    """Returns (target_kcal_or_None, source_str).

    source_str ∈ {"plan", "estimate-cut", "estimate-bulk", "estimate-tdee", "none"}.

    Priority:
      1. daily_plans.target_kcal_intake (set by /plan)
      2. BMR (from latest InBody) × 1.45 with ±500/+300 adjustment based on primary
         goal direction (cut / bulk / maintain)
      3. None if no BMR available
    """
    plan = get_daily_plan(user_id, date)
    if plan and plan.get("target_kcal_intake"):
        return float(plan["target_kcal_intake"]), "plan"

    latest = get_latest_inbody(user_id)
    bmr = (latest or {}).get("bmr_kcal")
    if not bmr:
        return None, "none"

    tdee = float(bmr) * 1.45

    primary = get_primary_goal(user_id)
    if primary and primary.get("start_value") is not None:
        metric = primary["metric"]
        start = float(primary["start_value"])
        target = float(primary["target_value"])
        if metric == "weight":
            if target < start:
                return tdee - 500, "estimate-cut"
            if target > start:
                return tdee + 300, "estimate-bulk"
        elif metric == "body_fat_pct" and target < start:
            return tdee - 500, "estimate-cut"
        elif metric == "skeletal_muscle_kg" and target > start:
            return tdee + 300, "estimate-bulk"

    return tdee, "estimate-tdee"


def get_active_users_recent(days: int = 7) -> list[dict]:
    """Users with any workout/meal/inbody activity in the last N days.
    Returns [{user_id, chat_id}] — uses latest activity's chat_id per user."""
    conn = get_conn()
    cutoff_dt = datetime.utcnow()
    from datetime import timedelta
    cutoff = (cutoff_dt - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        """SELECT user_id, chat_id, MAX(created_at) as latest FROM (
              SELECT user_id, chat_id, created_at FROM records WHERE date >= ?
              UNION ALL
              SELECT user_id, chat_id, created_at FROM meals WHERE date >= ?
              UNION ALL
              SELECT user_id, chat_id, created_at FROM inbody_records WHERE measured_at >= ?
              UNION ALL
              SELECT user_id, chat_id, created_at FROM goals WHERE status='active'
           ) GROUP BY user_id, chat_id
           ORDER BY latest DESC""",
        (cutoff, cutoff, cutoff),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
