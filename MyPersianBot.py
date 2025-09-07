import os
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CallbackContext, CallbackQueryHandler, MessageHandler, Filters
from googletrans import Translator

# دریافت توکن از متغیر محیطی
TOKEN = os.environ.get('BOT_TOKEN')

# ایجاد برنامه Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "ربات تلگرام در حال اجراست!"

def translate_text(text, dest='fa'):
    translator = Translator()
    translation = translator.translate(text, dest=dest)
    return translation.text

def handle_message(update: Update, context: CallbackContext):
    if update.channel_post:
        message = update.channel_post
        text = message.text

        if text:
            keyboard = [
                [InlineKeyboardButton("Translate", callback_data=f"translate_{message.message_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            context.bot.send_message(
                chat_id=message.chat_id,
                text="👇 ترجمه فارسی",
                reply_to_message_id=message.message_id,
                reply_markup=reply_markup
            )

def button_click(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data

    if data.startswith("translate_"):
        original_message = query.message.reply_to_message

        if original_message.text:
            translated_text = translate_text(original_message.text)
            query.answer(translated_text, show_alert=True)

def run_bot():
    """تابع برای اجرای ربات تلگرام"""
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.text & Filters.chat_type.channel, handle_message))
    dp.add_handler(CallbackQueryHandler(button_click))

    updater.start_polling()
    print("ربات شروع به کار کرد...")
    updater.idle()

def run_flask():
    """تابع برای اجرای Flask"""
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    # اجرای ربات در یک thread جداگانه
    bot_thread = Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    # اجرای Flask در thread اصلی
    run_flask()
