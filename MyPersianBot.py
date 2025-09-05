import logging
import os
import threading
from flask import Flask
import google.genergenerativeai as genai
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

# --- راه‌اندازی جمینی (با مدل PRO) ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-pro-latest')
except Exception as e:
    print(f"Error initializing Gemini: {e}")
    model = None

# ... (بخش لاگ و وب‌سرور مثل قبل است) ...
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)
@app.route('/')
def index(): return "Bot is alive and running!"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

# --- تابع ترجمه (با دستورالعمل حرفه‌ای) ---
def translate_with_gemini(text_to_translate):
    if not model:
        return "خطا: مدل هوش مصنوعی به درستی تنظیم نشده است."
    try:
        prompt = f"""Your task is to translate the following English text into elegant and natural-sounding Persian.
        Pay close attention to the original tone, style, and nuance.
        The translation should be fluent and poetic, not a literal word-for-word translation.
        Provide only the final Persian translation without any extra comments or introductory phrases.

        English Text:
        "{text_to_translate}"
        """
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini translation failed: {e}")
        return "خطا در هنگام ترجمه با هوش مصنوعی."

# ... (توابع start_command و handle_channel_post مثل قبل است) ...
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("Contact", url=f"https://t.me/{USERNAME}"), InlineKeyboardButton("Channel", url=f"https://t.me/{CHANNEL_LINK}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(rf"سلام {user.mention_html()} عزیز،\nاین ربات برای استفاده های غریبه نیست.", reply_markup=reply_markup)

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.channel_post
    if message and message.chat.id == CHANNEL_ID and message.text:
        try:
            keyboard = [[InlineKeyboardButton("Translate", callback_data='translate_to_fa')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.edit_reply_markup(reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Could not add button: {e}")

# --- تابع کلیک روی دکمه (فقط با پاپ-آپ) ---
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data == 'translate_to_fa':
        try:
            original_text = query.message.text
            translated_text = translate_with_gemini(original_text)

            if translated_text and len(translated_text) <= 200:
                await query.answer(text=translated_text, show_alert=True)
            elif translated_text:
                await query.answer(text="خطا: متن ترجمه شده برای نمایش در پاپ-آپ بیش از حد طولانی است (بیشتر از ۲۰۰ کاراکتر).", show_alert=True)
            else:
                await query.answer(text="هوش مصنوعی پاسخی برای این متن ارائه نکرد.", show_alert=True)

        except Exception as e:
            logger.error(f"Callback handler failed: {e}", exc_info=True)
            try:
                # تلاش برای نمایش خطای عمومی در پاپ-آپ
                await query.answer(text="خطا در ترجمه! ممکن است پاسخ هوش مصنوعی طول کشیده باشد.", show_alert=True)
            except BadRequest:
                # اگر حتی نمایش خطای پاپ-آپ هم به دلیل تایم‌اوت شکست بخورد
                logger.error("Could not send error popup because the query was too old.")

# ... (تابع main مثل قبل است) ...
def main() -> None:
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    request = HTTPXRequest(connect_timeout=10, read_timeout=10)
    application = Application.builder().token(TOKEN).request(request).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    print("AI Translator Bot is running (High-Quality Pro Mode - Popup Only)...")
    application.run_polling()

if __name__ == '__main__':
    main()
