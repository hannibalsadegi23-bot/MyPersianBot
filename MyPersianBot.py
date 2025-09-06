import logging
import os
import threading
from flask import Flask
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.request import HTTPXRequest
from telegram.error import BadRequest

# --- خواندن اطلاعات از متغیرهای محیطی Render ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CHANNEL_ID = int(os.environ.get("YOUR_CHANNEL_ID"))
USERNAME = os.environ.get("YOUR_USERNAME")
CHANNEL_LINK = os.environ.get("YOUR_CHANNEL_LINK")

# --- راه‌اندازی جمینی (با مدل FLASH برای سرعت و سهمیه بیشتر) ---
model = None
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    print("Gemini AI (Flash Model) configured successfully.")
except Exception as e:
    print(f"CRITICAL ERROR initializing Gemini: {e}")

# --- ساخت حافظه پنهان (Cache) برای ترجمه‌ها ---
translation_cache = {}

# --- تنظیمات لاگ و وب‌سرور ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)
@app.route('/')
def index(): return "Bot is alive and running!"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

# --- تابع ترجمه با هوش مصنوعی ---
def translate_with_gemini(text_to_translate):
    if not model:
        return "Error: AI model is not configured."
    try:
        # استفاده از دستورالعمل حرفه‌ای برای ترجمه باکیفیت
        prompt = f"""Your task is to translate the following English text into elegant and natural-sounding Persian.
        Pay close attention to the original tone, style, and nuance.
        The translation should be fluent and poetic, not a literal word-for-word translation.
        Provide only the final Persian translation without any extra comments.
        English Text: "{text_to_translate}"
        """
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini translation failed: {e}")
        return "Error during AI translation."

# --- توابع اصلی ربات ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("Contact", url=f"https://t.me/{USERNAME}"), InlineKeyboardButton("Channel", url=f"https://t.me/{CHANNEL_LINK}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(
        rf"Hello {user.mention_html()},\nThis bot is not for public use.",
        reply_markup=reply_markup
    )

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.channel_post
    if message and message.chat.id == CHANNEL_ID and message.text:
        try:
            keyboard = [[InlineKeyboardButton("Translate", callback_data='translate_to_fa')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.edit_reply_markup(reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Could not add button: {e}")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data == 'translate_to_fa':
        try:
            original_text = query.message.text
            
            # ۱. ابتدا در حافظه پنهان جستجو کن
            if original_text in translation_cache:
                translated_text = translation_cache[original_text]
                logger.info("Translation found in cache!")
            else:
                # ۲. اگر در حافظه نبود، از هوش مصنوعی ترجمه را بگیر
                translated_text = translate_with_gemini(original_text)
                # ۳. نتیجه را در حافظه ذخیره کن
                if translated_text and "Error" not in translated_text:
                    translation_cache[original_text] = translated_text
                    logger.info("Translation fetched from Gemini and cached.")

            if translated_text and len(translated_text) <= 200:
                await query.answer(text=translated_text, show_alert=True)
            elif translated_text:
                await query.answer(text="Error: Translated text is too long for a pop-up.", show_alert=True)
            else:
                await query.answer(text="The AI did not provide a response for this text.", show_alert=True)
        except Exception as e:
            logger.error(f"Callback handler failed: {e}", exc_info=True)
            try:
                await query.answer(text="Translation Error! The AI might have taken too long.", show_alert=True)
            except BadRequest:
                logger.error("Could not send error popup because the query was too old.")

# --- تابع اصلی اجرای ربات ---
def main() -> None:
    if not model:
        print("Bot is NOT running because Gemini AI failed to initialize.")
        return
        
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    request = HTTPXRequest(connect_timeout=10, read_timeout=10)
    application = Application.builder().token(TOKEN).request(request).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    print("Optimized AI Translator Bot is running on Render...")
    application.run_polling()

if __name__ == '__main__':
    main()
