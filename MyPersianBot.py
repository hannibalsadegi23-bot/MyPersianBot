import logging
import os
import sqlite3
import re
import asyncio
import random
from urllib.parse import quote_plus, unquote_plus
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
        conn = sqlite3.connect('cache.db', check_same_thread=False)
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
                    db_query('INSERT OR REPLACE INTO translations (text, translation) VALUES (?, ?)', (text, translation))
                    return translation
                else:
                    logger.error(f"Google Translate returned status {response.status}")
                    return "Error: Translation service returned an error."
        except Exception as e:
            logger.error(f"Translation failed: {e}", exc_info=True)
            return "Error during translation."

async def fetch_url(session, url, headers):
    try:
        async with session.get(url, headers=headers, timeout=15) as response:
            return await response.text() if response.status == 200 else None
    except Exception as e:
        logger.error(f"Exception while fetching {url}: {e}")
        return None

async def scrape_lyrics(song_title, artist):
    query = f"{artist} {song_title}"
    cached = db_query('SELECT lyrics FROM lyrics WHERE song_title = ?', (query,))
    if cached:
        logger.info(f"Lyrics CACHE HIT for: {query}")
        return cached[0][0]
    
    logger.info(f"Lyrics CACHE MISS for: {query}. Starting scrape process...")
    async with aiohttp.ClientSession() as session:
        for site in SITES:
            try:
                search_url = site['search_url'].format(query=quote_plus(query))
                headers = {'User-Agent': random.choice(USER_AGENTS)}
                search_html = await fetch_url(session, search_url, headers)
                if not search_html: continue

                soup = BeautifulSoup(search_html, 'lxml')
                link_tag = soup.find('a', href=re.compile(r'/lyrics/|lyric\.php'))
                if not link_tag or not link_tag.get('href'): continue
                
                lyrics_url = link_tag['href']
                if not lyrics_url.startswith('http'):
                    lyrics_url = site['base_url'] + lyrics_url
                
                lyrics_html = await fetch_url(session, lyrics_url, headers)
                if not lyrics_html: continue

                lyrics_soup = BeautifulSoup(lyrics_html, 'lxml')
                lyrics_elem = lyrics_soup.select_one(site['lyrics_selector'])
                if lyrics_elem:
                    lyrics = lyrics_elem.get_text(separator='\n', strip=True)
                    lyrics_formatted = f"📜 **Lyrics for {song_title} by {artist}**\n\n{lyrics}"
                    db_query('INSERT OR REPLACE INTO lyrics (song_title, lyrics) VALUES (?, ?)', (query, lyrics_formatted))
                    return lyrics_formatted
            except Exception as e:
                logger.error(f"Error scraping {site['name']} for '{query}': {e}")
    
    return f"Sorry, lyrics for '{song_title}' by '{artist}' were not found."

def get_song_details(message):
    if message.audio:
        logger.info("Message is 'Audio' type. Reading metadata.")
        return message.audio.performer, message.audio.title
    elif message.document and message.document.mime_type in ('audio/mpeg', 'audio/mp3'):
        logger.info("Message is 'Document' type (MP3). Reading filename.")
        filename = message.document.file_name.rsplit('.', 1)[0]
        match = re.match(r'(.*?)\s*[-–—]\s*(.*)', filename)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        else:
            return "Unknown Artist", filename.strip()
    return None, None

# --- توابع ربات ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args
    if args and args[0].startswith('lyrics_'):
        try:
            _, song_info = args[0].split('_', 1)
            artist, title = song_info.rsplit('_by_', 1)
            artist = unquote_plus(artist)
            title = unquote_plus(title)

            await update.message.reply_text("Searching for lyrics...")
            lyrics_text = await scrape_lyrics(title, artist)
            await update.message.reply_text(lyrics_text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Deep link failed: {e}", exc_info=True)
            await update.message.reply_text("Error processing song request.")
    else:
        channel_link = f"https://t.me/{CHANNEL_ID}".replace('-100', '')
        keyboard = [[InlineKeyboardButton("Contact", url=f"https://t.me/{USERNAME}"), InlineKeyboardButton("Channel", url=channel_link)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_html(rf"Hello {user.mention_html()},\nThis bot provides translation and lyrics.", reply_markup=reply_markup)

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.channel_post
    if not message or message.chat.id != CHANNEL_ID: return
    
    logger.info(f"New post in channel {CHANNEL_ID}. Msg ID: {message.message_id}")
    try:
        if message.text:
            logger.info("Post is text. Adding translate button.")
            keyboard = [[InlineKeyboardButton("Translate", callback_data='translate_text')]]
            await message.edit_reply_markup(InlineKeyboardMarkup(keyboard))
        else:
            artist, title = get_song_details(message)
            logger.info(f"Extracted song details -> Artist: '{artist}', Title: '{title}'")
            if artist and title:
                safe_artist = quote_plus(artist)
                safe_title = quote_plus(title)
                payload = f"lyrics_{safe_title}_by_{safe_artist}"
                deep_link = f"https://t.me/{context.bot.username}?start={payload}"
                
                keyboard = [[InlineKeyboardButton("📜 Show Lyrics", url=deep_link)]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                if message.audio:
                    current_caption = message.caption if message.caption is not None else f"{title} - {artist}"
                    await message.edit_caption(caption=current_caption, reply_markup=reply_markup)
                elif message.document:
                    await message.reply_text("Click here for lyrics:", reply_markup=reply_markup)
            else:
                logger.warning("Post was not text or a recognized audio format.")
    except Exception as e:
        logger.error(f"Error in handle_channel_post: {e}", exc_info=True)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
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
                logger.warning("Query was too old.")
            else: raise e

def main() -> None:
    init_db()
    
    port = int(os.environ.get('PORT', 8080))
    from threading import Thread
    Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True).start()

    request = HTTPXRequest(connect_timeout=10, read_timeout=20)
    application = Application.builder().token(TOKEN).request(request).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    logger.info("Starting bot...")
    application.run_polling()

if __name__ == '__main__':
    main()
