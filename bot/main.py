import datetime as dt
import logging
import os
from zoneinfo import ZoneInfo

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.database import init_db
from bot.handlers import (
    cmd_analyze,
    cmd_breakfast,
    cmd_delete,
    cmd_dinner,
    cmd_editdate,
    cmd_goal,
    cmd_help,
    cmd_history,
    cmd_inbody,
    cmd_lunch,
    cmd_plan,
    cmd_setheight,
    cmd_settrainer,
    cmd_setweight,
    cmd_snack,
    cmd_start,
    cmd_stats,
    cmd_today,
    cmd_unsettrainer,
    daily_summary_job,
    daily_scoreboard_job,
    handle_photo,
    handle_text,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# httpx logs each request URL at INFO — the Telegram getUpdates URL embeds the
# bot token, leaking it into server logs. Silence httpx to WARNING to keep the
# token out of the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def run_bot() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        raise SystemExit("TELEGRAM_BOT_TOKEN environment variable is required")

    init_db()

    app = ApplicationBuilder().token(token).build()

    # Command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("setweight", cmd_setweight))
    app.add_handler(CommandHandler("setheight", cmd_setheight))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("editdate", cmd_editdate))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("settrainer", cmd_settrainer))
    app.add_handler(CommandHandler("unsettrainer", cmd_unsettrainer))

    # New: inbody / meals / goals / plan / today
    app.add_handler(CommandHandler("inbody", cmd_inbody))
    app.add_handler(CommandHandler("breakfast", cmd_breakfast))
    app.add_handler(CommandHandler("lunch", cmd_lunch))
    app.add_handler(CommandHandler("dinner", cmd_dinner))
    app.add_handler(CommandHandler("snack", cmd_snack))
    app.add_handler(CommandHandler("goal", cmd_goal))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("today", cmd_today))

    # Photo + caption command routing (CommandHandler doesn't match message.caption).
    # These must be registered BEFORE the generic photo handler so a captioned photo
    # is dispatched to the right flow instead of falling through to the workout extractor.
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/inbody(\s|$|@)"), cmd_inbody))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/breakfast(\s|$|@)"), cmd_breakfast))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/lunch(\s|$|@)"), cmd_lunch))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/dinner(\s|$|@)"), cmd_dinner))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/snack(\s|$|@)"), cmd_snack))

    # Photo handler — all other photos (default: workout extraction)
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))

    # Text handler — non-command text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Schedule daily summary at 21:00 KST
    if app.job_queue is not None:
        kst = ZoneInfo("Asia/Seoul")
        app.job_queue.run_daily(
            daily_summary_job,
            time=dt.time(hour=21, minute=0, tzinfo=kst),
            name="daily_summary_21kst",
        )
        app.job_queue.run_daily(
            daily_scoreboard_job,
            time=dt.time(hour=21, minute=0, tzinfo=kst),
            name="daily_scoreboard_21kst",
        )
        logger.info("Daily summary + scoreboard jobs scheduled at 21:00 KST")
    else:
        logger.warning("JobQueue not available — daily summary disabled")

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)
