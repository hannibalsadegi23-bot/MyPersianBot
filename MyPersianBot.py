import logging
import os
import sqlite3
import re
import asyncio
import random
from urllib.parse import quote_plus
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
import aiohttp
from bs4 import BeautifulSoup

# لاگینگ کامل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# متغیرهای محیطی
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = int(os.environ.get("YOUR_CHANNEL_ID", 0))
BOT_USERNAME = os.environ.get("YOUR_USERNAME", "")

logger.info(f"Bot starting with username: {BOT_USERNAME}")

# بقیه کد دقیقاً مانند نسخه قبلی بدون تغییر باقی می‌ماند
# فقط مطمئن شو که خط زیر در تابع main وجود دارد:
# application.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))

def main() -> None:
    """راه‌اندازی ربات"""
    logger.info("Initializing database...")
    init_db()
    
    # ایجاد اپلیکیشن
    application = Application.builder().token(TOKEN).build()

    # اضافه کردن handlerها
    application.add_handler(CommandHandler("start", handle_start_with_lyrics))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # این خط مهم است - باید دقیقاً اینجا باشد
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))

    # شروع ربات
    logger.info("🤖 ربات Lyrics در حال اجرا است...")
    print("🤖 ربات Lyrics در حال اجرا است...")
    application.run_polling()

if __name__ == "__main__":
    main()
