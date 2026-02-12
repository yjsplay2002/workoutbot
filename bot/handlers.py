import asyncio
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from bot.analyzer import (
    analyze_workout,
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
    get_last_record,
    get_recent_records,
    get_stats,
    get_today_record,
    get_user_weight,
    merge_record,
    save_record,
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
    await update.message.reply_text(
        "🏋️ <b>운동 기록 분석 봇</b>에 오신 것을 환영합니다!\n\n"
        "이 봇은 운동 기록(텍스트 또는 이미지)을 자동으로 감지하고 "
        "전문가 수준의 분석을 제공합니다.\n\n"
        "<b>사용법:</b>\n"
        "• 운동 기록을 텍스트나 사진으로 보내주세요 (여러 장도 OK)\n"
        "• /setweight 75 — 체중 설정 (칼로리 추정용)\n"
        "• /history — 최근 운동 기록\n"
        "• /stats — 전체 통계\n"
        "• /analyze — 마지막 기록 재분석\n"
        "• /help — 도움말",
        parse_mode="HTML",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 <b>도움말</b>\n\n"
        "이 봇은 그룹 채팅이나 DM에서 운동 기록을 자동 감지합니다.\n\n"
        "<b>명령어:</b>\n"
        "• /start — 봇 소개\n"
        "• /setweight — 체중 설정\n"
        "• /history — 최근 5개 운동 기록 요약\n"
        "• /stats — 전체 운동 통계\n"
        "• /analyze — 마지막 기록 재분석 (메시지에 답장하면 해당 메시지 분석)\n"
        "• /help — 이 도움말\n\n"
        "<b>자동 감지:</b>\n"
        "운동 관련 키워드가 포함된 텍스트나 운동 기록 이미지를 보내면 자동으로 분석합니다.\n"
        "📸 여러 장의 이미지를 한꺼번에 보내도 자동으로 합쳐서 분석합니다.",
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
    await update.message.reply_text(f"✅ 체중이 {weight}kg으로 설정되었습니다.")


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


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Buffer photos for album handling - wait briefly for more photos."""
    if update.effective_user.is_bot:
        return
    _track_group_member(update)

    chat_id = update.effective_chat.id
    user = update.effective_user
    key = (chat_id, user.id)

    # Download this photo
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await file.download_as_bytearray())

    if key in _album_buffers:
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

    chat_id, user_id = key
    user = update.effective_user
    images = buf["images"]
    status_msg = buf["status_msg"]

    if not check_rate_limit(chat_id):
        await status_msg.edit_text("⏳ 잠시 후 다시 시도해주세요 (속도 제한).")
        return

    upsert_user(user.id, chat_id, user.full_name)

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
        weight = get_user_weight(user.id, chat_id)
        history = get_recent_records(chat_id, user.id, 5)

        date_count = len(date_groups)
        await status_msg.edit_text(f"📊 {date_count}개 날짜 분석 중...")

        # Analyze each date group IN PARALLEL
        async def analyze_one(date, data_list):
            combined = "\n\n".join(data_list)
            existing = get_today_record(chat_id, user.id, date)
            if existing:
                merged = existing["structured_md"] + "\n\n" + combined
                analysis = await analyze_workout(merged, weight, format_history_summary(history))
                kcal = extract_kcal(analysis)
                merge_record(existing["id"], merged, analysis, kcal)
            else:
                analysis = await analyze_workout(combined, weight, format_history_summary(history))
                kcal = extract_kcal(analysis)
                save_record(chat_id, user.id, f"[image x{len(data_list)}]", combined, analysis, kcal, date=date)
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
        await status_msg.edit_text(f"✅ {len(results)}개 날짜 분석 완료!")
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
        history = get_recent_records(chat_id, user.id, 5)
        analysis = await analyze_workout(
            structured, weight, format_history_summary(history)
        )
        kcal = extract_kcal(analysis)
        save_record(chat_id, user.id, "[image]", structured, analysis, kcal)
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
            merge_record(existing["id"], merged_structured, analysis, kcal)
            await status_msg.edit_text(
                f"📋 오늘 기록에 병합 완료!\n\n{analysis}",
                parse_mode="HTML",
            )
        else:
            analysis = await analyze_workout(
                structured, weight, format_history_summary(history)
            )
            kcal = extract_kcal(analysis)
            save_record(chat_id, user.id, text, structured, analysis, kcal)
            await status_msg.edit_text(analysis, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Text analysis error: {e}")
        await status_msg.edit_text("❌ 분석 중 오류가 발생했습니다.")
