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


def _infer_goal_direction(metric: Optional[str], delta_kg: Optional[float]) -> str:
    """Return 'cut' | 'maintain' | 'bulk' | 'muscle-gain' based on goal metric+delta."""
    if delta_kg is None or abs(delta_kg) < 0.5:
        return "maintain"
    if metric == "skeletal_muscle_kg" and delta_kg > 0:
        return "muscle-gain"
    if delta_kg < 0:
        return "cut"
    return "bulk"


def compute_macro_targets(target_kcal: float, body_weight_kg: float, direction: str) -> dict:
    """Split target_kcal into protein/carbs/fat grams using standard guidelines.

    Per-kg-bodyweight protein and fat are fixed by direction; carbs absorb the
    remaining calories. Protein 4 kcal/g, carbs 4 kcal/g, fat 9 kcal/g.

    Direction presets:
      - cut: protein 2.0 g/kg (muscle preservation), fat 0.8 g/kg
      - maintain: protein 1.6 g/kg, fat 0.9 g/kg
      - bulk: protein 2.0 g/kg, fat 1.0 g/kg
      - muscle-gain: protein 2.2 g/kg, fat 0.9 g/kg
    """
    presets = {
        "cut":         (2.0, 0.8),
        "maintain":    (1.6, 0.9),
        "bulk":        (2.0, 1.0),
        "muscle-gain": (2.2, 0.9),
    }
    p_per_kg, f_per_kg = presets.get(direction, presets["maintain"])

    protein_g = max(0, round(p_per_kg * body_weight_kg))
    fat_g = max(0, round(f_per_kg * body_weight_kg))
    protein_kcal = protein_g * 4
    fat_kcal = fat_g * 9
    carb_kcal_remaining = max(0.0, target_kcal - protein_kcal - fat_kcal)
    carbs_g = max(0, round(carb_kcal_remaining / 4))
    carbs_kcal = carbs_g * 4

    total_kcal = protein_kcal + fat_kcal + carbs_kcal or 1
    return {
        "direction": direction,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "protein_kcal": protein_kcal,
        "carbs_kcal": carbs_kcal,
        "fat_kcal": fat_kcal,
        "protein_pct": round(protein_kcal / total_kcal * 100, 1),
        "carbs_pct": round(carbs_kcal / total_kcal * 100, 1),
        "fat_pct": round(fat_kcal / total_kcal * 100, 1),
    }


def compute_target_kcal_detailed(user_id: int, date: str) -> dict:
    """Compute daily calorie intake target from the user's primary goal + InBody.

    Method:
      1. If /plan generated today's daily_plans row → use that directly
      2. Else if InBody BMR available:
         - TDEE = BMR × 1.45 (moderate activity)
         - From primary goal: compute required body change (kg of fat / muscle / weight)
         - Required daily kcal delta = (delta_kg × kcal_per_kg) / days_remaining
           - 1 kg fat ≈ 7700 kcal, 1 kg lean mass ≈ 5500 kcal (estimate)
         - target_kcal = TDEE + daily_delta, clamped to [max(BMR, 1200), TDEE + 800]
      3. Else (no BMR): None

    Returns dict with keys:
      - target_kcal: float or None
      - source: 'plan' | 'goal-derived' | 'maintain-tdee' | 'none'
      - bmr, tdee, days_left, current_value, target_value, metric, delta_kg,
        daily_delta_kcal, weekly_delta_kg, reasoning_md (human-readable HTML)
    """
    result: dict = {
        "target_kcal": None,
        "source": "none",
        "bmr": None,
        "tdee": None,
        "days_left": None,
        "current_value": None,
        "target_value": None,
        "metric": None,
        "delta_kg": None,
        "daily_delta_kcal": None,
        "weekly_delta_kg": None,
        "reasoning_md": "",
        "macros": None,
    }

    plan = get_daily_plan(user_id, date)
    latest = get_latest_inbody(user_id)
    body_weight = (latest or {}).get("weight_kg") if latest else None

    if plan and plan.get("target_kcal_intake"):
        result["target_kcal"] = float(plan["target_kcal_intake"])
        result["source"] = "plan"
        result["reasoning_md"] = "오늘자 /plan에서 산출한 목표를 사용 중입니다."
        if body_weight:
            # We don't know plan-time direction; assume maintain unless primary goal exists
            pg = get_primary_goal(user_id)
            d = _infer_goal_direction(pg.get("metric") if pg else None,
                                       (float(pg["target_value"]) - float(pg["start_value"]))
                                       if (pg and pg.get("start_value") is not None) else None)
            result["macros"] = compute_macro_targets(result["target_kcal"], float(body_weight), d)
        return result

    bmr = (latest or {}).get("bmr_kcal") if latest else None
    if not bmr:
        result["reasoning_md"] = "BMR 정보가 없어서 목표 칼로리를 계산할 수 없습니다. /inbody로 인바디 사진을 등록해주세요."
        return result

    bmr = float(bmr)
    tdee = bmr * 1.45
    result["bmr"] = bmr
    result["tdee"] = tdee

    primary = get_primary_goal(user_id)
    if not primary:
        result["target_kcal"] = tdee
        result["source"] = "maintain-tdee"
        result["reasoning_md"] = f"활성 주 목표가 없어 유지 칼로리(TDEE) {int(tdee)} kcal로 설정. /goal로 목표를 추가하면 자동 조정됩니다."
        if body_weight:
            result["macros"] = compute_macro_targets(tdee, float(body_weight), "maintain")
        return result

    # Days remaining
    try:
        target_dt = datetime.strptime(primary["target_date"], "%Y-%m-%d").date()
        today_dt = datetime.strptime(date, "%Y-%m-%d").date()
        days_left = max(1, (target_dt - today_dt).days)
    except Exception:
        days_left = 30
    result["days_left"] = days_left

    metric = primary["metric"]
    target_val = float(primary["target_value"])
    result["metric"] = metric
    result["target_value"] = target_val

    # Current value — prefer latest InBody, fallback to goal start_value
    current_val = latest.get(metric) if latest else None
    if current_val is None and metric == "weight":
        current_val = latest.get("weight_kg") if latest else None
    if current_val is None:
        current_val = primary.get("start_value")
    if current_val is None:
        result["target_kcal"] = tdee
        result["source"] = "maintain-tdee"
        result["reasoning_md"] = "현재 수치를 알 수 없어 유지 칼로리를 사용합니다. 최신 인바디를 등록해주세요."
        if body_weight:
            result["macros"] = compute_macro_targets(tdee, float(body_weight), "maintain")
        return result
    current_val = float(current_val)
    result["current_value"] = current_val

    # Compute kg-change to achieve + kcal/kg coefficient
    KCAL_PER_KG_FAT = 7700.0
    KCAL_PER_KG_MUSCLE = 5500.0
    delta_kg = 0.0
    kcal_per_kg = KCAL_PER_KG_FAT

    if metric == "weight":
        delta_kg = target_val - current_val
        # Mostly fat change for cut/bulk in this context
        kcal_per_kg = KCAL_PER_KG_FAT
    elif metric == "body_fat_pct":
        current_weight = (latest or {}).get("weight_kg")
        if not current_weight:
            result["target_kcal"] = tdee
            result["source"] = "maintain-tdee"
            result["reasoning_md"] = "체지방률 목표는 체중 정보가 필요합니다. /setweight 또는 인바디로 등록해주세요."
            if body_weight:
                result["macros"] = compute_macro_targets(tdee, float(body_weight), "maintain")
            return result
        cw = float(current_weight)
        current_fat_kg = cw * current_val / 100.0
        target_fat_kg = cw * target_val / 100.0
        delta_kg = target_fat_kg - current_fat_kg
        kcal_per_kg = KCAL_PER_KG_FAT
    elif metric == "body_fat_kg":
        delta_kg = target_val - current_val
        kcal_per_kg = KCAL_PER_KG_FAT
    elif metric == "skeletal_muscle_kg":
        delta_kg = target_val - current_val
        kcal_per_kg = KCAL_PER_KG_MUSCLE
    else:
        result["target_kcal"] = tdee
        result["source"] = "maintain-tdee"
        result["reasoning_md"] = "알 수 없는 지표라 유지 칼로리를 사용합니다."
        if body_weight:
            result["macros"] = compute_macro_targets(tdee, float(body_weight), "maintain")
        return result

    result["delta_kg"] = delta_kg
    daily_delta = (delta_kg * kcal_per_kg) / days_left
    result["daily_delta_kcal"] = daily_delta
    result["weekly_delta_kg"] = (delta_kg / days_left) * 7

    target_kcal = tdee + daily_delta

    # Sanity clamps — never go below BMR or 1200, never above TDEE + 800
    floor = max(bmr, 1200.0)
    ceiling = tdee + 800.0
    clamped = max(floor, min(ceiling, target_kcal))
    was_clamped = abs(clamped - target_kcal) > 1
    result["target_kcal"] = clamped
    result["source"] = "goal-derived"

    # Compute macros from goal direction + body weight
    inferred_dir = _infer_goal_direction(metric, delta_kg)
    bw_for_macros = (latest or {}).get("weight_kg") or body_weight
    if bw_for_macros:
        result["macros"] = compute_macro_targets(clamped, float(bw_for_macros), inferred_dir)

    # Human-readable reasoning
    metric_labels = {
        "weight": ("체중", "kg"),
        "body_fat_pct": ("체지방률", "%"),
        "body_fat_kg": ("체지방량", "kg"),
        "skeletal_muscle_kg": ("골격근량", "kg"),
    }
    lbl, unit = metric_labels.get(metric, (metric, ""))
    direction_label = "감량" if delta_kg < 0 else ("증량" if delta_kg > 0 else "유지")
    weekly = abs(result["weekly_delta_kg"])
    parts = [
        f"BMR <b>{int(bmr)}</b> · TDEE(중강도 활동) <b>{int(tdee)}</b> kcal",
        f"주 목표: {lbl} <b>{current_val}{unit}</b> → <b>{target_val}{unit}</b> by {primary['target_date']} (D-{days_left})",
        f"필요 변화: <b>{delta_kg:+.2f} kg</b> ({direction_label}, 주 {weekly:.2f} kg)",
        f"하루 칼로리 조정: <b>{int(daily_delta):+d}</b> kcal → 목표 섭취 <b>{int(clamped)}</b> kcal",
    ]
    if was_clamped:
        parts.append(f"<i>(안전 범위 [{int(floor)}, {int(ceiling)}]로 보정됨 — 목표가 너무 공격적입니다)</i>")
    if result.get("macros") and bw_for_macros:
        m = result["macros"]
        dir_label = {"cut": "감량", "maintain": "유지", "bulk": "증량", "muscle-gain": "근비대"}.get(m["direction"], m["direction"])
        parts.append(
            f"매크로 비율 ({dir_label}, 체중 {bw_for_macros}kg 기준): "
            f"단백 <b>{m['protein_g']}g</b> ({m['protein_pct']}%) · "
            f"탄수 <b>{m['carbs_g']}g</b> ({m['carbs_pct']}%) · "
            f"지방 <b>{m['fat_g']}g</b> ({m['fat_pct']}%)"
        )
    result["reasoning_md"] = "\n".join(parts)

    return result


def estimate_daily_target_kcal(user_id: int, date: str) -> tuple:
    """Backward-compat wrapper. Returns (target_kcal_or_None, source_label)."""
    d = compute_target_kcal_detailed(user_id, date)
    return d.get("target_kcal"), d.get("source", "none")


def compute_deficit_progress(user_id: int, today: str) -> dict:
    """Track cumulative calorie-deficit progress toward the primary goal.

    Concept:
      - Reaching a weight/fat goal requires a total energy deficit
        (delta_kg × kcal_per_kg). Spread over the goal window, that is a
        required daily deficit (total_deficit / total_days).
      - "Should-have-achieved by now" = daily_target × days_elapsed.
      - "Actually achieved" = Σ over logged days of
            (TDEE + exercise_kcal − intake_kcal).
        Only days that have at least one logged meal count as measured,
        since intake is unknown otherwise.

    Returns dict with keys:
      available (bool), reason (str when unavailable),
      metric, direction ('deficit'|'surplus'), unit,
      current_value, target_value, tdee,
      total_needed, daily_target, total_days, days_elapsed, days_left,
      target_cumulative, actual_cumulative, achievement_pct,
      exercise_total, measured_days, rows (recent per-day breakdown).
    """
    from datetime import date as _date, timedelta

    result = {"available": False, "reason": "", "rows": []}

    primary = get_primary_goal(user_id)
    if not primary:
        result["reason"] = "활성 주 목표가 없습니다. /goal로 목표를 추가하세요."
        return result

    latest = get_latest_inbody(user_id)
    bmr = (latest or {}).get("bmr_kcal") if latest else None
    if not bmr:
        result["reason"] = "BMR 정보가 없어 계산할 수 없습니다. /inbody로 인바디를 등록하세요."
        return result
    bmr = float(bmr)
    tdee = bmr * 1.45

    metric = primary["metric"]
    target_val = float(primary["target_value"])

    # Current value — latest InBody, fallback to goal start_value
    current_val = latest.get(metric) if latest else None
    if current_val is None and metric == "weight":
        current_val = latest.get("weight_kg") if latest else None
    if current_val is None:
        current_val = primary.get("start_value")
    if current_val is None:
        result["reason"] = "현재 수치를 알 수 없습니다. 최신 인바디를 등록하세요."
        return result
    current_val = float(current_val)

    # kg-change to achieve + kcal/kg coefficient (mirror compute_target_kcal_detailed)
    KCAL_PER_KG_FAT = 7700.0
    KCAL_PER_KG_MUSCLE = 5500.0
    if metric == "weight":
        delta_kg = target_val - current_val
        kcal_per_kg = KCAL_PER_KG_FAT
    elif metric == "body_fat_pct":
        cw = (latest or {}).get("weight_kg")
        if not cw:
            result["reason"] = "체지방률 목표는 체중 정보가 필요합니다."
            return result
        cw = float(cw)
        delta_kg = (cw * target_val / 100.0) - (cw * current_val / 100.0)
        kcal_per_kg = KCAL_PER_KG_FAT
    elif metric == "body_fat_kg":
        delta_kg = target_val - current_val
        kcal_per_kg = KCAL_PER_KG_FAT
    elif metric == "skeletal_muscle_kg":
        delta_kg = target_val - current_val
        kcal_per_kg = KCAL_PER_KG_MUSCLE
    else:
        result["reason"] = "이 지표는 칼로리 적자 추적을 지원하지 않습니다."
        return result

    total_needed = abs(delta_kg) * kcal_per_kg  # positive magnitude
    direction = "surplus" if delta_kg > 0 else "deficit"

    # Goal window: created_at → target_date
    try:
        start_dt = datetime.fromisoformat(primary["created_at"]).date()
    except Exception:
        start_dt = None
    try:
        target_dt = datetime.strptime(primary["target_date"], "%Y-%m-%d").date()
    except Exception:
        target_dt = None
    try:
        today_dt = datetime.strptime(today, "%Y-%m-%d").date()
    except Exception:
        today_dt = _date.today()

    if not start_dt or not target_dt:
        result["reason"] = "목표 기간 정보가 올바르지 않습니다."
        return result

    total_days = max(1, (target_dt - start_dt).days)
    days_elapsed = max(0, min(total_days, (today_dt - start_dt).days))
    days_left = max(0, (target_dt - today_dt).days)
    daily_target = total_needed / total_days

    # Signed daily contribution: for a deficit goal, positive deficit helps;
    # for a surplus goal, positive surplus helps.
    sign = 1.0 if direction == "deficit" else -1.0

    lbl, unit = GOAL_METRICS.get(metric, (metric, ""))

    # Aggregate intake + exercise per day over [start, today]
    conn = get_conn()
    start_s = start_dt.isoformat()
    today_s = today_dt.isoformat()
    meal_rows = conn.execute(
        """SELECT date, SUM(COALESCE(estimated_kcal,0)) AS kcal, COUNT(*) AS n
           FROM meals WHERE user_id=? AND date>=? AND date<=? GROUP BY date""",
        (user_id, start_s, today_s),
    ).fetchall()
    ex_rows = conn.execute(
        """SELECT date, SUM(COALESCE(estimated_kcal,0)) AS kcal
           FROM records WHERE user_id=? AND date>=? AND date<=? GROUP BY date""",
        (user_id, start_s, today_s),
    ).fetchall()
    conn.close()

    intake_by_day = {r["date"]: (r["kcal"] or 0.0, r["n"]) for r in meal_rows}
    exercise_by_day = {r["date"]: (r["kcal"] or 0.0) for r in ex_rows}

    exercise_total = sum(exercise_by_day.values())
    actual_cumulative = 0.0
    measured_days = 0
    rows = []
    # Iterate each logged-meal day (intake known); ascending
    for i in range(days_elapsed + 1):
        d = start_dt + timedelta(days=i)
        ds = d.isoformat()
        if ds not in intake_by_day:
            continue
        intake, _n = intake_by_day[ds]
        exercise = exercise_by_day.get(ds, 0.0)
        day_deficit = tdee + exercise - intake  # positive = ate below expenditure
        signed = day_deficit * sign
        actual_cumulative += signed
        measured_days += 1
        rows.append({
            "date": ds,
            "intake": round(intake),
            "exercise": round(exercise),
            "tdee": round(tdee),
            "day_deficit": round(signed),
            "target_daily": round(daily_target),
            "met": signed >= daily_target,
        })

    rows = rows[-14:]  # recent 14 measured days
    target_cumulative = daily_target * days_elapsed
    achievement_pct = (
        round(actual_cumulative / target_cumulative * 100, 1)
        if target_cumulative > 0 else None
    )

    result.update({
        "available": True,
        "metric": metric,
        "label": lbl,
        "unit": unit,
        "direction": direction,
        "current_value": current_val,
        "target_value": target_val,
        "delta_kg": round(delta_kg, 2),
        "tdee": round(tdee),
        "total_needed": round(total_needed),
        "daily_target": round(daily_target),
        "total_days": total_days,
        "days_elapsed": days_elapsed,
        "days_left": days_left,
        "target_cumulative": round(target_cumulative),
        "actual_cumulative": round(actual_cumulative),
        "achievement_pct": achievement_pct,
        "exercise_total": round(exercise_total),
        "measured_days": measured_days,
        "target_date": primary["target_date"],
        "rows": rows,
    })
    return result


def get_scoreboard_chats() -> list[int]:
    """Group chats eligible for the nightly scoreboard: any chat with 2+ tracked
    members (real coach/client groups, not solo DMs)."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT chat_id FROM group_members
           GROUP BY chat_id HAVING COUNT(*) >= 2""",
    ).fetchall()
    conn.close()
    return [r["chat_id"] for r in rows]


def _consecutive_streak(log_dates: set, today_dt) -> int:
    """Count consecutive days ending at (or the day before) today that have a log."""
    from datetime import timedelta
    streak = 0
    d = today_dt
    # Allow the streak to still count if nothing logged *today* yet but yesterday was.
    if d.isoformat() not in log_dates:
        d = d - timedelta(days=1)
    while d.isoformat() in log_dates:
        streak += 1
        d = d - timedelta(days=1)
    return streak


def get_group_scoreboard(chat_id: int, date: str) -> dict:
    """Build the nightly ranked accountability scoreboard for one group chat.

    Per non-trainer member for `date`:
      - trained_today (bool), meal_logged_today (bool)
      - intake_kcal, target_kcal, kcal_pct (intake/target)
      - exercise_kcal
      - streak (consecutive logged days ending today)
      - goal_pct (progress toward primary goal via latest InBody)
    Rows are ranked: logged-today first, then streak, then goal progress.

    Returns {date, chat_id, rows: [...], any_activity: bool}.
    """
    from datetime import date as _date, timedelta
    try:
        today_dt = datetime.strptime(date, "%Y-%m-%d").date()
    except Exception:
        today_dt = _date.today()

    members = get_group_members(chat_id)
    conn = get_conn()
    rows = []
    for m in members:
        if m.get("is_trainer"):
            continue
        uid = m["user_id"]
        name = m.get("name") or f"회원{uid}"

        trained = conn.execute(
            "SELECT COUNT(*) c FROM records WHERE user_id=? AND date=?",
            (uid, date),
        ).fetchone()["c"] > 0
        ex_kcal = conn.execute(
            "SELECT SUM(estimated_kcal) v FROM records WHERE user_id=? AND date=? AND estimated_kcal IS NOT NULL",
            (uid, date),
        ).fetchone()["v"] or 0
        intake = conn.execute(
            "SELECT SUM(estimated_kcal) v FROM meals WHERE user_id=? AND date=? AND estimated_kcal IS NOT NULL",
            (uid, date),
        ).fetchone()["v"] or 0
        meal_logged = conn.execute(
            "SELECT COUNT(*) c FROM meals WHERE user_id=? AND date=?",
            (uid, date),
        ).fetchone()["c"] > 0

        # streak: distinct dates from records ∪ meals up to today
        log_rows = conn.execute(
            """SELECT date FROM records WHERE user_id=? AND date<=?
               UNION SELECT date FROM meals WHERE user_id=? AND date<=?""",
            (uid, date, uid, date),
        ).fetchall()
        log_dates = {r["date"] for r in log_rows}
        streak = _consecutive_streak(log_dates, today_dt)
        last_log = max(log_dates) if log_dates else None
        if last_log:
            try:
                days_silent = (today_dt - datetime.strptime(last_log, "%Y-%m-%d").date()).days
            except Exception:
                days_silent = None
        else:
            days_silent = None

        # target kcal + goal progress (pure DB, no LLM)
        detail = compute_target_kcal_detailed(uid, date)
        target_kcal = detail.get("target_kcal")
        kcal_pct = round(intake / target_kcal * 100) if (target_kcal and intake) else None

        goal_pct = None
        primary = get_primary_goal(uid)
        if primary and primary.get("start_value") is not None:
            latest = get_latest_inbody(uid)
            cur = (latest or {}).get(primary["metric"]) if latest else None
            if cur is None and primary["metric"] == "weight":
                cur = (latest or {}).get("weight_kg") if latest else None
            if cur is not None:
                try:
                    span = float(primary["target_value"]) - float(primary["start_value"])
                    done = float(cur) - float(primary["start_value"])
                    goal_pct = 100 if span == 0 else max(0, min(100, round(done / span * 100)))
                except Exception:
                    goal_pct = None

        rows.append({
            "user_id": uid,
            "name": name,
            "trained": trained,
            "meal_logged": meal_logged,
            "intake_kcal": round(intake),
            "exercise_kcal": round(ex_kcal),
            "target_kcal": round(target_kcal) if target_kcal else None,
            "kcal_pct": kcal_pct,
            "streak": streak,
            "goal_pct": goal_pct,
            "logged_today": trained or meal_logged,
            "last_log": last_log,
            "days_silent": days_silent,
        })
    conn.close()

    # Rank: logged-today desc, streak desc, goal progress desc, name asc
    rows.sort(key=lambda r: (
        0 if r["logged_today"] else 1,
        -r["streak"],
        -(r["goal_pct"] if r["goal_pct"] is not None else -1),
        r["name"],
    ))
    return {
        "date": date,
        "chat_id": chat_id,
        "rows": rows,
        "any_activity": any(r["logged_today"] for r in rows),
    }


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
