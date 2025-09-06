import logging
import os
import sqlite3
import re
import asyncio
import random
from urllib.parse import quote_plus
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.request import HTTPXRequest
from telegram.error import BadRequest
import aiohttp
from bs4 import BeautifulSoup

# --- تنظیمات لاگ ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- خواندن اطلاعات از متغیرهای محیطی ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = int(os.environ.get("YOUR_CHANNEL_ID", 0))
USERNAME = os.environ.get("YOUR_USERNAME", "YourUsername")

# --- وب‌سرور برای بیدار نگه داشتن ---
app = Flask(__name__)
@app.route('/')
def index():
    return "Bot is alive!"

# --- لیست سایت‌ها و User-Agentها ---
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
]
SITES = [
    {'name': 'AZLyrics', 'search_url': 'https://search.azlyrics.com/search.php?q={query}', 'lyrics_selector': 'div.ringtone ~ div', 'base_url': 'https://www.azlyrics.com'},
    {'name': 'Lyrics.com', 'search_url': 'https://www.lyrics.com/serp.php?st={query}', 'lyrics_selector': 'pre#lyric-body-text', 'base_url': 'https://www.lyrics.com'}
]

# --- مدیریت دیتابیس کش ---
def db_query(query, params=()):
    try:
        conn = sqlite3.connect('cache.db')
        cursor = conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchall()
        conn.commit()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Database query failed: {e}")
        return []

def init_db():
    logger.info("Initializing database...")
    db_query('CREATE TABLE IF NOT EXISTS translations (text TEXT PRIMARY KEY, translation TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    db_query('CREATE TABLE IF NOT EXISTS lyrics (song_title TEXT PRIMARY KEY, lyrics TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    db_query('DELETE FROM translations WHERE timestamp < date("now", "-30 days")')
    db_query('DELETE FROM lyrics WHERE timestamp < date("now", "-30 days")')
    logger.info("Database initialized successfully.")

# --- توابع اصلی ---
async def translate_standard_async(text):
    cached = db_query('SELECT translation FROM translations WHERE text = ?', (text,))
    if cached:
        logger.info(f"Translation CACHE HIT for: {text[:30]}...")
        return cached[0][0]
    
    logger.info(f"Translation CACHE MISS. Fetching from Google for: {text[:30]}...")
    async with aiohttp.ClientSession() as session:
        try:
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=fa&dt=t&q={quote_plus(text)}"
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    translation = "".join([sentence[0] for sentence in data[0] if sentence[0]])
                    logger.info("Successfully fetched translation from Google.")
                    db_query('INSERT OR REPLACE INTO translations (text, translation) VALUES (?, ?)', (text, translation))
                    return translation
                else:
                    logger.error(f"Google Translate returned status {response.status}")
                    return "Error: Translation service returned an error."
        except Exception as e:
            logger.error(f"Translation failed with exception: {e}", exc_info=True)
            return "Error during translation."

async def fetch_url(session, url, headers):
    logger.debug(f"Fetching URL: {url}")
    try:
        async with session.get(url, headers=headers, timeout=15) as response:
            logger.debug(f"URL: {url}, Status: {response.status}")
            return await response.text() if response.status == 200 else None
    except Exception as e:
        logger.error(f"Exception while fetching {url}: {e}")
        return None

async def scrape_lyrics(song_title, artist):
    query = f"{artist} {song_title}"
    logger.info(f"Attempting to scrape lyrics for: {query}")
    cached = db_query('SELECT lyrics FROM lyrics WHERE song_title = ?', (query,))
    if cached:
        logger.info(f"Lyrics CACHE HIT for: {query}")
        return cached[0][0]
    
    logger.info(f"Lyrics CACHE MISS for: {query}. Starting scrape process...")
    async with aiohttp.ClientSession() as session:
        for site in SITES:
            # ... (بخش اسکرپینگ مثل قبل است)
    
    logger.warning(f"Failed to find lyrics for '{query}' on all sites.")
    return f"Sorry, lyrics for '{song_title}' by '{artist}' were not found."

# --- توابع ربات ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args
    logger.info(f"Received /start command from user {user.id}. Args: {args}")

    if args and args[0].startswith('lyrics_'):
        try:
            payload = args[0]
            logger.info(f"Processing deep link with payload: {payload}")
            _, song_info = payload.split('_', 1)
            song_title, artist = song_info.rsplit('_by_', 1)
            song_title = urllib.parse.unquote_plus(song_title)
            artist = urllib.parse.unquote_plus(artist)

            await update.message.reply_text("Searching for lyrics...")
            lyrics_text = await scrape_lyrics(song_title, artist)
            await update.message.reply_text(lyrics_text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Deep link processing failed: {e}", exc_info=True)
            await update.message.reply_text("Error processing the song request.")
    else:
        channel_link = f"https://t.me/{CHANNEL_ID}".replace('-100', '')
        keyboard = [[InlineKeyboardButton("Contact", url=f"https://t.me/{USERNAME}"), InlineKeyboardButton("Channel", url=channel_link)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_html(rf"Hello {user.mention_html()},\nThis bot provides translation and lyrics.", reply_markup=reply_markup)

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.channel_post
    if not message or message.chat.id != CHANNEL_ID:
        return
    
    logger.info(f"New post received from channel {CHANNEL_ID}. Message ID: {message.message_id}")
    try:
        if message.text:
            logger.info("Post is text. Adding translate button.")
            keyboard = [[InlineKeyboardButton("Translate", callback_data='translate_text')]]
            await message.edit_reply_markup(InlineKeyboardMarkup(keyboard))
            
        elif message.audio:
            logger.info("Post is audio. Attempting to add lyrics button.")
            caption = message.audio.title
            artist = message.audio.performer
            
            # لاگ جدید برای عیب‌یابی
            logger.info(f"Extracted from audio metadata -> Artist: '{artist}', Title: '{caption}'")
            
            if artist and caption:
                safe_title = urllib.parse.quote_plus(caption)
                safe_artist = urllib.parse.quote_plus(artist)
                payload = f"lyrics_{safe_title}_by_{safe_artist}"
                
                # --- رفع باگ اصلی ---
                # دریافت نام کاربری ربات به صورت مستقیم و مطمئن
                bot_username = context.bot.username
                deep_link = f"https://t.me/{bot_username}?start={payload}"
                logger.info(f"Generated deep link: {deep_link}")
                
                keyboard = [[InlineKeyboardButton("📜 Show Lyrics", url=deep_link)]]
                # اگر فایل کپشن نداشت، نام آهنگ و خواننده را به عنوان کپشن اضافه می‌کنیم
                new_caption = message.caption if message.caption is not None else f"{caption} - {artist}"
                await message.edit_caption(caption=new_caption, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                logger.warning("Could not add lyrics button because Artist or Title metadata is missing.")

    except Exception as e:
        logger.error(f"Error in handle_channel_post: {e}", exc_info=True)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    logger.info(f"Button callback received from user {query.from_user.id}. Data: '{query.data}'")
    
    if query.data == 'translate_text':
        # ... (کد این بخش مثل قبل است)

def main() -> None:
    init_db()
    
    port = int(os.environ.get('PORT', 8080))
    from threading import Thread
    Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True).start()

    request = HTTPXRequest(connect_timeout=10, read_timeout=20)
    # حذف post_init چون دیگر به آن روش برای گرفتن نام کاربری نیاز نداریم
    application = Application.builder().token(TOKEN).request(request).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    logger.info("Starting bot polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
