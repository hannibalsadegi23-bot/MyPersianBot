import logging
import os
import sqlite3
import re
import asyncio
import random
from urllib.parse import quote_plus
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
import aiohttp
from bs4 import BeautifulSoup

# لاگینگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# متغیرهای محیطی
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = int(os.environ.get("YOUR_CHANNEL_ID", 0))
BOT_USERNAME = os.environ.get("YOUR_USERNAME", "")  # یوزرنیم ربات بدون @

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
    cursor.execute('CREATE TABLE IF NOT EXISTS lyrics (song_title TEXT UNIQUE, lyrics TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('DELETE FROM lyrics WHERE timestamp < date("now", "-30 days")')
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

# تابع استخراج اطلاعات آهنگ
def extract_song_info(caption, audio):
    if caption:
        # حذف هر چیزی که داخل پرانتز یا براکت هست
        clean_caption = re.sub(r'[\(\[].*?[\)\]]', '', caption).strip()
        match = re.match(r'(.*?)\s*[-–—]\s*(.*)', clean_caption)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return clean_caption, "Unknown Artist"
    elif audio.file_name:
        clean_filename = re.sub(r'[\(\[].*?[\)\]]', '', audio.file_name)
        clean_filename = re.sub(r'\.(mp3|wav|flac|m4a)$', '', clean_filename, flags=re.IGNORECASE).strip()
        return clean_filename, "Unknown Artist"
    return "Unknown Song", "Unknown Artist"

# تابع اسکرپ لیریکس
async def scrape_lyrics(song_title, artist):
    query = f"{artist} {song_title}" if artist != "Unknown Artist" else song_title
    query = query.strip()
    
    cached = get_cached_lyrics(query)
    if cached:
        logger.info(f"Lyrics from cache: {query}")
        return cached
    
    encoded_query = quote_plus(query)
    
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
                    lyrics = re.sub(r'\n\s*\n', '\n\n', lyrics_elem.get_text().strip())
                    cache_lyrics(query, lyrics)
                    logger.info(f"Lyrics scraped from {site['name']} for '{query}'")
                    return lyrics
            except Exception as e:
                logger.error(f"Error scraping {site['name']} for '{query}': {e}")
                continue
    
    return "❌ متأسفانه متن این آهنگ پیدا نشد.\n\nلطفاً نام آهنگ و خواننده را به صورت دستی در ربات جستجو کنید."

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
    await update.message.reply_text(
        f"سلام {user.first_name}! 👋\n\n"
        "برای دریافت متن آهنگ، روی دکمه «Lyrics» زیر آهنگ در کانال کلیک کنید.\n\n"
        "یا نام آهنگ و خواننده را برای من بفرستید."
    )

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.channel_post
    if not message or message.chat.id != CHANNEL_ID:
        return
    
    try:
        if message.audio:
            audio = message.audio
            caption = message.caption or ""
            song_title, artist = extract_song_info(caption, audio)
            
            # ایجاد deep link برای انتقال مستقیم به ربات
            deep_link = f"https://t.me/{BOT_USERNAME}?start=lyrics_{message.message_id}"
            
            # ایجاد دکمه Lyrics
            keyboard = [[InlineKeyboardButton("🎵 Lyrics", url=deep_link)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # ذخیره اطلاعات آهنگ برای استفاده بعدی
            context.chat_data[f"song_{message.message_id}"] = f"{song_title}|{artist}"
            
            # ارسال دکمه زیر آهنگ
            await message.reply_text(" ", reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"خطا در افزودن دکمه: {e}")

async def handle_start_with_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پردازش زمانی که کاربر از طریق دکمه Lyrics به ربات می‌آید"""
    user = update.effective_user
    
    if context.args and context.args[0].startswith('lyrics_'):
        message_id = context.args[0].replace('lyrics_', '')
        song_info = context.chat_data.get(f"song_{message_id}")
        
        if song_info:
            song_title, artist = song_info.split('|')
            
            # نمایش پیام در حال پردازش
            processing_msg = await update.message.reply_text(
                f"🔍 در حال جستجو برای:\n"
                f"🎵 {song_title}\n"
                f"👤 {artist}\n\n"
                f"لطفاً کمی صبر کنید..."
            )
            
            # دریافت متن آهنگ
            lyrics = await scrape_lyrics(song_title, artist)
            
            # حذف پیام در حال پردازش
            await processing_msg.delete()
            
            # ارسال متن آهنگ
            if len(lyrics) > 4000:
                # اگر متن خیلی طولانی است، به چند قسمت تقسیم کن
                parts = [lyrics[i:i+4000] for i in range(0, len(lyrics), 4000)]
                for i, part in enumerate(parts, 1):
                    await update.message.reply_text(
                        f"🎵 {song_title} - {artist}\n\n"
                        f"{part}\n\n"
                        f"📄 صفحه {i}/{len(parts)}"
                    )
            else:
                await update.message.reply_text(
                    f"🎵 {song_title} - {artist}\n\n"
                    f"{lyrics}"
                )
        else:
            await update.message.reply_text(
                "❌ اطلاعات آهنگ پیدا نشد.\n\n"
                "لطفاً نام آهنگ و خواننده را برای من بفرستید."
            )
    else:
        await start_command(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پردازش پیام‌های متنی برای جستجوی دستی"""
    if update.message and update.message.text and not update.message.text.startswith('/'):
        search_text = update.message.text
        
        processing_msg = await update.message.reply_text(
            f"🔍 در حال جستجو برای: {search_text}\n\nلطفاً صبر کنید..."
        )
        
        lyrics = await scrape_lyrics(search_text, "")
        
        await processing_msg.delete()
        
        if len(lyrics) > 4000:
            parts = [lyrics[i:i+4000] for i in range(0, len(lyrics), 4000)]
            for i, part in enumerate(parts, 1):
                await update.message.reply_text(
                    f"🎵 نتیجه جستجو: {search_text}\n\n"
                    f"{part}\n\n"
                    f"📄 صفحه {i}/{len(parts)}"
                )
        else:
            await update.message.reply_text(
                f"🎵 نتیجه جستجو: {search_text}\n\n"
                f"{lyrics}"
            )

def main() -> None:
    """راه‌اندازی ربات"""
    init_db()
    
    # ایجاد اپلیکیشن
    application = Application.builder().token(TOKEN).build()

    # اضافه کردن handlerها
    application.add_handler(CommandHandler("start", handle_start_with_lyrics))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.CHAT_TYPE_CHANNEL, handle_channel_post))

    # شروع ربات
    print("🤖 ربات Lyrics در حال اجرا است...")
    application.run_polling()

if __name__ == "__main__":
    main()
