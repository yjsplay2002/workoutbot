#!/usr/bin/env python3
import os
import threading
from dotenv import load_dotenv
load_dotenv()

import uvicorn
from bot.web import app as web_app
from bot.main import run_bot


def start_web():
    port = int(os.environ.get("WEB_PORT", "8080"))
    uvicorn.run(web_app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    threading.Thread(target=start_web, daemon=True).start()
    run_bot()
