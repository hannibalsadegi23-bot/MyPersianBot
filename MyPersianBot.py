import logging
import os
import threading
from flask import Flask
from deep_translator import GoogleTranslator  # <--- بازگشت به مترجم استاندارد
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.request import HTTPXRequest
from telegram.error import BadRequest

# --- خواندن اطلاعات از متغیرهای محیطی Render ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = int(os.environ.get("YOUR_CHANNEL_ID"))
USERNAME = os.environ.get("YOUR_USERNAME")
CHANNEL_LINK = os.environ.get("YOUR_CHANNEL_LINK")

# --- راه‌اندازی مترجم استاندارد گوگل ---
try:
    translator = GoogleTranslator(source='auto', target='fa')
    print("Google Translator configured successfully.")
except Exception as e:
    print(f"CRITICAL ERROR initializing Google Translator: {e}")
    translator = None

# --- تنظیمات لاگ و وب‌سرور ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)
@app.route('/')
def index(): return "Bot is alive and running!"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

# --- تابع ترجمه ---
def translate_standard(text_to_translate):
    if not translator:
        return "Error: Translator is not configured."
    try:
        return translator.translate(text_to_translate)
    except Exception as e:
        logger.error(f"Google Translate failed: {e}")
        return "Error during translation."

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
            translated_text = translate_standard(original_text)

            if translated_text and len(translated_text) <= 200:
                await query.answer(text=translated_text, show_alert=True)
            elif translated_text:
                await query.answer(text="Error: Translated text is too long for a pop-up.", show_alert=True)
            else:
                await query.answer(text="The translator did not provide a response.", show_alert=True)
        except Exception as e:
            logger.error(f"Callback handler failed: {e}", exc_info=True)
            await query.answer(text="Translation Error!", show_alert=True)

# --- تابع اصلی اجرای ربات ---
def main() -> None:
    if not translator:
        print("Bot is NOT running because the translator failed to initialize.")
        return
        
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    request = HTTPXRequest(connect_timeout=10, read_timeout=10)
    application = Application.builder().token(TOKEN).request(request).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    print("Standard Translator Bot is running on Render...")
    application.run_polling()

if __name__ == '__main__':
    main()
