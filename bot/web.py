"""FastAPI web dashboard for workout bot with Telegram auth."""

import calendar as cal_module
import hashlib
import hmac
import json
import logging
import os
import sqlite3
from datetime import datetime, date
from typing import Optional
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def _kst_today() -> date:
    """Server runs in UTC on Render; users are in Korea. 'Today' must be KST so
    the dashboard's today-records/deficit/scoreboard match the user's clock."""
    return datetime.now(KST).date()

import httpx
from fastapi import FastAPI, File, Form, Request, Query, Depends, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeSerializer
from markupsafe import Markup

from bot.database import (
    GOAL_METRICS,
    create_goal,
    delete_goal,
    delete_inbody,
    delete_meal,
    delete_record,
    get_all_records_by_month_for_trainer,
    get_all_records_for_trainer,
    get_daily_plan,
    get_daily_summary,
    get_group_members,
    get_inbody_history,
    get_latest_inbody,
    get_meals_for_date,
    get_primary_goal,
    get_records_by_month,
    get_recent_records,
    get_today_record,
    compute_target_kcal_detailed,
    estimate_daily_target_kcal,
    get_records_for_user,
    get_records_without_category,
    get_recent_meals,
    compute_deficit_progress,
    get_group_scoreboard,
    get_user_height,
    get_user_weight,
    get_trainer_groups,
    get_user_groups,
    is_user_trainer,
    list_goals,
    merge_record,
    save_inbody,
    save_meal,
    save_record,
    set_primary_goal,
    update_goal,
    update_goal_status,
    update_record_category,
    update_record_date,
    upsert_daily_plan,
    upsert_daily_summary,
    upsert_user,
)
from bot.analyzer import (
    analyze_workout,
    classify_intent_from_image,
    classify_intent_from_text,
    classify_workout,
    extract_date,
    extract_from_image,
    extract_from_text,
    extract_inbody,
    extract_kcal,
    extract_meal_from_image,
    extract_meal_from_text,
    generate_daily_plan,
    generate_daily_summary,
    get_category_color,
    group_by_date,
    is_workout_text,
    strip_date_line,
)

logger = logging.getLogger(__name__)

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
    return templates.TemplateResponse(request, "login.html", {
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
    return templates.TemplateResponse(request, "policy.html", {"request": request, "user": user})


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
    # Trainers land on their command center — the dashboard's primary surface.
    if user.get("is_trainer") and user.get("trainer_groups"):
        return RedirectResponse("/trainer", status_code=302)

    conn = get_conn()
    user_id = user["user_id"]

    # Calendar month
    today = _kst_today()
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

    # Goals / inbody / plan — for non-trainer users only (trainer dashboard already has its own)
    today_str = _kst_today().strftime("%Y-%m-%d")
    if not user["is_trainer"]:
        active_goals = list_goals(user_id)
        latest_inbody = get_latest_inbody(user_id)
        latest_for_progress = latest_inbody or {}
        fallback_weight = get_user_weight(user_id, user["groups"][0]) if user.get("groups") else None
        kcal_detail = compute_target_kcal_detailed(user_id, today_str)
        deficit_progress = compute_deficit_progress(user_id, today_str)
        today_meals_dash = get_meals_for_date(user_id, today_str)
        today_meal_kcal = sum((m.get("estimated_kcal") or 0) for m in today_meals_dash)
        _tconn = get_conn()
        today_exercise_kcal = _tconn.execute(
            "SELECT SUM(estimated_kcal) AS v FROM records WHERE user_id=? AND date=? AND estimated_kcal IS NOT NULL",
            (user_id, today_str),
        ).fetchone()["v"] or 0
        _tconn.close()
        today_p = sum((m.get("protein_g") or 0) for m in today_meals_dash)
        today_c = sum((m.get("carbs_g") or 0) for m in today_meals_dash)
        today_f = sum((m.get("fat_g") or 0) for m in today_meals_dash)
        for g in active_goals:
            try:
                g["days_left"] = (datetime.strptime(g["target_date"], "%Y-%m-%d").date() - _kst_today()).days
            except Exception:
                g["days_left"] = None
            label, unit = GOAL_METRICS.get(g["metric"], (g["metric"], ""))
            g["label"] = label
            g["unit"] = unit
            g["current_value"] = latest_for_progress.get(g["metric"])
            if g["current_value"] is None and g["metric"] == "weight":
                g["current_value"] = fallback_weight
            if g["current_value"] is not None and g.get("start_value"):
                try:
                    total = g["target_value"] - g["start_value"]
                    done = g["current_value"] - g["start_value"]
                    g["progress_pct"] = 100 if total == 0 else max(0, min(100, int(done / total * 100)))
                except Exception:
                    g["progress_pct"] = None
            else:
                g["progress_pct"] = None
        today_plan = get_daily_plan(user_id, today_str)
        recomp_dday = (date(2026, 8, 10) - _kst_today()).days
    else:
        active_goals = []
        latest_inbody = None
        today_plan = None
        kcal_detail = None
        deficit_progress = None
        today_exercise_kcal = 0
        today_meal_kcal = 0
        today_p = today_c = today_f = 0
        recomp_dday = None

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

    return templates.TemplateResponse(request, "dashboard.html", {
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
        "active_goals": active_goals,
        "latest_inbody": latest_inbody,
        "today_plan": today_plan,
        "today_str": today_str,
        "kcal_detail": kcal_detail,
        "deficit_progress": deficit_progress,
        "today_exercise_kcal": today_exercise_kcal,
        "today_meal_kcal": today_meal_kcal,
        "today_p": today_p,
        "today_c": today_c,
        "today_f": today_f,
        "recomp_dday": recomp_dday,
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
    return templates.TemplateResponse(request, "records.html", {
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

    return templates.TemplateResponse(request, "record_detail.html", {
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

    # Goal deficit progress + goal card for this member
    today_str = _kst_today().strftime("%Y-%m-%d")
    deficit_progress = compute_deficit_progress(target_user_id, today_str)
    latest_inbody = get_latest_inbody(target_user_id)
    return templates.TemplateResponse(request, "user.html", {
        "request": request,
        "user": user,
        "target_user": dict(target_user) if target_user else {"user_id": target_user_id, "name": f"사용자 {target_user_id}", "weight_kg": None},
        "records": records,
        "stats": dict(stats) if stats else {"cnt": 0, "avg_kcal": 0, "total_kcal": 0},
        "weekly": weekly,
        "deficit_progress": deficit_progress,
        "latest_inbody": latest_inbody,
    })


@app.get("/report/{target_user_id}", response_class=HTMLResponse)
async def weekly_report(request: Request, target_user_id: int, user: dict = Depends(require_user)):
    """Shareable weekly progress report — the referral asset. A clean, branded
    card a trainer can screenshot and forward. Own-self or trainer-of-group only."""
    from datetime import timedelta
    if target_user_id != user["user_id"]:
        if user["is_trainer"]:
            if not (set(get_user_groups(target_user_id)) & set(user["trainer_groups"])):
                return HTMLResponse("<h1>접근 권한이 없습니다</h1>", status_code=403)
        else:
            return HTMLResponse("<h1>접근 권한이 없습니다</h1>", status_code=403)

    today = _kst_today()
    start = today - timedelta(days=6)
    start_s, today_s = start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")

    conn = get_conn()
    tu = conn.execute("SELECT * FROM users WHERE user_id=? LIMIT 1", (target_user_id,)).fetchone()
    name = (dict(tu).get("name") if tu else None) or f"회원 {target_user_id}"

    workouts = conn.execute(
        "SELECT COUNT(*) c, SUM(estimated_kcal) k FROM records WHERE user_id=? AND date>=? AND date<=?",
        (target_user_id, start_s, today_s),
    ).fetchone()
    meals = conn.execute(
        """SELECT COUNT(DISTINCT date) d, AVG(estimated_kcal) ak, AVG(protein_g) ap
           FROM meals WHERE user_id=? AND date>=? AND date<=?""",
        (target_user_id, start_s, today_s),
    ).fetchone()
    log_days = conn.execute(
        """SELECT COUNT(DISTINCT date) d FROM (
             SELECT date FROM records WHERE user_id=? AND date>=? AND date<=?
             UNION SELECT date FROM meals WHERE user_id=? AND date>=? AND date<=?)""",
        (target_user_id, start_s, today_s, target_user_id, start_s, today_s),
    ).fetchone()["d"]
    conn.close()

    inbody_hist = get_inbody_history(target_user_id, limit=2)
    inbody_delta = None
    if len(inbody_hist) >= 2:
        cur, prev = inbody_hist[0], inbody_hist[1]
        inbody_delta = {}
        for key in ("weight_kg", "skeletal_muscle_kg", "body_fat_kg", "body_fat_pct"):
            if cur.get(key) is not None and prev.get(key) is not None:
                inbody_delta[key] = round(float(cur[key]) - float(prev[key]), 1)

    deficit_progress = compute_deficit_progress(target_user_id, today_s)

    return templates.TemplateResponse(request, "report.html", {
        "request": request,
        "name": name,
        "period": f"{start_s} ~ {today_s}",
        "workout_count": workouts["c"] or 0,
        "workout_kcal": round(workouts["k"] or 0),
        "adherence_pct": round(log_days / 7 * 100),
        "log_days": log_days,
        "avg_kcal": round(meals["ak"]) if meals["ak"] else None,
        "avg_protein": round(meals["ap"]) if meals["ap"] else None,
        "inbody_delta": inbody_delta,
        "deficit_progress": deficit_progress,
    })


@app.get("/trainer", response_class=HTMLResponse)
async def trainer_page(request: Request, user: dict = Depends(require_user)):
    if not user["is_trainer"]:
        return HTMLResponse("<h1>접근 권한이 없습니다</h1><p>트레이너만 접근할 수 있습니다.</p>", status_code=403)

    conn = get_conn()
    today = _kst_today()
    today_str = today.strftime("%Y-%m-%d")
    this_month = today.strftime("%Y-%m")

    # Today's compliance from the same engine that powers the 21:00 scoreboard —
    # keyed by user_id so each client card shows one consistent set of numbers.
    compliance = {}
    for chat_id in user["trainer_groups"]:
        try:
            board = get_group_scoreboard(chat_id, today_str)
            for r in board["rows"]:
                compliance[r["user_id"]] = r
        except Exception:
            pass

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

            comp = compliance.get(uid, {})
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
                # Today's compliance (from scoreboard engine)
                "trained_today": comp.get("trained", False),
                "meal_logged_today": comp.get("meal_logged", False),
                "kcal_pct": comp.get("kcal_pct"),
                "streak": comp.get("streak", 0),
                "goal_pct": comp.get("goal_pct"),
                "days_silent": comp.get("days_silent"),
            })

    # Risk status from days_silent (today-relative, actionable):
    #   green = logged today, yellow = 1-2 days quiet, red = 3+ days or never.
    for c in clients:
        ds = c["days_silent"]
        if ds is None:
            c["activity"] = "red"
            c["days_since"] = None
        else:
            c["days_since"] = ds
            c["activity"] = "green" if ds == 0 else ("yellow" if ds <= 2 else "red")
        c["at_risk"] = (ds is None) or (ds >= 3)
        c["weekly_max"] = max((w["cnt"] for w in c["weekly"]), default=1)

    # Sort by risk first (at-risk on top so trainers act), then longest silence,
    # then streak so strong clients bubble up within the healthy group.
    rank = {"red": 0, "yellow": 1, "green": 2}
    clients.sort(key=lambda c: (
        rank.get(c["activity"], 3),
        -(c["days_silent"] if c["days_silent"] is not None else 9999),
        -c["streak"],
    ))

    # Summary
    total_sessions = sum(c["total_sessions"] for c in clients)
    total_monthly = sum(c["monthly_sessions"] for c in clients)
    total_kcal = sum(c["total_kcal"] for c in clients)
    active_today = sum(1 for c in clients if c["days_silent"] == 0)
    at_risk_clients = [c for c in clients if c["at_risk"]]
    avg_streak = round(sum(c["streak"] for c in clients) / len(clients), 1) if clients else 0

    conn.close()

    return templates.TemplateResponse(request, "trainer.html", {
        "request": request,
        "user": user,
        "clients": clients,
        "total_sessions": total_sessions,
        "total_monthly": total_monthly,
        "total_kcal": total_kcal,
        "active_today": active_today,
        "at_risk_clients": at_risk_clients,
        "avg_streak": avg_streak,
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


@app.post("/api/records/{record_id}/analyze")
async def api_analyze_record(record_id: int, user: dict = Depends(require_user)):
    """Generate (or regenerate) the coach analysis for a record and persist it.
    Called from the record detail page's '리포트 생성' button."""
    from bot.analyzer import analyze_workout, extract_kcal, classify_workout
    from bot.database import merge_record as db_merge_record, get_user_weight as db_get_user_weight, get_user_height as db_get_user_height
    from bot.utils import format_history_summary as fmt_history

    conn = get_conn()
    row = conn.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
    if not row:
        conn.close()
        return JSONResponse({"error": "기록을 찾을 수 없습니다"}, status_code=404)
    rec = dict(row)
    # Access check — owner or trainer-of-the-group
    if rec["user_id"] != user["user_id"]:
        if not user.get("is_trainer") or rec["chat_id"] not in user.get("trainer_groups", []):
            conn.close()
            return JSONResponse({"error": "권한이 없습니다"}, status_code=403)
    history_rows = conn.execute(
        "SELECT * FROM records WHERE chat_id=? AND user_id=? AND id != ? ORDER BY created_at DESC LIMIT 5",
        (rec["chat_id"], rec["user_id"], record_id),
    ).fetchall()
    conn.close()
    history = [dict(r) for r in history_rows]

    weight = db_get_user_weight(rec["user_id"], rec["chat_id"])
    height = db_get_user_height(rec["user_id"], rec["chat_id"])

    try:
        analysis = await analyze_workout(
            rec.get("structured_md") or "",
            weight,
            fmt_history(history),
            height_cm=height,
        )
        kcal = extract_kcal(analysis)
        category = classify_workout(rec.get("structured_md") or "") or rec.get("category")
        db_merge_record(record_id, rec.get("structured_md") or "", analysis, kcal, category=category)
        return JSONResponse({"ok": True, "analysis": analysis, "kcal": kcal})
    except Exception as e:
        return JSONResponse({"error": f"분석 중 오류: {e}"}, status_code=500)


# ── Goals ────────────────────────────────────────────────────

@app.get("/goals", response_class=HTMLResponse)
async def goals_page(request: Request, user: dict = Depends(require_user)):
    goals = list_goals(user["user_id"])
    achieved = []
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM goals WHERE user_id=? AND status='achieved' ORDER BY updated_at DESC LIMIT 20",
        (user["user_id"],),
    ).fetchall()
    achieved = [dict(r) for r in rows]
    conn.close()

    today = _kst_today()
    for g in goals + achieved:
        try:
            g["days_left"] = (datetime.strptime(g["target_date"], "%Y-%m-%d").date() - today).days
        except Exception:
            g["days_left"] = None
        label, unit = GOAL_METRICS.get(g["metric"], (g["metric"], ""))
        g["label"] = label
        g["unit"] = unit

    latest = get_latest_inbody(user["user_id"])

    return templates.TemplateResponse(request, "goals.html", {
        "request": request,
        "user": user,
        "goals": goals,
        "achieved": achieved,
        "latest_inbody": latest,
        "metrics": GOAL_METRICS,
    })


@app.post("/api/goals")
async def api_create_goal(request: Request, user: dict = Depends(require_user)):
    body = await request.json()
    metric = body.get("metric", "")
    if metric not in GOAL_METRICS:
        return JSONResponse({"error": "잘못된 지표"}, status_code=400)
    try:
        target_value = float(body["target_value"])
        target_date_str = body["target_date"]
        datetime.strptime(target_date_str, "%Y-%m-%d")
    except (KeyError, ValueError):
        return JSONResponse({"error": "잘못된 입력"}, status_code=400)

    start_value = body.get("start_value")
    if start_value is None:
        latest = get_latest_inbody(user["user_id"])
        if latest:
            start_value = latest.get(metric)
    try:
        start_value = float(start_value) if start_value is not None else None
    except (TypeError, ValueError):
        start_value = None

    chat_id = user["groups"][0] if user.get("groups") else 0
    gid = create_goal(
        user["user_id"], chat_id, metric, target_value, target_date_str,
        start_value=start_value, is_primary=bool(body.get("is_primary")),
    )
    return JSONResponse({"ok": True, "id": gid})


@app.post("/api/goals/{goal_id}/delete")
async def api_delete_goal(goal_id: int, user: dict = Depends(require_user)):
    if delete_goal(goal_id, user["user_id"]):
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "삭제 실패"}, status_code=403)


@app.post("/api/goals/{goal_id}/primary")
async def api_primary_goal(goal_id: int, user: dict = Depends(require_user)):
    if set_primary_goal(goal_id, user["user_id"]):
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "처리 실패"}, status_code=403)


@app.post("/api/goals/{goal_id}/done")
async def api_done_goal(goal_id: int, user: dict = Depends(require_user)):
    if update_goal_status(goal_id, user["user_id"], "achieved"):
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "처리 실패"}, status_code=403)


@app.post("/api/goals/{goal_id}/update")
async def api_update_goal(goal_id: int, request: Request, user: dict = Depends(require_user)):
    body = await request.json()
    target_value = body.get("target_value")
    target_date_str = body.get("target_date")
    if target_value is not None:
        try:
            target_value = float(target_value)
        except ValueError:
            return JSONResponse({"error": "잘못된 값"}, status_code=400)
    if target_date_str:
        try:
            datetime.strptime(target_date_str, "%Y-%m-%d")
        except ValueError:
            return JSONResponse({"error": "잘못된 날짜"}, status_code=400)
    if update_goal(goal_id, user["user_id"], target_value=target_value, target_date=target_date_str):
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "수정 실패"}, status_code=403)


# ── InBody ───────────────────────────────────────────────────

@app.get("/inbody", response_class=HTMLResponse)
async def inbody_page(request: Request, user: dict = Depends(require_user)):
    history = get_inbody_history(user["user_id"], limit=100)
    return templates.TemplateResponse(request, "inbody.html", {
        "request": request,
        "user": user,
        "history": history,
    })


@app.post("/api/inbody/{inbody_id}/delete")
async def api_delete_inbody(inbody_id: int, user: dict = Depends(require_user)):
    if delete_inbody(inbody_id, user["user_id"]):
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "삭제 실패"}, status_code=403)


# ── Meals ────────────────────────────────────────────────────

@app.get("/meals", response_class=HTMLResponse)
async def meals_page(request: Request, date_str: Optional[str] = Query(None, alias="date"), user: dict = Depends(require_user)):
    today_str = date_str or _kst_today().strftime("%Y-%m-%d")
    try:
        datetime.strptime(today_str, "%Y-%m-%d")
    except ValueError:
        today_str = _kst_today().strftime("%Y-%m-%d")
    today_meals = get_meals_for_date(user["user_id"], today_str)
    recent = get_recent_meals(user["user_id"], 30)
    today_kcal = sum((m.get("estimated_kcal") or 0) for m in today_meals)
    today_p = sum((m.get("protein_g") or 0) for m in today_meals)
    today_c = sum((m.get("carbs_g") or 0) for m in today_meals)
    today_f = sum((m.get("fat_g") or 0) for m in today_meals)
    detail = compute_target_kcal_detailed(user["user_id"], today_str)
    target_kcal = detail.get("target_kcal")
    source_label = {
        "plan": "/plan으로 계산",
        "goal-derived": "목표·인바디 기반",
        "maintain-tdee": "유지 칼로리 (TDEE)",
    }.get(detail.get("source"), "")
    remaining_kcal = (target_kcal - today_kcal) if target_kcal else None
    return templates.TemplateResponse(request, "meals.html", {
        "request": request,
        "user": user,
        "today_str": today_str,
        "today_meals": today_meals,
        "recent": recent,
        "today_kcal": today_kcal,
        "today_p": today_p,
        "today_c": today_c,
        "today_f": today_f,
        "target_kcal": target_kcal,
        "target_source_label": source_label,
        "remaining_kcal": remaining_kcal,
        "kcal_detail": detail,
    })


@app.post("/api/meals/{meal_id}/delete")
async def api_delete_meal(meal_id: int, user: dict = Depends(require_user)):
    if delete_meal(meal_id, user["user_id"]):
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "삭제 실패"}, status_code=403)


@app.get("/api/calendar")
async def api_calendar(request: Request, year: Optional[int] = None, month: Optional[int] = None, user: dict = Depends(require_user)):
    """Calendar data as JSON."""
    today = _kst_today()
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


# ── Native app API ───────────────────────────────────────────
APP_API_TOKEN = os.environ.get("APP_API_TOKEN", "")


def _check_app_token(request: Request) -> bool:
    """Optional shared-secret gate for the native app. If APP_API_TOKEN is unset
    (prototype), allow all; if set, require matching X-App-Token header."""
    if not APP_API_TOKEN:
        return True
    return request.headers.get("X-App-Token") == APP_API_TOKEN


@app.get("/api/app/summary")
async def api_app_summary(request: Request, user_id: int):
    """Compact dashboard payload for the native iOS app: today's calories,
    macro target, goal-deficit progress, primary goal, streak, recent records."""
    if not _check_app_token(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    today_str = _kst_today().strftime("%Y-%m-%d")
    conn = get_conn()
    name_row = conn.execute("SELECT name FROM users WHERE user_id=? LIMIT 1", (user_id,)).fetchone()
    ex = conn.execute(
        "SELECT SUM(estimated_kcal) v FROM records WHERE user_id=? AND date=? AND estimated_kcal IS NOT NULL",
        (user_id, today_str),
    ).fetchone()["v"] or 0
    recent = [
        {
            "id": r["id"], "date": r["date"], "category": r["category"],
            "estimated_kcal": r["estimated_kcal"],
        }
        for r in conn.execute(
            "SELECT id, date, category, estimated_kcal FROM records WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
            (user_id,),
        ).fetchall()
    ]
    conn.close()

    meals = get_meals_for_date(user_id, today_str)
    today_intake = sum((m.get("estimated_kcal") or 0) for m in meals)
    kcal_detail = compute_target_kcal_detailed(user_id, today_str)
    deficit = compute_deficit_progress(user_id, today_str)
    goals = list_goals(user_id)
    primary = next((g for g in goals if g.get("is_primary")), goals[0] if goals else None)

    return JSONResponse({
        "user_id": user_id,
        "name": (dict(name_row).get("name") if name_row else None) or f"회원 {user_id}",
        "date": today_str,
        "today": {
            "intake_kcal": round(today_intake),
            "exercise_kcal": round(ex),
            "target_kcal": round(kcal_detail["target_kcal"]) if kcal_detail.get("target_kcal") else None,
            "tdee": round(kcal_detail["tdee"]) if kcal_detail.get("tdee") else None,
            "protein_g": round(sum((m.get("protein_g") or 0) for m in meals)),
            "carbs_g": round(sum((m.get("carbs_g") or 0) for m in meals)),
            "fat_g": round(sum((m.get("fat_g") or 0) for m in meals)),
            "macros": kcal_detail.get("macros"),
        },
        "primary_goal": {
            "metric": primary["metric"],
            "target_value": primary["target_value"],
            "target_date": primary["target_date"],
        } if primary else None,
        "deficit": deficit if deficit.get("available") else {"available": False, "reason": deficit.get("reason", "")},
        "recent_records": recent,
        "plan": _serialize_plan(get_daily_plan(user_id, today_str)),
        "daily_summary": _serialize_daily_summary(get_daily_summary(user_id, today_str)),
    })


# ── Native app write APIs (upload / text record / plan / summary) ─

def _app_today_str() -> str:
    return _kst_today().strftime("%Y-%m-%d")


def _resolve_app_chat_id(user_id: int) -> int:
    """Pick a stable chat_id for app-originated records.

    Prefer an existing group membership, else the user's last known chat_id from
    the users table, else 0 (same convention as web goal creation).
    """
    groups = get_user_groups(user_id)
    if groups:
        return groups[0]
    conn = get_conn()
    row = conn.execute(
        "SELECT chat_id FROM users WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return int(row["chat_id"]) if row else 0


def _ensure_app_user(user_id: int, chat_id: int) -> None:
    conn = get_conn()
    row = conn.execute(
        "SELECT name FROM users WHERE user_id=? LIMIT 1", (user_id,)
    ).fetchone()
    conn.close()
    name = (dict(row).get("name") if row else None) or f"app_{user_id}"
    upsert_user(user_id, chat_id, name)


def _meal_type_by_time() -> str:
    from bot.handlers import _meal_type_by_time as _h
    return _h()


def _format_meal_items_md(items: list) -> str:
    from bot.handlers import format_meal_items_md
    return format_meal_items_md(items)


def _render_meal_html(meal: Optional[dict]) -> str:
    from bot.handlers import _render_meal_html as _h
    return _h(meal)


def _build_plan_context(user_id: int, chat_id: int, date: str) -> str:
    from bot.handlers import _build_plan_context as _h
    return _h(user_id, chat_id, date)


def _serialize_plan(plan: Optional[dict]) -> Optional[dict]:
    if not plan:
        return None
    full = plan.get("full_plan") or ""
    full_obj = None
    if full:
        try:
            full_obj = json.loads(full) if isinstance(full, str) else full
        except Exception:
            full_obj = None
    return {
        "date": plan.get("date"),
        "target_kcal_intake": plan.get("target_kcal_intake"),
        "target_kcal_burn": plan.get("target_kcal_burn"),
        "breakfast_suggestion": plan.get("breakfast_suggestion") or "",
        "lunch_suggestion": plan.get("lunch_suggestion") or "",
        "dinner_suggestion": plan.get("dinner_suggestion") or "",
        "full_plan": full_obj,
        "full_plan_raw": full if isinstance(full, str) else json.dumps(full, ensure_ascii=False),
    }


def _serialize_daily_summary(summary: Optional[dict]) -> Optional[dict]:
    if not summary:
        return None
    return {
        "date": summary.get("date"),
        "summary_md": summary.get("summary_md") or "",
        "goal_assessment_md": summary.get("goal_assessment_md") or "",
    }


def _save_meals_from_extraction_app(
    chat_id: int,
    user_id: int,
    date: str,
    data: dict,
    raw_label: str,
    default_meal_type: str,
) -> list[dict]:
    """Persist meal extraction (same shape as handlers._save_meals_from_extraction)."""
    meals_by_type = (data or {}).get("meals_by_type") or {}
    if not meals_by_type and (data or {}).get("items"):
        meals_by_type = {
            default_meal_type: {
                "items": data["items"],
                "total_kcal": data.get("total_kcal"),
                "protein_g": data.get("protein_g"),
                "carbs_g": data.get("carbs_g"),
                "fat_g": data.get("fat_g"),
                "summary_md": data.get("summary_md", ""),
                "analysis_md": data.get("analysis_md", ""),
            }
        }

    saved = []
    for meal_type, meal_data in meals_by_type.items():
        if meal_type not in ("breakfast", "lunch", "dinner", "snack"):
            continue
        items = (meal_data or {}).get("items") or []
        if not items:
            continue
        items_md = _format_meal_items_md(items)
        structured_md = meal_data.get("summary_md") or items_md
        analysis_md = meal_data.get("analysis_md", "")
        kcal = meal_data.get("total_kcal")
        macros = {
            "protein_g": meal_data.get("protein_g"),
            "carbs_g": meal_data.get("carbs_g"),
            "fat_g": meal_data.get("fat_g"),
        }
        meal_id = save_meal(
            chat_id, user_id, date, meal_type, raw_label,
            structured_md, kcal, macros, analysis_md,
        )
        saved.append({
            "id": meal_id,
            "meal_type": meal_type,
            "structured_md": structured_md,
            "analysis_md": analysis_md,
            "items_md": items_md,
            "estimated_kcal": kcal,
            "protein_g": macros.get("protein_g"),
            "carbs_g": macros.get("carbs_g"),
            "fat_g": macros.get("fat_g"),
            "date": date,
        })
    return saved


async def _app_process_workout_image(
    chat_id: int, user_id: int, image_bytes: bytes, caption: str, date: str,
) -> dict:
    structured = await extract_from_image(image_bytes, user_caption=caption)
    all_extracted = []
    if "NO_WORKOUT_DATA" not in structured:
        all_extracted.append(structured)
    elif caption and is_workout_text(caption):
        text_result = await extract_from_text(caption)
        if "NO_WORKOUT_DATA" not in text_result:
            all_extracted.append(text_result)

    if not all_extracted:
        return {
            "ok": False,
            "intent": "workout",
            "error": "운동 사진으로 인식했지만 기록을 추출하지 못했습니다.",
        }

    date_groups = group_by_date(all_extracted, fallback_date=date)
    raw_label = f"[app-image] {caption}".strip() if caption else "[app-image]"
    records = []
    for rec_date, data_list in sorted(date_groups.items()):
        combined = "\n\n".join(data_list)
        category = classify_workout(combined)
        existing = get_today_record(chat_id, user_id, rec_date)
        if existing:
            merged = (existing.get("structured_md") or "") + "\n\n" + combined
            merge_record(
                existing["id"], merged,
                existing.get("analysis") or "",
                existing.get("estimated_kcal"),
                category=category,
            )
            records.append({
                "id": existing["id"],
                "date": rec_date,
                "category": category,
                "structured_md": merged,
                "analysis": existing.get("analysis") or "",
                "estimated_kcal": existing.get("estimated_kcal"),
                "merged": True,
            })
        else:
            new_id = save_record(
                chat_id, user_id, raw_label, combined, "", None,
                date=rec_date, category=category,
            )
            records.append({
                "id": new_id,
                "date": rec_date,
                "category": category,
                "structured_md": combined,
                "analysis": "",
                "estimated_kcal": None,
                "merged": False,
            })
    return {
        "ok": True,
        "intent": "workout",
        "message": f"운동 기록 {len(records)}건 저장 완료",
        "records": records,
    }


async def _app_process_meal_image(
    chat_id: int, user_id: int, image_bytes: bytes, caption: str,
    date: str, default_meal_type: str,
) -> dict:
    weight = get_user_weight(user_id, chat_id)
    height = get_user_height(user_id, chat_id)
    ctx_lines = []
    if weight:
        ctx_lines.append(f"사용자 체중: {weight}kg")
    if height:
        ctx_lines.append(f"키: {height}cm")
    if caption:
        ctx_lines.append(f"사용자 메모: {caption}")
    user_ctx = "\n".join(ctx_lines)

    data = await extract_meal_from_image(
        image_bytes, default_meal_type, user_ctx, lock_to_default=False,
    )
    raw_label = f"[app-image] {caption}".strip() if caption else "[app-image]"
    saved = _save_meals_from_extraction_app(
        chat_id, user_id, date, data, raw_label, default_meal_type,
    )
    if not saved:
        return {
            "ok": False,
            "intent": "meal",
            "error": "식사로 인식했지만 음식 정보를 추출하지 못했습니다.",
        }
    return {
        "ok": True,
        "intent": "meal",
        "message": f"식단 {len(saved)}건 저장 완료",
        "meals": saved,
    }


async def _app_process_inbody_image(
    chat_id: int, user_id: int, image_bytes: bytes, caption: str, date: str,
) -> dict:
    metrics = await extract_inbody(image_bytes, user_caption=caption)
    if not metrics:
        return {
            "ok": False,
            "intent": "inbody",
            "error": "인바디 이미지로 인식했지만 수치 추출에 실패했습니다.",
        }

    measured_at = metrics.get("measured_at") or date
    try:
        datetime.strptime(measured_at, "%Y-%m-%d")
    except (ValueError, TypeError):
        measured_at = date

    clean = {
        k: metrics.get(k)
        for k in (
            "weight_kg", "skeletal_muscle_kg", "body_fat_kg", "body_fat_pct",
            "bmi", "bmr_kcal", "body_water_kg", "protein_kg", "mineral_kg",
            "visceral_fat_level",
        )
        if metrics.get(k) is not None
    }
    inbody_id = save_inbody(
        chat_id, user_id, measured_at, clean, json.dumps(metrics, ensure_ascii=False),
    )
    return {
        "ok": True,
        "intent": "inbody",
        "message": f"인바디 저장 완료 ({measured_at})",
        "inbody": {"id": inbody_id, "measured_at": measured_at, **clean},
    }


async def _app_process_workout_text(
    chat_id: int, user_id: int, text: str, date: str, do_analyze: bool = False,
) -> dict:
    structured = await extract_from_text(text)
    if "NO_WORKOUT_DATA" in structured:
        return {
            "ok": False,
            "intent": "workout",
            "error": "운동 기록을 인식할 수 없습니다.",
        }

    record_date = extract_date(structured) or date
    structured_clean = strip_date_line(structured)
    category = classify_workout(structured_clean)
    existing = get_today_record(chat_id, user_id, record_date)
    analysis = ""
    kcal = None
    merged = False

    if existing:
        merged_structured = (existing.get("structured_md") or "") + "\n\n" + structured_clean
        rec_id = existing["id"]
        if do_analyze:
            weight = get_user_weight(user_id, chat_id)
            height = get_user_height(user_id, chat_id)
            history = get_recent_records(chat_id, user_id, 5)
            from bot.utils import format_history_summary
            analysis = await analyze_workout(
                merged_structured, weight, format_history_summary(history), height_cm=height,
            )
            kcal = extract_kcal(analysis)
            category = classify_workout(merged_structured)
            merge_record(rec_id, merged_structured, analysis, kcal, category=category)
        else:
            merge_record(
                rec_id, merged_structured,
                existing.get("analysis") or "",
                existing.get("estimated_kcal"),
                category=classify_workout(merged_structured),
            )
            analysis = existing.get("analysis") or ""
            kcal = existing.get("estimated_kcal")
            category = classify_workout(merged_structured)
        structured_out = merged_structured
        merged = True
    else:
        if do_analyze:
            weight = get_user_weight(user_id, chat_id)
            height = get_user_height(user_id, chat_id)
            history = get_recent_records(chat_id, user_id, 5)
            from bot.utils import format_history_summary
            analysis = await analyze_workout(
                structured_clean, weight, format_history_summary(history), height_cm=height,
            )
            kcal = extract_kcal(analysis)
            rec_id = save_record(
                chat_id, user_id, text, structured_clean, analysis, kcal,
                date=record_date, category=category,
            )
        else:
            rec_id = save_record(
                chat_id, user_id, text, structured_clean, "", None,
                date=record_date, category=category,
            )
        structured_out = structured_clean

    return {
        "ok": True,
        "intent": "workout",
        "message": "운동 기록 저장 완료" + (" (병합)" if merged else ""),
        "records": [{
            "id": rec_id,
            "date": record_date,
            "category": category,
            "structured_md": structured_out,
            "analysis": analysis,
            "estimated_kcal": kcal,
            "merged": merged,
        }],
    }


async def _app_process_meal_text(
    chat_id: int, user_id: int, text: str, date: str, default_meal_type: str,
) -> dict:
    weight = get_user_weight(user_id, chat_id)
    height = get_user_height(user_id, chat_id)
    ctx_lines = []
    if weight:
        ctx_lines.append(f"사용자 체중: {weight}kg")
    if height:
        ctx_lines.append(f"키: {height}cm")
    user_ctx = "\n".join(ctx_lines)

    data = await extract_meal_from_text(
        text, default_meal_type, user_ctx, lock_to_default=False,
    )
    saved = _save_meals_from_extraction_app(
        chat_id, user_id, date, data, text, default_meal_type,
    )
    if not saved:
        return {
            "ok": False,
            "intent": "meal",
            "error": "식사로 인식했지만 음식 구체화에 실패했습니다.",
        }
    return {
        "ok": True,
        "intent": "meal",
        "message": f"식단 {len(saved)}건 저장 완료",
        "meals": saved,
    }


@app.post("/api/app/upload")
async def api_app_upload(
    request: Request,
    photo: UploadFile = File(...),
    user_id: int = Form(...),
    caption: str = Form(""),
):
    """Multipart photo upload for the native app.

    Classifies photo type (workout/meal/inbody) via analyzer, then reuses the
    same extraction/save path as the Telegram bot handlers.
    """
    if not _check_app_token(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    image_bytes = await photo.read()
    if not image_bytes:
        return JSONResponse({"error": "빈 이미지입니다"}, status_code=400)
    # Soft cap ~12MB to avoid runaway memory
    if len(image_bytes) > 12 * 1024 * 1024:
        return JSONResponse({"error": "이미지가 너무 큽니다 (최대 12MB)"}, status_code=400)

    chat_id = _resolve_app_chat_id(user_id)
    _ensure_app_user(user_id, chat_id)
    date = _app_today_str()
    caption = (caption or "").strip()

    try:
        intent_data = await classify_intent_from_image(image_bytes, hint=caption)
    except Exception as e:
        logger.error(f"App upload intent error: {e}")
        intent_data = {"intent": "workout", "confidence": 0.3}

    intent = (intent_data.get("intent") or "workout").lower()
    confidence = intent_data.get("confidence")
    reason = intent_data.get("reason_md", "")

    try:
        if intent == "inbody":
            result = await _app_process_inbody_image(
                chat_id, user_id, image_bytes, caption, date,
            )
        elif intent == "meal":
            meal_type = (intent_data.get("meal_type") or "").lower() or _meal_type_by_time()
            if meal_type not in ("breakfast", "lunch", "dinner", "snack"):
                meal_type = _meal_type_by_time()
            result = await _app_process_meal_image(
                chat_id, user_id, image_bytes, caption, date, meal_type,
            )
        elif intent == "unrelated":
            msg = "운동·식단·인바디 어느 것에도 해당되지 않는 사진으로 보입니다."
            if reason:
                msg += f" ({reason})"
            result = {"ok": False, "intent": "unrelated", "error": msg}
        else:
            result = await _app_process_workout_image(
                chat_id, user_id, image_bytes, caption, date,
            )
    except Exception as e:
        logger.error(f"App upload process error (intent={intent}): {e}")
        return JSONResponse(
            {"ok": False, "error": f"분석 중 오류: {e}", "intent": intent},
            status_code=500,
        )

    result["confidence"] = confidence
    result["reason_md"] = reason
    status = 200 if result.get("ok") else 422
    return JSONResponse(result, status_code=status)


@app.post("/api/app/record")
async def api_app_record(request: Request):
    """Text workout/meal record for the native app.

    Body JSON: { "user_id": int, "text": str, "analyze": bool? }
    Reuses classify_intent_from_text + extract_from_text / extract_meal_from_text.
    """
    if not _check_app_token(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON body required"}, status_code=400)

    try:
        user_id = int(body.get("user_id"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "user_id required"}, status_code=400)

    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text required"}, status_code=400)
    if len(text) > 8000:
        return JSONResponse({"error": "text too long"}, status_code=400)

    do_analyze = bool(body.get("analyze", False))
    chat_id = _resolve_app_chat_id(user_id)
    _ensure_app_user(user_id, chat_id)
    date = _app_today_str()

    try:
        intent_data = await classify_intent_from_text(text)
    except Exception as e:
        logger.error(f"App record intent error: {e}")
        intent_data = {"intent": "workout", "confidence": 0.3}

    intent = (intent_data.get("intent") or "workout").lower()
    confidence = intent_data.get("confidence")
    reason = intent_data.get("reason_md", "")

    try:
        if intent == "meal":
            meal_type = (intent_data.get("meal_type") or "").lower() or _meal_type_by_time()
            if meal_type not in ("breakfast", "lunch", "dinner", "snack"):
                meal_type = _meal_type_by_time()
            result = await _app_process_meal_text(
                chat_id, user_id, text, date, meal_type,
            )
        elif intent == "inbody":
            result = {
                "ok": False,
                "intent": "inbody",
                "error": "인바디 수치는 사진으로 보내주세요. (텍스트 입력 미지원)",
            }
        elif intent == "unrelated":
            msg = "운동·식단·인바디 어느 것에도 해당되지 않아 보입니다."
            if reason:
                msg += f" ({reason})"
            result = {"ok": False, "intent": "unrelated", "error": msg}
        else:
            result = await _app_process_workout_text(
                chat_id, user_id, text, date, do_analyze=do_analyze,
            )
    except Exception as e:
        logger.error(f"App record process error (intent={intent}): {e}")
        return JSONResponse(
            {"ok": False, "error": f"분석 중 오류: {e}", "intent": intent},
            status_code=500,
        )

    result["confidence"] = confidence
    result["reason_md"] = reason
    status = 200 if result.get("ok") else 422
    return JSONResponse(result, status_code=status)


@app.post("/api/app/plan")
async def api_app_plan(request: Request):
    """Generate (or return cached) daily plan via generate_daily_plan.

    Body JSON: { "user_id": int, "refresh": bool? }
    """
    if not _check_app_token(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON body required"}, status_code=400)

    try:
        user_id = int(body.get("user_id"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "user_id required"}, status_code=400)

    refresh = bool(body.get("refresh", False))
    date = _app_today_str()
    chat_id = _resolve_app_chat_id(user_id)
    _ensure_app_user(user_id, chat_id)

    cached = get_daily_plan(user_id, date)
    if cached and not refresh:
        payload = _serialize_plan(cached)
        payload["ok"] = True
        payload["cached"] = True
        return JSONResponse(payload)

    if not list_goals(user_id):
        return JSONResponse({
            "ok": False,
            "error": "활성 목표가 없어 일일 계획을 생성할 수 없습니다. 웹/텔레그램에서 목표를 먼저 등록하세요.",
        }, status_code=422)

    try:
        kcal_detail = compute_target_kcal_detailed(user_id, date)
        targets_block = []
        if kcal_detail.get("target_kcal"):
            targets_block.append("## 사전 계산된 목표 (이 수치를 따르세요)")
            targets_block.append(f"- 일일 섭취 목표: **{int(kcal_detail['target_kcal'])} kcal**")
            m = kcal_detail.get("macros") or {}
            if m:
                targets_block.append(
                    f"- 매크로 ({m.get('direction', 'maintain')}): "
                    f"단백 {m['protein_g']}g ({m['protein_pct']}%) · "
                    f"탄수 {m['carbs_g']}g ({m['carbs_pct']}%) · "
                    f"지방 {m['fat_g']}g ({m['fat_pct']}%)"
                )
            if kcal_detail.get("bmr"):
                targets_block.append(
                    f"- BMR: {int(kcal_detail['bmr'])} kcal · TDEE: {int(kcal_detail['tdee'])} kcal"
                )
            if kcal_detail.get("days_left"):
                targets_block.append(f"- 목표일까지 D-{kcal_detail['days_left']}")
        ctx_md = "\n".join(targets_block) + "\n\n" + _build_plan_context(user_id, chat_id, date)

        data = await generate_daily_plan(ctx_md)
        if not data:
            return JSONResponse({"ok": False, "error": "계획 생성 실패"}, status_code=500)

        meals_dict = data.get("meals") or {}
        breakfast_html = _render_meal_html(meals_dict.get("breakfast"))
        lunch_html = _render_meal_html(meals_dict.get("lunch"))
        dinner_html = _render_meal_html(meals_dict.get("dinner"))

        target_intake = data.get("target_kcal_intake") or kcal_detail.get("target_kcal")
        if not data.get("macros") and kcal_detail.get("macros"):
            data["macros"] = kcal_detail["macros"]

        upsert_daily_plan(
            user_id, chat_id, date,
            target_intake,
            data.get("target_kcal_burn"),
            breakfast_html,
            lunch_html,
            dinner_html,
            json.dumps(data, ensure_ascii=False),
        )

        plan = get_daily_plan(user_id, date)
        payload = _serialize_plan(plan)
        payload["ok"] = True
        payload["cached"] = False
        return JSONResponse(payload)
    except Exception as e:
        logger.error(f"App plan generation error: {e}")
        return JSONResponse({"ok": False, "error": f"계획 생성 중 오류: {e}"}, status_code=500)


@app.post("/api/app/daily-summary")
async def api_app_daily_summary(request: Request):
    """Generate (or return cached) end-of-day summary via generate_daily_summary.

    Body JSON: { "user_id": int, "refresh": bool? }
    Named /daily-summary to avoid clashing with GET /api/app/summary.
    """
    if not _check_app_token(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON body required"}, status_code=400)

    try:
        user_id = int(body.get("user_id"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "user_id required"}, status_code=400)

    refresh = bool(body.get("refresh", False))
    date = _app_today_str()
    chat_id = _resolve_app_chat_id(user_id)
    _ensure_app_user(user_id, chat_id)

    cached = get_daily_summary(user_id, date)
    if cached and not refresh:
        payload = _serialize_daily_summary(cached)
        payload["ok"] = True
        payload["cached"] = True
        return JSONResponse(payload)

    try:
        ctx_md = _build_plan_context(user_id, chat_id, date)
        data = await generate_daily_summary(ctx_md)
        if not data:
            return JSONResponse({"ok": False, "error": "요약 생성 실패"}, status_code=500)

        summary_md = data.get("summary_md", "")
        assessment = data.get("goal_assessment_md", "")
        upsert_daily_summary(user_id, chat_id, date, summary_md, assessment)

        payload = {
            "ok": True,
            "cached": False,
            "date": date,
            "summary_md": summary_md,
            "goal_assessment_md": assessment,
        }
        return JSONResponse(payload)
    except Exception as e:
        logger.error(f"App daily summary error: {e}")
        return JSONResponse({"ok": False, "error": f"요약 생성 중 오류: {e}"}, status_code=500)


# ── v2: Agent chat API ───────────────────────────────────────────────────

from bot import inbody_api as _inbody_api
from bot.agent import run_agent_turn
from bot.database import get_chat_history, save_chat_message, save_inbody as _save_inbody_v2


def _photo_result_to_cards(result: dict) -> list[dict]:
    """Convert /api/app/upload-style pipeline results into chat cards."""
    cards: list[dict] = []
    intent = result.get("intent")
    if intent == "meal":
        for meal in result.get("meals") or []:
            type_ko = {"breakfast": "아침", "lunch": "점심", "dinner": "저녁", "snack": "간식"}.get(
                meal.get("meal_type"), meal.get("meal_type", ""))
            kcal = meal.get("estimated_kcal")
            cards.append({
                "kind": "meal",
                "ref_id": meal.get("id"),
                "title": f"식사 기록 · {type_ko}",
                "rows": [
                    ["내용", (meal.get("structured_md") or "")[:120]],
                    ["칼로리", f"{kcal:,.0f} kcal" if kcal else "—"],
                ],
                "meta": meal.get("date") or "",
            })
    elif intent == "inbody":
        ib = result.get("inbody") or {}
        def _f(v, unit="", d=1):
            try:
                return f"{float(v):,.{d}f}{unit}"
            except (TypeError, ValueError):
                return "—"
        cards.append({
            "kind": "inbody",
            "ref_id": ib.get("id"),
            "title": "인바디 기록",
            "rows": [
                ["측정일", str(ib.get("measured_at") or "")[:10]],
                ["체중 / 골격근 / 체지방률",
                 f"{_f(ib.get('weight_kg'))} / {_f(ib.get('skeletal_muscle_kg'))} / {_f(ib.get('body_fat_pct'), '%')}"],
                ["기초대사량", _f(ib.get("bmr_kcal"), " kcal", 0)],
            ],
            "meta": str(ib.get("measured_at") or "")[:10],
        })
    elif intent == "workout":
        for rec in result.get("records") or []:
            cards.append({
                "kind": "workout",
                "ref_id": rec.get("id"),
                "title": f"운동 기록 · {rec.get('category') or '기타'}",
                "rows": [["내용", (rec.get("structured_md") or "")[:160]]],
                "meta": rec.get("date") or "",
            })
    return cards


@app.post("/api/v2/chat")
async def api_v2_chat(
    request: Request,
    photo: Optional[UploadFile] = File(None),
    user_id: Optional[int] = Form(None),
    text: str = Form(""),
):
    """Agent chat endpoint. Multipart (photo optional) or JSON {user_id, text}.

    Text-only -> tool-calling agent loop.
    Photo -> existing classify/extract pipeline (no LLM loop), result as cards.
    """
    if not _check_app_token(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    image_bytes = b""
    if photo is not None:
        image_bytes = await photo.read()
    if user_id is None:
        try:
            body = await request.json()
            user_id = int(body.get("user_id"))
            text = (body.get("text") or "").strip()
        except Exception:
            return JSONResponse({"error": "user_id required"}, status_code=400)

    text = (text or "").strip()
    if not text and not image_bytes:
        return JSONResponse({"error": "text or photo required"}, status_code=400)
    if len(text) > 8000:
        return JSONResponse({"error": "text too long"}, status_code=400)

    chat_id = _resolve_app_chat_id(user_id)
    _ensure_app_user(user_id, chat_id)
    date = _app_today_str()

    try:
        if image_bytes:
            if len(image_bytes) > 12 * 1024 * 1024:
                return JSONResponse({"error": "이미지가 너무 큽니다 (최대 12MB)"}, status_code=400)
            save_chat_message(user_id, "user", text or "[사진]")
            try:
                intent_data = await classify_intent_from_image(image_bytes, hint=text)
            except Exception as e:
                logger.error(f"v2 chat intent error: {e}")
                intent_data = {"intent": "workout", "confidence": 0.3}
            intent = (intent_data.get("intent") or "workout").lower()

            if intent == "inbody":
                result = await _app_process_inbody_image(chat_id, user_id, image_bytes, text, date)
            elif intent == "meal":
                meal_type = (intent_data.get("meal_type") or "").lower() or _meal_type_by_time()
                if meal_type not in ("breakfast", "lunch", "dinner", "snack"):
                    meal_type = _meal_type_by_time()
                result = await _app_process_meal_image(chat_id, user_id, image_bytes, text, date, meal_type)
            elif intent == "unrelated":
                result = {"ok": False, "intent": "unrelated",
                          "error": "운동·식단·인바디 어느 것에도 해당되지 않는 사진 같아요."}
            else:
                result = await _app_process_workout_image(chat_id, user_id, image_bytes, text, date)

            cards = _photo_result_to_cards(result) if result.get("ok") else []
            if result.get("ok"):
                reply_md = result.get("message") or "저장했어요."
            else:
                reply_md = result.get("error") or "사진을 인식하지 못했어요."
            save_chat_message(
                user_id, "assistant", reply_md,
                cards_json=json.dumps(cards, ensure_ascii=False) if cards else None,
            )
            return JSONResponse({"ok": bool(result.get("ok")), "reply_md": reply_md, "cards": cards})

        turn = await run_agent_turn(user_id, chat_id, text)
        return JSONResponse({"ok": True, "reply_md": turn["reply_md"], "cards": turn["cards"]})
    except Exception as e:
        logger.exception("v2 chat error")
        return JSONResponse({"ok": False, "error": f"처리 중 오류: {e}"}, status_code=500)


@app.get("/api/v2/chat/history")
async def api_v2_chat_history(request: Request, user_id: int = Query(...), limit: int = Query(50)):
    if not _check_app_token(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    limit = max(1, min(limit, 200))
    messages = get_chat_history(user_id, limit=limit)
    out = []
    for m in messages:
        cards = []
        if m.get("cards_json"):
            try:
                cards = json.loads(m["cards_json"])
            except ValueError:
                cards = []
        out.append({
            "id": m["id"],
            "role": m["role"],
            "content": m.get("content") or "",
            "cards": cards,
            "created_at": m.get("created_at"),
        })
    return JSONResponse({"ok": True, "messages": out})


@app.post("/api/v2/inbody/sync")
async def api_v2_inbody_sync(request: Request):
    """Fetch latest measurement from LookinBody WebAPI by phone and store it."""
    if not _check_app_token(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
        user_id = int(body.get("user_id"))
    except Exception:
        return JSONResponse({"error": "user_id required"}, status_code=400)
    phone = (body.get("phone") or "").strip()
    if not phone:
        return JSONResponse({"error": "phone required"}, status_code=400)
    if not _inbody_api.is_configured():
        return JSONResponse(
            {"ok": False, "error": "InBody 연동이 아직 설정되지 않았습니다."}, status_code=503)

    chat_id = _resolve_app_chat_id(user_id)
    _ensure_app_user(user_id, chat_id)
    try:
        measurements = await _inbody_api.fetch_measurements(phone)
    except RuntimeError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)
    if not measurements:
        return JSONResponse({"ok": False, "error": "조회된 측정 데이터가 없습니다."}, status_code=404)

    latest = dict(measurements[0])
    raw_json = latest.pop("raw_json", "")
    measured_at = str(latest.pop("measured_at", None) or _app_today_str())
    inbody_id = _save_inbody_v2(chat_id, user_id, measured_at, latest, raw_json=raw_json)
    return JSONResponse({
        "ok": True,
        "inbody": {"id": inbody_id, "measured_at": measured_at, **latest},
        "count_available": len(measurements),
    })
