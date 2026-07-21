import asyncio
import html
import json
import logging
import os
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

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
    group_by_date,
    is_fitness_relevant_text,
    is_workout_text,
    recommend_workout,
    strip_date_line,
)
from bot.database import (
    GOAL_METRICS,
    add_group_member,
    create_goal,
    delete_all_records,
    delete_goal,
    delete_inbody,
    delete_meal,
    delete_record,
    compute_target_kcal_detailed,
    estimate_daily_target_kcal,
    get_daily_plan,
    get_daily_summary,
    get_group_clients,
    get_inbody_history,
    get_last_record,
    get_latest_inbody,
    get_meals_for_date,
    get_primary_goal,
    get_recent_records,
    get_records_for_date,
    get_stats,
    get_today_record,
    get_user_by_username,
    get_user_height,
    get_user_weight,
    is_trainer_in_chat,
    list_goals,
    merge_record,
    save_inbody,
    save_meal,
    save_record,
    set_height,
    set_primary_goal,
    set_trainer,
    set_weight,
    unset_trainer,
    update_goal_status,
    update_record_date,
    upsert_daily_plan,
    upsert_daily_summary,
    upsert_user,
)
from bot.utils import check_rate_limit, format_history_summary

logger = logging.getLogger(__name__)


WEB_URL = os.environ.get("WEB_URL", "https://workoutbot-ybbz.onrender.com")


def _dashboard_kb() -> InlineKeyboardMarkup:
    """Inline URL button that opens the dashboard in the phone's default browser.
    Telegram's chat/menu button can only host a WebApp (in-app browser) or the
    command list — an inline url button is the only way to hand off to the
    external browser."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🌐 대시보드 열기 (브라우저)", url=WEB_URL)]])


async def _safe_edit(status_msg, text: str, **kwargs):
    """edit_text that tolerates Telegram's 'Message is not modified' 400.

    Editing a message to content identical to what it already shows raises
    BadRequest. That is harmless (the message already says what we want), so
    swallow it instead of letting it bubble up as a fake '분석 중 오류'."""
    try:
        return await status_msg.edit_text(text, **kwargs)
    except BadRequest as e:
        if "not modified" in str(e).lower():
            return status_msg
        raise


def _track_group_member(update: Update) -> None:
    """Auto-register sender as group member if in a group chat."""
    chat = update.effective_chat
    user = update.effective_user
    if chat and user and chat.type in ("group", "supergroup"):
        add_group_member(chat.id, user.id)
        upsert_user(user.id, chat.id, user.full_name, username=user.username)


async def cmd_settrainer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("이 명령어는 그룹에서만 사용 가능합니다.")
        return
    # Check if command issuer is admin
    member = await chat.get_member(update.effective_user.id)
    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("❌ 그룹 관리자만 사용할 수 있습니다.")
        return

    target_id, target_name = None, None

    # 방법 1: 답장 방식
    if update.message.reply_to_message:
        t = update.message.reply_to_message.from_user
        target_id, target_name = t.id, t.full_name

    # 방법 2: @멘션 방식 (/settrainer @username)
    elif context.args:
        mention = context.args[0].lstrip("@")
        user_row = get_user_by_username(chat.id, mention)
        if not user_row:
            await update.message.reply_text(
                f"❌ @{mention} 유저를 찾을 수 없습니다.\n"
                "해당 유저가 아직 이 채팅에서 메시지를 보낸 적이 없으면 등록이 불가능합니다.\n"
                "또는 메시지에 답장하는 방식을 사용하세요."
            )
            return
        target_id, target_name = user_row["user_id"], user_row["name"]

    else:
        await update.message.reply_text(
            "사용법:\n"
            "• 답장 방식: 트레이너 메시지에 답장 후 /settrainer\n"
            "• 멘션 방식: /settrainer @유저네임"
        )
        return

    set_trainer(chat.id, target_id)
    await update.message.reply_text(f"✅ {target_name}님이 트레이너로 설정되었습니다.")


async def cmd_unsettrainer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("이 명령어는 그룹에서만 사용 가능합니다.")
        return
    member = await chat.get_member(update.effective_user.id)
    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("❌ 그룹 관리자만 사용할 수 있습니다.")
        return

    target_id, target_name = None, None

    # 방법 1: 답장 방식
    if update.message.reply_to_message:
        t = update.message.reply_to_message.from_user
        target_id, target_name = t.id, t.full_name

    # 방법 2: @멘션 방식
    elif context.args:
        mention = context.args[0].lstrip("@")
        user_row = get_user_by_username(chat.id, mention)
        if not user_row:
            await update.message.reply_text(
                f"❌ @{mention} 유저를 찾을 수 없습니다.\n"
                "메시지에 답장하는 방식을 사용하세요."
            )
            return
        target_id, target_name = user_row["user_id"], user_row["name"]

    else:
        await update.message.reply_text(
            "사용법:\n"
            "• 답장 방식: 트레이너 메시지에 답장 후 /unsettrainer\n"
            "• 멘션 방식: /unsettrainer @유저네임"
        )
        return

    unset_trainer(chat.id, target_id)
    await update.message.reply_text(f"✅ {target_name}님의 트레이너 권한이 해제되었습니다.")


# Album buffer: collect multiple photos sent as album
# Key: (chat_id, user_id) -> {images: [bytes], timer: Task, status_msg, update}
_album_buffers: dict[tuple, dict] = {}
ALBUM_WAIT_SECONDS = 2.0  # wait for more photos in album


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id
    upsert_user(user.id, chat_id, user.full_name)

    weight = get_user_weight(user.id, chat_id)
    height = get_user_height(user.id, chat_id)

    # If already set up, show welcome back
    if weight and height:
        await update.message.reply_text(
            f"🏋️ <b>운동 기록 분석 봇</b>\n\n"
            f"안녕하세요, {user.first_name}님! (체중: {weight}kg, 키: {height}cm)\n\n"
            "운동 기록을 사진이나 텍스트로 보내주세요. 자동으로 분석해드립니다!\n\n"
            "아래 버튼으로 웹 대시보드를 열 수 있습니다.\n"
            "전체 명령어는 /help 를 확인해주세요.",
            parse_mode="HTML",
            reply_markup=_dashboard_kb(),
        )
        return

    # Onboarding flow
    await update.message.reply_text(
        "🏋️ <b>운동 기록 분석 봇</b>에 오신 것을 환영합니다!\n\n"
        "이 봇은 운동 기록(텍스트 또는 이미지)을 AI로 분석하여\n"
        "전문가 수준의 피드백과 칼로리 추정을 제공합니다.\n\n"
        "📸 <b>사용법:</b>\n"
        "• 운동 기록 사진을 보내면 자동 분석 (여러 장 OK)\n"
        "• 운동 내용을 텍스트로 입력해도 자동 감지\n\n"
        "⚙️ 먼저 정확한 칼로리 추정을 위해 신체 정보를 설정해주세요!\n\n"
        "👇 아래 명령어를 순서대로 입력해주세요:\n\n"
        "1️⃣ 체중 설정: /setweight [kg]\n"
        "   예: /setweight 75\n\n"
        "2️⃣ 키 설정: /setheight [cm]\n"
        "   예: /setheight 175\n\n"
        "설정 완료 후 운동 기록을 보내주시면 됩니다! 💪\n"
        "웹 대시보드는 아래 버튼으로 열 수 있습니다.\n"
        "전체 명령어는 /help 를 확인해주세요.",
        parse_mode="HTML",
        reply_markup=_dashboard_kb(),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 <b>도움말</b>\n\n"
        "운동·인바디·식단을 모두 기록하고 목표 달성까지 AI가 코칭합니다.\n\n"
        "<b>📋 기본:</b>\n"
        "• /start — 봇 소개\n"
        "• /help — 이 도움말\n\n"
        "<b>📊 운동 기록:</b>\n"
        "• 사진/텍스트를 보내면 자동 분석\n"
        "• /history — 최근 5개\n"
        "• /stats — 전체 통계\n"
        "• /analyze — 마지막 기록 재분석\n"
        "• /editdate [ID] [날짜] — 기록 날짜 수정\n"
        "• /delete [ID] / /delete all — 삭제\n\n"
        "<b>📏 인바디:</b>\n"
        "• /inbody — 인바디 사진과 함께 (캡션 또는 답장)\n\n"
        "<b>🍽️ 식단:</b>\n"
        "• /breakfast, /lunch, /dinner, /snack\n"
        "  예: /lunch 닭가슴살 200g + 현미밥\n"
        "  예: 사진에 캡션 /dinner\n\n"
        "<b>🎯 목표:</b>\n"
        "• /goal add 체중 75 2026-08-01\n"
        "• /goal add 체지방률 15 2026-09-01\n"
        "• /goal list / /goal primary [ID] / /goal done [ID] / /goal del [ID]\n\n"
        "<b>📅 일일 코칭:</b>\n"
        "• /plan — 오늘 권장 칼로리·식단 (LLM 생성)\n"
        "• /today — 오늘 요약 미리보기\n"
        "• 매일 <b>오후 9시(KST)</b> 자동 알림:\n"
        "   – 그룹: 🏆 오늘의 순위표 (회원별 운동·식단·칼로리 달성률·연속일·목표 진행률 랭킹)\n"
        "   – 개인 DM: 하루 요약·목표 평가\n\n"
        "<b>⚙️ 설정:</b>\n"
        "• /setweight [kg], /setheight [cm]\n\n"
        "<b>👥 그룹·트레이너 (관리자 전용):</b>\n"
        "• /settrainer, /unsettrainer (답장 또는 @멘션)\n"
        "• 트레이너는 매일 밤 <b>이탈 주의 회원</b>(3일+ 미기록)을 DM으로 자동 수신\n\n"
        "<b>🌐 웹 대시보드:</b>\n"
        "• 목표 카드 · 인바디 추이 · 일일 계획 · 식단 일지\n"
        "• 🎯 오늘의 칼로리 적자·운동 소비 표기\n"
        "• 📉 목표 칼로리 적자 달성 현황(필요 적자·하루 목표·누적 달성률·일자별 표)\n"
        "• 아래 버튼으로 브라우저에서 열기",
        parse_mode="HTML",
        reply_markup=_dashboard_kb(),
    )


async def cmd_setweight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("사용법: /setweight 75", parse_mode="HTML")
        return
    try:
        weight = float(context.args[0])
        if weight < 20 or weight > 300:
            raise ValueError
    except ValueError:
        await update.message.reply_text("올바른 체중을 입력해주세요 (20-300 kg)")
        return

    user = update.effective_user
    set_weight(user.id, update.effective_chat.id, weight)
    height = get_user_height(user.id, update.effective_chat.id)
    if not height:
        await update.message.reply_text(
            f"✅ 체중이 {weight}kg으로 설정되었습니다.\n\n"
            "👉 이제 키도 설정해주세요: /setheight [cm]\n"
            "예: /setheight 175"
        )
    else:
        await update.message.reply_text(
            f"✅ 체중이 {weight}kg으로 설정되었습니다.\n"
            f"현재 설정: 체중 {weight}kg, 키 {height}cm\n\n"
            "🎉 설정 완료! 운동 기록을 보내주세요 💪"
        )


async def cmd_setheight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("사용법: /setheight 175", parse_mode="HTML")
        return
    try:
        height = float(context.args[0])
        if height < 100 or height > 250:
            raise ValueError
    except ValueError:
        await update.message.reply_text("올바른 키를 입력해주세요 (100-250 cm)")
        return

    user = update.effective_user
    set_height(user.id, update.effective_chat.id, height)
    weight = get_user_weight(user.id, update.effective_chat.id)
    if not weight:
        await update.message.reply_text(
            f"✅ 키가 {height}cm으로 설정되었습니다.\n\n"
            "👉 이제 체중도 설정해주세요: /setweight [kg]\n"
            "예: /setweight 75"
        )
    else:
        await update.message.reply_text(
            f"✅ 키가 {height}cm으로 설정되었습니다.\n"
            f"현재 설정: 체중 {weight}kg, 키 {height}cm\n\n"
            "🎉 설정 완료! 운동 기록을 보내주세요 💪"
        )


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    records = get_recent_records(update.effective_chat.id, update.effective_user.id, 5)
    if not records:
        await update.message.reply_text("📭 아직 운동 기록이 없습니다.")
        return

    lines = ["📋 <b>최근 운동 기록</b>\n"]
    for i, r in enumerate(records, 1):
        kcal = f"{r['estimated_kcal']:.0f} kcal" if r.get("estimated_kcal") else "N/A"
        summary = (r.get("structured_md") or "")[:150].replace("\n", " ")
        lines.append(f"<b>{i}. {r['date']}</b> — {kcal}\n{summary}\n")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stats = get_stats(update.effective_chat.id, update.effective_user.id)
    cnt = stats.get("cnt", 0)
    if cnt == 0:
        await update.message.reply_text("📭 아직 운동 기록이 없습니다.")
        return

    avg_kcal = stats.get("avg_kcal") or 0
    total_kcal = stats.get("total_kcal") or 0
    await update.message.reply_text(
        f"📊 <b>운동 통계</b>\n\n"
        f"• 총 세션 수: <b>{cnt}</b>회\n"
        f"• 평균 칼로리: <b>{avg_kcal:.0f}</b> kcal\n"
        f"• 총 칼로리 소모: <b>{total_kcal:.0f}</b> kcal",
        parse_mode="HTML",
    )


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.reply_to_message:
        reply_msg = update.message.reply_to_message
        if reply_msg.photo:
            await _process_single_photo(update, context, reply_msg)
        elif reply_msg.text:
            await _process_text_workout(update, context, reply_msg.text, do_analyze=True)
        else:
            await update.message.reply_text("분석할 수 있는 메시지가 아닙니다.")
        return

    record = get_last_record(update.effective_chat.id, update.effective_user.id)
    if not record:
        await update.message.reply_text("📭 분석할 기록이 없습니다.")
        return

    await update.message.reply_text("🔄 마지막 기록을 분석 중...")
    try:
        weight = get_user_weight(update.effective_user.id, update.effective_chat.id)
        height = get_user_height(update.effective_user.id, update.effective_chat.id)
        history = get_recent_records(update.effective_chat.id, update.effective_user.id, 5)
        analysis = await analyze_workout(
            record["structured_md"], weight, format_history_summary(history), height_cm=height,
        )
        kcal = extract_kcal(analysis)
        # Persist the result so the web dashboard shows it without re-running.
        merge_record(record["id"], record["structured_md"], analysis, kcal, category=record.get("category"))
        await update.message.reply_text(analysis, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Re-analysis error: {e}")
        await update.message.reply_text("❌ 분석 중 오류가 발생했습니다.")


async def cmd_editdate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Change the date of a record. Usage: /editdate <record_id> <YYYY-MM-DD>"""
    if not context.args or len(context.args) < 2:
        # Show recent records to help user pick an ID
        records = get_recent_records(update.effective_chat.id, update.effective_user.id, 5)
        if not records:
            await update.message.reply_text("📭 수정할 기록이 없습니다.")
            return
        lines = ["사용법: /editdate [기록ID] [새날짜]\n예시: /editdate 3 2026-01-24\n\n<b>최근 기록:</b>"]
        for r in records:
            lines.append(f"• ID <b>{r['id']}</b> — {r['date']} ({(r.get('structured_md') or '')[:50]}...)")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    try:
        record_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("기록 ID는 숫자여야 합니다.")
        return

    new_date = context.args[1]
    # Validate date format
    try:
        datetime.strptime(new_date, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식으로 입력해주세요.\n예: 2026-01-24")
        return

    if update_record_date(record_id, new_date, update.effective_user.id):
        await update.message.reply_text(f"✅ 기록 #{record_id}의 날짜가 <b>{new_date}</b>로 수정되었습니다.", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ 수정 실패 — 해당 기록을 찾을 수 없거나 권한이 없습니다.")


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a record. Usage: /delete <record_id> or /delete all"""
    if not context.args:
        records = get_recent_records(update.effective_chat.id, update.effective_user.id, 5)
        if not records:
            await update.message.reply_text("📭 삭제할 기록이 없습니다.")
            return
        lines = ["사용법:\n• /delete [기록ID] — 개별 삭제\n• /delete all — 전체 삭제\n\n<b>최근 기록:</b>"]
        for r in records:
            lines.append(f"• ID <b>{r['id']}</b> — {r['date']} ({(r.get('structured_md') or '')[:50]}...)")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    arg = context.args[0].lower()

    if arg == "all":
        count = delete_all_records(update.effective_chat.id, update.effective_user.id)
        await update.message.reply_text(f"🗑️ {count}개 기록이 전체 삭제되었습니다.")
        return

    try:
        record_id = int(arg)
    except ValueError:
        await update.message.reply_text("기록 ID는 숫자여야 합니다. 전체 삭제는 /delete all")
        return

    if delete_record(record_id, update.effective_user.id):
        await update.message.reply_text(f"🗑️ 기록 #{record_id}이 삭제되었습니다.")
    else:
        await update.message.reply_text("❌ 삭제 실패 — 해당 기록을 찾을 수 없거나 권한이 없습니다.")


async def _resolve_target_user(update: Update, chat_id: int, sender_id: int) -> tuple[int, str | None]:
    """
    Determine the actual target user_id for saving records.
    If sender is a trainer:
      - reply to client msg → use that client's user_id
      - only 1 client in group → use that client
      - multiple clients → return (sender_id, error_msg)
    Otherwise → use sender_id.
    Returns (target_user_id, error_message_or_None)
    """
    if not is_trainer_in_chat(sender_id, chat_id):
        return sender_id, None

    # Sender is trainer — find target client
    # 1. If replying to a specific client's message
    if update.message.reply_to_message:
        replied_user = update.message.reply_to_message.from_user
        if replied_user and not is_trainer_in_chat(replied_user.id, chat_id):
            return replied_user.id, None

    # 2. Auto-detect if only 1 client in group
    clients = get_group_clients(chat_id)
    if len(clients) == 1:
        return clients[0]["user_id"], None
    elif len(clients) == 0:
        return sender_id, "⚠️ 그룹에 등록된 클라이언트가 없습니다."
    else:
        names = ", ".join(c.get("name") or f"ID:{c['user_id']}" for c in clients)
        return sender_id, f"⚠️ 클라이언트가 여러 명입니다. 해당 클라이언트의 메시지에 답장하며 이미지를 보내주세요.\n클라이언트: {names}"


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Buffer photos for album handling - wait briefly for more photos."""
    if update.effective_user.is_bot:
        return
    _track_group_member(update)

    chat_id = update.effective_chat.id
    user = update.effective_user

    # Resolve actual target user (trainer → client)
    target_user_id, err = await _resolve_target_user(update, chat_id, user.id)
    if err:
        await update.message.reply_text(err)
        return

    key = (chat_id, user.id)

    # Download this photo
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await file.download_as_bytearray())
    caption = (update.message.caption or "").strip()

    if key in _album_buffers:
        # Update target_user_id (use latest reply target)
        _album_buffers[key]["target_user_id"] = target_user_id
        # Add to existing buffer
        _album_buffers[key]["images"].append(image_bytes)
        if caption:
            _album_buffers[key]["captions"].append(caption)
        # Reset timer
        _album_buffers[key]["timer"].cancel()
        _album_buffers[key]["timer"] = asyncio.create_task(
            _process_album_after_delay(key, update, context)
        )
        # Update status message
        count = len(_album_buffers[key]["images"])
        try:
            await _album_buffers[key]["status_msg"].edit_text(
                f"📸 이미지 {count}장 수신 중... 잠시만 기다려주세요."
            )
        except Exception:
            pass
    else:
        # New album buffer
        status_msg = await update.message.reply_text("📸 이미지 분석 준비 중...")
        _album_buffers[key] = {
            "images": [image_bytes],
            "captions": [caption] if caption else [],
            "status_msg": status_msg,
            "update": update,
            "context": context,
            "target_user_id": target_user_id,
            "timer": asyncio.create_task(
                _process_album_after_delay(key, update, context)
            ),
        }


def _meal_type_by_time() -> str:
    """Default meal type based on current Asia/Seoul hour."""
    from zoneinfo import ZoneInfo
    h = datetime.now(ZoneInfo("Asia/Seoul")).hour
    if 4 <= h < 11:
        return "breakfast"
    if 11 <= h < 15:
        return "lunch"
    if 17 <= h < 22:
        return "dinner"
    return "snack"


def message_date_kst(message) -> str:
    """Date the user sent the message, in Asia/Seoul YYYY-MM-DD.

    Telegram's Message.date is timezone-aware UTC. Convert to KST so a record sent
    at 1 AM KST gets that day's date (not yesterday in UTC). Falls back to now()
    if message or date is missing.
    """
    from zoneinfo import ZoneInfo
    seoul = ZoneInfo("Asia/Seoul")
    dt = getattr(message, "date", None) if message is not None else None
    if dt is None:
        dt = datetime.now(seoul)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(seoul).strftime("%Y-%m-%d")


def format_meal_items_md(items: list) -> str:
    """Render an items list from extract_meal_* into HTML lines.
    Marks items whose kcal came from a printed menu source ('menu' tag) with 📋."""
    lines = []
    for it in items or []:
        name = it.get("name", "")
        amount = it.get("amount", "")
        kcal = it.get("kcal")
        p = it.get("protein_g")
        c = it.get("carbs_g")
        f = it.get("fat_g")
        source = it.get("source", "")
        prefix = "📋 " if source == "menu" else "• "
        kcal_str = f"{int(kcal)}kcal" if kcal is not None else "?kcal"
        macro_str = ""
        if any(v is not None for v in (p, c, f)):
            macro_str = f" · P{int(p or 0)}/C{int(c or 0)}/F{int(f or 0)}"
        amount_str = f" ({amount})" if amount else ""
        lines.append(f"{prefix}{name}{amount_str} — {kcal_str}{macro_str}")
    return "\n".join(lines)


def format_meal_kcal_status(user_id: int, date: str) -> str:
    """Build the kcal+macro status block appended to meal replies."""
    meals = get_meals_for_date(user_id, date)
    today_kcal = sum((m.get("estimated_kcal") or 0) for m in meals)
    today_p = sum((m.get("protein_g") or 0) for m in meals)
    today_c = sum((m.get("carbs_g") or 0) for m in meals)
    today_f = sum((m.get("fat_g") or 0) for m in meals)

    detail = compute_target_kcal_detailed(user_id, date)
    target = detail.get("target_kcal")
    macros = detail.get("macros")

    source_note = {
        "plan": "/plan 기반",
        "goal-derived": "목표·인바디 기반 자동 계산",
        "maintain-tdee": "유지 칼로리 (TDEE)",
    }.get(detail.get("source"), "")

    lines = [
        f"\n📊 <b>오늘 섭취</b>: {int(today_kcal)} kcal"
        + (f"  (P {int(today_p)}g · C {int(today_c)}g · F {int(today_f)}g)" if (today_p or today_c or today_f) else "")
    ]
    if target:
        remaining = target - today_kcal
        lines.append(f"🎯 목표: <b>{int(target)}</b> kcal" + (f" <i>({source_note})</i>" if source_note else ""))
        if macros:
            lines.append(
                f"   • 단백 <b>{macros['protein_g']}g</b> · "
                f"탄수 <b>{macros['carbs_g']}g</b> · "
                f"지방 <b>{macros['fat_g']}g</b>"
            )
        if remaining >= 0:
            lines.append(f"✅ 남은 허용: <b>{int(remaining)}</b> kcal")
        else:
            lines.append(f"⚠️ 초과: <b>{int(-remaining)}</b> kcal")
        if macros:
            rp = macros["protein_g"] - today_p
            rc = macros["carbs_g"] - today_c
            rf = macros["fat_g"] - today_f
            def fmt(label, val):
                if val > 0:
                    return f"{label} +{int(val)}g 더"
                return f"{label} -{int(-val)}g 초과"
            lines.append(f"   • {fmt('단백', rp)} · {fmt('탄수', rc)} · {fmt('지방', rf)}")
        if detail.get("source") == "goal-derived" and detail.get("reasoning_md"):
            lines.append(f"\n<blockquote>{detail['reasoning_md']}</blockquote>")
    else:
        lines.append("ℹ️ " + (detail.get("reasoning_md") or "/inbody 로 인바디 등록 후 /goal 로 목표 추가하세요."))
    return "\n".join(lines)


async def _process_album_after_delay(
    key: tuple, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Wait for album to complete, then classify intent and dispatch."""
    await asyncio.sleep(ALBUM_WAIT_SECONDS)

    buf = _album_buffers.pop(key, None)
    if not buf:
        return

    chat_id, sender_id = key
    user = update.effective_user
    target_user_id = buf.get("target_user_id", sender_id)
    images = buf["images"]
    captions = buf.get("captions", [])
    combined_caption = " ".join(captions).strip()
    status_msg = buf["status_msg"]

    if not check_rate_limit(chat_id):
        await status_msg.edit_text("⏳ 잠시 후 다시 시도해주세요 (속도 제한).")
        return

    upsert_user(user.id, chat_id, user.full_name)
    if target_user_id != user.id:
        upsert_user(target_user_id, chat_id, f"client_{target_user_id}")

    count = len(images)
    await status_msg.edit_text(f"🤔 사진 {count}장 분류 중...")

    # Classify intent on the first image, passing the caption as a strong hint —
    # a dumbbell photo plus "10kg x 10회 4세트" should classify as workout even
    # if the image alone is ambiguous.
    try:
        intent_data = await classify_intent_from_image(images[0], hint=combined_caption)
    except Exception as e:
        logger.error(f"Intent classification error: {e}")
        intent_data = {"intent": "workout", "confidence": 0.3}

    intent = (intent_data.get("intent") or "workout").lower()
    reason = intent_data.get("reason_md", "")
    logger.info(f"Image intent={intent} confidence={intent_data.get('confidence')} reason={reason} caption={combined_caption[:80]!r}")

    try:
        if intent == "inbody":
            await _process_inbody_image(update, chat_id, user, target_user_id, images[0], combined_caption, status_msg)
        elif intent == "meal":
            meal_type = (intent_data.get("meal_type") or "").lower() or _meal_type_by_time()
            if meal_type not in ("breakfast", "lunch", "dinner", "snack"):
                meal_type = _meal_type_by_time()
            await _process_meal_image(update, chat_id, user, target_user_id, images, meal_type, combined_caption, status_msg)
        elif intent == "unrelated":
            msg = "🤔 운동·식단·인바디 어느 것에도 해당되지 않는 사진으로 보입니다."
            if reason:
                msg += f"\n<i>{reason}</i>"
            await status_msg.edit_text(msg, parse_mode="HTML")
        else:
            await _process_workout_album(update, chat_id, user, target_user_id, images, combined_caption, status_msg)
    except Exception as e:
        logger.error(f"Dispatch error (intent={intent}): {e}")
        await status_msg.edit_text("❌ 분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")


async def _process_workout_album(
    update: Update, chat_id: int, user, target_user_id: int,
    images: list[bytes], caption: str, status_msg,
) -> None:
    """Extract workout records from one or more images (+ optional caption text), analyze, save."""
    from bot.analyzer import extract_from_image as _extract_from_image
    count = len(images)
    await status_msg.edit_text(f"📸 운동 기록 추출 중... (1/{count})")

    async def extract_one(idx, img):
        # Pass the caption to every image — it might describe sets/reps/weight
        # that aren't visible in the photo (e.g. dumbbell photo + "10kg x 10 x 4").
        result = await _extract_from_image(img, user_caption=caption)
        try:
            await status_msg.edit_text(f"📸 이미지 추출 중... ({idx + 1}/{count})")
        except Exception:
            pass
        return result

    extracted_results = await asyncio.gather(
        *[extract_one(i, img) for i, img in enumerate(images)],
        return_exceptions=True,
    )

    all_extracted = []
    for r in extracted_results:
        if isinstance(r, Exception):
            logger.error(f"Image extraction error: {r}")
            continue
        if "NO_WORKOUT_DATA" not in r:
            all_extracted.append(r)

    # If the image yielded nothing but the caption itself describes a workout,
    # fall back to text extraction on the caption — the photo was just context.
    if not all_extracted and caption and is_workout_text(caption):
        try:
            text_result = await extract_from_text(caption)
            if "NO_WORKOUT_DATA" not in text_result:
                all_extracted.append(text_result)
        except Exception as e:
            logger.error(f"Caption fallback extraction error: {e}")

    if not all_extracted:
        await status_msg.edit_text(
            "운동 사진으로 인식했지만 기록을 추출하지 못했습니다.\n"
            "글자가 잘 안 보이거나 손글씨라면 텍스트로 입력해주세요."
        )
        return

    msg_date = message_date_kst(update.message)
    date_groups = group_by_date(all_extracted, fallback_date=msg_date)

    raw_input_label = f"[image x{count}]"
    if caption:
        raw_input_label += f" caption: {caption}"

    saved_records = []
    for date, data_list in sorted(date_groups.items()):
        combined = "\n\n".join(data_list)
        category = classify_workout(combined)
        existing = get_today_record(chat_id, target_user_id, date)
        if existing:
            merged = existing["structured_md"] + "\n\n" + combined
            # Preserve any existing analysis/kcal; merge_record sets to None otherwise.
            merge_record(existing["id"], merged, existing.get("analysis") or "", existing.get("estimated_kcal"), category=category)
            saved_records.append((existing["id"], date, merged, True))
        else:
            new_id = save_record(chat_id, target_user_id, raw_input_label, combined, "", None, date=date, category=category)
            saved_records.append((new_id, date, combined, False))

    saved_for = f" (클라이언트 ID: {target_user_id} 기록으로 저장)" if target_user_id != user.id else ""
    header = f"✅ 운동 기록 저장 완료!{saved_for}"
    blocks = [header]
    for rec_id, date, structured, merged in saved_records:
        title = f"📅 <b>{date}</b>" + (" <i>(오늘 기록에 병합)</i>" if merged else "")
        body = html.escape((structured or "").strip())
        if len(body) > 1500:
            body = body[:1500] + "..."
        blocks.append(f"{title}\n<pre>{body}</pre>\nID {rec_id}")
    msg = "\n\n".join(blocks)
    await status_msg.edit_text(msg[:4000] if len(msg) > 4000 else msg, parse_mode="HTML")

    # Auto-analyze right after saving, then hand over a dashboard link.
    analyze_msg = await update.message.reply_text("📊 코치 분석 생성 중...")
    try:
        weight = get_user_weight(target_user_id, chat_id)
        height = get_user_height(target_user_id, chat_id)
        history = get_recent_records(chat_id, target_user_id, 5)
        last_analysis = None
        for rec_id, date, structured, merged in saved_records:
            analysis = await analyze_workout(
                structured, weight, format_history_summary(history), height_cm=height,
            )
            kcal = extract_kcal(analysis)
            # Persist so the web dashboard shows analysis + kcal without re-running.
            merge_record(rec_id, structured, analysis, kcal, category=classify_workout(structured))
            last_analysis = analysis
        if last_analysis:
            out = last_analysis[:4000]
            await analyze_msg.edit_text(out, parse_mode="HTML", reply_markup=_dashboard_kb())
        else:
            await analyze_msg.edit_text("❌ 분석 결과가 비어 있습니다.", reply_markup=_dashboard_kb())
    except Exception as e:
        logger.error(f"Auto-analysis error: {e}")
        await analyze_msg.edit_text(
            "⚠️ 기록은 저장됐지만 분석 생성에 실패했습니다. /analyze 로 다시 시도하세요.",
            reply_markup=_dashboard_kb(),
        )


async def _process_inbody_image(
    update: Update, chat_id: int, user, target_user_id: int,
    image_bytes: bytes, caption: str, status_msg,
) -> None:
    """Extract InBody metrics, save, and reply."""
    await status_msg.edit_text("📊 인바디 수치 추출 중...")
    metrics = await extract_inbody(image_bytes, user_caption=caption)
    if not metrics:
        await status_msg.edit_text("❌ 인바디 이미지로 인식했지만 수치 추출에 실패했습니다.")
        return

    msg_date = message_date_kst(update.message)
    measured_at = metrics.get("measured_at") or msg_date
    try:
        datetime.strptime(measured_at, "%Y-%m-%d")
    except (ValueError, TypeError):
        measured_at = msg_date

    clean = {k: metrics.get(k) for k in [
        "weight_kg", "skeletal_muscle_kg", "body_fat_kg", "body_fat_pct",
        "bmi", "bmr_kcal", "body_water_kg", "protein_kg", "mineral_kg", "visceral_fat_level",
    ] if metrics.get(k) is not None}

    save_inbody(chat_id, target_user_id, measured_at, clean, json.dumps(metrics, ensure_ascii=False))

    lines = [f"✅ <b>인바디 저장 완료</b> ({measured_at})"]
    label_map = {
        "weight_kg": ("체중", "kg"),
        "skeletal_muscle_kg": ("골격근량", "kg"),
        "body_fat_kg": ("체지방량", "kg"),
        "body_fat_pct": ("체지방률", "%"),
        "bmi": ("BMI", ""),
        "bmr_kcal": ("기초대사량", "kcal"),
        "body_water_kg": ("체수분", "kg"),
        "protein_kg": ("단백질", "kg"),
        "mineral_kg": ("무기질", "kg"),
        "visceral_fat_level": ("내장지방 레벨", ""),
    }
    for key, (label, unit) in label_map.items():
        v = clean.get(key)
        if v is not None:
            lines.append(f"• {label}: <b>{v}</b>{unit}")
    if target_user_id != user.id:
        lines.append(f"\n(클라이언트 ID: {target_user_id} 기록으로 저장)")
    await status_msg.edit_text("\n".join(lines), parse_mode="HTML")


async def _process_meal_image(
    update: Update, chat_id: int, user, target_user_id: int,
    images: list[bytes], default_meal_type: str, caption: str, status_msg,
    lock_to_default: bool = False,
) -> None:
    """Analyze a meal photo (uses first image). LLM decides meal_type splits."""
    await _safe_edit(status_msg, "🍽️ 식단 분석 중...")
    weight = get_user_weight(target_user_id, chat_id)
    height = get_user_height(target_user_id, chat_id)
    ctx_lines = []
    if weight:
        ctx_lines.append(f"사용자 체중: {weight}kg")
    if height:
        ctx_lines.append(f"키: {height}cm")
    if caption:
        ctx_lines.append(f"사용자 메모: {caption}")
    user_ctx = "\n".join(ctx_lines)

    data = await extract_meal_from_image(images[0], default_meal_type, user_ctx, lock_to_default=lock_to_default)
    saved = await _save_meals_from_extraction(
        update, chat_id, user, target_user_id, data, raw_label_prefix=f"[image] {caption}".strip(),
        default_meal_type=default_meal_type,
    )
    if not saved:
        await status_msg.edit_text(
            "❌ 식사로 인식했지만 음식 정보를 추출하지 못했습니다.\n"
            "<i>무엇을 드셨는지 텍스트로 알려주시면 다시 시도할게요. 예: '닭가슴살 200g + 현미밥'</i>",
            parse_mode="HTML",
        )
        return

    date = message_date_kst(update.message)
    reply = _format_multi_meal_reply(saved, date, target_user_id, user.id)
    if len(images) > 1:
        reply += f"\n<i>(첫 번째 사진만 분석. 나머지 {len(images)-1}장은 무시.)</i>"
    await status_msg.edit_text(reply, parse_mode="HTML")


async def _save_meals_from_extraction(
    update: Update, chat_id: int, user, target_user_id: int,
    data: dict, raw_label_prefix: str, default_meal_type: str,
) -> list:
    """Persist all meal_type entries from the LLM result. Returns list of saved tuples
    (meal_type, items_md, structured_md, analysis_md, kcal, macros)."""
    meals_by_type = (data or {}).get("meals_by_type") or {}
    # Backward-compat: if LLM returned old single-meal shape, wrap it
    if not meals_by_type and (data or {}).get("items"):
        meals_by_type = {default_meal_type: {
            "items": data["items"],
            "total_kcal": data.get("total_kcal"),
            "protein_g": data.get("protein_g"),
            "carbs_g": data.get("carbs_g"),
            "fat_g": data.get("fat_g"),
            "summary_md": data.get("summary_md", ""),
            "analysis_md": data.get("analysis_md", ""),
        }}

    date = message_date_kst(update.message)
    saved = []
    for meal_type, meal_data in meals_by_type.items():
        if meal_type not in ("breakfast", "lunch", "dinner", "snack"):
            continue
        items = (meal_data or {}).get("items") or []
        if not items:
            continue
        items_md = format_meal_items_md(items)
        structured_md = meal_data.get("summary_md") or items_md
        analysis_md = meal_data.get("analysis_md", "")
        kcal = meal_data.get("total_kcal")
        macros = {
            "protein_g": meal_data.get("protein_g"),
            "carbs_g": meal_data.get("carbs_g"),
            "fat_g": meal_data.get("fat_g"),
        }
        save_meal(chat_id, target_user_id, date, meal_type, raw_label_prefix,
                  structured_md, kcal, macros, analysis_md)
        saved.append((meal_type, items_md, structured_md, analysis_md, kcal, macros))
    return saved


def _format_multi_meal_reply(saved: list, date: str, target_user_id: int, sender_id: int) -> str:
    """Combine multiple meal save results into one reply with kcal status at the end."""
    type_label = {
        "breakfast": "🌅 아침", "lunch": "☀️ 점심",
        "dinner": "🌙 저녁",   "snack": "🍪 간식",
    }
    order = {"breakfast": 0, "lunch": 1, "dinner": 2, "snack": 3}
    saved_sorted = sorted(saved, key=lambda s: order.get(s[0], 99))

    blocks = []
    for meal_type, items_md, structured_md, analysis_md, kcal, _macros in saved_sorted:
        kcal_str = f"{int(kcal)} kcal" if kcal else "?"
        section = [f"{type_label.get(meal_type, meal_type)} ({date}) — <b>{kcal_str}</b>", ""]
        if items_md:
            section.append(items_md)
        if analysis_md:
            section += ["", analysis_md]
        blocks.append("\n".join(section))

    reply = "\n\n".join(blocks)
    if len(saved) > 1:
        reply = f"✅ {len(saved)}개 식사 저장됨\n\n" + reply
    reply += format_meal_kcal_status(target_user_id, date)
    if target_user_id != sender_id:
        reply += f"\n\n(클라이언트 ID: {target_user_id} 기록으로 저장)"
    return reply


async def _process_single_photo(
    update: Update, context: ContextTypes.DEFAULT_TYPE, source_message
) -> None:
    """Process a single photo (for /analyze reply)."""
    chat_id = update.effective_chat.id
    user = update.effective_user

    upsert_user(user.id, chat_id, user.full_name)

    photo = source_message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await file.download_as_bytearray())

    status_msg = await update.message.reply_text("📸 이미지 분석 중...")

    caption = (source_message.caption or "").strip()

    try:
        structured = await extract_from_image(image_bytes, user_caption=caption)
        if "NO_WORKOUT_DATA" in structured:
            await status_msg.edit_text("이 이미지에서 운동 기록을 찾을 수 없습니다.")
            return

        weight = get_user_weight(user.id, chat_id)
        height = get_user_height(user.id, chat_id)
        history = get_recent_records(chat_id, user.id, 5)
        analysis = await analyze_workout(
            structured, weight, format_history_summary(history), height_cm=height,
        )
        kcal = extract_kcal(analysis)
        category = classify_workout(structured)
        raw = f"[image] {caption}".strip() if caption else "[image]"
        save_record(chat_id, user.id, raw, structured, analysis, kcal, category=category)
        await status_msg.edit_text(analysis, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Photo analysis error: {e}")
        await status_msg.edit_text("❌ 분석 중 오류가 발생했습니다.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    if update.effective_user.is_bot:
        return
    _track_group_member(update)
    text = update.message.text
    if text.startswith("/"):
        return
    # Gate the LLM classifier behind a cheap keyword filter so random group-chat
    # chitchat doesn't trigger an API call. Anything matching workout/meal/inbody
    # vocabulary or numeric patterns (sets, weights, kcal) goes to the classifier.
    if not is_fitness_relevant_text(text):
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    target_user_id, err = await _resolve_target_user(update, chat_id, user.id)
    if err:
        await update.message.reply_text(err)
        return

    if not check_rate_limit(chat_id):
        return

    upsert_user(user.id, chat_id, user.full_name)
    if target_user_id != user.id:
        upsert_user(target_user_id, chat_id, f"client_{target_user_id}")

    # Workout recommendation request ("오늘 운동 추천해줘") — handle before the
    # log classifier, otherwise it gets read as a workout log and fails extraction.
    if _is_workout_recommend_request(text):
        await _process_workout_recommendation(update, chat_id, target_user_id)
        return

    status_msg = await update.message.reply_text("🤔 분류 중...")

    try:
        intent_data = await classify_intent_from_text(text)
    except Exception as e:
        logger.error(f"Text intent classification error: {e}")
        intent_data = {"intent": "workout", "confidence": 0.3}

    intent = (intent_data.get("intent") or "workout").lower()
    reason = intent_data.get("reason_md", "")
    logger.info(f"Text intent={intent} confidence={intent_data.get('confidence')} reason={reason}")

    try:
        if intent == "meal":
            meal_type = (intent_data.get("meal_type") or "").lower() or _meal_type_by_time()
            if meal_type not in ("breakfast", "lunch", "dinner", "snack"):
                meal_type = _meal_type_by_time()
            await _process_meal_text(update, chat_id, user, target_user_id, text, meal_type, status_msg)
        elif intent == "inbody":
            await status_msg.edit_text(
                "📊 인바디 수치는 사진으로 보내주세요. (텍스트 입력 미지원)"
            )
        elif intent == "unrelated":
            msg = "🤔 운동·식단·인바디 어느 것에도 해당되지 않아 보입니다."
            if reason:
                msg += f"\n<i>{reason}</i>"
            await status_msg.edit_text(msg, parse_mode="HTML")
        else:
            await _process_text_workout(update, context, text, status_msg=status_msg, target_user_id=target_user_id)
    except Exception as e:
        logger.error(f"Text dispatch error (intent={intent}): {e}")
        await status_msg.edit_text("❌ 분석 중 오류가 발생했습니다.")


_RECOMMEND_KEYWORDS = ("추천", "뭐 하", "뭐하", "무슨 운동", "어떤 운동", "뭘 해", "뭐 할까")


def _is_workout_recommend_request(text: str) -> bool:
    """Detect a workout-recommendation request (not a workout log).
    Requires a workout cue + a recommendation cue so meal/log text isn't caught."""
    t = text.lower()
    has_workout_cue = "운동" in t or "루틴" in t or "workout" in t
    has_recommend_cue = any(kw in t for kw in _RECOMMEND_KEYWORDS)
    return has_workout_cue and has_recommend_cue


async def _process_workout_recommendation(
    update: Update, chat_id: int, target_user_id: int
) -> None:
    """Recommend today's workout based on the user's recent workout history."""
    status_msg = await update.message.reply_text("🏋️ 최근 기록 참고해 추천 준비 중...")
    date = message_date_kst(update.message)
    try:
        ctx_md = _build_plan_context(target_user_id, chat_id, date)
        recommendation = await recommend_workout(ctx_md)
        if not recommendation.strip():
            await status_msg.edit_text("❌ 추천 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.")
            return
        await status_msg.edit_text(recommendation, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Workout recommendation error: {e}")
        await status_msg.edit_text("❌ 추천 생성 중 오류가 발생했습니다.")


async def _process_meal_text(
    update: Update, chat_id: int, user, target_user_id: int,
    text: str, default_meal_type: str, status_msg,
    lock_to_default: bool = False,
) -> None:
    await _safe_edit(status_msg, "🍽️ 식단 분석 중...")
    weight = get_user_weight(target_user_id, chat_id)
    height = get_user_height(target_user_id, chat_id)
    ctx_lines = []
    if weight:
        ctx_lines.append(f"사용자 체중: {weight}kg")
    if height:
        ctx_lines.append(f"키: {height}cm")
    user_ctx = "\n".join(ctx_lines)

    data = await extract_meal_from_text(text, default_meal_type, user_ctx, lock_to_default=lock_to_default)
    saved = await _save_meals_from_extraction(
        update, chat_id, user, target_user_id, data, raw_label_prefix=text,
        default_meal_type=default_meal_type,
    )
    if not saved:
        await status_msg.edit_text(
            "❌ 식사로 인식했지만 음식 구체화에 실패했습니다.\n"
            "<i>다시 시도하려면 음식명·분량을 명확히 적어주세요. 예: '닭가슴살 200g + 현미밥 한공기'</i>",
            parse_mode="HTML",
        )
        return

    date = message_date_kst(update.message)
    reply = _format_multi_meal_reply(saved, date, target_user_id, user.id)
    await status_msg.edit_text(reply, parse_mode="HTML")


async def _process_text_workout(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str,
    *, status_msg=None, target_user_id: int | None = None,
    do_analyze: bool = False,
) -> None:
    """Extract a workout from text and save. With do_analyze=True, also generate
    a full coach analysis (used by /analyze command). Default save-only path
    just stores the structured record and returns a brief confirmation."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    tuid = target_user_id if target_user_id is not None else user.id

    if status_msg is None:
        if not check_rate_limit(chat_id):
            return
        upsert_user(user.id, chat_id, user.full_name)
        status_msg = await update.message.reply_text("📝 운동 기록 추출 중...")
    else:
        await status_msg.edit_text("📝 운동 기록 추출 중...")

    try:
        structured = await extract_from_text(text)
        if "NO_WORKOUT_DATA" in structured:
            await status_msg.edit_text("운동 기록을 인식할 수 없습니다.")
            return

        msg_date = message_date_kst(update.message)
        # If the LLM extracted a DATE line from the user's text, honor it; otherwise
        # use the message send date so workouts logged from a phone always pin to
        # the day the user actually trained on.
        record_date = extract_date(structured) or msg_date
        structured_clean = strip_date_line(structured)
        existing = get_today_record(chat_id, tuid, record_date)
        category = classify_workout(structured_clean)

        if existing:
            merged_structured = existing["structured_md"] + "\n\n" + structured_clean
            structured_for_reply = merged_structured
            rec_id = existing["id"]
            if do_analyze:
                weight = get_user_weight(tuid, chat_id)
                height = get_user_height(tuid, chat_id)
                history = get_recent_records(chat_id, tuid, 5)
                analysis = await analyze_workout(
                    merged_structured, weight, format_history_summary(history), height_cm=height,
                )
                kcal = extract_kcal(analysis)
                merge_record(rec_id, merged_structured, analysis, kcal, category=classify_workout(merged_structured))
            else:
                merge_record(rec_id, merged_structured, existing.get("analysis") or "", existing.get("estimated_kcal"), category=classify_workout(merged_structured))
            merged_flag = True
        else:
            if do_analyze:
                weight = get_user_weight(tuid, chat_id)
                height = get_user_height(tuid, chat_id)
                history = get_recent_records(chat_id, tuid, 5)
                analysis = await analyze_workout(
                    structured_clean, weight, format_history_summary(history), height_cm=height,
                )
                kcal = extract_kcal(analysis)
                rec_id = save_record(chat_id, tuid, text, structured_clean, analysis, kcal, date=record_date, category=category)
            else:
                rec_id = save_record(chat_id, tuid, text, structured_clean, "", None, date=record_date, category=category)
            structured_for_reply = structured_clean
            merged_flag = False

        if do_analyze:
            await status_msg.edit_text(analysis, parse_mode="HTML")
        else:
            title = f"📅 <b>{record_date}</b>" + (" <i>(오늘 기록에 병합)</i>" if merged_flag else "")
            body = html.escape(structured_for_reply.strip())
            if len(body) > 1500:
                body = body[:1500] + "..."
            await status_msg.edit_text(
                f"✅ 운동 기록 저장 완료!\n\n{title}\n<pre>{body}</pre>\n"
                f"ID {rec_id} · 분석 리포트는 /analyze 또는 웹 대시보드에서 생성.",
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"Text workout error: {e}")
        await status_msg.edit_text("❌ 분석 중 오류가 발생했습니다.")


# ════════════════════════════════════════════════════════════
# InBody
# ════════════════════════════════════════════════════════════

async def cmd_inbody(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Analyze an InBody image. Usage: send image with /inbody caption, or reply to image with /inbody."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    _track_group_member(update)

    target_user_id, err = await _resolve_target_user(update, chat_id, user.id)
    if err:
        await update.message.reply_text(err)
        return

    # Get image from current message or replied message
    photo = None
    if update.message.photo:
        photo = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]

    if not photo:
        await update.message.reply_text(
            "사용법:\n"
            "• 인바디 사진을 보낼 때 캡션에 /inbody 입력\n"
            "• 또는 인바디 사진에 답장하며 /inbody 입력"
        )
        return

    status_msg = await update.message.reply_text("📊 인바디 분석 중...")

    try:
        file = await context.bot.get_file(photo.file_id)
        image_bytes = bytes(await file.download_as_bytearray())

        # If caption follows the slash command (e.g. "/inbody 2026-05-15"), pass it through
        caption = ""
        if update.message.photo and update.message.caption:
            caption = re.sub(r"^/inbody(@\w+)?\s*", "", update.message.caption).strip()
        elif update.message.reply_to_message and update.message.reply_to_message.caption:
            caption = update.message.reply_to_message.caption.strip()

        metrics = await extract_inbody(image_bytes, user_caption=caption)
        if not metrics:
            await status_msg.edit_text("❌ 인바디 이미지로 인식되지 않습니다.")
            return

        msg_date = message_date_kst(update.message)
        measured_at = metrics.get("measured_at") or msg_date
        try:
            datetime.strptime(measured_at, "%Y-%m-%d")
        except (ValueError, TypeError):
            measured_at = msg_date

        # Filter to known keys for save
        clean_metrics = {k: metrics.get(k) for k in [
            "weight_kg", "skeletal_muscle_kg", "body_fat_kg", "body_fat_pct",
            "bmi", "bmr_kcal", "body_water_kg", "protein_kg", "mineral_kg", "visceral_fat_level",
        ] if metrics.get(k) is not None}

        save_inbody(chat_id, target_user_id, measured_at, clean_metrics, json.dumps(metrics, ensure_ascii=False))

        lines = [f"✅ <b>인바디 저장 완료</b> ({measured_at})"]
        label_map = {
            "weight_kg": ("체중", "kg"),
            "skeletal_muscle_kg": ("골격근량", "kg"),
            "body_fat_kg": ("체지방량", "kg"),
            "body_fat_pct": ("체지방률", "%"),
            "bmi": ("BMI", ""),
            "bmr_kcal": ("기초대사량", "kcal"),
            "body_water_kg": ("체수분", "kg"),
            "protein_kg": ("단백질", "kg"),
            "mineral_kg": ("무기질", "kg"),
            "visceral_fat_level": ("내장지방 레벨", ""),
        }
        for key, (label, unit) in label_map.items():
            v = clean_metrics.get(key)
            if v is not None:
                lines.append(f"• {label}: <b>{v}</b>{unit}")

        suffix = f"\n\n(클라이언트 ID: {target_user_id} 기록으로 저장)" if target_user_id != user.id else ""
        await status_msg.edit_text("\n".join(lines) + suffix, parse_mode="HTML")
    except Exception as e:
        logger.error(f"InBody analysis error: {e}")
        await status_msg.edit_text("❌ 분석 중 오류가 발생했습니다.")


# ════════════════════════════════════════════════════════════
# Meals
# ════════════════════════════════════════════════════════════

async def _cmd_meal(update: Update, context: ContextTypes.DEFAULT_TYPE, meal_type: str) -> None:
    """Generic meal handler. meal_type: breakfast | lunch | dinner | snack."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    _track_group_member(update)

    target_user_id, err = await _resolve_target_user(update, chat_id, user.id)
    if err:
        await update.message.reply_text(err)
        return

    # Get image from current or replied message, or text args / replied text
    photo = None
    text_input = ""

    if update.message.photo:
        photo = update.message.photo[-1]
        text_input = update.message.caption or ""
    elif update.message.reply_to_message:
        if update.message.reply_to_message.photo:
            photo = update.message.reply_to_message.photo[-1]
        elif update.message.reply_to_message.text:
            text_input = update.message.reply_to_message.text

    if not text_input and context.args:
        text_input = " ".join(context.args)

    # If caption starts with /<meal_type> (e.g. "/lunch 닭가슴살"), strip the leading command
    # so the LLM only sees the food description, not the slash command.
    text_input = re.sub(rf"^/{meal_type}(@\w+)?\s*", "", text_input).strip()

    if not photo and not text_input:
        meal_label = {"breakfast": "아침", "lunch": "점심", "dinner": "저녁", "snack": "간식"}[meal_type]
        await update.message.reply_text(
            f"사용법 ({meal_label}):\n"
            f"• /{meal_type} 닭가슴살 200g, 현미밥 한공기\n"
            f"• 사진에 캡션 /{meal_type}\n"
            f"• 사진에 답장하며 /{meal_type}"
        )
        return

    status_msg = await update.message.reply_text("🍽️ 식단 분석 중...")

    try:
        # Slash commands lock the meal_type — user explicitly chose /breakfast etc.
        if photo:
            file = await context.bot.get_file(photo.file_id)
            image_bytes = bytes(await file.download_as_bytearray())
            await _process_meal_image(
                update, chat_id, user, target_user_id,
                [image_bytes], meal_type, text_input, status_msg,
                lock_to_default=True,
            )
        else:
            await _process_meal_text(
                update, chat_id, user, target_user_id,
                text_input, meal_type, status_msg,
                lock_to_default=True,
            )
    except Exception as e:
        logger.error(f"Meal command error: {e}")
        await status_msg.edit_text("❌ 분석 중 오류가 발생했습니다.")


async def cmd_breakfast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _cmd_meal(update, context, "breakfast")


async def cmd_lunch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _cmd_meal(update, context, "lunch")


async def cmd_dinner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _cmd_meal(update, context, "dinner")


async def cmd_snack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _cmd_meal(update, context, "snack")


# ════════════════════════════════════════════════════════════
# Goals
# ════════════════════════════════════════════════════════════

GOAL_METRIC_ALIASES = {
    "체중": "weight", "weight": "weight", "kg": "weight",
    "체지방률": "body_fat_pct", "체지방": "body_fat_pct", "bodyfat": "body_fat_pct", "fat": "body_fat_pct", "bf%": "body_fat_pct", "bf": "body_fat_pct",
    "체지방량": "body_fat_kg", "지방량": "body_fat_kg",
    "골격근량": "skeletal_muscle_kg", "근육": "skeletal_muscle_kg", "근육량": "skeletal_muscle_kg", "muscle": "skeletal_muscle_kg",
}


def _resolve_metric(raw: str) -> str | None:
    key = raw.strip().lower()
    if key in GOAL_METRIC_ALIASES:
        return GOAL_METRIC_ALIASES[key]
    if key in GOAL_METRICS:
        return key
    return None


def _format_goal_line(g: dict) -> str:
    label, unit = GOAL_METRICS.get(g["metric"], (g["metric"], ""))
    star = "⭐ " if g["is_primary"] else ""
    return (
        f"{star}ID <b>{g['id']}</b> — {label}: "
        f"{g.get('start_value') or '?'}{unit} → <b>{g['target_value']}{unit}</b> "
        f"by {g['target_date']}"
    )


async def cmd_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Goal CRUD.
    /goal add <metric> <target> <YYYY-MM-DD>
    /goal list
    /goal del <id>
    /goal primary <id>
    /goal done <id>
    """
    chat_id = update.effective_chat.id
    user = update.effective_user
    _track_group_member(update)

    target_user_id, err = await _resolve_target_user(update, chat_id, user.id)
    if err:
        await update.message.reply_text(err)
        return

    args = context.args
    if not args:
        # Default: list
        goals = list_goals(target_user_id)
        if not goals:
            await update.message.reply_text(
                "📭 활성 목표가 없습니다.\n\n"
                "사용법:\n"
                "• /goal add 체중 75 2026-08-01\n"
                "• /goal add 체지방률 15 2026-09-01\n"
                "• /goal add 골격근량 38 2026-12-31\n"
                "• /goal list — 목록 조회\n"
                "• /goal primary [ID] — 주 목표 지정\n"
                "• /goal done [ID] — 완료 처리\n"
                "• /goal del [ID] — 삭제"
            )
            return
        lines = ["🎯 <b>활성 목표</b>\n"]
        for g in goals:
            lines.append(_format_goal_line(g))
        lines.append("\n⭐ = 주 목표 (칼로리 계산 기준)")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    sub = args[0].lower()

    if sub == "list":
        goals = list_goals(target_user_id)
        if not goals:
            await update.message.reply_text("📭 활성 목표가 없습니다.")
            return
        lines = ["🎯 <b>활성 목표</b>\n"]
        for g in goals:
            lines.append(_format_goal_line(g))
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    if sub == "add":
        if len(args) < 4:
            await update.message.reply_text(
                "사용법: /goal add <지표> <목표값> <YYYY-MM-DD>\n"
                "예: /goal add 체중 75 2026-08-01\n"
                "지표: 체중 / 체지방률 / 체지방량 / 골격근량"
            )
            return
        metric = _resolve_metric(args[1])
        if not metric:
            await update.message.reply_text(
                "지표를 인식하지 못했습니다. (체중 / 체지방률 / 체지방량 / 골격근량 중 하나)"
            )
            return
        try:
            target_value = float(args[2])
        except ValueError:
            await update.message.reply_text("목표값은 숫자여야 합니다.")
            return
        target_date = args[3]
        try:
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text("날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식으로 입력해주세요.")
            return

        # Get start value from latest inbody
        latest = get_latest_inbody(target_user_id)
        start_value = None
        if latest:
            start_value = latest.get(metric)
        if start_value is None and metric == "weight":
            start_value = get_user_weight(target_user_id, chat_id)

        goal_id = create_goal(
            target_user_id, chat_id, metric, target_value, target_date,
            start_value=start_value,
        )
        label, unit = GOAL_METRICS[metric]
        await update.message.reply_text(
            f"✅ 목표 등록 (ID {goal_id}): {label} → {target_value}{unit} by {target_date}",
            parse_mode="HTML",
        )
        return

    if sub in ("del", "delete", "rm"):
        if len(args) < 2:
            await update.message.reply_text("사용법: /goal del [ID]")
            return
        try:
            gid = int(args[1])
        except ValueError:
            await update.message.reply_text("ID는 숫자여야 합니다.")
            return
        if delete_goal(gid, target_user_id):
            await update.message.reply_text(f"🗑️ 목표 #{gid} 삭제됨")
        else:
            await update.message.reply_text("❌ 삭제 실패")
        return

    if sub == "primary":
        if len(args) < 2:
            await update.message.reply_text("사용법: /goal primary [ID]")
            return
        try:
            gid = int(args[1])
        except ValueError:
            await update.message.reply_text("ID는 숫자여야 합니다.")
            return
        if set_primary_goal(gid, target_user_id):
            await update.message.reply_text(f"⭐ 목표 #{gid}이 주 목표로 설정되었습니다.")
        else:
            await update.message.reply_text("❌ 설정 실패")
        return

    if sub == "done":
        if len(args) < 2:
            await update.message.reply_text("사용법: /goal done [ID]")
            return
        try:
            gid = int(args[1])
        except ValueError:
            await update.message.reply_text("ID는 숫자여야 합니다.")
            return
        if update_goal_status(gid, target_user_id, "achieved"):
            await update.message.reply_text(f"🎉 목표 #{gid} 달성 처리!")
        else:
            await update.message.reply_text("❌ 처리 실패")
        return

    await update.message.reply_text(
        "알 수 없는 서브 명령어입니다.\n"
        "사용 가능: add / list / del / primary / done"
    )


# ════════════════════════════════════════════════════════════
# Plan / Today
# ════════════════════════════════════════════════════════════

def _build_plan_context(user_id: int, chat_id: int, date: str) -> str:
    """Build markdown context for plan/summary generation."""
    goals = list_goals(user_id)
    primary = get_primary_goal(user_id)
    latest_ib = get_latest_inbody(user_id)
    weight = get_user_weight(user_id, chat_id)
    height = get_user_height(user_id, chat_id)
    today_workouts = get_records_for_date(user_id, date)
    today_meals = get_meals_for_date(user_id, date)
    recent_workouts = get_recent_records(chat_id, user_id, 7)

    lines = [f"# 날짜: {date}", ""]

    # User profile
    lines.append("## 사용자 프로필")
    if weight:
        lines.append(f"- 체중: {weight}kg")
    if height:
        lines.append(f"- 키: {height}cm")
    if latest_ib:
        lines.append(f"- 최근 인바디 ({latest_ib['measured_at']}):")
        for key, (label, unit) in [
            ("weight_kg", ("체중", "kg")),
            ("skeletal_muscle_kg", ("골격근량", "kg")),
            ("body_fat_kg", ("체지방량", "kg")),
            ("body_fat_pct", ("체지방률", "%")),
            ("bmr_kcal", ("기초대사량", "kcal")),
            ("bmi", ("BMI", "")),
            ("visceral_fat_level", ("내장지방", "")),
        ]:
            v = latest_ib.get(key)
            if v is not None:
                lines.append(f"  • {label}: {v}{unit}")

    # Goals
    lines.append("\n## 활성 목표")
    if goals:
        for g in goals:
            label, unit = GOAL_METRICS.get(g["metric"], (g["metric"], ""))
            try:
                days_left = (datetime.strptime(g["target_date"], "%Y-%m-%d").date()
                             - datetime.strptime(date, "%Y-%m-%d").date()).days
            except Exception:
                days_left = "?"
            prefix = "★ (주 목표) " if g["is_primary"] else ""
            lines.append(
                f"- {prefix}{label}: {g.get('start_value') or '?'}{unit} → {g['target_value']}{unit} "
                f"by {g['target_date']} (남은일수: {days_left})"
            )
    else:
        lines.append("- 등록된 목표 없음")

    # Today's workouts
    lines.append("\n## 오늘의 운동")
    if today_workouts:
        for r in today_workouts:
            kcal = r.get("estimated_kcal")
            kcal_str = f" — {int(kcal)}kcal" if kcal else ""
            lines.append(f"- {r.get('category', '')}{kcal_str}: {(r.get('structured_md') or '')[:200]}")
    else:
        lines.append("- 아직 없음")

    # Recent workouts
    if recent_workouts:
        lines.append("\n## 최근 7개 운동 기록")
        for r in recent_workouts:
            lines.append(f"- {r['date']}: {r.get('category', '')} — {(r.get('structured_md') or '')[:150]}")

    # Today's meals
    lines.append("\n## 오늘의 식단")
    if today_meals:
        total_kcal = 0.0
        for m in today_meals:
            k = m.get("estimated_kcal") or 0
            total_kcal += k
            lines.append(f"- {m['meal_type']} — {int(k)}kcal: {(m.get('structured_md') or '')[:200]}")
        lines.append(f"- 합계: 약 {int(total_kcal)}kcal")
    else:
        lines.append("- 아직 없음")

    return "\n".join(lines)


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = update.effective_user
    _track_group_member(update)

    target_user_id, err = await _resolve_target_user(update, chat_id, user.id)
    if err:
        await update.message.reply_text(err)
        return

    date = message_date_kst(update.message)
    cached = get_daily_plan(target_user_id, date)
    refresh = bool(context.args and context.args[0].lower() in ("refresh", "new", "재생성"))

    if cached and not refresh:
        await _send_plan(update, cached)
        return

    if not list_goals(target_user_id):
        await update.message.reply_text(
            "🎯 활성 목표가 없어서 일일 계획을 생성할 수 없습니다.\n"
            "/goal add <지표> <값> <기한> 으로 먼저 목표를 등록해주세요."
        )
        return

    status_msg = await update.message.reply_text("📅 오늘의 계획 생성 중...")

    try:
        # Pre-compute calorie + macro targets so the LLM works backwards from them
        # instead of inventing its own numbers.
        kcal_detail = compute_target_kcal_detailed(target_user_id, date)
        targets_block = []
        if kcal_detail.get("target_kcal"):
            targets_block.append(f"## 사전 계산된 목표 (이 수치를 따르세요)")
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
                targets_block.append(f"- BMR: {int(kcal_detail['bmr'])} kcal · TDEE: {int(kcal_detail['tdee'])} kcal")
            if kcal_detail.get("days_left"):
                targets_block.append(f"- 목표일까지 D-{kcal_detail['days_left']}")
        ctx_md = "\n".join(targets_block) + "\n\n" + _build_plan_context(target_user_id, chat_id, date)

        data = await generate_daily_plan(ctx_md)
        if not data:
            await status_msg.edit_text("❌ 계획 생성 실패")
            return

        # Render each meal as HTML for the legacy *_suggestion columns and the reply.
        meals_dict = data.get("meals") or {}
        breakfast_html = _render_meal_html(meals_dict.get("breakfast"))
        lunch_html = _render_meal_html(meals_dict.get("lunch"))
        dinner_html = _render_meal_html(meals_dict.get("dinner"))

        # If LLM didn't provide intake target, fall back to our pre-computed one.
        target_intake = data.get("target_kcal_intake") or kcal_detail.get("target_kcal")
        if not data.get("macros") and kcal_detail.get("macros"):
            data["macros"] = kcal_detail["macros"]

        upsert_daily_plan(
            target_user_id, chat_id, date,
            target_intake,
            data.get("target_kcal_burn"),
            breakfast_html,
            lunch_html,
            dinner_html,
            json.dumps(data, ensure_ascii=False),
        )

        await status_msg.delete()
        await _send_plan(update, {
            "date": date,
            "target_kcal_intake": target_intake,
            "target_kcal_burn": data.get("target_kcal_burn"),
            "breakfast_suggestion": breakfast_html,
            "lunch_suggestion": lunch_html,
            "dinner_suggestion": dinner_html,
            "full_plan": json.dumps(data, ensure_ascii=False),
        })
    except Exception as e:
        logger.error(f"Plan generation error: {e}")
        await status_msg.edit_text("❌ 분석 중 오류가 발생했습니다.")


def _render_meal_html(meal: dict | None) -> str:
    """Render a meal dict (kcal/P/C/F/items/title/notes_md) as HTML for Telegram + dashboard."""
    if not meal:
        return ""
    parts = []
    title = meal.get("title", "")
    kcal = meal.get("kcal")
    p = meal.get("protein_g")
    c = meal.get("carbs_g")
    f = meal.get("fat_g")

    header_bits = []
    if title:
        header_bits.append(f"<b>{html.escape(title)}</b>")
    macro_line = []
    if kcal is not None:
        macro_line.append(f"{int(kcal)} kcal")
    if p is not None or c is not None or f is not None:
        macro_line.append(f"P {int(p or 0)}g · C {int(c or 0)}g · F {int(f or 0)}g")
    if macro_line:
        header_bits.append(f"<i>({' · '.join(macro_line)})</i>")
    if header_bits:
        parts.append(" ".join(header_bits))

    items = meal.get("items") or []
    for it in items:
        if isinstance(it, dict):
            name = html.escape(str(it.get("name", "")))
            amount = html.escape(str(it.get("amount", "")))
            ikcal = it.get("kcal")
            ip = it.get("protein_g")
            ic = it.get("carbs_g")
            ifa = it.get("fat_g")
            sub_bits = []
            if ikcal is not None:
                sub_bits.append(f"{int(ikcal)}kcal")
            if any(v is not None for v in (ip, ic, ifa)):
                sub_bits.append(f"P{int(ip or 0)}/C{int(ic or 0)}/F{int(ifa or 0)}")
            sub = f" — {' · '.join(sub_bits)}" if sub_bits else ""
            parts.append(f"• {name} ({amount}){sub}")
        else:
            parts.append(f"• {html.escape(str(it))}")
    if meal.get("notes_md"):
        parts.append(f"<i>{meal['notes_md']}</i>")
    return "\n".join(parts)


async def _send_plan(update: Update, plan: dict) -> None:
    try:
        full = json.loads(plan.get("full_plan") or "{}")
    except Exception:
        full = {}
    intake = plan.get("target_kcal_intake")
    burn = plan.get("target_kcal_burn")
    macros = full.get("macros") or {}
    parts = [f"📅 <b>오늘의 계획</b> ({plan.get('date', '')})\n"]
    if intake:
        parts.append(f"• 권장 섭취: <b>{int(intake)} kcal</b>")
    if macros and (macros.get("protein_g") or macros.get("carbs_g") or macros.get("fat_g")):
        parts.append(
            f"   • 단백 <b>{int(macros.get('protein_g', 0))}g</b> · "
            f"탄수 <b>{int(macros.get('carbs_g', 0))}g</b> · "
            f"지방 <b>{int(macros.get('fat_g', 0))}g</b>"
        )
    if burn:
        parts.append(f"• 권장 소모: <b>{int(burn)} kcal</b>")
    parts.append("")

    # Prefer the rich meal dicts from full_plan; fall back to legacy *_suggestion columns.
    meals_dict = (full.get("meals") or {})
    def block(emoji: str, label: str, key: str, legacy: str):
        meal = meals_dict.get(key)
        html_str = _render_meal_html(meal) if meal else legacy
        if html_str:
            parts.append(f"{emoji} <b>{label}</b>\n{html_str}\n")

    block("🌅", "아침", "breakfast", plan.get("breakfast_suggestion", ""))
    block("☀️", "점심", "lunch", plan.get("lunch_suggestion", ""))
    block("🌙", "저녁", "dinner", plan.get("dinner_suggestion", ""))
    snack = meals_dict.get("snack")
    if snack:
        snack_html = _render_meal_html(snack)
        if snack_html:
            parts.append(f"🍪 <b>간식</b>\n{snack_html}\n")

    if full.get("rationale_md"):
        parts.append(f"💡 <b>가이드</b>\n{full['rationale_md']}")

    msg = "\n".join(parts)
    # Telegram message length cap; split if needed
    if len(msg) > 4000:
        await update.message.reply_text(msg[:4000], parse_mode="HTML")
        await update.message.reply_text(msg[4000:], parse_mode="HTML")
    else:
        await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Preview today's end-of-day summary (same as 9pm push)."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    _track_group_member(update)

    target_user_id, err = await _resolve_target_user(update, chat_id, user.id)
    if err:
        await update.message.reply_text(err)
        return

    date = message_date_kst(update.message)
    status_msg = await update.message.reply_text("📊 오늘 요약 생성 중...")

    try:
        ctx_md = _build_plan_context(target_user_id, chat_id, date)
        data = await generate_daily_summary(ctx_md)
        if not data:
            await status_msg.edit_text("❌ 요약 생성 실패")
            return

        summary = data.get("summary_md", "")
        assessment = data.get("goal_assessment_md", "")
        upsert_daily_summary(target_user_id, chat_id, date, summary, assessment)

        parts = [f"🌙 <b>오늘 요약</b> ({date})\n"]
        if summary:
            parts.append(summary)
        if assessment:
            parts.append(f"\n🎯 <b>목표 평가</b>\n{assessment}")

        await status_msg.edit_text("\n".join(parts), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Today summary error: {e}")
        await status_msg.edit_text("❌ 분석 중 오류가 발생했습니다.")


def _fmt_scoreboard(board: dict) -> str:
    """Render the ranked group scoreboard as a Telegram monospace table.
    Shame/pride ritual — logged-today first, absentees sink to the bottom."""
    rows = board["rows"]
    date = board["date"]
    medals = ["🥇", "🥈", "🥉"]

    def clip(name: str, n: int = 6) -> str:
        name = name or "?"
        return name if len(name) <= n else name[: n - 1] + "…"

    header = f"🏆 <b>오늘의 순위표</b> ({date})\n"
    if not rows:
        return header + "\n아직 등록된 회원이 없습니다."

    lines = ["```",
             "순위 이름    운동 식단 칼로리 🔥연속 목표",
             "──────────────────────────────────────"]
    for i, r in enumerate(rows):
        rank = medals[i] if i < 3 else f"{i+1:>2}."
        nm = clip(r["name"]).ljust(6)
        w = "✅" if r["trained"] else "❌"
        me = "✅" if r["meal_logged"] else "❌"
        kc = f"{r['kcal_pct']}%" if r["kcal_pct"] is not None else "—"
        st = f"{r['streak']}일" if r["streak"] else "0"
        gp = f"{r['goal_pct']}%" if r["goal_pct"] is not None else "—"
        lines.append(f"{rank} {nm} {w}  {me}  {kc:>5} {st:>4} {gp:>4}")
    lines.append("```")

    absent = [r["name"] for r in rows if not r["logged_today"]]
    tail = ""
    if absent:
        tail = "\n😴 오늘 미기록: " + ", ".join(absent)
    return header + "\n".join(lines) + tail


async def daily_scoreboard_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback: post the ranked accountability scoreboard to each
    coach/client group at 21:00 KST. This is the product's core ritual."""
    from bot.database import get_scoreboard_chats, get_group_scoreboard
    from zoneinfo import ZoneInfo
    date = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    chats = get_scoreboard_chats()
    logger.info(f"Scoreboard job firing for {len(chats)} groups on {date}")
    for chat_id in chats:
        try:
            board = get_group_scoreboard(chat_id, date)
            if not board["rows"]:
                continue
            text = _fmt_scoreboard(board)
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            await _alert_trainers_silent_clients(context, chat_id, board)
        except Exception as e:
            logger.error(f"Scoreboard failed for chat {chat_id}: {e}")


async def _alert_trainers_silent_clients(context, chat_id: int, board: dict, threshold: int = 3) -> None:
    """DM each trainer of the group a list of clients who have gone silent
    (no workout/meal log for `threshold`+ days) so quiet drop-offs get a poke."""
    from bot.database import get_group_members
    silent = [
        r for r in board["rows"]
        if r["days_silent"] is None or r["days_silent"] >= threshold
    ]
    if not silent:
        return
    lines = [f"⚠️ <b>이탈 주의 회원</b> ({board['date']})", ""]
    for r in silent:
        if r["days_silent"] is None:
            lines.append(f"• {r['name']} — 기록 없음")
        else:
            lines.append(f"• {r['name']} — {r['days_silent']}일째 미기록 (마지막 {r['last_log']})")
    lines.append("\n먼저 연락해 동기부여를 해보세요. 💪")
    text = "\n".join(lines)
    for m in get_group_members(chat_id):
        if not m.get("is_trainer"):
            continue
        try:
            await context.bot.send_message(chat_id=m["user_id"], text=text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Trainer alert DM failed for {m['user_id']}: {e}")


async def daily_summary_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback: send the personal LLM day-summary at 21:00 KST.
    Groups get the ranked scoreboard instead (see daily_scoreboard_job); this
    only DMs individual users in private chats to avoid group spam."""
    from bot.database import get_active_users_recent
    from zoneinfo import ZoneInfo
    date = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    users = get_active_users_recent(days=7)
    logger.info(f"Daily summary job firing for {len(users)} users on {date}")

    for u in users:
        user_id = u["user_id"]
        chat_id = u["chat_id"]
        # Group chats (negative id) get the scoreboard, not the essay.
        if chat_id < 0:
            continue
        try:
            ctx_md = _build_plan_context(user_id, chat_id, date)
            data = await generate_daily_summary(ctx_md)
            if not data:
                continue
            summary = data.get("summary_md", "")
            assessment = data.get("goal_assessment_md", "")
            upsert_daily_summary(user_id, chat_id, date, summary, assessment)

            parts = [f"🌙 <b>오늘의 요약</b> ({date})\n"]
            if summary:
                parts.append(summary)
            if assessment:
                parts.append(f"\n🎯 <b>목표 평가</b>\n{assessment}")
            text = "\n".join(parts)
            if len(text) > 4000:
                text = text[:4000]
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Daily summary failed for user {user_id} chat {chat_id}: {e}")
