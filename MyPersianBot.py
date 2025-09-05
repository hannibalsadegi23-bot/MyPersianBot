import logging
import os
import threading
from flask import Flask
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.request import HTTPXRequest

# --- خواندن اطلاعات از متغیرهای محیطی Render ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CHANNEL_ID = int(os.environ.get("YOUR_CHANNEL_ID"))
USERNAME = os.environ.get("YOUR_USERNAME")
CHANNEL_LINK = os.environ.get("YOUR_CHANNEL_LINK")

# --- راه‌اندازی جمینی ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    print(f"Error initializing Gemini: {e}")
    model = None

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- بخش وب‌سرور برای بیدار نگه داشتن ربات ---
app = Flask(__name__)
@app.route('/')
def index():
    return "Bot is alive and running!"
def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

# --- تابع ترجمه با هوش مصنوعی جمینی ---
def translate_with_gemini(text_to_translate):
    if not model:
        return "خطا: مدل هوش مصنوعی به درستی تنظیم نشده است."
    try:
        prompt = f"Translate the following English text to Persian. Provide only the Persian translation, without any additional explanations or introductory phrases. The text is:\n\n\"{text_to_translate}\""
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini translation failed: {e}")
        return "خطا در هنگام ترجمه با هوش مصنوعی."

# --- توابع اصلی ربات ---
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

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data == 'translate_to_fa':
        await query.answer(text="در حال ارسال به هوش مصنوعی...")
        try:
            original_text = query.message.text
            translated_text = translate_with_gemini(original_text)
            
            if len(translated_text) <= 200:
                await query.answer(text=translated_text, show_alert=True)
            else:
                await query.answer(text="ترجمه طولانی است و به صورت خصوصی ارسال شد.")
                await context.bot.send_message(chat_id=query.from_user.id, text=f"-- ترجمه با هوش مصنوعی --\n\n{translated_text}")
        except Exception as e:
            logger.error(f"Callback handler failed: {e}", exc_info=True)
            await query.answer(text="خطا در ترجمه!", show_alert=True)

def main() -> None:
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    request = HTTPXRequest(connect_timeout=10, read_timeout=10)
    application = Application.builder().token(TOKEN).request(request).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    print("AI Translator Bot is running on Render...")
    application.run_polling()

if __name__ == '__main__':
    main()
