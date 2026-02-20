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
    conn.close()


def upsert_user(user_id: int, chat_id: int, name: str, weight_kg: Optional[float] = None) -> None:
    conn = get_conn()
    existing = conn.execute(
        "SELECT weight_kg FROM users WHERE user_id=? AND chat_id=?",
        (user_id, chat_id),
    ).fetchone()
    if existing:
        if weight_kg is not None:
            conn.execute(
                "UPDATE users SET name=?, weight_kg=? WHERE user_id=? AND chat_id=?",
                (name, weight_kg, user_id, chat_id),
            )
        else:
            conn.execute(
                "UPDATE users SET name=? WHERE user_id=? AND chat_id=?",
                (name, user_id, chat_id),
            )
    else:
        conn.execute(
            "INSERT INTO users (user_id, chat_id, name, weight_kg, created_at) VALUES (?,?,?,?,?)",
            (user_id, chat_id, name, weight_kg, datetime.utcnow().isoformat()),
        )
    conn.commit()
    conn.close()


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
