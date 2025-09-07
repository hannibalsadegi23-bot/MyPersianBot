import os
import time
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CallbackContext, CallbackQueryHandler, MessageHandler, Filters
from googletrans import Translator

# تنظیمات اولیه
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("Error: BOT_TOKEN environment variable is not set!")
    exit(1)

app = Flask(__name__)

@app.route('/')
def home():
    return "ربات تلگرام در حال اجراست!"

@app.route('/health')
def health():
    return "OK", 200

def translate_text(text, dest='fa'):
    try:
        translator = Translator()
        translation = translator.translate(text, dest=dest)
        return translation.text
    except Exception as e:
        print(f"Translation error: {e}")
        return "خطا در ترجمه"

def handle_message(update: Update, context: CallbackContext):
    if update.channel_post:
        message = update.channel_post
        text = message.text
        if text:
            keyboard = [[InlineKeyboardButton("Translate", callback_data="translate")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                context.bot.send_message(
                    chat_id=message.chat_id,
                    text="👇 ترجمه فارسی",
                    reply_to_message_id=message.message_id,
                    reply_markup=reply_markup
                )
            except Exception as e:
                print(f"Error sending message: {e}")

def button_click(update: Update, context: CallbackContext):
    query = update.callback_query
    original_message = query.message.reply_to_message
    
    if original_message and original_message.text:
        translated_text = translate_text(original_message.text)
        query.answer(translated_text, show_alert=True)

def run_bot():
    print("Starting bot...")
    try:
        updater = Updater(TOKEN, use_context=True)
        dp = updater.dispatcher
        
        dp.add_handler(MessageHandler(Filters.text & Filters.chat_type.channel, handle_message))
        dp.add_handler(CallbackQueryHandler(button_click))
        
        updater.start_polling()
        print("Bot started successfully!")
        updater.idle()
    except Exception as e:
        print(f"Bot error: {e}")
        # به جای ری‌استارت بی‌نهایت، فقط لاگ می‌کنیم
        # اگه نیاز به ری‌استارت داری، از سیستم مدیریت رندر استفاده کن

if __name__ == "__main__":
    print("Starting application...")
    
    # استارت ربات توی یه ترد جدا
    bot_thread = Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # استارت اپلیکیشن Flask
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
