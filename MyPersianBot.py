import logging
import os
import threading  # کتابخانه برای اجرای همزمان
from flask import Flask  # کتابخانه برای وب‌سرور
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.request import HTTPXRequest
from deep_translator import GoogleTranslator

# --- خواندن اطلاعات از متغیرهای محیطی Render ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = int(os.environ.get("YOUR_CHANNEL_ID"))
USERNAME = os.environ.get("YOUR_USERNAME")
CHANNEL_LINK = os.environ.get("YOUR_CHANNEL_LINK")

# --- ساخت آبجکت‌ها ---
translator = GoogleTranslator(source='auto', target='fa')

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- بخش وب‌سرور کوچک برای بیدار نگه داشتن ربات ---
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is alive!"

def run_flask():
    # این تابع وب‌سرور را روی پورت مناسب برای Render اجرا می‌کند
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
# ----------------------------------------------------


# --- تابع برای دستور /start ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("Contact", url=f"https://t.me/{USERNAME}"), InlineKeyboardButton("Channel", url=f"https://t.me/{CHANNEL_LINK}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(rf"سلام {user.mention_html()} عزیز،\nاین ربات برای استفاده های غریبه نیست.", reply_markup=reply_markup)


# --- تابع برای پیام‌های کانال ---
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.channel_post
    if message and message.chat.id == CHANNEL_ID and message.text:
        try:
            keyboard = [[InlineKeyboardButton("Translate", callback_data='translate_to_fa')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.edit_reply_markup(reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Could not add button: {e}")


# --- تابع برای کلیک روی دکمه ---
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data == 'translate_to_fa':
        try:
            original_text = query.message.text
            translated_text = translator.translate(original_text)
            
            if len(translated_text) <= 200:
                await query.answer(text=translated_text, show_alert=True)
            else:
                await query.answer(text="ترجمه طولانی است و به صورت خصوصی ارسال شد.")
                await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text=f"-- ترجمه متن طولانی --\n\n{translated_text}"
                )

        except Exception as e:
            logger.error(f"Translation failed: {e}", exc_info=True)
            await query.answer(text="خطا در ترجمه!", show_alert=True)


def main() -> None:
    # اجرای وب‌سرور در یک نخ جداگانه تا با ربات تداخل نداشته باشد
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # تنظیمات ربات
    request = HTTPXRequest(connect_timeout=10, read_timeout=10)
    application = Application.builder().token(TOKEN).request(request).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    print("Bot is running with web server to stay awake...")
    application.run_polling()


if __name__ == '__main__':
    main()
