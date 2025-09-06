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

# --- تنظیمات لاگ (با جزئیات بیشتر) ---
# با تغییر سطح به DEBUG، جزئیات بیشتری از فعالیت کتابخانه‌ها ثبت می‌شود
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
# ما یک لاگر مخصوص برای ربات خودمان می‌سازیم
logger = logging.getLogger(__name__)

# --- خواندن اطلاعات از متغیرهای محیطی ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = int(os.environ.get("YOUR_CHANNEL_ID", 0))
USERNAME = os.environ.get("YOUR_USERNAME", "YourUsername")
BOT_USERNAME = "" # این به صورت خودکار پر می‌شود

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
            try:
                logger.info(f"Searching on site: {site['name']}")
                search_url = site['search_url'].format(query=quote_plus(query))
                headers = {'User-Agent': random.choice(USER_AGENTS)}
                search_html = await fetch_url(session, search_url, headers)
                if not search_html:
                    logger.warning(f"Failed to get search page from {site['name']}")
                    continue

                soup = BeautifulSoup(search_html, 'lxml')
                link_tag = soup.find('a', href=re.compile(r'/lyrics/|lyric\.php'))
                if not link_tag or not link_tag.get('href'):
                    logger.warning(f"No lyrics link found on search page of {site['name']}")
                    continue
                
                lyrics_url = link_tag['href']
                if not lyrics_url.startswith('http'):
                    lyrics_url = site['base_url'] + lyrics_url
                
                logger.info(f"Found lyrics page on {site['name']}: {lyrics_url}")
                lyrics_html = await fetch_url(session, lyrics_url, headers)
                if not lyrics_html:
                    logger.warning(f"Failed to get lyrics page content from {lyrics_url}")
                    continue

                lyrics_soup = BeautifulSoup(lyrics_html, 'lxml')
                lyrics_elem = lyrics_soup.select_one(site['lyrics_selector'])
                if lyrics_elem:
                    lyrics = lyrics_elem.get_text(separator='\n', strip=True)
                    lyrics_formatted = f"📜 **Lyrics for {song_title} by {artist}**\n\n{lyrics}"
                    db_query('INSERT OR REPLACE INTO lyrics (song_title, lyrics) VALUES (?, ?)', (query, lyrics_formatted))
                    logger.info(f"Successfully scraped lyrics from {site['name']}")
                    return lyrics_formatted
            except Exception as e:
                logger.error(f"Error during scraping {site['name']}: {e}", exc_info=True)
    
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
        channel_link = f"https://t.me/{CHANNEL_ID}".replace('-100', '') if str(CHANNEL_ID).startswith('-100') else f"https://t.me/{CHANNEL_ID}"
        keyboard = [[InlineKeyboardButton("Contact", url=f"https://t.me/{USERNAME}"), InlineKeyboardButton("Channel", url=channel_link)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_html(rf"Hello {user.mention_html()},\nThis bot provides translation and lyrics.", reply_markup=reply_markup)

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.channel_post
    if not message or message.chat.id != CHANNEL_ID:
        logger.warning(f"Ignoring message from incorrect channel: {message.chat.id if message else 'N/A'}")
        return
    
    logger.info(f"New post received from channel {CHANNEL_ID}. Message ID: {message.message_id}")
    try:
        if message.text:
            logger.info("Post is text. Adding translate button.")
            keyboard = [[InlineKeyboardButton("Translate", callback_data='translate_text')]]
            await message.edit_reply_markup(InlineKeyboardMarkup(keyboard))
        elif message.audio:
            logger.info("Post is audio. Adding lyrics button.")
            caption = message.caption or message.audio.title or "Unknown"
            artist = message.audio.performer or "Unknown Artist"
            
            safe_title = urllib.parse.quote_plus(caption.replace('_', ' '))
            safe_artist = urllib.parse.quote_plus(artist.replace('_', ' '))
            payload = f"lyrics_{safe_title}_by_{safe_artist}"
            
            deep_link = f"https://t.me/{BOT_USERNAME}?start={payload}"
            keyboard = [[InlineKeyboardButton("📜 Show Lyrics", url=deep_link)]]
            await message.edit_caption(caption=message.caption or f"{caption} - {artist}", reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        logger.error(f"Error adding button in channel: {e}", exc_info=True)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    logger.info(f"Button callback received from user {query.from_user.id}. Data: '{query.data}'")
    
    if query.data == 'translate_text':
        original_text = query.message.text
        translated_text = await translate_standard_async(original_text)

        try:
            if len(translated_text) <= 200:
                await query.answer(text=translated_text, show_alert=True)
            else:
                await query.answer(text="Translation is long, sent to private chat.")
                await context.bot.send_message(chat_id=query.from_user.id, text=f"**Translation:**\n\n{translated_text}", parse_mode='Markdown')
        except BadRequest as e:
            if "Query is too old" in str(e):
                logger.warning("Query was too old. Could not show translation popup.")
            else:
                raise e

async def post_init(application: Application):
    global BOT_USERNAME
    bot_info = await application.bot.get_me()
    BOT_USERNAME = bot_info.username
    logger.info(f"Bot started as @{BOT_USERNAME}")

def main() -> None:
    init_db()
    
    port = int(os.environ.get('PORT', 8080))
    from threading import Thread
    Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True).start()

    request = HTTPXRequest(connect_timeout=10, read_timeout=20)
    application = Application.builder().token(TOKEN).request(request).post_init(post_init).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    logger.info("Starting bot polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
