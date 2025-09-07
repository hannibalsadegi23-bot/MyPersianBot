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
import aiohttp
from bs4 import BeautifulSoup

# لاگینگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# متغیرهای محیطی
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = int(os.environ.get("YOUR_CHANNEL_ID", 0))
USERNAME = os.environ.get("YOUR_USERNAME", "")
CHANNEL_LINK = os.environ.get("YOUR_CHANNEL_LINK", "")
PORT = int(os.environ.get("PORT", 8080))

# راه‌اندازی Flask
app = Flask(__name__)
@app.route('/')
def index():
    return "Translation & Lyrics Bot is alive!"

# User-Agent‌های چرخشی
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
]

# سایت‌های لیریکس
SITES = [
    {'name': 'AZLyrics', 'search_url': 'https://search.azlyrics.com/search.php?q={query}', 'lyrics_selector': 'div.ringtone ~ div', 'base_url': 'https://www.azlyrics.com'},
    {'name': 'Lyrics.com', 'search_url': 'https://www.lyrics.com/serp.php?st={query}', 'lyrics_selector': 'pre#lyric-body-text', 'base_url': 'https://www.lyrics.com'},
    {'name': 'SongLyrics', 'search_url': 'http://www.songlyrics.com/index.php?section=search&searchW={query}&submit=Search', 'lyrics_selector': 'div#lyrics', 'base_url': 'http://www.songlyrics.com'}
]

# راه‌اندازی دیتابیس کش
def init_db():
    conn = sqlite3.connect('cache.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS translations (text TEXT UNIQUE, translation TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS lyrics (song_title TEXT UNIQUE, lyrics TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('DELETE FROM translations WHERE timestamp < date("now", "-30 days")')
    cursor.execute('DELETE FROM lyrics WHERE timestamp < date("now", "-30 days")')
    conn.commit()
    conn.close()

def get_cached_translation(text):
    conn = sqlite3.connect('cache.db')
    cursor = conn.cursor()
    cursor.execute('SELECT translation FROM translations WHERE text = ?', (text,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def cache_translation(text, translation):
    conn = sqlite3.connect('cache.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO translations (text, translation) VALUES (?, ?)', (text, translation))
    conn.commit()
    conn.close()

def get_cached_lyrics(song_title):
    conn = sqlite3.connect('cache.db')
    cursor = conn.cursor()
    cursor.execute('SELECT lyrics FROM lyrics WHERE song_title = ?', (song_title,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def cache_lyrics(song_title, lyrics):
    conn = sqlite3.connect('cache.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO lyrics (song_title, lyrics) VALUES (?, ?)', (song_title, lyrics))
    conn.commit()
    conn.close()

# تابع ترجمه
async def translate_standard_async(text):
    cached = get_cached_translation(text)
    if cached:
        logger.info(f"Translation from cache: {text}")
        return cached
    
    async with aiohttp.ClientSession() as session:
        for attempt in range(3):
            try:
                async with session.get(
                    f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=fa&dt=t&q={quote_plus(text)}",
                    timeout=10
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        translation = data[0][0][0]
                        cache_translation(text, translation)
                        return translation
                    await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Translation attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(2)
        return "خطا در ترجمه. لطفاً بعداً امتحان کنید."

# تابع استخراج اطلاعات آهنگ
def extract_song_info(caption, audio):
    if caption:
        match = re.match(r'(.*?)\s*[-–—]\s*(.*)', caption.strip())
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return caption.strip(), "Unknown Artist"
    elif audio.file_name:
        return re.sub(r'\.(mp3|wav|flac)$', '', audio.file_name, flags=re.IGNORECASE).strip(), "Unknown Artist"
    return "Unknown Song", "Unknown Artist"

# تابع اسکرپ لیریکس
async def scrape_lyrics(song_title, artist):
    query = f"{artist} {song_title}" if artist != "Unknown Artist" else song_title
    encoded_query = quote_plus(query)
    
    cached = get_cached_lyrics(query)
    if cached:
        logger.info(f"Lyrics from cache: {query}")
        return cached
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for site in SITES:
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            search_url = site['search_url'].format(query=encoded_query)
            tasks.append(fetch_url(session, search_url, headers))
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        for idx, response in enumerate(responses):
            if not response or isinstance(response, Exception):
                continue
            site = SITES[idx]
            try:
                soup = BeautifulSoup(response, 'lxml')
                first_link = soup.find('a', href=re.compile(r'/lyric[s]?/.*'))
                if not first_link:
                    continue
                lyrics_url = first_link['href'] if first_link['href'].startswith('http') else site['base_url'] + first_link['href']
                
                headers = {'User-Agent': random.choice(USER_AGENTS)}
                lyrics_html = await fetch_url(session, lyrics_url, headers)
                if not lyrics_html:
                    continue
                
                lyrics_soup = BeautifulSoup(lyrics_html, 'lxml')
                lyrics_elem = lyrics_soup.select_one(site['lyrics_selector'])
                if lyrics_elem:
                    lyrics = re.sub(r'\n\s*\n', '\n', lyrics_elem.get_text(strip=True))
                    cache_lyrics(query, lyrics)
                    logger.info(f"Lyrics scraped from {site['name']} for '{query}'")
                    return lyrics
            except Exception as e:
                logger.error(f"Error scraping {site['name']} for '{query}': {e}")
                continue
    
    return "متأسفانه متن این آهنگ پیدا نشد. لطفاً بعداً امتحان کنید."

async def fetch_url(session, url, headers):
    for attempt in range(3):
        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    return await response.text()
                elif response.status == 429:
                    await asyncio.sleep(random.uniform(5, 10))
                    continue
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            await asyncio.sleep(random.uniform(2, 5))
    return None

# توابع ربات
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("تماس", url=f"https://t.me/{USERNAME}"), InlineKeyboardButton("کانال", url=f"https://t.me/{CHANNEL_LINK}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(
        rf"سلام {user.mention_html()}،\nاین ربات ترجمه متن و متن آهنگ‌ها رو ارائه می‌ده.",
        reply_markup=reply_markup
    )

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.channel_post
    if not message or message.chat.id != CHANNEL_ID:
        return
    
    try:
        if message.text:
            keyboard = [[InlineKeyboardButton("ترجمه (پاپ‌آپ)", callback_data='translate_to_fa_popup')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.edit_reply_markup(reply_markup=reply_markup)
        elif message.audio:
            audio = message.audio
            caption = message.caption or ""
            song_title, artist = extract_song_info(caption, audio)
            encoded_title = re.sub(r'[^\w\s]', '', f"{song_title} {artist}").replace(' ', '_')
            deep_link = f"https://t.me/{USERNAME}?start=lyrics_{encoded_title}"
            
            keyboard = [[InlineKeyboardButton("🎵 متن آهنگ", url=deep_link)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.edit_caption(
                caption=caption or f"{song_title} - {artist}",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"خطا در افزودن دکمه: {e}")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    original_text = query.message.text
    translated_text = await translate_standard_async(original_text)
    
    if query.data == 'translate_to_fa_popup':
        if len(translated_text) <= 200:
            await query.answer(text=translated_text, show_alert=True)
        else:
            await query.answer(text="ترجمه برای پاپ‌آپ طولانی‌ست. بعداً امتحان کنید!", show_alert=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args
    
    if args and args[0].startswith('lyrics_'):
        encoded_title = args[0].replace('lyrics_', '')
        parts = encoded_title.replace('_', ' ').split()
        song_title = ' '.join(parts[:-1]) if len(parts) > 1 else parts[0]
        artist = parts[-1] if len(parts) > 1 else "Unknown Artist"
        
        lyrics = await scrape_lyrics(song_title, artist)
        
        await update.message.reply_text(
            f"🎵 متن آهنگ: {song_title} توسط {artist}\n\n{lyrics}",
            parse_mode='HTML'
        )
        logger.info(f"لیریکس برای '{song_title}' به کاربر {user.id} ارسال شد")
    else:
        await start_command(update, context)

def main() -> None:
    if not all([TOKEN, CHANNEL_ID, USERNAME, CHANNEL_LINK]):
        logger.error("متغیرهای محیطی ناقص‌اند. ربات اجرا نمی‌شود.")
        return
    
    init_db()
    request = HTTPXRequest(connect_timeout=20, read_timeout=20)
    application = Application.builder().token(TOKEN).request(request).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST & (filters.TEXT | filters.AUDIO), handle_channel_post))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    logger.info("ربات ترجمه و لیریکس در حال اجرا روی Render...")
    application.run_polling()

if __name__ == '__main__':
    import threading
    flask_thread = threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': PORT})
    flask_thread.start()
    main()
