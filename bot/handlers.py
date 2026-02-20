import asyncio
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from bot.analyzer import (
    analyze_workout,
    classify_workout,
    extract_from_image,
    extract_from_text,
    extract_kcal,
    group_by_date,
    is_workout_text,
)
from bot.database import (
    add_group_member,
    delete_all_records,
    delete_record,
    get_group_clients,
    get_last_record,
    get_recent_records,
    get_stats,
    get_today_record,
    get_user_height,
    get_user_weight,
    is_trainer_in_chat,
    merge_record,
    save_record,
    set_height,
    set_trainer,
    set_weight,
    unset_trainer,
    update_record_date,
    upsert_user,
)
from bot.utils import check_rate_limit, format_history_summary

logger = logging.getLogger(__name__)


def _track_group_member(update: Update) -> None:
    """Auto-register sender as group member if in a group chat."""
    chat = update.effective_chat
    user = update.effective_user
    if chat and user and chat.type in ("group", "supergroup"):
        add_group_member(chat.id, user.id)


async def cmd_settrainer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("이 명령어는 그룹에서만 사용 가능합니다.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("트레이너로 설정할 사용자의 메시지에 답장하세요.\n사용법: /settrainer (답장)")
        return
    # Check if command issuer is admin
    member = await chat.get_member(update.effective_user.id)
    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("❌ 그룹 관리자만 사용할 수 있습니다.")
        return
    target = update.message.reply_to_message.from_user
    set_trainer(chat.id, target.id)
    await update.message.reply_text(f"✅ {target.full_name}님이 트레이너로 설정되었습니다.")


async def cmd_unsettrainer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("이 명령어는 그룹에서만 사용 가능합니다.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("트레이너를 해제할 사용자의 메시지에 답장하세요.\n사용법: /unsettrainer (답장)")
        return
    member = await chat.get_member(update.effective_user.id)
    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("❌ 그룹 관리자만 사용할 수 있습니다.")
        return
    target = update.message.reply_to_message.from_user
    unset_trainer(chat.id, target.id)
    await update.message.reply_text(f"✅ {target.full_name}님의 트레이너 권한이 해제되었습니다.")


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
            "🌐 웹 대시보드: https://workoutbot-ybbz.onrender.com\n"
            "전체 명령어는 /help 를 확인해주세요.",
            parse_mode="HTML",
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
        "🌐 웹 대시보드: https://workoutbot-ybbz.onrender.com\n"
        "전체 명령어는 /help 를 확인해주세요.",
        parse_mode="HTML",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 <b>도움말</b>\n\n"
        "이 봇은 그룹 채팅이나 DM에서 운동 기록을 자동 감지하고 AI 전문가 분석을 제공합니다.\n\n"
        "<b>📋 기본 명령어:</b>\n"
        "• /start — 봇 소개\n"
        "• /help — 이 도움말\n\n"
        "<b>📊 기록 조회:</b>\n"
        "• /history — 최근 5개 운동 기록 요약\n"
        "• /stats — 전체 운동 통계 (세션수, 평균/총 칼로리)\n"
        "• /analyze — 마지막 기록 재분석 (메시지에 답장하면 해당 메시지 분석)\n\n"
        "<b>✏️ 기록 관리:</b>\n"
        "• /editdate [ID] [날짜] — 기록 날짜 수정 (예: /editdate 3 2026-01-24)\n"
        "• /delete [ID] — 개별 기록 삭제 (예: /delete 3)\n"
        "• /delete all — 내 기록 전체 삭제\n\n"
        "<b>⚙️ 설정:</b>\n"
        "• /setweight [kg] — 체중 설정 (예: /setweight 75)\n"
        "• /setheight [cm] — 키 설정 (예: /setheight 175)\n\n"
        "<b>👥 그룹 관리 (관리자 전용):</b>\n"
        "• /settrainer — 트레이너 지정 (메시지에 답장)\n"
        "• /unsettrainer — 트레이너 해제 (메시지에 답장)\n\n"
        "<b>📸 자동 감지:</b>\n"
        "• 운동 기록 이미지를 보내면 자동 분석 (여러 장 OK)\n"
        "• 운동 관련 텍스트를 입력하면 자동 감지 후 분석\n"
        "• 이미지 속 날짜를 자동 인식하여 날짜별 분리 저장\n\n"
        "<b>🌐 웹 대시보드:</b>\n"
        "• 텔레그램 로그인으로 웹에서 기록 열람 가능\n"
        "• 달력 뷰, 운동 카테고리별 색상 표시\n"
        "• https://workoutbot-ybbz.onrender.com",
        parse_mode="HTML",
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
            await _process_text_workout(update, context, reply_msg.text)
        else:
            await update.message.reply_text("분석할 수 있는 메시지가 아닙니다.")
        return

    record = get_last_record(update.effective_chat.id, update.effective_user.id)
    if not record:
        await update.message.reply_text("📭 분석할 기록이 없습니다.")
        return

    await update.message.reply_text("🔄 마지막 기록을 재분석 중...")
    try:
        weight = get_user_weight(update.effective_user.id, update.effective_chat.id)
        height = get_user_height(update.effective_user.id, update.effective_chat.id)
        history = get_recent_records(update.effective_chat.id, update.effective_user.id, 5)
        analysis = await analyze_workout(
            record["structured_md"], weight, format_history_summary(history)
        )
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

    if key in _album_buffers:
        # Update target_user_id (use latest reply target)
        _album_buffers[key]["target_user_id"] = target_user_id
        # Add to existing buffer
        _album_buffers[key]["images"].append(image_bytes)
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
            "status_msg": status_msg,
            "update": update,
            "context": context,
            "target_user_id": target_user_id,
            "timer": asyncio.create_task(
                _process_album_after_delay(key, update, context)
            ),
        }


async def _process_album_after_delay(
    key: tuple, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Wait for album to complete, then process all images together."""
    await asyncio.sleep(ALBUM_WAIT_SECONDS)

    buf = _album_buffers.pop(key, None)
    if not buf:
        return

    chat_id, sender_id = key
    user = update.effective_user
    # Use resolved target user (client), not necessarily the sender (trainer)
    target_user_id = buf.get("target_user_id", sender_id)
    images = buf["images"]
    status_msg = buf["status_msg"]

    if not check_rate_limit(chat_id):
        await status_msg.edit_text("⏳ 잠시 후 다시 시도해주세요 (속도 제한).")
        return

    upsert_user(user.id, chat_id, user.full_name)
    # Ensure target user (client) is also registered
    if target_user_id != user.id:
        upsert_user(target_user_id, chat_id, f"client_{target_user_id}")

    count = len(images)
    await status_msg.edit_text(f"📸 이미지 {count}장 분석 중...")

    try:
        # Extract from all images IN PARALLEL
        await status_msg.edit_text(f"📸 이미지 {count}장에서 운동 기록 추출 중... (1/{count})")

        async def extract_one(idx, img):
            result = await extract_from_image(img)
            try:
                await status_msg.edit_text(
                    f"📸 이미지 추출 중... ({idx + 1}/{count})"
                )
            except Exception:
                pass
            return result

        tasks = [extract_one(i, img) for i, img in enumerate(images)]
        extracted_results = await asyncio.gather(*tasks, return_exceptions=True)

        all_extracted = []
        for r in extracted_results:
            if isinstance(r, Exception):
                logger.error(f"Image extraction error: {r}")
                continue
            if "NO_WORKOUT_DATA" not in r:
                all_extracted.append(r)

        if not all_extracted:
            await status_msg.edit_text("이미지에서 운동 기록을 찾을 수 없습니다.")
            return

        # Group by date extracted from images
        date_groups = group_by_date(all_extracted)
        weight = get_user_weight(target_user_id, chat_id)
        height = get_user_height(target_user_id, chat_id)
        history = get_recent_records(chat_id, target_user_id, 5)

        date_count = len(date_groups)
        await status_msg.edit_text(f"📊 {date_count}개 날짜 분석 중...")

        # Analyze each date group IN PARALLEL
        async def analyze_one(date, data_list):
            combined = "\n\n".join(data_list)
            existing = get_today_record(chat_id, target_user_id, date)
            if existing:
                merged = existing["structured_md"] + "\n\n" + combined
                analysis = await analyze_workout(merged, weight, format_history_summary(history), height_cm=height)
                kcal = extract_kcal(analysis)
                category = classify_workout(merged)
                merge_record(existing["id"], merged, analysis, kcal, category=category)
            else:
                analysis = await analyze_workout(combined, weight, format_history_summary(history), height_cm=height)
                kcal = extract_kcal(analysis)
                category = classify_workout(combined)
                save_record(chat_id, target_user_id, f"[image x{len(data_list)}]", combined, analysis, kcal, date=date, category=category)
            return date, analysis

        analysis_tasks = [analyze_one(d, dl) for d, dl in sorted(date_groups.items())]
        analysis_results = await asyncio.gather(*analysis_tasks, return_exceptions=True)

        results = []
        for r in analysis_results:
            if isinstance(r, Exception):
                logger.error(f"Analysis error: {r}")
                continue
            date, analysis = r
            results.append(f"📅 <b>{date}</b>\n{analysis}")

        # Send results — one message per date to avoid length issues
        saved_for = f" (클라이언트 ID: {target_user_id} 기록으로 저장)" if target_user_id != user.id else ""
        await status_msg.edit_text(f"✅ {len(results)}개 날짜 분석 완료!{saved_for}")
        for r in results:
            # Split if too long
            if len(r) > 4000:
                await update.message.reply_text(r[:4000], parse_mode="HTML")
            else:
                await update.message.reply_text(r, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Album analysis error: {e}")
        await status_msg.edit_text("❌ 분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")


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

    try:
        structured = await extract_from_image(image_bytes)
        if "NO_WORKOUT_DATA" in structured:
            await status_msg.edit_text("이 이미지에서 운동 기록을 찾을 수 없습니다.")
            return

        weight = get_user_weight(user.id, chat_id)
        height = get_user_height(user.id, chat_id)
        history = get_recent_records(chat_id, user.id, 5)
        analysis = await analyze_workout(
            structured, weight, format_history_summary(history)
        )
        kcal = extract_kcal(analysis)
        category = classify_workout(structured)
        save_record(chat_id, user.id, "[image]", structured, analysis, kcal, category=category)
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
    if not is_workout_text(text):
        return
    await _process_text_workout(update, context, text)


async def _process_text_workout(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    chat_id = update.effective_chat.id
    user = update.effective_user

    if not check_rate_limit(chat_id):
        return

    upsert_user(user.id, chat_id, user.full_name)

    status_msg = await update.message.reply_text("📝 운동 기록 분석 중...")

    try:
        structured = await extract_from_text(text)
        if "NO_WORKOUT_DATA" in structured:
            await status_msg.edit_text("운동 기록을 인식할 수 없습니다.")
            return

        weight = get_user_weight(user.id, chat_id)
        height = get_user_height(user.id, chat_id)
        history = get_recent_records(chat_id, user.id, 5)

        # Same-day merge
        today = datetime.now().strftime("%Y-%m-%d")
        existing = get_today_record(chat_id, user.id, today)

        if existing:
            merged_structured = existing["structured_md"] + "\n\n" + structured
            analysis = await analyze_workout(
                merged_structured, weight, format_history_summary(history)
            )
            kcal = extract_kcal(analysis)
            category = classify_workout(merged_structured)
            merge_record(existing["id"], merged_structured, analysis, kcal, category=category)
            await status_msg.edit_text(
                f"📋 오늘 기록에 병합 완료!\n\n{analysis}",
                parse_mode="HTML",
            )
        else:
            analysis = await analyze_workout(
                structured, weight, format_history_summary(history)
            )
            kcal = extract_kcal(analysis)
            category = classify_workout(structured)
            save_record(chat_id, user.id, text, structured, analysis, kcal, category=category)
            await status_msg.edit_text(analysis, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Text analysis error: {e}")
        await status_msg.edit_text("❌ 분석 중 오류가 발생했습니다.")
