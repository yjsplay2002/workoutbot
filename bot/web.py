"""FastAPI web dashboard for workout bot with Telegram auth."""

import calendar as cal_module
import hashlib
import hmac
import os
import sqlite3
from datetime import datetime, date
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Query, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeSerializer
from markupsafe import Markup

from bot.database import (
    delete_record,
    get_all_records_by_month_for_trainer,
    get_all_records_for_trainer,
    get_group_members,
    get_records_by_month,
    get_records_for_user,
    get_records_without_category,
    get_trainer_groups,
    get_user_groups,
    is_user_trainer,
    update_record_category,
    update_record_date,
)
from bot.analyzer import classify_workout, get_category_color

DB_PATH = os.environ.get("DB_PATH", os.path.join("data", "workout.db"))
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WEB_URL = os.environ.get("WEB_URL", "http://localhost:8080")
COOKIE_SECRET = os.environ.get("COOKIE_SECRET", BOT_TOKEN or "dev-secret-key")
COOKIE_NAME = "tg_session"

app = FastAPI(title="운동 대시보드")

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)

serializer = URLSafeSerializer(COOKIE_SECRET)

# Will be set on startup
bot_username: str = ""


@app.on_event("startup")
async def _fetch_bot_username():
    global bot_username
    if not BOT_TOKEN:
        bot_username = "test_bot"
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
            data = resp.json()
            if data.get("ok"):
                bot_username = data["result"]["username"]
    except Exception:
        bot_username = "unknown_bot"

    # Backfill categories for existing records
    try:
        records = get_records_without_category()
        for r in records:
            if r.get("structured_md"):
                cat = classify_workout(r["structured_md"])
                update_record_category(r["id"], cat)
    except Exception:
        pass


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def safe_html(text: Optional[str]) -> Markup:
    if not text:
        return Markup("")
    return Markup(text)


def strip_tags(text: Optional[str]) -> str:
    """Remove HTML tags and return plain text."""
    if not text:
        return ""
    import re
    return re.sub(r'<[^>]+>', '', text)


def nl2br(text: Optional[str]) -> Markup:
    """Convert newlines to <br> while preserving existing HTML tags."""
    if not text:
        return Markup("")
    return Markup(text.replace("\n", "<br>\n"))


templates.env.filters["safe_html"] = safe_html
templates.env.filters["strip_tags"] = strip_tags
templates.env.filters["nl2br"] = nl2br
templates.env.globals["Markup"] = Markup


# ── Auth helpers ─────────────────────────────────────────────

def verify_telegram_auth(data: dict) -> bool:
    """Verify Telegram Login Widget data using HMAC-SHA256."""
    check_hash = data.pop("hash", None)
    if not check_hash:
        return False
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(data.items()) if v
    )
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    data["hash"] = check_hash  # restore
    return hmac.compare_digest(computed, check_hash)


def get_current_user(request: Request) -> Optional[dict]:
    """Read session cookie and return user info or None."""
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    try:
        user_data = serializer.loads(cookie)
        # Enrich with current DB info
        user_id = user_data["user_id"]
        user_data["is_trainer"] = is_user_trainer(user_id)
        user_data["groups"] = get_user_groups(user_id)
        user_data["trainer_groups"] = get_trainer_groups(user_id) if user_data["is_trainer"] else []
        return user_data
    except Exception:
        return None


def require_user(request: Request) -> dict:
    """Dependency that requires authentication."""
    user = get_current_user(request)
    if not user:
        raise RedirectToLogin()
    return user


class RedirectToLogin(Exception):
    pass


@app.exception_handler(RedirectToLogin)
async def _redirect_to_login(request: Request, exc: RedirectToLogin):
    return RedirectResponse("/login", status_code=302)


# ── Auth endpoints ───────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "bot_username": bot_username,
        "web_url": WEB_URL,
    })


@app.get("/auth/telegram")
async def auth_telegram(request: Request):
    params = dict(request.query_params)
    if not verify_telegram_auth(dict(params)):
        return HTMLResponse("<h1>인증 실패</h1><p>텔레그램 인증 데이터가 유효하지 않습니다.</p>", status_code=403)

    user_data = {
        "user_id": int(params["id"]),
        "first_name": params.get("first_name", ""),
        "username": params.get("username", ""),
    }
    cookie_value = serializer.dumps(user_data)
    response = RedirectResponse("/", status_code=302)
    response.set_cookie(COOKIE_NAME, cookie_value, max_age=86400 * 30, httponly=True, samesite="lax")
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ── Public Pages ─────────────────────────────────────────────

@app.get("/policy", response_class=HTMLResponse)
async def policy_page(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("policy.html", {"request": request, "user": user})


# ── HTML Pages ───────────────────────────────────────────────

def _build_calendar_data(records: list[dict], year: int, month: int) -> dict:
    """Build calendar data structure from records. Returns {day: [{record}, ...]}."""
    cal_data = {}
    for r in records:
        try:
            d = r["date"]
            day = int(d.split("-")[2])
            if day not in cal_data:
                cal_data[day] = []
            cal_data[day].append(r)
        except (IndexError, ValueError):
            continue
    return cal_data


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, year: Optional[int] = None, month: Optional[int] = None, user: dict = Depends(require_user)):
    conn = get_conn()
    user_id = user["user_id"]

    # Calendar month
    today = date.today()
    cal_year = year or today.year
    cal_month = month or today.month
    # Clamp
    if cal_month < 1:
        cal_month = 12
        cal_year -= 1
    elif cal_month > 12:
        cal_month = 1
        cal_year += 1

    if user["is_trainer"]:
        trainer_groups = user["trainer_groups"]
        if trainer_groups:
            placeholders = ",".join("?" * len(trainer_groups))
            total = conn.execute(f"SELECT COUNT(*) as c FROM records WHERE chat_id IN ({placeholders})", trainer_groups).fetchone()["c"]
            total_users = conn.execute(f"SELECT COUNT(DISTINCT user_id) as c FROM records WHERE chat_id IN ({placeholders})", trainer_groups).fetchone()["c"]
            avg_kcal = conn.execute(f"SELECT AVG(estimated_kcal) as v FROM records WHERE estimated_kcal IS NOT NULL AND chat_id IN ({placeholders})", trainer_groups).fetchone()["v"]
            total_kcal = conn.execute(f"SELECT SUM(estimated_kcal) as v FROM records WHERE estimated_kcal IS NOT NULL AND chat_id IN ({placeholders})", trainer_groups).fetchone()["v"]
            recent = [dict(r) for r in conn.execute(
                f"SELECT r.*, u.name FROM records r LEFT JOIN users u ON r.user_id=u.user_id AND r.chat_id=u.chat_id WHERE r.chat_id IN ({placeholders}) ORDER BY r.created_at DESC LIMIT 20",
                trainer_groups
            ).fetchall()]
        else:
            total = total_users = 0
            avg_kcal = total_kcal = 0
            recent = []
        cal_records = get_all_records_by_month_for_trainer(user_id, cal_year, cal_month)
    else:
        total = conn.execute("SELECT COUNT(*) as c FROM records WHERE user_id=?", (user_id,)).fetchone()["c"]
        total_users = 1
        avg_kcal = conn.execute("SELECT AVG(estimated_kcal) as v FROM records WHERE estimated_kcal IS NOT NULL AND user_id=?", (user_id,)).fetchone()["v"]
        total_kcal = conn.execute("SELECT SUM(estimated_kcal) as v FROM records WHERE estimated_kcal IS NOT NULL AND user_id=?", (user_id,)).fetchone()["v"]
        recent = [dict(r) for r in conn.execute(
            "SELECT r.*, u.name FROM records r LEFT JOIN users u ON r.user_id=u.user_id AND r.chat_id=u.chat_id WHERE r.user_id=? ORDER BY r.created_at DESC LIMIT 20",
            (user_id,)
        ).fetchall()]
        cal_records = get_records_by_month(user_id, cal_year, cal_month)

    conn.close()

    cal_data = _build_calendar_data(cal_records, cal_year, cal_month)
    # Calendar grid: weeks as list of days (Mon=0)
    first_weekday, num_days = cal_module.monthrange(cal_year, cal_month)
    # first_weekday: 0=Mon, build weeks
    weeks = []
    current_week = [None] * first_weekday
    for day in range(1, num_days + 1):
        current_week.append(day)
        if len(current_week) == 7:
            weeks.append(current_week)
            current_week = []
    if current_week:
        current_week.extend([None] * (7 - len(current_week)))
        weeks.append(current_week)

    # Prev/next month
    if cal_month == 1:
        prev_year, prev_month = cal_year - 1, 12
    else:
        prev_year, prev_month = cal_year, cal_month - 1
    if cal_month == 12:
        next_year, next_month = cal_year + 1, 1
    else:
        next_year, next_month = cal_year, cal_month + 1

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "total_records": total,
        "total_users": total_users,
        "avg_kcal": round(avg_kcal, 1) if avg_kcal else 0,
        "total_kcal": round(total_kcal, 1) if total_kcal else 0,
        "recent": recent,
        "cal_year": cal_year,
        "cal_month": cal_month,
        "cal_weeks": weeks,
        "cal_data": cal_data,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "today_day": today.day if today.year == cal_year and today.month == cal_month else None,
        "get_category_color": get_category_color,
    })


@app.get("/records", response_class=HTMLResponse)
async def records_page(request: Request, date_from: Optional[str] = None, date_to: Optional[str] = None, page: int = 1, user: dict = Depends(require_user)):
    conn = get_conn()
    per_page = 20
    offset = (page - 1) * per_page
    where, params = [], []

    if user["is_trainer"]:
        trainer_groups = user["trainer_groups"]
        if trainer_groups:
            placeholders = ",".join("?" * len(trainer_groups))
            where.append(f"r.chat_id IN ({placeholders})")
            params.extend(trainer_groups)
        else:
            where.append("r.user_id = ?")
            params.append(user["user_id"])
    else:
        where.append("r.user_id = ?")
        params.append(user["user_id"])

    if date_from:
        where.append("r.date >= ?")
        params.append(date_from)
    if date_to:
        where.append("r.date <= ?")
        params.append(date_to)

    where_sql = "WHERE " + " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) as c FROM records r {where_sql}", params).fetchone()["c"]
    rows = [dict(r) for r in conn.execute(
        f"SELECT r.*, u.name FROM records r LEFT JOIN users u ON r.user_id=u.user_id AND r.chat_id=u.chat_id {where_sql} ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()]
    conn.close()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return templates.TemplateResponse("records.html", {
        "request": request,
        "user": user,
        "records": rows,
        "page": page,
        "total_pages": total_pages,
        "date_from": date_from or "",
        "date_to": date_to or "",
    })


@app.get("/records/{record_id}", response_class=HTMLResponse)
async def record_detail(request: Request, record_id: int, user: dict = Depends(require_user)):
    conn = get_conn()
    row = conn.execute(
        "SELECT r.*, u.name FROM records r LEFT JOIN users u ON r.user_id=u.user_id AND r.chat_id=u.chat_id WHERE r.id=?",
        (record_id,)
    ).fetchone()
    conn.close()
    if not row:
        return HTMLResponse("<h1>기록을 찾을 수 없습니다</h1>", status_code=404)

    record = dict(row)
    # Access check
    if record["user_id"] != user["user_id"]:
        if not user["is_trainer"] or record["chat_id"] not in user["trainer_groups"]:
            # Check if same group
            user_groups = set(user["groups"])
            if record["chat_id"] not in user_groups:
                return HTMLResponse("<h1>접근 권한이 없습니다</h1>", status_code=403)

    return templates.TemplateResponse("record_detail.html", {
        "request": request,
        "user": user,
        "record": record,
    })


@app.get("/user/{target_user_id}", response_class=HTMLResponse)
async def user_page(request: Request, target_user_id: int, user: dict = Depends(require_user)):
    # Access check
    if target_user_id != user["user_id"]:
        if user["is_trainer"]:
            # Check if target is in one of trainer's groups
            target_groups = set(get_user_groups(target_user_id))
            trainer_groups = set(user["trainer_groups"])
            if not target_groups & trainer_groups:
                return HTMLResponse("<h1>접근 권한이 없습니다</h1>", status_code=403)
        else:
            return HTMLResponse("<h1>접근 권한이 없습니다</h1>", status_code=403)

    conn = get_conn()
    target_user = conn.execute("SELECT * FROM users WHERE user_id=? LIMIT 1", (target_user_id,)).fetchone()
    records = [dict(r) for r in conn.execute(
        "SELECT * FROM records WHERE user_id=? ORDER BY created_at DESC", (target_user_id,)
    ).fetchall()]
    stats = conn.execute(
        "SELECT COUNT(*) as cnt, AVG(estimated_kcal) as avg_kcal, SUM(estimated_kcal) as total_kcal FROM records WHERE user_id=?",
        (target_user_id,)
    ).fetchone()
    weekly = [dict(r) for r in conn.execute(
        """SELECT strftime('%Y-W%W', date) as week, SUM(estimated_kcal) as kcal, COUNT(*) as cnt
           FROM records WHERE user_id=? AND estimated_kcal IS NOT NULL
           GROUP BY week ORDER BY week DESC LIMIT 8""",
        (target_user_id,)
    ).fetchall()]
    weekly.reverse()
    conn.close()
    return templates.TemplateResponse("user.html", {
        "request": request,
        "user": user,
        "target_user": dict(target_user) if target_user else {"user_id": target_user_id, "name": f"사용자 {target_user_id}", "weight_kg": None},
        "records": records,
        "stats": dict(stats) if stats else {"cnt": 0, "avg_kcal": 0, "total_kcal": 0},
        "weekly": weekly,
    })


@app.get("/trainer", response_class=HTMLResponse)
async def trainer_page(request: Request, user: dict = Depends(require_user)):
    if not user["is_trainer"]:
        return HTMLResponse("<h1>접근 권한이 없습니다</h1><p>트레이너만 접근할 수 있습니다.</p>", status_code=403)

    conn = get_conn()
    today = date.today()
    this_month = today.strftime("%Y-%m")

    clients = []
    seen_user_ids = set()

    for chat_id in user["trainer_groups"]:
        members = get_group_members(chat_id)
        for m in members:
            uid = m["user_id"]
            if m.get("is_trainer") or uid == user["user_id"]:
                continue
            if uid in seen_user_ids:
                continue
            seen_user_ids.add(uid)

            # Stats
            stats = conn.execute(
                """SELECT COUNT(*) as total, MAX(date) as last_date,
                          SUM(estimated_kcal) as total_kcal,
                          AVG(estimated_kcal) as avg_kcal
                   FROM records WHERE user_id=?""",
                (uid,)
            ).fetchone()

            monthly = conn.execute(
                "SELECT COUNT(*) as cnt FROM records WHERE user_id=? AND strftime('%Y-%m', date)=?",
                (uid, this_month)
            ).fetchone()

            # dominant category this month
            cat_row = conn.execute(
                """SELECT category, COUNT(*) as cnt FROM records
                   WHERE user_id=? AND strftime('%Y-%m', date)=? AND category IS NOT NULL
                   GROUP BY category ORDER BY cnt DESC LIMIT 1""",
                (uid, this_month)
            ).fetchone()

            # recent 3 records
            recent = [dict(r) for r in conn.execute(
                "SELECT * FROM records WHERE user_id=? ORDER BY date DESC LIMIT 3",
                (uid,)
            ).fetchall()]

            # weekly sessions (last 8 weeks)
            weekly = [dict(r) for r in conn.execute(
                """SELECT strftime('%Y-W%W', date) as week, COUNT(*) as cnt, SUM(estimated_kcal) as kcal
                   FROM records WHERE user_id=? AND estimated_kcal IS NOT NULL
                   GROUP BY week ORDER BY week DESC LIMIT 8""",
                (uid,)
            ).fetchall()]
            weekly.reverse()

            clients.append({
                "user_id": uid,
                "name": m.get("name") or f"사용자 {uid}",
                "chat_id": chat_id,
                "total_sessions": stats["total"] if stats else 0,
                "last_date": stats["last_date"] if stats else None,
                "total_kcal": round(stats["total_kcal"], 0) if stats and stats["total_kcal"] else 0,
                "avg_kcal": round(stats["avg_kcal"], 0) if stats and stats["avg_kcal"] else 0,
                "monthly_sessions": monthly["cnt"] if monthly else 0,
                "top_category": cat_row["category"] if cat_row else None,
                "recent": recent,
                "weekly": weekly,
            })

    # Compute days since last session + activity dot
    for c in clients:
        if c["last_date"]:
            try:
                delta = (today - datetime.strptime(c["last_date"], "%Y-%m-%d").date()).days
                c["days_since"] = delta
                c["activity"] = "green" if delta <= 7 else ("yellow" if delta <= 30 else "red")
            except Exception:
                c["days_since"] = None
                c["activity"] = "red"
        else:
            c["days_since"] = None
            c["activity"] = "red"

        # weekly max for sparkline
        c["weekly_max"] = max((w["cnt"] for w in c["weekly"]), default=1)

    # Sort by last_date desc (most active first)
    clients.sort(key=lambda c: c["last_date"] or "0000-00-00", reverse=True)

    # Summary totals
    total_sessions = sum(c["total_sessions"] for c in clients)
    total_monthly = sum(c["monthly_sessions"] for c in clients)
    total_kcal = sum(c["total_kcal"] for c in clients)

    conn.close()

    return templates.TemplateResponse("trainer.html", {
        "request": request,
        "user": user,
        "clients": clients,
        "total_sessions": total_sessions,
        "total_monthly": total_monthly,
        "total_kcal": total_kcal,
        "this_month": today.strftime("%Y년 %m월"),
        "get_category_color": get_category_color,
    })


# ── JSON API ─────────────────────────────────────────────────

@app.get("/api/records")
async def api_records(request: Request, user_id: Optional[int] = None, limit: int = Query(20, le=100), offset: int = 0):
    conn = get_conn()
    if user_id:
        rows = conn.execute(
            "SELECT * FROM records WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM records ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/records/{record_id}")
async def api_record(record_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
    conn.close()
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    return dict(row)


@app.get("/api/stats")
async def api_stats():
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as total_records, COUNT(DISTINCT user_id) as total_users, AVG(estimated_kcal) as avg_kcal, SUM(estimated_kcal) as total_kcal FROM records"
    ).fetchone()
    conn.close()
    return dict(row)


@app.post("/api/records/{record_id}/editdate")
async def api_edit_date(record_id: int, request: Request, user: dict = Depends(require_user)):
    """Edit the date of a record."""
    body = await request.json()
    new_date = body.get("date", "")
    try:
        from datetime import datetime as dt
        dt.strptime(new_date, "%Y-%m-%d")
    except ValueError:
        return JSONResponse({"error": "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)"}, status_code=400)

    if update_record_date(record_id, new_date, user["user_id"]):
        return JSONResponse({"ok": True, "new_date": new_date})
    return JSONResponse({"error": "수정 실패"}, status_code=403)


@app.post("/api/records/{record_id}/delete")
async def api_delete_record(record_id: int, user: dict = Depends(require_user)):
    """Delete a record."""
    if delete_record(record_id, user["user_id"]):
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "삭제 실패"}, status_code=403)


@app.get("/api/calendar")
async def api_calendar(request: Request, year: Optional[int] = None, month: Optional[int] = None, user: dict = Depends(require_user)):
    """Calendar data as JSON."""
    today = date.today()
    y = year or today.year
    m = month or today.month

    if user["is_trainer"]:
        records = get_all_records_by_month_for_trainer(user["user_id"], y, m)
    else:
        records = get_records_by_month(user["user_id"], y, m)

    cal_data = _build_calendar_data(records, y, m)
    # Convert to JSON-serializable
    result = {}
    for day, recs in cal_data.items():
        result[str(day)] = [
            {
                "id": r["id"],
                "date": r["date"],
                "category": r.get("category", ""),
                "name": r.get("name", ""),
                "estimated_kcal": r.get("estimated_kcal"),
            }
            for r in recs
        ]
    return JSONResponse({"year": y, "month": m, "days": result})
