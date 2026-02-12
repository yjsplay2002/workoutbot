import logging
import os

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.database import init_db
from bot.handlers import (
    cmd_analyze,
    cmd_editdate,
    cmd_help,
    cmd_history,
    cmd_settrainer,
    cmd_setweight,
    cmd_start,
    cmd_stats,
    cmd_unsettrainer,
    handle_photo,
    handle_text,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
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
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("editdate", cmd_editdate))
    app.add_handler(CommandHandler("settrainer", cmd_settrainer))
    app.add_handler(CommandHandler("unsettrainer", cmd_unsettrainer))

    # Photo handler — all photos
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))

    # Text handler — non-command text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)
